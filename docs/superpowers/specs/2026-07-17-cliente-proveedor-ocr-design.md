# Cliente y proveedor obligatorios en la precarga OCR

## Objetivo

Corregir la identidad comercial de los viajes precargados desde una foto de remito:

- el destinatario de la mercadería debe proponerse y validarse como cliente;
- el remitente de la mercadería debe proponerse y validarse como proveedor;
- el operador debe seleccionar un cliente activo y un proveedor activo antes de confirmar.

Para el documento de referencia, el resultado esperado es:

- cliente: Alcogreen;
- proveedor: Forestal Paraguay.

## Alcance

El cambio alcanza exclusivamente al flujo de carga de viajes desde imagen:

1. extracción estructurada mediante OCR;
2. normalización y resolución contra los catálogos;
3. propuesta devuelta por el backend;
4. revisión editable en el frontend;
5. payload y validación de confirmación;
6. persistencia del viaje de pesaje único;
7. pruebas y documentación operativa del flujo OCR.

No se modificará la carga manual de viajes, la selección de chofer, patente o unidad de negocio, el cálculo de pesos, el almacenamiento de la imagen ni la regla de remito FGPY.

## Regla de negocio

Un viaje OCR de pesaje único solamente puede confirmarse cuando:

- `cliente_id` identifica un cliente existente y activo;
- `proveedor_id` identifica un proveedor existente y activo.

La ausencia, inactividad o invalidez de cualquiera de los dos bloquea la confirmación. La validación se ejecutará tanto en el frontend, para dar respuesta inmediata al operador, como en el backend, que será la autoridad final.

Los IDs no se fijarán en el código. El backend propondrá cada entidad comparando una versión normalizada de la razón social extraída con el catálogo activo correspondiente. Si la coincidencia no es única, devolverá el ID vacío y el operador deberá seleccionar manualmente una opción activa.

## Extracción OCR

El contrato de extracción separará dos campos:

- `cliente_candidato`: razón social ubicada en `DESTINATARIO DE LA MERCADERÍA`;
- `proveedor_candidato`: razón social ubicada en `REMITENTE DE LA MERCADERÍA`.

El OCR solamente transcribe las razones sociales observadas. No decide IDs ni sustituye la validación contra la base de datos.

La respuesta continuará siendo estricta: ambos campos formarán parte del conjunto exacto de claves aceptadas y podrán ser `null` cuando el texto no sea legible. La ausencia de uno de ellos no invalida el análisis de la imagen, pero deja la propuesta sin resolver y bloquea su confirmación hasta la selección manual.

## Normalización y resolución de catálogos

La normalización de razones sociales será común para clientes y proveedores. Mantendrá el comportamiento existente de:

- convertir a minúsculas;
- quitar acentos y puntuación;
- colapsar espacios;
- ignorar sufijos societarios como `S.A.`, `S.R.L.` y `S.A.S.`.

El servicio de análisis resolverá las entidades de forma independiente:

1. normalizar `cliente_candidato`;
2. buscar coincidencia exacta normalizada entre clientes activos;
3. asignar `cliente_id` solamente cuando exista una única coincidencia;
4. normalizar `proveedor_candidato`;
5. buscar coincidencia exacta normalizada entre proveedores activos;
6. asignar `proveedor_id` solamente cuando exista una única coincidencia.

Una coincidencia faltante o ambigua generará una advertencia específica para la entidad afectada. La resolución correcta de una entidad no compensará la falta de la otra.

## Contrato de análisis y confirmación

La propuesta de análisis incluirá:

- `cliente_id`;
- `cliente_candidato`;
- `proveedor_id`;
- `proveedor_candidato`;
- los campos actuales de fecha, remito, pesos, observaciones OCR y configuración observada.

La solicitud de confirmación incorporará `cliente_id` como entero positivo obligatorio y conservará `proveedor_id` con la misma condición. No aceptará razones sociales libres: los valores confirmados siempre deben provenir de los catálogos vigentes.

El servicio de confirmación trasladará ambos IDs al objeto `RegistroViajeCreate`. El backend consultará nuevamente las dos entidades y rechazará la operación con un error controlado si alguna no existe o está inactiva.

## Persistencia de pesaje único

La regla actual que prohíbe `cliente_id` en un viaje de pesaje único será reemplazada. Para `pesaje_unico=true` se exigirán:

- proveedor activo;
- cliente activo;
- los restantes requisitos actuales de configuración, remito y pesos.

El registro persistido conservará ambos vínculos. No habrá valor predeterminado ni sustitución silenciosa para cliente o proveedor en este flujo.

La carga manual mantendrá su comportamiento actual, incluido cualquier valor predeterminado existente, porque queda fuera del alcance de esta corrección.

## Experiencia de revisión

La sección `Revisá los datos detectados` mostrará dos selectores separados:

1. `Cliente`;
2. `Proveedor`.

Cada selector:

- listará solamente entidades activas de su catálogo;
- quedará precargado cuando el backend encuentre una coincidencia única;
- mostrará una opción inicial explícita cuando no haya resolución;
- será obligatorio antes de habilitar una confirmación válida.

Si falta cualquiera de los dos, la pantalla conservará la imagen y los demás datos editados, señalará qué selección falta y no enviará la confirmación.

## Errores y seguridad

El frontend impedirá construir el payload cuando cliente o proveedor:

- no sea un entero positivo;
- no figure entre los IDs activos cargados en el dispositivo.

El backend no confiará en esa comprobación y volverá a verificar ambos catálogos. Un ID inexistente o inactivo producirá un error `400` específico, sin crear viaje ni promover definitivamente la imagen.

Los errores no incluirán rutas privadas, tokens de carga, respuestas crudas del proveedor OCR ni información sensible.

## Pruebas

### Backend

- El prompt solicita remitente como proveedor y destinatario como cliente.
- El adaptador acepta y valida exactamente los dos campos candidatos.
- La normalización produce `alcogreen` y `forestal paraguay` para las variantes societarias esperadas.
- El análisis resuelve Alcogreen únicamente desde clientes activos.
- El análisis resuelve Forestal Paraguay únicamente desde proveedores activos.
- Una coincidencia ausente o ambigua deja vacío solamente el ID correspondiente y agrega una advertencia específica.
- La confirmación exige `cliente_id` y `proveedor_id`.
- Un cliente o proveedor inexistente/inactivo devuelve `400`.
- Un pesaje único válido persiste ambos IDs.
- Un fallo de validación no crea viaje ni evidencia confirmada.
- La idempotencia de confirmación continúa funcionando.

### Frontend

- El modelo de revisión conserva ambos candidatos e IDs.
- Los catálogos de configuración exponen IDs activos de clientes y proveedores.
- El payload contiene ambos IDs.
- La construcción del payload falla si falta cualquiera o si no pertenece al catálogo activo.
- La vista presenta los dos selectores y precarga las coincidencias propuestas.
- La confirmación no se envía con una selección incompleta.
- Un error conserva los valores elegidos y los demás campos editados.

### Verificación del documento de referencia

Una prueba o smoke controlado con la imagen provista debe producir:

- remito FGPY `002-003-0003755`;
- cliente candidato `Alcogreen S.A.` y cliente seleccionado Alcogreen;
- proveedor candidato `Forestal Paraguay S.A.` y proveedor seleccionado Forestal Paraguay;
- bruto `48.250 TN`;
- tara `16.460 TN`;
- neto `31.790 TN`.

La prueba de análisis no debe confirmar ni escribir un viaje real.

## Criterios de aceptación

La corrección queda aceptada cuando:

1. el OCR distingue destinatario/cliente de remitente/proveedor;
2. la revisión muestra y permite seleccionar ambas entidades;
3. no se puede confirmar sin cliente y proveedor activos;
4. el backend rechaza intentos que eludan la validación del frontend;
5. un viaje válido persiste `cliente_id` de Alcogreen y `proveedor_id` de Forestal Paraguay;
6. el flujo manual y las demás reglas del OCR permanecen sin cambios.
