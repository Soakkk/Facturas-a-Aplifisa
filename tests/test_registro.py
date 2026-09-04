"""Contraste con el listado de apuntes de Aplifisa.

El cuadre a tres bandas: factura escaneada -> Excel -> lo que quedo registrado.
El listado de Aplifisa es un PDF con texto, asi que se lee sin IA y sin coste.
"""

import fitz
import pytest

from facturas_excel.modelo import Factura
from facturas_excel.registro import contrastar, leer_registro

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
