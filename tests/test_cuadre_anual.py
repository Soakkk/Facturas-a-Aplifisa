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
        _apunte("2", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0),   # ¿repetida?
        _apunte("3", "12/03/2026", "PROVEEDOR TRES SL", 80.0, 16.8),
        _apunte("4", "05/04/2026", "PROVEEDOR CUATRO SL", 60.0, 12.6),
        _apunte("5", "18/05/2026", "PROVEEDOR CINCO SL", 30.0, 6.3),   # no la tenemos
        _apunte("6", "09/07/2026", "TELECOM PRUEBA SA", 90.0, 18.9),
        _apunte("6", "09/07/2026", "TELECOM PRUEBA SA", 12.0, None),
        _apunte("7", "20/10/2026", "PROVEEDOR UNO SL", 10.0, 2.1),     # fuera
    ])
    estados = _por_estado(cuadre)
    assert sorted(estados[BIEN]) == ["A-1", "G-1"]
    assert sorted(estados[FALTA_APLIFISA]) == ["B-1", "F-1"]
    assert sorted(estados[FALTA_PROGRAMA]) == ["2", "3", "5"]
    assert estados[SIN_PDF] == ["D-1"]
    # Sin número de factura en el listado no se puede asegurar: la del 12/03
    # no se da por la misma con otra fecha, pero se avisa en las dos…
    f1 = next(l for l in cuadre.lineas if l.programa and l.programa.num_factura == "F-1")
    assert "12/03/2026" in f1.detalle and "Compruebe la fecha" in f1.detalle
    tres = next(l for l in cuadre.lineas if l.aplifisa and l.aplifisa.numero == "3")
    assert "10/03/2026" in tres.detalle
    # …y la repetida sin número no se llama «duplicada», pero se dice.
    dos = next(l for l in cuadre.lineas if l.aplifisa and l.aplifisa.numero == "2")
    assert "otra igual en el listado" in dos.detalle
    assert DUPLICADA not in estados and DISTINTA not in estados
    # Ni la de octubre ni el ingreso entran (solo se cargó el de compras).
    todas = [l.programa.num_factura for l in cuadre.lineas if l.programa]
    assert "Z-9" not in todas and "V-1" not in todas
    assert cuadre.fuera_de_periodo == 1 and cuadre.fuera_programa == 1
    assert not cuadre.todo_bien
    t1 = cuadre.trimestres[("gasto", 2026, 1)]
    assert t1["programa"][3] == 3 and t1["aplifisa"][3] == 3
    assert cuadre.trimestres[("gasto", 2026, 3)]["programa"][:3] == [102.0, 18.9, 120.9]
    assert cuadre.trimestres[("gasto", 2026, 3)]["aplifisa"][:3] == [102.0, 18.9, 120.9]


def _apunte_con(num_proveedor, fecha, nombre, base, cuota, nif="B12345674", numero=""):
    """Como en el listado de compras con columnas (nº del proveedor y NIF)."""
    a = _apunte(numero, fecha, nombre, base, cuota)
    a.num_factura_proveedor, a.nif = num_proveedor, nif
    return a


def test_con_el_numero_de_factura_se_ve_la_fecha_cambiada(tmp_path):
    _guardar(tmp_path, [_f("F-1", "10/03/2026", "PROVEEDOR TRES SL", 80.0, 16.8)])
    cuadre = _cuadrar([_apunte_con("F-1", "12/03/2026", "PROVEEDOR TRES SL", 80.0, 16.8,
                                   numero="31")])
    (linea,) = cuadre.lineas
    assert linea.estado == DISTINTA and "fecha" in linea.detalle


def test_cuotas_iguales_de_un_mismo_proveedor_no_se_cruzan(tmp_path):
    """Revisión: R-03 (marzo) no es «la R-02 con otra fecha»: falta R-03 en
    Aplifisa y R-02 en el programa."""
    _guardar(tmp_path, [_f("R-01", "01/01/2026", "ALQUILER PRUEBA SL", 50.0, 10.5),
                        _f("R-03", "01/03/2026", "ALQUILER PRUEBA SL", 50.0, 10.5)])
    sin_numeros = _cuadrar([_apunte("1", "01/01/2026", "ALQUILER PRUEBA SL", 50.0, 10.5),
                            _apunte("2", "01/02/2026", "ALQUILER PRUEBA SL", 50.0, 10.5)])
    assert _por_estado(sin_numeros) == {BIEN: ["R-01"], FALTA_APLIFISA: ["R-03"],
                                        FALTA_PROGRAMA: ["2"]}
    con_numeros = _cuadrar([_apunte_con("R-01", "01/01/2026", "ALQUILER PRUEBA SL", 50.0, 10.5),
                            _apunte_con("R-02", "01/02/2026", "ALQUILER PRUEBA SL", 50.0, 10.5)])
    estados = _por_estado(con_numeros)
    assert estados[FALTA_APLIFISA] == ["R-03"] and DISTINTA not in estados
    # Ni dos facturas del mismo día y proveedor con otros importes.
    _guardar(tmp_path, [_f("F-10", "05/05/2026", "TALLER PRUEBA SL", 100.0, 21.0)])
    otra = _cuadrar([_apunte_con("F-11", "05/05/2026", "TALLER PRUEBA SL", 30.0, 6.3)],
                    desde=date(2026, 5, 1), hasta=date(2026, 5, 31))
    assert _por_estado(otra) == {FALTA_APLIFISA: ["F-10"], FALTA_PROGRAMA: [""]}


def test_otro_nif_el_mismo_dia_e_importes_no_es_la_misma(tmp_path):
    _guardar(tmp_path, [_f("X-1", "10/03/2026", "EMPRESA EQUIS SL", 50.0, 10.5)])
    cuadre = _cuadrar([
        _apunte_con("Y-1", "10/03/2026", "EMPRESA YE SL", 50.0, 10.5, nif="B76543214"),
        _apunte_con("X-1", "11/03/2026", "EMPRESA EQUIS SL", 50.0, 10.5)])
    estados = _por_estado(cuadre)
    assert estados == {DISTINTA: ["X-1"], FALTA_PROGRAMA: [""]}
    distinta = next(l for l in cuadre.lineas if l.estado == DISTINTA)
    assert distinta.aplifisa.fecha == "11/03/2026"


def test_duplicada_solo_con_el_mismo_numero_de_factura(tmp_path):
    _guardar(tmp_path, [_f("FA-100", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    # Metida dos veces en Aplifisa: dos nº de registro, el mismo del proveedor.
    cuadre = _cuadrar([
        _apunte_con("FA-100", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0, numero="1"),
        _apunte_con("FA-100", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0, numero="2")])
    assert _por_estado(cuadre) == {BIEN: ["FA-100"], DUPLICADA: ["2"]}
    # Ventas: el número es el de la propia factura.
    _guardar(tmp_path, [_f("V-1", "03/02/2026", "CLIENTE FINAL SL", 100.0, 21.0)],
             tipo="venta")
    ventas = Registro(tipo="venta", apuntes=[
        _apunte("V-1", "03/02/2026", "CLIENTE FINAL SL", 100.0, 21.0),
        _apunte("V-2", "03/02/2026", "CLIENTE FINAL SL", 100.0, 21.0),   # otra
        _apunte("V-1", "03/02/2026", "CLIENTE FINAL SL", 100.0, 21.0)])  # repetida
    programa = cuadre_anual.facturas_del_registro(*CLIENTE, DESDE, HASTA)
    cuadre = cuadre_anual.cuadrar(programa, cuadre_anual.facturas_aplifisa(ventas),
                                  DESDE, HASTA, ("venta",))
    assert _por_estado(cuadre) == {BIEN: ["V-1"], FALTA_PROGRAMA: ["V-2"],
                                   DUPLICADA: ["V-1"]}


def test_tres_iguales_sin_numero_siempre_dan_lo_mismo(tmp_path):
    _guardar(tmp_path, [_f("T-1", "07/02/2026", "GASOLINERA PRUEBA", 41.32, 8.68)])
    apuntes = [_apunte(str(n), "07/02/2026", "GASOLINERA PRUEBA", 41.32, 8.68)
               for n in (1, 2, 3)]
    resultados = {tuple(sorted((l.estado for l in _cuadrar(apuntes).lineas)))
                  for _ in range(5)}
    assert resultados == {(BIEN, FALTA_PROGRAMA, FALTA_PROGRAMA)}


def test_una_factura_sin_numero_con_dos_tipos_de_iva_va_junta(tmp_path):
    _guardar(tmp_path, [_f("S-1", "04/04/2026", "SUPERMERCADO PRUEBA", 70.0, 9.2)])
    cuadre = _cuadrar([_apunte("", "04/04/2026", "SUPERMERCADO PRUEBA", 50.0, 5.0),
                       _apunte("", "04/04/2026", "SUPERMERCADO PRUEBA", 20.0, 4.2)])
    assert _por_estado(cuadre) == {BIEN: ["S-1"]}


def test_un_pdf_propio_que_ya_no_esta_es_falta_el_pdf(tmp_path):
    f = _f("P-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0,
           origen_imagen=_pdf(tmp_path, "taco_enero"))
    _guardar(tmp_path, [f])
    os.remove(registro_facturas.del_ejercicio(*CLIENTE[:1], 2026, CLIENTE[1],
                                              solo_exportadas=False)[0]["pdf"])
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    assert _por_estado(cuadre) == {SIN_PDF: ["P-1"]}


def test_un_cliente_guardado_con_nif_y_sin_el_se_carga_entero(tmp_path):
    _guardar(tmp_path, [_f("C-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    registro_facturas.exportar("", {"gasto": [_f("C-2", "16/01/2026", "PROVEEDOR DOS SL",
                                                 50.0, 10.5)]}, {"gasto": "G.xlsx"},
                               CLIENTE[1])
    assert cuadre_anual.clientes_guardados() == [CLIENTE]
    programa = cuadre_anual.facturas_del_registro(*CLIENTE, DESDE, HASTA)
    assert sorted(p.num_factura for p in programa) == ["C-1", "C-2"]
    assert cuadre_anual.mismo_cliente(("12.345.678-Z", ""), CLIENTE)


def test_el_nif_corregido_en_el_lote_no_la_hace_doble(tmp_path):
    exportada = _f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0, nif="A12345674")
    _guardar(tmp_path, [exportada])
    corregida = _f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)  # otro NIF
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)],
                      lote=[(corregida, "gasto", 3)])
    assert _por_estado(cuadre) == {BIEN: ["A-1"]}
    assert cuadre.lineas[0].programa.fila == 3


def test_dos_proveedores_con_el_mismo_numero_no_son_la_misma(tmp_path):
    _guardar(tmp_path, [_f("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    _guardar(tmp_path, [_f("1", "15/01/2026", "OTRA EMPRESA SL", 100.0, 21.0,
                           nif="A12345674")])
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0),
                       _apunte("2", "15/01/2026", "OTRA EMPRESA SL", 100.0, 21.0)])
    assert _por_estado(cuadre) == {BIEN: ["1", "1"]}


def test_una_linea_repetida_en_el_lote_no_suma_dos_veces():
    f = _f("H-1", "03/07/2026", "PROVEEDOR SEIS SL", 70.0, 14.7)
    (p,) = cuadre_anual.facturas_del_lote([(f, "gasto", 0), (f, "gasto", 1)])
    assert (p.base, p.cuota) == (70.0, 14.7)


def test_sin_facturas_no_dice_todo_bien(tmp_path):
    cuadre = _cuadrar([], desde=date(2026, 1, 1), hasta=date(2026, 3, 31))
    assert not cuadre.lineas and not cuadre.todo_bien


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


def test_el_periodo_sale_del_listado_por_trimestres_enteros():
    compras = Registro(apuntes=[_apunte("1", "02/07/2026", "X", 1.0, 0.21),
                                _apunte("2", "20/08/2026", "X", 1.0, 0.21)])
    # Aunque falte septiembre en Aplifisa, el periodo llega al 30/09: lo
    # guardado de septiembre saldrá como «falta en Aplifisa».
    assert cuadre_anual.periodo_de_listados([compras]) == (date(2026, 7, 1),
                                                           date(2026, 9, 30))
    enero = Registro(apuntes=[_apunte("1", "10/02/2026", "X", 1.0, 0.21)])
    assert cuadre_anual.periodo_de_listados([compras, enero])[0] == date(2026, 1, 1)
    # Una suelta del año anterior no arrastra el periodo a ese año.
    suelta = Registro(apuntes=[_apunte("9", "28/12/2025", "X", 1.0, 0.21)])
    assert cuadre_anual.periodo_de_listados([compras, suelta])[0] == date(2026, 7, 1)


def test_lo_guardado_del_ultimo_mes_que_no_esta_en_aplifisa_se_ve(tmp_path):
    _guardar(tmp_path, [_f("A-1", "15/07/2026", "PROVEEDOR UNO SL", 100.0, 21.0),
                        _f("S-9", "20/09/2026", "PROVEEDOR UNO SL", 40.0, 8.4)])
    compras = Registro(tipo="gasto", apuntes=[
        _apunte("1", "15/07/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    desde, hasta = cuadre_anual.periodo_de_listados([compras])
    cuadre = _cuadrar(compras.apuntes, desde=desde, hasta=hasta)
    assert _por_estado(cuadre) == {BIEN: ["A-1"], FALTA_APLIFISA: ["S-9"]}


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
    # El periodo, el del listado por trimestres (julio a septiembre).
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
