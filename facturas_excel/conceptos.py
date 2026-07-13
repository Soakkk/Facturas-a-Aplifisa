"""Criterio GENERAL de asignacion de concepto (cuenta PGC PYMES) para la columna
Concepto del Excel de Aplifisa. Vale para todos los clientes de la asesoria.

Se asigna a partir de la descripcion que sugiere Gemini (contraparte + concepto),
por palabras clave. Es facilmente editable: ajusta CUENTA_* y los MAPA_*.

Aplifisa: la columna Concepto es el CODIGO NUMERICO de la cuenta. Las cuentas de
suministros 628 son "genericas" y Aplifisa pedira a mano la subclave AEAT (GXX):
  628 luz=G14 · agua=G15 · gas=G16 · telefonia/internet=G17 · otros=G18
La primera vez de cada proveedor se elige el GXX; despues Aplifisa lo recuerda.
"""

from __future__ import annotations

import unicodedata

# --- cuentas base (ajustables por criterio de la asesoria) ---
CUENTA_COMBUSTIBLE = "628"   # carburante como suministro (subclave GXX: G18 otros)
DEFAULT_GASTO = "600"        # Aplifisa asigna 600 por defecto en compras
DEFAULT_VENTA = "700"        # y 700 en ventas

# Reglas ordenadas por PRIORIDAD (la primera que coincide gana). El orden importa:
# los tributos y suministros van antes que reparacion/combustible para evitar
# falsos positivos (p.ej. "traccion mecanica" no debe ir a reparacion).
REGLAS_GASTOS = [
    ("631", ["impuesto", "tributo", "tasa", "ivtm", "vehiculos de traccion",
             "agencia tributaria", "ayuntamiento", "suma gestion"]),
    ("628", ["telefon", "telecomunicacion", "internet", "movil", "orange",
             "movistar", "vodafone", "masmovil", "yoigo", "fibra"]),
    ("628", ["electricidad", "energia electrica", "iberdrola", "endesa", "naturgy"]),
    ("628", ["aquaservice", "suministro de agua", "hidrogea", "aguas de",
             "factura de agua", "consumo de agua"]),
    ("628", ["gas natural", "butano", "propano", "redexis"]),
    ("623", ["notari", "registr", "abogad", "procurador", "gestoria",
             "asesoria", "auditor"]),
    ("625", ["seguro", "poliza", "mutua", "mapfre"]),
    ("626", ["comision bancaria", "banco", "interes"]),
    ("627", ["publicidad", "marketing"]),
    ("621", ["alquiler", "arrendamiento", "renting"]),
    ("622", ["taller", "reparacion", "averia", "neumatico", "recambio",
             "repuesto", "kit distribucion", "revision vehiculo"]),
    (CUENTA_COMBUSTIBLE, ["combustible", "gasoleo", "gasoil", "gasolina",
                          "diesel", "carburante"]),
    ("624", ["mensajeria", "porte", "paqueteria"]),
    ("629", ["papeleria", "material de oficina"]),
]
REGLAS_VENTAS = [
    # normalmente todas al 700; se puede afinar por actividad del cliente
]


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def asignar_concepto(tipo: str, texto_busqueda: str) -> str:
    """Devuelve el codigo de concepto segun palabras clave, por prioridad.
    `texto_busqueda` incluye el concepto sugerido y el nombre de la contraparte."""
    texto = _sin_acentos((texto_busqueda or "").lower())
    reglas = REGLAS_GASTOS if tipo == "gasto" else REGLAS_VENTAS
    for codigo, claves in reglas:
        if any(_sin_acentos(c) in texto for c in claves):
            return codigo
    return DEFAULT_GASTO if tipo == "gasto" else DEFAULT_VENTA


# Subclave AEAT sugerida para suministros 628 (solo informativa para el usuario).
GXX_628 = {"luz": "G14", "electricidad": "G14", "aquaservice": "G15",
           "suministro de agua": "G15", "gas natural": "G16",
           "telefon": "G17", "internet": "G17", "movil": "G17", "orange": "G17",
           "movistar": "G17", "vodafone": "G17",
           "combustible": "G18", "gasoleo": "G18", "gasoil": "G18",
           "gasolina": "G18", "diesel": "G18", "carburante": "G18"}


def subclave_628(texto_busqueda: str) -> str | None:
    texto = _sin_acentos((texto_busqueda or "").lower())
    for clave, gxx in GXX_628.items():
        if _sin_acentos(clave) in texto:
            return gxx
    return None
