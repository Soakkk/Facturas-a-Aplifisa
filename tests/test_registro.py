"""Contraste con el listado de apuntes de Aplifisa.

El cuadre a tres bandas: factura escaneada -> Excel -> lo que quedo registrado.
El listado de Aplifisa es un PDF con texto, asi que se lee sin IA y sin coste.
"""

import fitz
import pytest

from facturas_excel.modelo import Factura
from facturas_excel.registro import Registro, contrastar, leer_registro

# Un listado como el que imprime Aplifisa (mismo orden de columnas y totales).
LISTADO = """LISTADO DE APUNTES DE COMPRAS DESGLOSADOS
Fecha
Factura
Cto.
Cuenta
Base I.V.A.
Cuota
Recargo
I.R.P.F.
Imp. Neto GD
1
31/01/2025
628
20
1,54
0,15
AREA DE SERVICIOS DE EJEMPLO SL
1,69
2
28/02/2025
628
20
140,56
29,52
AREA DE SERVICIOS DE EJEMPLO SL
170,08
3
31/03/2025
629
20
1.048,25
220,13
GESTORIA DE EJEMPLO SL
1.268,38
TOTAL DE PAGINA ..........
TOTAL ACUMULADO .......
1.190,35
1.190,35
249,80
249,80
1.440,15
1.440,15
"""


@pytest.fixture
def listado(tmp_path):
    """El listado, en un PDF con capa de texto como el de Aplifisa."""
    ruta = tmp_path / "registro.pdf"
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((40, 40), LISTADO, fontsize=8)
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


def factura(fecha, base, cuota, nombre="AREA DE SERVICIOS DE EJEMPLO SL"):
    return Factura(num_factura="FA-1", fecha=fecha, nombre=nombre,
                   nif="B12345674", concepto="628", base_iva=base,
                   pct_iva=21.0, cuota_iva=cuota)


def test_se_leen_los_apuntes_y_cuadran_con_sus_propios_totales(listado):
    r = leer_registro(listado)

    assert len(r.apuntes) == 3
    assert r.suma_base == r.total_base == 1190.35
    assert r.suma_cuota == r.total_cuota == 249.80
    assert r.bien_leido           # el listado se comprueba contra si mismo
    assert r.apuntes[0].nombre == "AREA DE SERVICIOS DE EJEMPLO SL"
    assert r.apuntes[2].concepto == "629"


def test_si_todo_esta_registrado_no_hay_diferencias(listado):
    r = leer_registro(listado)
    facturas = [factura(a.fecha, a.base, a.cuota, a.nombre) for a in r.apuntes]

    informe = contrastar(facturas, r)

    assert informe.todo_cuadra
    assert informe.emparejadas == 3
    assert informe.descuadre_base == 0


def test_una_factura_que_no_llego_a_registrarse_se_ve(listado):
    r = leer_registro(listado)
    facturas = [factura(a.fecha, a.base, a.cuota, a.nombre) for a in r.apuntes]
    facturas.append(factura("30/04/2025", 500.0, 105.0))   # esta no esta alli

    informe = contrastar(facturas, r)

    assert len(informe.sin_registrar) == 1
    assert "30/04/2025" in informe.sin_registrar[0]
    assert informe.descuadre_base == 500.0
    assert not informe.todo_cuadra


def test_un_apunte_de_mas_en_aplifisa_se_ve(listado):
    r = leer_registro(listado)
    facturas = [factura(a.fecha, a.base, a.cuota, a.nombre)
                for a in r.apuntes[:2]]          # falta la tercera en el lote

    informe = contrastar(facturas, r)

    assert len(informe.de_mas) == 1
    assert "GESTORIA" in informe.de_mas[0]


def test_una_registrada_con_otro_iva_se_dice_cual(listado):
    r = leer_registro(listado)
    facturas = [factura(a.fecha, a.base, a.cuota, a.nombre) for a in r.apuntes]
    facturas[0].cuota_iva = 0.99                 # en Aplifisa figura 0,15

    informe = contrastar(facturas, r)

    assert len(informe.distintas) == 1
    assert "0,15" in informe.distintas[0]
    assert not informe.sin_registrar             # no es que falte: es distinta


def test_un_pdf_sin_apuntes_no_revienta(tmp_path):
    ruta = tmp_path / "otro.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((40, 40), "Esto no es un listado", fontsize=10)
    doc.save(str(ruta))
    doc.close()

    r = leer_registro(str(ruta))
    assert r.apuntes == []


# ------------------------------------------ el listado no se manda a Gemini --
def test_se_reconoce_el_listado_de_aplifisa(listado, tmp_path):
    """Si se cuela como facturas se paga por leer un papel que aqui es gratis."""
    from facturas_excel.registro import parece_listado

    assert parece_listado(listado)

    otro = tmp_path / "factura.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((40, 40), "FACTURA Nº 123\nTotal 121,00",
                               fontsize=10)
    doc.save(str(otro))
    doc.close()
    assert not parece_listado(str(otro))


def test_soltar_el_listado_no_lo_manda_a_gemini(listado, monkeypatch, tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox

    from facturas_excel.app import VentanaPrincipal

    QApplication.instance() or QApplication([])
    v = VentanaPrincipal(comprobar_updates=False)
    llamadas = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: llamadas.append(a[2])))
    monkeypatch.setattr(v, "_contrastar_registro",
                        lambda ruta="": llamadas.append("contraste"))

    v.procesar_rutas([listado])          # con el lote vacio

    # Ni Worker ni Gemini: solo dice que primero hay que cargar las facturas.
    assert not getattr(v, "worker", None)
    assert llamadas and "listado de apuntes" in llamadas[0]


# ------------------------------- el listado "IVA - Facturas recibidas" -------
# Es el que se saca para un requerimiento. Sus columnas se solapan al leer el
# texto seguido y una linea de suplido trae menos importes que las demas, asi
# que se lee por la posicion de cada palabra.
COLUMNAS_RECIBIDAS = [
    (20, "Orden"), (44, "Fecha"), (80, "Nºfact.rec."), (110, "Serie"),
    (128, "Nºfra.proveedor"), (178, "Identificación"),
    (330, "Base IVA"), (366, "%"), (393, "Cuota IVA"),
    (437, "Base R.Eq."), (479, "%"), (500, "Cuota R.Eq."), (540, "Base + Cuota"),
]
# orden, fecha, nº fact.rec., nº del proveedor, nif y nombre, base, %, cuota, total
FILAS_RECIBIDAS = [
    ("1", "31/01/2025", "1", "FA-338", "B12345674 PROVEEDOR DE EJEMPLO SL",
     "1,54", "10,00", "0,15", "1,69"),
    ("2", "31/01/2025", "1", "FA-338", "B12345674 PROVEEDOR DE EJEMPLO SL",
     "140,56", "21,00", "29,52", "170,08"),
    ("3", "28/02/2025", "2", "FA-739", "B12345674 PROVEEDOR DE EJEMPLO SL",
     "72,79", "21,00", "15,29", "88,08"),
    # Un suplido: base sin IVA, sin % ni cuota. Aqui se rompia la lectura.
    ("4", "13/11/2025", "3", "25 / 5.887", "B12345675 GESTORIA DE EJEMPLO",
     "109,08", "", "", "109,08"),
]


@pytest.fixture
def listado_recibidas(tmp_path):
    """El listado de facturas recibidas, con sus columnas en su sitio."""
    ruta = tmp_path / "recibidas.pdf"
    doc = fitz.open()
    pagina = doc.new_page()
    for x, texto in COLUMNAS_RECIBIDAS:
        pagina.insert_text((x, 92), texto, fontsize=6)
    y = 104
    for orden, fecha, rec, prov, quien, base, pct, cuota, total in FILAS_RECIBIDAS:
        pagina.insert_text((31, y), orden, fontsize=6)
        pagina.insert_text((41, y), fecha, fontsize=6)
        pagina.insert_text((101, y), rec, fontsize=6)
        pagina.insert_text((128, y), prov, fontsize=6)
        pagina.insert_text((178, y), quien, fontsize=6)
        for x, valor in ((337, base), (361, pct), (405, cuota), (560, total)):
            if valor:
                pagina.insert_text((x, y), valor, fontsize=6)
        y += 10
    pagina.insert_text((332, y + 20), "323,97", fontsize=6)
    pagina.insert_text((398, y + 20), "44,96", fontsize=6)
    pagina.insert_text((554, y + 20), "368,93", fontsize=6)
    pagina.insert_text((215, y + 22), "TOTAL ACUMULADO:", fontsize=6)
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


def test_se_lee_el_listado_de_facturas_recibidas(listado_recibidas):
    r = leer_registro(listado_recibidas)

    assert len(r.apuntes) == 4
    assert r.bien_leido                       # cuadra con sus propios totales
    assert r.suma_base == r.total_base == 323.97
    assert r.suma_cuota == r.total_cuota == 44.96
    # El nº que interesa para el requerimiento es el de factura recibida.
    assert [a.numero for a in r.apuntes] == ["1", "1", "2", "3"]
    assert r.apuntes[0].nombre == "PROVEEDOR DE EJEMPLO SL"   # sin el NIF delante


def test_el_suplido_se_lee_como_base_sin_iva(listado_recibidas):
    """Antes se colaba el % en la base y el listado entero descuadraba."""
    r = leer_registro(listado_recibidas)

    suplido = r.apuntes[-1]
    assert suplido.base == 109.08
    assert suplido.cuota is None
    assert r.apuntes[0].base == 1.54 and r.apuntes[0].cuota == 0.15


# --------------------------- listados fiscales anuales actuales de Aplifisa --
# Estas maquetas reproducen la geometría de listados reales facilitados por el
# usuario, pero todos los datos son ficticios y quedan protegidos por pruebas.
def _insertar(pagina, y, *valores):
    for x, texto in valores:
        if texto not in (None, ""):
            pagina.insert_text((x, y), str(texto), fontsize=5)


@pytest.fixture
def listado_anual_gastos(tmp_path):
    ruta = tmp_path / "gastos-anual.pdf"
    doc = fitz.open()
    pagina = doc.new_page(width=842, height=595)
    pagina.insert_text((350, 55), "Compras y gastos / Facturas recibidas",
                       fontsize=7)
    cabecera = (
        (34, "Orden"), (55, "Fecha"), (90, "Nºfra.rec."),
        (133, "Nºfra.proveedor"), (178, "Rt"), (190, "Identificación"),
        (325, "Concepto"), (437, "Base"), (452.7, "IVA"), (476, "%"),
        (503, "Cuota"), (521, "IVA"), (539, "Base"), (554.7, "R."),
        (562.6, "Equiv."), (590, "%"), (608, "Cuota"),
        (626, "R.Equiv."), (650, "Imputable"), (678.7, "a"),
        (683.8, "IRPF"), (704, "Base"), (719.7, "retención"),
        (754, "%"), (774, "Cuota"), (792, "retenida"),
    )
    _insertar(pagina, 82, *cabecera)
    filas = (
        ("1", "15/01/2026", "1", "FA-100", "B12345674", "PROVEEDOR UNO SL",
         "COMPRAS", "100,00", "21,00", "21,00", "100,00", "5,20", "100,00", "15,00"),
        ("2", "15/01/2026", "1", "FA-100", "B12345674", "PROVEEDOR UNO SL",
         "COMPRAS", "50,00", "10,00", "5,00", "", "", "50,00", ""),
        ("3", "20/02/2026", "2", "FA-200", "B12345675", "PROVEEDOR DOS SA",
         "SERVICIOS", "200,00", "21,00", "42,00", "", "", "200,00", ""),
    )
    for y, fila in zip((94, 106, 118), filas):
        orden, fecha, recibido, proveedor, nif, nombre, concepto, base, pct, iva, bre, req, birpf, irpf = fila
        _insertar(pagina, y,
                  (47, orden), (53, fecha), (114, recibido), (133, proveedor),
                  (188, nif), (215, nombre), (325, concepto), (446, base),
                  (468, pct), (518, iva), (548, bre), (618, req),
                  (680, birpf), (784, irpf))
    _insertar(pagina, 145, (272, "TOTAL"), (293, "ACUMULADO"),
              (436, "350,00"), (508, "68,00"), (608, "5,20"),
              (774, "15,00"))
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


@pytest.fixture
def listado_anual_ingresos(tmp_path):
    ruta = tmp_path / "ingresos-anual.pdf"
    doc = fitz.open()
    pagina = doc.new_page(width=595, height=842)
    pagina.insert_text((250, 55), "Ventas e ingresos", fontsize=7)
    cabecera = (
        (20, "Orden"), (44, "Fecha"), (92, "Nºfactura"),
        (127, "Identificación"), (165, "del"), (175, "cliente"),
        (267, "Concepto"), (370, "Base"), (386, "IVA"),
        (410, "Cuota"), (428, "IVA"), (467, "Suma"),
        (507, "Base"), (523, "Imp."), (545, "Reten."), (565, "IRPF"),
    )
    _insertar(pagina, 82, *cabecera)
    _insertar(pagina, 94, (34, "1"), (41, "15/01/2026"), (116, "V-100"),
              (124, "B12345674"), (151, "CLIENTE UNO SL"),
              (265, "SERVICIOS"), (372, "100,00"), (419, "21,00"),
              (462, "121,00"), (511, "100,00"), (563, "1,00"))
    _insertar(pagina, 106, (34, "2"), (41, "20/02/2026"), (116, "V-200"),
              (124, "B12345675"), (151, "CLIENTE DOS SA"),
              (265, "SERVICIOS"), (372, "200,00"), (419, "42,00"),
              (462, "242,00"), (511, "200,00"), (563, "2,00"))
    # En el original los importes acumulados están en la línea anterior.
    _insertar(pagina, 140, (369, "300,00"), (415, "63,00"),
              (459, "363,00"), (508, "300,00"), (560, "3,00"))
    _insertar(pagina, 143, (252, "TOTAL"), (281, "ACUMULADO:"))
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


def test_lee_columnas_del_listado_anual_de_gastos(listado_anual_gastos):
    r = leer_registro(listado_anual_gastos)

    assert r.tipo == "gasto"
    assert len(r.apuntes) == 3 and r.facturas == 2
    assert r.apuntes[0].num_factura_proveedor == "FA-100"
    assert r.apuntes[0].nif == "B12345674"
    assert r.apuntes[0].nombre == "PROVEEDOR UNO SL"
    assert (r.suma_base, r.suma_cuota, r.suma_recargo, r.suma_irpf) == (
        350.0, 68.0, 5.2, 15.0)
    assert r.bien_leido


def test_una_factura_con_fecha_distinta_se_localiza(listado_anual_gastos):
    r = leer_registro(listado_anual_gastos)
    a = r.apuntes[0]
    f = Factura(
        num_factura=a.num_factura_proveedor, fecha="30/01/2026",
        nombre=a.nombre, nif=a.nif, base_iva=a.base, pct_iva=a.pct_iva,
        cuota_iva=a.cuota, base_requiv=a.base_recargo,
        cuota_requiv=a.recargo, base_irpf=a.base_irpf, cuota_irpf=a.irpf,
    )

    informe = contrastar([f], Registro(apuntes=[a]))

    assert len(informe.distintas) == 1
    assert "Fecha:" in informe.distintas[0]


def test_lee_columnas_y_retenciones_del_listado_anual_de_ingresos(
        listado_anual_ingresos):
    r = leer_registro(listado_anual_ingresos)

    assert r.tipo == "venta"
    assert len(r.apuntes) == r.facturas == 2
    assert r.apuntes[0].nombre == "CLIENTE UNO SL"
    assert (r.suma_base, r.suma_cuota, r.suma_irpf) == (300.0, 63.0, 3.0)
    assert r.suma_neto == r.total_neto == 360.0
    assert r.bien_leido


def test_el_irpf_del_listado_de_ingresos_cuadra_tambien_el_total(
        listado_anual_ingresos):
    r = leer_registro(listado_anual_ingresos)
    facturas = []
    for apunte in r.apuntes:
        f = Factura(
            num_factura=apunte.numero, fecha=apunte.fecha,
            nombre=apunte.nombre, nif=apunte.nif, concepto="705",
            base_iva=apunte.base, pct_iva=21, cuota_iva=apunte.cuota,
            base_irpf=apunte.base_irpf, pct_irpf=1, cuota_irpf=apunte.irpf,
            total_impreso=apunte.neto,
        )
        facturas.append(f)

    informe = contrastar(facturas, r)

    assert informe.todo_cuadra
    assert informe.descuadre_irpf == informe.descuadre_total == 0
    assert (informe.facturas_programa, informe.lineas_programa) == (2, 2)


# --- «Listado de apuntes de compras desglosados», leído por filas ----------
# Como lo imprime Aplifisa: una línea por apunte, importes alineados a la
# derecha en su columna y alguna factura sin número (se metió después).

def _derecha(pagina, x_fin, y, texto, tam=7):
    pagina.insert_text((x_fin - fitz.get_text_length(texto, fontsize=tam), y),
                       texto, fontsize=tam)


def _listado_por_filas(ruta, filas, totales, titulo="COMPRAS"):
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((112, 125), f"LISTADO DE APUNTES DE {titulo} DESGLOSADOS",
                       fontsize=9)
    for x, texto in ((30, "Fecha"), (86, "Factura"), (136, "Cto."),
                     (218, "Cuenta"), (317, "Base"), (341, "I.V.A."),
                     (377, "Cuota"), (419, "Recargo"), (469, "I.R.P.F."),
                     (514, "Imp."), (535, "Neto"), (561, "GD")):
        pagina.insert_text((x, 152), texto, fontsize=7)
    y = 168
    for numero, fecha, cto, cuenta, nombre, base, cuota, neto in filas:
        pagina.insert_text((17, y), fecha, fontsize=7)
        if numero:
            _derecha(pagina, 137, y, numero)
        pagina.insert_text((139, y), cto, fontsize=7)
        pagina.insert_text((169, y), cuenta, fontsize=7)
        pagina.insert_text((179, y), nombre, fontsize=7)
        _derecha(pagina, 369, y, base)
        if cuota:
            _derecha(pagina, 415, y, cuota)
        _derecha(pagina, 563, y, neto)
        y += 14
    for desplazamiento, etiqueta in ((0, "TOTAL DE PAGINA .........."),
                                     (18, "TOTAL ACUMULADO .......")):
        for x_fin, valor in zip((366, 413, 561), totales):
            _derecha(pagina, x_fin, y + 10 + desplazamiento, valor)
        pagina.insert_text((209, y + 13 + desplazamiento), etiqueta, fontsize=7)
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


FILAS = [
    ("29", "02/06/2026", "622", "51", "PROVEEDOR UNO SL", "400,00", "84,00", "484,00"),
    ("44", "08/06/2026", "628", "89", "TELECOM PRUEBA SA", "90,00", "18,90", "108,90"),
    ("44", "08/06/2026", "628", "89", "TELECOM PRUEBA SA", "12,00", "", "12,00"),
    ("40", "20/06/2026", "628", "18", "GASOLINERA PRUEBA", "30,00", "3,00", "33,00"),
    ("", "23/06/2026", "681", "89", "TELECOM PRUEBA SA", "700,00", "147,00", "847,00"),
    ("7", "09/07/2026", "628", "89", "TELECOM PRUEBA SA", "80,00", "16,80", "96,80"),
    ("7", "17/07/2026", "628", "28", "COMBUSTIBLES PRUEBA SL", "1.500,00", "315,00", "1.815,00"),
    ("23", "20/09/2026", "628", "18", "GASOLINERA PRUEBA", "20,00", "4,20", "24,20"),
]
TOTALES = ("2.832,00", "588,90", "3.420,90")


def test_listado_por_filas_con_una_factura_sin_numero(tmp_path):
    """La del 23/06 no lleva número: antes el total de la línea anterior
    (33,00) pasaba a ser su número y a esa le faltaba el IVA, y el propio
    listado «no cuadraba»."""
    r = leer_registro(_listado_por_filas(tmp_path / "compras.pdf", FILAS, TOTALES))
    assert r.tipo == "gasto"
    assert len(r.apuntes) == len(FILAS)
    assert r.bien_leido, r.diferencias_totales
    assert (r.suma_base, r.suma_cuota, r.suma_neto) == (2832.0, 588.9, 3420.9)
    gasolinera = r.apuntes[3]
    assert (gasolinera.numero, gasolinera.cuota, gasolinera.neto) == ("40", 3.0, 33.0)
    sin_numero = r.apuntes[4]
    assert (sin_numero.numero, sin_numero.fecha, sin_numero.base) == ("", "23/06/2026", 700.0)
    assert sin_numero.concepto == "681" and sin_numero.nombre == "TELECOM PRUEBA SA"
    assert r.apuntes[2].cuota is None and r.apuntes[2].neto == 12.0
    # Mismo número en facturas distintas (7) y dos líneas de una (44).
    assert r.facturas == 7
    from datetime import date
    assert r.periodo == (date(2026, 6, 1), date(2026, 9, 30))


def test_un_listado_de_ventas_es_de_ventas(tmp_path):
    r = leer_registro(_listado_por_filas(tmp_path / "ventas.pdf", FILAS[:1],
                                         ("400,00", "84,00", "484,00"),
                                         titulo="VENTAS"))
    assert r.tipo == "venta" and r.bien_leido


def test_se_comparan_los_gastos_de_las_fechas_del_listado(tmp_path):
    from facturas_excel.registro import contrastar_listado
    r = leer_registro(_listado_por_filas(tmp_path / "compras.pdf", FILAS, TOTALES))
    lote = [factura(a.fecha, a.base, a.cuota, a.nombre) for a in r.apuntes]
    tipos = ["gasto"] * len(lote)
    lote.append(factura("30/06/2026", 500.0, 105.0, "CLIENTE PRUEBA SL"))
    tipos.append("venta")                       # un ingreso
    lote.append(factura("31/05/2026", 200.0, 42.0, "OTRO PROVEEDOR SL"))
    tipos.append("gasto")                       # de antes del listado
    lote.append(factura("15/08/2026", 60.0, 12.6, "FALTA PRUEBA SL"))
    tipos.append("gasto")                       # esta sí falta en Aplifisa

    informe = contrastar_listado(lote, tipos, r)
    assert informe.sin_registrar and len(informe.sin_registrar) == 1
    assert informe.resultados[len(lote) - 1] == "sin_registrar"
    assert informe.no_comprobadas == [len(FILAS), len(FILAS) + 1]
    assert len(FILAS) not in informe.resultados
    assert informe.emparejadas == len(FILAS)
    assert "del 01/06/2026 al 30/09/2026" in informe.ambito
    assert "1 ingresos no entran" in informe.ambito.replace("Los ", "")
    assert "1 gastos del lote son de otras fechas" in informe.ambito
