"""Regresiones de edición y exportación de documentos completos."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from facturas_excel.app import VentanaPrincipal, C_BASE, C_CUOTA, C_TIPO, C_NOMBRE
from facturas_excel.procesar import construir
from facturas_excel.validacion import ERROR, OK

_app = QApplication.instance() or QApplication([])

@pytest.fixture(autouse=True)
def datos_aislados(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))

def datos(numero='F-1', segunda=100):
    return dict(emisor_nombre='PROVEEDOR PRUEBA SL', emisor_nif='B12345674',
                receptor_nombre='CLIENTE PRUEBA', receptor_nif='12345678Z',
                num_factura=numero, fecha='03/09/2026', cuenta_gasto='622',
                subclave_gxx='G13', confianza='alta',
                lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21),
                            dict(base=segunda, tipo_iva=10, cuota_iva=segunda/10)],
                total=121+segunda*1.1)

def ventana(*lecturas):
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for d in lecturas:
        pr = construir(d, '12345678Z', 'CLIENTE PRUEBA', 'ficticio.pdf', 1)
        for f in pr.facturas:
            v._anadir_fila(b'', f, pr.tipo, pr.cuenta, pr.gxx, pr.aviso)
    v._revalidar_todo()
    return v

def test_editar_multitipo_recalcula_total_y_corregir_quita_aviso():
    v = ventana(datos())
    v.tabla.item(1, C_BASE).setText('200')
    v.tabla.item(1, C_CUOTA).setText('20')
    tipos, _, errores, pendientes = v._clasificar_exportacion()
    assert errores or pendientes
    assert not tipos['gasto']
    assert any('341' in m and '231' in m for m in v.filas[0]['mensajes'])
    v.tabla.item(1, C_BASE).setText('100')
    v.tabla.item(1, C_CUOTA).setText('10')
    assert all(f['estado'] == OK for f in v.filas)

def test_copias_con_desglose_distinto_bloquean_documentos_enteros():
    v = ventana(datos(), datos(segunda=200))
    tipos, excluidas, errores, pendientes = v._clasificar_exportacion()
    assert len(errores) == 4
    assert not tipos['gasto'] and not excluidas

def test_copia_completa_se_aparta_entera():
    v = ventana(datos(), datos())
    tipos, excluidas, errores, pendientes = v._clasificar_exportacion()
    assert len(tipos['gasto']) == 2 and len(excluidas) == 2
    assert not errores and not pendientes

def test_quitar_una_linea_no_exporta_documento_incompleto():
    v = ventana(datos())
    v.tabla.selectRow(1)
    v._eliminar_seleccion()
    tipos, _, errores, _ = v._clasificar_exportacion()
    assert errores and not tipos['gasto']
    v._deshacer_borrado()
    assert len(v._clasificar_exportacion()[0]['gasto']) == 2

def test_cambiar_tipo_no_deja_cuenta_de_gasto_exportable_como_ingreso():
    v = ventana(datos())
    for r in range(2):
        v.tabla.cellWidget(r, C_TIPO).setCurrentIndex(1)
    tipos, _, errores, pendientes = v._clasificar_exportacion()
    assert errores and not tipos['venta']

def test_cambio_propagado_invalida_confirmacion():
    a, b = datos(), datos('F-2')
    a['confianza'] = b['confianza'] = 'media'
    v = ventana(a, b)
    for registro in v.filas:
        registro['factura'].revision_confirmada = True
    v.tabla.item(0, C_NOMBRE).setText('PROVEEDOR RENOMBRADO')
    assert all(not r['factura'].revision_confirmada for r in v.filas)

def test_editar_una_linea_invalida_revision_del_documento_completo():
    d = datos(); d['confianza'] = 'media'
    v = ventana(d)
    for registro in v.filas:
        registro['factura'].revision_confirmada = True
    v.tabla.item(0, C_BASE).setText('200')
    assert all(not r['factura'].revision_confirmada for r in v.filas)
