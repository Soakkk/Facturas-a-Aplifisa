"""Las distribuciones de la pantalla: los cinco prototipos del lienzo.

El usuario los vio dibujados y quiere elegir en el propio programa el que
mejor le vaya (Ver → Distribución de la pantalla). Todas usan las mismas
tres piezas (la tabla de facturas, la factura con su hoja y lo leído, y los
totales con «Su suma»); cambia dónde va cada una y cómo se enseña.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Dónde va cada pieza.
COLUMNAS = "columnas"            # facturas | factura | totales
TABLA_ARRIBA = "tabla_arriba"    # facturas a lo ancho; debajo factura | totales
TOTALES_ABAJO = "totales_abajo"  # facturas | factura; debajo los totales


@dataclass(frozen=True)
class Distribucion:
    clave: str
    numero: int
    nombre: str
    # Para qué va mejor (sale en el menú): cada una sirve a un momento del
    # trabajo, no son cinco maneras de ver lo mismo.
    uso: str
    descripcion: str
    colocacion: str
    # La hoja arriba y lo leído debajo (si no, uno al lado del otro).
    factura_vertical: bool = False
    # Los totales con un concepto por fila (en columna o en una caja);
    # si no, una fila por ámbito, a lo ancho.
    totales_en_columna: bool = True
    # Lo leído, plegado a una línea al elegirla (se puede desplegar).
    lectura_plegada: bool = False
    # Los datos que ya se sabe dónde están, señalados sobre la hoja.
    datos_sobre_hoja: bool = False
    # La tabla con lo justo: estado, nombre y total.
    tabla_compacta: bool = False
    # Encima de los totales, cuántas facturas están listas y cuántas faltan.
    progreso: bool = False
    # Tamaños de partida de los divisores que usa.
    tamanos: dict = field(default_factory=dict)

    @property
    def titulo(self) -> str:
        return f"{self.numero} · {self.nombre}"

    @property
    def titulo_menu(self) -> str:
        return f"{self.titulo} — {self.uso}"


DISTRIBUCIONES = (
    Distribucion(
        "columnas", 1, "Tres columnas", "todo a la vista en una pantalla grande",
        "Facturas | factura (la hoja arriba y lo leído debajo) | totales "
        "en columna, con «Su suma» al lado de cada importe.",
        COLUMNAS, factura_vertical=True,
        tamanos={"revision": [700, 480, 620], "factura": [520, 320]}),
    Distribucion(
        "sobre_hoja", 2, "Lectura sobre la hoja", "comprobar contra el papel",
        "Como la 1, pero la hoja ocupa toda la factura: lo leído se queda en "
        "una línea y los datos que ya se sabe dónde están se señalan sobre "
        "ella.",
        COLUMNAS, factura_vertical=True, lectura_plegada=True,
        datos_sobre_hoja=True,
        tamanos={"revision": [680, 500, 620], "factura": [520, 320]}),
    Distribucion(
        "tabla_arriba", 3, "Tabla arriba", "repasar el lote entero",
        "La tabla de facturas a lo ancho, con sus columnas a la vista; "
        "debajo, la factura (la hoja y lo leído al lado) y los totales.",
        TABLA_ARRIBA,
        tamanos={"principal": [420, 480], "inferior": [1100, 620],
                 "factura": [440, 520]}),
    Distribucion(
        "cuadre", 4, "Cuadre con su suma", "cuadrar con su suma y con Aplifisa",
        "Facturas | factura arriba; abajo, a todo lo ancho, los totales como "
        "el listado de Aplifisa con «Su suma» bajo cada columna.",
        TOTALES_ABAJO, totales_en_columna=False,
        tamanos={"revision": [900, 960], "factura": [480, 440]}),
    Distribucion(
        "una_a_una", 5, "Una a una", "revisar las pendientes una detrás de otra",
        "Una lista con lo justo (estado, nombre y total), la factura en "
        "grande con lo leído al lado, cuántas quedan y los totales en "
        "columna. Para pantallas anchas.",
        COLUMNAS, tabla_compacta=True, progreso=True,
        tamanos={"revision": [520, 760, 620], "factura": [520, 440]}),
)

POR_DEFECTO = "cuadre"
_POR_CLAVE = {d.clave: d for d in DISTRIBUCIONES}


def buscar(clave) -> Distribucion:
    """La distribución con esa clave (la de siempre si no existe)."""
    return _POR_CLAVE.get(clave, _POR_CLAVE[POR_DEFECTO])
