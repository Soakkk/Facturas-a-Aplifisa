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


def _jpeg(numero):
    """La imagen de una hoja (pequeña, distinta en cada una)."""
    import io
    from PIL import Image
    imagen = Image.new("RGB", (60, 80), (255, (numero * 7) % 256, (numero * 13) % 256))
    salida = io.BytesIO()
    imagen.save(salida, format="JPEG", quality=70)
    return salida.getvalue()


def _bloques(tmp_path, hojas, por_bloque=25):
    """Los bloques de la cola: [(procesadas, crudos)] como los da la lectura."""
    from facturas_excel.doble_lectura import combinar
    from facturas_excel.procesar import preparar_lote
    lecturas = _lecturas(hojas)
    ruta = str(tmp_path / "taco.pdf")
    bloques = []
    for desde in range(0, len(lecturas), por_bloque):
        crudos = [(_jpeg(desde + i), ruta, desde + i,
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


# ------------------------------------------- lo exportado, una vez por cliente
def _factura_exportada(numero):
    return Factura(num_factura=numero, fecha="10/03/2025", nombre="PROVEEDOR PRUEBA SL",
                   nif="B12345674", base_iva=100.0, pct_iva=21.0, cuota_iva=21.0,
                   total_impreso=121.0)


def test_lo_exportado_se_pregunta_una_vez_hasta_que_se_apunta_algo(monkeypatch):
    from facturas_excel import almacen, historial, registro_facturas
    from facturas_excel.rutas import dir_datos
    historial.registrar("12345678Z", {"gasto": [_factura_exportada("F-1")]}, {})
    consultas = _contar(monkeypatch, registro_facturas, "_con")
    primera = historial.exportadas_de("12345678Z")
    assert len(primera) == 1 and len(consultas) == 1
    for _ in range(3):
        assert historial.exportadas_de("12345678Z") == primera
    assert len(consultas) == 1
    # Lo que haga quien pregunta con la respuesta no cambia lo recordado.
    next(iter(primera.values()))["nif"] = "OTRO"
    assert historial.exportadas_de("12345678Z") != primera
    # Exportar algo más se ve en la siguiente pregunta...
    historial.registrar("12345678Z", {"gasto": [_factura_exportada("F-2")]}, {})
    assert len(historial.exportadas_de("12345678Z")) == 2
    # ...y olvidarlo (Aplifisa rechazó el Excel), también.
    historial.olvidar("12345678Z", {"gasto": [_factura_exportada("F-2")]})
    assert len(historial.exportadas_de("12345678Z")) == 1
    # Lo que cambie la base por fuera (otra copia del programa, restaurar
    # una copia de seguridad) también.
    antes = len(consultas)
    with almacen.conexion(dir_datos()) as con:
        con.execute("UPDATE facturas SET exportada_en = NULL")
    assert historial.exportadas_de("12345678Z") == {}
    assert len(consultas) == antes + 1


# ------------------------------- las líneas de cada factura, de una pasada
def test_marcar_revisada_todo_busca_las_lineas_de_cada_factura_de_una_pasada(
        tmp_path, monkeypatch):
    from facturas_excel import app, control_facturas, ventana_ficha
    from facturas_excel.validacion import REVISAR
    v = _ventana_con_lote(tmp_path, 60)
    n = len(v.filas)
    # Lo que habría marcado buscando fila a fila, como antes.
    esperadas = sorted({r for fila in range(n) for r in v._filas_del_documento(fila)
                        if v.filas[r].estado == REVISAR})
    claves = []

    def contada(f):
        claves.append(f)
        return control_facturas.clave_documento(f)
    monkeypatch.setattr(ventana_ficha, "clave_documento", contada)
    monkeypatch.setattr(app, "clave_documento", contada)
    v.tabla.selectAll()
    assert v._marcar_revisada() is not None
    # Unas pocas pasadas por el lote (marcar, revisar y la ficha de la que
    # se ve), no una por cada fila seleccionada (n × n).
    assert len(claves) <= 6 * n
    monkeypatch.undo()
    assert sorted(r for r in range(n) if v.filas[r].factura.revision_confirmada
                  and v.filas[r].estado == REVISAR) == esperadas


# ------------------------------------- eliminar varias de una vez, sin parpadeo
def _seleccionar(v, filas):
    from PySide6.QtCore import QItemSelection, QItemSelectionModel
    seleccion = QItemSelection()
    modelo = v.tabla.model()
    for r in filas:
        seleccion.select(modelo.index(r, 0), modelo.index(r, modelo.columnCount() - 1))
    v.tabla.selectionModel().select(
        seleccion, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)


def test_eliminar_varias_carga_la_hoja_y_la_ficha_una_vez(tmp_path, monkeypatch):
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.tabla_facturas import C_NIF
    miniaturas = _contar(monkeypatch, VentanaPrincipal, "_mostrar_miniatura")
    senaladas = _contar(monkeypatch, VentanaPrincipal, "_senalar_celda")
    v = _ventana_con_lote(tmp_path, 60)
    n = len(v.filas)
    v.tabla.setCurrentCell(4, C_NIF)
    _seleccionar(v, range(4, 16))
    quitadas = [v.filas[r] for r in range(4, 16)]
    del miniaturas[:], senaladas[:]
    v._eliminar_seleccion()
    assert len(v.filas) == n - 12 and not any(f in quitadas for f in v.filas)
    assert len(miniaturas) <= 2 and len(senaladas) <= 2      # antes, una por fila
    # Se queda en una fila de las que siguen, con su hoja y su ficha.
    r = v.tabla.currentRow()
    assert 0 <= r < len(v.filas)
    assert v.lbl_pagina.text() == f"Pág. {v.filas[r].factura.pagina_origen}"
    assert v._columna_senalada == v.tabla.currentColumn() or v._columna_senalada is None
    # Y se puede deshacer como siempre.
    v._deshacer_borrado()
    assert len(v.filas) == n and v.filas[4:16] == quitadas


# ------------------------- el cliente del lote, sin abrir la base por cada hoja
def _directorio_de_la_suite(clientes_suite):
    import json
    from facturas_excel import suite
    ruta = suite.ruta_directorio()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": 1, "clientes": clientes_suite}, fh)
    suite._cache.update(mtime=None, ruta=None, datos=None)


def _clientes_inventados():
    """Clientes guardados aquí y en la suite (identificadores inventados, no
    son NIF), con homónimos, nombres en conflicto y uno roto."""
    from facturas_excel import clientes
    for i in range(40):
        clientes._guardar_ficha(f"ZZPRUEBA{i:04d}", {
            "nombre": f"CLIENTE INVENTADO {i:04d} SL", "confirmado": i % 4 != 0})
    clientes._guardar_ficha("ZZHOMONIMO1", {"nombre": "Repetido, S.L.", "confirmado": True})
    clientes._guardar_ficha("ZZHOMONIMO2", {"nombre": "REPETIDO SL", "confirmado": True})
    clientes._guardar_ficha("ZZROTO", {"nombre": "JOS​ PRUEBA", "confirmado": True})
    suite_clientes = {f"ZZSUITE{i:04d}": {"nif": f"ZZSUITE{i:04d}",
                                          "nombre": f"Socio Inventado {i:04d}"}
                      for i in range(40)}
    suite_clientes["ZZSUITE0007"]["conflictos"] = {"nombre": ["Uno", "Otro"]}
    suite_clientes["ZZDOBLE"] = {"nif": "ZZDOBLE", "nombre": "Cliente Inventado 0001 SL"}
    suite_clientes["ZZPRUEBA0002"] = {"nif": "ZZPRUEBA0002", "nombre": "Otro nombre"}
    _directorio_de_la_suite(suite_clientes)


def _buscar_como_antes(nombre):
    """buscar_confirmado_por_nombre tal como era (la referencia)."""
    from facturas_excel import clientes, suite
    clave = clientes._clave_nombre(nombre)
    if not clave:
        return None
    coincidencias = {}
    for nif, ficha in clientes._leer_todo().items():
        if (isinstance(ficha, dict) and ficha.get("confirmado")
                and clientes._clave_nombre(ficha.get("nombre")) == clave):
            coincidencias[clientes._normaliza(nif)] = ficha.get("nombre", "")
    for nif in suite.clientes():
        otro = suite.nombre_de(nif)
        if otro and clientes._clave_nombre(otro) == clave:
            coincidencias.setdefault(nif, otro)
    return next(iter(coincidencias.items())) if len(coincidencias) == 1 else None


def test_el_directorio_de_clientes_responde_lo_mismo_que_antes():
    from facturas_excel import clientes, suite
    _clientes_inventados()
    nombres = ([f"cliente inventado {i:04d} s.l." for i in range(40)]
               + [f"SOCIO INVENTADO {i:04d}" for i in range(40)]
               + ["Repetido SL", "JOS​ PRUEBA", "JOS PRUEBA", "Otro nombre",
                  "NADIE CONOCIDO", "", None, "Uno"])
    directorio = clientes.Directorio()
    for nombre in nombres:
        assert directorio.buscar_por_nombre(nombre) == _buscar_como_antes(nombre), nombre
        assert clientes.buscar_confirmado_por_nombre(nombre) == _buscar_como_antes(nombre)
    todo = clientes._leer_todo()
    for nif in [*todo, *suite.clientes(), "zzprueba0001", "ZZ-SUITE-0003", "NADIE", ""]:
        ficha = todo.get(clientes._normaliza(nif), {})
        confirmado = bool(clientes._normaliza(nif) and (
            ficha.get("confirmado") or suite.es_cliente(clientes._normaliza(nif))))
        assert directorio.es_confirmado(nif) == confirmado, nif
        if ficha.get("confirmado") and ficha.get("nombre") and not clientes._roto(ficha["nombre"]):
            esperado = ficha["nombre"].strip()
        else:
            esperado = suite.nombre_de(clientes._normaliza(nif))
        assert directorio.nombre_confirmado(nif) == esperado, nif


def test_el_indice_de_nombres_se_rehace_solo_si_cambian_los_clientes(monkeypatch):
    from facturas_excel import clientes
    _clientes_inventados()
    assert clientes.Directorio().buscar_por_nombre("Socio Inventado 0003")
    normalizados = _contar(monkeypatch, clientes, "_clave_nombre")
    assert clientes.Directorio().buscar_por_nombre("Socio Inventado 0004")[0] == "ZZSUITE0004"
    assert len(normalizados) == 1                      # solo el nombre buscado
    clientes.marcar_cliente("ZZNUEVO", "CLIENTE NUEVO INVENTADO")
    assert clientes.Directorio().buscar_por_nombre("Cliente nuevo inventado") == (
        "ZZNUEVO", "CLIENTE NUEVO INVENTADO")


def test_analizar_el_lote_lee_los_clientes_y_proveedores_una_vez(monkeypatch):
    from facturas_excel import clientes, procesar, proveedores
    _clientes_inventados()
    lecturas = [d for d, _segunda in _lecturas(80)]
    antes = procesar.analizar_cliente(lecturas)
    leidas_clientes = _contar(monkeypatch, clientes, "_leer_todo")
    leidas_proveedores = _contar(monkeypatch, proveedores, "leer_todo")
    ahora = procesar.analizar_cliente(lecturas)
    assert len(leidas_clientes) == 1 and len(leidas_proveedores) == 1   # antes, cientos
    assert ahora == antes


# ------------------------------------------ muestras de revisión, sin agobiar
def test_la_muestra_automatica_va_como_mucho_una_por_minuto(tmp_path, monkeypatch):
    from facturas_excel import app, muestras_revision
    from facturas_excel.tabla_facturas import C_BASE
    reloj = [1000.0]
    monkeypatch.setattr(app.time, "monotonic", lambda: reloj[0])
    fotos = _contar(monkeypatch, muestras_revision, "guardar_revision")
    v = _ventana_con_lote(tmp_path, 60)
    # Leer los bloques ya no hace una foto entera del lote por cada uno.
    assert fotos == []
    v._guardar_muestra_revision_automatica()            # la primera, al momento
    assert len(fotos) == 1
    for segundos in (5, 20, 40):
        reloj[0] = 1000.0 + segundos
        v.tabla.item(segundos, C_BASE).setText("12,34")
        v._guardar_muestra_revision_automatica()
    assert len(fotos) == 1
    # Queda pendiente para cuando se cumpla el minuto (desde el primer
    # cambio: no se aplaza con los siguientes), con lo último.
    assert v._timer_muestra_minuto.isActive()
    assert 50_000 <= v._timer_muestra_minuto.remainingTime() <= 55_001
    reloj[0] = 1061.0
    v._timer_muestra_minuto.stop()
    v._guardar_muestra_revision_automatica()
    assert len(fotos) == 2
    assert v.filas[40].factura.base_iva == 12.34
    assert any(f["factura"].base_iva == 12.34 for f in fotos[-1][0])
    # Antes de algo que no se puede deshacer, al momento aunque no haya
    # pasado el minuto.
    reloj[0] = 1062.0
    v._guardar_muestra_revision()
    assert len(fotos) == 3


def test_la_muestra_se_guarda_en_json_compacto(tmp_path):
    import json
    from facturas_excel import muestras_revision
    v = _ventana_con_lote(tmp_path, 30)
    v._guardar_muestra_revision()
    fotos = list((muestras_revision.carpeta() / "revisiones").glob("*.json"))
    assert len(fotos) == 1
    texto = fotos[0].read_text(encoding="utf-8")
    assert "\n" not in texto and ", " not in texto.split('"filas"')[0]
    assert len(json.loads(texto)["filas"]) == len(v.filas)
    # La misma foto otra vez no se repite.
    v._guardar_muestra_revision()
    assert len(list((muestras_revision.carpeta() / "revisiones").glob("*.json"))) == 1
