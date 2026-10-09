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
