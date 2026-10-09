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

import hashlib
import html
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from . import identidad_archivo, registro_facturas
from .pdf import CERROJO
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
                  # Las facturas separadas empiezan por su fecha
                  # (2026-02-12 …): por nombre quedan en orden cronológico.
                  key=lambda r: os.path.basename(r).lower())


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
    """Un PDF con índice y un marcador por archivo. Devuelve sus páginas.

    El expediente se puede hacer en un hilo aparte mientras el visor dibuja
    una hoja, y PyMuPDF no admite dos hilos a la vez (ver pdf.CERROJO): el
    cerrojo se coge archivo a archivo, no durante todo el expediente."""
    import fitz
    # 1º cuántas páginas tiene cada uno, para saber cuántas ocupa el índice.
    abiertos = []
    for ruta in pdfs:
        try:
            with CERROJO:
                abiertos.append((ruta, fitz.open(ruta)))
        except Exception:
            abiertos.append((ruta, None))
    hojas_indice = max(1, -(-len(abiertos) // FILAS_POR_PAGINA_INDICE))
    with CERROJO:
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
            with CERROJO:
                inicio = salida.page_count + 1
                salida.insert_pdf(doc)
                marcadores.append([1, nombre, inicio])
                filas.append((nombre, inicio, f"{doc.page_count} pág."))
    finally:
        for _ruta, doc in abiertos:
            if doc is not None:
                with CERROJO:
                    doc.close()
    for n in range(hojas_indice):
        with CERROJO:
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
    temporal = destino + ".tmp"
    with CERROJO:
        salida.set_toc(marcadores)
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
    exportadas = [f for f in facturas if f.get("exportada_en")]
    otras = [f for f in facturas if not f.get("exportada_en")]
    if not exportadas:
        partes.append("<p><i>No hay facturas de este ejercicio exportadas a "
                      "Aplifisa desde el programa (o se exportaron antes de la "
                      "versión 1.14).</i></p>")
    for tipo, titulo in (("gasto", "Gastos exportados a Aplifisa"),
                         ("venta", "Ingresos exportados a Aplifisa")):
        filas = [f for f in exportadas if f.get("tipo") == tipo]
        if not filas:
            continue
        suma = {k: round(sum(float(f.get(k) or 0) for f in filas), 2)
                for k in ("base", "cuota_iva", "cuota_requiv", "cuota_irpf", "total")}
        partes.append(
            f"<h3>{titulo}: {len(filas)} factura(s)</h3>"
            "<table border='1' cellspacing='0' cellpadding='3' width='100%'>"
            "<tr><th align='left'>Fecha</th><th align='left'>Nº</th>"
            "<th align='left'>Nombre</th><th>Base</th><th>IVA</th>"
            "<th>Recargo</th><th>Retención</th><th>Total</th>"
            "<th align='left'>PDF</th></tr>")
        for f in filas:
            partes.append(
                f"<tr><td>{html.escape(str(f.get('fecha') or ''))}</td>"
                f"<td>{html.escape(str(f.get('num_factura') or ''))}</td>"
                f"<td>{html.escape(str(f.get('nombre') or ''))}</td>"
                f"<td align='right'>{eur(f.get('base'))}</td>"
                f"<td align='right'>{eur(f.get('cuota_iva'))}</td>"
                f"<td align='right'>{eur(f.get('cuota_requiv'))}</td>"
                f"<td align='right'>{eur(f.get('cuota_irpf'))}</td>"
                f"<td align='right'>{eur(f.get('total'))}</td>"
                f"<td>{html.escape(os.path.basename(f.get('pdf') or '') or '—')}</td></tr>")
        partes.append(
            f"<tr><td colspan='3'><b>TOTAL</b></td>"
            f"<td align='right'><b>{eur(suma['base'])}</b></td>"
            f"<td align='right'><b>{eur(suma['cuota_iva'])}</b></td>"
            f"<td align='right'><b>{eur(suma['cuota_requiv'])}</b></td>"
            f"<td align='right'><b>{eur(suma['cuota_irpf'])}</b></td>"
            f"<td align='right'><b>{eur(suma['total'])}</b></td><td></td></tr></table>")
    if otras:
        # Las que tienen su PDF pero no salieron en el Excel: apartadas por
        # versiones anteriores (gestión manual) o con la exportación deshecha.
        partes.append(
            f"<h3>Archivadas sin exportar a Aplifisa: {len(otras)}</h3>"
            "<p>Apartadas en versiones anteriores o con la exportación "
            "deshecha. Tienen su PDF, pero no van en el Excel.</p>"
            "<table border='1' cellspacing='0' cellpadding='3' width='100%'>"
            "<tr><th align='left'>Tipo</th><th align='left'>Fecha</th>"
            "<th align='left'>Nº</th><th align='left'>Nombre</th><th>Total</th>"
            "<th align='left'>PDF</th></tr>")
        for f in otras:
            partes.append(
                f"<tr><td>{'Ingreso' if f.get('tipo') == 'venta' else 'Gasto'}</td>"
                f"<td>{html.escape(str(f.get('fecha') or ''))}</td>"
                f"<td>{html.escape(str(f.get('num_factura') or ''))}</td>"
                f"<td>{html.escape(str(f.get('nombre') or ''))}</td>"
                f"<td align='right'>{eur(f.get('total'))}</td>"
                f"<td>{html.escape(os.path.basename(f.get('pdf') or '') or '—')}</td></tr>")
        partes.append("</table>")
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


# Los PDF son fotos JPEG (y lo demás ya va comprimido dentro del PDF) y un
# .xlsx es ya un ZIP: comprimirlos otra vez no ahorra casi nada y era lo más
# lento del expediente (9 de 14 s con un taco de 450 hojas, con la ventana
# parada). Entran en el ZIP tal cual.
YA_COMPRIMIDOS = (".pdf", ".xlsx")


def _compresion_zip(nombre: str) -> int:
    if nombre.lower().endswith(YA_COMPRIMIDOS):
        return zipfile.ZIP_STORED
    return zipfile.ZIP_DEFLATED


# ------------------------------------------------- rehacer solo lo cambiado
# Cada exportación rehacía el expediente entero: unir otra vez todos los PDF
# del año (3 s con 450 hojas), el resumen y el ZIP. Se apunta lo que entró
# la última vez (nombre, tamaño y fecha de cada archivo, y lo que dice el
# registro) y lo que salió; si nada ha cambiado no se rehace, y si solo ha
# cambiado una parte (los ingresos), la otra (los gastos) se aprovecha.
# Se apunta en la base de datos del programa, no en la carpeta del cliente.

def _hechos():
    from .almacen import Coleccion
    from .rutas import dir_datos
    return Coleccion("expedientes", dir_datos())


def _clave_hecho(destino: str) -> str:
    return os.path.normcase(os.path.abspath(destino))


def _apuntar_hecho(destino: str, hecho: Optional[dict]) -> None:
    """Apunta (o con None, olvida) lo hecho. Es solo para ir más deprisa:
    si no se puede apuntar, la próxima vez se rehace todo, como antes."""
    try:
        if hecho is None:
            _hechos().borrar(_clave_hecho(destino))
        else:
            _hechos().guardar(_clave_hecho(destino), hecho)
    except Exception:
        pass


def _firma(*partes) -> str:
    return hashlib.sha1(repr(partes).encode("utf-8", "replace")).hexdigest()


def _firma_archivos(rutas: List[str]) -> list:
    salida = []
    for ruta in rutas:
        estado = os.stat(ruta)
        salida.append((os.path.basename(ruta), estado.st_size, estado.st_mtime_ns))
    return salida


def _estado_carpeta(carpeta: str) -> dict:
    """{ruta relativa: [tamaño, fecha]} de lo que hay en la carpeta."""
    salida = {}
    for raiz, _carpetas, archivos in os.walk(carpeta):
        for nombre in archivos:
            ruta = os.path.join(raiz, nombre)
            estado = os.stat(ruta)
            salida[os.path.relpath(ruta, carpeta).replace(os.sep, "/")] = [
                estado.st_size, estado.st_mtime_ns]
    return salida


def _estado_zip(zip_ruta: str):
    if not zip_ruta or not os.path.isfile(zip_ruta):
        return None
    estado = os.stat(zip_ruta)
    return [estado.st_size, estado.st_mtime_ns]


def _hecho_antes(destino: str, zip_ruta: str) -> Optional[dict]:
    """Lo apuntado la última vez, si la carpeta (y el ZIP, si se pide) siguen
    exactamente como quedaron. Si alguien ha tocado algo, no vale."""
    try:
        hecho = _hechos().leer(_clave_hecho(destino))
        if not isinstance(hecho, dict) or not os.path.isdir(destino):
            return None
        if _estado_carpeta(destino) != hecho.get("carpeta"):
            return None
        if zip_ruta and _estado_zip(zip_ruta) != hecho.get("zip"):
            return None
        return hecho
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _aprovechar(desde: str, hasta: str) -> bool:
    """Mueve el PDF unido que no ha cambiado al expediente nuevo. Si no se
    puede (abierto en otro programa), se vuelve a unir."""
    try:
        os.replace(desde, hasta)
        return True
    except OSError:
        return False


def crear(base: str, e: Ejercicio, con_zip: bool = True) -> dict:
    """Genera (o rehace) el expediente. Devuelve rutas y recuentos.

    Solo rehace lo que ha cambiado desde la última vez (ver `_hecho_antes`)."""
    origen = os.path.join(base, e.carpeta_cliente, str(e.ejercicio))
    if not os.path.isdir(origen):
        raise ValueError(f"No existe el ejercicio {e.ejercicio} de {e.nombre}.")
    destino = carpeta_expediente(base, e.carpeta_cliente, e.ejercicio)
    zip_ruta = (os.path.join(base, e.carpeta_cliente, f"Expediente {e.ejercicio}.zip")
                if con_zip else "")
    # Lo que va a entrar: los PDF de cada tipo, los Excel y lo del registro.
    partes = {}
    for carpeta, titulo in TIPOS:
        pdfs = _pdfs(os.path.join(origen, carpeta))
        indice = f"{titulo} {e.ejercicio} · {e.nombre}"
        partes[titulo] = (pdfs, indice, _firma(indice, _firma_archivos(pdfs)))
    excel_origen = os.path.join(origen, CARPETA_EXCEL)
    excels = (sorted(n for n in os.listdir(excel_origen) if n.lower().endswith(".xlsx"))
              if os.path.isdir(excel_origen) else [])
    # Del registro de facturas: lo exportado y lo archivado sin exportar.
    facturas = registro_facturas.del_ejercicio(
        e.nif, e.ejercicio, e.nombre, solo_exportadas=False)
    firma = _firma({t: p[2] for t, p in partes.items()},
                   _firma_archivos([os.path.join(excel_origen, n) for n in excels]),
                   e.nombre, e.nif, facturas)
    anterior = _hecho_antes(destino, zip_ruta) or {}
    exportadas = sum(1 for f in facturas if f.get("exportada_en"))
    if anterior.get("firma") == firma:
        return {"carpeta": destino, "zip": zip_ruta,
                "documentos": {t: tuple(v) for t, v in anterior["documentos"].items()},
                "facturas": exportadas}
    hechas_antes = anterior.get("partes", {})
    # Se genera aparte y se cambia de golpe: nunca queda un expediente a medias.
    trabajo = tempfile.mkdtemp(prefix=".expediente-", dir=os.path.dirname(destino))
    viejo = destino + ".anterior"
    aprovechados = []          # PDF unidos que no han cambiado: se mueven
    try:
        documentos, hechas = {}, {}
        for titulo, (pdfs, indice, firma_parte) in partes.items():
            if not pdfs:
                documentos[titulo] = (0, 0, "")
                continue
            nombre = f"{titulo} {e.ejercicio}.pdf"
            antes = hechas_antes.get(titulo) or {}
            if antes.get("firma") == firma_parte and _aprovechar(
                    os.path.join(destino, nombre), os.path.join(trabajo, nombre)):
                aprovechados.append(nombre)
                paginas = antes["paginas"]
            else:
                paginas = _unir(pdfs, os.path.join(trabajo, nombre), indice)
            documentos[titulo] = (len(pdfs), paginas, nombre)
            hechas[titulo] = {"firma": firma_parte, "paginas": paginas}
        if os.path.isdir(excel_origen):
            os.makedirs(os.path.join(trabajo, CARPETA_EXCEL), exist_ok=True)
            for nombre in excels:
                shutil.copy2(os.path.join(excel_origen, nombre),
                             os.path.join(trabajo, CARPETA_EXCEL, nombre))
        documentos["Excel Aplifisa"] = (len(excels), 0, ", ".join(excels))
        resumen = f"Resumen {e.ejercicio}.pdf"
        _pdf_desde_html(_html_resumen(e, documentos, facturas),
                        os.path.join(trabajo, resumen))
        if os.path.isdir(destino):
            if os.path.isdir(viejo):
                shutil.rmtree(viejo, ignore_errors=True)
            os.replace(destino, viejo)
        os.replace(trabajo, destino)
        shutil.rmtree(viejo, ignore_errors=True)
    except Exception:
        # Lo aprovechado vuelve a su sitio: el expediente de antes queda entero.
        de_vuelta = destino if os.path.isdir(destino) else viejo
        for nombre in aprovechados:
            try:
                os.replace(os.path.join(trabajo, nombre), os.path.join(de_vuelta, nombre))
            except OSError:
                pass
        shutil.rmtree(trabajo, ignore_errors=True)
        raise
    # Antes de rehacer el ZIP se olvida lo apuntado: si se corta a medias, la
    # próxima vez se rehace todo.
    _apuntar_hecho(destino, None)
    if con_zip:
        temporal = zip_ruta + ".tmp"
        with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for raiz, _carpetas, archivos in os.walk(destino):
                for nombre in sorted(archivos):
                    ruta = os.path.join(raiz, nombre)
                    z.write(ruta, os.path.relpath(ruta, os.path.dirname(destino)),
                            compress_type=_compresion_zip(nombre))
        os.replace(temporal, zip_ruta)
    try:
        _apuntar_hecho(destino, {
            "firma": firma, "partes": hechas, "documentos": documentos,
            "carpeta": _estado_carpeta(destino), "zip": _estado_zip(zip_ruta)})
    except OSError:
        pass                 # sin apuntar, la próxima vez se rehace entero
    return {"carpeta": destino, "zip": zip_ruta, "documentos": documentos,
            "facturas": exportadas}


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
