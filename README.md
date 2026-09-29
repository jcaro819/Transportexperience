# TransportExperience — Backend

Plataforma para alquilar, vender y entregar a domicilio ciclas, patines y monopatines
eléctricos. Proyecto académico del equipo **SystemSolutions** (Scrum, 4 sprints de 2 semanas).

- Requisitos: [`docs/SRS.pdf`](docs/SRS.pdf)
- Plan y backlog: [`docs/plan-desarrollo.pdf`](docs/plan-desarrollo.pdf)
- Guía de la API para el frontend: [`docs/api/README.md`](docs/api/README.md)
- Guía de trabajo del equipo y de Claude Code: [`CLAUDE.md`](CLAUDE.md)

## Requisitos previos

- Python 3.11 o superior
- Docker Desktop (para PostgreSQL)
- Git

## Puesta en marcha

```bash
# 1. Clonar
git clone https://github.com/jcaro819/Transportexperience.git
cd Transportexperience

# 2. Crear y activar el entorno virtual (nunca instalar global)
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows (PowerShell)

# 3. Instalar dependencias del proyecto y de desarrollo
pip install -e ".[dev]"

# 4. Variables de entorno
cp .env.example .env             # Windows: copy .env.example .env

# 5. Levantar PostgreSQL y Adminer (http://localhost:8080)
docker compose up -d --wait

# 6. Aplicar migraciones y arrancar la API
alembic upgrade head
uvicorn app.main:app --reload    # docs en http://127.0.0.1:8000/docs
```

## Datos de ejemplo (seeds)

```bash
python -m seeds.cargar     # solo con ENTORNO=desarrollo; se puede correr varias veces
```

Carga usuarios, catálogo (6 modelos, 15 unidades en estados variados), accesorios y
repuestos (3 en bajo stock), 3 zonas de cobertura aproximadas de Bucaramanga, métodos de
pago, contenido del portal (**provisional**) y horarios de atención.

Usuarios de desarrollo. **Todos tienen la contraseña `Desarrollo2026!`**. Solo existen
en bases de desarrollo: el script se niega a correr si `ENTORNO` no es `desarrollo`.

| Rol | Correo |
|---|---|
| Administrador | `admin@transportexperience.test` |
| Operador | `operador@transportexperience.test` |
| Cliente | `cliente@transportexperience.test` |
| Domiciliario | `domiciliario@transportexperience.test` |

## Comandos habituales

```bash
pytest                 # correr los tests (necesita docker compose up: usan Postgres)
ruff check .           # revisar estilo y errores
ruff format .          # formatear el código
alembic revision --autogenerate -m "descripcion"   # nueva migración
alembic upgrade head   # aplicar migraciones pendientes
python -m scripts.generar_diagrama_er   # regenerar docs/uml/modelo-datos.md
docker compose down    # apagar la base (conserva los datos)
```

## Estructura

```
app/
├── comun/          utilidades compartidas (errores, paginación, dinero)
└── modulos/
    ├── usuarios/   HU-12
    ├── inventario/ HU-02, HU-09, HU-10
    ├── alquileres/ HU-03
    ├── ventas/     HU-04
    ├── pagos/      HU-05
    ├── domicilios/ HU-06, HU-07
    ├── rastreo/    HU-08
    └── reportes/   HU-11
simulador_gps/      posiciones simuladas para desarrollar HU-08 sin hardware
seeds/              datos de ejemplo
docs/uml/           diagramas (PlantUML / Mermaid)
docs/api/           OpenAPI exportado para el frontend
tests/
```

Cada módulo tendrá `modelos.py`, `esquemas.py`, `servicio.py`, `rutas.py` y
`excepciones.py`. Las reglas de negocio viven en `servicio.py`.

## Convenciones

- Commits en español referenciando la historia: `HU-03: bloqueo de vehículo al crear reserva`.
- Una rama por historia: `hu-03-alquileres`.
- El dinero se guarda como entero en pesos. Nunca `float`.
- `.env` nunca se sube al repositorio.
