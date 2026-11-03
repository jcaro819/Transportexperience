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

## Respaldo y restauración (SRS 3.3.2)

El script `scripts/respaldo_bd.py` usa `pg_dump` y `pg_restore` **dentro del contenedor**
de Postgres: no hay que instalar nada más. Necesita `docker compose up -d`.

### Respaldar

```bash
python -m scripts.respaldo_bd respaldar                  # crea backups/<base>-<fecha>.dump
python -m scripts.respaldo_bd respaldar --conservar 10   # y deja solo los 10 más recientes
```

- Respalda la base de `DATABASE_URL` (la del `.env`) en el formato propio de Postgres
  (`-Fc`): comprimido y restaurable completo o por partes.
- Queda en `backups/`, que **no se sube a git**: los respaldos tienen datos personales.
- El archivo se escribe primero como `.parcial` y se renombra al terminar: nunca queda un
  respaldo a medias con apariencia de completo.
- Para respaldar a diario en Windows: Programador de tareas → "Crear tarea básica" →
  acción "Iniciar un programa": `.venv\Scripts\python.exe` con argumentos
  `-m scripts.respaldo_bd respaldar --conservar 14`, y como carpeta de inicio la del
  proyecto.

### Restaurar

**Primero, probar el respaldo sin tocar nada**, restaurándolo en otra base:

```bash
python -m scripts.respaldo_bd restaurar backups/transportexperience-2026-11-02_070509.dump --base transportexperience_prueba
```

Si la base no existe, se crea. Revísala en Adminer (http://localhost:8080) y bórrala al
terminar (`DROP DATABASE transportexperience_prueba;`).

**Para recuperar la base de trabajo** (reemplaza **todos** sus datos por los del respaldo):

1. Detén la API (Ctrl+C en la terminal de `uvicorn`), para que nadie escriba mientras tanto.
2. Restaura sobre la base del `.env`; sin `--confirmar`, el script se niega:

   ```bash
   python -m scripts.respaldo_bd restaurar backups/ARCHIVO.dump --confirmar
   ```

3. Corre `alembic upgrade head`: si el respaldo es de una versión anterior del código, lo
   pone al día.
4. Arranca la API de nuevo.

La restauración se detiene ante el primer error (`--exit-on-error`) y lo muestra.

## Comandos habituales

```bash
pytest                 # correr los tests (necesita docker compose up: usan Postgres)
ruff check .           # revisar estilo y errores
ruff format .          # formatear el código
alembic revision --autogenerate -m "descripcion"   # nueva migración
alembic upgrade head   # aplicar migraciones pendientes
python -m scripts.generar_diagrama_er   # regenerar docs/uml/modelo-datos.md
python -m scripts.respaldo_bd respaldar   # respaldo de la base (ver arriba)
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
