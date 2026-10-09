"""Tabla rápida con lotes grandes (800 líneas, 450 hojas).

Lo que medía el banco de estrés: cada bloque leído rehacía la tabla entera
(un desplegable por fila, insertada de una en una y con las columnas
recalculadas por cada fila), cada corrección volvía a pintar las 800 líneas
y la muestra de revisión escribía 3 MB de JSON en la ventana a los 0,8 s de
cada cambio. Estas pruebas fijan cada arreglo; ninguno cambia lo que se ve
ni lo que se decide (lo comprueba una huella de la tabla entera).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from facturas_excel.lote import Fila
from facturas_excel.modelo import Factura
from facturas_excel.tabla_facturas import C_CUENTA, C_NIF, TablaFacturas
from facturas_excel.validacion import Incidencia

_app = QApplication.instance() or QApplication([])


def _fila_suelta():
    return Fila(b"", Factura(num_factura="F-1", fecha="01/02/2026", nombre="PROVEEDOR PRUEBA",
                             nif="B12345674", base_iva=100.0, pct_iva=21.0,
                             cuota_iva=21.0, total_impreso=121.0, concepto="622"))


# ------------------------------------------- globo de ayuda de la cuenta
def test_el_globo_de_la_cuenta_no_repite_ni_conserva_avisos_viejos():
    tabla = TablaFacturas()
    fila = _fila_suelta()
    tabla.insertar(0, fila, lambda _control: None)
    cuenta = Incidencia("La cuenta 622 no corresponde a ingreso.", ("concepto",), "error")
    nif = Incidencia("NIF dudoso.", ("nif",), "revisar")
    tabla.resaltar(0, fila, "error", [cuenta])
    tabla.resaltar(0, fila, "error", [cuenta, nif])
    # El aviso de la cuenta, una sola vez (antes salía una vez por revisión).
    assert tabla.item(0, C_CUENTA).toolTip() == str(cuenta)
    assert tabla.item(0, C_NIF).toolTip() == str(nif)
    # Corregida la cuenta, su aviso se va del globo.
    tabla.resaltar(0, fila, "revisar", [nif])
    assert tabla.item(0, C_CUENTA).toolTip() == ""
    assert not tabla.item(0, C_CUENTA).font().bold()


# --------------------------------------------- un lote grande, inventado
CLIENTE = ("CLIENTE PRUEBA", "12345678Z")
# nombre, NIF, cuenta, subclave, tipos de IVA, número, % de retención
PROVEEDORES = [
    ("ALIMENTACION DE MUESTRA SL", "B12345674", "600", "G01", (10.0, 4.0, 21.0), "AM{n:05d}", None),
    ("TALLERES EJEMPLO SA", "A12345674", "622", "G13", (21.0, 10.0), "F25/{n:05d}", None),
    ("ASESORES FICTICIOS SL", "B76543214", "623", "G19", (21.0,), "{n}/2025", 15.0),
]
TIQUES = ["PARKING CENTRO INVENTADO", "CAFETERIA DE PRUEBA"]


def _lecturas(hojas, semilla=7):
    """Lo que «lee» la IA en cada hoja (dos lecturas): un surtido como el de
    un lote de verdad (varias líneas de IVA, ventas, tiques sin NIF, totales
    que no cuadran, cuentas sin poner, facturas de dos hojas, otra fecha de
    año, una hoja escaneada dos veces y diferencias entre las lecturas)."""
    import copy
    import random
    rnd = random.Random(semilla)
    contadores = {p[1]: rnd.randint(1, 300) for p in PROVEEDORES}
    venta = 0
    salida = []
    while len(salida) < hojas:
        mes, dia = 1 + len(salida) * 12 // max(hojas, 1), rnd.randint(1, 28)
        d = dict(emisor_nombre=None, emisor_nif=None, receptor_nombre=None,
                 receptor_nif=None, num_factura=None, fecha=f"{dia:02d}/{min(mes, 12):02d}/2025",
                 estado_pagina_factura="unica", lineas_iva=[], base_irpf=None,
                 pct_irpf=None, cuota_irpf=None, total=None, cuenta_gasto=None,
                 subclave_gxx=None, cuenta_ingreso="705", subclave_ingreso="I01",
                 tipo_documento="factura")
        dado = rnd.random()
        if dado < 0.12:
            nombre, nif = rnd.choice([(p[0], p[1]) for p in PROVEEDORES])
            venta += 1
            d.update(emisor_nombre=CLIENTE[0], emisor_nif=CLIENTE[1],
                     receptor_nombre=nombre, receptor_nif=nif,
                     num_factura=f"V25-{venta:04d}")
            tipos = (21.0,)
        elif dado < 0.16:
            d.update(emisor_nombre=rnd.choice(TIQUES), num_factura=f"TQ{rnd.randint(1000, 99999)}",
                     tipo_documento="factura_simplificada")
            tipos = (21.0,)
        else:
            nombre, nif, cuenta, sub, tipos, plantilla, irpf = rnd.choice(PROVEEDORES)
            contadores[nif] += 1
            d.update(emisor_nombre=nombre, emisor_nif=nif, receptor_nombre=CLIENTE[0],
                     receptor_nif=CLIENTE[1], num_factura=plantilla.format(n=contadores[nif]))
            if rnd.random() < 0.85:          # si no, la cuenta va por descarte (ámbar)
                d.update(cuenta_gasto=cuenta, subclave_gxx=sub)
        for tipo in tipos[:rnd.randint(1, len(tipos))]:
            base = round(rnd.uniform(8, 1500), 2)
            d["lineas_iva"].append(dict(base=base, tipo_iva=tipo,
                                        cuota_iva=round(base * tipo / 100, 2)))
        if d["emisor_nif"] == "B76543214":
            base = d["lineas_iva"][0]["base"]
            d.update(base_irpf=base, pct_irpf=15.0, cuota_irpf=round(base * 0.15, 2))
        d["total"] = round(sum(x["base"] + x["cuota_iva"] for x in d["lineas_iva"])
                           - (d["cuota_irpf"] or 0), 2)
        if rnd.random() < 0.04:
            d["total"] = round(d["total"] + 10, 2)          # no cuadra
        if rnd.random() < 0.01:
            d["fecha"] = d["fecha"][:-4] + "2024"            # otro año
        segunda = copy.deepcopy(d)
        if rnd.random() < 0.05:
            segunda["total"] = round((segunda["total"] or 0) + 1, 2)
        if rnd.random() < 0.04 and len(salida) + 2 <= hojas and d["emisor_nif"] != CLIENTE[1]:
            inicio = dict(d, estado_pagina_factura="inicio", lineas_iva=[], total=None,
                          base_irpf=None, pct_irpf=None, cuota_irpf=None)
            salida.append((inicio, copy.deepcopy(inicio)))
            salida.append((dict(d, estado_pagina_factura="final"),
                           dict(segunda, estado_pagina_factura="final")))
            continue
        salida.append((d, segunda))
    # Una hoja escaneada dos veces: duplicada.
    for i in range(3, len(salida), 37):
        if salida[i][0]["estado_pagina_factura"] == salida[i - 2][0]["estado_pagina_factura"] == "unica":
            salida[i] = copy.deepcopy(salida[i - 2])
    return salida[:hojas]


def _bloques(tmp_path, hojas, por_bloque=25):
    """Los bloques de la cola: [(procesadas, crudos)] como los da la lectura."""
    from facturas_excel.doble_lectura import combinar
    from facturas_excel.procesar import preparar_lote
    lecturas = _lecturas(hojas)
    ruta = str(tmp_path / "taco.pdf")
    bloques = []
    for desde in range(0, len(lecturas), por_bloque):
        crudos = [(f"hoja {desde + i}".encode(), ruta, desde + i,
                   combinar(d1, d2, "modelo-1", "modelo-2"))
                  for i, (d1, d2) in enumerate(lecturas[desde:desde + por_bloque], 1)]
        bloques.append(crudos)
    return [(preparar_lote(crudos, *CLIENTE), crudos) for crudos in bloques]


def _ventana(tmp_path):
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.clientes import marcar_cliente
    marcar_cliente(CLIENTE[1], CLIENTE[0])
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._rutas_actuales = [str(tmp_path / "taco.pdf")]
    return v


def _ventana_con_lote(tmp_path, hojas=60):
    v = _ventana(tmp_path)
    for procesadas, crudos in _bloques(tmp_path, hojas):
        v._on_terminado(procesadas, *CLIENTE, crudos)
    return v


def _contar(monkeypatch, dueno, nombre):
    """Cuenta las llamadas a dueno.nombre sin cambiar lo que hace."""
    llamadas = []
    original = getattr(dueno, nombre)

    def contada(*a, **k):
        llamadas.append(a)
        return original(*a, **k)
    monkeypatch.setattr(dueno, nombre, contada)
    return llamadas


# ------------------------------------- la tabla, de una vez (no fila a fila)
def test_ordenar_rehace_la_tabla_de_una_vez(tmp_path, monkeypatch):
    from facturas_excel.tabla_facturas import C_FECHA
    v = _ventana_con_lote(tmp_path, 60)
    n = v.tabla.rowCount()
    assert n > 50
    insertadas = _contar(monkeypatch, v.tabla, "insertRow")
    columnas = _contar(monkeypatch, v, "_actualizar_columnas")
    v._ordenar_tabla_por(C_FECHA)
    assert v.tabla.rowCount() == n
    # Ni una inserción por fila, y las columnas se deciden al final (más la
    # de la revisión del lote), no una vez por cada fila.
    assert insertadas == []
    assert len(columnas) <= 2


def test_abrir_con_la_sesion_guardada_pone_las_filas_de_una_vez(tmp_path, monkeypatch):
    from facturas_excel import sesion
    from facturas_excel.app import VentanaPrincipal
    v = _ventana_con_lote(tmp_path, 60)
    textos = [[v.tabla.item(r, c).text() for c in range(2, v.tabla.columnCount())]
              for r in range(v.tabla.rowCount())]
    v._guardar_sesion()
    sesion.esperar(30)
    insertadas = _contar(monkeypatch, TablaFacturas, "insertRow")
    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    assert [[otra.tabla.item(r, c).text() for c in range(2, otra.tabla.columnCount())]
            for r in range(otra.tabla.rowCount())] == textos
    assert insertadas == []


def _color(valor):
    if valor is None:
        return None
    return (valor.color() if hasattr(valor, "color") else valor).name()


def _entero(valor):
    try:
        return int(valor)
    except TypeError:
        return int(valor.value)


def _huella(v):
    """Todo lo que se ve de la tabla y lo que el programa decide de cada línea."""
    from PySide6.QtCore import Qt
    from facturas_excel.tabla_facturas import C_TIPO
    t = v.tabla
    celdas = []
    for r in range(t.rowCount()):
        fila = [t.isRowHidden(r), t.rowHeight(r)]
        for c in range(t.columnCount()):
            if c == C_TIPO:
                combo = t.cellWidget(r, c)
                fila.append((combo.currentData(), combo.toolTip()))
                continue
            it = t.item(r, c)
            fila.append((it.text(), _color(it.data(Qt.BackgroundRole)),
                         _color(it.data(Qt.ForegroundRole)), it.font().bold(),
                         it.toolTip(), _entero(it.textAlignment()), _entero(it.flags())))
        celdas.append(fila)
    lineas = [(f.presentacion, f.estado, f.estado_base, [str(m) for m in f.mensajes],
               f.aviso, f.tipo, f.bloque, f.aceptada, f.ya_exportada, f.factura.nombre,
               f.factura.nif) for f in v.filas]
    columnas = [(t.isColumnHidden(c), t.columnWidth(c)) for c in range(t.columnCount())]
    seleccion = (t.currentRow(), t.currentColumn(),
                 sorted(i.row() for i in t.selectionModel().selectedRows()),
                 t.verticalScrollBar().value())
    textos = (v.lbl_resultados.text(), v.lbl_contadores.text(), v.lbl_origen.text(),
              v.lbl_pagina.text())
    return celdas, lineas, columnas, seleccion, textos


# ---------------------------- cada bloque añade sus filas, sin rehacerlas
class _Gemelas:
    """Dos ventanas con el mismo lote, cada una con su carpeta de datos (lo
    que aprende una, un NIF o una cuenta, no lo encuentra hecho la otra)."""

    def __init__(self, tmp_path, monkeypatch):
        self.monkeypatch = monkeypatch
        self.carpetas = [tmp_path / "a", tmp_path / "b"]
        self.ventanas = [self._en(i, lambda: _ventana(tmp_path)) for i in (0, 1)]

    def _en(self, i, hacer):
        self.monkeypatch.setenv("APPDATA", str(self.carpetas[i] / "perfil"))
        self.monkeypatch.setenv("LOCALAPPDATA", str(self.carpetas[i] / "local"))
        return hacer()

    def ambas(self, hacer):
        for i, v in enumerate(self.ventanas):
            self._en(i, lambda: hacer(v))


def test_cada_bloque_anade_sus_filas_y_queda_igual_que_rehaciendo(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from facturas_excel.tabla_facturas import C_BASE, C_NIF, C_NOMBRE, C_TIPO
    from facturas_excel.validacion import REVISAR
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    gemelas = _Gemelas(tmp_path, monkeypatch)
    a, b = gemelas.ventanas
    # «a» como ahora: añade las filas nuevas; «b» como antes: rehace la
    # tabla entera en cada bloque.
    monkeypatch.setattr(b, "_solo_se_anaden", lambda filas: False, raising=False)
    gemelas.ambas(lambda v: v.resize(1400, 800))
    rehechas = _contar(monkeypatch, a.tabla, "poner_filas")

    def ambar(v):
        return next(r for r, f in enumerate(v.filas)
                    if f.estado == REVISAR and not f.factura.revision_confirmada)

    def quitar_bloque(v):
        v.combo_filtro_bloque.setCurrentIndex(2)
        v._quitar_bloque()

    def por_el_total(v):
        v.tabla.selectRow(4)
        v._alternar_por_el_total()

    def eliminar(v):
        v.tabla.selectRow(6)
        v._eliminar_seleccion()

    # Entre bloque y bloque, lo que haría una persona revisando a la vez.
    entre = [
        lambda v: None,
        lambda v: v.tabla.selectRow(5),
        lambda v: v.tabla.item(3, C_BASE).setText("150,00"),
        lambda v: v._marcar_revisada([ambar(v)]),
        lambda v: v.tabla.cellWidget(7, C_TIPO).setCurrentIndex(1),
        lambda v: v.tabla.item(2, C_NIF).setText("B12345674"),
        lambda v: v.combo_filtro_estado.setCurrentIndex(1),
        lambda v: v.combo_filtro_estado.setCurrentIndex(0),
        eliminar,
        por_el_total,
        quitar_bloque,
        lambda v: v._rehacer_con_cliente(*CLIENTE),
        lambda v: v._ordenar_tabla_por(C_NOMBRE),
        lambda v: None,
    ]
    lotes = [gemelas._en(i, lambda: _bloques(tmp_path, 8 * len(entre), 8)) for i in (0, 1)]
    for paso, ((pa, ca), (pb, cb)) in enumerate(zip(*lotes)):
        gemelas._en(0, lambda: a._on_terminado(pa, *CLIENTE, ca))
        gemelas._en(1, lambda: b._on_terminado(pb, *CLIENTE, cb))
        assert _huella(a) == _huella(b), f"distinto tras el bloque {paso + 1}"
        if paso == 0:
            combo = a.tabla.cellWidget(0, C_TIPO)
        if paso == 8:
            # Hasta aquí, las celdas de la primera fila son las de siempre.
            assert a.tabla.cellWidget(0, C_TIPO) is combo
        gemelas.ambas(entre[paso])
        assert _huella(a) == _huella(b), f"distinto tras lo hecho en el paso {paso + 1}"
    # Solo se ha rehecho entera con el primer bloque y cuando hacía falta
    # (por el total, quitar un bloque, cambiar de cliente, ordenar y el
    # bloque siguiente a cada una de esas cosas, salvo tras quitar uno).
    assert 6 <= len(rehechas) <= 9
    assert a.tabla.rowCount() > 100


# ------------------------------ pintar solo lo que cambia al revisar el lote
def test_revisar_el_lote_sin_cambios_no_vuelve_a_pintar_las_filas(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QTableWidgetItem
    v = _ventana_con_lote(tmp_path, 60)
    v._revalidar_todo()
    antes = _huella(v)
    tocadas = []
    for nombre in ("setBackground", "setToolTip", "setText", "setFont"):
        original = getattr(QTableWidgetItem, nombre)

        def apuntar(item, *a, _original=original):
            # Solo las de la tabla de facturas (los totales sí se rehacen:
            # son otra tabla).
            if item.tableWidget() is v.tabla:
                tocadas.append(item.row())
            return _original(item, *a)
        monkeypatch.setattr(QTableWidgetItem, nombre, apuntar)
    v._revalidar_todo()
    assert tocadas == []
    assert _huella(v) == antes


def test_lo_que_cambia_se_pinta_igual_que_en_una_tabla_recien_hecha(tmp_path, monkeypatch):
    from facturas_excel.tabla_facturas import C_BASE, C_CUENTA, C_NUM, C_TIPO, C_TOTAL
    from facturas_excel.validacion import ERROR, REVISAR
    v = _ventana_con_lote(tmp_path, 60)
    ambar = [r for r, f in enumerate(v.filas) if f.estado == REVISAR]
    rojas = [r for r, f in enumerate(v.filas) if f.estado == ERROR]
    assert len(ambar) > 3 and rojas
    v.tabla.item(rojas[0], C_TOTAL).setText("1,00")
    v.tabla.item(ambar[0], C_CUENTA).setText("629")
    v.tabla.item(ambar[1], C_BASE).setText("10,00")
    v._marcar_revisada([ambar[2]])
    v.tabla.cellWidget(ambar[3], C_TIPO).setCurrentIndex(1)
    v.tabla.item(rojas[-1], C_NUM).setText("")
    pintado = _huella(v)[:3]
    # La misma tabla rehecha entera y pintada desde cero.
    v._poner_filas(list(v.filas))
    v._revalidar_todo()
    assert _huella(v)[:3] == pintado


def test_filtrar_solo_oculta_o_ensena_las_filas_que_cambian(tmp_path, monkeypatch):
    v = _ventana_con_lote(tmp_path, 60)
    v.combo_filtro_estado.setCurrentIndex(1)            # las de revisar
    ocultas = [r for r in range(v.tabla.rowCount()) if v.tabla.isRowHidden(r)]
    assert ocultas
    cambios = _contar(monkeypatch, v.tabla, "setRowHidden")
    v._aplicar_filtro()
    assert cambios == []
    v.combo_filtro_estado.setCurrentIndex(0)            # todas otra vez
    assert sorted(r for r, _oculta in cambios) == ocultas
    assert not any(v.tabla.isRowHidden(r) for r in range(v.tabla.rowCount()))


# ------------------------------------------------------- fechas recordadas
def test_una_fecha_ya_entendida_no_se_vuelve_a_descifrar(monkeypatch):
    from datetime import date, datetime
    from facturas_excel import validacion

    class Contada(datetime):
        veces = 0

        @classmethod
        def strptime(cls, texto, formato):
            cls.veces += 1
            return datetime.strptime(texto, formato)
    monkeypatch.setattr(validacion, "datetime", Contada)
    assert validacion.fecha_de("2031-07-19") == date(2031, 7, 19)
    veces = Contada.veces
    assert veces >= 1
    for _ in range(5):
        assert validacion.fecha_de("2031-07-19") == date(2031, 7, 19)
    assert Contada.veces == veces
    # Lo raro (que no se puede recordar) se entiende igual que siempre.
    assert validacion.fecha_de(["19/07/2031"]) is None
    assert validacion.fecha_de(None) is None and validacion.fecha_de("") is None
