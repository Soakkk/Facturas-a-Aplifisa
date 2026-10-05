"""Copias de seguridad de lo que el programa recuerda (1.23)."""

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from facturas_excel import almacen, clientes, copias, pendientes
from facturas_excel.rutas import dir_datos


def _regimen(nif):
    return clientes.regimen_recargo(nif)


def test_la_copia_lleva_la_base_las_notas_y_el_indice(tmp_path):
    from facturas_excel.archivo import carpeta_escaneos
    clientes.guardar_regimen_recargo("12345678Z", clientes.TOTAL, "TIENDA")
    pendientes.guardar_notas("mis apuntes")
    indice = os.path.join(carpeta_escaneos(), ".clientes.json")
    with open(indice, "w", encoding="utf-8") as fh:
        json.dump({"12345678Z": {"nombre": "TIENDA", "carpeta": "TIENDA"}}, fh)

    ruta = copias.hacer()

    assert os.path.dirname(ruta) == os.path.join(carpeta_escaneos(),
                                                 copias.CARPETA)
    for fichero in (almacen.FICHERO, copias.NOTAS, copias.INDICE,
                    copias.RESUMEN):
        assert os.path.exists(os.path.join(ruta, fichero)), fichero
    # La base copiada está entera aunque lo último siga en su diario (WAL).
    with closing(sqlite3.connect(os.path.join(ruta, almacen.FICHERO))) as con:
        assert con.execute("SELECT COUNT(*) FROM datos WHERE clave = ?",
                           ("12345678Z",)).fetchone()[0] == 1
    [copia] = copias.listar()
    assert copia.motivo == "diaria" and copia.facturas == 0


def test_la_copia_diaria_se_hace_una_vez_al_dia():
    assert copias.diaria()
    assert copias.diaria() == ""
    assert len(copias.listar()) == 1


def test_se_quedan_las_ultimas_quince():
    for _ in range(copias.GUARDAR + 3):
        copias.hacer("a mano")
    assert len(copias.listar()) == copias.GUARDAR


def test_restaurar_vuelve_a_lo_de_la_copia_y_guarda_lo_de_ahora():
    clientes.guardar_regimen_recargo("12345678Z", clientes.TOTAL, "TIENDA")
    pendientes.guardar_notas("notas de antes")
    buena = copias.hacer()
    clientes.guardar_regimen_recargo("12345678Z", clientes.DESGLOSE, "TIENDA")
    pendientes.guardar_notas("notas de después")

    antes = copias.restaurar(buena)

    assert _regimen("12345678Z") == clientes.TOTAL
    assert "notas de antes" in pendientes.leer_notas()
    # Y lo que había justo antes de restaurar se puede recuperar.
    copias.restaurar(antes)
    assert _regimen("12345678Z") == clientes.DESGLOSE


def test_restaurar_la_mas_vieja_no_la_borra_antes_de_tiempo(monkeypatch):
    clientes.guardar_regimen_recargo("12345678Z", clientes.TOTAL, "TIENDA")
    vieja = copias.hacer()
    clientes.guardar_regimen_recargo("12345678Z", clientes.DESGLOSE, "TIENDA")
    for _ in range(copias.GUARDAR - 1):
        copias.hacer("a mano")
    # Que la elegida sea la más vieja de verdad (mismo segundo en la prueba).
    resumen = os.path.join(vieja, copias.RESUMEN)
    with open(resumen, encoding="utf-8") as fh:
        datos = json.load(fh)
    datos["fecha"] = (datetime.now() - timedelta(days=30)).isoformat(
        timespec="seconds")
    with open(resumen, "w", encoding="utf-8") as fh:
        json.dump(datos, fh)

    copias.restaurar(vieja)

    assert _regimen("12345678Z") == clientes.TOTAL
    assert len(copias.listar()) == copias.GUARDAR


def test_si_no_se_puede_hacer_la_copia_del_dia_se_avisa(monkeypatch):
    from PySide6.QtWidgets import QApplication

    from facturas_excel.app import VentanaPrincipal
    QApplication.instance() or QApplication([])
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)

    def disco_lleno(*_a, **_k):
        raise OSError("No queda espacio en el disco")
    monkeypatch.setattr(copias, "hacer", disco_lleno)
    v._copia_diaria()
    assert "copia de seguridad de hoy" in v.banda.lbl.text()
    assert "espacio" in v.banda.lbl.text()


def test_la_ventana_de_copias_hace_y_restaura(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from facturas_excel.dialogo_copias import DialogoCopias
    QApplication.instance() or QApplication([])
    clientes.guardar_regimen_recargo("12345678Z", clientes.TOTAL, "TIENDA")
    d = DialogoCopias()
    assert d.lista.count() == 0 and not d.btn_restaurar.isEnabled()
    d.btn_hacer.click()
    assert d.lista.count() == 1

    clientes.guardar_regimen_recargo("12345678Z", clientes.DESGLOSE, "TIENDA")
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    avisos = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: avisos.append(a[2])))
    d.btn_restaurar.click()
    assert _regimen("12345678Z") == clientes.TOTAL
    assert avisos and "vuelva a abrirlo" in avisos[0]
    assert d.lista.count() == 2          # la de «antes de restaurar»


def test_sin_carpeta_de_documentacion_la_copia_va_a_los_datos(monkeypatch):
    from facturas_excel import archivo

    def sin_carpeta():
        raise OSError("unidad de red desconectada")
    monkeypatch.setattr(archivo, "carpeta_escaneos", sin_carpeta)
    ruta = copias.hacer()
    assert ruta.startswith(os.path.join(dir_datos(), copias.CARPETA))
