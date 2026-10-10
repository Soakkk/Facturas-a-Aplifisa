"""El diálogo de escanear: el blanco y negro avisa de lo que se pierde."""

from PySide6.QtWidgets import QApplication

from facturas_excel import ajustes
from facturas_excel.dialogo_escaneo import DialogoEscaneo

_app = QApplication.instance() or QApplication([])


def _dialogo():
    return DialogoEscaneo([("hp-1", "HP LaserJet")], ["CLIENTE PRUEBA"])


def test_por_defecto_se_escanea_en_grises_sin_aviso():
    d = _dialogo()
    assert d.valores()["modo_color"] == "grises"
    assert d.aviso_bn.isHidden()


def test_el_blanco_y_negro_dice_que_no_sirve_para_tiques_ni_letra_fina():
    d = _dialogo()
    i = d.combo_color.findData("bn")
    etiqueta = d.combo_color.itemText(i)
    assert "tiques" in etiqueta and "letra fina" in etiqueta
    d.combo_color.setCurrentIndex(i)
    assert not d.aviso_bn.isHidden()
    assert "tiques" in d.aviso_bn.text() and "grises" in d.aviso_bn.text()
    d.combo_color.setCurrentIndex(d.combo_color.findData("grises"))
    assert d.aviso_bn.isHidden()


def test_si_la_ultima_vez_fue_blanco_y_negro_el_aviso_sale_al_abrir():
    ajustes.guardar("escaneo_color", "bn")
    d = _dialogo()
    assert d.valores()["modo_color"] == "bn"
    assert not d.aviso_bn.isHidden()
