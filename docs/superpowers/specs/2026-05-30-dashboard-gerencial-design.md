# Dashboard gerencial protegido

## Objetivo

Crear una vista gerencial separada del dashboard operativo de choferes, orientada a duenos y gerentes. La vista debe ayudar a entender el estado de la operacion, detectar problemas de sincronizacion y revisar indicadores clave sin permitir carga o modificacion de registros.

## Alcance inicial

La primera version se enfocara en datos accionables y confiables, sin graficos complejos. Debe incluir filtros por rango de fechas y una composicion de tarjetas KPI, tablas resumidas y alertas. Los graficos quedan para una segunda etapa, cuando los endpoints consolidados esten validados.

Incluye:

- Nueva ruta frontend protegida: `/admin/dashboard`.
- Nuevo endpoint backend protegido para resumen gerencial.
- Acceso solo para usuarios autorizados como admin/gerencia.
- KPIs ejecutivos del periodo.
- Resumen operativo por equipo, chofer y unidad de negocio.
- Panel de alertas de sincronizacion, registros bloqueados y errores frontend recientes.

No incluye en esta etapa:

- Edicion o correccion de registros desde el panel.
- Graficos avanzados o librerias nuevas de visualizacion.
- Sistema nuevo de roles/permisos.
- Exportacion Excel/PDF.

## Autorizacion

La proteccion debe usar el patron existente:

- En frontend, la ruta usara `meta.requiresAuth` y `meta.requiresAdmin`.
- En backend, el endpoint usara `require_admin_user`.
- La lista de autorizados seguira saliendo de `VITE_ADMIN_USER_IDS` en frontend y `ADMIN_USER_IDS` en backend.

Esto evita introducir un sistema de permisos nuevo y mantiene consistencia con `/admin/logs`.

## Experiencia de usuario

La pantalla debe sentirse ejecutiva, densa y escaneable. No debe parecer una pantalla de marketing ni una vista de carga de datos. Debe priorizar lectura rapida, comparacion y deteccion de problemas.

Estructura recomendada:

1. Encabezado con titulo, rango de fechas y boton de actualizar.
2. Fila de KPIs ejecutivos.
3. Seccion de control operativo con rankings o tablas cortas.
4. Seccion de alertas y sincronizacion.
5. Acceso secundario hacia errores frontend existentes si el usuario necesita diagnostico detallado.

Los KPIs iniciales seran:

- Total de viajes.
- Toneladas transportadas.
- Promedio de toneladas por viaje.
- Litros cargados.
- Movimientos de carreton.
- Registros pendientes offline.
- Registros bloqueados.
- Errores/warnings frontend recientes.

## Datos y backend

Se agregara un endpoint protegido, por ejemplo:

`GET /api/admin/dashboard-summary`

Parametros:

- `fecha_desde`: fecha inicial obligatoria o con default al primer dia del mes.
- `fecha_hasta`: fecha final obligatoria o con default al dia actual.

Respuesta propuesta:

```json
{
  "period": {
    "fecha_desde": "2026-05-01",
    "fecha_hasta": "2026-05-30"
  },
  "kpis": {
    "viajes": 0,
    "toneladas": 0,
    "promedio_toneladas_por_viaje": 0,
    "litros": 0,
    "movimientos_carreton": 0,
    "errores_frontend": 0,
    "warnings_frontend": 0
  },
  "rankings": {
    "por_equipo": [],
    "por_chofer": [],
    "por_unidad_negocio": []
  },
  "alerts": {
    "client_log_items": 0,
    "blocked_records_note": "Los pendientes locales no son visibles en backend hasta sincronizar."
  }
}
```

Los registros pendientes offline viven en IndexedDB del dispositivo, por lo que el backend no puede conocer todos los pendientes locales sin una telemetria adicional. En esta primera version, el frontend mostrara pendientes del dispositivo actual usando el store existente, y el backend mostrara errores frontend persistidos en `client_log_summary`.

## Frontend

Se creara una vista nueva, por ejemplo `frontend/src/views/AdminDashboard.vue`, y servicios auxiliares si conviene mantener la logica testeable.

La vista debe:

- Cargar datos al montar con el rango mensual por defecto.
- Permitir cambiar `fecha_desde` y `fecha_hasta`.
- Mostrar error claro si el usuario no esta autorizado o falla la carga.
- Reusar el patron visual existente de Tailwind, sin introducir dependencias nuevas.
- Mostrar pendientes locales del dispositivo actual usando `syncStore.pendingRecords`.
- Incluir enlace o boton hacia `/admin/logs`.

## Testing

Pruebas frontend:

- Verificar que la ruta `/admin/dashboard` exige admin mediante `resolveAuthNavigation`.
- Probar helpers de normalizacion/resumen si se extraen a un servicio.
- Mantener `npm run test` y `npm run build` como verificacion.

Pruebas backend:

- Probar que el endpoint rechaza usuarios no autorizados.
- Probar respuesta basica con rango de fechas valido.
- Probar que los KPIs devuelven numeros aunque no haya datos.

## Riesgos y decisiones

- El dashboard no debe reemplazar al dashboard de choferes. Sera una ruta admin separada.
- Los pendientes offline globales no son posibles con los datos actuales; solo se mostraran pendientes del dispositivo actual hasta implementar telemetria multi-dispositivo.
- La primera version debe evitar graficos para reducir riesgo y acelerar entrega.
- La autorizacion debe validarse en backend; el control frontend solo mejora la navegacion.
