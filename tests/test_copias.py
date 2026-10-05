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

    antes = copias.restaurar(buena).antes

    assert _regimen("12345678Z") == clientes.TOTAL
    # Unas notas que existen no se pisan (se perdería lo apuntado después).
    assert "notas de después" in pendientes.leer_notas()
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


# ------------------------------------------- lo que encontró la revisión
def _con_facturas(n=3):
    """Un registro con n facturas exportadas (datos de prueba)."""
    from facturas_excel import historial
    from facturas_excel.modelo import Factura
    facturas = [Factura(num_factura=f"F-{i}", fecha="03/09/2026",
                        nombre="PROVEEDOR PRUEBA SL", nif="B12345674",
                        base_iva=100.0, pct_iva=21.0, cuota_iva=21.0)
                for i in range(n)]
    historial.registrar("12345678Z", {"gasto": facturas}, {})


def _vaciar_registro():
    with closing(sqlite3.connect(almacen.ruta(dir_datos()))) as con, con:
        con.execute("DELETE FROM facturas")


def test_la_rotacion_no_se_lleva_la_ultima_copia_buena():
    """Cambio de ordenador (o registro estropeado): quince días copiando un
    registro vacío no pueden borrar la última copia con facturas."""
    _con_facturas()
    buena = copias.hacer()
    _envejecer(buena)
    _vaciar_registro()
    for _ in range(copias.GUARDAR + 5):
        copias.hacer("a mano")
    assert os.path.isdir(buena)
    assert len(copias.listar()) == copias.GUARDAR + 1


def _envejecer(ruta, dias=30):
    resumen = os.path.join(ruta, copias.RESUMEN)
    with open(resumen, encoding="utf-8") as fh:
        datos = json.load(fh)
    datos["fecha"] = (datetime.now() - timedelta(days=dias)).isoformat(
        timespec="seconds")
    with open(resumen, "w", encoding="utf-8") as fh:
        json.dump(datos, fh)


def test_las_copias_de_otro_equipo_no_se_rotan_ni_cuentan_como_de_hoy(
        monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "OTRO-PC")
    del_otro = copias.hacer()
    monkeypatch.setenv("COMPUTERNAME", "ESTE-PC")
    assert not copias.hecha_hoy()
    for _ in range(copias.GUARDAR + 2):
        copias.hacer("a mano")
    assert os.path.isdir(del_otro)
    [otra] = [c for c in copias.listar() if c.equipo == "OTRO-PC"]
    assert otra.ruta == del_otro


def test_con_el_registro_vacio_se_ofrece_la_copia_buena(monkeypatch):
    from PySide6.QtWidgets import QApplication

    from facturas_excel.app import VentanaPrincipal
    QApplication.instance() or QApplication([])
    _con_facturas(4)
    copias.hacer()
    _vaciar_registro()
    assert copias.mejor_que_la_actual().facturas == 4

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._copia_diaria()
    assert "4 factura(s)" in v.banda.lbl.text()
    assert "Copias de seguridad" in v.banda.lbl.text()
    # Una sola vez por equipo de origen: no se repite cada día.
    v.banda.lbl.setText("")
    v._copia_diaria()
    assert v.banda.lbl.text() == ""


def test_se_restaura_aunque_la_base_en_uso_este_danada():
    _con_facturas(2)
    buena = copias.hacer()
    db = almacen.ruta(dir_datos())
    with open(db, "r+b") as fh:            # cabecera de SQLite estropeada
        fh.write(b"\0" * 100)

    resultado = copias.restaurar(buena)

    assert copias._contar_facturas(db) == 2
    assert os.path.isdir(resultado.antes)
    # La copia «antes» guarda la base dañada tal cual, para rescatarla.
    assert os.path.exists(os.path.join(resultado.antes, almacen.FICHERO))
    assert not [n for n in os.listdir(copias.carpeta())
                if not os.path.exists(os.path.join(copias.carpeta(), n,
                                                   copias.RESUMEN))]


def test_si_la_copia_falla_no_queda_una_carpeta_a_medias(monkeypatch):
    def falla(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")
    _con_facturas(1)
    monkeypatch.setattr(copias, "_contar_facturas", falla)
    try:
        copias.hacer()
    except sqlite3.OperationalError:
        pass
    assert os.listdir(copias.carpeta()) == []


def test_restaurar_no_cambia_la_carpeta_de_documentacion(tmp_path):
    from facturas_excel import ajustes
    from facturas_excel.archivo import carpeta_escaneos
    vieja = carpeta_escaneos()
    buena = copias.hacer()
    nueva = str(tmp_path / "Documentacion nueva")
    ajustes.guardar("carpeta_escaneos", nueva)
    os.makedirs(os.path.join(nueva, copias.CARPETA))
    # La copia elegida (de la carpeta vieja) se restaura desde la nueva.
    copias.restaurar(buena)
    assert carpeta_escaneos() == nueva != vieja
    assert copias.listar()          # la copia «antes de restaurar» se ve


def test_las_notas_y_el_indice_solo_vuelven_si_faltan(tmp_path):
    from facturas_excel.archivo import carpeta_escaneos
    pendientes.guardar_notas("notas buenas")
    indice = os.path.join(carpeta_escaneos(), ".clientes.json")
    with open(indice, "w", encoding="utf-8") as fh:
        json.dump({"12345678Z": {"nombre": "TIENDA", "carpeta": "TIENDA"}}, fh)
    buena = copias.hacer()
    os.remove(pendientes.ruta_notas())
    with open(indice, "w", encoding="utf-8") as fh:
        fh.write("{roto")

    resultado = copias.restaurar(buena)

    assert "notas buenas" in pendientes.leer_notas()
    with open(indice, encoding="utf-8") as fh:
        assert "TIENDA" in fh.read()
    assert not resultado.avisos
    assert not [n for n in os.listdir(os.path.dirname(indice))
                if n.endswith(".restaurando")]


def test_contar_facturas_no_crea_una_base_vacia(tmp_path):
    db = str(tmp_path / "no-existe.db")
    assert copias._contar_facturas(db) is None
    assert not os.path.exists(db)


def test_una_copia_con_una_base_vacia_de_cero_bytes_no_se_restaura():
    import pytest
    clientes.guardar_regimen_recargo("12345678Z", clientes.TOTAL, "TIENDA")
    ruta = copias.hacer()
    open(os.path.join(ruta, almacen.FICHERO), "wb").close()
    with pytest.raises(ValueError, match="no tiene un registro"):
        copias.restaurar(ruta)
    assert _regimen("12345678Z") == clientes.TOTAL     # nada tocado
