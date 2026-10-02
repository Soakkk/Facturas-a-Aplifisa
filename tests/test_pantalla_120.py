"""La pantalla de la 1.20 (prototipo 4): lo que encontró la revisión.

Facturas y factura arriba; abajo, a lo ancho, los totales y «Su suma». Cada
prueba es un fallo que se vio antes de publicar: la hoja que se quedaba en
una tira al restaurar la ventana, las casillas de «Su suma» que se iban de
su columna al desplazar, el «Total» al que no se llegaba sin «Su suma», el
hueco en blanco al arrancar sin lote, el título cortado a secas y el
tabulador que no salía de «Su suma».
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from facturas_excel.app import VentanaPrincipal
from facturas_excel.modelo import Factura
from facturas_excel.su_suma import PRIMERA_COLUMNA_IMPORTE

_app = QApplication.instance() or QApplication([])


def _factura(**cambios):
    datos = dict(num_factura="F-1", fecha="03/09/2026", nombre="PROVEEDOR SL",
                 nif="B12345674", concepto="622", base_iva=100.0, pct_iva=21.0,
                 cuota_iva=21.0, total_impreso=121.0, confianza_ia="alta")
    datos.update(cambios)
    return Factura(**datos)


def _procesar(veces=4):
    for _ in range(veces):
        _app.processEvents()


def _ventana(tipos=(21.0,)):
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for i, pct in enumerate(tipos):
        v._anadir_fila(b"", _factura(num_factura=f"G-{i}", pct_iva=pct,
                                     cuota_iva=pct, total_impreso=100 + pct),
                       "gasto", "622", "", "")
    v._anadir_fila(b"", _factura(num_factura="P-1", nif="12345678Z",
                                 base_iva=150.0, cuota_iva=31.5, base_irpf=150.0,
                                 pct_irpf=15.0, cuota_irpf=22.5,
                                 total_impreso=159.0),
                   "gasto", "622", "", "")
    v._anadir_fila(b"", _factura(num_factura="V-1", base_iva=200.0,
                                 cuota_iva=42.0, total_impreso=242.0),
                   "venta", "700", "", "")
    v._revalidar_todo()
    return v


def test_la_hoja_no_se_queda_en_una_tira_al_restaurar_la_ventana():
    v = _ventana()
    v.resize(1024, 700)
    v.show()
    _procesar(8)
    antes = v.visor_scroll.width()
    v.resize(1920, 1040)                    # maximizar…
    _procesar(8)
    v.resize(1024, 700)                     # …y volver
    _procesar(8)
    assert v.visor_scroll.width() >= 240
    assert abs(v.visor_scroll.width() - antes) <= 4
    # La tarjeta de la factura no se estrecha por debajo de lo que necesita
    # (la hoja y lo leído, lado a lado), si la ventana da para todo: en las
    # máquinas de GitHub, sin el estilo del programa, los botones de Windows
    # piden más de lo que cabe en 1024.
    if v.minimumSizeHint().width() <= v.width():
        assert v.factura_card.width() >= v.factura_card.minimumSizeHint().width()
    v.close()


def _desfase(v, clave="base"):
    """Píxeles entre la casilla de «Su suma» y su columna de los totales."""
    totales, campo = v.tabla_totales, v.tabla_su_suma.campo(clave)
    columna = PRIMERA_COLUMNA_IMPORTE + [c[0] for c in v.tabla_su_suma._columnas].index(clave)
    x_campo = campo.mapTo(v, campo.rect().topLeft()).x()
    x_columna = (totales.viewport().mapTo(v, totales.viewport().rect().topLeft()).x()
                 + totales.columnViewportPosition(columna))
    return x_campo - x_columna


def test_su_suma_sigue_bajo_su_columna_al_desplazar_a_lo_ancho():
    # Cuatro tipos de IVA en 1024: no cabe a lo ancho. Con un filtro hay
    # cuatro filas y con los totales bajos sale además la barra vertical.
    v = _ventana(tipos=(21.0, 10.0, 5.0, 4.0))
    v.resize(1024, 700)
    v.show()
    _procesar(6)
    v.txt_buscar.setText("12345678Z")
    v._alto_totales_a_mano = True
    total = sum(v.split_principal.sizes())
    v.split_principal.setSizes([total - 150, 150])
    _procesar(6)
    barra_totales = v.tabla_totales.horizontalScrollBar()
    barra_suma = v.tabla_su_suma.horizontalScrollBar()
    assert barra_suma.maximum() > 0
    assert barra_suma.maximum() == barra_totales.maximum()
    # Se desplace la que se desplace (la rueda sobre los totales mueve la
    # de arriba), las dos van juntas y cada casilla, bajo su columna.
    for barra in (barra_suma, barra_totales):
        for valor in (0, barra.maximum() // 2, barra.maximum()):
            barra.setValue(valor)
            _procesar(2)
            assert barra_totales.value() == barra_suma.value() == valor
            for clave in ("base", "total"):
                assert _desfase(v, clave) == 0, (valor, clave)
    v.close()


def test_sin_su_suma_se_llega_al_total():
    v = _ventana(tipos=(21.0, 10.0, 5.0, 4.0))
    v.resize(1024, 700)
    v.show()
    _procesar(6)
    v.btn_ver_su_suma.setChecked(False)
    _procesar(6)
    barra = v.tabla_totales.horizontalScrollBar()
    assert v.tabla_su_suma.isHidden()
    assert v.tabla_totales.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert barra.maximum() > 0
    # La barra no tapa la última fila: el alto la cuenta.
    filas = sum(v.tabla_totales.rowHeight(r)
                for r in range(v.tabla_totales.rowCount()))
    assert v.tabla_totales.maximumHeight() >= (
        filas + v.tabla_totales.horizontalHeader().height()
        + barra.sizeHint().height())
    v.btn_ver_su_suma.setChecked(True)
    _procesar(2)
    assert v.tabla_totales.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    v.close()


def test_sin_lote_los_totales_no_ocupan_una_tabla_en_blanco():
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v.resize(1420, 820)
    v.show()
    _procesar(6)
    totales = v.tabla_totales
    assert totales.rowCount() == 0
    # Las columnas de siempre (ámbito, Nº, base, total IVA, recargo,
    # retención, suplidos, total) y «Su suma» con las mismas.
    assert totales.columnCount() == 8
    assert v.tabla_su_suma.columnCount() >= 8
    assert totales.maximumHeight() < 60
    assert v.split_principal.sizes()[1] < 0.3 * sum(v.split_principal.sizes())
    v.close()


def test_un_titulo_largo_se_recorta_con_puntos_y_va_entero_en_el_globo():
    from facturas_excel.ventana_comun import EtiquetaRecortada
    etiqueta = EtiquetaRecortada("Comprobación de totales  ·  3T 2026  ·  "
                                 "septiembre 2026 y otros filtros  ·  cliente "
                                 "en recargo de equivalencia", minimo=170)
    assert etiqueta.minimumSizeHint().width() == 170
    etiqueta.resize(200, 24)
    etiqueta.show()
    _procesar(2)
    assert etiqueta._visible(etiqueta.contentsRect().width()).endswith("…")
    assert etiqueta.toolTip() == etiqueta.text()
    etiqueta.resize(2000, 24)
    _procesar(2)
    assert etiqueta.toolTip() == ""
    etiqueta.close()
    v = _ventana()
    assert isinstance(v.lbl_resumen_titulo, EtiquetaRecortada)
    assert isinstance(v.tabla_su_suma.lbl_ambito, EtiquetaRecortada)


def test_el_tabulador_sale_de_su_suma():
    v = _ventana()
    assert not v.tabla_su_suma.tabKeyNavigation()
    assert not v.tabla_totales.tabKeyNavigation()


def test_los_botones_de_revisar_van_en_la_linea_del_titulo():
    v = _ventana()
    v.resize(1366, 720)
    v.show()
    _procesar(4)
    y = v.titulo_visor.geometry().center().y()
    for boton in (v.btn_revisada_factura, v.btn_correcta_siguiente):
        assert abs(boton.geometry().center().y() - y) <= 6
        assert boton.y() < v.visor_scroll.mapTo(v.factura_card, v.visor_scroll.rect().topLeft()).y()
    v.close()


def test_al_cambiar_las_columnas_no_quedan_casillas_viejas_a_la_vista():
    """Al salir otro tipo de IVA cambian las columnas: las casillas de antes
    no pueden quedarse pintadas donde estaban (se veían «su cifra» de más
    a la izquierda)."""
    from PySide6.QtWidgets import QLineEdit
    v = _ventana()
    v.resize(1366, 720)
    v.show()
    _procesar()
    v._anadir_fila(b"", _factura(num_factura="G-10", pct_iva=10.0,
                                 cuota_iva=10.0, total_impreso=110.0),
                   "gasto", "622", "", "")
    v._revalidar_todo()
    _procesar()
    visibles = [e for e in v.tabla_su_suma.findChildren(QLineEdit)
                if e.objectName() == "suSuma" and e.isVisible()]
    assert sorted(map(id, visibles)) == sorted(map(id, v.tabla_su_suma._campos.values()))
    assert "iva_10" in v.tabla_su_suma._campos
    v.close()
