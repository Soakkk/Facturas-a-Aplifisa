import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, Qt, QUrl
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


def test_solo_la_factura_de_otro_ejercicio_queda_en_rojo():
    from facturas_excel.app import C_FECHA, ICONO_ESTADO
    from facturas_excel.validacion import ERROR

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    aviso_antiguo = (
        "El PDF mezcla varios ejercicios; se ha archivado en el 2026, "
        "que es el más frecuente. Revise su ubicación.")
    for numero, fecha in (("F-100", "17/02/2026"),
                          ("F-101", "19/02/2026"),
                          ("F-102", "25/02/2020")):
        factura = Factura(
            num_factura=numero, fecha=fecha, nombre="PROVEEDOR DE PRUEBA SL",
            nif="B30048276", concepto="600", subclave="G01",
            base_iva=100, pct_iva=4, cuota_iva=4, total_impreso=104,
            revision_confirmada=True,
        )
        v._anadir_fila(b"", factura, "gasto", "600", "G01", aviso_antiguo)

    v._revalidar_todo()

    assert v._ejercicio_lote == 2026
    for fila in (0, 1):
        assert "mezcla varios ejercicios" not in v.tabla.item(
            fila, C_ESTADO).toolTip()
        assert "AÑO DISTINTO" not in v.tabla.item(fila, C_ESTADO).toolTip()
        assert v.tabla.item(fila, C_ESTADO).text() != ICONO_ESTADO[ERROR]
    erronea = v.tabla.item(2, C_ESTADO)
    assert erronea.text() == ICONO_ESTADO[ERROR]
    assert "AÑO DISTINTO" in erronea.toolTip()
    assert "25/02/2020" in erronea.toolTip()
    assert "lote es 2026" in erronea.toolTip()
    assert "F-102" in v.lbl_alerta_texto.text()
    fecha_erronea = v.tabla.item(2, C_FECHA)
    assert fecha_erronea.background().color().name() == "#ffcdd2"
    assert fecha_erronea.font().bold()
    assert "AÑO DISTINTO" in fecha_erronea.toolTip()

    # Al corregir el OCR, el campo vuelve automáticamente a su aspecto normal.
    fecha_erronea.setText("25/02/2026")
    v._revalidar_todo()
    assert fecha_erronea.data(Qt.BackgroundRole) is None
    assert fecha_erronea.data(Qt.ForegroundRole) is None
    assert not fecha_erronea.font().bold()
    assert "AÑO DISTINTO" not in fecha_erronea.toolTip()


def test_las_celdas_correctas_no_reciben_fondo_negro_al_revalidar():
    from facturas_excel.app import C_BASE, C_FECHA, C_NOMBRE

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._anadir_fila(b"", Factura(
        num_factura="F-150", fecha="18/02/2026", nombre="PROVEEDOR PRUEBA SL",
        nif="B30048276", concepto="600", subclave="G01", base_iva=100,
        pct_iva=4, cuota_iva=4, total_impreso=104,
    ), "gasto", "600", "G01", "")

    v._revalidar_todo()

    for columna in (C_FECHA, C_NOMBRE, C_BASE):
        item = v.tabla.item(0, columna)
        assert item.data(Qt.BackgroundRole) is None
        assert item.data(Qt.ForegroundRole) is None
        assert item.text()


def test_factura_multi_iva_cuenta_una_vez_al_decidir_el_ejercicio():
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for pct, base, cuota in ((21, 100, 21), (10, 100, 10)):
        v._anadir_fila(b"", Factura(
            num_factura="F-ANTIGUA", fecha="10/01/2020",
            nombre="PROVEEDOR DE PRUEBA SL", nif="B30048276",
            concepto="600", subclave="G01", base_iva=base, pct_iva=pct,
            cuota_iva=cuota, total_impreso=231, lineas_factura=2,
            origen_imagen="lote.pdf",
        ), "gasto", "600", "G01", "")
    for numero in ("F-200", "F-201"):
        v._anadir_fila(b"", Factura(
            num_factura=numero, fecha="10/01/2026",
            nombre="OTRO PROVEEDOR DE PRUEBA SL", nif="B30048276",
            concepto="600", subclave="G01", base_iva=100, pct_iva=4,
            cuota_iva=4, total_impreso=104, origen_imagen="lote.pdf",
        ), "gasto", "600", "G01", "")

    v._revalidar_todo()

    assert v._ejercicio_lote == 2026
    assert "AÑO DISTINTO" in v.tabla.item(0, C_ESTADO).toolTip()
    assert "AÑO DISTINTO" in v.tabla.item(1, C_ESTADO).toolTip()
    assert v.lbl_alerta_texto.text().count("F-ANTIGUA") == 1


def test_repara_sesion_si_un_abono_emitido_se_guardo_como_gasto():
    from facturas_excel.procesar import FacturaProcesada

    cliente = "12345678Z"
    f = Factura(
        num_factura="AB-400", fecha="16/04/2026", nombre="COMPRADOR PRUEBA SL",
        nif="B30048276", concepto="600", subclave="G01", base_iva=-50,
        pct_iva=21, cuota_iva=-10.5, total_impreso=-60.5,
        tipo_revision="gasto",
    )
    pr = FacturaProcesada("gasto", [f], "600", "G01", "lote.pdf", 1)
    crudo = {
        "emisor_nombre": "CLIENTE DE PRUEBA", "emisor_nif": cliente,
        "receptor_nombre": "COMPRADOR PRUEBA SL", "receptor_nif": "B30048276",
        "num_factura": "AB-400", "fecha": "16/04/2026",
        "lineas_iva": [{"base": -50, "tipo_iva": 21, "cuota_iva": -10.5}],
        "total": -60.5, "cuenta_ingreso": "700", "subclave_ingreso": "I01",
    }
    fila = {"factura": f, "tipo": "gasto", "cuenta": "600", "gxx": "G01",
            "bloque": "LOTE", "fuentes": [f]}
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nif, v._cliente_nombre = cliente, "CLIENTE DE PRUEBA"
    v._bloques = [{"nombre": "LOTE", "procesadas": [(b"", pr)],
                   "crudos": [(b"", "lote.pdf", 1, crudo)]}]

    v._reparar_abonos_emitidos_guardados([fila])

    assert (fila["tipo"], fila["cuenta"], fila["gxx"]) == (
        "venta", "700", "I01")
    assert (pr.tipo, pr.cuenta, pr.gxx) == ("venta", "700", "I01")
    assert f.tipo_revision == "venta"


def test_barra_rapida_y_acciones_se_adaptan_a_portatiles():
    from PySide6.QtCore import Qt
    from facturas_excel.app import C_BLOQUE, C_CUENTA, C_GXX
    from facturas_excel.estilo import FUENTE_UI, QSS

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    assert v.windowTitle() == "Facturas a Aplifisa"
    assert "Mono" not in FUENTE_UI
    assert "monospace" not in QSS
    assert not v.lbl_mostrar.icon().isNull()
    assert v.visor_scroll.widget() is v.lbl_img
    assert v.btn_zoom_menos.toolTip() == "Alejar documento"
    assert v.minimumWidth() == 1024
    assert v.menuBar().cornerWidget(Qt.TopRightCorner) is v.barra_rapida
    assert v.layout_herramientas.getItemPosition(
        v.layout_herramientas.indexOf(v.btn_siguiente))[0] == 0
    assert v.tabla.isColumnHidden(C_BLOQUE)
    assert v.tabla.columnWidth(C_CUENTA) <= 70
    assert v.tabla.columnWidth(C_GXX) <= 60
    assert [v.btn_cargar.text(), v.btn_escanear.text(), v.btn_vaciar.text(),
            v.btn_revisar_gemini.text(), v.btn_gastos.text()] == [
        "Abrir PDF", "Escanear", "Vaciar todo", "Revisar Gemini",
        "Exportar a Aplifisa"]
    acciones = [accion.text() for accion in v.menu_acciones.actions()]
    assert "Vaciar todo" not in acciones
    assert "Quitar bloque" in acciones
    assert "Eliminar selección" in acciones

    v.show()
    _app.processEvents()
    v.resize(1024, 640)
    _app.processEvents()
    assert v.menuBar().cornerWidget(Qt.TopRightCorner) is None
    assert v.barra_rapida.parentWidget() is v.fila_barra_estrecha
    assert v.layout_herramientas.getItemPosition(
        v.layout_herramientas.indexOf(v.btn_siguiente))[0] == 1
    assert v.layout_herramientas.getItemPosition(
        v.layout_herramientas.indexOf(v.btn_manual))[0] == 2
    assert not v.btn_unir_hojas.icon().isNull()
    assert v.btn_unir_hojas.toolTip().startswith("Seleccione las filas")
    for boton in (v.btn_siguiente, v.btn_revisada, v.btn_unir_hojas, v.btn_manual,
                  v.btn_mas_acciones):
        assert boton.width() >= boton.sizeHint().width()
    v.resize(1420, 820)
    _app.processEvents()
    assert v.menuBar().cornerWidget(Qt.TopRightCorner) is v.barra_rapida


def test_irpf_visible_y_ordenacion_por_fecha_y_retencion():
    from facturas_excel.app import (
        C_BASE_IRPF, C_CUOTA_IRPF, C_FECHA, C_NUM, C_PCT_IRPF,
    )

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nombre = "PERSONA DE PRUEBA"
    v._cliente_nif = "12345678Z"
    v._bloques = [{"nombre": "LOTE", "crudos": [
        (b"", "lote.pdf", 1, {
            "emisor_nombre": "TRANSPORTES DE PRUEBA",
            "emisor_nif": "12345678Z",
        })]}]
    datos = (
        ("V-3", "30/06/2024", None),
        ("V-1", "21/05/2024", 1.0),
        ("V-2", "04/06/2024", None),
    )
    for numero, fecha, irpf in datos:
        f = Factura(
            num_factura=numero, fecha=fecha, nombre="CLIENTE FACTURA SL",
            nif="B30048276", concepto="705", subclave="I01",
            base_iva=100, pct_iva=21, cuota_iva=21,
            total_impreso=120 if irpf else 121,
        )
        if irpf:
            f.base_irpf, f.pct_irpf, f.cuota_irpf = 100, irpf, 1
        v._anadir_fila(b"", f, "venta", "705", "I01", "")
    v._revalidar_todo()

    assert v.tabla.item(1, C_BASE_IRPF).text() == "100"
    assert v.tabla.item(1, C_PCT_IRPF).text() == "1,00"
    assert v.tabla.item(1, C_CUOTA_IRPF).text() == "1"
    assert "SIN IRPF" in v.tabla.item(0, C_PCT_IRPF).toolTip()

    v._ordenar_tabla_por(C_FECHA)
    assert [v.tabla.item(r, C_NUM).text() for r in range(3)] == [
        "V-1", "V-2", "V-3"]
    v._ordenar_tabla_por(C_PCT_IRPF)
    assert v.tabla.item(0, C_NUM).text() == "V-1"
    assert v.tabla.item(0, C_PCT_IRPF).text() == "1,00"


def test_boton_unir_hojas_reconstruye_una_sola_factura(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from facturas_excel import sesion
    from facturas_excel.procesar import preparar_lote

    cliente = ("CLIENTE DE PRUEBA", "12345678Z")
    cabecera = {
        "emisor_nombre": cliente[0], "emisor_nif": cliente[1],
        "receptor_nombre": "COMPRADOR DE PRUEBA SL", "receptor_nif": "B12345674",
        "num_factura": "V-700", "fecha": "02/05/2026",
        "lineas_iva": [{}], "total": None,
        "cuenta_ingreso": "700", "subclave_ingreso": "I01",
    }
    resumen = {
        "emisor_nombre": cliente[0], "emisor_nif": cliente[1],
        "receptor_nombre": None, "receptor_nif": None,
        "num_factura": "V-700", "fecha": "02/05/2024",
        "lineas_iva": [{"base": 80, "tipo_iva": 10, "cuota_iva": 8}],
        "total": 88,
    }
    crudos = [
        (b"cabecera", "lote.pdf", 4, cabecera),
        (b"resumen", "lote.pdf", 5, resumen),
    ]
    # Se fuerzan como dos fragmentos para probar el botón, no el automatismo.
    procesadas = [
        (b"cabecera", preparar_lote([crudos[0]], *cliente)[0][1]),
        (b"resumen", preparar_lote([crudos[1]], *cliente)[0][1]),
    ]
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._bloques = [{
        "nombre": "Bloque 1", "procesadas": procesadas, "crudos": crudos,
        "cliente": cliente[0], "nif": cliente[1], "tipo_declarado": "ingresos",
    }]
    v._rellenar_tabla()
    monkeypatch.setattr(v, "_filas_seleccionadas", lambda: [0, 1])
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(sesion, "guardar", lambda datos: None)

    v._unir_hojas_seleccionadas()

    assert len(v._bloques[0]["crudos"]) == 1
    assert v.tabla.rowCount() == 1
    assert v.filas[0]["factura"].num_factura == "V-700"
    assert v.filas[0]["factura"].fecha == "02/05/2026"
    assert v.filas[0]["factura"].total_impreso == 88

def test_revisar_gemini_copia_la_orden_para_codex(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from facturas_excel import revision_gemini

    texto = "orden segura para revisar Gemini"
    monkeypatch.setattr(
        revision_gemini, "guardar_solicitud",
        lambda version: (texto, r"C:\datos\solicitud-revision-gemini.md"))
    mensajes = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *args: mensajes.append(args[2])))
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)

    v.btn_revisar_gemini.click()

    assert QApplication.clipboard().text() == texto
    assert mensajes and "copiado al portapapeles" in mensajes[0]
