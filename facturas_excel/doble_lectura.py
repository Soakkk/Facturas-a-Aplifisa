"""Doble lectura: dos modelos leen la misma hoja y se comparan dato a dato.

Un digito mal leido casi nunca lo leen mal IGUAL dos modelos distintos. Si las
dos lecturas coinciden, el dato esta verificado; si no, la fila queda en ambar
con los dos valores delante para que decida una persona. Nunca se elige uno de
los dos a escondidas.
"""

from __future__ import annotations

import re
from typing import List, Optional

# Lo que se compara, con el nombre que ve el usuario y el campo de la Factura
# al que afecta (para colorear la celda y poder aplicar el otro valor).
CAMPOS_COMPARADOS = (
    ("emisor_nif", "NIF del emisor"),
    ("receptor_nif", "NIF del destinatario"),
    ("num_factura", "Nº de factura"),
    ("fecha", "Fecha"),
    ("total", "Total"),
    ("cuota_irpf", "Retención IRPF"),
    ("suplidos", "Suplidos"),
)

TOLERANCIA = 0.011


def _texto(valor) -> str:
    return "".join(c for c in str(valor or "") if c.isalnum()).upper()


def _numero(valor) -> Optional[float]:
    from .extraccion import _num
    return _num(valor)


def _fecha(valor):
    from .validacion import fecha_de
    return fecha_de(valor) if valor else None


def _iguales(campo: str, a, b) -> bool:
    if campo in ("total", "cuota_irpf", "suplidos"):
        na, nb = _numero(a), _numero(b)
        if na is None or nb is None:
            return na is None and nb is None
        return abs(na - nb) <= TOLERANCIA
    if campo == "fecha":
        fa, fb = _fecha(a), _fecha(b)
        if fa and fb:
            return fa == fb
        return _texto(a) == _texto(b)
    return _texto(a) == _texto(b)


def _lineas(datos: dict) -> list:
    """Lineas de IVA comparables: (tipo, base, cuota, recargo) por tipo."""
    salida = []
    for linea in datos.get("lineas_iva") or []:
        if not isinstance(linea, dict):
            continue
        valores = tuple(_numero(linea.get(c)) for c in
                        ("tipo_iva", "base", "cuota_iva", "cuota_requiv"))
        if any(v is not None for v in valores[:3]):
            salida.append(valores)
    return sorted(salida, key=lambda v: (v[0] is None, v[0] or 0, v[1] or 0))


def _fmt(valor) -> str:
    if valor is None or valor == "":
        return "(vacío)"
    if isinstance(valor, float):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(valor)


def _fmt_lineas(lineas: list) -> str:
    if not lineas:
        return "(sin desglose)"
    partes = []
    for tipo, base, cuota, recargo in lineas:
        texto = f"base {_fmt(base)} al {_fmt(tipo).replace(',00', '')}% = {_fmt(cuota)}"
        if recargo:
            texto += f" + RE {_fmt(recargo)}"
        partes.append(texto)
    return "; ".join(partes)


def comparar(uno: dict, dos: dict) -> List[dict]:
    """Diferencias entre dos lecturas de la misma hoja.

    Devuelve [{campo, etiqueta, valor_1, valor_2}] con los valores tal como
    los devolvio cada modelo (para poder aplicarlos sin reinterpretarlos).
    """
    diferencias = []
    for campo, etiqueta in CAMPOS_COMPARADOS:
        a, b = uno.get(campo), dos.get(campo)
        if not _iguales(campo, a, b):
            diferencias.append({"campo": campo, "etiqueta": etiqueta,
                                "valor_1": a, "valor_2": b})
    l1, l2 = _lineas(uno), _lineas(dos)
    iguales = len(l1) == len(l2) and all(
        all((x is None and y is None) or (x is not None and y is not None
                                          and abs(x - y) <= TOLERANCIA)
            for x, y in zip(a, b))
        for a, b in zip(l1, l2))
    if not iguales:
        diferencias.append({"campo": "lineas_iva", "etiqueta": "Desglose de IVA",
                            "valor_1": _fmt_lineas(l1),
                            "valor_2": _fmt_lineas(l2),
                            "lineas_1": uno.get("lineas_iva"),
                            "lineas_2": dos.get("lineas_iva")})
    return diferencias


def texto_diferencia(d: dict, modelo_1: str = "", modelo_2: str = "") -> str:
    m1 = modelo_1 or "lectura 1"
    m2 = modelo_2 or "lectura 2"
    return (f"Doble lectura: {d['etiqueta']} no coincide — {m1}: "
            f"{_fmt(d['valor_1'])} · {m2}: {_fmt(d['valor_2'])}")


def es_dudosa(datos: dict) -> bool:
    """Si una lectura merece una segunda opinion (modo «solo dudosas»)."""
    from .validacion import validar_nif
    if str(datos.get("confianza") or "").strip().lower() != "alta":
        return True
    if datos.get("manuscrito_en_importes"):
        return True
    for campo in ("emisor_nif", "receptor_nif"):
        valor = datos.get(campo)
        if valor and not validar_nif(re.sub(r"[\s.-]", "", str(valor))):
            return True
    total = _numero(datos.get("total"))
    lineas = _lineas(datos)
    estado = str(datos.get("estado_pagina_factura") or "").lower()
    if estado in ("inicio", "intermedia"):
        return False          # hoja sin resumen fiscal: no hay nada que cuadrar
    if total is None or not lineas:
        return True
    suma = sum((base or 0) + (cuota or 0) + (recargo or 0)
               for _t, base, cuota, recargo in lineas)
    suma += _numero(datos.get("suplidos")) or 0
    suma -= _numero(datos.get("cuota_irpf")) or 0
    return abs(round(suma, 2) - total) > 0.02


def combinar(principal: dict, segunda: Optional[dict], modelo_1: str,
             modelo_2: str, error_2: str = "") -> dict:
    """La lectura que va a la tabla, con el resultado de la comparacion.

    Los datos que se usan son SIEMPRE los del modelo principal; la segunda
    lectura solo confirma o señala. Se guardan las dos para poder elegir.
    """
    datos = dict(principal)
    datos["_modelo_1"] = modelo_1
    if segunda is None:
        datos["_verificacion"] = "simple"
        if error_2:
            datos["_error_2"] = error_2
        return datos
    datos["_modelo_2"] = modelo_2
    datos["_lectura_2"] = segunda
    datos["_discrepancias"] = comparar(principal, segunda)
    datos["_verificacion"] = "doble"
    return datos
