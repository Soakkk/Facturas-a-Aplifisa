import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QApplication

from facturas_excel.app import (
    C_ESTADO, VentanaPrincipal, VisorClicable, _argumentos,
    parse_numero, rutas_factura_de_mime,
)
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
    rutas = [os.path.normpath(ruta) for ruta in rutas_factura_de_mime(mime)]
    assert rutas == [os.path.normpath(str(pdf))]


def test_la_rueda_del_raton_no_cambia_gasto_venta():
    # Bajando por el listado con la rueda, al pasar por encima del desplegable
    # se cambiaba gasto<->venta en silencio. Solo debe cambiarse con un clic.
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from facturas_excel.app import C_TIPO

    v = VentanaPrincipal(comprobar_updates=False)
    v._anadir_fila(b"", Factura(
        num_factura="F-1", fecha="16/07/2026", nombre="Proveedor",
        nif="B30048276", concepto="600", base_iva=100, pct_iva=21,
        cuota_iva=21, total_impreso=121,
    ), "gasto", "600", None, "")

    def rueda(w):
        for _ in range(3):
            _app.sendEvent(w, QWheelEvent(
                QPointF(5, 5), w.mapToGlobal(QPoint(5, 5)), QPoint(0, -40),
                QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                Qt.ScrollUpdate, False))

    combo = v.tabla.cellWidget(0, C_TIPO)
    rueda(combo)
    assert combo.currentData() == "gasto"

    combo.setCurrentIndex(combo.findData("venta"))      # elegirlo a mano si funciona
    assert combo.currentData() == "venta"


def test_eliminar_y_deshacer_una_factura():
    v = VentanaPrincipal(comprobar_updates=False)
    v._anadir_fila(b"", Factura(
        num_factura="F-1", fecha="16/07/2026", nombre="Proveedor",
        nif="B30048276", concepto="600", base_iva=100, pct_iva=21,
        cuota_iva=21, total_impreso=121,
    ), "gasto", "600", None, "")
    v.tabla.selectRow(0)
    v._eliminar_seleccion()
    assert v.tabla.rowCount() == 0
    assert v.btn_deshacer_borrado.isEnabled()
    v._deshacer_borrado()
    assert v.tabla.rowCount() == 1
    assert v._tipo_fila(0) == "gasto"


def test_insertar_filas_es_atomico_y_marca_duplicados():
    from facturas_excel.validacion import ERROR
    from facturas_excel.app import ICONO_ESTADO

    v = VentanaPrincipal(comprobar_updates=False)
    for _ in range(2):
        v._anadir_fila(b"", Factura(
            num_factura="F-1", fecha="16/07/2026", nombre="Proveedor",
            nif="B12345678", concepto="628", base_iva=100,
            pct_iva=21, cuota_iva=21, total_impreso=121,
        ), "gasto", "628", "G17", "")
    v._revalidar_todo()
    # Duplicado = rojo y alerta arriba: importarlo lo paga dos veces.
    celda = v.tabla.item(1, C_ESTADO)
    assert "FACTURA DUPLICADA" in celda.toolTip()
    assert celda.text() == ICONO_ESTADO[ERROR]
    assert not v.alerta.isHidden()
    assert "revisar" in v.lbl_alerta_titulo.text()
    assert "repetida" in v.lbl_alerta_texto.text()


def test_el_suplido_es_una_linea_de_base_sin_iva():
    """Como lo registra Aplifisa: una segunda linea de base, sin % ni cuota.

    Lo enseño el usuario con su pantalla delante (2026-09-02): el suplido no va
    en la columna Suplidos, va como otra base imponible del mismo apunte.
    """
    from facturas_excel.app import C_BASE, C_CUOTA, C_PCT
    v = VentanaPrincipal(comprobar_updates=False)
    suplido = Factura(
        num_factura="F-1", fecha="16/07/2026", nombre="Proveedor",
        nif="B30048276", concepto="623", base_iva=109.08, total_impreso=230.08)
    suplido.es_suplido = True
    v._anadir_fila(b"", suplido, "gasto", "623", "G19", "")

    assert v.tabla.item(0, C_BASE).text() == "109,08"
    assert v.tabla.item(0, C_PCT).text() == ""
    assert v.tabla.item(0, C_CUOTA).text() == ""
    assert "SUPLIDO" in v.tabla.item(0, C_BASE).toolTip()


def test_el_documento_original_es_clicable_y_abre_la_vista_grande(monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtTest import QSignalSpy, QTest
    from PySide6.QtWidgets import QDialog

    v = VentanaPrincipal(comprobar_updates=False)
    assert isinstance(v.lbl_img, VisorClicable)
    spy = QSignalSpy(v.lbl_img.clicked)
    abiertos = []
    monkeypatch.setattr(QDialog, "exec", lambda dialog: abiertos.append(dialog.size()))
    v._pixmap_documento = QPixmap(600, 900)

    QTest.mouseClick(v.lbl_img, Qt.LeftButton)

    assert spy.count() == 1
    assert abiertos and abiertos[0].width() > 600


def test_una_factura_con_varios_tipos_de_iva_no_es_un_duplicado():
    # Son varias filas con el mismo nº y NIF: si dos lineas tuvieran la misma
    # base se marcaban como duplicadas sin serlo.
    v = VentanaPrincipal(comprobar_updates=False)
    for pct, cuota in ((21, 21), (10, 10)):
        v._anadir_fila(b"", Factura(
            num_factura="F-2", fecha="16/07/2026", nombre="Proveedor",
            nif="B12345678", concepto="600", base_iva=100,
            pct_iva=pct, cuota_iva=cuota, total_impreso=231, lineas_factura=2,
        ), "gasto", "600", None, "")
    v._revalidar_todo()
    assert v._duplicados == {}
    assert v.alerta.isHidden()


def test_barra_rapida_y_acciones_se_adaptan_a_portatiles():
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    assert v.minimumWidth() == 1024
    assert v.barra_rapida.parentWidget() is not None
    assert [v.btn_cargar.text(), v.btn_escanear.text(), v.btn_vaciar.text(),
            v.btn_gastos.text()] == [
        "Abrir PDF", "Escanear", "Vaciar todo", "Exportar a Aplifisa"]
    acciones = [accion.text() for accion in v.menu_acciones.actions()]
    assert "Vaciar todo" not in acciones
    assert "Quitar bloque" in acciones
    assert "Eliminar selección" in acciones
