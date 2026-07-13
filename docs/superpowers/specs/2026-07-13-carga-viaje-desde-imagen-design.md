# Carga de viaje desde imagen con MiniMax

## Objetivo

Permitir que un operador cree un viaje a partir de una fotografía de una nota de remisión y su ticket de balanza. El sistema extrae los datos con MiniMax, muestra la imagen original y una revisión editable, y solamente graba el viaje después de la confirmación explícita del operador.

El primer caso operativo es un traslado de chips desde la playa de chipeo de Forestal Paraguay hasta la planta de Alcogreen, a aproximadamente 500 metros. Existe un único pesaje realizado en la balanza de Forestal Paraguay y no hay un segundo pesaje en destino.

## Alcance funcional

- Incorporar un botón independiente `Cargar desde foto`, visualmente separado del formulario manual y de las acciones de movimiento de carretón.
- Permitir tomar una foto desde el celular o seleccionar una imagen existente.
- Procesar la imagen en el backend con MiniMax Vision.
- Mostrar la imagen original y los campos extraídos en una pantalla de revisión editable.
- Completar chofer, patente y unidad de negocio desde la sesión y configuración del celular, nunca desde el OCR.
- Buscar al proveedor por nombre normalizado en la base de datos.
- Crear el viaje únicamente después de que el operador confirme la revisión.
- Conservar la imagen vinculada al viaje durante 60 días y eliminarla automáticamente después.
- Mantener sin cambios el flujo manual existente.

## Decisiones de negocio aprobadas

### Identidades y catálogos

- `proveedor_id`: buscar `Alcogreen` en el catálogo de proveedores. No se debe fijar un ID en el código. Si la búsqueda no devuelve una única coincidencia activa, el operador debe seleccionar el proveedor antes de confirmar.
- `cliente_id`: guardar `null` para este flujo.
- `chofer_id`: tomarlo de la identidad autenticada/configuración vigente del celular. El nombre observado en una imagen nunca reemplaza este valor.
- `patente`: tomar `default_patente` de la configuración del celular. La patente leída por OCR puede mostrarse solamente como advertencia si no coincide.
- `unidad_negocio_id`: tomar `default_unidad_negocio` del celular. No se infiere de la imagen ni se fija a la unidad mostrada en ejemplos.

### Remitos y fechas

- `numero_remision`: dejarlo vacío, porque no se registra un remito de proveedor para este caso.
- `numero_remision_fpv`: usar el número completo leído de la nota de remisión. Para la imagen de prueba es `002-003-0003677`.
- `fecha_remision`: tomarla del documento y normalizarla a formato ISO. Para la imagen de prueba es `2026-07-13`.
- `fecha_recepcion`: conservar la regla actual del formulario y no inventarla a partir del OCR.

### Pesaje único

Se incorpora el indicador explícito `pesaje_unico=true`. Para este modo:

- `peso_bruto_origen`: `0`.
- `tara_origen`: `0`.
- `neto_origen`: `0`.
- `peso_bruto_destino`: peso bruto leído, convertido de kilogramos a toneladas.
- `tara_destino`: tara leída, convertida de kilogramos a toneladas.
- `neto_destino`: peso neto leído, convertido de kilogramos a toneladas.
- `produccion_tn`: igual a `neto_destino`.

Para la imagen de prueba:

| Campo | Lectura | Valor almacenado |
|---|---:|---:|
| Peso bruto destino | 49.690 kg | 49,690 TN |
| Tara destino | 17.080 kg | 17,080 TN |
| Neto destino | 32.610 kg | 32,610 TN |
| Neto origen | Sin pesaje de origen | 0 TN |
| Producción | Derivada del neto destino | 32,610 TN |

La conversión se hará con aritmética decimal, dividiendo los kilogramos por 1.000. La regla actual que exige `neto_origen > 0` se omitirá solamente cuando `pesaje_unico=true`. Los viajes manuales normales conservarán sus validaciones actuales. No se duplicará el pesaje destino en los campos de origen.

## Arquitectura

La solución usa un flujo backend intermedio. El navegador nunca se conecta directamente a MiniMax y nunca recibe `MINIMAX_API_KEY`.

### Frontend Vue

Se incorporará una vista específica con cuatro estados:

1. Selección o captura de imagen.
2. Procesamiento con indicación de progreso.
3. Revisión de imagen original y campos editables.
4. Confirmación exitosa o error recuperable.

El botón de entrada estará separado del resto de las acciones de carga. El formulario manual seguirá siendo una alternativa independiente. La pantalla de revisión distinguirá visualmente los datos extraídos de los datos tomados de la configuración del celular.

### API FastAPI

Se agregarán dos operaciones autenticadas:

- Análisis: recibe la imagen, valida el archivo, la almacena temporalmente, consulta MiniMax y devuelve un identificador temporal junto con una propuesta normalizada.
- Confirmación: recibe el identificador temporal y los valores revisados, vuelve a validarlos y crea el viaje y el vínculo con la imagen en una única transacción lógica.

La confirmación no confiará en valores de identidad enviados libremente por el navegador. El chofer se derivará de la sesión autenticada; la patente y la unidad configuradas se validarán contra los catálogos permitidos.

### Servicios internos

La implementación se separará en unidades pequeñas:

- Cliente MiniMax: envío de imagen y recepción de una respuesta JSON estructurada.
- Normalizador OCR: fechas, números de remito, unidades y conversiones kg/TN.
- Resolución de proveedor: búsqueda normalizada y detección de coincidencias ambiguas.
- Almacenamiento de evidencia: archivos temporales, archivos confirmados y limpieza.
- Creación de viaje desde imagen: reglas de `pesaje_unico` y mapeo al modelo actual.

La lógica no se agregará íntegramente al archivo principal del backend.

## Contrato de extracción

MiniMax devolverá una estructura controlada que incluya, cuando estén visibles:

- Fecha de remisión.
- Número completo de remisión FGPY, separado además en tipo, sucursal y número para validar prefijos.
- Razón social del destinatario/proveedor candidato.
- Peso bruto, tara y neto, con unidad original.
- Patente y chofer observados solamente para comparación informativa.
- Indicadores de confianza o advertencias para campos dudosos.

El backend rechazará respuestas que no cumplan el esquema. Los valores numéricos se normalizarán de forma determinista; no se confiará en que el modelo realice la conversión final.

## Flujo de datos

1. El operador abre `Cargar desde foto` y selecciona una imagen.
2. El frontend envía la imagen al endpoint de análisis autenticado.
3. El backend valida formato y tamaño, calcula un hash y crea un archivo temporal no público.
4. El backend consulta MiniMax y valida la respuesta estructurada.
5. El backend convierte kilogramos a toneladas, busca el proveedor y devuelve la propuesta.
6. El frontend muestra la imagen original, los campos editables, la configuración vigente y cualquier advertencia.
7. El operador corrige lo necesario y confirma.
8. El backend comprueba que el archivo temporal sigue vigente, valida duplicados y catálogos, y crea el viaje con `pesaje_unico=true`.
9. El archivo pasa al almacenamiento confirmado y queda vinculado al viaje.
10. Una tarea idempotente elimina imágenes confirmadas vencidas y temporales abandonadas.

No se crea ningún registro de viaje durante el análisis.

## Persistencia de imágenes

Las imágenes se guardarán fuera del repositorio y fuera de una ruta pública de Nginx, en un directorio configurable mediante `VIAJE_IMAGE_STORAGE_DIR`. La API entregará la imagen solamente a usuarios autenticados mediante un endpoint controlado.

Se incorporará una tabla específica de evidencia vinculada al registro del viaje, con al menos:

- Identificador.
- Identificador del viaje.
- Ruta interna del archivo.
- Nombre original y tipo MIME.
- Hash del contenido.
- Fecha de creación.
- Fecha de vencimiento.

La tabla se creará mediante una migración explícita. No se dependerá silenciosamente de la creación automática de tablas al iniciar producción.

La misma migración incorporará `pesaje_unico` en `tablero_produccion` y permitirá `NULL` en `cliente_id`. Este último cambio es necesario porque el flujo aprobado conserva el cliente vacío; no se usará el cliente `1` como valor sustituto. Antes de aplicar la migración se verificará el tipo real y las restricciones actuales de ambas columnas en producción.

La retención será de 60 días desde la confirmación. La limpieza borrará primero el archivo y después marcará o eliminará el metadato según la estrategia vigente del proyecto. Los archivos temporales abandonados tendrán una retención corta independiente. La tarea se diseñará para ejecutarse varias veces sin fallar y deberá coordinarse con la futura corrección del scheduler registrada en el issue correspondiente.

## Validaciones

- Usuario autenticado y configuración completa de chofer, patente y unidad de negocio.
- Formatos de imagen permitidos: JPEG, PNG y WebP, validados por contenido además de extensión.
- Límite de tamaño configurable y dimensiones razonables.
- Número de remisión FGPY con prefijos completos y formato válido.
- Proveedor activo y resuelto de manera inequívoca.
- Pesos no negativos y consistencia `bruto - tara = neto` dentro de una tolerancia explícita de redondeo.
- Para `pesaje_unico`, neto destino mayor que cero y origen igual a cero.
- Para flujos normales, conservar la exigencia actual de neto origen mayor que cero.
- Prevención de confirmaciones dobles mediante consumo idempotente del identificador temporal.
- Control de duplicado del remito antes de grabar.

## Errores y recuperación

- Si MiniMax no responde o devuelve datos inválidos, se conserva temporalmente la imagen y se ofrece reintentar o volver a la carga manual; no se crea el viaje.
- Si un campo tiene baja confianza, se resalta para revisión sin bloquear los demás campos.
- Si el proveedor es ambiguo o inexistente, la confirmación queda bloqueada hasta que el operador seleccione uno válido.
- Si la configuración del celular está incompleta, se dirige al operador a Ajustes.
- Si la sesión vence antes de confirmar, se solicita reautenticación sin exponer la clave ni la respuesta cruda de MiniMax.
- Los logs no incluirán la clave, la imagen codificada ni documentos completos.

## Seguridad

- `MINIMAX_API_KEY` estará únicamente en el entorno del backend.
- Los endpoints de análisis, confirmación y consulta de imagen requerirán autenticación.
- Los nombres de archivo serán generados por el servidor y no se usarán rutas aportadas por el cliente.
- Se aplicarán límites de carga y tiempos de espera a la llamada externa.
- Las imágenes no se servirán como archivos estáticos públicos.
- La respuesta cruda del proveedor de IA no se persistirá salvo que una necesidad diagnóstica futura lo justifique y se diseñe su protección.

## Pruebas

### Backend

- Conversión exacta de `49.690`, `17.080` y `32.610` kg a toneladas.
- Normalización de `002-003-0003677` y rechazo de prefijos incompletos.
- Creación con `pesaje_unico=true`, origen cero y `produccion_tn=neto_destino`.
- Conservación de las reglas actuales para viajes sin pesaje único.
- Resolución única, ambigua e inexistente de proveedor.
- Rechazo de MIME falso, archivo excesivo y respuesta MiniMax inválida.
- Ausencia de escritura antes de confirmar.
- Confirmación idempotente y control de duplicados.
- Retención y limpieza segura de imágenes.
- Derivación de chofer desde la sesión y validación de patente/unidad.

### Frontend

- Botón OCR separado de las acciones existentes.
- Estados de selección, procesamiento, revisión, error y éxito.
- Imagen original visible durante la revisión.
- Campos OCR editables y campos de configuración identificados correctamente.
- Bloqueo de confirmación ante errores obligatorios.
- Conversión y visualización coherente de kg y TN.
- El flujo manual existente continúa funcionando.

### Integración

- Prueba del documento de muestra con proveedor Alcogreen y los tres pesos esperados.
- Simulación de MiniMax en pruebas automatizadas; las pruebas normales no consumirán la API real.
- Una prueba manual controlada con MiniMax real antes del despliegue.

## Despliegue

Antes de desplegar esta funcionalidad se reparará la configuración de Tailwind/PostCSS para que una compilación nueva genere CSS procesado. El artefacto restaurado actualmente en producción no debe ser sobrescrito por una compilación que contenga directivas `@tailwind` o `@apply` sin procesar.

El despliegue incluirá:

- Variables `MINIMAX_API_KEY`, `VIAJE_IMAGE_STORAGE_DIR`, límite de archivo y días de retención.
- Creación segura del directorio con permisos para el servicio.
- Migración explícita de la tabla de evidencia, del campo `pesaje_unico` y de la nulabilidad de `cliente_id` requerida por este flujo.
- Compilación verificada del frontend.
- Pruebas backend, frontend y smoke test público.
- Reinicio del servicio realizado por el usuario si requiere `sudo`.

## Fuera de alcance

- Guardar automáticamente sin confirmación humana.
- Reemplazar el formulario manual.
- Elegir chofer, patente o unidad de negocio a partir del OCR.
- Publicar imágenes mediante Nginx o enlaces anónimos.
- Procesar documentos sin conexión.
- Resolver dentro de esta funcionalidad los issues generales de autenticación, rate limiting o scheduler, excepto las protecciones mínimas necesarias para este flujo.

## Criterios de aceptación

La funcionalidad se considera aceptada cuando un operador autenticado puede cargar la imagen de prueba, revisar el remito `002-003-0003677`, resolver Alcogreen como proveedor, conservar cliente vacío, recibir chofer/patente/unidad desde su configuración, confirmar un viaje con `pesaje_unico=true`, origen cero, destino `49,690 / 17,080 / 32,610 TN` y producción `32,610 TN`, y consultar la imagen asociada de forma autenticada durante 60 días. Ningún viaje debe existir si el operador abandona o rechaza la revisión.
