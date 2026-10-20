# TransportExperience — Frontend v1 (prototipo visual)

Primera versión estática del frontend para el Sprint 1. No consume todavía el backend; usa datos simulados y sirve para validar estructura, navegación, estilo y pantallas.

## Incluye

- Portal institucional: inicio, servicios, misión, visión y contacto (HU-01).
- Catálogo con filtros visuales y ficha de vehículo (HU-02).
- Pantalla de inicio de sesión de demostración y acceso simulado al panel (HU-12).
- Panel administrativo con usuarios/roles y gestión visual de flota/mantenimiento (HU-12 y HU-09).
- Diseño responsive para escritorio y móvil.

## Cómo ejecutarlo

No requiere instalar dependencias.

### Opción rápida

Abre `index.html` en el navegador.

### Opción recomendada (puerto compatible con el backend)

Desde esta carpeta:

```bash
python -m http.server 5173
```

Luego abre:

```text
http://localhost:5173
```

El backend actual ya contempla `localhost:5173` como origen CORS, por lo que este mismo prototipo puede evolucionar después a una versión conectada.

## Navegación demo

- `Inicio`: portal público institucional.
- `Catálogo`: lista y filtros con datos mock.
- `Iniciar sesión`: formulario visual; cualquier envío lleva al panel demo.
- `Panel administrativo`: pestañas de resumen, usuarios, flota y mantenimiento.

## Siguiente paso para volverlo funcional

1. Reemplazar los datos mock de `app.js` por `fetch()` contra la API.
2. Conectar `/portal` y `/catalogo/modelos` primero.
3. Implementar `/autenticacion/token` y guardar temporalmente el JWT.
4. Mostrar/ocultar módulos según el rol devuelto por la API.
5. Conectar usuarios y acciones de inactivación/mantenimiento.

## Nota

Los textos, precios, ubicaciones y métricas del prototipo son datos de demostración. No representan datos reales de producción.
