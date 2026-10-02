"""Cuadre con Aplifisa de lo guardado: el listado del periodo que se quiera
frente a todo lo que el programa tiene en PDF de ese cliente.

El proceso del usuario: saca de Aplifisa el listado de lo que quiere
comprobar (del 1 de enero a hoy, 6 o 9 meses, el año entero) y el programa
le dice si eso es lo que tiene guardado en PDF. Datos inventados.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date

import fitz
import pytest
from PySide6.QtWidgets import QApplication

from facturas_excel import cuadre_anual, registro_facturas
from facturas_excel.cuadre_anual import (
    BIEN, DISTINTA, DUPLICADA, FALTA_APLIFISA, FALTA_PROGRAMA, SIN_PDF,
)
from facturas_excel.modelo import Factura
from facturas_excel.registro import Apunte, Registro

_app = QApplication.instance() or QApplication([])

CLIENTE = ("12345678Z", "CLIENTE PRUEBA")
DESDE, HASTA = date(2026, 1, 1), date(2026, 9, 30)


def _f(num, fecha, nombre, base, cuota, nif="B12345674", **extra):
    return Factura(num_factura=num, fecha=fecha, nombre=nombre, nif=nif,
                   base_iva=base, pct_iva=21.0, cuota_iva=cuota,
                   total_impreso=round(base + (cuota or 0), 2), **extra)


def _pdf(tmp_path, nombre):
    ruta = tmp_path / f"{nombre}.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((40, 40), nombre)
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


def _guardar(tmp_path, facturas, tipo="gasto", con_pdf=True):
    """Como al exportar: ficha en el registro y su PDF en el archivo."""
    registro_facturas.exportar(CLIENTE[0], {tipo: facturas}, {tipo: "GASTOS_X.xlsx"},
                               CLIENTE[1])
    if con_pdf:
        registro_facturas.archivar(
            CLIENTE[0], CLIENTE[1],
            [(tipo, f, _pdf(tmp_path, f"{f.num_factura}_{f.fecha.replace('/', '')}"))
             for f in facturas])


def _apunte(numero, fecha, nombre, base, cuota):
    return Apunte(numero=numero, fecha=fecha, nombre=nombre, base=base,
                  cuota=cuota, neto=round(base + (cuota or 0), 2))


def _cuadrar(apuntes, lote=(), tipos=("gasto",), desde=DESDE, hasta=HASTA):
    programa = cuadre_anual.facturas_del_registro(*CLIENTE, desde, hasta)
    if lote:
        programa = cuadre_anual.juntar(programa, cuadre_anual.facturas_del_lote(lote))
    aplifisa = cuadre_anual.facturas_aplifisa(Registro(apuntes=list(apuntes), tipo="gasto"))
    return cuadre_anual.cuadrar(programa, aplifisa, desde, hasta, tipos)


def _por_estado(cuadre):
    salida = {}
    for linea in cuadre.lineas:
        d = linea.programa or linea.aplifisa
        salida.setdefault(linea.estado, []).append(
            (linea.programa.num_factura if linea.programa else linea.aplifisa.numero))
    return salida




def test_cada_caso_sale_con_su_nombre(tmp_path):
    _guardar(tmp_path, [
        _f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0),      # bien
        _f("B-1", "20/02/2026", "PROVEEDOR DOS SL", 50.0, 10.5),       # falta en Aplifisa
        _f("F-1", "10/03/2026", "PROVEEDOR TRES SL", 80.0, 16.8),      # otra fecha allí
    ])
    _guardar(tmp_path, [_f("D-1", "05/04/2026", "PROVEEDOR CUATRO SL", 60.0, 12.6)],
             con_pdf=False)                                              # sin PDF
    # Una de dos líneas de IVA: en Aplifisa salen dos líneas con el mismo nº.
    # (el total impreso es el de la factura entera, en las dos líneas)
    lineas_g = [_f("G-1", "09/07/2026", "TELECOM PRUEBA SA", 90.0, 18.9),
                _f("G-1", "09/07/2026", "TELECOM PRUEBA SA", 12.0, None)]
    for linea in lineas_g:
        linea.total_impreso = 120.9
    _guardar(tmp_path, lineas_g)
    _guardar(tmp_path, [_f("Z-9", "15/10/2026", "PROVEEDOR UNO SL", 10.0, 2.1)])  # fuera
    _guardar(tmp_path, [_f("V-1", "01/02/2026", "CLIENTE FINAL SL", 500.0, 105.0)],
             tipo="venta")                                               # ingreso

    cuadre = _cuadrar([
        _apunte("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0),
        _apunte("2", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0),   # repetida
        _apunte("3", "12/03/2026", "PROVEEDOR TRES SL", 80.0, 16.8),
        _apunte("4", "05/04/2026", "PROVEEDOR CUATRO SL", 60.0, 12.6),
        _apunte("5", "18/05/2026", "PROVEEDOR CINCO SL", 30.0, 6.3),   # no la tenemos
        _apunte("6", "09/07/2026", "TELECOM PRUEBA SA", 90.0, 18.9),
        _apunte("6", "09/07/2026", "TELECOM PRUEBA SA", 12.0, None),
        _apunte("7", "20/10/2026", "PROVEEDOR UNO SL", 10.0, 2.1),     # fuera
    ])
    estados = _por_estado(cuadre)
    assert sorted(estados[BIEN]) == ["A-1", "G-1"]
    assert estados[FALTA_APLIFISA] == ["B-1"]
    assert estados[FALTA_PROGRAMA] == ["5"]
    assert estados[SIN_PDF] == ["D-1"]
    assert estados[DUPLICADA] == ["2"]
    assert estados[DISTINTA] == ["F-1"]
    distinta = next(l for l in cuadre.lineas if l.estado == DISTINTA)
    assert "fecha" in distinta.detalle and "12/03/2026" in distinta.detalle
    # Ni la de octubre ni el ingreso entran (solo se cargó el de compras).
    todas = [l.programa.num_factura for l in cuadre.lineas if l.programa]
    assert "Z-9" not in todas and "V-1" not in todas
    assert cuadre.fuera_de_periodo == 1
    assert not cuadre.todo_bien
    # Totales por trimestre: en el 1T el programa tiene 3 y Aplifisa 3
    # (dos de ellas repetidas).
    t1 = cuadre.trimestres[("gasto", 1)]
    assert t1["programa"][3] == 3 and t1["aplifisa"][3] == 3
    assert cuadre.trimestres[("gasto", 3)]["programa"][:3] == [102.0, 18.9, 120.9]
    assert cuadre.trimestres[("gasto", 3)]["aplifisa"][:3] == [102.0, 18.9, 120.9]


def test_si_todo_esta_bien_lo_dice(tmp_path):
    _guardar(tmp_path, [_f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0),
                        _f("A-2", "15/02/2026", "PROVEEDOR UNO SL", 40.0, 8.4)])
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO", 100.0, 21.0),
                       _apunte("2", "15/02/2026", "PROVEEDOR UNO", 40.0, 8.4)])
    assert cuadre.todo_bien and len(cuadre.lineas) == 2


def test_el_lote_abierto_cuenta_y_no_se_duplica_con_lo_guardado(tmp_path):
    guardada = _f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)
    _guardar(tmp_path, [guardada])
    escaneo = _pdf(tmp_path, "taco_julio")
    nueva = _f("H-1", "03/07/2026", "PROVEEDOR SEIS SL", 70.0, 14.7,
               origen_imagen=escaneo)
    lote = [(guardada, "gasto", 0), (nueva, "gasto", 1)]
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO", 100.0, 21.0),
                       _apunte("2", "03/07/2026", "PROVEEDOR SEIS", 70.0, 14.7)],
                      lote=lote)
    assert cuadre.todo_bien and len(cuadre.lineas) == 2
    filas = {l.programa.num_factura: l.programa.fila for l in cuadre.lineas}
    assert filas == {"A-1": 0, "H-1": 1}            # «Ver en el lote»
    sin_exportar = next(l for l in cuadre.lineas if l.programa.num_factura == "H-1")
    assert sin_exportar.programa.origen == "lote"


def test_la_misma_factura_escaneada_dos_veces_sale_duplicada(tmp_path):
    _guardar(tmp_path, [_f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    # Otra vez la misma, leída con otro NIF en otro lote.
    _guardar(tmp_path, [_f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0,
                           nif="A12345674")])
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO", 100.0, 21.0)])
    estados = _por_estado(cuadre)
    assert estados[BIEN] == ["A-1"] and estados[DUPLICADA] == ["A-1"]
    assert FALTA_APLIFISA not in estados


def test_el_periodo_sale_del_listado():
    compras = Registro(apuntes=[_apunte("1", "02/07/2026", "X", 1.0, 0.21),
                                _apunte("2", "20/09/2026", "X", 1.0, 0.21)])
    assert cuadre_anual.periodo_de_listados([compras]) == (date(2026, 7, 1),
                                                           date(2026, 9, 30))
    enero = Registro(apuntes=[_apunte("1", "10/01/2026", "X", 1.0, 0.21)])
    assert cuadre_anual.periodo_de_listados([compras, enero])[0] == date(2026, 1, 1)


# ------------------------------------------------------------ la ventana

def _derecha(pagina, x_fin, y, texto, tam=7):
    pagina.insert_text((x_fin - fitz.get_text_length(texto, fontsize=tam), y),
                       texto, fontsize=tam)


def _listado_pdf(ruta, filas):
    """Un «listado de apuntes de compras desglosados» como el de Aplifisa."""
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((112, 125), "LISTADO DE APUNTES DE COMPRAS DESGLOSADOS",
                       fontsize=9)
    for x, texto in ((30, "Fecha"), (86, "Factura"), (136, "Cto."),
                     (218, "Cuenta"), (317, "Base"), (341, "I.V.A."),
                     (377, "Cuota"), (419, "Recargo"), (469, "I.R.P.F."),
                     (514, "Imp."), (535, "Neto"), (561, "GD")):
        pagina.insert_text((x, 152), texto, fontsize=7)
    y = 168
    for numero, fecha, nombre, base, cuota, neto in filas:
        pagina.insert_text((17, y), fecha, fontsize=7)
        _derecha(pagina, 137, y, numero)
        pagina.insert_text((139, y), "628", fontsize=7)
        pagina.insert_text((169, y), "15", fontsize=7)
        pagina.insert_text((179, y), nombre, fontsize=7)
        _derecha(pagina, 369, y, base)
        _derecha(pagina, 415, y, cuota)
        _derecha(pagina, 563, y, neto)
        y += 14
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


def test_la_ventana_carga_el_listado_cuadra_y_guarda_el_informe(tmp_path):
    from facturas_excel.dialogo_cuadre import DialogoCuadre
    _guardar(tmp_path, [_f("A-1", "15/07/2026", "PROVEEDOR UNO SL", 100.0, 21.0),
                        _f("B-1", "20/08/2026", "PROVEEDOR DOS SL", 50.0, 10.5)])
    listado = _listado_pdf(tmp_path / "compras.pdf", [
        ("1", "15/07/2026", "PROVEEDOR UNO SL", "100,00", "21,00", "121,00"),
        ("2", "03/09/2026", "PROVEEDOR CINCO SL", "30,00", "6,30", "36,30"),
    ])
    dialogo = DialogoCuadre(cliente=CLIENTE)
    assert dialogo.cliente() == CLIENTE
    assert not dialogo.boton_cuadrar.isEnabled()
    assert dialogo.cargar_listado(listado)
    # El periodo, el del listado (julio a septiembre).
    assert (dialogo.desde.date().month(), dialogo.hasta.date().day()) == (7, 30)
    dialogo.cuadrar()
    texto = dialogo.resumen.text()
    assert "1</b> falta en el programa" in texto and "1</b> falta en Aplifisa" in texto
    assert "Los ingresos no se comprueban" in texto
    # Por defecto, solo lo que falla.
    assert {l.estado for l in dialogo.lineas_visibles()} == {FALTA_APLIFISA, FALTA_PROGRAMA}
    assert dialogo.tabla.rowCount() == 2
    informe = dialogo.guardar_informe(str(tmp_path / "informe"))
    assert informe.endswith(".pdf") and os.path.getsize(informe) > 0
    with fitz.open(informe) as doc:
        assert "PROVEEDOR CINCO SL" in doc[0].get_text()
    dialogo.close()


def test_ver_en_el_lote_lleva_a_la_fila(tmp_path):
    from facturas_excel.dialogo_cuadre import DialogoCuadre
    nueva = _f("H-1", "03/07/2026", "PROVEEDOR SEIS SL", 70.0, 14.7)
    listado = _listado_pdf(tmp_path / "compras.pdf", [
        ("1", "01/07/2026", "PROVEEDOR UNO SL", "10,00", "2,10", "12,10")])
    dialogo = DialogoCuadre(cliente=CLIENTE, lote=[(nueva, "gasto", 4)])
    dialogo.cargar_listado(listado)
    dialogo.cuadrar()
    r = next(i for i, l in enumerate(dialogo.lineas_visibles())
             if l.programa and l.programa.num_factura == "H-1")
    dialogo.tabla.selectRow(r)
    assert dialogo.boton_lote.isEnabled()
    dialogo.boton_lote.click()
    assert dialogo.fila_seleccionada() == 4


def test_en_la_ventana_principal_hay_boton_y_menu():
    from facturas_excel.app import VentanaPrincipal
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    assert v.btn_cuadre_anual.isEnabled()
    assert v.accion_cuadre_anual.shortcut().toString() == "Ctrl+Shift+R"
    assert "Aplifisa" in v.btn_cuadre_anual.toolTip()
    v.close()
