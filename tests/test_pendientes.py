"""Panel «Para mejorar el programa»: lo que hace falta saber y las notas."""

import pytest

from facturas_excel import pendientes
from facturas_excel.dialogo_pendientes import DialogoPendientes

VERSION = "9.9.9"


@pytest.fixture(autouse=True)
def datos_limpios(tmp_path, monkeypatch):
    """Cada test con su carpeta: no tocar las notas reales del usuario."""
    monkeypatch.setattr(pendientes, "dir_datos", lambda: str(tmp_path))


def test_las_dudas_viajan_con_el_programa():
    # config/ va dentro del .exe, asi que el panel no sale vacio al instalar.
    texto = pendientes.leer_pendientes()
    assert "total factura" in texto        # lo que mas falta hace
    assert texto.startswith("#")           # es markdown


def test_las_notas_se_guardan_y_se_releen():
    assert pendientes.guardar_notas("La copia de BIMBO sí se registra.")
    assert "La copia de BIMBO sí se registra." in pendientes.leer_notas()


def test_sin_notas_todavia_sale_la_cabecera_de_ayuda():
    assert "Escribe aquí lo que veas" in pendientes.leer_notas()


def test_apuntar_anade_al_final_sin_pisar_lo_anterior():
    pendientes.guardar_notas("# Notas\n\nLo primero.")
    pendientes.apuntar("Lo segundo.")
    texto = pendientes.leer_notas()
    assert "Lo primero." in texto and "Lo segundo." in texto


def test_apuntar_ignora_lo_vacio():
    pendientes.guardar_notas("# Notas")
    assert not pendientes.apuntar("   ")


def test_el_panel_solo_salta_una_vez_por_version():
    assert not pendientes.ya_visto(VERSION)
    pendientes.marcar_visto(VERSION)
    assert pendientes.ya_visto(VERSION)
    assert not pendientes.ya_visto("9.9.10")   # version nueva -> vuelve a salir


def test_el_panel_carga_las_dudas_y_las_notas():
    pendientes.guardar_notas("mis apuntes")
    d = DialogoPendientes(VERSION, al_arrancar=True)
    assert "total factura" in d.visor.toPlainText()
    assert d.editor.toPlainText().strip() == "mis apuntes"
    assert d.chk_no_mostrar.isChecked()      # al arrancar, por defecto no repetir


def test_guardar_en_el_panel_escribe_y_marca_visto():
    d = DialogoPendientes(VERSION, al_arrancar=True)
    d.editor.setPlainText("El recargo del 10% es 1,4.")
    d._guardar()
    assert "El recargo del 10% es 1,4." in pendientes.leer_notas()
    assert pendientes.ya_visto(VERSION)


def test_abierto_desde_el_menu_no_marca_visto_al_cerrar():
    d = DialogoPendientes(VERSION, al_arrancar=False)
    assert not d.chk_no_mostrar.isChecked()
    d.reject()
    assert not pendientes.ya_visto(VERSION)
