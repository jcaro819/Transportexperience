"""Datos de ejemplo para desarrollo. Solo declaraciones; la carga está en ``cargar.py``.

Todo el dinero está en pesos enteros. Los textos marcados como PROVISIONAL deben
reemplazarse por los oficiales del equipo antes de la sustentación.
"""

from datetime import time

from app.modulos.inventario.modelos import CategoriaProducto, EstadoVehiculo, TipoNovedad
from app.modulos.usuarios.modelos import Rol

# Contraseña de TODOS los usuarios de desarrollo. Documentada en el README.
# Solo existe en bases de desarrollo: el script se niega a correr en otro entorno.
CONTRASENA_DESARROLLO = "Desarrollo2026!"

USUARIOS = [
    {
        "correo": "admin@transportexperience.test",
        "nombre_completo": "Ana Administradora",
        "telefono": "3000000001",
        "rol": Rol.ADMINISTRADOR,
    },
    {
        "correo": "operador@transportexperience.test",
        "nombre_completo": "Óscar Operador",
        "telefono": "3000000002",
        "rol": Rol.OPERADOR,
    },
    {
        "correo": "cliente@transportexperience.test",
        "nombre_completo": "Carla Cliente",
        "telefono": "3000000003",
        "rol": Rol.CLIENTE,
    },
    {
        "correo": "domiciliario@transportexperience.test",
        "nombre_completo": "Diego Domiciliario",
        "telefono": "3000000004",
        "rol": Rol.DOMICILIARIO,
    },
]

TIPOS_VEHICULO = [
    {"nombre": "Cicla", "usa_bateria": False},
    {"nombre": "Patín", "usa_bateria": False},
    {"nombre": "Monopatín eléctrico", "usa_bateria": True},
]

# tarifa_diaria=None: no se alquila. precio_venta=None: no se vende.
MODELOS_VEHICULO = [
    {
        "tipo": "Cicla",
        "nombre": "Cicla urbana 7 cambios",
        "tarifa_diaria": 25_000,
        "precio_venta": 950_000,
        "descripcion": "Cicla de ciudad con canasta y guardabarros. Ideal para trayectos cortos.",
    },
    {
        "tipo": "Cicla",
        "nombre": "Cicla de montaña 21 cambios",
        "tarifa_diaria": 35_000,
        "precio_venta": None,
        "descripcion": "Suspensión delantera y frenos de disco. Solo alquiler.",
    },
    {
        "tipo": "Patín",
        "nombre": "Patín clásico plegable",
        "tarifa_diaria": 15_000,
        "precio_venta": 280_000,
        "descripcion": "Patín de impulso, liviano y plegable.",
    },
    {
        "tipo": "Monopatín eléctrico",
        "nombre": "Monopatín urbano 350 W",
        "tarifa_diaria": 60_000,
        "precio_venta": 2_400_000,
        "descripcion": "Autonomía aproximada de 25 km. Velocidad máxima 25 km/h.",
    },
    {
        "tipo": "Monopatín eléctrico",
        "nombre": "Monopatín pro 500 W",
        "tarifa_diaria": 85_000,
        "precio_venta": None,
        "descripcion": "Autonomía aproximada de 45 km, para las lomas de la ciudad. Solo alquiler.",
    },
    {
        "tipo": "Monopatín eléctrico",
        "nombre": "Monopatín compacto 250 W",
        "tarifa_diaria": None,
        "precio_venta": 1_800_000,
        "descripcion": "Liviano, cabe en el baúl de un carro. Solo venta.",
    },
]

# 15 unidades. Los estados distintos de "disponible" van respaldados por su operación
# (alquiler en curso, venta pagada o novedad abierta), para no violar las reglas de 7.2.
VEHICULOS = [
    {"codigo": "CIC-0001", "modelo": "Cicla urbana 7 cambios", "ubicacion": "Sede Centro"},
    {"codigo": "CIC-0002", "modelo": "Cicla urbana 7 cambios", "ubicacion": "Sede Cabecera"},
    {"codigo": "CIC-0003", "modelo": "Cicla de montaña 21 cambios", "ubicacion": "Sede Centro"},
    {
        "codigo": "CIC-0004",
        "modelo": "Cicla urbana 7 cambios",
        "ubicacion": "Sede Centro",
        "estado": EstadoVehiculo.VENDIDO,
    },
    {"codigo": "PAT-0001", "modelo": "Patín clásico plegable", "ubicacion": "Sede Centro"},
    {"codigo": "PAT-0002", "modelo": "Patín clásico plegable", "ubicacion": "Sede Cabecera"},
    {
        "codigo": "PAT-0003",
        "modelo": "Patín clásico plegable",
        "ubicacion": "Sede Cabecera",
        "estado": EstadoVehiculo.MANTENIMIENTO,
    },
    {
        "codigo": "MON-0001",
        "modelo": "Monopatín urbano 350 W",
        "ubicacion": "Sede Centro",
        "nivel_bateria": 95,
    },
    {
        "codigo": "MON-0002",
        "modelo": "Monopatín urbano 350 W",
        "ubicacion": "Sede Cabecera",
        "nivel_bateria": 80,
    },
    {
        "codigo": "MON-0003",
        "modelo": "Monopatín urbano 350 W",
        "ubicacion": "Sede Centro",
        "nivel_bateria": 64,
        "estado": EstadoVehiculo.ALQUILADO,
    },
    {
        "codigo": "MON-0004",
        "modelo": "Monopatín pro 500 W",
        "ubicacion": "Sede Cabecera",
        "nivel_bateria": 100,
    },
    {
        "codigo": "MON-0005",
        "modelo": "Monopatín pro 500 W",
        "ubicacion": "Sede Centro",
        "nivel_bateria": 8,
        "estado": EstadoVehiculo.MANTENIMIENTO,
    },
    {
        "codigo": "MON-0006",
        "modelo": "Monopatín pro 500 W",
        "ubicacion": "Sede Centro",
        "nivel_bateria": 72,
    },
    {
        "codigo": "MON-0007",
        "modelo": "Monopatín compacto 250 W",
        "ubicacion": "Sede Cabecera",
        "nivel_bateria": 100,
    },
    {
        "codigo": "MON-0008",
        "modelo": "Monopatín compacto 250 W",
        "ubicacion": "Sede Cabecera",
        "nivel_bateria": 100,
    },
]

# Novedades abiertas que justifican los vehículos en mantenimiento.
NOVEDADES = [
    {
        "vehiculo": "PAT-0003",
        "tipo": TipoNovedad.MANTENIMIENTO,
        "es_critica": True,
        "descripcion": "Inactivado para cambio de rodamientos (HU-09).",
    },
    {
        "vehiculo": "MON-0005",
        "tipo": TipoNovedad.BATERIA_BAJA,
        "es_critica": True,
        "descripcion": "Batería al 8 %: no retiene carga. Revisar celdas.",
    },
]

# stock <= stock_minimo dispara la alerta de bajo stock (HU-10).
PRODUCTOS = [
    {
        "codigo": "ACC-CASCO-U",
        "nombre": "Casco urbano talla M",
        "categoria": CategoriaProducto.ACCESORIO,
        "precio_venta": 120_000,
        "stock": 12,
        "stock_minimo": 5,
    },
    {
        "codigo": "ACC-CASCO-N",
        "nombre": "Casco infantil",
        "categoria": CategoriaProducto.ACCESORIO,
        "precio_venta": 85_000,
        "stock": 3,
        "stock_minimo": 5,
    },  # bajo stock
    {
        "codigo": "ACC-CANDADO",
        "nombre": "Candado en U",
        "categoria": CategoriaProducto.ACCESORIO,
        "precio_venta": 65_000,
        "stock": 10,
        "stock_minimo": 4,
    },
    {
        "codigo": "ACC-LUCES",
        "nombre": "Kit de luces LED recargables",
        "categoria": CategoriaProducto.ACCESORIO,
        "precio_venta": 45_000,
        "stock": 1,
        "stock_minimo": 3,
    },  # bajo stock
    {
        "codigo": "ACC-CARGADOR",
        "nombre": "Cargador para monopatín 42 V",
        "categoria": CategoriaProducto.ACCESORIO,
        "precio_venta": 150_000,
        "stock": 6,
        "stock_minimo": 2,
    },
    {
        "codigo": "REP-LLANTA-10",
        "nombre": "Llanta 10 pulgadas para monopatín",
        "categoria": CategoriaProducto.REPUESTO,
        "precio_venta": 90_000,
        "stock": 4,
        "stock_minimo": 2,
    },
    {
        "codigo": "REP-PASTILLAS",
        "nombre": "Pastillas de freno de disco (par)",
        "categoria": CategoriaProducto.REPUESTO,
        "precio_venta": 35_000,
        "stock": 8,
        "stock_minimo": 5,
    },
    {
        "codigo": "REP-CAMARA-26",
        "nombre": "Neumático interior (cámara) rin 26",
        "categoria": CategoriaProducto.REPUESTO,
        "precio_venta": 18_000,
        "stock": 0,
        "stock_minimo": 3,
    },  # agotado
]


def _poligono(*vertices: tuple[float, float]) -> dict:
    """GeoJSON Polygon a partir de vértices (latitud, longitud). Cierra el anillo solo."""
    anillo = [[lng, lat] for lat, lng in vertices]
    anillo.append(anillo[0])
    return {"type": "Polygon", "coordinates": [anillo]}


# APROXIMADAS: trazadas a mano sobre el mapa de Bucaramanga, sin traslaparse. Antes de
# producción, redibujarlas con precisión (p. ej., en geojson.io) y cargarlas desde el
# panel del administrador.
ZONAS_COBERTURA = [
    {
        "nombre": "Centro",
        "tarifa_envio": 4_000,
        # Parque Santander, Parque García Rovira, San Francisco.
        "poligono": _poligono(
            (7.1300, -73.1350), (7.1300, -73.1150), (7.1100, -73.1150), (7.1100, -73.1350)
        ),
    },
    {
        "nombre": "Cabecera del Llano",
        "tarifa_envio": 5_000,
        # Cabecera, Sotomayor, El Prado.
        "poligono": _poligono(
            (7.1250, -73.1150), (7.1250, -73.0950), (7.1050, -73.0950), (7.1050, -73.1150)
        ),
    },
    {
        "nombre": "Sur (Provenza)",
        "tarifa_envio": 7_000,
        # Provenza, Fontana, Diamante II.
        "poligono": _poligono(
            (7.1000, -73.1200), (7.1000, -73.1000), (7.0800, -73.1000), (7.0800, -73.1200)
        ),
    },
]

METODOS_PAGO = [
    {"codigo": "tarjeta", "nombre": "Tarjeta de crédito o débito"},
    {"codigo": "pse", "nombre": "PSE (débito desde cuenta bancaria)"},
]

_PROVISIONAL = "[TEXTO PROVISIONAL: reemplazar por el texto oficial del equipo] "

CONTENIDO_PORTAL = [
    {
        "seccion": "mision",
        "titulo": "Misión",
        "contenido": _PROVISIONAL + "Facilitar la movilidad urbana sostenible en Bucaramanga "
        "con el alquiler, la venta y la entrega a domicilio de ciclas, patines y monopatines "
        "eléctricos, de forma sencilla, segura y confiable.",
    },
    {
        "seccion": "vision",
        "titulo": "Visión",
        "contenido": _PROVISIONAL + "Ser la plataforma de referencia en movilidad liviana del "
        "área metropolitana de Bucaramanga, reconocida por la calidad de su flota y de su "
        "servicio.",
    },
    {
        "seccion": "contacto",
        "titulo": "Contacto",
        "contenido": _PROVISIONAL + "Correo: contacto@transportexperience.test · "
        "Teléfono: por definir · Dirección: Bucaramanga, Santander.",
    },
]

# 0 = lunes ... 6 = domingo. Sin fila = cerrado (domingo). PROVISIONAL.
HORARIOS_ATENCION = [
    *(
        {"dia_semana": dia, "hora_apertura": time(7, 0), "hora_cierre": time(19, 0)}
        for dia in range(5)
    ),
    {"dia_semana": 5, "hora_apertura": time(8, 0), "hora_cierre": time(17, 0)},
]
