"""Exportar sin dejar la ventana parada (taco de 450 hojas, 800 líneas).

Antes, con 800 líneas, la ventana se quedaba 19 s sin responder al exportar:
casi todo era el archivo del cliente (un PDF por factura y el expediente).
Aquí se comprueba que lo que lo hace más rápido no cambia lo que se guarda.
Solo datos inventados.
"""
import os
import zipfile

import fitz
from PySide6.QtWidgets import QApplication

from facturas_excel import archivo, expediente

_app = QApplication.instance() or QApplication([])

CLIENTE = ("TALLERES PRUEBA SL", "B12345674")


def _hoja_escaneada(doc, semilla):
    """Una hoja como las del escáner: una foto JPEG que ocupa la página."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 170), False)
    pix.set_rect(pix.irect, ((semilla * 37) % 256, (semilla * 91) % 256, 200))
    pix.set_rect(fitz.IRect(10, 10 + semilla % 100, 110, 30 + semilla % 100),
                 (20, 20, 20))
    pagina = doc.new_page(width=595, height=842)
    pagina.insert_image(pagina.rect, stream=pix.tobytes("jpeg"))
    return pagina


def _pdf_escaneado(ruta, semillas):
    doc = fitz.open()
    for s in semillas:
        _hoja_escaneada(doc, s)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    doc.save(ruta)
    doc.close()
    return ruta


def _archivo_con_facturas(base, n_gastos=3, n_ingresos=2):
    gastos = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "gastos", base, nif=CLIENTE[1])
    ingresos = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "ingresos", base, nif=CLIENTE[1])
    for i in range(n_gastos):
        _pdf_escaneado(os.path.join(gastos, f"2026-02-{i + 10} PROVEEDOR G-{i}.pdf"), [i])
    for i in range(n_ingresos):
        _pdf_escaneado(os.path.join(ingresos, f"2026-03-{i + 10} CLIENTE V-{i}.pdf"),
                       [50 + i])
    excel = os.path.join(os.path.dirname(gastos), "Excel Aplifisa")
    os.makedirs(excel, exist_ok=True)
    from openpyxl import Workbook
    libro = Workbook()
    libro.active.append(["10/02/2026", "G-0", 100])
    libro.save(os.path.join(excel, "GASTOS 2026 2026-03-31 101010.xlsx"))
    [e] = expediente.listar(base)
    return e


# ---------------------------------------------------------------- 1. ZIP
def test_el_zip_del_expediente_guarda_los_pdf_y_excel_sin_recomprimir(tmp_path):
    """Los PDF son fotos JPEG y el .xlsx ya es un ZIP: comprimirlos otra vez
    costaba 9 s con 450 hojas y no ahorraba casi nada."""
    base = str(tmp_path / "archivo")
    e = _archivo_con_facturas(base)
    r = expediente.crear(base, e)

    carpeta = os.path.dirname(r["carpeta"])
    with zipfile.ZipFile(r["zip"]) as z:
        assert z.testzip() is None
        entradas = z.infolist()
        assert sorted(i.filename for i in entradas) == [
            "Expediente 2026/Excel Aplifisa/GASTOS 2026 2026-03-31 101010.xlsx",
            "Expediente 2026/Gastos 2026.pdf",
            "Expediente 2026/Ingresos 2026.pdf",
            "Expediente 2026/Resumen 2026.pdf"]
        for info in entradas:
            assert info.compress_type == zipfile.ZIP_STORED, info.filename
            # Lo que va dentro es exactamente lo que hay en la carpeta.
            with open(os.path.join(carpeta, info.filename), "rb") as fh:
                assert z.read(info) == fh.read()


# ------------------------------------------- 2. separar sin dibujar hojas
def _f(num, nombre, fecha, origen, pag, doc=""):
    from facturas_excel.modelo import Factura
    return Factura(num_factura=num, nombre=nombre, fecha=fecha, nif="12345678Z",
                   base_iva=100, pct_iva=21, cuota_iva=21, total_impreso=121,
                   origen_imagen=origen, pagina_origen=pag, ultima_pagina_origen=pag,
                   documento_id=doc or num)


def _contar_dibujos(monkeypatch):
    """Cada vez que se dibuja una hoja (lo que hacía lenta la comparación)."""
    dibujos = []
    original = fitz.Page.get_pixmap

    def contar(self, *a, **k):
        dibujos.append(self.number)
        return original(self, *a, **k)
    monkeypatch.setattr(fitz.Page, "get_pixmap", contar)
    return dibujos


def _taco_escaneado(base, hojas):
    carpeta = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "gastos", base, nif=CLIENTE[1])
    return _pdf_escaneado(os.path.join(carpeta, "taco.pdf"), range(1, hojas + 1))


def test_separar_no_dibuja_las_hojas_para_saber_si_ya_estaban(tmp_path, monkeypatch):
    """Dibujar cada hoja en pequeño para compararla costaba 4,4 s con 400
    facturas. La primera vez no hay nada con qué comparar; la segunda, las
    hojas copiadas tal cual se reconocen sin dibujarlas."""
    from facturas_excel import separar
    base = str(tmp_path / "archivo")
    taco = _taco_escaneado(base, 3)
    facturas = [_f(f"G-{i}", "PROVEEDOR", "12/02/2026", taco, i) for i in (1, 2, 3)]
    dibujos = _contar_dibujos(monkeypatch)

    primera = separar.separar({"gasto": facturas}, base, *CLIENTE)
    assert len(primera["creados"]) == 3 and dibujos == []

    movido = primera["tacos"][taco]           # el taco se apartó intacto
    for f in facturas:
        f.origen_imagen = movido
    segunda = separar.separar({"gasto": facturas}, base, *CLIENTE)
    assert (segunda["creados"], segunda["ya_estaban"]) == ([], 3)
    assert dibujos == []
    assert [r for _t, _f2, r in segunda["pdfs"]] == [r for _t, _f2, r in primera["pdfs"]]


def test_el_mismo_pdf_guardado_de_otra_manera_sigue_siendo_el_mismo(tmp_path):
    """Si los bytes no coinciden (otra versión u otro programa lo volvió a
    guardar) pero las hojas se ven igual, sigue siendo «el mismo PDF», como
    cuando se comparaban dibujadas: no se crea un «(2)»."""
    from facturas_excel import separar
    base = str(tmp_path / "archivo")
    taco = _taco_escaneado(base, 1)
    f = _f("G-1", "PROVEEDOR", "12/02/2026", taco, 1)
    [ruta] = separar.separar({"gasto": [f]}, base, *CLIENTE)["creados"]
    with fitz.open(ruta) as doc:
        pagina = doc[0]
        doc.update_stream(pagina.get_contents()[0], b"q Q\n" + pagina.read_contents())
        doc.save(ruta + ".otro")
    os.replace(ruta + ".otro", ruta)

    f.origen_imagen = os.path.join(os.path.dirname(os.path.dirname(ruta)),
                                   separar.TACOS, "taco.pdf")
    r = separar.separar({"gasto": [f]}, base, *CLIENTE)
    assert (r["creados"], r["ya_estaban"]) == ([], 1)
    assert sorted(os.listdir(os.path.dirname(ruta))) == [os.path.basename(ruta)]


def test_otra_hoja_escaneada_con_el_mismo_nombre_tiene_su_pdf(tmp_path):
    """Dos tiques sin número del mismo proveedor y día, en dos exportaciones:
    son fotos distintas, así que el segundo lleva « (2)» y no se pisa."""
    from facturas_excel import separar
    base = str(tmp_path / "archivo")
    taco = _taco_escaneado(base, 2)
    [primero] = separar.separar(
        {"gasto": [_f("", "GASOLINERA", "12/02/2026", taco, 1, doc="t1")]},
        base, *CLIENTE)["creados"]
    movido = os.path.join(os.path.dirname(os.path.dirname(primero)), separar.TACOS,
                          "taco.pdf")
    r = separar.separar(
        {"gasto": [_f("", "GASOLINERA", "12/02/2026", movido, 2, doc="t2")]},
        base, *CLIENTE)
    [segundo] = r["creados"]
    assert segundo.endswith(" (2).pdf") and r["ya_estaban"] == 0
    with fitz.open(primero) as a, fitz.open(segundo) as b:
        assert a[0].get_images()[0][0] and \
            a.xref_stream_raw(a[0].get_images()[0][0]) != \
            b.xref_stream_raw(b[0].get_images()[0][0])
