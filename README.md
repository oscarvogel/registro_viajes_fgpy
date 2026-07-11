# Registro de Viajes FGPY

Aplicación para registrar y administrar viajes, con una interfaz web orientada a choferes y un panel de gestión.

## Estado del repositorio

Este repositorio fue reconstruido a partir de archivos recuperados del historial local, restos del repo anterior y assets servidos por `https://viajes.forestalparaguay.com`.

Estado actual:

- Frontend Vue/Vite recuperado, instala dependencias, pasa tests y compila.
- Servidor local del frontend verificado en `http://127.0.0.1:5173/`.
- Backend parcialmente recuperado: `backend/main.py` compila, pero todavía faltan módulos locales (`database.py`, modelos, esquemas y servicios). Los tests backend no pueden correr hasta recuperar esos archivos del servidor.

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
Set-Location O:\proyectos\actives\registro_viajes\frontend
npm install --strict-ssl=false
npm test
npm run build
npm run dev -- --host 127.0.0.1 --port 5173
```

El `--strict-ssl=false` fue necesario en esta máquina por un problema local de certificados contra el registry de npm.

## Backend

El backend todavía no está completo. Para dejarlo ejecutable se deben recuperar o crear:

1. `backend/database.py`
2. `backend/models.py`
3. `backend/schemas.py`
4. Servicios locales importados por `backend/main.py`
5. `backend/requirements.txt`
6. Un archivo `.env.example` sin credenciales, con la configuración requerida.

No se deben guardar credenciales, claves JWT, conexiones de base de datos ni archivos `.env` reales en Git.

## Verificación actual

- `frontend`: `npm test` pasa 56/56.
- `frontend`: `npm run build` genera `dist/` correctamente.
- `frontend`: `http://127.0.0.1:5173/` responde 200.
- `backend`: `py -m py_compile backend\main.py` pasa.
- `backend`: `py -m pytest backend -q` falla por `ModuleNotFoundError: No module named 'database'`.

## Documentación

Las decisiones y el plan del dashboard gerencial están disponibles en [`docs/superpowers`](docs/superpowers/).
