#!/usr/bin/env bash
# Deploy del feature OCR de combustible (issues #15-#19).
# Ejecutar con: sudo bash deploy_fuel_ocr.sh
#
# Pasos:
#   1. Pre-flight checks (estado actual, conectividad DB, permisos).
#   2. Backup completo de la DB con mysqldump.
#   3. Pull de main y checkout al commit objetivo.
#   4. Edicion de nginx para agregar /fuel-image al proxy_pass.
#   5. Migracion de la DB (combustible_imagenes + proveedor INTERNO).
#   6. Verificacion de la migracion.
#   7. Build del frontend (npm run build).
#   8. Deploy del frontend (rsync del dist/ al webroot).
#   9. Restart del backend (systemctl restart viajes).
#  10. Health check + smoke contra el API.
#
# Flags:
#   --skip-frontend-build  Saltea el build y deploy del frontend (util si
#                          el front ya esta al dia y solo cambia el backend).
#   --skip-backend-restart No reinicia el backend (util para validar solo DB).
#   --target-commit SHA   Checkea este SHA en vez del HEAD de origin/main.
#   --no-smoke            No corre el smoke al final.
#   --auto                No pregunta, asume "si" a todo (para CI o debug).
#   --no-color            Desactiva colores en output.
#
# Salida: logging a /var/log/viajes_fgpy_deploy_YYYYMMDD_HHMMSS.log
set -euo pipefail

# --- Constantes ---------------------------------------------------------------

PROJECT_DIR="/var/www/html/django/viajes_fgpy"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
NGINX_SITE="/etc/nginx/sites-enabled/viajes.forestalparaguay.com"
SERVICE_NAME="viajes.service"
LOG_DIR="/var/log"

# Colores (desactivables con --no-color)
if [[ "${NO_COLOR:-0}" == "1" ]] || ! [[ -t 1 ]]; then
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_RESET=""
else
  C_RED=$'\033[0;31m'; C_GREEN=$'\033[0;32m'; C_YELLOW=$'\033[1;33m'
  C_BLUE=$'\033[0;34m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
fi

# --- Flags --------------------------------------------------------------------

SKIP_FRONTEND_BUILD=0
SKIP_BACKEND_RESTART=0
NO_SMOKE=0
AUTO=0
TARGET_COMMIT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-frontend-build) SKIP_FRONTEND_BUILD=1; shift ;;
    --skip-backend-restart) SKIP_BACKEND_RESTART=1; shift ;;
    --no-smoke) NO_SMOKE=1; shift ;;
    --auto) AUTO=1; shift ;;
    --no-color) NO_COLOR=1; shift ;;
    --target-commit) TARGET_COMMIT="$2"; shift 2 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Flag desconocida: $1" >&2; exit 2 ;;
  esac
done
[[ "${NO_COLOR:-0}" == "1" ]] && C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_RESET=""

# --- Logging ------------------------------------------------------------------

LOG_FILE="$LOG_DIR/viajes_fgpy_deploy_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

log_step() { echo -e "${C_BOLD}${C_BLUE}==>${C_RESET} ${C_BOLD}$1${C_RESET}"; }
log_ok()   { echo -e "   ${C_GREEN}OK${C_RESET} $1"; }
log_warn() { echo -e "   ${C_YELLOW}WARN${C_RESET} $1"; }
log_err()  { echo -e "   ${C_RED}ERR${C_RESET} $1"; }

confirm() {
  local prompt="$1"
  if [[ "$AUTO" == "1" ]]; then
    echo -e "   ${C_YELLOW}[auto]${C_RESET} $prompt -> y"
    return 0
  fi
  local reply
  read -r -p "   $(echo "$prompt") [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

# --- Pre-flight ---------------------------------------------------------------

log_step "Pre-flight checks"

# sudo
if ! sudo -n true 2>/dev/null; then
  log_err "Se necesita sudo sin password. Reabrir con 'sudo bash $0' o configurar NOPASSWD."
  exit 1
fi
log_ok "sudo disponible"

# Directorios
for d in "$PROJECT_DIR" "$BACKEND_DIR" "$FRONTEND_DIR"; do
  if ! [[ -d "$d" ]]; then
    log_err "Directorio faltante: $d"
    exit 1
  fi
done
log_ok "Project dir existe"

# DB env
ENV_FILE="$BACKEND_DIR/.env"
if ! [[ -r "$ENV_FILE" ]]; then
  log_err "No se puede leer $ENV_FILE. Permisos?"
  exit 1
fi
DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)
if [[ -z "$DATABASE_URL" ]]; then
  log_err "DATABASE_URL no encontrado en $ENV_FILE"
  exit 1
fi
log_ok "DATABASE_URL leido"

# Parsear DATABASE_URL (mysql+mysqlconnector://user:pass@host/db)
DB_USER=$(echo "$DATABASE_URL" | sed -E 's|^mysql\+mysqlconnector://([^:]+):.*|\1|')
DB_PASS=$(echo "$DATABASE_URL" | sed -E 's|^mysql\+mysqlconnector://[^:]+:([^@]+)@.*|\1|')
DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|^.*@([^/]+)/.*|\1|')
DB_NAME=$(echo "$DATABASE_URL" | sed -E 's|^.*/([^?]+)(\?.*)?$|\1|')
log_ok "DB destino: $DB_HOST / $DB_NAME (user $DB_USER)"

# Conexion a DB
if ! mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" -e "SELECT 1;" "$DB_NAME" >/dev/null 2>&1; then
  log_err "No se pudo conectar a $DB_HOST/$DB_NAME con user $DB_USER"
  exit 1
fi
log_ok "Conexion a DB OK"

# Estado de git
cd "$PROJECT_DIR"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  log_err "$PROJECT_DIR no es un repo git"
  exit 1
fi
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
CURRENT_COMMIT=$(git rev-parse --short HEAD)
log_ok "Branch actual: $CURRENT_BRANCH @ $CURRENT_COMMIT"

# Target commit
git fetch origin main >/dev/null 2>&1 || log_warn "fetch de origin/main fallo"
if [[ -z "$TARGET_COMMIT" ]]; then
  TARGET_COMMIT=$(git rev-parse origin/main 2>/dev/null || echo "")
fi
if [[ -z "$TARGET_COMMIT" ]]; then
  log_err "No se pudo determinar el commit objetivo. Usar --target-commit SHA."
  exit 1
fi
log_ok "Commit objetivo: $TARGET_COMMIT"

# Service estado
SERVICE_ACTIVE=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "unknown")
log_ok "Servicio $SERVICE_NAME: $SERVICE_ACTIVE"

# --- 2. Backup de la DB -------------------------------------------------------

log_step "Backup de la DB"

BACKUP_DIR="/srv/backups/viajes_fgpy"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/pre_fuel_ocr_$(date +%Y%m%d_%H%M%S).sql"
BACKUP_SHA="${BACKUP_FILE}.sha256"

echo "   Destino: $BACKUP_FILE"
confirm "Continuar con mysqldump?" || { log_warn "Backup cancelado por el usuario"; exit 0; }

mysqldump -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" \
  --single-transaction --routines --triggers --events \
  --default-character-set=utf8mb4 \
  "$DB_NAME" > "$BACKUP_FILE" 2>"$BACKUP_FILE.err"

BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE")
if [[ "$BACKUP_SIZE" -lt 1000 ]]; then
  log_err "Backup demasiado pequeno ($BACKUP_SIZE bytes). Algo salio mal."
  cat "$BACKUP_FILE.err"
  exit 1
fi
log_ok "Backup OK: $BACKUP_FILE ($BACKUP_SIZE bytes)"

# SHA-256
sha256sum "$BACKUP_FILE" | cut -d' ' -f1 > "$BACKUP_SHA"
log_ok "SHA-256: $(cat "$BACKUP_SHA")"

# --- 3. Pull de main ----------------------------------------------------------

log_step "Pull de main"

confirm "git pull origin main + checkout a $TARGET_COMMIT?" || { log_warn "Pull cancelado"; exit 0; }

git pull --ff-only origin main
git checkout "$TARGET_COMMIT"
NEW_COMMIT=$(git rev-parse --short HEAD)
log_ok "Ahora en $NEW_COMMIT"

# --- 4. Edicion de nginx ------------------------------------------------------

log_step "Edicion de nginx: agregar /fuel-image al proxy_pass"

if [[ -r "$NGINX_SITE" ]]; then
  log_ok "Nginx site legible: $NGINX_SITE"
else
  log_err "No se puede leer $NGINX_SITE"
  exit 1
fi

if grep -q "fuel-image|/api|/api)(/.*)?\\\$" "$NGINX_SITE" || grep -E "fuel-image\|api" "$NGINX_SITE" >/dev/null; then
  log_ok "fuel-image ya esta en la lista del proxy_pass"
else
  log_warn "fuel-image NO esta en la lista. Aplicando cambio..."
  # Reemplaza la regex, agregando |fuel-image| antes de |api
  # La regex evita capturar el `^` (anchor) y la apertura `(`, asi el
  # reemplazo es solo el grupo de alternativas + el grupo del final.
  sudo sed -i -E 's|(\([^)]+\|api\))(\(/.*\)\?\$)|\1fuel-image\2|' "$NGINX_SITE"
  log_ok "Regex actualizada"
fi

# Mostrar el location resultante
echo "   --- location actualizado ---"
grep -A 6 "^    location ~" "$NGINX_SITE" | head -10
echo "   ---"

# Validar config
log_step "Validar config de nginx"
if ! sudo nginx -t; then
  log_err "Config de nginx invalida. Revirtiendo..."
  # No revertimos automaticamente; el usuario decide
  exit 1
fi
log_ok "Config valida"

# Recargar
confirm "Recargar nginx?" || { log_warn "Reload cancelado"; exit 0; }
sudo systemctl reload nginx
log_ok "nginx recargado"

# --- 5. Migracion de la DB ---------------------------------------------------

log_step "Migracion de la DB"

MIGRATION_FILE="$BACKEND_DIR/migrations/20260731_add_combustible_imagenes.sql"
VERIFY_FILE="$BACKEND_DIR/migrations/20260731_verify_combustible_imagenes.sql"

if [[ -r "$MIGRATION_FILE" ]]; then
  log_ok "Migracion legible: $MIGRATION_FILE"
else
  log_err "Migracion no encontrada"
  exit 1
fi

echo "   --- Primeras 30 lineas de la migracion ---"
head -30 "$MIGRATION_FILE"
echo "   ---"

confirm "Aplicar migracion?" || { log_warn "Migracion cancelada"; exit 0; }

mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$MIGRATION_FILE"
log_ok "Migracion aplicada"

# --- 6. Verificacion ---------------------------------------------------------

log_step "Verificacion de la migracion"

if [[ -r "$VERIFY_FILE" ]]; then
  log_ok "Verificacion legible"
else
  log_err "Script de verificacion no encontrado"
  exit 1
fi

confirm "Correr verificacion?" || { log_warn "Verificacion cancelada"; exit 0; }

echo "   --- Output del verify ---"
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" --table "$DB_NAME" < "$VERIFY_FILE"
echo "   ---"

# Capturar el id del INTERNO
INTERNAL_ID=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" -BNe \
  "SELECT id FROM $DB_NAME.proveedor WHERE LOWER(razon_social) LIKE '%interno%' LIMIT 1;" 2>/dev/null || echo "")
if [[ -n "$INTERNAL_ID" ]]; then
  echo
  echo "   ${C_BOLD}==> INTERNO PROVIDER ID = ${C_GREEN}${INTERNAL_ID}${C_RESET}    <=="
  echo "   (anotar este id en el README del deploy, ver backend/migrations/README)"
  echo
else
  log_warn "No se pudo capturar el id del INTERNO. Verificar manualmente."
fi

# --- 7. Build del frontend ---------------------------------------------------

if [[ "$SKIP_FRONTEND_BUILD" == "1" ]]; then
  log_step "Build del frontend: salteado (--skip-frontend-build)"
else
  log_step "Build del frontend"
  cd "$FRONTEND_DIR"

  confirm "Correr npm ci + npm run build?" || { log_warn "Build cancelado"; exit 0; }

  npm ci --no-audit --no-fund 2>&1 | tail -5
  log_ok "deps instaladas"

  npm run build 2>&1 | tail -10
  log_ok "Build OK"

  # Validar que se genero el dist
  if [[ ! -d "$FRONTEND_DIR/dist" ]]; then
    log_err "No se genero $FRONTEND_DIR/dist"
    exit 1
  fi
  DIST_SIZE=$(du -sh "$FRONTEND_DIR/dist" | cut -f1)
  log_ok "dist/ generado ($DIST_SIZE)"

  # Deploy del frontend
  log_step "Deploy del frontend al webroot"
  WEBROOT="/var/www/html/django/viajes_fgpy/frontend"

  # Backup del frontend actual
  if [[ -d "$WEBROOT/index.html" ]] || [[ -f "$WEBROOT/index.html" ]]; then
    BACKUP_WEBROOT="/var/www/html/django/viajes_fgpy/frontend.before-fuel-ocr-$(date +%Y%m%d-%H%M%S)"
    log_warn "Backup del frontend actual a $BACKUP_WEBROOT"
    sudo cp -r "$WEBROOT" "$BACKUP_WEBROOT"
  fi

  # Sync dist/ al webroot (preserva archivos no presentes en dist/, p.ej. sw.js)
  log_step "Sync dist/ -> $WEBROOT"
  sudo rsync -a --delete \
    --exclude='sw.js' --exclude='workbox-*.js' --exclude='manifest.webmanifest' \
    "$FRONTEND_DIR/dist/" "$WEBROOT/"
  log_ok "Frontend deployado"

  # Actualizar DEPLOYED_COMMIT
  echo "$NEW_COMMIT" | sudo tee "$PROJECT_DIR/DEPLOYED_COMMIT" >/dev/null
  log_ok "DEPLOYED_COMMIT actualizado a $NEW_COMMIT"
fi

# --- 9. Restart del backend --------------------------------------------------

if [[ "$SKIP_BACKEND_RESTART" == "1" ]]; then
  log_step "Restart del backend: salteado (--skip-backend-restart)"
else
  log_step "Restart del backend"
  confirm "Reiniciar $SERVICE_NAME?" || { log_warn "Restart cancelado"; exit 0; }

  sudo systemctl restart "$SERVICE_NAME"
  sleep 2

  # Health check
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_ok "Servicio activo"
  else
    log_err "Servicio NO activo tras restart. Revisar journal."
    sudo journalctl -u "$SERVICE_NAME" -n 30 --no-pager
    exit 1
  fi

  # Probar health endpoint
  for i in 1 2 3 4 5; do
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8003/api/admin/health 2>/dev/null | grep -q "200\|404"; then
      log_ok "Health check responde (intento $i)"
      break
    fi
    log_warn "Health check no respondio aun (intento $i/5)"
    sleep 2
  done
fi

# --- 10. Smoke ----------------------------------------------------------------

if [[ "$NO_SMOKE" == "1" ]]; then
  log_step "Smoke: salteado (--no-smoke)"
else
  log_step "Smoke test"
  echo
  echo "   Para correr el smoke hace falta un JWT valido."
  echo "   Si queres, corré manualmente:"
  echo "     python $BACKEND_DIR/scripts/smoke_fuel_image.py \\"
  echo "       --api-url https://viajes.forestalparaguay.com/api \\"
  echo "       --token <JWT> \\"
  echo "       --ticket /ruta/a/ticket.jpg \\"
  echo "       --remito /ruta/a/remito.jpg \\"
  echo "       --skip-confirm"
  echo
fi

# --- Resumen -----------------------------------------------------------------

log_step "Deploy finalizado"
echo
echo "   Commit desplegado:  $NEW_COMMIT"
echo "   DB backup:           $BACKUP_FILE"
echo "   DB SHA-256:          $(cat "$BACKUP_SHA")"
echo "   INTERNO provider id: ${INTERNAL_ID:-NO DETECTADO}"
echo "   Nginx:               recargado"
echo "   Backend:             $SERVICE_NAME $([[ "$SKIP_BACKEND_RESTART" == "1" ]] && echo "(no reiniciado)" || echo "reiniciado")"
echo "   Frontend:            $([[ "$SKIP_FRONTEND_BUILD" == "1" ]] && echo "(salteado)" || echo "deployado")"
echo "   Log:                 $LOG_FILE"
echo
echo "   ${C_GREEN}Listo para probar desde un celular.${C_RESET}"
