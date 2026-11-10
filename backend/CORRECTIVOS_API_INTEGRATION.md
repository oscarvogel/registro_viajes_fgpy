# Integración API de correctivos (#30)

El módulo `correctivos_api.py` expone una factory:

```python
build_correctivos_router(get_db, get_current_user)
```

El router está diseñado para incluirse dentro del `api_router` existente de `main.py`, manteniendo el prefijo `/api` centralizado:

```python
from correctivos_api import build_correctivos_router

api_router.include_router(build_correctivos_router(get_db, get_current_user))
```

Endpoints resultantes:

- `GET /api/correctivos/catalogos`
- `POST /api/correctivos`
- `GET /api/correctivos`
- `GET /api/correctivos/{id}`
- `GET /api/equipos/{equipo_id}/correctivos`

La identidad siempre se toma de `get_current_user`; el payload de alta rechaza campos extra como `usuario` o `cerrado_por`.
