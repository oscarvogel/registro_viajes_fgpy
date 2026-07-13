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

## Frontend

```powershell
git clone https://github.com/oscarvogel/registro_viajes_fgpy.git
Set-Location registro_viajes_fgpy\frontend
npm install --strict-ssl=false
npm test
npm run build
npm run dev -- --host 127.0.0.1 --port 5173
```

Si ya tenés el proyecto clonado, reemplazá los dos primeros comandos por entrar a la carpeta donde lo tengas guardado:

```powershell
Set-Location <carpeta-donde-clonaste-el-repo>\frontend
```

El `--strict-ssl=false` fue necesario en esta máquina por un problema local de certificados contra el registry de npm. Si tu npm funciona normal, podés usar simplemente `npm install`.

## Backend

Antes de levantar el backend, crear `backend\.env` a partir de `backend\.env.example` y completar los valores reales fuera de Git.

```powershell
Set-Location registro_viajes_fgpy
py -m pip install -r backend\requirements.txt
py -m pytest backend -q
py -m py_compile backend\main.py backend\database.py backend\models.py backend\schemas.py
```

No se deben guardar credenciales, claves JWT, conexiones de base de datos ni archivos `.env` reales en Git.

## Verificación actual

- `frontend`: `npm test` pasa 56/56.
- `frontend`: `npm run build` genera `dist/` correctamente.
- `frontend`: `http://127.0.0.1:5173/` responde 200.
- `backend`: `py -m pytest backend -q` pasa.
- `backend`: `/api/panioles?limit=10000` responde 200 contra MySQL configurado por `.env`.

## Documentación

Las decisiones y el plan del dashboard gerencial están disponibles en [`docs/superpowers`](docs/superpowers/).
