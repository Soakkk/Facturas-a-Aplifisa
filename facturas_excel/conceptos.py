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
DEFAULT_VENTA = "700"        # y 700 en ventas

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
# Aplifisa tiene una pantalla ("Importación de Excel / Parametrizar los textos
# de los Conceptos") donde se le dice: el texto TAL es el concepto CUAL. Si en
# la columna Concepto del Excel va ese texto, el apunte entra con su cuenta Y su
# subclave puestas, sin tener que elegir nada a mano ni siquiera con proveedores
# nuevos. Que es justo el problema de la 628.
#
# Aqui esta lo que escribe el programa. Se configura una vez en Aplifisa (el
# menu Configuración -> "Textos de conceptos para Aplifisa" da la lista hecha).
# Clave: (cuenta, subclave o None). Texto: lo que va al Excel.
TEXTOS_APLIFISA = {
    ("600", None): "COMPRAS",
    ("621", None): "ALQUILERES",
    ("622", None): "REPARACIONES",
    ("623", None): "PROFESIONALES",
    ("624", None): "TRANSPORTES",
    ("625", None): "SEGUROS",
    ("626", None): "GASTOS BANCARIOS",
    ("627", None): "PUBLICIDAD",
    ("628", "G14"): "LUZ",
    ("628", "G15"): "AGUA",
    ("628", "G16"): "GASOLEO",
    ("628", "G17"): "TELEFONO",
    ("628", "G18"): "OTROS SUMINISTROS",
    ("629", None): "OTROS SERVICIOS",
    ("631", None): "TRIBUTOS",
    ("700", None): "VENTAS",
}


def texto_para(cuenta, subclave=None) -> str | None:
    """El texto parametrizado de ese concepto, o None si no hay ninguno.

    Sin texto no se inventa nada: se exporta el codigo de siempre.
    """
    cuenta = (str(cuenta or "").strip() or None)
    if not cuenta:
        return None
    gxx = (str(subclave or "").strip().upper() or None)
    return (TEXTOS_APLIFISA.get((cuenta, gxx))
            or TEXTOS_APLIFISA.get((cuenta, None)))


def tabla_textos() -> list:
    """[(concepto legible, texto)] para enseñarla y copiarla."""
    filas = []
    for (cuenta, gxx), texto in TEXTOS_APLIFISA.items():
        etiqueta = f"{cuenta} ({gxx})" if gxx else cuenta
        descripcion = SUBCLAVES_628.get(gxx, "") if cuenta == "628" else ""
        filas.append((etiqueta, descripcion, texto))
    return filas
