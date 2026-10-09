"""Exportar sin dejar la ventana parada (taco de 450 hojas, 800 líneas).

Antes, con 800 líneas, la ventana se quedaba 19 s sin responder al exportar:
casi todo era el archivo del cliente (un PDF por factura y el expediente).
Aquí se comprueba que lo que lo hace más rápido no cambia lo que se guarda.
Solo datos inventados.
"""
import os
import zipfile

import fitz
from PySide6.QtWidgets import QApplication

from facturas_excel import archivo, expediente

_app = QApplication.instance() or QApplication([])

CLIENTE = ("TALLERES PRUEBA SL", "B12345674")


def _hoja_escaneada(doc, semilla):
    """Una hoja como las del escáner: una foto JPEG que ocupa la página."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 170), False)
    pix.set_rect(pix.irect, ((semilla * 37) % 256, (semilla * 91) % 256, 200))
    pix.set_rect(fitz.IRect(10, 10 + semilla % 100, 110, 30 + semilla % 100),
                 (20, 20, 20))
    pagina = doc.new_page(width=595, height=842)
    pagina.insert_image(pagina.rect, stream=pix.tobytes("jpeg"))
    return pagina


def _pdf_escaneado(ruta, semillas):
    doc = fitz.open()
    for s in semillas:
        _hoja_escaneada(doc, s)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    doc.save(ruta)
    doc.close()
    return ruta


def _archivo_con_facturas(base, n_gastos=3, n_ingresos=2):
    gastos = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "gastos", base, nif=CLIENTE[1])
    ingresos = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "ingresos", base, nif=CLIENTE[1])
    for i in range(n_gastos):
        _pdf_escaneado(os.path.join(gastos, f"2026-02-{i + 10} PROVEEDOR G-{i}.pdf"), [i])
    for i in range(n_ingresos):
        _pdf_escaneado(os.path.join(ingresos, f"2026-03-{i + 10} CLIENTE V-{i}.pdf"),
                       [50 + i])
    excel = os.path.join(os.path.dirname(gastos), "Excel Aplifisa")
    os.makedirs(excel, exist_ok=True)
    from openpyxl import Workbook
    libro = Workbook()
    libro.active.append(["10/02/2026", "G-0", 100])
    libro.save(os.path.join(excel, "GASTOS 2026 2026-03-31 101010.xlsx"))
    [e] = expediente.listar(base)
    return e


# ---------------------------------------------------------------- 1. ZIP
def test_el_zip_del_expediente_guarda_los_pdf_y_excel_sin_recomprimir(tmp_path):
    """Los PDF son fotos JPEG y el .xlsx ya es un ZIP: comprimirlos otra vez
    costaba 9 s con 450 hojas y no ahorraba casi nada."""
    base = str(tmp_path / "archivo")
    e = _archivo_con_facturas(base)
    r = expediente.crear(base, e)

    carpeta = os.path.dirname(r["carpeta"])
    with zipfile.ZipFile(r["zip"]) as z:
        assert z.testzip() is None
        entradas = z.infolist()
        assert sorted(i.filename for i in entradas) == [
            "Expediente 2026/Excel Aplifisa/GASTOS 2026 2026-03-31 101010.xlsx",
            "Expediente 2026/Gastos 2026.pdf",
            "Expediente 2026/Ingresos 2026.pdf",
            "Expediente 2026/Resumen 2026.pdf"]
        for info in entradas:
            assert info.compress_type == zipfile.ZIP_STORED, info.filename
            # Lo que va dentro es exactamente lo que hay en la carpeta.
            with open(os.path.join(carpeta, info.filename), "rb") as fh:
                assert z.read(info) == fh.read()
