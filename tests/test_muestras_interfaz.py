"""La captura debe ocurrir en el flujo real, no solo al invocar el módulo."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
from zipfile import ZipFile
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from facturas_excel import app, muestras_revision
from facturas_excel.procesar import construir

_qt = QApplication.instance() or QApplication([])

@pytest.fixture
def v(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    monkeypatch.setattr(QMessageBox,'warning',lambda *a,**k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox,'information',lambda *a,**k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k: QMessageBox.Yes)
    from facturas_excel.clientes import marcar_cliente
    marcar_cliente('12345678Z','CLIENTE PRUEBA')
    v=app.VentanaPrincipal(comprobar_updates=False,restaurar_sesion=False)
    yield v
    v.deleteLater()

def cargar(v,tmp_path):
    ruta=tmp_path/'ejemplo.png'; ruta.write_bytes(b'imagen-ficticia')
    d=dict(num_factura='F-1',fecha='01/09/2026',emisor_nombre='PROVEEDOR PRUEBA',
           emisor_nif='B12345674',receptor_nombre='CLIENTE PRUEBA',
           receptor_nif='12345678Z',cuenta_gasto='622',subclave_gxx='G13',
           total=121,lineas_iva=[dict(base=100,tipo_iva=21,cuota_iva=21)])
    pr=construir(d,'12345678Z','CLIENTE PRUEBA',str(ruta),1)
    v._on_terminado([(b'imagen-ficticia',pr)],'CLIENTE PRUEBA','12345678Z',
                    [(b'imagen-ficticia',str(ruta),1,d)])
    return ruta

def test_original_se_guarda_aunque_no_haya_api(v,tmp_path,monkeypatch):
    ruta=tmp_path/'escaneo.png'; ruta.write_bytes(b'original ficticio')
    monkeypatch.setattr(app,'leer_api_key',lambda:None)
    v.procesar_rutas([str(ruta)],desde_escaner=True)
    archivos=list((muestras_revision.carpeta()/'originales').glob('*'))
    assert len(archivos)==1 and archivos[0].read_bytes()==b'original ficticio'

def test_vaciar_preserva_lectura_y_correccion(v,tmp_path):
    cargar(v,tmp_path)
    v.tabla.item(0,app.C_BASE).setText('200')
    v._vaciar_todo()
    lecturas=[json.loads(p.read_text()) for p in (muestras_revision.carpeta()/'lecturas').glob('*.json')]
    revisiones=[json.loads(p.read_text()) for p in (muestras_revision.carpeta()/'revisiones').glob('*.json')]
    assert lecturas and lecturas[0]['datos']['lineas_iva'][0]['base']==100
    assert any(x['factura']['base_iva']==200 for r in revisiones for x in r['filas'])
    assert v.tabla.rowCount()==0

def test_zip_del_menu_incluye_estado_actual(v,tmp_path,monkeypatch):
    cargar(v,tmp_path)
    v.tabla.item(0,app.C_NUM).setText('CORREGIDA')
    destino=tmp_path/'revision.zip'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(str(destino),'ZIP'))
    v._exportar_muestras()
    with ZipFile(destino) as z:
        snapshots=[json.loads(z.read(n)) for n in z.namelist() if n.startswith('revisiones/')]
        assert any(f['factura']['num_factura']=='CORREGIDA' for s in snapshots for f in s['filas'])
        assert any(n.startswith('originales/') for n in z.namelist())

def test_error_muestra_no_impide_cargar(v,tmp_path,monkeypatch):
    def fallo(*a,**k): raise OSError('disco lleno')
    monkeypatch.setattr(muestras_revision,'guardar_lecturas',fallo)
    cargar(v,tmp_path)
    assert v.tabla.rowCount()==1
    assert v._error_muestras

def test_continuacion_cruza_partes_25_y_26_sin_identidad(v,tmp_path):
    ruta=tmp_path/'taco.png'; ruta.write_bytes(b'original de prueba')
    primera=dict(num_factura='L-1',fecha='01/09/2026',emisor_nombre='PROVEEDOR PRUEBA',
                 emisor_nif='B12345674',receptor_nombre='CLIENTE PRUEBA',
                 receptor_nif='12345678Z',cuenta_gasto='622',subclave_gxx='G13',
                 estado_pagina_factura='inicio',lineas_iva=[],total=None)
    ultima=dict(num_factura=None,estado_pagina_factura='final',
                lineas_iva=[dict(base=100,tipo_iva=21,cuota_iva=21)],total=121)
    for parte,pagina,d in [(1,25,primera),(2,1,ultima)]:
        v._elemento_cola_actual={'original':str(ruta),'parte':parte,'partes':2,
                                'archivar':False,'rutas':[str(ruta)]}
        # La última página por sí sola no identifica al cliente.
        nif='12345678Z' if parte==1 else ''
        nombre='CLIENTE PRUEBA' if parte==1 else ''
        pr=construir(d,nif,nombre,str(ruta),pagina)
        v._on_terminado([(b'img',pr)],nombre,nif,[(b'img',str(ruta),pagina,d)])
    assert v.tabla.rowCount()==1
    f=v.filas[0]['factura']
    assert (f.pagina_origen,f.ultima_pagina_origen)==(25,26)
    assert f.num_factura=='L-1' and f.base_iva==100
    assert v.filas[0]['aviso']

def test_cargar_otro_bloque_conserva_cuenta_corregida(v,tmp_path):
    cargar(v,tmp_path)
    v.tabla.item(0,app.C_CUENTA).setText('600')
    v.tabla.item(0,app.C_GXX).setText('G01')
    v._rellenar_tabla()
    assert v.tabla.item(0,app.C_CUENTA).text()=='600'
    assert v.tabla.item(0,app.C_GXX).text()=='G01'

def test_reutilizar_ruta_no_cambia_original_de_revision_anterior(v,tmp_path):
    ruta=cargar(v,tmp_path)
    primer_id=v.filas[0]['factura'].original_id
    assert primer_id
    ruta.write_bytes(b'OTRO DOCUMENTO')
    segundo_id=muestras_revision.guardar_original(str(ruta))
    v._guardar_muestra_revision()
    revisiones=[json.loads(p.read_text()) for p in (muestras_revision.carpeta()/'revisiones').glob('*.json')]
    assert segundo_id!=primer_id
    assert all(x['original_id']==primer_id for r in revisiones for x in r['filas'])

def test_union_manual_conserva_correcciones_de_otras_facturas(v,tmp_path):
    from PySide6.QtCore import QItemSelectionModel
    from copy import deepcopy
    ruta=cargar(v,tmp_path)
    v.tabla.item(0,app.C_NUM).setText('CORREGIDA-A-MANO')
    d=deepcopy(v._bloques[0]['crudos'][0][3])
    d.update(num_factura='CABECERA',lineas_iva=[],total=None)
    e=deepcopy(d); e.update(num_factura='PIE-MAL-LEIDO',lineas_iva=[dict(base=100,tipo_iva=21,cuota_iva=21)],total=121)
    for pagina,datos in [(2,d),(3,e)]:
        pr=construir(datos,'12345678Z','CLIENTE PRUEBA',str(ruta),pagina)
        v._bloques[0]['crudos'].append((b'img',str(ruta),pagina,datos))
        v._bloques[0]['procesadas'].append((b'img',pr))
    v._rellenar_tabla(); v._revalidar_todo()
    v.tabla.clearSelection()
    for fila in [1,2]:
        v.tabla.selectionModel().select(v.tabla.model().index(fila,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
    v._unir_hojas_seleccionadas()
    assert v.tabla.rowCount()==2
    assert v.tabla.item(0,app.C_NUM).text()=='CORREGIDA-A-MANO'
