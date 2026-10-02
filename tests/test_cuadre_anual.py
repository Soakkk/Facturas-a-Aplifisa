"""Cuadre con Aplifisa de lo guardado: el listado del periodo que se quiera
frente a todo lo que el programa tiene en PDF de ese cliente.

El proceso del usuario: saca de Aplifisa el listado de lo que quiere
comprobar (del 1 de enero a hoy, 6 o 9 meses, el año entero) y el programa
le dice si eso es lo que tiene guardado en PDF. Datos inventados.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from datetime import date, timedelta

import fitz
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
    ruta = tmp_path / f"{nombre.replace('/', '-')}.pdf"
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


def _cuadrar(apuntes, lote=(), desde=DESDE, hasta=HASTA, formato="apuntes"):
    programa = cuadre_anual.facturas_del_registro(*CLIENTE, date(2025, 1, 1),
                                                  date(2027, 12, 31))
    if lote:
        programa = cuadre_anual.juntar(programa, cuadre_anual.facturas_del_lote(lote))
    aplifisa = cuadre_anual.facturas_aplifisa(
        Registro(apuntes=list(apuntes), tipo="gasto", formato=formato))
    return cuadre_anual.cuadrar(programa, aplifisa, {"gasto": (desde, hasta)})


def _por_estado(cuadre):
    salida = {}
    for linea in cuadre.lineas:
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
    # La de octubre del listado también se comprueba (todas se comprueban).
    assert sorted(estados[FALTA_PROGRAMA]) == ["2", "3", "5", "7"]
    assert estados[SIN_PDF] == ["D-1"]
    # Sin número de factura en el listado no se puede asegurar: la del 12/03
    # no se da por la misma con otra fecha, pero se avisa en las dos…
    f1 = next(l for l in cuadre.lineas if l.programa and l.programa.num_factura == "F-1")
    assert "12/03/2026" in f1.detalle and "Cambia la fecha" in f1.detalle
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
    siete = next(l for l in cuadre.lineas if l.aplifisa and l.aplifisa.numero == "7")
    assert "fuera del periodo" in siete.detalle and "15/10/2026" in siete.detalle
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
    ventas.formato = "columnas"                 # «facturas emitidas»
    programa = cuadre_anual.facturas_del_registro(*CLIENTE, DESDE, HASTA)
    cuadre = cuadre_anual.cuadrar(programa, cuadre_anual.facturas_aplifisa(ventas),
                                  {"venta": (DESDE, HASTA)})
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


def test_el_lote_abierto_con_el_mismo_nif_no_la_hace_doble(tmp_path):
    exportada = _f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)
    _guardar(tmp_path, [exportada])
    otra_vez = _f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)],
                      lote=[(otra_vez, "gasto", 3)])
    assert _por_estado(cuadre) == {BIEN: ["A-1"]}
    assert cuadre.lineas[0].programa.fila == 3


def test_el_nif_corregido_despues_se_avisa(tmp_path):
    """Exportada con un NIF y corregido después en el lote: dos NIF válidos
    son dos facturas para el cuadre; la del lote sale con el aviso."""
    _guardar(tmp_path, [_f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0,
                           nif="A12345674")])
    corregida = _f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)],
                      lote=[(corregida, "gasto", 3)])
    assert _por_estado(cuadre) == {BIEN: ["A-1"], FALTA_APLIFISA: ["A-1"]}
    falta = next(l for l in cuadre.lineas if l.estado == FALTA_APLIFISA)
    assert "salvo el NIF" in falta.detalle and falta.programa.fila == 3


def test_dos_proveedores_con_el_mismo_numero_no_son_la_misma(tmp_path):
    _guardar(tmp_path, [_f("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    _guardar(tmp_path, [_f("1", "15/01/2026", "OTRA EMPRESA SL", 100.0, 21.0,
                           nif="A12345674")])
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0),
                       _apunte("2", "15/01/2026", "OTRA EMPRESA SL", 100.0, 21.0)])
    assert _por_estado(cuadre) == {BIEN: ["1", "1"]}


def test_las_lineas_iguales_de_una_factura_suman_como_en_el_registro():
    f = _f("H-1", "03/07/2026", "PROVEEDOR SEIS SL", 35.0, 7.35)
    (p,) = cuadre_anual.facturas_del_lote([(f, "gasto", 0), (f, "gasto", 1)])
    assert (p.base, p.cuota) == (70.0, 14.7)


def test_las_copias_repetidas_del_lote_no_entran(monkeypatch):
    from facturas_excel import dialogo_cuadre
    from facturas_excel.app import VentanaPrincipal
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    for _ in range(2):
        v._anadir_fila(b"", _f("H-1", "03/07/2026", "PROVEEDOR SEIS SL", 70.0, 14.7),
                       "gasto", "628", "G17", "")
    v._revalidar_todo()
    assert v._duplicados
    recibido = {}

    class Falso:
        def __init__(self, _padre, _cliente, lote):
            recibido["lote"] = lote

        def exec(self):
            return 0

        def fila_seleccionada(self):
            return -1
    monkeypatch.setattr(dialogo_cuadre, "DialogoCuadre", Falso)
    v._cuadre_anual()
    assert [fila for _f, _t, fila in recibido["lote"]] == [0]
    v.close()


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


def test_la_misma_factura_guardada_dos_veces_sale_duplicada(tmp_path):
    _guardar(tmp_path, [_f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    # Otra vez la misma en otro lote, con el NIF sin leer.
    _guardar(tmp_path, [_f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0, nif="")])
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO", 100.0, 21.0)])
    estados = _por_estado(cuadre)
    assert estados[BIEN] == ["A-1"] and estados[DUPLICADA] == ["A-1"]
    assert FALTA_APLIFISA not in estados


def test_la_misma_con_otro_nif_valido_no_se_esconde(tmp_path):
    """Dos NIF válidos son dos facturas: la que no está en Aplifisa sale, con
    el aviso de que puede ser la misma guardada con otro NIF."""
    _guardar(tmp_path, [_f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    _guardar(tmp_path, [_f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0,
                           nif="A12345674")])
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO", 100.0, 21.0)])
    assert sorted(l.estado for l in cuadre.lineas) == sorted([FALTA_APLIFISA, BIEN])
    assert "salvo el NIF" in next(l.detalle for l in cuadre.lineas
                                  if l.estado == FALTA_APLIFISA)


def test_el_periodo_sale_del_listado_por_trimestres_enteros():
    def listado(*fechas):
        return Registro(apuntes=[_apunte(str(n), f, "X", 1.0, 0.21)
                                 for n, f in enumerate(fechas)])
    # Aunque falte septiembre en Aplifisa, el periodo llega al 30/09: lo
    # guardado de septiembre saldrá como «falta en Aplifisa».
    assert cuadre_anual.periodo_de_listado(listado("02/07/2026", "20/08/2026")) == \
        (date(2026, 7, 1), date(2026, 9, 30))
    # Una suelta del año anterior no lo arrastra…
    junio = listado("28/12/2025", *[f"{d:02d}/07/2026" for d in range(1, 25)])
    assert cuadre_anual.periodo_de_listado(junio)[0] == date(2026, 7, 1)
    # …pero de octubre a marzo son dos años y se cogen los dos.
    medio_anio = listado("05/10/2025", "05/11/2025", "05/12/2025", "20/12/2025",
                         "10/01/2026", "10/03/2026")
    assert cuadre_anual.periodo_de_listado(medio_anio) == (date(2025, 10, 1),
                                                           date(2026, 3, 31))
    # Las de finales de diciembre registradas en enero (pocas, aunque sean
    # más de dos) no llevan el periodo a octubre.
    tarde = listado(*[f"{d}/12/2025" for d in (27, 28, 29, 30, 31)],
                    *[f"{d:02d}/{m:02d}/2026" for m in (1, 2, 3) for d in range(1, 21)])
    assert cuadre_anual.periodo_de_listado(tarde)[0] == date(2026, 1, 1)
    # Una del año siguiente sí lo alarga: de más se ve; de menos, no.
    despues = listado(*[f"{d:02d}/{m}/2025" for m in (10, 11, 12) for d in range(1, 11)],
                      "05/01/2026")
    assert cuadre_anual.periodo_de_listado(despues) == (date(2025, 10, 1),
                                                        date(2026, 3, 31))


def test_lo_guardado_del_ultimo_mes_que_no_esta_en_aplifisa_se_ve(tmp_path):
    _guardar(tmp_path, [_f("A-1", "15/07/2026", "PROVEEDOR UNO SL", 100.0, 21.0),
                        _f("S-9", "20/09/2026", "PROVEEDOR UNO SL", 40.0, 8.4)])
    compras = Registro(tipo="gasto", apuntes=[
        _apunte("1", "15/07/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    desde, hasta = cuadre_anual.periodo_de_listado(compras)
    cuadre = _cuadrar(compras.apuntes, desde=desde, hasta=hasta)
    assert _por_estado(cuadre) == {BIEN: ["A-1"], FALTA_APLIFISA: ["S-9"]}


# ------------------------------------------------------------ la ventana

def _derecha(pagina, x_fin, y, texto, tam=7):
    pagina.insert_text((x_fin - fitz.get_text_length(texto, fontsize=tam), y),
                       texto, fontsize=tam)


def _listado_pdf(ruta, filas, nif=CLIENTE[0], totales=True):
    """Un «listado de apuntes de compras desglosados» como el de Aplifisa:
    con el NIF del cliente en la cabecera y su «TOTAL ACUMULADO»."""
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((17, 60), "GESTION FISCAL", fontsize=8)
    pagina.insert_text((17, 72), f"CLIENTE PRUEBA       D.N.I./C.I.F.: {nif}       Ref.  1",
                       fontsize=8)
    pagina.insert_text((112, 125), "LISTADO DE APUNTES DE COMPRAS DESGLOSADOS",
                       fontsize=9)
    for x, texto in ((30, "Fecha"), (86, "Factura"), (136, "Cto."),
                     (218, "Cuenta"), (317, "Base"), (341, "I.V.A."),
                     (377, "Cuota"), (419, "Recargo"), (469, "I.R.P.F."),
                     (514, "Imp."), (535, "Neto"), (561, "GD")):
        pagina.insert_text((x, 152), texto, fontsize=7)
    y = 168
    sumas = [0.0, 0.0, 0.0]
    for numero, fecha, nombre, base, cuota, neto in filas:
        pagina.insert_text((17, y), fecha, fontsize=7)
        _derecha(pagina, 137, y, numero)
        pagina.insert_text((139, y), "628", fontsize=7)
        pagina.insert_text((169, y), "15", fontsize=7)
        pagina.insert_text((179, y), nombre, fontsize=7)
        for i, (x_fin, valor) in enumerate(((369, base), (415, cuota), (563, neto))):
            _derecha(pagina, x_fin, y, valor)
            sumas[i] += float(valor.replace(",", "."))
        y += 14
    if totales:
        pagina.insert_text((179, y + 6), "TOTAL ACUMULADO", fontsize=7)
        for x_fin, valor in zip((369, 415, 563), sumas):
            _derecha(pagina, x_fin, y + 6, f"{valor:.2f}".replace(".", ","))
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
    assert (dialogo.desde["gasto"].date().month(), dialogo.hasta["gasto"].date().day()) \
        == (7, 30)
    assert not dialogo.desde["venta"].isEnabled()
    dialogo.cuadrar()
    texto = dialogo.resumen.text()
    assert "1</b> falta en el programa" in texto and "1</b> falta en Aplifisa" in texto
    assert "Los ingresos no se comprueban" in texto
    assert "no trae el número de factura del proveedor" in texto
    assert "totales" not in texto and "es del cliente con NIF" not in texto
    # Por defecto, solo lo que falla.
    assert {l.estado for l in dialogo.lineas_visibles()} == {FALTA_APLIFISA, FALTA_PROGRAMA}
    assert dialogo.tabla.rowCount() == 2
    # Lo que lleva el informe (el texto del PDF depende de las fuentes de
    # la máquina: en las de GitHub, sin pantalla, no se puede leer).
    contenido = dialogo.html_informe()
    assert "PROVEEDOR CINCO SL" in contenido and "Falta en Aplifisa" in contenido
    informe = dialogo.guardar_informe(str(tmp_path / "informe"))
    assert informe.endswith(".pdf") and os.path.getsize(informe) > 1000
    with fitz.open(informe) as doc:
        assert doc.page_count >= 1
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


# --------------------------------------- lo que encontró la segunda revisión

def test_sin_leer_entero_el_listado_no_hay_todo_bien(tmp_path):
    _guardar(tmp_path, [_f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    leido = Registro(tipo="gasto", formato="apuntes", total_base=150.0, total_cuota=31.5,
                     apuntes=[_apunte("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    programa = cuadre_anual.facturas_del_registro(*CLIENTE, DESDE, HASTA)
    cuadre = cuadre_anual.cuadrar(programa, cuadre_anual.facturas_aplifisa(leido),
                                  {"gasto": (DESDE, HASTA)})
    assert all(l.estado == BIEN for l in cuadre.lineas)
    cuadre.avisos += cuadre_anual.avisos_de_listado(leido)
    assert cuadre.avisos and not cuadre.todo_bien


def test_sin_fecha_en_el_programa_no_hay_todo_bien(tmp_path):
    _guardar(tmp_path, [_f("A-1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    sin_fecha = _f("Q-1", "", "PROVEEDOR UNO SL", 5.0, 1.05)
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)],
                      lote=[(sin_fecha, "gasto", 0)])
    assert cuadre.sin_fecha == 1 and not cuadre.todo_bien


def test_dos_copropietarios_con_el_mismo_numero_no_son_una_guardada_dos_veces(tmp_path):
    _guardar(tmp_path, [_f("3/2026", "01/03/2026", "GARCIA LOPEZ JOSE", 300.0, 63.0,
                           nif="12345678Z")])
    _guardar(tmp_path, [_f("3/2026", "01/03/2026", "GARCIA LOPEZ MARIA", 300.0, 63.0,
                           nif="B76543214")])
    cuadre = _cuadrar([_apunte("1", "01/03/2026", "GARCIA LOPEZ JOSE", 300.0, 63.0)])
    assert sorted(l.estado for l in cuadre.lineas) == sorted([FALTA_APLIFISA, BIEN])
    falta = next(l for l in cuadre.lineas if l.estado == FALTA_APLIFISA)
    assert falta.programa.nombre == "GARCIA LOPEZ MARIA"
    # Con su lote abierto tampoco se pierde.
    lote = [(_f("3/2026", "01/03/2026", "GARCIA LOPEZ MARIA", 300.0, 63.0,
                nif="B76543214"), "gasto", 7)]
    programa = cuadre_anual.juntar(
        [p for p in cuadre_anual.facturas_del_registro(*CLIENTE, DESDE, HASTA)
         if p.nombre != "GARCIA LOPEZ MARIA"], cuadre_anual.facturas_del_lote(lote))
    assert any(p.fila == 7 for p in programa)


def test_gana_el_nombre_mas_parecido(tmp_path):
    _guardar(tmp_path, [_f("A-5", "02/02/2026", "AUTOCARES GARCIA SL", 80.0, 16.8),
                        _f("M-9", "02/02/2026", "GARCIA MOTOR SL", 80.0, 16.8)])
    cuadre = _cuadrar([_apunte("1", "02/02/2026", "GARCIA MOTOR SL", 80.0, 16.8)])
    assert _por_estado(cuadre) == {BIEN: ["M-9"], FALTA_APLIFISA: ["A-5"]}


def test_mismo_dia_e_importes_con_otro_nombre_no_se_emparejan(tmp_path):
    _guardar(tmp_path, [_f("E-1", "02/02/2026", "ESTACION DE SERVICIO NORTE SL", 40.0, 8.4)])
    cuadre = _cuadrar([_apunte("1", "02/02/2026", "LIBRERIA CENTRAL SL", 40.0, 8.4)])
    assert _por_estado(cuadre) == {FALTA_APLIFISA: ["E-1"], FALTA_PROGRAMA: ["1"]}
    assert all("el nombre" in l.detalle for l in cuadre.lineas)
    # Pero «AQUASERVICE» sí es «VIVA AQUA SERVICE».
    _guardar(tmp_path, [_f("W-1", "03/02/2026", "VIVA AQUA SERVICE SPAIN SA", 34.0, 3.4)])
    agua = _cuadrar([_apunte("2", "03/02/2026", "AQUASERVICE SA", 34.0, 3.4)],
                    desde=date(2026, 2, 3), hasta=date(2026, 2, 3))
    assert _por_estado(agua) == {BIEN: ["W-1"]}


def test_numeros_de_factura_escritos_de_otra_forma():
    mismo = cuadre_anual._mismo_numero
    for a, b in (("F-0012", "F12"), ("0012", "12"), ("2026-0123", "123"),
                 ("2026/0012", "12"), ("F-0012", "12"), ("CO F26 0100", "COF260100"),
                 ("12/2026", "12"), ("FV-2026-12", "12"), ("2026 / 0001-r", "2026/1R")):
        assert mismo(a, b), (a, b)
    for a, b in (("A-0123", "B-0123"), ("11234", "1234"), ("R-0123", "F-0123"),
                 ("F-2026-0001", "F-2025-0001"),
                 # Revisión 3: la letra de detrás, la rectificativa y el año.
                 ("0001/A", "0001/B"), ("2026/001-R", "2026/001"), ("1/2026", "2026"),
                 ("0001/A", "1"), ("12/2026", "2026")):
        assert not mismo(a, b), (a, b)


def test_un_numero_distinto_veta_pero_deja_la_pista(tmp_path):
    _guardar(tmp_path, [_f("F-0012", "02/02/2026", "PROVEEDOR UNO SL", 80.0, 16.8)])
    cuadre = _cuadrar([_apunte_con("F-0013", "02/02/2026", "PROVEEDOR UNO SL", 80.0, 16.8,
                                   numero="4")], formato="columnas")
    assert _por_estado(cuadre) == {FALTA_APLIFISA: ["F-0012"], FALTA_PROGRAMA: ["4"]}
    assert all("F-0013" in l.detalle for l in cuadre.lineas if l.programa)


def test_dos_tiques_iguales_del_mismo_dia_sin_numero_son_dos(tmp_path):
    _guardar(tmp_path, [_f("T-1", "07/02/2026", "GASOLINERA PRUEBA", 33.06, 6.94),
                        _f("T-2", "07/02/2026", "GASOLINERA PRUEBA", 24.79, 5.21)])
    cuadre = _cuadrar([_apunte("", "07/02/2026", "GASOLINERA PRUEBA", 33.06, 6.94),
                       _apunte("", "07/02/2026", "GASOLINERA PRUEBA", 24.79, 5.21)])
    assert _por_estado(cuadre) == {BIEN: ["T-1", "T-2"]}


def test_clientes_con_el_mismo_nombre_y_un_cliente_que_cambio_de_nombre(tmp_path):
    registro_facturas.exportar("12345678Z", {"gasto": [_f("A", "01/01/2026", "P", 1.0, 0.21)]},
                               {"gasto": "x.xlsx"}, "JOSE GARCIA LOPEZ")
    registro_facturas.exportar("B76543214", {"gasto": [_f("B", "01/01/2026", "P", 1.0, 0.21)]},
                               {"gasto": "x.xlsx"}, "JOSE GARCIA LOPEZ")
    registro_facturas.exportar("A12345674", {"gasto": [_f("C", "01/01/2026", "P", 1.0, 0.21)]},
                               {"gasto": "x.xlsx"}, "NOMBRE VIEJO SL")
    registro_facturas.exportar("A12345674", {"gasto": [_f("D", "02/01/2026", "P", 1.0, 0.21)]},
                               {"gasto": "x.xlsx"}, "NOMBRE NUEVO SL")
    clientes = cuadre_anual.clientes_guardados()
    assert ("12345678Z", "JOSE GARCIA LOPEZ") in clientes
    assert ("B76543214", "JOSE GARCIA LOPEZ") in clientes
    assert [c for c in clientes if c[0] == "A12345674"] == [("A12345674", "NOMBRE NUEVO SL")]
    programa = cuadre_anual.facturas_del_registro("A12345674", "NOMBRE NUEVO SL",
                                                  DESDE, HASTA)
    assert sorted(p.num_factura for p in programa) == ["C", "D"]


def test_listado_de_compras_sin_numero_del_proveedor_lo_dice():
    sin = Registro(tipo="gasto", apuntes=[_apunte("1", "01/01/2026", "X", 1.0, 0.21)])
    con = Registro(tipo="gasto", apuntes=[_apunte_con("F-1", "01/01/2026", "X", 1.0, 0.21)])
    assert cuadre_anual.notas_de_listado(sin) and not cuadre_anual.notas_de_listado(con)


def test_cada_listado_con_su_periodo(tmp_path):
    _guardar(tmp_path, [_f("G-1", "15/08/2026", "PROVEEDOR UNO SL", 10.0, 2.1)])
    _guardar(tmp_path, [_f("V-8", "15/08/2026", "CLIENTE FINAL SL", 20.0, 4.2)],
             tipo="venta")
    programa = cuadre_anual.facturas_del_registro(*CLIENTE, DESDE, HASTA)
    compras = cuadre_anual.facturas_aplifisa(Registro(tipo="gasto", apuntes=[
        _apunte("1", "15/08/2026", "PROVEEDOR UNO SL", 10.0, 2.1)]))
    cuadre = cuadre_anual.cuadrar(programa, compras, {
        "gasto": (date(2026, 1, 1), date(2026, 9, 30)),
        "venta": (date(2026, 1, 1), date(2026, 6, 30))})    # ventas hasta junio
    assert _por_estado(cuadre) == {BIEN: ["G-1"]}           # V-8 no se reclama


def test_en_el_desglosado_de_ventas_el_numero_no_veta(tmp_path):
    _guardar(tmp_path, [_f("V-1", "03/02/2026", "CLIENTE FINAL SL", 100.0, 21.0)],
             tipo="venta")
    ventas = Registro(tipo="venta", formato="apuntes", apuntes=[
        _apunte("45", "03/02/2026", "CLIENTE FINAL SL", 100.0, 21.0)])
    programa = cuadre_anual.facturas_del_registro(*CLIENTE, DESDE, HASTA)
    cuadre = cuadre_anual.cuadrar(programa, cuadre_anual.facturas_aplifisa(ventas),
                                  {"venta": (DESDE, HASTA)})
    assert _por_estado(cuadre) == {BIEN: ["V-1"]}


# --------------------------------------- lo que encontró la tercera revisión

def test_dos_tiques_sin_nif_del_mismo_numero_y_dia_no_se_esconden(tmp_path):
    """Dos NIF vacíos no son «el mismo»: el tique de otra tienda con el mismo
    número, día e importes no se da por el ya guardado (antes se perdía y
    salía «todo bien»)."""
    _guardar(tmp_path, [_f("1", "15/01/2026", "BAR ESQUINA", 10.0, 2.1, nif="")])
    lote = [(_f("1", "15/01/2026", "FERRETERIA CENTRAL", 10.0, 2.1, nif=""), "gasto", 5)]
    cuadre = _cuadrar([_apunte("1", "15/01/2026", "BAR ESQUINA", 10.0, 2.1)], lote=lote)
    assert _por_estado(cuadre) == {BIEN: ["1"], FALTA_APLIFISA: ["1"]}
    falta = next(l for l in cuadre.lineas if l.estado == FALTA_APLIFISA)
    assert falta.programa.nombre == "FERRETERIA CENTRAL" and falta.programa.fila == 5
    assert not cuadre.todo_bien
    # Tampoco son «la misma guardada dos veces».
    progs = [cuadre_anual.FacturaPrograma("gasto", "16/01/2026", "7", nombre, "", 5.0, 1.05)
             for nombre in ("BAR ESQUINA", "FERRETERIA CENTRAL")]
    dos = cuadre_anual.cuadrar(progs, [], {"gasto": (DESDE, HASTA)})
    assert [l.estado for l in dos.lineas] == [FALTA_APLIFISA, FALTA_APLIFISA]
    # Sin nombre ni NIF no se sabe: tampoco.
    sin_nada = [cuadre_anual.FacturaPrograma("gasto", "16/01/2026", "7", "", "", 5.0, 1.05)
                for _ in range(2)]
    assert DUPLICADA not in _por_estado(
        cuadre_anual.cuadrar(sin_nada, [], {"gasto": (DESDE, HASTA)}))


def test_el_numero_corto_no_basta_para_darla_por_buena(tmp_path):
    """«F-1» y «1» del mismo día e importes, de dos proveedores, no son la
    misma. Un número largo e idéntico sí basta cuando no consta el proveedor."""
    _guardar(tmp_path, [_f("F-1", "15/01/2026", "TALLERES NORTE SL", 100.0, 21.0, nif="")])
    cuadre = _cuadrar([_apunte_con("1", "15/01/2026", "LIBRERIA SUR SL", 100.0, 21.0,
                                   nif="")])
    assert _por_estado(cuadre) == {FALTA_APLIFISA: ["F-1"], FALTA_PROGRAMA: [""]}
    assert all("el nombre" in l.detalle for l in cuadre.lineas)
    _guardar(tmp_path, [_f("2026-0457", "20/01/2026", "", 50.0, 10.5, nif="")])
    largo = _cuadrar([_apunte_con("2026-0457", "20/01/2026", "LIBRERIA SUR SL", 50.0, 10.5,
                                  nif="")], desde=date(2026, 1, 20), hasta=date(2026, 1, 20))
    (linea,) = largo.lineas
    assert linea.estado == BIEN and "nº de factura" in linea.detalle


def test_el_mismo_numero_de_otro_proveedor_no_es_un_dato_distinto(tmp_path):
    _guardar(tmp_path, [_f("100", "10/02/2026", "TALLERES NORTE SL", 100.0, 21.0)])
    otra_fecha = _cuadrar([_apunte_con("100", "15/02/2026", "LIBRERIA SUR SL", 100.0, 21.0,
                                       nif="")])
    assert _por_estado(otra_fecha) == {FALTA_APLIFISA: ["100"], FALTA_PROGRAMA: [""]}
    otros_importes = _cuadrar([_apunte_con("100", "10/02/2026", "LIBRERIA SUR SL", 40.0, 8.4,
                                           nif="")])
    assert _por_estado(otros_importes) == {FALTA_APLIFISA: ["100"], FALTA_PROGRAMA: [""]}
    # Con el mismo NIF y otro nombre sí es la misma, y se dice qué cambia.
    mismo_nif = _cuadrar([_apunte_con("100", "15/02/2026", "NOMBRE COMERCIAL", 100.0, 21.0)])
    (linea,) = mismo_nif.lineas
    assert linea.estado == DISTINTA
    assert "nombre: programa «TALLERES NORTE SL», Aplifisa «NOMBRE COMERCIAL»" in linea.detalle
    assert "fecha: programa 10/02/2026, Aplifisa 15/02/2026" in linea.detalle


def test_series_distintas_no_son_la_misma_factura(tmp_path):
    """«0001/A» y «0001/B» son dos facturas: la B no es una duplicada."""
    _guardar(tmp_path, [_f("0001/A", "05/03/2026", "TALLERES NORTE SL", 60.0, 12.6)])
    cuadre = _cuadrar([
        _apunte_con("0001/A", "05/03/2026", "TALLERES NORTE SL", 60.0, 12.6, numero="7"),
        _apunte_con("0001/B", "05/03/2026", "TALLERES NORTE SL", 60.0, 12.6, numero="8")])
    assert _por_estado(cuadre) == {BIEN: ["0001/A"], FALTA_PROGRAMA: ["8"]}


def test_la_repetida_es_la_de_despues_aunque_se_empareje_la_otra(tmp_path):
    """Si el programa se empareja con la segunda de dos iguales, la que sobra
    sigue siendo una duplicada (no «falta en el programa»)."""
    _guardar(tmp_path, [_f("FA-7", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    cuadre = _cuadrar([
        _apunte_con("FA-7", "15/01/2026", "PROVEEDOR UNO", 100.0, 21.0, numero="1",
                    nif=""),
        _apunte_con("FA-7", "15/01/2026", "PROVEEDOR UNO SL", 100.0, 21.0, numero="2")])
    assert sorted(l.estado for l in cuadre.lineas) == sorted([BIEN, DUPLICADA])


def test_nombres_por_palabras_enteras_y_el_proveedor_que_no_consta():
    parecidos = cuadre_anual.nombres_parecidos
    assert parecidos("AQUASERVICE SA", "VIVA AQUA SERVICE SPAIN SA")
    assert parecidos("ORANGE", "ORANGE ESPAGNE, S.A.U.")
    assert not parecidos("MARTIN SL", "MARTINEZ SL")
    assert not parecidos("TALLERES SL", "TALLERES PEREZ SL")     # solo una genérica
    assert not parecidos("", "ORANGE") and not parecidos("S.L.", "S.L.")
    emisor = cuadre_anual.mismo_emisor
    assert emisor("", "", "", "ORANGE") is None
    assert emisor("", "S.L.", "", "S.L.") is None
    assert emisor("B12345674", "", "B-12345674", "OTRO NOMBRE") is True
    assert emisor("B12345674", "ORANGE", "A12345674", "ORANGE") is False
    assert emisor("B1234567", "ORANGE SA", "B12345674", "ORANGE ESPAGNE") is True


def test_dos_lineas_al_mismo_tipo_con_centimos_redondeados_son_dos_tiques(tmp_path):
    """0,11 € de IVA sobre 0,50 € es un 21 % (no un 22 %): con otro tique al
    21 % del mismo día son dos facturas, no una de dos tipos de IVA."""
    _guardar(tmp_path, [_f("T-1", "08/02/2026", "GASOLINERA PRUEBA", 0.50, 0.11),
                        _f("T-2", "08/02/2026", "GASOLINERA PRUEBA", 100.0, 21.0)])
    cuadre = _cuadrar([_apunte("", "08/02/2026", "GASOLINERA PRUEBA", 0.50, 0.11),
                       _apunte("", "08/02/2026", "GASOLINERA PRUEBA", 100.0, 21.0)])
    assert _por_estado(cuadre) == {BIEN: ["T-1", "T-2"]}


def test_en_el_desglosado_de_ventas_un_numero_corto_no_basta_para_otra_fecha(tmp_path):
    """El número del desglosado de ventas puede ser el de Aplifisa: un «45»
    no hace la misma factura con otra fecha; uno largo e idéntico, sí."""
    _guardar(tmp_path, [_f("45", "03/02/2026", "CLIENTE FINAL SL", 100.0, 21.0),
                        _f("2026-0046", "10/02/2026", "CLIENTE FINAL SL", 80.0, 16.8)],
             tipo="venta")
    ventas = Registro(tipo="venta", formato="apuntes", apuntes=[
        _apunte("45", "05/02/2026", "CLIENTE FINAL SL", 100.0, 21.0),
        _apunte("2026-0046", "12/02/2026", "CLIENTE FINAL SL", 80.0, 16.8)])
    programa = cuadre_anual.facturas_del_registro(*CLIENTE, DESDE, HASTA)
    cuadre = cuadre_anual.cuadrar(programa, cuadre_anual.facturas_aplifisa(ventas),
                                  {"venta": (DESDE, HASTA)})
    estados = _por_estado(cuadre)
    assert estados[DISTINTA] == ["2026-0046"]
    assert estados[FALTA_APLIFISA] == ["45"] and estados[FALTA_PROGRAMA] == ["45"]
    falta = next(l for l in cuadre.lineas if l.estado == FALTA_APLIFISA)
    assert "Cambia la fecha" in falta.detalle


def test_sin_totales_ni_fechas_del_listado_no_hay_todo_bien():
    sin = Registro(tipo="gasto", apuntes=[_apunte("1", "15/01/2026", "X SL", 1.0, 0.21)])
    assert "TOTAL ACUMULADO" in " ".join(cuadre_anual.avisos_de_listado(sin))
    con = Registro(tipo="gasto", total_base=1.0, total_cuota=0.21, total_neto=1.21,
                   apuntes=list(sin.apuntes))
    assert not cuadre_anual.avisos_de_listado(con)
    # Una línea con la fecha ilegible no se puede comprobar: se dice.
    rara = cuadre_anual.facturas_aplifisa(Registro(tipo="gasto", apuntes=[
        _apunte("1", "15/13/2026", "X SL", 1.0, 0.21)]))
    cuadre = cuadre_anual.cuadrar([], rara, {"gasto": (DESDE, HASTA)})
    assert cuadre.avisos and not cuadre.todo_bien


def test_miles_de_facturas_en_poco_tiempo(tmp_path):
    """Antes, 4.000 facturas tardaban más de un minuto (todas con todas)."""
    pdf = _pdf(tmp_path, "factura")
    nombres = ("ALFA MOTOR SL", "BETA PAPELERIA SA", "GAMMA COMBUSTIBLES SL",
               "DELTA OFICINAS SL", "EPSILON LIMPIEZAS SL")
    progs, apls = [], []
    for n in range(4000):
        dia = date(2026, 1, 1) + timedelta(days=n % 270)
        base = round(10 + (n % 97) * 1.5, 2)
        cuota = round(base * 0.21, 2)
        nombre = nombres[n % len(nombres)]
        progs.append(cuadre_anual.FacturaPrograma(
            "gasto", f"{dia:%d/%m/%Y}", f"F-{n}", nombre, "", base, cuota,
            round(base + cuota, 2), pdf=pdf))
        apls.append(cuadre_anual.FacturaAplifisa(
            "gasto", f"{dia:%d/%m/%Y}", numero=str(n + 1), nombre=nombre, base=base,
            cuota=cuota, neto=round(base + cuota, 2), orden=n))
    inicio = time.perf_counter()
    cuadre = cuadre_anual.cuadrar(progs, apls, {"gasto": (date(2026, 1, 1),
                                                          date(2026, 12, 31))})
    assert time.perf_counter() - inicio < 20
    assert cuadre.todo_bien and len(cuadre.lineas) == 4000


def test_la_ventana_elige_el_cliente_del_listado_y_avisa_si_es_otro(tmp_path):
    from facturas_excel.dialogo_cuadre import DialogoCuadre
    _guardar(tmp_path, [_f("A-1", "15/07/2026", "PROVEEDOR UNO SL", 100.0, 21.0)])
    registro_facturas.exportar("B76543214", {"gasto": [
        _f("Z-1", "15/07/2026", "OTRO PROVEEDOR SL", 1.0, 0.21)]}, {"gasto": "x.xlsx"},
        "OTRO CLIENTE SL")
    listado = _listado_pdf(tmp_path / "compras.pdf", [
        ("1", "15/07/2026", "PROVEEDOR UNO SL", "100,00", "21,00", "121,00")])
    dialogo = DialogoCuadre(cliente=("B76543214", "OTRO CLIENTE SL"))
    assert dialogo.cliente()[0] == "B76543214"
    dialogo.cargar_listado(listado)
    assert dialogo.cliente() == CLIENTE              # el NIF de su cabecera
    dialogo.cuadrar()
    texto = dialogo.resumen.text()
    # Todo bien, pero sin el nº de factura del proveedor: se dice cómo.
    assert dialogo.cuadre.todo_bien and "Todo cuadra" in texto
    assert "no trae el nº de factura" in texto
    # Elegido otro cliente a mano: se avisa y no hay «todo bien».
    dialogo.combo_cliente.setCurrentIndex(
        next(i for i in range(dialogo.combo_cliente.count())
             if dialogo.combo_cliente.itemData(i)[0] == "B76543214"))
    dialogo.cuadrar()
    assert "es del cliente con NIF 12345678Z" in dialogo.resumen.text()
    assert not dialogo.cuadre.todo_bien
    # Un listado sin sus totales tampoco da «todo bien».
    sin_totales = _listado_pdf(tmp_path / "sin.pdf", [
        ("1", "15/07/2026", "PROVEEDOR UNO SL", "100,00", "21,00", "121,00")], totales=False)
    dialogo.cargar_listado(sin_totales)
    assert "sin sus totales" in dialogo.etiquetas_listado["gasto"].text()
    dialogo.cuadrar()
    assert not dialogo.cuadre.todo_bien and "TOTAL ACUMULADO" in dialogo.resumen.text()
    dialogo.close()


def test_las_lineas_de_fuera_del_periodo_se_dicen_en_naranja(tmp_path):
    from facturas_excel.dialogo_cuadre import DialogoCuadre
    _guardar(tmp_path, [_f("A-1", "15/07/2026", "PROVEEDOR UNO SL", 100.0, 21.0),
                        _f("J-1", "20/06/2026", "PROVEEDOR UNO SL", 40.0, 8.4)])
    listado = _listado_pdf(tmp_path / "compras.pdf", [
        ("1", "15/07/2026", "PROVEEDOR UNO SL", "100,00", "21,00", "121,00"),
        ("2", "20/06/2026", "PROVEEDOR UNO SL", "40,00", "8,40", "48,40")])
    dialogo = DialogoCuadre(cliente=CLIENTE)
    dialogo.cargar_listado(listado)
    dialogo.desde["gasto"].setDate(dialogo.desde["gasto"].date().addMonths(3))   # julio
    dialogo.cuadrar()
    texto = dialogo.resumen.text()
    assert "#86500A'>1 línea(s) del listado son de fuera del periodo" in texto
    assert "cambie el periodo" in texto
    dialogo.close()
