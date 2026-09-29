"""Modelo inicial del MVP: las 20 tablas de los nueve módulos y la de auditoría.

Generada con --autogenerate y ajustada a mano:
- se agrega la extensión btree_gist (restricción de exclusión de alquileres);
- se quitan los CHECK duplicados que Alembic genera para las columnas de estado.

Revision ID: 05ddce1f9e8a
Revises:
Create Date: 2026-09-29 10:50:08.580235

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "05ddce1f9e8a"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea todas las tablas del MVP."""
    # btree_gist permite combinar "=" (vehiculo_id) y "&&" (rango de fechas) en la
    # restricción de exclusión de alquileres. Viene incluida en la imagen de Postgres.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "contenido_portal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("seccion", sa.String(length=30), nullable=False),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contenido_portal")),
        sa.UniqueConstraint("seccion", name=op.f("uq_contenido_portal_seccion")),
    )
    op.create_table(
        "horarios_atencion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dia_semana", sa.SmallInteger(), nullable=False),
        sa.Column("hora_apertura", sa.Time(), nullable=False),
        sa.Column("hora_cierre", sa.Time(), nullable=False),
        sa.CheckConstraint(
            "dia_semana BETWEEN 0 AND 6", name=op.f("ck_horarios_atencion_dia_semana_rango")
        ),
        sa.CheckConstraint(
            "hora_cierre > hora_apertura", name=op.f("ck_horarios_atencion_horas_ordenadas")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_horarios_atencion")),
        sa.UniqueConstraint("dia_semana", name=op.f("uq_horarios_atencion_dia_semana")),
    )
    op.create_table(
        "metodos_pago",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=60), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metodos_pago")),
        sa.UniqueConstraint("codigo", name=op.f("uq_metodos_pago_codigo")),
    )
    op.create_table(
        "productos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column(
            "categoria",
            sa.Enum(
                "accesorio",
                "repuesto",
                name="categoria_producto",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("imagen_url", sa.String(length=500), nullable=True),
        sa.Column("precio_venta", sa.BigInteger(), nullable=False),
        sa.Column("stock", sa.Integer(), server_default="0", nullable=False),
        sa.Column("stock_minimo", sa.Integer(), server_default="0", nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "categoria IN ('accesorio', 'repuesto')", name=op.f("ck_productos_categoria_producto")
        ),
        sa.CheckConstraint("precio_venta > 0", name=op.f("ck_productos_precio_venta_positivo")),
        sa.CheckConstraint("stock >= 0", name=op.f("ck_productos_stock_no_negativo")),
        sa.CheckConstraint("stock_minimo >= 0", name=op.f("ck_productos_stock_minimo_no_negativo")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_productos")),
        sa.UniqueConstraint("codigo", name=op.f("uq_productos_codigo")),
    )
    op.create_table(
        "tipos_vehiculo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=50), nullable=False),
        sa.Column("usa_bateria", sa.Boolean(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tipos_vehiculo")),
        sa.UniqueConstraint("nombre", name=op.f("uq_tipos_vehiculo_nombre")),
    )
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre_completo", sa.String(length=150), nullable=False),
        sa.Column("correo", sa.String(length=254), nullable=False),
        sa.Column("telefono", sa.String(length=20), nullable=True),
        sa.Column("hash_contrasena", sa.String(length=255), nullable=False),
        sa.Column(
            "rol",
            sa.Enum(
                "cliente",
                "administrador",
                "operador",
                "domiciliario",
                name="rol",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rol IN ('cliente', 'administrador', 'operador', 'domiciliario')",
            name=op.f("ck_usuarios_rol"),
        ),
        sa.CheckConstraint("correo = lower(correo)", name=op.f("ck_usuarios_correo_minusculas")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuarios")),
        sa.UniqueConstraint("correo", name=op.f("uq_usuarios_correo")),
    )
    op.create_index(op.f("ix_usuarios_rol"), "usuarios", ["rol"], unique=False)
    op.create_table(
        "zonas_cobertura",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=80), nullable=False),
        sa.Column("poligono", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tarifa_envio", sa.BigInteger(), nullable=False),
        sa.Column("activa", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tarifa_envio >= 0", name=op.f("ck_zonas_cobertura_tarifa_envio_no_negativa")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_zonas_cobertura")),
        sa.UniqueConstraint("nombre", name=op.f("uq_zonas_cobertura_nombre")),
    )
    op.create_table(
        "auditoria",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("accion", sa.String(length=30), nullable=False),
        sa.Column("entidad", sa.String(length=60), nullable=False),
        sa.Column("entidad_id", sa.String(length=40), nullable=False),
        sa.Column("datos_anteriores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("datos_nuevos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "ocurrido_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_auditoria_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auditoria")),
    )
    op.create_index("ix_auditoria_entidad", "auditoria", ["entidad", "entidad_id"], unique=False)
    op.create_index(op.f("ix_auditoria_ocurrido_en"), "auditoria", ["ocurrido_en"], unique=False)
    op.create_index(op.f("ix_auditoria_usuario_id"), "auditoria", ["usuario_id"], unique=False)
    op.create_table(
        "modelos_vehiculo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tipo_vehiculo_id", sa.Integer(), nullable=False),
        sa.Column("marca", sa.String(length=60), nullable=True),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("imagen_url", sa.String(length=500), nullable=True),
        sa.Column("tarifa_diaria", sa.BigInteger(), nullable=True),
        sa.Column("precio_venta", sa.BigInteger(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "precio_venta > 0", name=op.f("ck_modelos_vehiculo_precio_venta_positivo")
        ),
        sa.CheckConstraint(
            "tarifa_diaria > 0", name=op.f("ck_modelos_vehiculo_tarifa_diaria_positiva")
        ),
        sa.CheckConstraint(
            "tarifa_diaria IS NOT NULL OR precio_venta IS NOT NULL",
            name=op.f("ck_modelos_vehiculo_alquila_o_vende"),
        ),
        sa.ForeignKeyConstraint(
            ["tipo_vehiculo_id"],
            ["tipos_vehiculo.id"],
            name=op.f("fk_modelos_vehiculo_tipo_vehiculo_id_tipos_vehiculo"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_modelos_vehiculo")),
    )
    op.create_index(
        op.f("ix_modelos_vehiculo_tipo_vehiculo_id"),
        "modelos_vehiculo",
        ["tipo_vehiculo_id"],
        unique=False,
    )
    op.create_table(
        "ventas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente_pago",
                "pagada",
                "cancelada",
                "expirada",
                name="estado_venta",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("subtotal", sa.BigInteger(), nullable=False),
        sa.Column("valor_envio", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total", sa.BigInteger(), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(estado = 'pendiente_pago') = (expira_en IS NOT NULL)",
            name=op.f("ck_ventas_expiracion_solo_pendiente"),
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente_pago', 'pagada', 'cancelada', 'expirada')",
            name=op.f("ck_ventas_estado_venta"),
        ),
        sa.CheckConstraint("subtotal >= 0", name=op.f("ck_ventas_subtotal_no_negativo")),
        sa.CheckConstraint("total = subtotal + valor_envio", name=op.f("ck_ventas_total_cuadra")),
        sa.CheckConstraint("valor_envio >= 0", name=op.f("ck_ventas_valor_envio_no_negativo")),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["usuarios.id"], name=op.f("fk_ventas_cliente_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ventas")),
    )
    op.create_index(op.f("ix_ventas_cliente_id"), "ventas", ["cliente_id"], unique=False)
    op.create_index(op.f("ix_ventas_estado"), "ventas", ["estado"], unique=False)
    op.create_table(
        "vehiculos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("modelo_id", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "disponible",
                "reservado",
                "alquilado",
                "vendido",
                "mantenimiento",
                "asignado_a_domicilio",
                name="estado_vehiculo",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            server_default="disponible",
            nullable=False,
        ),
        sa.Column("nivel_bateria", sa.SmallInteger(), nullable=True),
        sa.Column("ubicacion", sa.String(length=150), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ('disponible', 'reservado', 'alquilado', 'vendido', 'mantenimiento', 'asignado_a_domicilio')",
            name=op.f("ck_vehiculos_estado_vehiculo"),
        ),
        sa.CheckConstraint(
            "nivel_bateria BETWEEN 0 AND 100", name=op.f("ck_vehiculos_nivel_bateria_rango")
        ),
        sa.ForeignKeyConstraint(
            ["modelo_id"],
            ["modelos_vehiculo.id"],
            name=op.f("fk_vehiculos_modelo_id_modelos_vehiculo"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehiculos")),
        sa.UniqueConstraint("codigo", name=op.f("uq_vehiculos_codigo")),
    )
    op.create_index(
        "ix_vehiculos_modelo_estado", "vehiculos", ["modelo_id", "estado"], unique=False
    )
    op.create_table(
        "alquileres",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("vehiculo_id", sa.Integer(), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=False),
        sa.Column("tarifa_diaria", sa.BigInteger(), nullable=False),
        sa.Column("subtotal", sa.BigInteger(), nullable=False),
        sa.Column("valor_envio", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total", sa.BigInteger(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente_pago",
                "confirmado",
                "en_curso",
                "finalizado",
                "cancelado",
                "expirado",
                name="estado_alquiler",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_cancelacion", sa.Text(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        postgresql.ExcludeConstraint(
            (sa.column("vehiculo_id"), "="),
            (sa.text("daterange(fecha_inicio, fecha_fin, '[]')"), "&&"),
            where=sa.text("estado IN ('pendiente_pago', 'confirmado', 'en_curso')"),
            using="gist",
            name="ex_alquileres_sin_solapamiento",
        ),
        sa.CheckConstraint(
            "(estado = 'pendiente_pago') = (expira_en IS NOT NULL)",
            name=op.f("ck_alquileres_expiracion_solo_pendiente"),
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente_pago', 'confirmado', 'en_curso', 'finalizado', 'cancelado', 'expirado')",
            name=op.f("ck_alquileres_estado_alquiler"),
        ),
        sa.CheckConstraint(
            "fecha_fin >= fecha_inicio", name=op.f("ck_alquileres_fechas_ordenadas")
        ),
        sa.CheckConstraint(
            "subtotal = (fecha_fin - fecha_inicio + 1) * tarifa_diaria",
            name=op.f("ck_alquileres_subtotal_cuadra"),
        ),
        sa.CheckConstraint("tarifa_diaria > 0", name=op.f("ck_alquileres_tarifa_diaria_positiva")),
        sa.CheckConstraint(
            "total = subtotal + valor_envio", name=op.f("ck_alquileres_total_cuadra")
        ),
        sa.CheckConstraint("valor_envio >= 0", name=op.f("ck_alquileres_valor_envio_no_negativo")),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["usuarios.id"], name=op.f("fk_alquileres_cliente_id_usuarios")
        ),
        sa.ForeignKeyConstraint(
            ["vehiculo_id"], ["vehiculos.id"], name=op.f("fk_alquileres_vehiculo_id_vehiculos")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alquileres")),
    )
    op.create_index(op.f("ix_alquileres_cliente_id"), "alquileres", ["cliente_id"], unique=False)
    op.create_index(op.f("ix_alquileres_estado"), "alquileres", ["estado"], unique=False)
    op.create_index(op.f("ix_alquileres_vehiculo_id"), "alquileres", ["vehiculo_id"], unique=False)
    op.create_table(
        "items_venta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("venta_id", sa.Integer(), nullable=False),
        sa.Column("vehiculo_id", sa.Integer(), nullable=True),
        sa.Column("producto_id", sa.Integer(), nullable=True),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", sa.BigInteger(), nullable=False),
        sa.Column("subtotal", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("cantidad > 0", name=op.f("ck_items_venta_cantidad_positiva")),
        sa.CheckConstraint(
            "num_nonnulls(vehiculo_id, producto_id) = 1",
            name=op.f("ck_items_venta_vehiculo_o_producto"),
        ),
        sa.CheckConstraint(
            "precio_unitario > 0", name=op.f("ck_items_venta_precio_unitario_positivo")
        ),
        sa.CheckConstraint(
            "subtotal = cantidad * precio_unitario", name=op.f("ck_items_venta_subtotal_cuadra")
        ),
        sa.CheckConstraint(
            "vehiculo_id IS NULL OR cantidad = 1", name=op.f("ck_items_venta_vehiculo_cantidad_uno")
        ),
        sa.ForeignKeyConstraint(
            ["producto_id"], ["productos.id"], name=op.f("fk_items_venta_producto_id_productos")
        ),
        sa.ForeignKeyConstraint(
            ["vehiculo_id"], ["vehiculos.id"], name=op.f("fk_items_venta_vehiculo_id_vehiculos")
        ),
        sa.ForeignKeyConstraint(
            ["venta_id"],
            ["ventas.id"],
            name=op.f("fk_items_venta_venta_id_ventas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_items_venta")),
    )
    op.create_index(
        op.f("ix_items_venta_producto_id"), "items_venta", ["producto_id"], unique=False
    )
    op.create_index(
        op.f("ix_items_venta_vehiculo_id"), "items_venta", ["vehiculo_id"], unique=False
    )
    op.create_index(op.f("ix_items_venta_venta_id"), "items_venta", ["venta_id"], unique=False)
    op.create_table(
        "novedades_vehiculo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vehiculo_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "dano",
                "falla",
                "perdida_accesorio",
                "bateria_baja",
                "incidente",
                "mantenimiento",
                name="tipo_novedad",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("es_critica", sa.Boolean(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "abierta",
                "cerrada",
                name="estado_novedad",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            server_default="abierta",
            nullable=False,
        ),
        sa.Column("reportada_por_id", sa.Integer(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("cerrada_por_id", sa.Integer(), nullable=True),
        sa.Column("cerrada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("solucion", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(estado = 'cerrada') = (cerrada_en IS NOT NULL AND cerrada_por_id IS NOT NULL)",
            name=op.f("ck_novedades_vehiculo_cierre_completo"),
        ),
        sa.CheckConstraint(
            "estado IN ('abierta', 'cerrada')", name=op.f("ck_novedades_vehiculo_estado_novedad")
        ),
        sa.CheckConstraint(
            "tipo IN ('dano', 'falla', 'perdida_accesorio', 'bateria_baja', 'incidente', 'mantenimiento')",
            name=op.f("ck_novedades_vehiculo_tipo_novedad"),
        ),
        sa.ForeignKeyConstraint(
            ["cerrada_por_id"],
            ["usuarios.id"],
            name=op.f("fk_novedades_vehiculo_cerrada_por_id_usuarios"),
        ),
        sa.ForeignKeyConstraint(
            ["reportada_por_id"],
            ["usuarios.id"],
            name=op.f("fk_novedades_vehiculo_reportada_por_id_usuarios"),
        ),
        sa.ForeignKeyConstraint(
            ["vehiculo_id"],
            ["vehiculos.id"],
            name=op.f("fk_novedades_vehiculo_vehiculo_id_vehiculos"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_novedades_vehiculo")),
    )
    op.create_index(
        "ix_novedades_vehiculo_vehiculo_estado",
        "novedades_vehiculo",
        ["vehiculo_id", "estado"],
        unique=False,
    )
    op.create_table(
        "posiciones_gps",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("vehiculo_id", sa.Integer(), nullable=False),
        sa.Column("latitud", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitud", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("precision_metros", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("velocidad_kmh", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("nivel_bateria", sa.SmallInteger(), nullable=True),
        sa.Column(
            "fuente",
            sa.Enum(
                "simulador",
                "dispositivo",
                name="fuente_gps",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("registrado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recibido_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "fuente IN ('simulador', 'dispositivo')", name=op.f("ck_posiciones_gps_fuente_gps")
        ),
        sa.CheckConstraint(
            "latitud BETWEEN -90 AND 90", name=op.f("ck_posiciones_gps_latitud_rango")
        ),
        sa.CheckConstraint(
            "longitud BETWEEN -180 AND 180", name=op.f("ck_posiciones_gps_longitud_rango")
        ),
        sa.CheckConstraint(
            "nivel_bateria BETWEEN 0 AND 100", name=op.f("ck_posiciones_gps_nivel_bateria_rango")
        ),
        sa.CheckConstraint(
            "precision_metros >= 0", name=op.f("ck_posiciones_gps_precision_no_negativa")
        ),
        sa.ForeignKeyConstraint(
            ["vehiculo_id"], ["vehiculos.id"], name=op.f("fk_posiciones_gps_vehiculo_id_vehiculos")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posiciones_gps")),
    )
    op.create_index(
        "ix_posiciones_gps_vehiculo_registrado",
        "posiciones_gps",
        ["vehiculo_id", sa.text("registrado_en DESC")],
        unique=False,
    )
    op.create_table(
        "domicilios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo_rastreo", sa.String(length=12), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("alquiler_id", sa.Integer(), nullable=True),
        sa.Column("venta_id", sa.Integer(), nullable=True),
        sa.Column("zona_id", sa.Integer(), nullable=False),
        sa.Column("direccion", sa.String(length=200), nullable=False),
        sa.Column("indicaciones", sa.String(length=200), nullable=True),
        sa.Column("latitud", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitud", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente",
                "asignado",
                "recogido",
                "en_camino",
                "entregado",
                "cancelado",
                name="estado_domicilio",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            server_default="pendiente",
            nullable=False,
        ),
        sa.Column("domiciliario_id", sa.Integer(), nullable=True),
        sa.Column("vehiculo_transporte_id", sa.Integer(), nullable=True),
        sa.Column("entregado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_cancelacion", sa.Text(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'asignado', 'recogido', 'en_camino', 'entregado', 'cancelado')",
            name=op.f("ck_domicilios_estado_domicilio"),
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'cancelado') OR domiciliario_id IS NOT NULL",
            name=op.f("ck_domicilios_asignado_tiene_domiciliario"),
        ),
        sa.CheckConstraint("latitud BETWEEN -90 AND 90", name=op.f("ck_domicilios_latitud_rango")),
        sa.CheckConstraint(
            "longitud BETWEEN -180 AND 180", name=op.f("ck_domicilios_longitud_rango")
        ),
        sa.CheckConstraint(
            "num_nonnulls(alquiler_id, venta_id) = 1",
            name=op.f("ck_domicilios_entrega_alquiler_o_venta"),
        ),
        sa.ForeignKeyConstraint(
            ["alquiler_id"], ["alquileres.id"], name=op.f("fk_domicilios_alquiler_id_alquileres")
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["usuarios.id"], name=op.f("fk_domicilios_cliente_id_usuarios")
        ),
        sa.ForeignKeyConstraint(
            ["domiciliario_id"],
            ["usuarios.id"],
            name=op.f("fk_domicilios_domiciliario_id_usuarios"),
        ),
        sa.ForeignKeyConstraint(
            ["vehiculo_transporte_id"],
            ["vehiculos.id"],
            name=op.f("fk_domicilios_vehiculo_transporte_id_vehiculos"),
        ),
        sa.ForeignKeyConstraint(
            ["venta_id"], ["ventas.id"], name=op.f("fk_domicilios_venta_id_ventas")
        ),
        sa.ForeignKeyConstraint(
            ["zona_id"], ["zonas_cobertura.id"], name=op.f("fk_domicilios_zona_id_zonas_cobertura")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_domicilios")),
        sa.UniqueConstraint("codigo_rastreo", name=op.f("uq_domicilios_codigo_rastreo")),
    )
    op.create_index(op.f("ix_domicilios_cliente_id"), "domicilios", ["cliente_id"], unique=False)
    op.create_index(
        op.f("ix_domicilios_domiciliario_id"), "domicilios", ["domiciliario_id"], unique=False
    )
    op.create_index(op.f("ix_domicilios_estado"), "domicilios", ["estado"], unique=False)
    op.create_index(
        "uq_domicilios_alquiler_activo",
        "domicilios",
        ["alquiler_id"],
        unique=True,
        postgresql_where="estado <> 'cancelado'",
    )
    op.create_index(
        "uq_domicilios_vehiculo_en_ruta",
        "domicilios",
        ["vehiculo_transporte_id"],
        unique=True,
        postgresql_where="estado IN ('asignado', 'recogido', 'en_camino')",
    )
    op.create_index(
        "uq_domicilios_venta_activo",
        "domicilios",
        ["venta_id"],
        unique=True,
        postgresql_where="estado <> 'cancelado'",
    )
    op.create_table(
        "pagos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referencia", sa.String(length=40), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "cobro",
                "compensacion",
                name="tipo_pago",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            server_default="cobro",
            nullable=False,
        ),
        sa.Column("alquiler_id", sa.Integer(), nullable=True),
        sa.Column("venta_id", sa.Integer(), nullable=True),
        sa.Column("metodo_pago_id", sa.Integer(), nullable=False),
        sa.Column("monto", sa.BigInteger(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente",
                "aprobado",
                "rechazado",
                "expirado",
                "error",
                name="estado_pago",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            server_default="pendiente",
            nullable=False,
        ),
        sa.Column("proveedor", sa.String(length=20), nullable=False),
        sa.Column("id_transaccion_pasarela", sa.String(length=64), nullable=True),
        sa.Column("pago_compensado_id", sa.Integer(), nullable=True),
        sa.Column("aprobado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detalle_error", sa.Text(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(estado = 'aprobado') = (aprobado_en IS NOT NULL)",
            name=op.f("ck_pagos_fecha_aprobacion"),
        ),
        sa.CheckConstraint(
            "(tipo = 'compensacion') = (pago_compensado_id IS NOT NULL)",
            name=op.f("ck_pagos_compensacion_referencia_pago"),
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'aprobado', 'rechazado', 'expirado', 'error')",
            name=op.f("ck_pagos_estado_pago"),
        ),
        sa.CheckConstraint("tipo IN ('cobro', 'compensacion')", name=op.f("ck_pagos_tipo_pago")),
        sa.CheckConstraint("monto > 0", name=op.f("ck_pagos_monto_positivo")),
        sa.CheckConstraint(
            "num_nonnulls(alquiler_id, venta_id) = 1", name=op.f("ck_pagos_una_sola_operacion")
        ),
        sa.ForeignKeyConstraint(
            ["alquiler_id"], ["alquileres.id"], name=op.f("fk_pagos_alquiler_id_alquileres")
        ),
        sa.ForeignKeyConstraint(
            ["metodo_pago_id"],
            ["metodos_pago.id"],
            name=op.f("fk_pagos_metodo_pago_id_metodos_pago"),
        ),
        sa.ForeignKeyConstraint(
            ["pago_compensado_id"], ["pagos.id"], name=op.f("fk_pagos_pago_compensado_id_pagos")
        ),
        sa.ForeignKeyConstraint(["venta_id"], ["ventas.id"], name=op.f("fk_pagos_venta_id_ventas")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pagos")),
        sa.UniqueConstraint(
            "id_transaccion_pasarela", name=op.f("uq_pagos_id_transaccion_pasarela")
        ),
        sa.UniqueConstraint("referencia", name=op.f("uq_pagos_referencia")),
    )
    op.create_index(op.f("ix_pagos_alquiler_id"), "pagos", ["alquiler_id"], unique=False)
    op.create_index(op.f("ix_pagos_estado"), "pagos", ["estado"], unique=False)
    op.create_index(op.f("ix_pagos_venta_id"), "pagos", ["venta_id"], unique=False)
    op.create_index(
        "uq_pagos_alquiler_cobro_aprobado",
        "pagos",
        ["alquiler_id"],
        unique=True,
        postgresql_where="estado = 'aprobado' AND tipo = 'cobro'",
    )
    op.create_index(
        "uq_pagos_venta_cobro_aprobado",
        "pagos",
        ["venta_id"],
        unique=True,
        postgresql_where="estado = 'aprobado' AND tipo = 'cobro'",
    )
    op.create_table(
        "actas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "entrega",
                "recepcion",
                name="tipo_acta",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("vehiculo_id", sa.Integer(), nullable=False),
        sa.Column("alquiler_id", sa.Integer(), nullable=True),
        sa.Column("venta_id", sa.Integer(), nullable=True),
        sa.Column("domicilio_id", sa.Integer(), nullable=True),
        sa.Column("estado_vehiculo", sa.Text(), nullable=False),
        sa.Column("nivel_bateria", sa.SmallInteger(), nullable=True),
        sa.Column("registrada_por_id", sa.Integer(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("conforme_por_id", sa.Integer(), nullable=True),
        sa.Column("conforme_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hash_pdf", sa.String(length=64), nullable=True),
        sa.CheckConstraint("tipo IN ('entrega', 'recepcion')", name=op.f("ck_actas_tipo_acta")),
        sa.CheckConstraint(
            "nivel_bateria BETWEEN 0 AND 100", name=op.f("ck_actas_nivel_bateria_rango")
        ),
        sa.CheckConstraint(
            "num_nonnulls(alquiler_id, venta_id) = 1",
            name=op.f("ck_actas_acta_de_alquiler_o_venta"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(conforme_por_id, conforme_en, hash_pdf) IN (0, 3)",
            name=op.f("ck_actas_conformidad_completa"),
        ),
        sa.ForeignKeyConstraint(
            ["alquiler_id"], ["alquileres.id"], name=op.f("fk_actas_alquiler_id_alquileres")
        ),
        sa.ForeignKeyConstraint(
            ["conforme_por_id"], ["usuarios.id"], name=op.f("fk_actas_conforme_por_id_usuarios")
        ),
        sa.ForeignKeyConstraint(
            ["domicilio_id"], ["domicilios.id"], name=op.f("fk_actas_domicilio_id_domicilios")
        ),
        sa.ForeignKeyConstraint(
            ["registrada_por_id"], ["usuarios.id"], name=op.f("fk_actas_registrada_por_id_usuarios")
        ),
        sa.ForeignKeyConstraint(
            ["vehiculo_id"], ["vehiculos.id"], name=op.f("fk_actas_vehiculo_id_vehiculos")
        ),
        sa.ForeignKeyConstraint(["venta_id"], ["ventas.id"], name=op.f("fk_actas_venta_id_ventas")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_actas")),
    )
    op.create_index(op.f("ix_actas_alquiler_id"), "actas", ["alquiler_id"], unique=False)
    op.create_index(op.f("ix_actas_vehiculo_id"), "actas", ["vehiculo_id"], unique=False)
    op.create_index(op.f("ix_actas_venta_id"), "actas", ["venta_id"], unique=False)
    op.create_table(
        "eventos_pago",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("proveedor", sa.String(length=20), nullable=False),
        sa.Column("clave_idempotencia", sa.String(length=120), nullable=True),
        sa.Column("pago_id", sa.Integer(), nullable=True),
        sa.Column("firma_valida", sa.Boolean(), nullable=False),
        sa.Column("estado_reportado", sa.String(length=30), nullable=True),
        sa.Column("cuerpo_crudo", sa.Text(), nullable=False),
        sa.Column("procesado", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "recibido_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pago_id"], ["pagos.id"], name=op.f("fk_eventos_pago_pago_id_pagos")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eventos_pago")),
        sa.UniqueConstraint("clave_idempotencia", name=op.f("uq_eventos_pago_clave_idempotencia")),
    )
    op.create_index(op.f("ix_eventos_pago_pago_id"), "eventos_pago", ["pago_id"], unique=False)
    op.create_table(
        "historial_estados_domicilio",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("domicilio_id", sa.Integer(), nullable=False),
        sa.Column(
            "estado_anterior",
            sa.Enum(
                "pendiente",
                "asignado",
                "recogido",
                "en_camino",
                "entregado",
                "cancelado",
                name="estado_anterior",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            nullable=True,
        ),
        sa.Column(
            "estado_nuevo",
            sa.Enum(
                "pendiente",
                "asignado",
                "recogido",
                "en_camino",
                "entregado",
                "cancelado",
                name="estado_nuevo",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("cambiado_por_id", sa.Integer(), nullable=True),
        sa.Column(
            "cambiado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado_anterior IN ('pendiente', 'asignado', 'recogido', 'en_camino', 'entregado', 'cancelado')",
            name=op.f("ck_historial_estados_domicilio_estado_anterior"),
        ),
        sa.CheckConstraint(
            "estado_nuevo IN ('pendiente', 'asignado', 'recogido', 'en_camino', 'entregado', 'cancelado')",
            name=op.f("ck_historial_estados_domicilio_estado_nuevo"),
        ),
        sa.ForeignKeyConstraint(
            ["cambiado_por_id"],
            ["usuarios.id"],
            name=op.f("fk_historial_estados_domicilio_cambiado_por_id_usuarios"),
        ),
        sa.ForeignKeyConstraint(
            ["domicilio_id"],
            ["domicilios.id"],
            name=op.f("fk_historial_estados_domicilio_domicilio_id_domicilios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_historial_estados_domicilio")),
    )
    op.create_index(
        op.f("ix_historial_estados_domicilio_domicilio_id"),
        "historial_estados_domicilio",
        ["domicilio_id"],
        unique=False,
    )


def downgrade() -> None:
    """Elimina todas las tablas del MVP."""
    op.drop_index(
        op.f("ix_historial_estados_domicilio_domicilio_id"),
        table_name="historial_estados_domicilio",
    )
    op.drop_table("historial_estados_domicilio")
    op.drop_index(op.f("ix_eventos_pago_pago_id"), table_name="eventos_pago")
    op.drop_table("eventos_pago")
    op.drop_index(op.f("ix_actas_venta_id"), table_name="actas")
    op.drop_index(op.f("ix_actas_vehiculo_id"), table_name="actas")
    op.drop_index(op.f("ix_actas_alquiler_id"), table_name="actas")
    op.drop_table("actas")
    op.drop_index(
        "uq_pagos_venta_cobro_aprobado",
        table_name="pagos",
        postgresql_where="estado = 'aprobado' AND tipo = 'cobro'",
    )
    op.drop_index(
        "uq_pagos_alquiler_cobro_aprobado",
        table_name="pagos",
        postgresql_where="estado = 'aprobado' AND tipo = 'cobro'",
    )
    op.drop_index(op.f("ix_pagos_venta_id"), table_name="pagos")
    op.drop_index(op.f("ix_pagos_estado"), table_name="pagos")
    op.drop_index(op.f("ix_pagos_alquiler_id"), table_name="pagos")
    op.drop_table("pagos")
    op.drop_index(
        "uq_domicilios_venta_activo",
        table_name="domicilios",
        postgresql_where="estado <> 'cancelado'",
    )
    op.drop_index(
        "uq_domicilios_vehiculo_en_ruta",
        table_name="domicilios",
        postgresql_where="estado IN ('asignado', 'recogido', 'en_camino')",
    )
    op.drop_index(
        "uq_domicilios_alquiler_activo",
        table_name="domicilios",
        postgresql_where="estado <> 'cancelado'",
    )
    op.drop_index(op.f("ix_domicilios_estado"), table_name="domicilios")
    op.drop_index(op.f("ix_domicilios_domiciliario_id"), table_name="domicilios")
    op.drop_index(op.f("ix_domicilios_cliente_id"), table_name="domicilios")
    op.drop_table("domicilios")
    op.drop_index(
        "ix_posiciones_gps_vehiculo_registrado",
        table_name="posiciones_gps",
    )
    op.drop_table("posiciones_gps")
    op.drop_index("ix_novedades_vehiculo_vehiculo_estado", table_name="novedades_vehiculo")
    op.drop_table("novedades_vehiculo")
    op.drop_index(op.f("ix_items_venta_venta_id"), table_name="items_venta")
    op.drop_index(op.f("ix_items_venta_vehiculo_id"), table_name="items_venta")
    op.drop_index(op.f("ix_items_venta_producto_id"), table_name="items_venta")
    op.drop_table("items_venta")
    op.drop_index(op.f("ix_alquileres_vehiculo_id"), table_name="alquileres")
    op.drop_index(op.f("ix_alquileres_estado"), table_name="alquileres")
    op.drop_index(op.f("ix_alquileres_cliente_id"), table_name="alquileres")
    op.drop_table("alquileres")
    op.drop_index("ix_vehiculos_modelo_estado", table_name="vehiculos")
    op.drop_table("vehiculos")
    op.drop_index(op.f("ix_ventas_estado"), table_name="ventas")
    op.drop_index(op.f("ix_ventas_cliente_id"), table_name="ventas")
    op.drop_table("ventas")
    op.drop_index(op.f("ix_modelos_vehiculo_tipo_vehiculo_id"), table_name="modelos_vehiculo")
    op.drop_table("modelos_vehiculo")
    op.drop_index(op.f("ix_auditoria_usuario_id"), table_name="auditoria")
    op.drop_index(op.f("ix_auditoria_ocurrido_en"), table_name="auditoria")
    op.drop_index("ix_auditoria_entidad", table_name="auditoria")
    op.drop_table("auditoria")
    op.drop_table("zonas_cobertura")
    op.drop_index(op.f("ix_usuarios_rol"), table_name="usuarios")
    op.drop_table("usuarios")
    op.drop_table("tipos_vehiculo")
    op.drop_table("productos")
    op.drop_table("metodos_pago")
    op.drop_table("horarios_atencion")
    op.drop_table("contenido_portal")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
