"""Contrato del flujo automático: solo pasan facturas completas y revisadas."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from facturas_excel.app import (
    C_BASE, C_ESTADO, ICONO_MANUAL, ICONO_REVISADO, VentanaPrincipal,
)
from facturas_excel.modelo import Factura
from facturas_excel.procesar import construir
from facturas_excel.validacion import ERROR, OK, REVISAR, validar

_app = QApplication.instance() or QApplication([])


def factura(**cambios):
    datos = dict(
        num_factura="F-2026-1", fecha="03/09/2026", nombre="PROVEEDOR SL",
        nif="B86561412", concepto="622", base_iva=100.0, pct_iva=21.0,
        cuota_iva=21.0, total_impreso=121.0, confianza_ia="alta",
    )
    datos.update(cambios)
    return Factura(**datos)


def test_verde_exige_todos_los_importes_rutinarios():
    assert validar(factura()).estado == OK
    assert validar(factura(base_iva=None)).estado == ERROR
    assert validar(factura(pct_iva=None)).estado == ERROR
    assert validar(factura(cuota_iva=None)).estado == ERROR
    assert validar(factura(total_impreso=None)).estado == ERROR


def test_confianza_media_o_baja_obliga_a_revisar():
    for confianza in ("media", "baja"):
        resultado = validar(factura(confianza_ia=confianza))
        assert resultado.estado == REVISAR
        assert any("Confianza de lectura" in m for m in resultado.mensajes)


def test_gemini_transfiere_confianza_y_detecta_bien_de_inversion():
    datos = {
        "emisor_nombre": "MAQUINARIA SL", "emisor_nif": "B86561412",
        "receptor_nombre": "CLIENTE", "receptor_nif": "12345678Z",
        "num_factura": "M-1", "fecha": "03/09/2026",
        "lineas_iva": [{"base": 1000, "tipo_iva": 21, "cuota_iva": 210}],
        "total": 1210, "cuenta_gasto": "622", "confianza": "media",
        "es_bien_inversion": True,
    }
    f = construir(datos, "12345678Z", "CLIENTE").facturas[0]
    assert f.confianza_ia == "media"
    assert f.tratamiento_manual == "Bien de inversión"


def test_un_aviso_ambar_no_pasa_hasta_confirmarlo():
    v = VentanaPrincipal(comprobar_updates=False)
    f = factura(confianza_ia="media")
    v._anadir_fila(b"", f, "gasto", "622", "G13", "")
    v._revalidar_todo()

    por_tipo, _, _, pendientes = v._clasificar_exportacion()
    assert pendientes == [0] and por_tipo["gasto"] == []

    v.tabla.selectRow(0)
    v._marcar_revisada()
    por_tipo, _, _, pendientes = v._clasificar_exportacion()
    assert not pendientes and por_tipo["gasto"] == [f]
    assert v.tabla.item(0, C_ESTADO).text() == ICONO_REVISADO

    # Cualquier cambio posterior invalida la aprobación anterior.
    v.tabla.item(0, C_BASE).setText("99,00")
    _, _, errores, _ = v._clasificar_exportacion()
    assert errores == [0] and not f.revision_confirmada


def test_duplicados_y_gestion_manual_se_apartan_del_excel():
    v = VentanaPrincipal(comprobar_updates=False)
    normal = factura(num_factura="F-1")
    duplicada = factura(num_factura="F-1")
    manual = factura(num_factura="F-2", tratamiento_manual="Factura con suplido")
    for f in (normal, duplicada, manual):
        v._anadir_fila(b"", f, "gasto", "622", "G13", "")
    v._revalidar_todo()

    por_tipo, excluidas, errores, pendientes = v._clasificar_exportacion()
    assert por_tipo["gasto"] == [normal]
    assert {motivo for _, motivo in excluidas} == {"duplicada", "Factura con suplido"}
    assert not errores and not pendientes
    assert v.tabla.item(2, C_ESTADO).text() == ICONO_MANUAL
