"""Una factura, un PDF: se parte el taco escaneado al exportar.

Al escanear, el taco entero queda en un solo PDF. Cuando el lote se exporta,
cada factura ya está revisada (proveedor, NIF, número, fecha y hojas bien
unidas), así que es el momento seguro de separarlas:

    Nombre — NIF / 2026 / Gastos   / 2026-02-12 GASOLINERA EJEMPLO SL G-118.pdf
    Nombre — NIF / 2026 / Ingresos / 2026-03-03 CLIENTE FINAL SA V-33.pdf
    Nombre — NIF / 2026 / Tacos escaneados / <el PDF original, intacto>

Cada factura va al ejercicio de SU fecha y a Gastos o Ingresos según SU tipo
(un taco puede mezclar años o tipos). La fecha va delante en el nombre para
que la carpeta se ordene sola. El taco original nunca se borra: se aparta en
«Tacos escaneados». Si una factura ya se había separado antes (el mismo nombre
ya existe), no se duplica.
"""

from __future__ import annotations

import os
import shutil
from collections import OrderedDict
from typing import Dict, Iterable, List, Tuple

from . import archivo
from .control_facturas import clave_documento
from .escaner import sanear
from .validacion import fecha_de

TACOS = "Tacos escaneados"


def paginas_de(f) -> List[Tuple[str, int]]:
    """Las hojas (archivo, página) de una factura, en orden."""
    manual = [(o, int(p)) for o, p in (getattr(f, "paginas_documento", ()) or ())]
    if manual:
        return manual
    origen = f.origen_imagen or ""
    primera = int(f.pagina_origen or 0)
    ultima = int(f.ultima_pagina_origen or primera)
    if not origen:
        return []
    if not origen.lower().endswith(".pdf"):
        return [(origen, 1)]           # una imagen suelta es una hoja
    if primera < 1:
        return []
    return [(origen, p) for p in range(primera, max(primera, ultima) + 1)]


def nombre_factura(f) -> str:
    dia = fecha_de(f.fecha) if f.fecha else None
    partes = [dia.isoformat() if dia else "sin fecha",
              sanear(f.nombre or "sin nombre")[:45],
              sanear(f.num_factura or "sin numero")[:30]]
    return " ".join(p for p in partes if p) + ".pdf"


def _documentos(facturas_por_tipo: Dict[str, Iterable]) -> "OrderedDict":
    """Agrupa las líneas de IVA de cada factura: {clave: (tipo, primera línea)}."""
    docs: "OrderedDict" = OrderedDict()
    for tipo, facturas in facturas_por_tipo.items():
        for f in facturas:
            docs.setdefault(clave_documento(f), (tipo, f))
    return docs


def _dentro(ruta: str, base: str) -> bool:
    ruta = os.path.normcase(os.path.abspath(ruta))
    base = os.path.normcase(os.path.abspath(base))
    return ruta.startswith(base + os.sep)


def separar(facturas_por_tipo: Dict[str, Iterable], base: str,
            cliente: str, nif: str) -> dict:
    """Crea un PDF por factura y aparta los tacos originales.

    Devuelve {"creados": [...], "ya_estaban": n, "sin_paginas": [...],
    "tacos": {ruta vieja: ruta nueva}, "afectados": {(ejercicio)}}.
    """
    import fitz

    creados, sin_paginas, ya_estaban = [], [], 0
    usados: set = set()
    afectados = set()
    abiertos: Dict[str, "fitz.Document"] = {}
    try:
        for _clave, (tipo, f) in _documentos(facturas_por_tipo).items():
            paginas = paginas_de(f)
            if not paginas or not all(os.path.isfile(o) for o, _ in paginas):
                sin_paginas.append(f.num_factura or f.nombre or "?")
                continue
            dia = fecha_de(f.fecha) if f.fecha else None
            ejercicio = dia.year if dia else None
            if not ejercicio:
                sin_paginas.append(f.num_factura or f.nombre or "?")
                continue
            carpeta = archivo.carpeta_tipo_cliente(cliente, ejercicio, tipo, base, nif=nif)
            destino = os.path.join(carpeta, nombre_factura(f))
            if os.path.exists(destino):
                ya_estaban += 1
                continue
            nuevo = fitz.open()
            for origen, pagina in paginas:
                if origen.lower().endswith(".pdf"):
                    if origen not in abiertos:
                        abiertos[origen] = fitz.open(origen)
                    fuente = abiertos[origen]
                    if 1 <= pagina <= fuente.page_count:
                        nuevo.insert_pdf(fuente, from_page=pagina - 1, to_page=pagina - 1)
                else:
                    with fitz.open(origen) as imagen:
                        nuevo.insert_pdf(fitz.open("pdf", imagen.convert_to_pdf()))
            if not nuevo.page_count:
                nuevo.close()
                sin_paginas.append(f.num_factura or f.nombre or "?")
                continue
            temporal = destino + ".tmp"
            nuevo.save(temporal, garbage=3, deflate=True)
            nuevo.close()
            os.replace(temporal, destino)
            creados.append(destino)
            afectados.add(ejercicio)
            usados.update(o for o, _ in paginas)
    finally:
        for doc in abiertos.values():
            doc.close()

    # Los tacos de los que han salido facturas se apartan, intactos. Solo los
    # que ya viven en el archivo documental: un PDF externo no se mueve.
    tacos = {}
    for origen in sorted(usados):
        if (not origen.lower().endswith(".pdf") or not _dentro(origen, base)
                or os.path.basename(os.path.dirname(origen)) == TACOS):
            continue
        carpeta_ejercicio = os.path.dirname(os.path.dirname(origen))
        if not os.path.basename(carpeta_ejercicio).isdigit():
            continue
        carpeta_tacos = os.path.join(carpeta_ejercicio, TACOS)
        os.makedirs(carpeta_tacos, exist_ok=True)
        nombre = os.path.basename(origen)
        destino = os.path.join(carpeta_tacos, nombre)
        n = 2
        while os.path.exists(destino):
            raiz, ext = os.path.splitext(nombre)
            destino = os.path.join(carpeta_tacos, f"{raiz}_{n}{ext}")
            n += 1
        try:
            shutil.move(origen, destino)
            tacos[origen] = destino
        except OSError:
            pass            # abierto en otro programa: se queda donde está
    return {"creados": creados, "ya_estaban": ya_estaban,
            "sin_paginas": sin_paginas, "tacos": tacos, "afectados": afectados}
