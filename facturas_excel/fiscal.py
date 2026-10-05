"""Lo que dice la ley de cada factura (1.24): avisos con su porqué.

Criterio del proyecto (CLAUDE.md): manda la ley vigente en la fecha de la
factura, no lo que traiga impresa. Aquí van los avisos que dependen de si la
factura es un gasto o una venta; los que no, están en validacion.py.

Todos son ámbar (se pueden confirmar con «Marcar revisada»): avisan de algo
que la persona tiene que decidir con la factura delante, y una lectura mala
de la IA no puede dejar una factura sin salida.
"""

from __future__ import annotations

from typing import List, Tuple

from .modelo import Factura

# (texto, campos, gravedad) como los usa ventana_validacion.
Aviso = Tuple[str, tuple, str]

NO_ES_FACTURA = {
    "proforma": "una factura PROFORMA",
    "albaran": "un ALBARÁN",
    "presupuesto": "un PRESUPUESTO",
    "pedido": "un PEDIDO",
    "recibo": "un RECIBO",
}

_MENCION = {
    ("gasto", "inversion_sujeto_pasivo"):
        "Inversión del sujeto pasivo: el proveedor no cobra el IVA; lo declara "
        "el cliente, que se lo repercute y se lo deduce en el 303 (art. 84.Uno.2º "
        "de la Ley del IVA). En Aplifisa, regístrela como inversión del sujeto "
        "pasivo.",
    ("venta", "inversion_sujeto_pasivo"):
        "Inversión del sujeto pasivo: la factura va sin IVA y lo declara el "
        "comprador (art. 84.Uno.2º de la Ley del IVA). En Aplifisa, regístrela "
        "como inversión del sujeto pasivo.",
    ("gasto", "intracomunitaria"):
        "Adquisición intracomunitaria: el cliente autoliquida el IVA en el 303 "
        "(se lo repercute y se lo deduce) y la declara en el 349 (arts. 13 y 85 "
        "de la Ley del IVA). En Aplifisa, regístrela como intracomunitaria.",
    ("venta", "intracomunitaria"):
        "Entrega intracomunitaria exenta (art. 25 de la Ley del IVA): va en el "
        "349 y el comprador tiene que tener NIF-IVA válido (ROI). En Aplifisa, "
        "regístrela como intracomunitaria.",
    ("gasto", "exportacion"):
        "Importación: el IVA que se deduce es el del DUA de la aduana, no el "
        "de esta factura (art. 97 de la Ley del IVA).",
    ("venta", "exportacion"):
        "Exportación exenta (art. 21 de la Ley del IVA): hace falta el DUA de "
        "exportación.",
}

_NO_DEDUCIBLE = {
    "restauracion":
        "Restauración u hostelería: su IVA solo se deduce si es un gasto "
        "deducible de la actividad (art. 96 de la Ley del IVA).",
    "regalo":
        "Regalos o atenciones a clientes, empleados o terceros: su IVA no se "
        "deduce (art. 96 de la Ley del IVA).",
    "alimentos_tabaco":
        "Alimentos, bebidas o tabaco: su IVA no se deduce, salvo que sean "
        "para revender o para la propia actividad (art. 96 de la Ley del IVA).",
    "joyas":
        "Joyas o alhajas: su IVA no se deduce, salvo que sean para revender "
        "(art. 96 de la Ley del IVA).",
    "espectaculos":
        "Espectáculos o servicios recreativos: su IVA no se deduce (art. 96 de "
        "la Ley del IVA).",
}

POR_EL_TOTAL = (" Si no se puede deducir, pulse «Por el total»: se registra el "
                "importe entero como gasto, sin IVA deducible.")


def avisos(f: Factura, tipo: str) -> List[Aviso]:
    """Los avisos de ley de esta línea, siendo un `tipo` («gasto»/«venta»)."""
    from .validacion import REVISAR
    salida: List[Aviso] = []

    def anadir(texto, *campos):
        salida.append((texto, campos, REVISAR))

    documento = str(getattr(f, "tipo_documento", "") or "").lower()
    if documento in NO_ES_FACTURA:
        anadir(f"Parece {NO_ES_FACTURA[documento]}, no una factura: no se "
               "registra (se registra la factura cuando llegue). Si sí es una "
               "factura, márquela revisada.", "num_factura")
    elif documento == "copia":
        anadir("Pone «copia» o «duplicado»: compruebe que la original no está "
               "ya registrada.", "num_factura")
    elif documento == "rectificativa" and (f.base_iva or 0) > 0 \
            and not getattr(f, "rectifica_a", ""):
        anadir("Factura rectificativa con importes en positivo: si es un abono "
               "(devolución, descuento), van en negativo.", "base_iva")

    moneda = str(getattr(f, "moneda", "") or "EUR").strip().upper()
    if moneda not in ("EUR", "EUROS", "€"):
        anadir(f"Importes en {moneda}: se registran en euros, al tipo de cambio "
               "de la fecha de la factura (art. 79.Once de la Ley del IVA). "
               "Corríjalos y márquela revisada.", "base_iva", "cuota_iva")

    lado = "venta" if tipo == "venta" else "gasto"
    texto = _MENCION.get((lado, getattr(f, "mencion_iva", None)))
    if texto:
        anadir(texto, "pct_iva")

    # El IVA que el cliente puede no deducir: solo en gastos, y no si ya va
    # por el total (recargo, actividad exenta o decidido a mano).
    if lado == "gasto" and not f.iva_incluido_en_base \
            and not getattr(f, "no_deducible", False) and (f.cuota_iva or 0) > 0:
        texto = _NO_DEDUCIBLE.get(getattr(f, "posible_no_deducible", None))
        if texto:
            anadir(texto + POR_EL_TOTAL, "cuota_iva")
        if getattr(f, "sin_nif_destinatario", False):
            anadir("La factura no trae el NIF del cliente: para deducir el IVA "
                   "hace falta la factura completa, con sus datos (art. 97 de la "
                   "Ley del IVA). Pida la factura completa." + POR_EL_TOTAL,
                   "cuota_iva")
    return salida
