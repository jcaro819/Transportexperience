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
6. **HU-11 pide "firma digital de conformidad"** en el plan. Propuesta: registro de
   conformidad con usuario, fecha y hash del PDF. La tabla `actas` ya existe con esos
   campos (`conforme_por_id`, `conforme_en`, `hash_pdf`), pero **sigue pendiente de
   confirmar con el equipo**.
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
6. **Rastreo GPS por consulta cada 5 segundos** (HU-08), no WebSocket. *Pendiente de
   confirmar con Julián (frontend).*

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

### Decisiones pendientes para HU-03

1. **Máximo de días por alquiler.** Hay que definir cuántos días puede durar como máximo un
   alquiler. Va **configurable en base de datos** por el administrador, no como constante en
   el código (SRS 3.5.3).
2. **Vehículo que pasa a mantenimiento durante un alquiler en curso.** La devolución debe
   finalizar el alquiler **sin intentar pasar el vehículo a `disponible`**: se queda en
   `mantenimiento` hasta que el taller cierre su novedad.
3. **Alquileres afectados por una unidad que sale de servicio (propuesta, sin implementar):**
   - Reasignación **asistida por el administrador**: un endpoint para mover el alquiler a
     otra unidad libre del mismo modelo en esas fechas, con el mismo precio, bloqueando las
     dos unidades en la misma transacción.
   - Si no hay unidad libre, el administrador decide entre esperar a que la unidad vuelva o
     cancelar con devolución (pago de compensación, sección 7.3).
   - Consulta de **"alquileres en riesgo"**: alquileres futuros de unidades en
     mantenimiento, para que nadie los olvide.
   - La reasignación automática queda para después.

### Decisiones pendientes para HU-04 y HU-05

1. **Vehículo reservado para compra que pasa a mantenimiento y luego se aprueba el pago.**
   Opciones: devolver el dinero con un pago de compensación, o impedir la inactivación
   mientras haya una compra pendiente. **Se decide al llegar a HU-04.**

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
  No hace falta más, pero tiene que existir y estar documentado.
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
   las rutas por rol.
7. Catálogo con filtros, paginación y disponibilidad en tiempo real.
8. Inactivación de unidades con motivo, y que desaparezcan del catálogo público al
   instante.
9. Endpoints del portal institucional.
10. Exportar el OpenAPI y avisarle al frontend que ya puede empezar.

De ahí en adelante seguimos el backlog sprint por sprint.

**El siguiente es el Bloque 1, paso 6** (usuarios, JWT y RBAC), en la rama
`hu-12-usuarios` que sale de `main`. Cuando lo termines, muéstrame qué quedó y espera mi
confirmación antes de seguir al paso 7.
