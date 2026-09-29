# API de TransportExperience: guía para el frontend

Todo lo necesario para consumir el backend del **Sprint 1** (HU-12, HU-02, HU-09, HU-01).
El contrato completo y exacto (esquemas, campos, ejemplos) está en
[`openapi.json`](openapi.json), que se genera desde el código. La forma más cómoda de
explorarlo es la documentación interactiva: **http://127.0.0.1:8000/docs**.

> Si algo de esta guía no coincide con lo que responde la API, manda la API: avísale a Juan
> Felipe para corregir la guía.

---

## 1. Levantar el backend

Requisitos: Python 3.11+, Docker Desktop y Git.

```powershell
git clone https://github.com/jcaro819/Transportexperience.git
cd Transportexperience
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

Abre `.env` y cambia `JWT_SECRETO` por uno generado con
`python -c "import secrets; print(secrets.token_urlsafe(48))"` (la API no arranca con el
valor de ejemplo). Luego:

```powershell
docker compose up -d --wait      # base de datos
alembic upgrade head             # crea las tablas
python -m seeds.cargar           # datos de ejemplo y usuarios de prueba
uvicorn app.main:app --reload    # API en http://127.0.0.1:8000
```

Si todo va bien, `http://127.0.0.1:8000/salud` responde
`{"estado": "ok", "base_datos": "ok"}`.

**CORS.** La API acepta peticiones del navegador desde `localhost:5173` (Vite),
`localhost:3000` (React/Next) y `localhost:4200` (Angular). Si tu frontend usa otro puerto,
agrégalo a `CORS_ORIGENES` en el `.env` (separado por comas) y reinicia la API.

---

## 2. Usuarios de prueba

Todos con la contraseña **`Desarrollo2026!`**. Solo existen en bases de desarrollo.

| Rol | Correo |
|---|---|
| Administrador | `admin@transportexperience.test` |
| Operador | `operador@transportexperience.test` |
| Cliente | `cliente@transportexperience.test` |
| Domiciliario | `domiciliario@transportexperience.test` |

---

## 3. Iniciar sesión y enviar el token

El inicio de sesión sigue el estándar OAuth2: recibe un **formulario, no JSON**, con el
correo en el campo `username`.

```js
const respuesta = await fetch("http://127.0.0.1:8000/autenticacion/token", {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ username: correo, password: contrasena }),
});
const { access_token, expira_en_segundos, usuario } = await respuesta.json();
```

La respuesta trae también `usuario` (con su `rol`), para armar el menú sin otra petición.
En cada petición protegida, envía el token en el encabezado:

```js
fetch(url, { headers: { Authorization: `Bearer ${access_token}` } });
```

- El token dura **60 minutos** (`expira_en_segundos`). No hay renovación automática: al
  vencer, la API responde `401` con código `sesion_expirada` y hay que iniciar sesión de nuevo.
- Si un administrador desactiva una cuenta o le cambia el rol, aplica **de inmediato**,
  aunque el token siga vigente.
- `GET /usuarios/yo` devuelve el usuario del token: sirve al recargar la página.

---

## 4. Errores: siempre la misma forma

Toda respuesta de error, sin excepción, tiene esta estructura:

```json
{
  "error": {
    "codigo": "correo_ya_registrado",
    "mensaje": "Ya existe una cuenta con ese correo.",
    "accion": "Inicia sesión o usa otro correo.",
    "detalles": null
  }
}
```

- **Decide por `codigo`**, que es estable. `mensaje` y `accion` ya están en español y
  pensados para el usuario final: muéstralos tal cual (el SRS 3.2.3 pide decir la causa y
  qué hacer).
- En los errores de validación (`datos_invalidos`), `detalles` indica cada campo con
  problema: `[{"campo": "correo", "mensaje": "..."}]`. Úsalo para marcar el formulario.

| Código | HTTP | Cuándo |
|---|---|---|
| `datos_invalidos` | 422 | Un campo falta o no es válido (ver `detalles`) |
| `cuerpo_invalido` | 400 | El cuerpo no es JSON válido o no está en UTF-8 |
| `no_autenticado` | 401 | Falta el token o no es válido |
| `sesion_expirada` | 401 | El token venció: hay que iniciar sesión de nuevo |
| `credenciales_invalidas` | 401 | Correo o contraseña incorrectos |
| `cuenta_inactiva` | 403 | La cuenta fue desactivada |
| `permiso_denegado` | 403 | El rol no puede hacer eso |
| `recurso_no_encontrado` | 404 | La dirección no existe |
| `usuario_no_encontrado` | 404 | El usuario no existe |
| `modelo_no_encontrado` | 404 | El modelo no existe o salió del catálogo |
| `vehiculo_no_encontrado` | 404 | La unidad no existe |
| `novedad_no_encontrada` | 404 | La novedad no existe o es de otra unidad |
| `metodo_no_permitido` | 405 | La dirección no admite ese método |
| `correo_ya_registrado` | 409 | Ya hay una cuenta con ese correo |
| `cambio_sobre_si_mismo` | 409 | Un administrador intenta desactivarse o quitarse el rol |
| `modelo_no_se_alquila` | 409 | El modelo solo está a la venta |
| `vehiculo_vendido` | 409 | La unidad ya fue vendida |
| `transicion_invalida` | 409 | La unidad no puede pasar a ese estado |
| `no_puede_volver_a_servicio` | 409 | La unidad aún no puede volver (el `mensaje` dice por qué) |
| `novedad_ya_cerrada` | 409 | La novedad ya estaba cerrada |
| `rango_de_tarifa_invalido` | 422 | `tarifa_min` es mayor que `tarifa_max` |
| `fechas_invalidas` | 422 | Fecha de inicio en el pasado o fin antes del inicio |
| `error_interno` | 500 | Falla inesperada; no se hizo ningún cambio |

---

## 5. Paginación

Todas las listas vienen paginadas. Parámetros de consulta: `pagina` (desde 1) y `tamano`
(por defecto 20, máximo 100). La respuesta siempre tiene esta forma:

```json
{ "elementos": [ ... ], "total": 57, "pagina": 2, "tamano": 20, "paginas": 3 }
```

`total` es la cantidad sin paginar y `paginas` el número de páginas. Las únicas listas sin
paginar son las pequeñas y acotadas dentro de otra respuesta (por ejemplo, las unidades
dentro de la ficha de un modelo o los 7 días de horario del portal).

---

## 6. Fechas, horas y dinero

- **Fechas** (`fecha_inicio`, `fecha_fin`): formato `AAAA-MM-DD`, p. ej. `2026-10-05`.
- **Los rangos de alquiler son inclusivos**: del 5 al 7 son **3 días**, y el siguiente
  cliente puede recoger desde el día 8.
- **"Hoy" es la fecha de Colombia**, no la del navegador ni la del servidor.
- **Fecha y hora** (`creado_en`, `cerrada_en`...): ISO 8601 con zona, **siempre en hora de
  Colombia**, p. ej. `2026-09-29T12:58:13-05:00`. `new Date(...)` las lee sin problema.
- **Horas** del portal: `HH:MM:SS`, p. ej. `07:00:00`.
- **Dinero**: **pesos colombianos enteros**, sin decimales ni centavos
  (`"tarifa_diaria": 60000` son $60.000). Para mostrarlo:
  `valor.toLocaleString("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 })`.
- **Batería**: `nivel_bateria` es un porcentaje de 0 a 100, o `null` si el vehículo no usa
  batería (ciclas, patines).

---

## 7. Endpoints del Sprint 1

"Público" = sin iniciar sesión. En `/docs`, cada ruta muestra sus parámetros, el cuerpo que
espera y ejemplos de respuesta.

### Autenticación y usuarios (HU-12)

| Método | Ruta | Quién | Para qué |
|---|---|---|---|
| `POST` | `/autenticacion/token` | Público | Iniciar sesión (formulario `username` + `password`) |
| `POST` | `/usuarios/registro` | Público | Registrarse; la cuenta queda como cliente |
| `GET` | `/usuarios/yo` | Cualquier usuario con sesión | Datos y rol del usuario actual |
| `GET` | `/usuarios` | Administrador | Lista de usuarios; filtros `rol`, `activo`, `busqueda` |
| `POST` | `/usuarios` | Administrador | Crear usuario con cualquier rol |
| `GET` | `/usuarios/{usuario_id}` | Administrador | Ver un usuario |
| `PATCH` | `/usuarios/{usuario_id}` | Administrador | Cambiar datos, rol o activar/desactivar (`{"activo": false}`) |

### Catálogo público (HU-02)

| Método | Ruta | Quién | Para qué |
|---|---|---|---|
| `GET` | `/catalogo/tipos` | Público | Tipos de vehículo, para el filtro |
| `GET` | `/catalogo/modelos` | Público | Catálogo con `disponibles_hoy`; filtros `tipo_id`, `tarifa_min`, `tarifa_max`, `modalidad` (`alquiler`/`venta`), `solo_disponibles` |
| `GET` | `/catalogo/modelos/{modelo_id}` | Público | Ficha del modelo con cada unidad libre hoy (código, ubicación, batería) |
| `GET` | `/catalogo/modelos/{modelo_id}/disponibilidad` | Público | Unidades libres entre `fecha_inicio` y `fecha_fin` |

### Gestión de la flota (HU-09)

| Método | Ruta | Quién | Para qué |
|---|---|---|---|
| `GET` | `/vehiculos` | Administrador, operador | Toda la flota con su estado real; filtros `estado`, `modelo_id`, `codigo` |
| `GET` | `/vehiculos/{vehiculo_id}/novedades` | Administrador, operador | Historial de novedades de una unidad; filtro `estado` |
| `POST` | `/vehiculos/{vehiculo_id}/inactivacion` | Administrador, operador | Pasar la unidad a mantenimiento con un `motivo` |
| `POST` | `/vehiculos/{vehiculo_id}/novedades` | Administrador, operador, domiciliario | Reportar daño, falla, batería baja...; si `es_critica`, la unidad sale de servicio |
| `POST` | `/vehiculos/{vehiculo_id}/novedades/{novedad_id}/cierre` | Administrador, operador | Cerrar la novedad con su `solucion`; con `devolver_a_servicio: true`, la unidad vuelve a estar disponible |

Al inactivar o reportar una novedad crítica, la respuesta trae `alquileres_afectados`: los
alquileres vigentes de esa unidad, que **no se cancelan solos**. Conviene mostrarlos al
operador.

### Portal institucional (HU-01)

| Método | Ruta | Quién | Para qué |
|---|---|---|---|
| `GET` | `/portal` | Público | Misión, visión, contacto y los 7 días de horario, en una sola petición |
| `PUT` | `/portal/secciones/{seccion}` | Administrador | Editar `mision`, `vision` o `contacto` |
| `PUT` | `/portal/horarios/{dia}` | Administrador | Abrir un día o cambiar su horario (`lunes` ... `domingo`) |
| `DELETE` | `/portal/horarios/{dia}` | Administrador | Cerrar un día |

### Sistema

| Método | Ruta | Quién | Para qué |
|---|---|---|---|
| `GET` | `/salud` | Público | Saber si la API y la base de datos responden |

---

## 8. Preguntas abiertas para el frontend

1. **Rastreo GPS (HU-08, Sprint 3): ¿consulta cada 5 segundos o WebSocket?** La propuesta
   del backend es que el mapa **consulte la API cada 5 segundos** (más simple de construir y
   de probar). Necesitamos tu confirmación antes de empezar ese módulo.
2. **Puerto del frontend**: si no es 5173, 3000 ni 4200, dinos cuál para dejarlo en
   `.env.example`.
