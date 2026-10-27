# TransportExperience — Guía de trabajo para Claude Code

> Junto a él van `docs/SRS.pdf` y `docs/plan-desarrollo.pdf`.

---

## 1. Contexto

Proyecto académico de ingeniería de software. Equipo **SystemSolutions**, 4 integrantes,
8 semanas, 4 sprints de 2 semanas bajo Scrum.

Yo soy el **Desarrollo Lead / Backend**. Mi responsabilidad son las APIs REST, la
integración de la pasarela de pagos y el módulo de seguimiento GPS. Otro compañero hace
el frontend, otro la planificación y calidad, y otro los requisitos.

Eso significa dos cosas para ti:

1. **El backend es lo primero y el contrato de la API es el entregable más urgente.** El
   frontend no puede avanzar hasta que existan los endpoints documentados. Prioriza
   publicar un OpenAPI utilizable por encima de tener la lógica perfecta por dentro.
2. **Escribe código que otras tres personas van a leer y que un profesor va a calificar.**
   Nombres en español donde el dominio lo pide, docstrings, y documentación que se genere
   desde el código y no a mano.

Hay dos documentos oficiales del proyecto en `docs/`. **Son la fuente de verdad de los
requisitos**, no los reinterpretes ni agregues funcionalidad que no esté ahí. Si algo te
parece que falta o se contradice, dímelo y lo resolvemos con el equipo antes de codificar.

---

## 2. Qué es TransportExperience

Plataforma para alquilar, vender y entregar a domicilio vehículos de movilidad urbana
liviana: ciclas, patines y monopatines eléctricos. Incluye inventario, reservas, pagos,
mantenimiento, asignación de domiciliarios, rastreo GPS y reportes.

Cuatro tipos de usuario, con permisos distintos:

| Rol | Qué hace |
|---|---|
| **Cliente** | Consulta catálogo, alquila, compra, solicita domicilio, paga, sigue su pedido |
| **Administrador** | Inventario, precios, usuarios, tarifas, zonas, reportes |
| **Operador** | Mantenimiento, novedades, disponibilidad de la flota |
| **Domiciliario** | Recibe asignaciones y actualiza el estado de la entrega |

---

## 3. Alcance: lo que SÍ y lo que NO

El plan de desarrollo es explícito en esto y hay que respetarlo a rajatabla.

El análisis COCOMO del equipo concluyó que el sistema completo son ~12 KLOC, lo que
requeriría 10 meses y 5.3 personas. **No cabe.** El alcance comprometido es un MVP de
**~2.2 KLOC y 100 Story Points**, con 40 SP de reserva para deuda técnica.

**Cada vez que yo te pida algo que no esté en el Product Backlog, recuérdamelo antes de
implementarlo.** El riesgo número uno de este proyecto, según nuestra propia matriz, es
que el alcance se desborde. Tu trabajo incluye frenarme.

### Product Backlog comprometido (100 SP)

| ID | Sprint | SP | Historia |
|---|---|---|---|
| HU-01 | 1 | 5 | Portal web institucional (misión, visión, contacto), carga < 2s, responsive |
| HU-02 | 1 | 8 | Catálogo de dispositivos con filtros por tipo y tarifa, disponibilidad en tiempo real, vista detallada |
| HU-12 | 1 | 8 | Gestión de usuarios y roles. RBAC (Admin, Operador, Cliente) + autenticación JWT |
| HU-09 | 1 | 8 | Inactivar unidades: ocultamiento inmediato del catálogo público, registro del motivo |
| HU-03 | 2 | 10 | Alquiler con selección de fechas, validación, cálculo de tarifa, bloqueo temporal del vehículo |
| HU-04 | 2 | 8 | Compra de dispositivo: descuento de stock, comprobante preliminar |
| HU-05 | 2 | 9 | Pagos con tarjeta o PSE, tokenización, respuesta < 3s, comprobante PDF |
| HU-06 | 3 | 8 | Solicitud de domicilio: captura de dirección, tarifa de envío, confirmación |
| HU-07 | 3 | 5 | Estado del domicilio: pendiente, en camino, entregado, código de rastreo |
| HU-08 | 3 | 15 | Rastreo GPS en mapa, actualización cada 5s, precisión < 10m |
| HU-10 | 4 | 8 | Inventario sincronizado, alertas de bajo stock |
| HU-11 | 4 | 8 | Reportes de entrega y recepción, exportación PDF/Excel |

**Fuera del MVP:** HU-13 (calificaciones) y HU-14 (alertas SMS/Email). No las construyas.

### Fuera de alcance explícito

Nada de microservicios, Kubernetes, arquitectura hexagonal completa, event sourcing, ni
CQRS. Un monolito modular bien organizado es la respuesta correcta para 8 semanas y
4 personas. La colas con Redis que menciona el SRS quedan como posibilidad arquitectónica
documentada, **no como implementación**, salvo que un requisito concreto lo exija.

---

## 4. Contradicciones en los documentos que hay que resolver

Detecté estas antes de codificar. Pregúntame por cada una cuando lleguemos a la parte
correspondiente, y si el equipo corrige el SRS, actualiza este archivo.

1. **SRS 3.1.2 y 3.1.3 tienen los cuerpos intercambiados.** "Gestión de ventas" describe
   crear solicitudes de domicilio, y "Gestión de domicilios" describe vender vehículos.
   Interpretación correcta: 3.1.2 es ventas, 3.1.3 es domicilios.
2. **Los roles no coinciden.** El SRS define cuatro (cliente, administrador, operador,
   domiciliario) pero HU-12 solo pide RBAC para tres (Admin, Operador, Cliente).
   **Implementa los cuatro**, porque HU-06 y HU-07 necesitan al domiciliario.
3. **Los Story Points del backlog suman 100, pero la tabla de esfuerzo por módulo suma 92.**
   Manda el backlog.
4. **El nombre del producto aparece de tres formas**: Transportexperience,
   TransportExperience y TransporeExperience. Usa **TransportExperience** en todo el código
   y la documentación.
5. **La numeración de secciones del SRS no coincide con su tabla de contenido.** No afecta
   el código, pero conviene arreglarlo antes de entregar.
6. **HU-11 pide "firma digital de conformidad"** en el plan. **Se decidió** (Sprint 4)
   implementarla como registro de conformidad con usuario, fecha y hash del PDF, en la
   tabla `actas` (`conforme_por_id`, `conforme_en`, `hash_pdf`). **Pendiente de
   confirmación del equipo.** Ver "Cómo quedó HU-11".
7. **Estados del domicilio:** HU-07 lista tres y el SRS 3.1.7 seis. Se usan los seis del
   SRS, que cubren los de HU-07.
8. **Autenticación:** el SRS 3.9.4 dice OAuth y el backlog JWT. Se usa el flujo OAuth2
   con contraseña de FastAPI, que emite JWT.
9. **Requisitos del SRS sin historia en el backlog** (no se construyen salvo decisión del
   equipo): incidencias de soporte (3.5.6), sección de ayuda (3.7), aceptación de términos
   (3.11), aviso de mantenimiento programado (3.3.5), Firebase y lectores QR (3.9).
10. **Mantenimiento y novedades (3.1.8)** no tienen módulo propio: viven en `inventario/`
    como parte de HU-09.
11. **El plan dice v0.1.1 en la portada** pero su historial llega a la 0.2.0.

### Decisiones tomadas antes del modelo de datos (29/09/2026)

1. **Vehículos como unidades únicas**, con código y estado propio; se alquilan o se venden.
   **Accesorios y repuestos como productos con cantidad en stock**; solo se venden.
2. **El alquiler se cobra por día.**
3. **Bloqueo temporal de 15 minutos** mientras se paga (HU-03). Si no se paga, la reserva
   expira y el vehículo se libera solo.
4. **Tarifa de envío fija por zona** (HU-06), configurable por el administrador en base de
   datos.
5. **Zonas de cobertura como polígonos guardados en la base.** El cliente marca el punto en
   el mapa, el frontend envía latitud y longitud, y el backend valida que esté dentro.
   Sin Google Maps.
6. **Rastreo GPS por consulta cada 5 segundos** (HU-08), no WebSocket. *Confirmado en
   las decisiones del Sprint 3.*

### Decisiones tomadas en la revisión del modelo de datos (29/09/2026)

1. **`modelos_vehiculo`**: ficha del catálogo (nombre, foto, tarifa diaria, precio de venta)
   compartida por las unidades iguales. Un modelo sin tarifa no se alquila; sin precio, no
   se vende. Accesorios y repuestos siguen aparte, como `productos` con cantidad.
2. **Módulo `portal/` mínimo**: solo contenido institucional (HU-01) y horarios de atención.
3. **Tipos de vehículo y métodos de pago en tablas**, configurables por el administrador.
4. **Zonas en GeoJSON (`jsonb`), sin PostGIS.** La validación de punto dentro de polígono es
   una **función propia con tests, sin dependencias nuevas** (se implementa con HU-06).
5. **`vehiculos.estado` es solo el estado físico actual.** La disponibilidad por fechas sale
   de `alquileres` (ver 7.1 y 7.2).
6. **Un domicilio es la entrega de un alquiler o de una venta**, ligado siempre a
   exactamente uno de los dos. No hay domicilios sueltos. El vehículo del domiciliario es
   opcional y, si se usa, queda en `asignado_a_domicilio`.
7. **Un solo pago con el envío incluido.** El alquiler o la venta guardan el desglose
   (`subtotal`, `valor_envio`, `total`) y el pago cubre el total.
8. **Fechas de alquiler inclusivas.** Del 5 al 7 son 3 días; el siguiente cliente puede
   recoger desde el día 8.
9. **Dirección fuera de cobertura: se bloquea** (SRS 3.6.1). No se marca para revisión.

### Decisiones de la revisión de HU-02 (29/09/2026)

1. **Accesorios y repuestos no van en el catálogo de HU-02.** Su listado se hace con HU-04
   (compra).
2. **No hay filtro por ubicación** en el catálogo: no está en HU-02 (aunque el SRS 3.4.2 lo
   mencione).
3. **Las unidades dentro de la ficha de un modelo van sin paginar** (ver la excepción en la
   sección 9).

### Decisiones de la revisión de HU-09 (29/09/2026)

1. **Solo las novedades críticas abiertas bloquean el regreso a servicio.** Las no críticas
   quedan como registro y no bloquean.
2. **Los domiciliarios pueden reportar novedades, incluidas críticas**, pero **no pueden
   cerrarlas ni devolver unidades a servicio**: eso es solo de operador y administrador.
   Inactivar (HU-09) también es solo de operador y administrador.
3. **Los alquileres vigentes de una unidad que sale de servicio no se cancelan solos.** La
   respuesta los informa en `alquileres_afectados`.

### Decisiones del Sprint 2 (27/10/2026)

1. **Máximo de días por alquiler: 30**, configurable en base de datos (tabla
   `parametros_sistema`, clave `max_dias_alquiler`; SRS 3.5.3). Se lee en cada reserva.
2. **Vehículo reservado para compra que pasa a mantenimiento y luego se aprueba el pago:**
   la venta **no se completa**, se registra un pago de compensación (devolución) y se avisa
   al administrador. *Implementado en HU-04* (ver "Cómo quedó HU-04"); la ejecución de la
   devolución en la pasarela llega con HU-05.
3. **Alquileres afectados por mantenimiento:** reasignación **asistida por el
   administrador** (`POST /alquileres/{id}/reasignacion`: otra unidad libre del mismo
   modelo, mismas fechas y precio, las dos unidades bloqueadas en la misma transacción) y
   la consulta de **alquileres en riesgo** (`GET /alquileres/en-riesgo`). **Sin
   reasignación automática.** Si no hay unidad libre, el administrador decide entre esperar
   o cancelar con devolución (llega con HU-05).
4. **El cliente solo cancela un alquiler mientras está en `pendiente_pago`.** Uno pagado se
   cancela con devolución, por el administrador (HU-05).
5. **Devolución de un vehículo que entró en mantenimiento durante el alquiler:** el alquiler
   se finaliza y el vehículo **se queda en `mantenimiento`** hasta que el taller cierre su
   novedad. *Implementado en HU-03.*

### Cómo quedó HU-03 (27/10/2026)

- **El cliente reserva un modelo, no una unidad**: el sistema asigna la primera unidad
  libre en esas fechas (el catálogo muestra modelos, no unidades).
- **Crear una reserva bloquea todas las unidades del modelo**, siempre en orden de `id`:
  serializa las reservas de un mismo modelo y evita *deadlocks*. La reasignación usa el
  mismo orden.
- **Pago con la pasarela falsa** (`app/modulos/pagos/pasarela.py`): interfaz
  `PasarelaPagos` + `PasarelaFalsa`. `POST /alquileres/{id}/pago` cobra y, si se aprueba,
  confirma. HU-05 agrega Wompi y el webhook, que llamará a `alquileres.servicio.confirmar_pago`.
- **Pendientes vencidos:** se expiran al reservar (los de las unidades del modelo) y al
  intentar pagar o cancelar. Las consultas muestran `expirado` sin escribir en la base.
- **Hecho en HU-04:** el barrido previo a reservar también expira las compras vencidas que
  apartan unidades del modelo (devolviendo su stock).
- **Sin endpoint** para que el administrador edite `parametros_sistema`; por ahora se
  cambia en la base (adminer). *Pendiente de decidir con el equipo si se agrega.*

### Cómo quedó HU-04 (27/10/2026)

- **Carrito**: `POST /ventas` con `vehiculos` (por modelo; el sistema asigna las unidades,
  como en HU-03) y `productos` (por cantidad). Una sola venta, un solo pago.
- **Listado de accesorios y repuestos** en el catálogo público: `GET /catalogo/productos`.
- **Orden global de bloqueo** (`inventario.servicio.bloquear_inventario`): vehículos por
  `id`, luego productos por `id`, luego la operación. Alquileres y ventas lo comparten.
- **Expirar antes de operar**: `ventas/liberacion.py` expira las compras vencidas que
  apartan lo pedido (devuelve stock y suelta unidades) en la misma transacción, también al
  reservar un alquiler.
- **No se vende** una unidad con alquileres `pendiente_pago`, `confirmado` o `en_curso`
  (sin importar la fecha). Una unidad apartada para compra no vuelve a servicio mientras
  la compra esté vigente.
- **Decisión 2**: si al aprobarse el pago una unidad ya no está `reservado`, la venta se
  cancela con `motivo_cancelacion`, se devuelve lo apartado y se registra un pago de
  compensación `pendiente`. El aviso al administrador es `GET /ventas/devoluciones-pendientes`
  más una advertencia en el log (no hay notificaciones: HU-14 está fuera del MVP).
- **Comprobante preliminar** en JSON (`GET /ventas/{id}/comprobante`). El PDF llega con HU-05.
- **Modelo de datos**: nueva columna `ventas.motivo_cancelacion` (migración `c74d60acf0af`).

### Decisiones de HU-05 (27/10/2026)

Las 5 decisiones de "Cómo quedó HU-04" quedaron **aprobadas** por el equipo.

1. **PSE lento:** mientras un alquiler o una compra tenga un pago `pendiente`, el bloqueo de
   15 minutos **no vence**. Expira solo cuando la pasarela reporta el pago como rechazado,
   expirado o con error, o tras un máximo de **60 minutos** con el pago pendiente
   (`max_minutos_pago_pendiente` en `parametros_sistema`). Si después llega un pago
   aprobado, se registra la devolución, igual que en la decisión 2 del Sprint 2.
2. **El pago se guarda como `pendiente` y se confirma en la base ANTES de llamar a Wompi.**
3. **Webhook de Wompi** con verificación de firma e idempotencia (7.3), más una **consulta
   de respaldo** del estado de la transacción a la API de Wompi, porque en desarrollo Wompi
   no puede llegar a 127.0.0.1. **Sin túneles.**
4. **Comprobante en PDF con ReportLab.**

Las llaves de sandbox las pone el responsable en el `.env`: **nunca se piden por chat ni
se escriben en el código.**

### Cómo quedó HU-05 (27/10/2026)

- **Cobro en tres pasos** (`pagos/procesamiento.py`): (1) con la operación bloqueada se
  guarda el pago `pendiente` y se hace commit; (2) se llama a la pasarela fuera de toda
  transacción; si no responde, el pago queda `pendiente`; (3) se aplica el resultado. El
  paso 3 también lo disparan el webhook y la consulta de respaldo; los tres son
  idempotentes (un pago ya resuelto no cambia).
- **Bloqueo extendido:** al empezar el cobro, `expira_en` de la operación pasa a
  `ahora + max_minutos_pago_pendiente`, y el plazo original queda en
  `pagos.bloqueo_original_hasta`. Si el cobro falla, se restaura ese plazo (si ya pasó,
  la operación expira). Así nadie retiene un vehículo encadenando pagos fallidos.
- **Un solo cobro en curso por operación**, y no se cancela una operación con un pago
  pendiente (`pago_en_curso`): si el banco lo aprobara después, habría que devolver.
- **Wompi sandbox** (`pagos/wompi.py`): `GET /merchants/info` para los tokens de aceptación
  (el endpoint viejo `/merchants/:llave` se retira el 31/10/2026), `POST /transactions`
  con firma de integridad, consulta de respaldo con `GET /transactions?reference=` (llave
  privada). URL del sandbox fija en el código. Timeouts cortos (SRS: < 3 s).
- **Tarjeta tokenizada en el frontend**: el número nunca llega al backend, solo el token.
- **Configuración:** nueva variable `WOMPI_SECRETO_INTEGRIDAD`. La API no arranca con
  llaves que no sean de sandbox (`pub_test_`, `prv_test_`, `test_events_`,
  `test_integrity_`), ni con `PAGOS_PROVEEDOR=wompi` y las llaves de ejemplo.
- **Webhook** `POST /pagos/webhooks/wompi`: guarda siempre el cuerpo crudo; procesa solo
  con firma válida, ambiente `test`, referencia conocida y monto igual; responde 200.
- **Consulta de respaldo**: `GET /pagos/{referencia}` pregunta a la pasarela si el pago
  sigue pendiente, y `python -m scripts.sincronizar_pagos` lo hace con todos.
- **Devoluciones**: `GET /pagos/devoluciones-pendientes` y
  `POST /pagos/{referencia}/devolucion-ejecutada` (el administrador hace el reembolso en el
  panel de Wompi y lo registra). Nueva `POST /alquileres/{id}/cancelacion-con-devolucion`
  (administrador; decisiones 3 y 4 del Sprint 2). `confirmado → cancelado` solo por ahí.
- **Comprobante PDF**: `GET /pagos/{referencia}/comprobante` (ReportLab).
- **Modelo de datos**: `pagos.url_redireccion`, `pagos.bloqueo_original_hasta` y el
  parámetro `max_minutos_pago_pendiente` (migración `7f6b572858d8`).
- **Pendiente de validar con las llaves reales**: el flujo contra el sandbox de Wompi
  (los tests usan un transporte simulado). El ejemplo de checksum de eventos de la
  documentación de Wompi no corresponde a su propia cadena (ver `tests/pagos/test_wompi.py`):
  hay que confirmar la firma con un evento real.

### Decisiones del Sprint 3 (27/10/2026)

Las dos cosas extra de HU-05 (cancelación con devolución por el administrador y registro
de la devolución ejecutada) quedaron **aprobadas**.

1. **El domicilio se agrega a un alquiler o compra mientras está en `pendiente_pago`**,
   antes de pagar; el total se recalcula con la tarifa de la zona. Dirección fuera de
   cobertura: **se bloquea**.
2. **La asignación del domiciliario la hace el administrador u operador a mano**, con una
   lista de domiciliarios disponibles. **Sin asignación automática.**
3. **El código de rastreo permite una consulta pública** que muestra solo el estado y las
   horas de cada cambio, sin dirección ni datos personales (SRS 3.6.4). *(HU-07)*
4. **GPS: consulta cada 5 segundos**, con el simulador sobre Bucaramanga (sección 8).
   *(HU-08)*
5. **Pendiente menor para el Sprint 4:** limitar el tamaño del cuerpo del webhook de pagos.

### Cómo quedó HU-06 (27/10/2026)

- **Punto dentro de polígono** propio (`domicilios/geometria.py`): trazado de rayos, el
  borde cuenta como adentro, soporta huecos y MultiPolygon. En un borde compartido entre
  dos zonas se cobra la tarifa más baja.
- **Solicitud** (`POST /domicilios`): solo con la operación en `pendiente_pago`, vigente y
  sin un pago en curso (si no, el total cambiaría bajo un cobro ya enviado). Suma
  `valor_envio` y recalcula `total`. Un solo domicilio vigente por operación; para cambiar
  la dirección se cancela y se pide otro.
- **Si la operación expira o se cancela**, su domicilio pendiente se cancela con ella
  (`domicilios/liberacion.py`, llamado desde el cambio de estado de alquileres y ventas).
  `cancelacion-con-devolucion` se rechaza si el domicilio ya está asignado: primero hay que
  cancelar la entrega (HU-07).
- **Asignación** (`/domicilios/{id}/asignacion`): operación pagada; domiciliario activo y
  **sin entregas en ruta** ("disponible"); vehículo de transporte opcional, `disponible`,
  sin alquiler hoy y distinto de la unidad que se entrega. Orden de bloqueo: vehículo,
  domiciliario, domicilio. Tests de concurrencia: la misma moto o el mismo domiciliario
  en cuatro asignaciones simultáneas quedan en una sola.
- **Nota del vehículo del domiciliario, resuelta**: `GET /domicilios/asignados` le muestra
  su `vehiculo_transporte`, y `reportar_novedad` ahora rechaza al domiciliario si la unidad
  no es la de una entrega suya en ruta.
- **Sin cambios en las tablas** (solo relaciones ORM nuevas en `Domicilio`).
- **Para HU-07** (resuelto, ver abajo): los cambios de estado de la entrega, la
  cancelación de una entrega asignada, el alquiler al entregar y el rastreo público.

### Decisiones de HU-07 (27/10/2026)

Los 5 puntos de "Cómo quedó HU-06" quedaron **aprobados**.

1. **Los cambios de estado (recogido, en_camino, entregado) los hace el domiciliario
   asignado**; el administrador y el operador también pueden, para corregir.
2. **Al entregar el domicilio de un alquiler, el alquiler pasa a `en_curso` y el vehículo
   a `alquilado`**, igual que la entrega en el local.
3. **Un domicilio asignado o en ruta solo lo cancela el administrador u operador, con
   motivo.** El cliente solo cancela antes de pagar.
4. **Si un domicilio pagado se cancela, se registra la devolución del valor del envío**
   con el mecanismo de devoluciones de HU-05; la reserva o compra sigue vigente.
5. **Consulta pública por código de rastreo: solo estado y hora de cada cambio**, sin
   dirección ni datos personales.

### Cómo quedó HU-07 (27/10/2026)

- `POST /domicilios/{id}/estado` con `recogido`, `en_camino` o `entregado`, sin saltar
  pasos. Un domiciliario que no es el asignado recibe 404 (no se revela la entrega).
- **Entregar** reutiliza `alquileres.servicio.poner_en_curso`, el mismo núcleo de la
  entrega en el local: si el alquiler no se puede entregar (fuera de fechas, unidad en
  mantenimiento), nada cambia. El vehículo de transporte vuelve a `disponible` (si entró
  en mantenimiento en la ruta, se queda). Se guarda `entregado_en`.
- **La entrega en el local se rechaza si el alquiler tiene un domicilio vigente**, para
  no entregar dos veces.
- `POST /domicilios/{id}/cancelacion-por-despacho` (motivo): solo con la operación
  pagada; libera el vehículo de transporte y registra la devolución del envío.
- **Nunca se devuelve más de lo cobrado**: `pagos.servicio.registrar_devolucion`
  descuenta las devoluciones anteriores del mismo cobro (p. ej., envío devuelto y luego
  `cancelacion-con-devolucion` del alquiler devuelve solo el resto). Si no queda nada,
  no registra nada.
- `GET /domicilios/rastreo/{codigo}`: público; solo `codigo_rastreo`, `estado` y
  `cambios` (`estado`, `en`). Hay un test que verifica que no aparezcan la dirección, el
  teléfono, el correo ni las coordenadas.
- **Orden de bloqueo** al avanzar o cancelar: las unidades (transporte y lo que se
  entrega), la operación y el domicilio.
- **Sin cambios en las tablas.**

### Decisiones de HU-08 (27/10/2026)

HU-07 quedó **aprobada**.

1. **Las posiciones llegan por HTTP** a un endpoint del backend, autenticadas con una
   **clave propia de cada vehículo** (no con el JWT de usuarios). La clave se guarda
   cifrada (hash), nunca en claro.
2. **El simulador es un programa aparte** (`python -m simulador_gps`) que mueve vehículos
   por calles de Bucaramanga con velocidades realistas y envía posiciones cada 5 segundos
   por el **mismo endpoint** que usaría un GPS real. `GPS_FUENTE` en el `.env` decide si se
   usa.
3. **El mapa de la flota es solo para administrador y operador.** El cliente sigue viendo
   solo el estado de su domicilio.
4. **Indicador en tiempo real**: un vehículo sin posición hace más de 30 segundos aparece
   "sin señal" (umbral configurable en base de datos).
5. **7 días de historial**, con un script de limpieza en `scripts/`; la consulta de "última
   posición de cada vehículo" debe ser rápida (índice adecuado). Precisión: 6 decimales.
6. **Consulta cada 5 segundos desde el frontend**, no WebSocket.

### Cómo quedó HU-08 (27/10/2026)

- **Clave GPS**: `POST /rastreo/vehiculos/{id}/clave` (solo administrador) genera
  `gps_` + 256 bits aleatorios, la muestra una vez y guarda su **SHA-256** en
  `vehiculos.hash_clave_gps` (único). SHA-256 y no bcrypt: la clave es aleatoria (no hay
  diccionario que probar) y bcrypt costaría ~0,25 s de CPU en cada posición. Emitir otra
  revoca la anterior. Cada clave se emite para una `fuente` (`simulador` o `dispositivo`).
- **`POST /rastreo/posiciones`** con `X-Clave-Gps`: solo acepta la fuente de `GPS_FUENTE`
  (así, con `dispositivo`, el simulador queda fuera aunque tenga clave). Redondea a 6
  decimales; rechaza horas futuras (> 1 min) o de más de 7 días. **No toca la fila del
  vehículo**, para no competir cada 5 s con los bloqueos de reservas y ventas.
- **Mapa** `GET /rastreo/flota`: `LATERAL ... ORDER BY registrado_en DESC LIMIT 1` por
  vehículo, sobre el índice `(vehiculo_id, registrado_en DESC)`. Verificado con `EXPLAIN`:
  un Index Scan de una fila por vehículo, 0,12 ms con 345.600 posiciones (20 vehículos × 1
  día cada 5 s). Hay un test que lo mide. La señal usa la hora de **llegada** al servidor,
  no el reloj del dispositivo. Umbral: parámetro `segundos_sin_senal` = 30.
- **Recorrido** `GET /rastreo/vehiculos/{id}/recorrido` (última hora por defecto).
- **Limpieza**: `python -m scripts.limpiar_posiciones_gps [--dias 7]`.
- **Simulador** (`simulador_gps/`): `rutas.py` (5 recorridos aproximados por calles reales
  de Bucaramanga), `movimiento.py` (lógica pura: haversine, ida y vuelta, velocidad por
  tipo, paradas, error del GPS de 3-8 m, batería) y `simulador.py` (cliente HTTP: inicia
  sesión como administrador, emite claves de fuente `simulador` y reporta). Se prueba de
  punta a punta contra la API con el cliente de pruebas, y se corrió de verdad contra
  uvicorn en una base temporal.
- **Modelo de datos**: `vehiculos.hash_clave_gps`, `fuente_gps`, `clave_gps_emitida_en` y
  el parámetro `segundos_sin_senal` (migración `845c1b8b60d3`).

### Decisiones del Sprint 4 (27/10/2026)

Los 4 puntos de "Cómo quedó HU-08" quedaron **aprobados**. Sprint 3 cerrado.

1. **HU-10 incluye la gestión del inventario para el administrador**: crear y editar tipos
   de vehículo, modelos, unidades y productos (SRS 3.1.4), con auditoría. **Alertas de bajo
   stock**: un endpoint con los productos en o bajo su stock mínimo, sin correo ni SMS
   (HU-14 está fuera del MVP).
2. **HU-11: actas de entrega y recepción**, generadas al entregar o recibir un vehículo (en
   el local y por domicilio), exportables a PDF (ReportLab) y Excel (openpyxl). Firma de
   conformidad: registro con usuario, fecha y hash del PDF (tabla `actas`), **pendiente de
   confirmar con el equipo**.
3. **Requisitos no funcionales pendientes para cerrar en este sprint**: el script de
   respaldo y restauración de Postgres documentado (SRS 3.3.2), y limitar el tamaño del
   cuerpo del webhook de pagos.

### Cómo quedó HU-10 (27/10/2026)

- **Rutas bajo `/inventario`** (`inventario/rutas_gestion.py`, servicio en
  `inventario/gestion.py`, esquemas en `inventario/esquemas_gestion.py`): consultar es del
  administrador y el operador; crear, editar y ajustar, solo del administrador.
- **`PATCH` parciales** (solo cambia lo enviado; null no vale en campos obligatorios).
  Cada cambio se audita con el antes y el después **solo de lo que cambió** (tarifas y
  precios incluidos); editar sin cambios no deja registro.
- **El stock no se edita**: `POST /inventario/productos/{id}/ajustes` suma o resta sobre
  la fila bloqueada (`FOR UPDATE`), con motivo, y nunca deja el stock en negativo. Test de
  concurrencia: 6 ajustes y 6 compras simultáneos dejan el stock exacto.
- **No se editan** el estado de una unidad (tiene sus flujos), ni el código ni el modelo
  de una unidad, ni el código de un producto: son su identidad.
- **Unidades**: entran `disponible`; código en mayúsculas y único; `nivel_bateria` solo si
  el tipo usa batería; una vendida no se edita; editar bloquea la fila (regla 1 de 7.1).
- **Alertas**: `GET /inventario/alertas-stock` (activos con `stock <= stock_minimo`, los
  más urgentes primero) y `GET /inventario/resumen` (unidades por estado y productos en
  alerta). `Producto.bajo_stock` es una propiedad, no una columna.
- **Sin cambios en las tablas.**

### Cómo quedó HU-11 (27/10/2026)

Los 5 puntos de "Cómo quedó HU-10" quedaron **aprobados**, incluido el resumen.

- **Firma de conformidad: se decidió como registro de usuario, fecha y hash (SHA-256) del
  PDF del acta** (tabla `actas`: `conforme_por_id`, `conforme_en`, `hash_pdf`). *Decidido
  así para implementar HU-11; sigue **pendiente de confirmación del equipo**.* No es una
  firma digital con certificado.
- **Las actas nacen solas** (`reportes/registro.py`), en la misma transacción de la
  operación: entrega y recepción en el local (`/alquileres/{id}/entrega` y `/devolucion`)
  y entrega por domicilio (al marcar `entregado`; una compra lleva un acta por unidad, los
  accesorios no). Si la operación falla, no queda acta. Cuerpo opcional
  `{estado_vehiculo, nivel_bateria}`; sin él, "Sin observaciones.".
- **No hay actas** de la entrega de una compra en el local (no existe ese flujo: una compra
  pagada se recoge sin registro) ni de recepción por domicilio (no existe recogida a
  domicilio). *Si el equipo las quiere, son historias nuevas.*
- **PDF determinista** (`reportes/documentos.py`, ReportLab con `invariant=True`): la misma
  acta produce los mismos bytes, así que su SHA-256 es la huella. La conformidad la da el
  cliente de la operación, una sola vez; `/verificacion` regenera el PDF y compara.
  **Limitación conocida:** el PDF incluye los nombres del cliente y de quien registró; si
  alguno cambia su nombre después, la verificación de un acta ya conformada dará "no
  coincide".
- **Exportación** a Excel (openpyxl, una fila por acta, con filtros) y a PDF (tabla
  horizontal), por rango de días de Colombia (por defecto 30, máximo 92).
- **Sin cambios en las tablas** (`actas` ya existía); solo relaciones ORM nuevas en `Acta` y
  `Alquiler.cliente`. Nueva dependencia: `openpyxl`.

---

## 5. Stack

Propón cambios si tienes una razón fuerte, pero no los apliques sin que yo confirme.

- **Python 3.11+**, entorno virtual local (`venv`), nunca instalación global
- **FastAPI** + **Uvicorn** — da OpenAPI automático, que es justo lo que el frontend necesita
- **SQLAlchemy 2.x** + **Alembic** para migraciones
- **PostgreSQL** vía **Docker Compose**, para que los cuatro tengamos exactamente la misma
  base. **Los tests que tocan base de datos también usan Postgres**, en una base de prueba
  separada dentro del mismo contenedor (`transportexperience_pruebas`). **Nada de SQLite**:
  el modelo usa funciones propias de Postgres (bloqueo de fila y la restricción de exclusión
  que impide reservas con fechas solapadas) y no queremos dos bases que se comporten
  distinto. Los tests de lógica pura (transiciones de estado, cálculo de tarifas) no usan
  base de datos.
- **Pydantic v2** para esquemas de entrada y salida
- **python-jose** + **passlib[bcrypt]** para JWT y hash de contraseñas
- **pytest** + **httpx** para tests
- **ruff** para formateo y linting
- **ReportLab** o **WeasyPrint** para los comprobantes PDF (HU-05, HU-11)
- **openpyxl** para la exportación a Excel (HU-11)

Para la pasarela: **Wompi en modo sandbox**. Nunca llaves de producción, nunca dinero real.
Si en algún momento ves una llave que empiece por algo distinto a `pub_test_` o
`prv_test_`, detente y avísame.

---

## 6. Arquitectura

Monolito modular. Una carpeta por módulo del SRS, con fronteras claras entre ellos.

```
transportexperience/
├── CLAUDE.md
├── README.md
├── docker-compose.yml          ← Postgres y adminer
├── .env.example
├── .gitignore
├── pyproject.toml
├── alembic/
├── docs/
│   ├── SRS.pdf
│   ├── plan-desarrollo.pdf
│   ├── uml/                    ← diagramas en PlantUML o Mermaid, versionados
│   └── api/                    ← OpenAPI exportado
├── app/
│   ├── main.py
│   ├── config.py               ← settings con Pydantic, valida el .env al arrancar
│   ├── db.py
│   ├── seguridad.py            ← JWT, hashing, dependencias de permisos
│   ├── auditoria.py            ← registro transversal de cambios sensibles
│   ├── comun/                  ← errores, paginación, tipos de dinero, utilidades
│   └── modulos/
│       ├── usuarios/           ← HU-12
│       ├── inventario/         ← HU-02, HU-09, HU-10
│       ├── alquileres/         ← HU-03
│       ├── ventas/             ← HU-04
│       ├── pagos/              ← HU-05
│       ├── domicilios/         ← HU-06, HU-07
│       ├── rastreo/            ← HU-08
│       ├── reportes/           ← HU-11
│       └── portal/             ← HU-01 (solo contenido institucional y horarios)
├── scripts/                    ← utilidades (generar el diagrama ER, respaldos)
├── simulador_gps/              ← ver sección 8
├── seeds/
└── tests/
```

Cada módulo sigue la misma estructura interna: `modelos.py`, `esquemas.py`,
`servicio.py`, `rutas.py`, `excepciones.py`. **Las reglas de negocio viven en
`servicio.py`, nunca en `rutas.py`.** Las rutas solo validan entrada, llaman al servicio y
formatean la salida. Esto importa porque los tests van contra los servicios y porque el
profesor va a buscar exactamente esa separación.

---

## 7. Las tres cosas que no pueden fallar

Si algo de este proyecto se rompe en la sustentación, va a ser una de estas. Ponles tests
antes que a nada más.

### 7.1 Que un vehículo no se reserve dos veces

El SRS 3.3.3 lo pide explícitamente y es el requisito técnicamente más difícil de todo el
sistema. Dos clientes pidiendo el mismo monopatín al mismo tiempo es el caso clásico de
condición de carrera.

**No lo resuelvas con un `if disponible:` en Python.** Eso falla bajo concurrencia. Usa:

- Una transacción con bloqueo de fila (`SELECT ... FOR UPDATE`) sobre el vehículo, y
- **Decidido:** la restricción de exclusión `ex_alquileres_sin_solapamiento` en Postgres
  (extensión `btree_gist`), que impide dos alquileres activos del mismo vehículo con rangos
  de fechas que se crucen. Ver 7.2.

Escribe un test que lance dos reservas concurrentes del mismo vehículo y verifique que
exactamente una gana. Ese test es oro para la sustentación.

**Regla 1: toda operación que toque un vehículo empieza bloqueando su fila.** Alquiler,
venta y domicilio arrancan con `SELECT ... FOR UPDATE` sobre la fila del vehículo, dentro de
la misma transacción que hace el cambio. La restricción de exclusión solo compara alquileres
entre sí: no impide que una venta y un alquiler, o dos ventas, tomen el mismo vehículo al
mismo tiempo. El bloqueo de fila sí, porque serializa todas las operaciones sobre ese
vehículo. Con la fila bloqueada, el servicio valida:

- **No vender** un vehículo con alquileres activos o futuros (`pendiente_pago`,
  `confirmado`, `en_curso`).
- **No alquilar** un vehículo `vendido` ni uno `reservado` (compra pendiente de pago).

**Regla 2: los pendientes vencidos se expiran antes de operar.** Nada pasa solo de
`pendiente_pago` a `expirado` cuando vence `expira_en`: una reserva abandonada bloquearía el
vehículo (y el stock) para siempre. Sin tareas en segundo plano ni Redis, la regla es:
**antes de crear un alquiler o una venta, en la misma transacción**, se marcan como
`expirado` los alquileres y `expirada` las ventas en `pendiente_pago` con `expira_en`
vencido. Una venta que expira **devuelve su stock** y libera sus vehículos (`reservado` →
`disponible`). Más adelante habrá un script en `scripts/` para hacer ese barrido a mano.

### 7.2 Los estados de los vehículos y los pedidos

El SRS 3.3.6 exige integridad de estados. Modela las transiciones explícitamente y prohíbe
las inválidas en el código, no en la interfaz.

`vehiculos.estado` es **solo el estado físico actual** del vehículo. Que un monopatín esté
reservado para el día 5 no cambia su estado hoy: la disponibilidad por fechas sale de la
tabla `alquileres`.

```
Vehículo:  disponible → alquilado → disponible   (entrega y devolución de un alquiler)
           disponible → reservado → vendido      (reservado = compra pendiente de pago;
                        reservado → disponible    vendido es terminal)
           cualquiera → mantenimiento → disponible (requiere autorización de operador)
           disponible → asignado_a_domicilio → disponible  (vehículo del domiciliario)

Domicilio: pendiente → asignado → recogido → en_camino → entregado
           cualquiera → cancelado
```

Una novedad crítica (SRS 3.1.8) debe pasar el vehículo a no disponible **automáticamente**,
y solo un operador puede devolverlo a servicio.

Un vehículo no puede volver a `disponible` si tiene una reserva activa, un mantenimiento
abierto o un domicilio sin finalizar.

**Protección contra dobles reservas por fechas:** una *exclusion constraint* de Postgres,
`ex_alquileres_sin_solapamiento`, sobre `(vehiculo_id WITH =, daterange(fecha_inicio,
fecha_fin, '[]') WITH &&)` para los alquileres activos (`pendiente_pago`, `confirmado`,
`en_curso`). Usa la extensión `btree_gist`, creada en la misma migración. Las fechas son
inclusivas (`'[]'`): un alquiler del 5 al 7 bloquea los días 5, 6 y 7. Un alquiler
`pendiente_pago` vencido sigue bloqueando hasta que el servicio lo marque `expirado`; por
eso, al crear una reserva, primero se expiran los bloqueos vencidos de ese vehículo en la
misma transacción.

### 7.3 Los pagos

- **El dinero se guarda como entero, en pesos.** El peso colombiano no usa centavos en la
  práctica. `float` para plata está prohibido en todo el código, incluso temporalmente.
- **La verdad del pago la da el webhook, no el navegador.** Nunca marques un pago como
  aprobado porque el usuario volvió a la página de éxito. PSE puede tardar minutos.
- **Verifica la firma de cada webhook entrante** antes de procesarlo.
- **Idempotencia obligatoria.** El webhook puede llegar repetido. Guarda la referencia
  única de la transacción y descarta duplicados.
- Guarda el cuerpo crudo del webhook. Cuando algo falle, es lo único que te va a decir
  qué pasó.
- Estados del pago: `pendiente`, `aprobado`, `rechazado`, `expirado`, `error`. Un pago
  aprobado nunca se modifica, se compensa con otro registro.

---

## 8. El GPS: constrúyelo simulado primero

HU-08 son 15 SP, la historia más cara del backlog, y depende de hardware que muy
probablemente no tenemos. El plan lo lista como riesgo de latencia, pero el riesgo real es
que no haya dispositivos.

**No dejes que el proyecto se bloquee esperando un GPS físico.**

Diseña el módulo de rastreo con una interfaz de entrada de posiciones y dos
implementaciones: un dispositivo real que reporta por HTTP, y un **simulador** que mueve
vehículos por coordenadas de Bucaramanga con velocidades realistas, publicando cada 5
segundos. Se escoge con una variable de entorno.

Con eso se puede desarrollar, probar y sustentar el módulo completo sin un solo aparato.
Y si aparecen los dispositivos, solo se cambia la implementación.

Lo mismo aplica a la pasarela: una interfaz de pagos con implementación Wompi sandbox y
una implementación falsa para tests, que no toque la red.

---

## 9. El contrato de la API es lo que desbloquea al equipo

Antes de implementar la lógica de un módulo, **define y publica sus endpoints con sus
esquemas de Pydantic**, aunque devuelvan datos de ejemplo. El frontend puede empezar
contra eso mientras tú terminas por dentro.

Reglas de la API:

- REST sobre HTTPS, JSON, autenticación con JWT en el header `Authorization: Bearer`.
- Rutas en plural y en inglés o español, pero **consistentes**: escoge una y no mezcles.
- Todas las listas paginadas desde el primer día (SRS 3.4.6). Nunca devuelvas una tabla
  completa.
  **Excepción:** las listas anidadas pequeñas y acotadas (como las unidades de un modelo
  dentro de su ficha) pueden ir sin paginar.
- Errores con una estructura uniforme: código, mensaje legible para el usuario y acción
  recomendada. El SRS 3.2.3 lo pide explícitamente: el mensaje debe decir la causa y qué
  hacer.
- Exporta el OpenAPI a `docs/api/openapi.json` en cada cambio importante y súbelo al repo.

---

## 10. Requisitos no funcionales que sí hay que implementar

No los dejes para el final, porque son los que el profesor va a revisar contra el SRS:

- **Auditoría (3.5.4):** registra quién cambió qué y cuándo en inventario, tarifas, estados
  de vehículos, cancelaciones y ajustes de pagos. Hazlo transversal, no módulo por módulo.
- **Configuración sin tocar código (3.5.3):** tarifas, zonas de cobertura, horarios de
  atención y métodos de pago van en base de datos, editables por el administrador. **No los
  escribas como constantes en el código.**
- **Zonas de cobertura (3.6.3):** validar que la dirección de entrega esté dentro del área
  autorizada, y bloquear o marcar para revisión si no lo está.
- **Tiempos de respuesta (3.4.1, 3.4.2):** consulta de disponibilidad < 3s, catálogo < 4s.
  Pon índices en la base desde el principio y un test que mida.
- **Respaldos (3.3.2):** un script de backup de Postgres y su instrucción de restauración.
  No hace falta más, pero tiene que existir y estar documentado. **Hecho (Sprint 4):**
  `python -m scripts.respaldo_bd respaldar|restaurar` (`pg_dump -Fc` y `pg_restore`
  dentro del contenedor), documentado en el README. Restaurar sobre la base del `.env`
  exige `--confirmar`; `--base` restaura en otra base para probar un respaldo. Hay un
  test de ida y vuelta real (respalda la base de pruebas, la restaura en otra y compara).
- **Límite del cuerpo del webhook de pagos (Sprint 4):** 64 KiB
  (`pagos.rutas.LIMITE_CUERPO_WEBHOOK`). Se lee por partes y se corta al pasar el
  límite (`app/comun/peticiones.py`), sin cargar el cuerpo entero a memoria; responde 413
  con `cuerpo_demasiado_grande` y no guarda el evento.
- **Registro de fallas (3.3.4):** logging estructurado, y que un error en un pago o una
  reserva conserve el estado anterior.

---

## 11. Cómo quiero que trabajes

- **Pregunta antes de decisiones grandes.** Cambiar de framework, agregar una dependencia
  pesada, cambiar el modelo de datos: se consulta primero.
- **No instales nada global sin avisarme.** Todo en el venv o en Docker.
- **Commits pequeños, en español, referenciando la historia**: `HU-03: bloqueo de vehículo
  al crear reserva`.
- **Una rama por historia de usuario**, nombradas `hu-03-alquileres`. Trabajamos cuatro
  personas sobre el mismo repo. Excepción: el Bloque 0 (fundación) se hace en la rama
  `claude/clever-ride-knc6dj`.
- **Nunca subas secretos.** `.env` en `.gitignore` desde el primer commit. Si ves una
  credencial en el código, párame.
- **Tests sobre los servicios**, no sobre las rutas. Prioridad: concurrencia de reservas,
  transiciones de estado, cálculo de totales, webhooks de pago.
- **Genera los diagramas UML desde el código** (PlantUML o Mermaid en `docs/uml/`) y
  mantenlos actualizados. Es un entregable del proyecto y así no se desincroniza.
- Cuando termines una tarea, dime **el comando exacto para que yo la pruebe**.
- Explícame en español y no asumas que conozco cada herramienta.
- Si algo de esta especificación te parece mala idea, dímelo antes de implementarlo.

---

## 12. Plan de arranque

En este orden. No saltes pasos, y para después de cada bloque para que yo revise.

**Bloque 0 — Fundación: completo (29/09/2026)**
1. Repositorio, venv, estructura de carpetas, `.gitignore`, `.env.example`, `pyproject.toml`
   con ruff y pytest configurados, primer commit.
2. `docker-compose.yml` con Postgres. Que arranque con un solo comando.
3. FastAPI mínimo con un `/salud` que responda, y Alembic inicializado.
4. Modelo de datos completo del MVP, en una sola migración inicial, con las tablas de los
   ocho módulos y la de auditoría. Revísalo conmigo antes de aplicarlo.
5. Seeds: usuarios de cada rol, catálogo de vehículos de ejemplo, zonas de cobertura,
   tarifas.

**Bloque 1 — Sprint 1 (HU-12, HU-02, HU-09, HU-01)**

6. Usuarios, JWT, RBAC con los cuatro roles, y las dependencias de FastAPI que protegen
   las rutas por rol. **Hecho (HU-12, PR #1).**
7. Catálogo con filtros, paginación y disponibilidad en tiempo real. **Hecho (HU-02, PR #2).**
8. Inactivación de unidades con motivo, y que desaparezcan del catálogo público al
   instante. **Hecho (HU-09, PR #3).**
9. Endpoints del portal institucional. **Hecho (HU-01, PR #4).**
10. Exportar el OpenAPI y avisarle al frontend que ya puede empezar. **Hecho (rama
    `paso-10-openapi`: guía en `docs/api/README.md` y CORS).**

De ahí en adelante seguimos el backlog sprint por sprint.

**Bloque 1 completo.** **Sprint 2 en curso** (una rama por historia saliendo de `main`):

11. HU-03 alquileres. **Hecho (PR #7).**
12. HU-04 compra. **Hecho (PR #8).**
13. HU-05 pagos. **Hecho (PR #9).** Falta probarlo contra el sandbox real cuando estén
    las llaves (ver "Cómo quedó HU-05").

**Sprint 2 completo.** **Sprint 3 en curso** (HU-06, HU-07, HU-08):

14. HU-06 domicilios. **Hecho (PR #10).**
15. HU-07 estado del domicilio y rastreo. **Hecho (PR #11).**
16. HU-08 rastreo GPS (simulador, consulta cada 5 s). **Hecho (PR #12).**

**Sprint 3 completo.** **Sprint 4 en curso**:

17. HU-10 inventario y alertas de bajo stock. **Hecho (PR #13).**
18. HU-11 actas de entrega y recepción, PDF y Excel. **Hecho (rama `hu-11-actas`, PR #14 en
    revisión).**
19. Requisitos no funcionales: script de respaldo y restauración (SRS 3.3.2) y límite
    del tamaño del cuerpo del webhook de pagos.

Espera mi confirmación antes de empezar cada historia.
