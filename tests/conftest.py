"""Configuración común de los tests.

Las variables se fijan antes de importar la aplicación. Las variables de entorno tienen
prioridad sobre el archivo .env, así los tests usan SQLite en memoria aunque exista
un .env apuntando a Postgres.
"""

import os

os.environ["ENTORNO"] = "pruebas"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRETO"] = "secreto-solo-para-tests"
os.environ["PAGOS_PROVEEDOR"] = "falso"
os.environ["GPS_FUENTE"] = "simulador"
