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
«Tacos escaneados». Si una factura ya se había separado antes (mismo nombre y
mismas hojas), no se duplica. Dos facturas distintas a las que les tocaría el
mismo nombre («A/1» y «A:1», dos tiques sin número de la misma gasolinera el
mismo día) tienen cada una su PDF: la segunda lleva « (2)».
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections import OrderedDict
from typing import Dict, Iterable, List, Tuple

from . import archivo
from .control_facturas import clave_documento
from .escaner import sanear
from .pdf import CERROJO
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


def _huella(doc) -> tuple:
    """Cómo son sus hojas (vistas en pequeño): igual huella, mismas hojas."""
    return tuple(hashlib.sha1(pagina.get_pixmap(dpi=24).samples).hexdigest()
                 for pagina in doc)


# Fotos que el PDF guarda tal cual (JPEG, fax, JBIG2): sus bytes son la foto.
# Las demás (sin comprimir o con Flate) se miran descomprimidas, porque al
# guardar el PDF con deflate=True una imagen sin comprimir pasa a Flate.
_FOTOS_TAL_CUAL = ("DCTDecode", "JPXDecode", "CCITTFaxDecode", "JBIG2Decode")


def _sha(datos: bytes) -> str:
    return hashlib.sha1(datos or b"").hexdigest()


def _huella_rapida(doc):
    """Lo que hay en cada hoja, sin dibujarla: su tamaño y giro, lo que se
    pinta en ella (el contenido, descomprimido) y los bytes de sus fotos y
    letras. Dibujar cada hoja en pequeño (`_huella`) obligaba a descomprimir
    la foto entera del escáner: 4,4 s con 400 facturas, con la ventana
    parada. Si dos huellas rápidas coinciden, las hojas son las mismas; si
    no, puede ser el mismo PDF guardado de otra manera, y se mira dibujado.
    None si la hoja tiene anotaciones o campos: entonces solo vale dibujarla."""
    hojas = []
    for pagina in doc:
        if pagina.first_annot is not None or pagina.first_widget is not None:
            return None
        fotos = []
        for xref, mascara, *_medio, nombre, filtro, _quien in pagina.get_images(full=True):
            flujo = (doc.xref_stream_raw(xref) if filtro in _FOTOS_TAL_CUAL
                     else doc.xref_stream(xref))
            fotos.append((nombre, filtro if filtro in _FOTOS_TAL_CUAL else "",
                          _sha(flujo),
                          _sha(doc.xref_stream(mascara)) if mascara else ""))
        formularios = [(nombre, _sha(doc.xref_stream(xref)))
                       for xref, nombre, *_resto in pagina.get_xobjects()]
        letras = []
        for xref, _ext, _tipo, nombre_base, nombre, codificacion, *_r in \
                pagina.get_fonts(full=True):
            letras.append((nombre, nombre_base, codificacion,
                           _sha(doc.extract_font(xref)[-1])))
        hojas.append((pagina.rotation, tuple(pagina.mediabox), tuple(pagina.cropbox),
                      _sha(pagina.read_contents()), tuple(sorted(fotos)),
                      tuple(sorted(formularios)), tuple(sorted(letras))))
    return tuple(hojas)


class _Hojas:
    """Las hojas de la factura nueva, para compararlas con el PDF que ya hay
    con su nombre. Solo se miran si hace falta (la primera vez que se separa
    un taco no hay ninguno) y primero sin dibujarlas: el resultado es el
    mismo que comparándolas dibujadas, que es lo que se hacía antes."""

    def __init__(self, doc):
        self.doc = doc
        self._rapida = self._dibujada = False      # False: sin calcular aún

    def rapida(self):
        if self._rapida is False:
            self._rapida = _huella_rapida(self.doc)
        return self._rapida

    def dibujada(self) -> tuple:
        if self._dibujada is False:
            self._dibujada = _huella(self.doc)
        return self._dibujada


def _misma_que(ruta: str, hojas: "_Hojas") -> bool:
    import fitz
    try:
        with fitz.open(ruta) as existente:
            if existente.page_count != hojas.doc.page_count:
                return False
            if _iguales_sin_dibujar(existente, hojas):
                return True
            return _huella(existente) == hojas.dibujada()
    except Exception:          # dañado o ilegible: no es «la misma»
        return False


def _iguales_sin_dibujar(existente, hojas: "_Hojas") -> bool:
    """Solo dice «iguales» si lo son seguro; si no lo sabe (una letra que no
    se puede sacar…), se comparan dibujadas, como antes."""
    try:
        rapida = hojas.rapida()
        return rapida is not None and _huella_rapida(existente) == rapida
    except Exception:
        return False


def _destino(carpeta: str, nombre: str, hojas: "_Hojas", reservados: set,
             suyo: str = ""):
    """(ruta, ya estaba). Un nombre que ya existe solo es «el mismo PDF» si
    tiene las mismas hojas. Si es el PDF que esta misma factura ya tenía
    (`suyo`, del registro) con otras hojas (se le unió la que faltaba), se
    sustituye. Si es de otra, se busca « (2)», « (3)»…"""
    raiz, ext = os.path.splitext(nombre)
    suyo = os.path.normcase(os.path.abspath(suyo)) if suyo else ""
    n = 1
    while True:
        candidato = os.path.join(carpeta, nombre if n == 1 else f"{raiz} ({n}){ext}")
        clave = os.path.normcase(os.path.abspath(candidato))
        if clave not in reservados:
            if not os.path.exists(candidato):
                return candidato, False
            if _misma_que(candidato, hojas):
                return candidato, True
            if clave == suyo:
                return candidato, False
        n += 1


def _a_la_papelera(ruta: str, base: str) -> bool:
    """El PDF viejo de una factura que se rehace no se borra: a _Papelera."""
    papelera = os.path.join(base, archivo.PAPELERA)
    raiz, ext = os.path.splitext(os.path.basename(ruta))
    destino, n = os.path.join(papelera, raiz + ext), 2
    while os.path.exists(destino):
        destino = os.path.join(papelera, f"{raiz}_{n}{ext}")
        n += 1
    try:
        os.makedirs(papelera, exist_ok=True)
        shutil.move(ruta, destino)
        return True
    except OSError:
        return False


def _dentro(ruta: str, base: str) -> bool:
    ruta = os.path.normcase(os.path.abspath(ruta))
    base = os.path.normcase(os.path.abspath(base))
    return ruta.startswith(base + os.sep)


def separar(facturas_por_tipo: Dict[str, Iterable], base: str,
            cliente: str, nif: str, pdf_previo=None, progreso=None) -> dict:
    """Crea un PDF por factura y aparta los tacos originales.

    `pdf_previo(tipo, factura)` dice qué PDF tenía ya esa factura (del
    registro), para rehacerlo en su sitio en vez de dejar dos.
    `progreso(hechas, total)`, si se da, se llama con cada factura: se puede
    llamar desde un hilo aparte (ver ventana_archivo.archivar_exportacion).

    Devuelve {"creados": [...], "ya_estaban": n, "sin_paginas": [...],
    "tacos": {ruta vieja: ruta nueva}, "afectados": {(ejercicio)},
    "pdfs": [(tipo, factura, ruta del PDF)]} (también los que ya estaban).
    """
    import fitz

    creados, sin_paginas, ya_estaban, pdfs = [], [], 0, []
    usados: set = set()
    reservados: set = set()     # los PDF que ya tienen dueño en esta pasada
    afectados = set()
    abiertos: Dict[str, "fitz.Document"] = {}
    documentos = _documentos(facturas_por_tipo)
    try:
        for hechas, (tipo, f) in enumerate(documentos.values()):
            if progreso:
                progreso(hechas, len(documentos))
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
            # PyMuPDF no admite dos hilos a la vez (ver pdf.CERROJO): el
            # cerrojo se coge factura a factura, así el visor y la lectura
            # no se quedan esperando a que se separe el taco entero.
            with CERROJO:
                nuevo = fitz.open()
                for origen, pagina in paginas:
                    if origen.lower().endswith(".pdf"):
                        if origen not in abiertos:
                            abiertos[origen] = fitz.open(origen)
                        fuente = abiertos[origen]
                        if 1 <= pagina <= fuente.page_count:
                            nuevo.insert_pdf(fuente, from_page=pagina - 1,
                                             to_page=pagina - 1)
                    else:
                        with fitz.open(origen) as imagen:
                            nuevo.insert_pdf(fitz.open("pdf", imagen.convert_to_pdf()))
                if not nuevo.page_count:
                    nuevo.close()
                    sin_paginas.append(f.num_factura or f.nombre or "?")
                    continue
                hojas = _Hojas(nuevo)
                suyo = (pdf_previo(tipo, f) if pdf_previo else "") or ""
                destino, ya_estaba = _destino(carpeta, nombre_factura(f), hojas,
                                              reservados, suyo)
                if not ya_estaba and os.path.exists(destino) \
                        and not _a_la_papelera(destino, base):
                    # El viejo está abierto en otro programa: no se pisa.
                    destino, ya_estaba = _destino(carpeta, nombre_factura(f),
                                                  hojas, reservados)
                reservados.add(os.path.normcase(os.path.abspath(destino)))
                if ya_estaba:
                    nuevo.close()
                    ya_estaban += 1
                    pdfs.append((tipo, f, destino))
                    continue
                temporal = destino + ".tmp"
                nuevo.save(temporal, garbage=3, deflate=True)
                nuevo.close()
            os.replace(temporal, destino)
            creados.append(destino)
            pdfs.append((tipo, f, destino))
            afectados.add(ejercicio)
            usados.update(o for o, _ in paginas)
        if progreso:
            progreso(len(documentos), len(documentos))
    finally:
        with CERROJO:
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
            "sin_paginas": sin_paginas, "tacos": tacos, "afectados": afectados,
            "pdfs": pdfs}
