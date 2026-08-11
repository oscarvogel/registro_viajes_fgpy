def test_app_principal_expone_rutas_correctivos():
    import main

    paths = {
        route.path
        for route in main.app.routes
        if hasattr(route, "path")
    }

    assert "/api/correctivos/catalogos" in paths
    assert "/api/correctivos" in paths
    assert "/api/correctivos/{correctivo_id}" in paths
    assert "/api/equipos/{equipo_id}/correctivos" in paths
