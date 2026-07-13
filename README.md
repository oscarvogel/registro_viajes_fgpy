# Registro de Viajes FGPY

Aplicación para registrar y administrar viajes, con una interfaz web orientada a choferes y un panel de gestión.

## Estado del repositorio

Este repositorio fue reconstruido a partir de archivos recuperados del historial local, restos del repo anterior y assets servidos por `https://viajes.forestalparaguay.com`.

Estado actual:

- Frontend Vue/Vite recuperado, instala dependencias, pasa tests y compila.
- Servidor local del frontend verificado en `http://127.0.0.1:5173/`.
- Backend FastAPI recuperado, compila, conecta por `.env` local y pasa las pruebas disponibles.

## Estructura

```text
registro_viajes/
├── backend/                 # API FastAPI y pruebas de autenticación/panel
├── frontend/
│   ├── src/
│   │   ├── composables/     # Hooks/composables de PWA
│   │   ├── components/      # Componentes Vue reutilizables
│   │   ├── router/          # Rutas de la aplicación
│   │   ├── services/        # Acceso a servicios y lógica de viajes
│   │   └── views/           # Pantallas de viajes, ajustes y administración
│   ├── public/              # Assets públicos PWA
│   └── tests/               # Pruebas del frontend
└── docs/
    └── superpowers/         # Especificaciones y planes de implementación
```

## Tecnologías identificadas

- Backend: Python, FastAPI, SQLAlchemy y JWT.
- Frontend: Vue 3, Vite, Pinia, Vue Router, IndexedDB y PWA.
- Pruebas: pruebas Python para el backend y JavaScript para el frontend.
- Observabilidad: integración con Sentry y registro de eventos.

## Funcionalidades presentes

- Inicio de sesión y protección de rutas.
- Registro de nuevos viajes y datos de remito.
- Registro de cargas de combustible.
- Registro de movimientos de carretón.
- Sincronización offline con registros pendientes.
- Navegación inferior para dispositivos móviles.
- Configuración de la aplicación.
- Panel administrativo y métricas gerenciales.
- Controles de autenticación, CORS y limitación de intentos de acceso.

## Instalación local en otra máquina

Requisitos:

- Git.
- Python 3.12 o compatible.
- Node.js y npm.
- `uv`/`uvx` disponible para el usuario que ejecuta el backend (adaptador MCP de MiniMax).
- Acceso a la base MySQL definida en `backend\.env`.

Clonar el proyecto:

```powershell
git clone https://github.com/oscarvogel/registro_viajes_fgpy.git
Set-Location registro_viajes_fgpy
```

Si ya tenés el proyecto clonado, entrá a la carpeta donde lo hayas guardado:

```powershell
Set-Location <carpeta-donde-clonaste-el-repo>
```

## Backend

Antes de levantar el backend, crear `backend\.env` a partir de `backend\.env.example` y completar los valores reales fuera de Git:

```powershell
Copy-Item backend\.env.example backend\.env
notepad backend\.env
```

Instalar dependencias y verificar:

```powershell
py -m pip install -r backend\requirements.txt
py -m pytest backend -q
py -m py_compile backend\main.py backend\database.py backend\models.py backend\schemas.py
```

Levantar el backend en una terminal:

```powershell
Set-Location registro_viajes_fgpy\backend
py -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Chequeo rápido:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/admin/health
```

La API queda disponible en `http://127.0.0.1:8000/api`.

No se deben guardar credenciales, claves JWT, conexiones de base de datos ni archivos `.env` reales en Git.

### Carga de viajes desde imagen (OCR)

El flujo **Cargar desde foto** envía JPEG, PNG o WebP al backend, extrae una propuesta con MiniMax y recién crea el viaje cuando el operador revisa y confirma. La imagen queda privada: se entrega únicamente por el endpoint autenticado, nunca como archivo estático. El OCR puede informar chofer y patente observados, pero el registro usa el usuario autenticado y la patente/unidad configuradas en el celular. El remito del proveedor queda vacío; el remito FGPY se conserva completo. Para este trayecto se guarda `pesaje_unico=true`, origen en cero, destino en toneladas y `cliente_id=NULL`.

Instalar `uv` (incluye `uvx`) y verificar que lo vea el mismo usuario del servicio:

```bash
uvx --version
```

Configurar en `backend/.env` las variables documentadas en `backend/.env.example`:

- `MINIMAX_API_KEY`: secreto de MiniMax, solo backend.
- `MINIMAX_API_HOST`: `https://api.minimax.io` para claves globales (valor por defecto) o `https://api.minimaxi.com` para China continental; host y clave deben pertenecer a la misma región.
- `MINIMAX_VISION_COMMAND`: por defecto `uvx minimax-coding-plan-mcp -y`.
- `MINIMAX_VISION_TIMEOUT_SECONDS`: espera total del proceso MCP; por defecto 90 segundos.
- `MINIMAX_VISION_MAX_OUTPUT_BYTES`: límite combinado de salida; por defecto 1 MiB.
- `VIAJE_IMAGE_STORAGE_DIR`: ruta absoluta, privada y fuera del repositorio/directorio público.
- `VIAJE_IMAGE_MAX_BYTES`: máximo por imagen; por defecto 10 MiB.
- `VIAJE_IMAGE_TEMP_TTL_HOURS`: vida de una carga sin confirmar; por defecto 24 horas.
- `IMAGE_TOKEN_SECRET`: secreto HMAC independiente de al menos 32 bytes.
- `TRIP_IMAGE_CLEANUP_TIME`: horario local diario `HH:MM`; por defecto `03:00`.

La evidencia confirmada se retiene **exactamente 60 días**. Es una regla fija del código, no una variable de ambiente. La limpieza diaria elimina temporales vencidas, evidencias vencidas y promociones huérfanas con controles de concurrencia e integridad.

En Linux, preparar el almacenamiento antes de iniciar el servicio. Reemplazar `USUARIO_SERVICIO` y `GRUPO_SERVICIO` por la cuenta real; no dar acceso al usuario de Nginx:

```bash
sudo install -d -m 0700 -o USUARIO_SERVICIO -g GRUPO_SERVICIO /var/lib/registro-viajes/imagenes
sudo -u USUARIO_SERVICIO test -r /var/lib/registro-viajes/imagenes
sudo -u USUARIO_SERVICIO test -w /var/lib/registro-viajes/imagenes
```

El backend crea subdirectorios con permisos restrictivos, pero la cuenta del servicio debe poder leer, escribir, renombrar y borrar dentro de la raíz. No apuntar `VIAJE_IMAGE_STORAGE_DIR` a `frontend/public`, `frontend/dist`, `/var/www` ni otra ruta publicada.

#### Migración MySQL

Antes de migrar producción, confirmar la base seleccionada, inspeccionar la estructura actual y realizar un backup. El script agrega `pesaje_unico`, permite `cliente_id=NULL` y crea `viaje_imagenes`; no debe ejecutarse a ciegas:

```bash
umask 077
export DB_NAME='BASE_DATOS'
export MYSQL_CNF='/ruta/privada/mysql-client.cnf'
export BACKUP="$PWD/backup-viaje-imagen-$(date +%Y%m%d-%H%M%S).sql"
mysql --defaults-extra-file="$MYSQL_CNF" --table "$DB_NAME" -e "SHOW CREATE TABLE tablero_produccion\G; SHOW COLUMNS FROM tablero_produccion LIKE 'cliente_id';"
mysqldump --defaults-extra-file="$MYSQL_CNF" --single-transaction --routines --triggers --events --databases "$DB_NAME" > "$BACKUP"
test -s "$BACKUP"
mysql --defaults-extra-file="$MYSQL_CNF" "$DB_NAME" < backend/migrations/20260713_add_trip_image_ocr.sql
mysql --defaults-extra-file="$MYSQL_CNF" --table "$DB_NAME" < backend/migrations/20260713_verify_trip_image_ocr.sql
```

`mysql-client.cnf` debe ser legible solo por la cuenta operativa y contener las credenciales fuera del historial del shell; no usar `-pCLAVE`. Conservar también la salida previa de `SHOW CREATE TABLE`, porque documenta el tipo y nullability originales de `cliente_id`. La migración es idempotente, pero se detiene si encuentra `token_hash` duplicados. La verificación es de solo lectura y debe mostrar:

- `tablero_produccion.pesaje_unico` no nulo con valor por defecto `0`;
- `tablero_produccion.cliente_id` nullable;
- tabla InnoDB `viaje_imagenes`, FK hacia `tablero_produccion(id)`;
- índice no único exacto sobre `expires_at` e índice único exacto sobre `token_hash`.

#### Rollback de aplicación y esquema

El rollback destructivo restaura la base al instante del backup y pierde cualquier escritura posterior. Usarlo únicamente con la aplicación detenida, una ventana aprobada y el archivo validado. Antes de comenzar, guardar además un backup del estado fallido para investigación.

```bash
sudo systemctl stop SERVICIO_REGISTRO_VIAJES

# Revertir el checkout/symlink o desplegar el artefacto anterior ya verificado.
# El mecanismo exacto depende del esquema de releases del servidor.

export DB_NAME='BASE_DATOS'
export MYSQL_CNF='/ruta/privada/mysql-client.cnf'
export BACKUP='/ruta/privada/backup-viaje-imagen-AAAAMMDD-HHMMSS.sql'
test -r "$BACKUP" && test -s "$BACKUP"
mysqldump --defaults-extra-file="$MYSQL_CNF" --single-transaction --routines --triggers --events --databases "$DB_NAME" > "${BACKUP}.estado-fallido"

# La tabla nueva no figura en un backup anterior y debe retirarse antes de restaurar.
mysql --defaults-extra-file="$MYSQL_CNF" "$DB_NAME" -e "SET FOREIGN_KEY_CHECKS=0; DROP TABLE IF EXISTS viaje_imagenes; SET FOREIGN_KEY_CHECKS=1;"
mysql --defaults-extra-file="$MYSQL_CNF" < "$BACKUP"

mysql --defaults-extra-file="$MYSQL_CNF" --table "$DB_NAME" -e "
SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='viaje_imagenes';
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='tablero_produccion' AND COLUMN_NAME IN ('cliente_id','pesaje_unico') ORDER BY COLUMN_NAME;"

sudo systemctl start SERVICIO_REGISTRO_VIAJES
curl --fail --silent --show-error http://127.0.0.1:8000/api/admin/health
```

La verificación debe mostrar que `viaje_imagenes` y `pesaje_unico` ya no existen, y que `cliente_id` volvió exactamente al `COLUMN_TYPE`, `IS_NULLABLE` y default capturados antes de migrar. El `UNIQUE token_hash` y los demás índices de evidencia desaparecen junto con `viaje_imagenes`; no intentar borrarlos después. Nunca eliminar `cliente_id`: la migración solo cambia su nullability.

Si hay que conservar escrituras posteriores al backup, **no** restaurar ni ejecutar el `DROP TABLE`: detener el rollback y preparar con un DBA una migración inversa basada en el `SHOW CREATE TABLE` previo, exportando antes las filas y archivos de evidencia. No es seguro reconstruir el tipo original de `cliente_id` por su nombre ni volverlo `NOT NULL` mientras existan viajes OCR con cliente nulo.

#### Verificación del flujo OCR

Ejecutar las pruebas focales del backend desde la raíz (usan bases aisladas, no producción):

```powershell
py -m pytest backend/test_minimax_vision.py backend/test_trip_image_normalization.py backend/test_image_storage.py backend/test_trip_image_api.py backend/test_trip_image_cleanup.py -q
```

Luego ejecutar la verificación completa compatible de backend y frontend:

```powershell
py -m pytest backend -q
Set-Location frontend
npm ci
npm run verify
```

Un timeout de MiniMax devuelve un error controlado y no crea ningún viaje. Para diagnosticarlo, verificar primero `uvx --version`, que `MINIMAX_API_HOST` corresponda a la región de la clave, la conectividad saliente y luego ajustar `MINIMAX_VISION_TIMEOUT_SECONDS`. No iniciar el servidor MCP manualmente en producción ni registrar la clave o la salida cruda del proveedor en logs o tickets.

## Frontend

Instalar dependencias y verificar:

```powershell
Set-Location registro_viajes_fgpy\frontend
npm install --strict-ssl=false
npm test
npm run build
```

Levantar el frontend en otra terminal:

```powershell
Set-Location registro_viajes_fgpy\frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Abrir en el navegador:

```text
http://127.0.0.1:5173/
```

Por defecto el frontend usa `http://localhost:8000/api`. Si necesitás apuntarlo a otra API, crear `frontend\.env.local`:

```powershell
Set-Content frontend\.env.local "VITE_API_URL=http://127.0.0.1:8000/api"
```

El `--strict-ssl=false` fue necesario en esta máquina por un problema local de certificados contra el registry de npm. Si tu npm funciona normal, podés usar simplemente `npm install`.

## Verificación actual

Usar los comandos anteriores para obtener evidencia fresca en cada entrega. No se considera suficiente un conteo histórico de pruebas ni una respuesta previa del servidor.

## Documentación

Las decisiones y el plan del dashboard gerencial están disponibles en [`docs/superpowers`](docs/superpowers/).
