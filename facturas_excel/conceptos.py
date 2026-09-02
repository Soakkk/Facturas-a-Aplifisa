"""Criterio GENERAL de asignacion de concepto (cuenta PGC PYMES) para la columna
Concepto del Excel de Aplifisa. Vale para todos los clientes de la asesoria.

Se asigna a partir de la descripcion que sugiere Gemini (contraparte + concepto),
por palabras clave. Es facilmente editable: ajusta CUENTA_* y los MAPA_*.

Aplifisa: la columna Concepto es el CODIGO NUMERICO de la cuenta. Las cuentas de
suministros 628 son "genericas" y Aplifisa pedira a mano la subclave AEAT (GXX):
  628 luz=G14 · agua=G15 · gas=G16 (gasoleo y derivados van aqui) ·
      telefonia/internet=G17 · otros=G18
La primera vez de cada proveedor se elige el GXX; despues Aplifisa lo recuerda.
"""

from __future__ import annotations

import re
import unicodedata

# --- cuentas base (ajustables por criterio de la asesoria) ---
CUENTA_COMBUSTIBLE = "628"   # carburante como suministro; subclave G16 (gas)
DEFAULT_GASTO = "600"        # Aplifisa asigna 600 por defecto en compras
DEFAULT_VENTA = "700"        # y 700 en ventas (subclave I01)

# Reglas ordenadas por PRIORIDAD (la primera que coincide gana). El orden importa:
# los tributos y suministros van antes que reparacion/combustible para evitar
# falsos positivos (p.ej. "traccion mecanica" no debe ir a reparacion).
REGLAS_GASTOS = [
    ("631", ["impuesto", "tributo", "tasa", "ivtm", "vehiculos de traccion",
             "agencia tributaria", "ayuntamiento", "suma gestion"]),
    ("628", ["telefon", "telecomunicacion", "internet", "movil", "orange",
             "movistar", "vodafone", "masmovil", "yoigo", "fibra", "jazztel",
             "pepephone", "lowi", "digi ", "finetwork", "adamo", "euskaltel",
             "simyo", "o2 ", "linea movil", "cuota fija", "banda ancha"]),
    ("628", ["electricidad", "energia electrica", "iberdrola", "endesa",
             "naturgy", "holaluz", "totalenergies", "audax", "curenergia",
             "energia xxi", "peaje de acceso", "kwh", "potencia contratada"]),
    ("628", ["aquaservice", "suministro de agua", "hidrogea", "aguas de",
             "factura de agua", "consumo de agua", "emuasa", "aqualia",
             "acuambiente", "canal de isabel", "agua potable", "alcantarillado",
             "saneamiento y depuracion"]),
    ("628", ["gas natural", "butano", "propano", "redexis", "nedgia"]),
    ("623", ["notari", "registr", "abogad", "procurador", "gestoria",
             "asesoria", "auditor"]),
    ("625", ["seguro", "poliza", "mutua", "mapfre"]),
    ("626", ["comision bancaria", "banco", "interes"]),
    ("627", ["publicidad", "marketing"]),
    ("621", ["alquiler", "arrendamiento", "renting"]),
    ("622", ["taller", "reparacion", "averia", "neumatico", "recambio",
             "repuesto", "kit distribucion", "revision vehiculo"]),
    (CUENTA_COMBUSTIBLE, ["combustible", "gasoleo", "gasoil", "gasolina",
                          "diesel", "carburante", "adblue", "estacion de servicio",
                          "area de servicio", "gasolinera", "cepsa", "repsol",
                          "galp", "petroprix", "ballenoil", "plenoil", "shell",
                          "avia", "bonarea combustible"]),
    ("624", ["mensajeria", "porte", "paqueteria"]),
    ("629", ["papeleria", "material de oficina"]),
]
REGLAS_VENTAS = [
    # normalmente todas al 700; se puede afinar por actividad del cliente
]


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _contiene(texto: str, clave: str) -> bool:
    """Busca la palabra ENTERA, no un trozo.

    Si no, "gas" cazaba dentro de "gasoleo" y el combustible se iba a la
    subclave del gas (G16) en vez de a otros suministros (G18).
    """
    clave = _sin_acentos(clave.strip().lower())
    if not clave:
        return False
    return re.search(r"\b" + re.escape(clave) + r"\b", texto) is not None


def asignar_concepto(tipo: str, texto_busqueda: str) -> str:
    """Devuelve el codigo de concepto segun palabras clave, por prioridad.
    `texto_busqueda` incluye el concepto sugerido y el nombre de la contraparte."""
    texto = _sin_acentos((texto_busqueda or "").lower())
    reglas = REGLAS_GASTOS if tipo == "gasto" else REGLAS_VENTAS
    for codigo, claves in reglas:
        if any(_contiene(texto, c) for c in claves):
            return codigo
    return DEFAULT_GASTO if tipo == "gasto" else DEFAULT_VENTA


# --- subclaves AEAT de la 628 -----------------------------------------------
# En Aplifisa la 628 NO se puede dejar sin subclave: son cuentas "genericas" y
# desde 2021 Hacienda exige decir de que suministro se trata. Si falta, el
# apunte se queda a revisar y hay que elegirla a mano.
SUBCLAVES_628 = {
    "G14": "Suministros electricidad",
    "G15": "Suministros agua",
    "G16": "Suministros gas (aquí van también gasóleo y derivados)",
    "G17": "Suministros telefonia e internet",
    "G18": "Otros suministros",
}

# Por orden: la primera palabra que se encuentre manda. El agua y la luz van
# antes que el combustible porque "suministro" a secas no dice de que es.
GXX_628 = [
    ("G14", ["electricidad", "energia electrica", "iberdrola", "endesa",
             "naturgy", "holaluz", "totalenergies", "audax", "curenergia",
             "energia xxi", "kwh", "potencia contratada", "luz"]),
    ("G15", ["agua", "aquaservice", "hidrogea", "emuasa", "aqualia",
             "acuambiente", "alcantarillado", "saneamiento"]),
    # Criterio de la asesoria (confirmado 2026-09-02): el GASOLEO y sus
    # derivados son gas, o sea G16. No van a "otros suministros".
    ("G16", ["gas natural", "butano", "propano", "redexis", "nedgia",
             "gas ciudad", "gas", "gasoleo", "gasoil", "gasolina", "diesel",
             "carburante", "combustible", "adblue", "estacion de servicio",
             "area de servicio", "gasolinera", "cepsa", "repsol", "galp",
             "petroprix", "ballenoil", "plenoil", "shell", "avia"]),
    ("G17", ["telefon", "internet", "movil", "fibra", "orange", "movistar",
             "vodafone", "masmovil", "yoigo", "jazztel", "pepephone", "lowi",
             "digi ", "finetwork", "adamo", "banda ancha", "telecomunicacion"]),
    ("G18", ["otros suministros"]),
]


def subclave_628(texto_busqueda: str) -> str | None:
    """Que suministro es, para la subclave que exige Aplifisa en la 628."""
    texto = _sin_acentos((texto_busqueda or "").lower())
    for gxx, claves in GXX_628:
        if any(_contiene(texto, c) for c in claves):
            return gxx
    return None


# --------------------------------------------------------- textos para Aplifisa
# Aplifisa tiene una pantalla ("Importacion de Excel / Parametrizar los textos
# de los Conceptos") donde se le dice: el texto TAL es el concepto CUAL. Si en
# la columna Concepto del Excel va ese texto, el apunte entra con su cuenta Y su
# subclave puestas, sin elegir nada a mano ni siquiera con proveedores nuevos.
# Que es justo lo que hacia falta para la 628.
#
# El texto que escribe el programa es la DESCRIPCION del propio Aplifisa
# ("SUMINISTROS GAS"), que es unica y se reconoce de un vistazo en su pantalla.
# El usuario puede añadir ademas sus propios sinonimos alli (van por comas).
def texto_para(cuenta, subclave=None) -> str | None:
    """El texto que se escribe en el Excel para ese concepto.

    None si la pareja no existe en el catalogo: entonces se exporta el codigo
    de siempre y no se inventa nada.
    """
    return descripcion_de(cuenta, subclave) if es_valido(cuenta, subclave) else None


def tabla_textos() -> list:
    """[(concepto, que es, texto)] para enseñarla y copiarla."""
    return [(f"{c} ({g})" if g else c, d, d) for c, g, d in catalogo()]


# ------------------------------------------- catalogo de conceptos de Aplifisa
# La lista EXACTA que ofrece Aplifisa (config/conceptos_aplifisa.csv, sacada de
# su pantalla de conceptos). Sirve para tres cosas:
#   1. decirle a Gemini entre que conceptos tiene que elegir (y no inventarse
#      cuentas que Aplifisa no admite),
#   2. comprobar que la pareja cuenta+subclave existe de verdad,
#   3. dar el texto que se parametriza en Aplifisa para que el apunte entre con
#      su subclave puesta.
_CATALOGO: list | None = None


def catalogo(tipo=None) -> list:
    """[(cuenta, gxx, descripcion)] tal como los ofrece Aplifisa.

    `tipo` filtra por "gasto" o "ingreso" (los conceptos de cada lado son
    distintos: los gastos llevan subclaves GXX y los ingresos IXX).
    """
    global _CATALOGO
    if _CATALOGO is None:
        from .rutas import ruta_config
        filas = []
        try:
            with open(ruta_config("conceptos_aplifisa.csv"), encoding="utf-8") as fh:
                for linea in fh.read().splitlines()[1:]:
                    if not linea.strip():
                        continue
                    partes = linea.split(";")
                    if len(partes) >= 4:
                        filas.append((partes[0].strip().lower(), partes[1].strip(),
                                      partes[2].strip().upper(), partes[3].strip()))
        except OSError:
            filas = []
        _CATALOGO = filas
    return [(c, g, d) for t, c, g, d in _CATALOGO
            if tipo is None or t in (tipo, "ambos")]


def normalizar_concepto(cuenta, subclave=None) -> tuple[str, str | None]:
    """Separa la cuenta y la subclave aunque Gemini devuelva la etiqueta entera.

    La respuesta pedida es ``628`` + ``G16``, pero a veces el modelo copia una
    linea completa del catalogo: ``628 (G16) SUMINISTROS GAS``. Esa etiqueta no
    puede llegar a la tabla como cuenta porque Aplifisa solo reconoce el codigo.
    Se conservan los valores desconocidos para que la validacion siga avisando
    en vez de corregir silenciosamente una propuesta realmente invalida.
    """
    texto_cuenta = str(cuenta or "").strip()
    texto_subclave = str(subclave or "").strip().upper()

    cuentas_validas = {c for c, _, _ in catalogo()}
    cuenta_limpia = texto_cuenta
    if cuenta_limpia not in cuentas_validas:
        encontrada = re.search(r"(?<!\d)(\d{3})(?!\d)", texto_cuenta)
        if encontrada and encontrada.group(1) in cuentas_validas:
            cuenta_limpia = encontrada.group(1)

    # Primero manda el campo especifico. Si viene vacio, se recupera la
    # subclave que Gemini haya incluido entre parentesis en cuenta_gasto/
    # cuenta_ingreso. Tambien se admite el concepto especial 200 (200).
    gxx = texto_subclave or None
    if texto_subclave:
        encontrada = re.search(r"(?<![A-Z0-9])([GI]\d{2}|200)(?![A-Z0-9])",
                               texto_subclave)
        if encontrada:
            gxx = encontrada.group(1)
    elif cuenta_limpia:
        posibles = [g for c, g, _ in catalogo() if c == cuenta_limpia and g]
        mayusculas = texto_cuenta.upper()
        gxx = next((g for g in posibles
                    if re.search(r"(?<![A-Z0-9])" + re.escape(g)
                                 + r"(?![A-Z0-9])", mayusculas)), None)

    return cuenta_limpia, gxx


def descripcion_de(cuenta, gxx=None) -> str | None:
    """Como llama Aplifisa a ese concepto, o None si no existe tal pareja."""
    cuenta = str(cuenta or "").strip()
    gxx = str(gxx or "").strip().upper()
    for c, g, desc in catalogo():
        if c == cuenta and (g == gxx or not gxx):
            return desc
    return None


def subclaves_de(cuenta) -> list:
    """Subclaves validas de una cuenta: [(gxx, descripcion)]."""
    cuenta = str(cuenta or "").strip()
    return [(g, d) for c, g, d in catalogo() if c == cuenta and g]


def es_valido(cuenta, gxx=None) -> bool:
    """La pareja cuenta+subclave existe en Aplifisa."""
    cuenta = str(cuenta or "").strip()
    gxx = str(gxx or "").strip().upper()
    if not cuenta:
        return False
    posibles = [g for c, g, _ in catalogo() if c == cuenta]
    if not posibles:
        return False
    return gxx in posibles if gxx else True

