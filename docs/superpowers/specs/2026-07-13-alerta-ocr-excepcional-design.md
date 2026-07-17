# Alerta OCR excepcional en la revisión de viajes

## Objetivo

Evitar que el operador revise dos veces la misma información en la pantalla de carga desde foto. La revisión editable y la tarjeta `Configuración del viaje` permanecen como fuentes principales; el bloque general `Datos observados en la foto` se elimina.

## Comportamiento aprobado

- No mostrar observaciones generales generadas por MiniMax en la interfaz.
- No mostrar normalmente patente ni chofer observados por OCR.
- Mostrar una única alerta compacta `Revisá la configuración` solamente cuando exista al menos una discrepancia:
  - patente observada distinta de la patente configurada en Ajustes; o
  - chofer observado distinto del usuario autenticado.
- La alerta enumera únicamente las diferencias concretas. Ejemplo: `La foto parece indicar AAXO300; en Ajustes figura AAX0300.`
- La tarjeta `Configuración del viaje` continúa mostrando una sola vez chofer, patente y unidad de negocio efectivos.
- La configuración del celular sigue siendo autoritativa. La alerta no reemplaza valores ni bloquea la confirmación.

## Alcance técnico

- Ajustar el modelo de revisión frontend para separar discrepancias de las advertencias generales del proveedor OCR.
- Renderizar la alerta únicamente a partir de discrepancias calculadas entre OCR y configuración.
- Eliminar del template el bloque general de datos observados y la lista de advertencias de MiniMax.
- No modificar backend, prompt OCR, base de datos, endpoints ni payload de confirmación.

## Estados y errores

- Sin discrepancias: no existe alerta ni espacio vacío asociado.
- Con una discrepancia: se muestra una sola línea concreta.
- Con dos discrepancias: se muestran ambas dentro de la misma alerta.
- Un valor OCR ausente no genera alerta.
- Los errores de análisis, confirmación y conectividad mantienen el comportamiento actual.

## Verificación

- Prueba de modelo: las advertencias generales de MiniMax no se convierten en alertas visibles.
- Prueba de componente: sin discrepancias no se renderiza `Revisá la configuración`.
- Prueba de componente: una discrepancia de patente o chofer renderiza la alerta compacta con ambos valores relevantes.
- Prueba de regresión: los valores de chofer, patente y unidad enviados al confirmar siguen viniendo exclusivamente de Ajustes/sesión.
- Ejecutar `npm run verify` y comprobar visualmente la pantalla móvil antes del despliegue.

## Despliegue

Publicar únicamente el nuevo artefacto frontend. No requiere migración ni reinicio de `viajes.service`. Conservar la versión anterior del frontend para rollback y verificar CSS, ruta y alerta en producción.
