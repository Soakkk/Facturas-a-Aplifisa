"""El acabado claro cambia la presentación, no los datos ni el exportador."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from facturas_excel.app import (
    C_BASE, C_BASE_RE, C_CUENTA, C_CUOTA_IRPF, C_CUOTA_RE, C_ESTADO, C_GXX,
    C_NIF, C_NOMBRE, C_PCT_RE, C_TOTAL, VentanaPrincipal,
)
from facturas_excel.estilo import ACCENT_FAINT, CARD, INK, aplicar_tema
from facturas_excel.modelo import Factura

_app = QApplication.instance() or QApplication([])


def ventana():
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for i, (tipo, nombre, fecha) in enumerate((
        ("gasto", "SUMINISTROS PRUEBA", "12/01/2026"),
        ("gasto", "OTRO PROVEEDOR PRUEBA", "04/02/2026"),
        ("venta", "CLIENTE PRUEBA", "15/03/2026"),
        ("gasto", "FUERA PRUEBA", "02/04/2026"),
    )):
        cuenta, concepto = ("600", "G01") if tipo == "gasto" else ("700", "I01")
        f = Factura(
            num_factura=f"F-{i}", nombre=nombre, nif="B12345674", fecha=fecha,
            base_iva=100, pct_iva=21, cuota_iva=21, total_impreso=121,
            concepto=cuenta, subclave=concepto,
        )
        v._anadir_fila(b"", f, tipo, cuenta, concepto, "", f"Parte {i + 1}")
    v._revalidar_todo()
    return v


def resumen(v, ambito, tipo):
    return next([v.tabla_resumen.item(r, c).text()
                 for c in range(v.tabla_resumen.columnCount())]
                for r in range(v.tabla_resumen.rowCount())
                if v.tabla_resumen.item(r, 0).text() == ambito
                and v.tabla_resumen.item(r, 1).text() == tipo)


def test_el_tema_fuerza_superficies_claras_y_texto_legible():
    anterior, paleta, fuente = _app.styleSheet(), _app.palette(), _app.font()
    try:
        aplicar_tema(_app)
        assert _app.palette().color(QPalette.Base).name() == CARD.lower()
        assert _app.palette().color(QPalette.Text).name() == INK.lower()
        assert "#071A3A" not in _app.styleSheet()
    finally:
        _app.setStyleSheet(anterior)
        _app.setPalette(paleta)
        _app.setFont(fuente)


def test_gastos_ingresos_filtran_sin_reclasificar_ni_alterar_lote():
    v = ventana()
    v.botones_tipo["venta"].click()
    assert [v.tabla.isRowHidden(i) for i in range(4)] == [True, True, False, True]
    assert v.txt_buscar.placeholderText().startswith("Cliente,")
    assert resumen(v, "TOTAL LOTE", "Gastos")[4] == "300,00 €"
    assert resumen(v, "FILTRO ACTUAL", "Ingresos")[4] == "100,00 €"
    assert v.tabla.currentRow() == 2
    assert [v._tipo_fila(i) for i in range(4)] == ["gasto", "gasto", "venta", "gasto"]
    v.botones_tipo["gasto"].click()
    v.txt_buscar.setText("suministros")
    assert v.txt_buscar.placeholderText().startswith("Proveedor,")
    assert resumen(v, "FILTRO ACTUAL", "Gastos")[2:5] == ["1", "1", "100,00 €"]
    r = next(r for r in range(v.tabla_resumen.rowCount())
             if v.tabla_resumen.item(r, 0).text() == "FILTRO ACTUAL")
    assert v.tabla_resumen.item(r, 4).background().color().name() == ACCENT_FAINT.lower()


def test_filtro_trimestral_y_siguiente_incidencia_no_dejan_filas_ocultas():
    v = ventana()
    v.combo_filtro_estado.setCurrentIndex(4)
    assert [v.tabla.isRowHidden(i) for i in range(4)] == [True, True, True, False]
    assert resumen(v, "DENTRO 1T 2026", "Gastos")[4] == "200,00 €"
    v.botones_tipo["venta"].click()
    v.txt_buscar.setText("sin coincidencias")
    v._siguiente_incidencia()
    assert v.tabla.currentRow() == 3
    assert not v.tabla.isRowHidden(3)
    assert v.tabla.item(3, C_ESTADO).text() == "! Revisar"
    assert not v._hay_filtro_activo()


def test_todos_los_campos_siguen_editables_sin_cambiar_indices():
    v = ventana()
    for c in (C_CUENTA, C_GXX, C_NIF, C_BASE, C_CUOTA_IRPF, C_TOTAL):
        assert not v.tabla.isColumnHidden(c)
        assert v.tabla.item(0, c).flags() & Qt.ItemIsEditable
    assert v.tabla.horizontalHeader().visualIndex(C_CUENTA) == 2
    assert v.tabla.horizontalHeader().visualIndex(C_GXX) == 3
    assert v.tabla.horizontalHeader().visualIndex(C_NOMBRE) == 6
    for c in (C_BASE_RE, C_PCT_RE, C_CUOTA_RE):
        assert v.tabla.isColumnHidden(c)


def test_el_recargo_aparece_solo_si_el_lote_lo_contiene():
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    f = Factura(
        num_factura="RE-1", nombre="PROVEEDOR RE", nif="B12345674",
        fecha="12/01/2026", concepto="600", subclave="G01",
        base_iva=100, pct_iva=21, cuota_iva=21,
        base_requiv=100, pct_requiv=5.2, cuota_requiv=5.2,
        total_impreso=126.2,
    )
    v._anadir_fila(b"", f, "gasto", "600", "G01", "", "Parte 1")

    for c in (C_BASE_RE, C_PCT_RE, C_CUOTA_RE):
        assert not v.tabla.isColumnHidden(c)
        assert v.tabla.item(0, c).flags() & Qt.ItemIsEditable


def test_boton_cuadrar_comparte_la_habilitacion_del_menu():
    v = ventana()
    assert not v.btn_cuadrar.isEnabled()
    v.btn_registro.setEnabled(True)
    assert v.btn_cuadrar.isEnabled()
    v.btn_registro.setEnabled(False)
    assert not v.btn_cuadrar.isEnabled()


def test_listado_pdf_incluye_totales_y_facturas_visibles(tmp_path, monkeypatch):
    from facturas_excel.app import QFileDialog

    v = ventana()
    v.txt_buscar.setText("SUMINISTROS")
    contenido = v._html_listado_totales()
    assert "Comprobación de totales" in contenido
    assert "TOTAL LOTE" in contenido
    assert "FILTRO ACTUAL" in contenido
    assert "SUMINISTROS PRUEBA" in contenido
    assert "OTRO PROVEEDOR PRUEBA" not in contenido.split(
        "Facturas mostradas", 1)[1]

    ruta = tmp_path / "comprobacion.pdf"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args, **kwargs: (str(ruta), "Documento PDF (*.pdf)"))
    v._guardar_listado_totales()

    assert ruta.read_bytes().startswith(b"%PDF")
    assert ruta.stat().st_size > 1_000


def test_filtro_sin_coincidencias_no_muestra_documento_anterior():
    v = ventana()
    v.txt_buscar.setText("no existe")
    assert not v.tabla.selectionModel().selectedRows()
    assert v._pixmap_documento.isNull()
    assert "0 facturas" in v.lbl_resultados.text()
