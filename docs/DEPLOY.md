# Deploy de `registro_viajes_fgpy` (viajes.forestalparaguay.com)

Guía paso a paso para deployar la app en el server `fasa_195` (192.168.0.195). Cualquiera debería poder seguirla sin conocer el proyecto.

---

## Tabla de contenidos

1. [Arquitectura del deploy](#arquitectura-del-deploy)
2. [Requisitos previos](#requisitos-previos)
3. [Estructura en el server](#estructura-en-el-server)
4. [Deploy con el script automático](#deploy-con-el-script-automático)
5. [Deploy manual paso a paso](#deploy-manual-paso-a-paso)
6. [Recuperación si algo se rompe](#recuperación-si-algo-se-rompe)
7. [Troubleshooting](#troubleshooting)
8. [Variables de entorno importantes](#variables-de-entorno-importantes)
9. [Endpoints útiles](#endpoints-útiles)
10. [Cómo mergear cambios del script de deploy](#cómo-mergear-cambios-del-script-de-deploy)

---

## Arquitectura del deploy

```
┌─────────────────────────────────────────────────────────┐
│ fasa_195 (192.168.0.195)                                │
│                                                         │
│  /var/www/html/django/viajes_fgpy/       ← WEBROOT      │
│    ├── backend/                                        │
│    │   ├── .env                  (preservado local)     │
│    │   ├── venv/                 (Python deps)          │
│    │   ├── migrations/                                   │
│    │   ├── main.py                                      │
│    │   └── scripts/deploy_fuel_ocr.sh                   │
│    ├── frontend/                                        │
│    │   ├── index.html            (build nuevo)          │
│    │   ├── assets/                                      │
│    │   ├── sw.js                                         │
│    │   ├── registerSW.js                                 │
│    │   ├── src/                  (código fuente Vite)   │
│    │   ├── node_modules/         (npm deps)             │
│    │   └── package.json                                  │
│    └── ...                                              │
│                                                         │
│  /var/www/html/django/viajes_fgpy_repo/   ← CLONE       │
│    └── .git/                    (depth 1 de main)      │
│                                                         │
│  /var/www/html/django/viajes_fgpy-data/   ← DATA        │
│    ├── images/                   (OCR tickets/remitos)  │
│    └── uv-cache/                                        │
│                                                         │
│  /srv/backups/viajes_fgpy/db/   ← BACKUPS DB           │
│    └── pre_fuel_ocr_*.sql.gz                           │
│                                                         │
│  systemd: viajes.service → uvicorn :8003 (127.0.0.1)   │
│  nginx: 443 (SSL Let's Encrypt) → proxy_pass :8003     │
│        y root /var/www/html/django/viajes_fgpy/frontend│
└─────────────────────────────────────────────────────────┘

┌──────────────────────────────────────┐
│ Hostinger (srv1723.hstgr.io)         │
│  MySQL: u604652499_fgpy              │
└──────────────────────────────────────┘
```

**Componentes clave:**

| Componente | Dónde | Notas |
|---|---|---|
| Código fuente | GitHub `oscarvogel/registro_viajes_fgpy` | Rama `main`. Clone `--depth 1` en el server. |
| Backend | `viajes.service` con `uvicorn :8003` | User `www-data`, group `www-data`. |
| Frontend | nginx sirve desde `/var/www/html/django/viajes_fgpy/frontend/` | **No** desde `frontend/dist/`. El script sincroniza el contenido de `dist/` a la raíz. |
| Base de datos | Hostinger `srv1723.hstgr.io` | NO está en fasa_195. Password URL-encoded en el `.env`. |
| Imágenes OCR | `/var/www/html/django/viajes_fgpy-data/images/` | Tokens con TTL 24h. |
| Cert SSL | Let's Encrypt vía certbot | Renovación automática. |
| Backups DB | `/srv/backups/viajes_fgpy/db/` | El script los crea antes de cada deploy. |

---

## Requisitos previos

Antes de hacer deploy, asegurate de tener:

- Acceso SSH al server: `ssh ferreteria@192.168.0.195` con llave `~/.ssh/fasa_195`
- `sudo` (pide password, no NOPASSWD)
- `git`, `node`, `npm`, `python3`, `mysql-client` instalados en el server
- Acceso al repo en GitHub (público: `https://github.com/oscarvogel/registro_viajes_fgpy.git`)
- Que el branch con los cambios esté mergeado a `main` (deploys sacan de `main`)
- El archivo `backend/.env` ya configurado en el server con `DATABASE_URL` y secretos

---

## Estructura en el server

Verificá antes del primer deploy que existan:

```bash
ls -la /var/www/html/django/viajes_fgpy/         # webroot
ls -la /var/www/html/django/viajes_fgpy/backend/  # backend
cat /var/www/html/django/viajes_fgpy/backend/.env # DB creds, secrets
ls -la /etc/nginx/sites-enabled/viajes.forestalparaguay.com  # nginx config
systemctl status viajes.service                   # backend systemd
```

Si `viajes_fgpy_repo/` no existe, el script lo crea solo con el primer deploy.

---

## Deploy con el script automático

**El script vive en el repo y se sube al server como `ferreteria`. NO se ejecuta solo, lo tiene que correr el operador con sudo.**

### Paso 1 — Hacer merge de los cambios a `main`

En tu Windows, con todos los PRs mergeados:

```powershell
cd D:\notebook\active\registro_viajes_fgpy
git checkout main
git pull origin main
```

### Paso 2 — Subir el script de deploy al server (solo si cambió)

```powershell
scp -i $env:USERPROFILE\.ssh\fasa_195 `
  D:\notebook\active\registro_viajes_fgpy\backend\scripts\deploy_fuel_ocr.sh `
  ferreteria@192.168.0.195:/var/www/html/django/viajes_fgpy/scripts/deploy_fuel_ocr.sh
```

(El script en el server tiene que tener `+x`. Si no: `chmod +x` desde una sesión SSH con sudo.)

### Paso 3 — Conectarse al server y correr el script

```powershell
ssh ferreteria@192.168.0.195
```

Una vez en el server:

```bash
sudo bash /var/www/html/django/viajes_fgpy/scripts/deploy_fuel_ocr.sh
```

El script va a ir preguntando en cada paso. Para modo no-interactivo, agregar `--auto`.

### Lo que hace el script (10 pasos, fail-fast en cada uno)

1. **Pre-flight**: chequea `sudo`, conectividad a Hostinger, estado de `viajes.service`.
2. **Backup DB**: `mysqldump` a `/srv/backups/viajes_fgpy/db/pre_fuel_ocr_<timestamp>.sql` con SHA-256.
3. **Sync del repo al webroot**: clone/fetch en `viajes_fgpy_repo/`, rsync al webroot preservando `backend/.env`, `venv/`, `node_modules/`, `dist/`.
4. **Patch de nginx**: agrega `|fuel-image|` al `location ~` del proxy_pass (solo si no está). Backup del nginx antes.
5. **Migración de la DB**: corre `backend/migrations/20260731_add_combustible_imagenes.sql` (idempotente, crea tabla `combustible_imagenes` y proveedor INTERNO).
6. **Verificación de la migración**: confirma tabla, índices, FK y proveedor INTERNO (típicamente id=29). Anotar el id del INTERNO en este doc.
7. **Setup de Python**: crea `venv/` con `pip install -r requirements.txt` si no existe.
8. **Build del frontend**: `npm ci` + `npm run build` (corre como root por permisos de `/var/.npm/`). Después `chown www-data:www-data`.
9. **Sync del dist al frontend**: copia el contenido de `dist/` a la raíz de `frontend/` (sin `--delete` para no romper fuentes).
10. **Restart del backend**: `systemctl restart viajes.service`.
11. **Health check**: `curl /api/admin/health`.

### Flags del script

| Flag | Efecto |
|---|---|
| `--auto` | Modo no-interactivo, asume "sí" en todas las confirmaciones |
| `--no-smoke` | No corre el smoke test al final |
| `--skip-frontend-build` | Saltea `npm ci` y `npm run build` (útil si solo cambia backend) |
| `--skip-backend-restart` | No reinicia el backend |
| `--target-commit SHA` | Deploya un SHA específico en vez de HEAD de main |
| `--no-color` | Desactiva colores en la salida |

---

## Deploy manual paso a paso

Si el script falla o necesitás hacer un deploy quirúrgico, seguí estos pasos en orden.

### 1. Backup de la DB (SIEMPRE antes de cualquier cambio)

```bash
mysqldump -h srv1723.hstgr.io -u u604652499_fgpy -p"${DB_PASS}" \
  --single-transaction --routines --triggers --events \
  --default-character-set=utf8mb4 \
  u604652499_fgpy | gzip > /srv/backups/viajes_fgpy/db/manual_$(date +%Y%m%d_%H%M%S).sql.gz
```

La password en `.env` está URL-encoded (`CLAVE_URL_ENCODED`). Acá va la **decodificada** (`"${DB_PASS}"`).

### 2. Pull del código

Si ya tenés `.git/` en el webroot:

```bash
cd /var/www/html/django/viajes_fgpy
sudo git fetch --depth 1 origin main
sudo git reset --hard origin/main
sudo chown -R www-data:www-data /var/www/html/django/viajes_fgpy
```

Si NO tenés `.git/` (primer deploy o deploy tradicional):

```bash
sudo mkdir -p /var/www/html/django/viajes_fgpy_repo
sudo chown ferreteria:ferreteria /var/www/html/django/viajes_fgpy_repo
cd /var/www/html/django/viajes_fgpy_repo
git clone --depth 1 -b main https://github.com/oscarvogel/registro_viajes_fgpy.git .
sudo rsync -a \
  --chown=www-data:www-data \
  --exclude='backend/.env' \
  --exclude='backend/venv/' \
  --exclude='frontend/node_modules/' \
  --exclude='frontend/dist/' \
  /var/www/html/django/viajes_fgpy_repo/ /var/www/html/django/viajes_fgpy/
```

### 3. venv y deps (solo si no existen)

```bash
if [ ! -d /var/www/html/django/viajes_fgpy/backend/venv ]; then
  cd /var/www/html/django/viajes_fgpy/backend
  sudo -u www-data python3 -m venv venv
  sudo -u www-data venv/bin/pip install -r requirements.txt
fi
```

### 4. Build del frontend

```bash
cd /var/www/html/django/viajes_fgpy/frontend
if [ ! -d node_modules ]; then
  sudo npm ci
fi
sudo npm run build
sudo rsync -a dist/ ./
sudo rm -rf dist
sudo chown -R www-data:www-data /var/www/html/django/viajes_fgpy/frontend
```

### 5. Patch de nginx (si es la primera vez con el feature OCR)

```bash
sudo cp /etc/nginx/sites-enabled/viajes.forestalparaguay.com /etc/nginx/sites-enabled/viajes.forestalparaguay.com.bak.$(date +%s)
# Esto agrega |fuel-image| al location del proxy_pass
sudo sed -i 's#|api)(/.\*)?\$#|api|fuel-image)(/.*)?\$#' /etc/nginx/sites-enabled/viajes.forestalparaguay.com
sudo nginx -t
sudo systemctl reload nginx
```

**Verificar manualmente** que la línea quedó como:
```
location ~ ^/(empleados|proveedores|...|api|fuel-image)(/.*)?$ {
```

### 6. Migración de la DB

```bash
mysql -h srv1723.hstgr.io -u u604652499_fgpy -p"${DB_PASS}" \
  u604652499_fgpy < /var/www/html/django/viajes_fgpy/backend/migrations/20260731_add_combustible_imagenes.sql
```

(La migración es idempotente — correrla dos veces no rompe nada.)

### 7. Restart del backend

```bash
sudo systemctl restart viajes.service
sudo systemctl status viajes.service
```

### 8. Health check

```bash
curl -sS -w '\nHTTP %{http_code}\n' https://viajes.forestalparaguay.com/api/admin/health
```

Debería devolver `{"status":"ok","timestamp":...}`. Si devuelve HTML, el nginx está mal configurado (ver [Troubleshooting](#troubleshooting)).

---

## Recuperación si algo se rompe

### Si el backend no responde datos del frontend

Probablemente nginx está mal configurado. Verificá:

```bash
sudo sed -n '5p' /etc/nginx/sites-enabled/viajes.forestalparaguay.com
```

Tiene que verse `...|api|fuel-image)(/.*)?$`. Si está roto (ej. `...|api)fuel-image...` o falta `|fuel-image|`):

```bash
sudo sed -i 's#|api)(/.\*)?\$#|api|fuel-image)(/.*)?\$#' /etc/nginx/sites-enabled/viajes.forestalparaguay.com
sudo nginx -t
sudo systemctl reload nginx
```

Si el sed de arriba falla o no matchea, restaurar el backup:

```bash
ls /etc/nginx/sites-enabled/viajes.forestalparaguay.com.bak.*
sudo cp /etc/nginx/sites-enabled/viajes.forestalparaguay.com.bak.<timestamp> /etc/nginx/sites-enabled/viajes.forestalparaguay.com
sudo systemctl reload nginx
```

### Si el frontend quedó sin `node_modules/`, `package.json`, `src/` (rsync --delete mal usado)

Restaurar desde el repo auxiliar:

```bash
sudo rsync -a /var/www/html/django/viajes_fgpy_repo/frontend/ /var/www/html/django/viajes_fgpy/frontend/
sudo chown -R www-data:www-data /var/www/html/django/viajes_fgpy/frontend
cd /var/www/html/django/viajes_fgpy/frontend
sudo rm -rf node_modules
sudo npm ci
sudo npm run build
sudo rsync -a dist/ ./
sudo rm -rf dist
sudo chown -R www-data:www-data /var/www/html/django/viajes_fgpy/frontend
sudo systemctl restart viajes.service
```

### Si el backend crashea al iniciar

Ver los logs:

```bash
sudo journalctl -u viajes.service -n 50 --no-pager
```

Errores comunes:
- `ModuleNotFoundError`: faltan deps de Python → `pip install -r requirements.txt`
- `Can't connect to MySQL`: DB caída o credenciales mal en `.env`
- `KeyError` en alguna config: revisar variables de entorno en `.env`

### Rollback completo del código (volver al commit anterior)

```bash
cd /var/www/html/django/viajes_fgpy
# Si tenés .git/, es directo
sudo git log --oneline -5
sudo git reset --hard <commit-anterior>
sudo systemctl restart viajes.service
```

### Rollback de la DB

```bash
gunzip < /srv/backups/viajes_fgpy/db/pre_fuel_ocr_<timestamp>.sql.gz | \
  mysql -h srv1723.hstgr.io -u u604652499_fgpy -p"${DB_PASS}" u604652499_fgpy
```

⚠️ **Esto borra los cambios hechos después del backup.** Hacelo solo si sabés lo que estás haciendo.

---

## Troubleshooting

### El deploy falla con "Access denied" en MySQL

La password en el `.env` está URL-encoded (`CLAVE_URL_ENCODED` donde `%40` = `@`). SQLAlchemy la decodifica automáticamente, pero `mysql` CLI y `mysqldump` esperan la literal.

**Decodificar antes de usar:**

```bash
# En bash
DB_PASS=$(printf '%b' "${DB_PASS//%/\\x}")
```

O pasar la password literal directo (sin URL-encoding).

### El script aborta con exit code 24 del rsync

`rsync --delete` está borrando archivos del destino. **Nunca uses `--delete` con directorios donde hay archivos fuente Y de build mezclados.** El script definitivo no usa `--delete`. Si tu copia local lo tiene, sacalo.

### npm falla con "cannot write to /var/.npm/_logs"

`www-data` no puede escribir en `/var/.npm/`. Corré npm como `root` y después `chown` el resultado:

```bash
sudo npm ci --prefix /var/www/html/django/viajes_fgpy/frontend
sudo chown -R www-data:www-data /var/www/html/django/viajes_fgpy/frontend
```

### curl a `/api/admin/health` devuelve HTML en vez de JSON

Nginx no está enrutando `/api/*` al backend. El `location ~` del proxy_pass está roto. Ver [Recuperación](#recuperación-si-algo-se-rompe).

### El frontend muestra banner pero no carga datos

Mismo problema que arriba: nginx no enruta al backend. El frontend renderiza bien (sirve el `index.html` desde `frontend/`), pero los requests a `/api/...` se pierden en el `location /` que devuelve `index.html`.

### `nginx -t` da "unknown directive" después del sed

El sed rompió la sintaxis. Restaurar el backup:

```bash
ls /etc/nginx/sites-enabled/viajes.forestalparaguay.com.bak.*
sudo cp /etc/nginx/sites-enabled/viajes.forestalparaguay.com.bak.<timestamp> \
        /etc/nginx/sites-enabled/viajes.forestalparaguay.com
```

---

## Variables de entorno importantes

Estas están en `/var/www/html/django/viajes_fgpy/backend/.env` (mode `640`, group `www-data`).

| Variable | Ejemplo | Notas |
|---|---|---|
| `DATABASE_URL` | `mysql+mysqlconnector://u604652499_fgpy:CLAVE_URL_ENCODED@srv1723.hstgr.io/u604652499_fgpy` | URL-encoded. El `%40` es `@`. |
| `JWT_SECRET_KEY` | random 64-char | No commitear. Generar con `python -c "import secrets; print(secrets.token_urlsafe(64))"`. |
| `MINIMAX_API_KEY` | `sk-cp-...` | API key del OCR. Sin esto, el OCR de tickets/remitos no anda. |
| `MINIMAX_API_HOST` | `https://api.minimax.io` | Endpoint del LLM vision. |
| `MINIMAX_VISION_COMMAND` | `/var/www/html/django/viajes_fgpy-data/minimax-venv/bin/minimax-coding-plan-mcp` | Path al binario MCP. |
| `SMTP_*` | varios | Config de email. |
| `DEFAULT_FUEL_PROVEEDOR_ID` | `1` | El proveedor genérico (NO TOCAR — id=1 histórico con 815 movimientos). |
| `INTERNAL_FUEL_PROVEEDOR_RAZON_SOCIAL` | `INTERNO FORESTAL PARAGUAY` | (conceptualmente) El helper `get_internal_provider_id()` busca por nombre. No hardcodear id. |
| `VIAJE_IMAGE_STORAGE_DIR` | `/var/www/html/django/viajes_fgpy-data/images` | Dónde se guardan las imágenes OCR. |
| `IMAGE_TOKEN_SECRET` | random | Para los tokens de URLs firmadas de imágenes. |
| `TRIP_IMAGE_CLEANUP_TIME` | `03:00` | Hora del cleanup diario de imágenes con TTL vencido. |

---

## Endpoints útiles

| Endpoint | Método | Notas |
|---|---|---|
| `/api/admin/health` | GET | Health check. Devuelve `{"status":"ok","timestamp":...}`. |
| `/api/proveedores` | GET | Lista de proveedores. |
| `/api/equipos` | GET | Lista de equipos/vehículos. |
| `/api/panioles` | GET | Lista de pañoles (tanques). |
| `/api/fuel-image/analyze` | POST | Analiza una imagen de ticket/remito. Devuelve JSON con datos extraídos. |
| `/api/fuel-image/confirm/ticket` | POST | Confirma un ticket y crea el movimiento de combustible. |
| `/api/fuel-image/confirm/remoto-interno` | POST | Confirma un remito interno y crea el movimiento. |
| `/api/fuel-image/{id}/blob` | GET | Devuelve la imagen original (token de URL firmado). |

> **No** existe `/api/health` (devuelve HTML por el SPA fallback). Usá `/api/admin/health`.

---

## Cómo mergear cambios del script de deploy

El script vive en el repo en `backend/scripts/deploy_fuel_ocr.sh`. Se desarrolla en un branch (`codex/deploy-script` típicamente) y se mergea a `main` con `--squash` cuando está listo.

```powershell
# En tu Windows
cd D:\notebook\active\registro_viajes_fgpy
git checkout codex/deploy-script
# Hacer los cambios al script
git add backend/scripts/deploy_fuel_ocr.sh
git commit -m "fix(deploy): descripcion del cambio"
git push origin codex/deploy-script
gh pr create --base main --title "chore(deploy): descripcion"
```

Después del merge a `main`, el próximo deploy va a bajar el script actualizado y usarlo automáticamente (porque el script se copia al server en el paso de sync).

**Si querés probar el script antes de mergear**, subilo al server con `scp` (como muestra el paso 2 de [Deploy con el script automático](#deploy-con-el-script-automático)).

---

## Changelog del deploy

- **2026-07-31** — Deploy inicial del feature OCR de combustible (#15-#19). Creado `deploy_fuel_ocr.sh`. Patch de nginx para `|fuel-image|`. Migración `20260731_add_combustible_imagenes.sql` aplicada. Proveedor INTERNO insertado con id=29.
