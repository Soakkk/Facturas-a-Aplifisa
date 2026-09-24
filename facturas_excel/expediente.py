"""Expediente de un cliente y ejercicio: todo lo suyo, junto y ordenado.

    Nombre — NIF / 2026 / Expediente 2026 /
        Gastos 2026.pdf      todas las facturas recibidas en un solo PDF,
                             con una página de índice y un marcador por archivo
        Ingresos 2026.pdf    lo mismo con las emitidas
        Resumen 2026.pdf     documentos, páginas y las facturas exportadas a
                             Aplifisa con sus totales (base, IVA, retención)
        Excel Aplifisa/      copia de los Excel exportados
    Nombre — NIF / Expediente 2026.zip   todo lo anterior para adjuntar

El expediente se GENERA a partir de las carpetas Gastos, Ingresos y Excel
Aplifisa: los originales no se tocan nunca, y se puede rehacer cuantas veces
haga falta (tras recoger sueltos o tras cada exportación, lo hace solo).
"""

from __future__ import annotations

import html
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from . import historial, identidad_archivo
from .recoger import CARPETA_EXCEL

TIPOS = (("Gastos", "Gastos"), ("Ingresos", "Ingresos"))


@dataclass
class Ejercicio:
    carpeta_cliente: str       # nombre de la carpeta del cliente
    nombre: str
    nif: str
    ejercicio: int
    documentos: int

    @property
    def etiqueta(self) -> str:
        return f"{self.nombre} — {self.ejercicio} ({self.documentos} documento(s))"


def carpeta_expediente(base: str, carpeta_cliente: str, ejercicio: int) -> str:
    return os.path.join(base, carpeta_cliente, str(int(ejercicio)),
                        f"Expediente {int(ejercicio)}")


def _pdfs(carpeta: str) -> List[str]:
    if not os.path.isdir(carpeta):
        return []
    return sorted((os.path.join(carpeta, n) for n in os.listdir(carpeta)
                   if n.lower().endswith(".pdf")),
                  key=lambda r: (os.path.getmtime(r), os.path.basename(r).lower()))


def listar(base: str) -> List[Ejercicio]:
    """Clientes y ejercicios del archivo que tienen documentos."""
    try:
        indice = {f["carpeta"]: (nif, f["nombre"])
                  for nif, f in identidad_archivo.leer(base).items()}
    except (OSError, ValueError):
        indice = {}
    salida = []
    if not os.path.isdir(base):
        return salida
    for carpeta in sorted(os.listdir(base)):
        ruta = os.path.join(base, carpeta)
        if not os.path.isdir(ruta) or carpeta.startswith(("_", ".")) \
                or carpeta == "Sin identificar":
            continue
        nif, nombre = indice.get(carpeta, ("", carpeta))
        for ano in sorted(os.listdir(ruta)):
            if not (ano.isdigit() and len(ano) == 4):
                continue
            n = sum(len(_pdfs(os.path.join(ruta, ano, t))) for t, _ in TIPOS)
            n += len([x for x in os.listdir(os.path.join(ruta, ano, CARPETA_EXCEL))
                      if x.lower().endswith(".xlsx")]) \
                if os.path.isdir(os.path.join(ruta, ano, CARPETA_EXCEL)) else 0
            if n:
                salida.append(Ejercicio(carpeta, nombre, nif, int(ano), n))
    return salida


FILAS_POR_PAGINA_INDICE = 50


def _unir(pdfs: List[str], destino: str, titulo: str) -> int:
    """Un PDF con índice y un marcador por archivo. Devuelve sus páginas."""
    import fitz
    # 1º cuántas páginas tiene cada uno, para saber cuántas ocupa el índice.
    abiertos = []
    for ruta in pdfs:
        try:
            abiertos.append((ruta, fitz.open(ruta)))
        except Exception:
            abiertos.append((ruta, None))
    hojas_indice = max(1, -(-len(abiertos) // FILAS_POR_PAGINA_INDICE))
    salida = fitz.open()
    for _ in range(hojas_indice):
        salida.new_page(width=595, height=842)
    marcadores = [[1, "Índice", 1]]
    filas = []
    try:
        for ruta, doc in abiertos:
            nombre = os.path.basename(ruta)
            if doc is None:
                filas.append((nombre, None, "no se pudo abrir"))
                continue
            inicio = salida.page_count + 1
            salida.insert_pdf(doc)
            marcadores.append([1, nombre, inicio])
            filas.append((nombre, inicio, f"{doc.page_count} pág."))
    finally:
        for _ruta, doc in abiertos:
            if doc is not None:
                doc.close()
    for n in range(hojas_indice):
        pagina = salida[n]
        y = 60
        if n == 0:
            pagina.insert_text((50, y), titulo, fontsize=15, fontname="helv")
            y += 20
            pagina.insert_text(
                (50, y), f"{len(pdfs)} documento(s) · generado el "
                f"{datetime.now():%d/%m/%Y %H:%M}", fontsize=9, fontname="helv")
            y += 24
        tramo = filas[n * FILAS_POR_PAGINA_INDICE:(n + 1) * FILAS_POR_PAGINA_INDICE]
        for nombre, inicio, detalle in tramo:
            pagina.insert_text((50, y), nombre[:72], fontsize=9, fontname="helv")
            pagina.insert_text(
                (440, y), f"pág. {inicio}  ({detalle})" if inicio else detalle,
                fontsize=9, fontname="helv")
            y += 14
    salida.set_toc(marcadores)
    temporal = destino + ".tmp"
    salida.save(temporal, garbage=3, deflate=True)
    paginas = salida.page_count
    salida.close()
    os.replace(temporal, destino)
    return paginas


def _html_resumen(e: Ejercicio, documentos: dict, facturas: list) -> str:
    def eur(v):
        texto = f"{float(v or 0):,.2f}"
        return texto.replace(",", "X").replace(".", ",").replace("X", ".") + " €"

    partes = [f"<h2 style='color:#1F3550'>Expediente {e.ejercicio} · "
              f"{html.escape(e.nombre)}</h2>",
              f"<p>NIF {html.escape(e.nif or '—')} · generado el "
              f"{datetime.now():%d/%m/%Y %H:%M}</p>",
              "<h3>Documentación</h3><table border='1' cellspacing='0' "
              "cellpadding='4' width='100%'><tr><th align='left'>Tipo</th>"
              "<th>Documentos</th><th>Páginas</th><th align='left'>Archivo</th></tr>"]
    for tipo, (n, paginas, archivo) in documentos.items():
        partes.append(f"<tr><td>{tipo}</td><td align='right'>{n}</td>"
                      f"<td align='right'>{paginas}</td>"
                      f"<td>{html.escape(archivo or '—')}</td></tr>")
    partes.append("</table>")
    if not facturas:
        partes.append("<p><i>No hay facturas de este ejercicio exportadas a "
                      "Aplifisa desde el programa (o se exportaron antes de la "
                      "versión 1.14).</i></p>")
        return "".join(partes)
    for tipo, titulo in (("gasto", "Gastos exportados a Aplifisa"),
                         ("venta", "Ingresos exportados a Aplifisa")):
        filas = [f for f in facturas if f.get("tipo") == tipo]
        if not filas:
            continue
        suma = {k: round(sum(float(f.get(k) or 0) for f in filas), 2)
                for k in ("base", "cuota_iva", "cuota_requiv", "cuota_irpf", "total")}
        partes.append(
            f"<h3>{titulo}: {len(filas)} factura(s)</h3>"
            "<table border='1' cellspacing='0' cellpadding='3' width='100%'>"
            "<tr><th align='left'>Fecha</th><th align='left'>Nº</th>"
            "<th align='left'>Nombre</th><th>Base</th><th>IVA</th>"
            "<th>Recargo</th><th>Retención</th><th>Total</th></tr>")
        for f in filas:
            partes.append(
                f"<tr><td>{html.escape(str(f.get('fecha') or ''))}</td>"
                f"<td>{html.escape(str(f.get('num_factura') or ''))}</td>"
                f"<td>{html.escape(str(f.get('nombre') or ''))}</td>"
                f"<td align='right'>{eur(f.get('base'))}</td>"
                f"<td align='right'>{eur(f.get('cuota_iva'))}</td>"
                f"<td align='right'>{eur(f.get('cuota_requiv'))}</td>"
                f"<td align='right'>{eur(f.get('cuota_irpf'))}</td>"
                f"<td align='right'>{eur(f.get('total'))}</td></tr>")
        partes.append(
            f"<tr><td colspan='3'><b>TOTAL</b></td>"
            f"<td align='right'><b>{eur(suma['base'])}</b></td>"
            f"<td align='right'><b>{eur(suma['cuota_iva'])}</b></td>"
            f"<td align='right'><b>{eur(suma['cuota_requiv'])}</b></td>"
            f"<td align='right'><b>{eur(suma['cuota_irpf'])}</b></td>"
            f"<td align='right'><b>{eur(suma['total'])}</b></td></tr></table>")
    return "".join(partes)


def _pdf_desde_html(contenido: str, destino: str) -> None:
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
    documento = QTextDocument()
    documento.setHtml(contenido)
    temporal = destino + ".tmp.pdf"
    escritor = QPdfWriter(temporal)
    escritor.setResolution(150)
    escritor.setPageSize(QPageSize(QPageSize.A4))
    escritor.setPageOrientation(QPageLayout.Landscape)
    documento.print_(escritor)
    del escritor
    os.replace(temporal, destino)


def crear(base: str, e: Ejercicio, con_zip: bool = True) -> dict:
    """Genera (o rehace) el expediente. Devuelve rutas y recuentos."""
    origen = os.path.join(base, e.carpeta_cliente, str(e.ejercicio))
    if not os.path.isdir(origen):
        raise ValueError(f"No existe el ejercicio {e.ejercicio} de {e.nombre}.")
    destino = carpeta_expediente(base, e.carpeta_cliente, e.ejercicio)
    # Se genera aparte y se cambia de golpe: nunca queda un expediente a medias.
    trabajo = tempfile.mkdtemp(prefix=".expediente-", dir=os.path.dirname(destino))
    try:
        documentos = {}
        for carpeta, titulo in TIPOS:
            pdfs = _pdfs(os.path.join(origen, carpeta))
            if not pdfs:
                documentos[titulo] = (0, 0, "")
                continue
            nombre = f"{titulo} {e.ejercicio}.pdf"
            paginas = _unir(pdfs, os.path.join(trabajo, nombre),
                            f"{titulo} {e.ejercicio} · {e.nombre}")
            documentos[titulo] = (len(pdfs), paginas, nombre)
        excel_origen = os.path.join(origen, CARPETA_EXCEL)
        excels = []
        if os.path.isdir(excel_origen):
            os.makedirs(os.path.join(trabajo, CARPETA_EXCEL), exist_ok=True)
            for nombre in sorted(os.listdir(excel_origen)):
                if nombre.lower().endswith(".xlsx"):
                    shutil.copy2(os.path.join(excel_origen, nombre),
                                 os.path.join(trabajo, CARPETA_EXCEL, nombre))
                    excels.append(nombre)
        documentos["Excel Aplifisa"] = (len(excels), 0, ", ".join(excels))
        facturas = historial.del_ejercicio(e.nif, e.ejercicio, e.nombre)
        resumen = f"Resumen {e.ejercicio}.pdf"
        _pdf_desde_html(_html_resumen(e, documentos, facturas),
                        os.path.join(trabajo, resumen))
        viejo = destino + ".anterior"
        if os.path.isdir(destino):
            if os.path.isdir(viejo):
                shutil.rmtree(viejo, ignore_errors=True)
            os.replace(destino, viejo)
        os.replace(trabajo, destino)
        shutil.rmtree(viejo, ignore_errors=True)
    except Exception:
        shutil.rmtree(trabajo, ignore_errors=True)
        raise
    zip_ruta = ""
    if con_zip:
        zip_ruta = os.path.join(base, e.carpeta_cliente,
                                f"Expediente {e.ejercicio}.zip")
        temporal = zip_ruta + ".tmp"
        with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for raiz, _carpetas, archivos in os.walk(destino):
                for nombre in sorted(archivos):
                    ruta = os.path.join(raiz, nombre)
                    z.write(ruta, os.path.relpath(ruta, os.path.dirname(destino)))
        os.replace(temporal, zip_ruta)
    return {"carpeta": destino, "zip": zip_ruta, "documentos": documentos,
            "facturas": len(facturas)}


def buscar(base: str, nif: str = "", nombre: str = "",
           ejercicio: Optional[int] = None) -> Optional[Ejercicio]:
    """El ejercicio de ese cliente (por NIF, o por nombre si no hay NIF)."""
    from .clientes import _normaliza
    nif = _normaliza(nif)
    for e in listar(base):
        if ejercicio is not None and e.ejercicio != int(ejercicio):
            continue
        if (nif and _normaliza(e.nif) == nif) or (not nif and nombre
                                                  and e.nombre == nombre):
            return e
    return None


def guardar_excel_exportado(base: str, ruta_excel: str, nombre: str, nif: str,
                            ejercicio: int, tipo: str) -> str:
    """Copia fechada del Excel exportado dentro del archivo del cliente."""
    from . import archivo
    carpeta_tipo = archivo.carpeta_tipo_cliente(nombre, ejercicio, tipo, base, nif=nif)
    carpeta = os.path.join(os.path.dirname(carpeta_tipo), CARPETA_EXCEL)
    os.makedirs(carpeta, exist_ok=True)
    etiqueta = "INGRESOS" if str(tipo).lower().startswith(("i", "v")) else "GASTOS"
    destino = os.path.join(carpeta, f"{etiqueta} {ejercicio} {datetime.now():%Y-%m-%d %H%M%S}.xlsx")
    shutil.copy2(ruta_excel, destino)
    return destino
