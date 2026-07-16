import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QApplication

from facturas_excel.app import C_ESTADO, VentanaPrincipal, _argumentos, parse_numero, rutas_factura_de_mime
from facturas_excel.modelo import Factura

_app = QApplication.instance() or QApplication([])


def test_parse_numero_admite_formato_espanol():
    assert parse_numero("1.234,56 €") == 1234.56
    assert parse_numero("1.234") == 1234.0
    assert parse_numero("1234.56") == 1234.56
    assert parse_numero(21) == 21.0


def test_argumentos_recibe_pdf_del_escaner():
    args = _argumentos(["app", "--import", "lote uno.pdf", "lote-dos.pdf"])
    assert args.importar == ["lote uno.pdf", "lote-dos.pdf"]


def test_arrastre_filtra_archivos_no_compatibles(tmp_path):
    pdf = tmp_path / "facturas.pdf"
    txt = tmp_path / "notas.txt"
    pdf.write_bytes(b"%PDF")
    txt.write_text("no")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(pdf)), QUrl.fromLocalFile(str(txt))])
    assert rutas_factura_de_mime(mime) == [str(pdf)]


def test_insertar_filas_es_atomico_y_marca_duplicados():
    v = VentanaPrincipal(comprobar_updates=False)
    for _ in range(2):
        v._anadir_fila(b"", Factura(
            num_factura="F-1", fecha="16/07/2026", nombre="Proveedor",
            nif="B12345678", concepto="628", base_iva=100,
            pct_iva=21, cuota_iva=21, total_impreso=121,
        ), "gasto", "628", "G17", "")
    v._revalidar_todo()
    assert "Posible duplicado" in v.tabla.item(1, C_ESTADO).toolTip()
