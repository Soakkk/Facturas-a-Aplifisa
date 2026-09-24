"""Un PDF por factura al exportar, con el taco original apartado."""
import os

import fitz
from PySide6.QtWidgets import QApplication, QDialog

from facturas_excel import archivo, separar
from facturas_excel.modelo import Factura

_app = QApplication.instance() or QApplication([])

CLIENTE = ("TALLERES PRUEBA SL", "B12345674")


def _taco(ruta, paginas):
    doc = fitz.open()
    for i in range(paginas):
        doc.new_page().insert_text((72, 72), f"hoja {i + 1}")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    doc.save(ruta)
    doc.close()
    return ruta


def _texto(ruta):
    with fitz.open(ruta) as doc:
        return [p.get_text().strip() for p in doc]


def _f(num, nombre, fecha, origen, pag, ultima=None, doc="", **extra):
    datos = dict(num_factura=num, nombre=nombre, fecha=fecha, nif="12345678Z",
                 base_iva=100, pct_iva=21, cuota_iva=21, total_impreso=121,
                 origen_imagen=origen, pagina_origen=pag,
                 ultima_pagina_origen=ultima or pag, documento_id=doc or num)
    datos.update(extra)
    return Factura(**datos)


def test_cada_factura_a_su_pdf_su_ejercicio_y_su_tipo(tmp_path):
    base = str(tmp_path / "archivo")
    carpeta = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "gastos", base, nif=CLIENTE[1])
    taco = _taco(os.path.join(carpeta, "TALLERES_gastos_2026-03-01.pdf"), 4)
    dos_lineas = [_f("F/2", "TALLER MECANICO", "19/02/2026", taco, 2, 3, doc="d2"),
                  _f("F/2", "TALLER MECANICO", "19/02/2026", taco, 2, 3, doc="d2",
                     pct_iva=10)]
    exportadas = {
        "gasto": [_f("G-118", "GASOLINERA EJEMPLO SL", "12/02/2026", taco, 1)] + dos_lineas,
        "venta": [_f("V-33", "CLIENTE FINAL SA", "30/12/2025", taco, 4)],
    }
    r = separar.separar(exportadas, base, *CLIENTE)
    nombres = sorted(os.path.relpath(c, base) for c in r["creados"])
    raiz = f"{CLIENTE[0]} — {CLIENTE[1]}"
    assert nombres == [
        os.path.join(raiz, "2025", "Ingresos", "2025-12-30 CLIENTE FINAL SA V-33.pdf"),
        os.path.join(raiz, "2026", "Gastos", "2026-02-12 GASOLINERA EJEMPLO SL G-118.pdf"),
        os.path.join(raiz, "2026", "Gastos", "2026-02-19 TALLER MECANICO F 2.pdf"),
    ]
    taller = next(c for c in r["creados"] if "TALLER MECANICO" in os.path.basename(c))
    assert _texto(taller) == ["hoja 2", "hoja 3"]          # sus dos hojas, una vez
    # El taco se aparta intacto y ya no está entre las facturas.
    [(viejo, nuevo)] = r["tacos"].items()
    assert viejo == taco and not os.path.exists(taco)
    assert os.path.basename(os.path.dirname(nuevo)) == "Tacos escaneados"
    assert len(_texto(nuevo)) == 4
    assert r["afectados"] == {2025, 2026}


def test_no_se_duplica_si_ya_se_habia_separado(tmp_path):
    base = str(tmp_path / "archivo")
    carpeta = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "gastos", base, nif=CLIENTE[1])
    taco = _taco(os.path.join(carpeta, "taco.pdf"), 1)
    f = _f("G-1", "GASOLINERA", "12/02/2026", taco, 1)
    separar.separar({"gasto": [f]}, base, *CLIENTE)
    f.origen_imagen = os.path.join(carpeta, "..", "Tacos escaneados", "taco.pdf")
    r = separar.separar({"gasto": [f]}, base, *CLIENTE)
    assert (r["creados"], r["ya_estaban"]) == ([], 1)


def test_hojas_unidas_a_mano_de_dos_archivos(tmp_path):
    base = str(tmp_path / "archivo")
    carpeta = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "gastos", base, nif=CLIENTE[1])
    a = _taco(os.path.join(carpeta, "a.pdf"), 3)
    b = _taco(os.path.join(carpeta, "b.pdf"), 2)
    f = _f("M-1", "PROVEEDOR", "01/03/2026", a, 3,
           paginas_documento=((a, 3), (b, 1)))
    r = separar.separar({"gasto": [f]}, base, *CLIENTE)
    assert _texto(r["creados"][0]) == ["hoja 3", "hoja 1"]
    assert set(r["tacos"]) == {a, b}


def test_un_pdf_externo_no_se_mueve(tmp_path):
    base = str(tmp_path / "archivo")
    externo = _taco(str(tmp_path / "Escritorio" / "hp.pdf"), 1)
    r = separar.separar({"gasto": [_f("G-1", "P", "01/03/2026", externo, 1)]},
                        base, *CLIENTE)
    assert len(r["creados"]) == 1 and r["tacos"] == {} and os.path.exists(externo)


def test_sin_documento_original_se_avisa(tmp_path):
    r = separar.separar({"gasto": [_f("G-1", "P", "01/03/2026", "", 0)]},
                        str(tmp_path), *CLIENTE)
    assert r["sin_paginas"] == ["G-1"] and not r["creados"]


def test_exportar_parte_el_taco_y_actualiza_la_ventana(monkeypatch):
    import facturas_excel.app as modulo_app

    class Orden:
        def __init__(self, parent):
            pass

        def exec(self):
            return QDialog.Accepted

        def recordar(self):
            pass

        def orden(self):
            return modulo_app.ORDEN_PDF

    monkeypatch.setattr(modulo_app, "DialogoOrden", Orden)
    base = archivo.carpeta_escaneos()
    carpeta = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "gastos", base, nif=CLIENTE[1])
    taco = _taco(os.path.join(carpeta, "taco.pdf"), 2)
    v = modulo_app.VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nombre, v._cliente_nif = CLIENTE
    v._bloques = [{"nombre": "b1", "cliente": CLIENTE[0], "nif": CLIENTE[1],
                   "original": taco, "procesadas": [], "crudos": []}]
    for n, pag in (("F-1", 1), ("F-2", 2)):
        f = _f(n, "PROVEEDOR PRUEBA", "10/02/2026", taco, pag,
               concepto="622", subclave="G13", verificacion="doble")
        v._anadir_fila(b"", f, "gasto", "622", "G13", "", "b1")
    v._revalidar_todo()
    v._exportar_todo()
    gastos = sorted(n for n in os.listdir(carpeta) if n.endswith(".pdf"))
    assert gastos == ["2026-02-10 PROVEEDOR PRUEBA F-1.pdf",
                      "2026-02-10 PROVEEDOR PRUEBA F-2.pdf"]
    nuevo = v.filas[0]["factura"].origen_imagen
    assert "Tacos escaneados" in nuevo and os.path.exists(nuevo)
    assert v._bloques[0]["original"] == nuevo
    assert "guardadas en su propio PDF" in v.banda.historial[-1]


def test_las_apartadas_tambien_tienen_su_pdf_pero_no_las_sustituidas(monkeypatch):
    import facturas_excel.app as modulo_app

    class Orden:
        def __init__(self, parent):
            pass

        def exec(self):
            return QDialog.Accepted

        def recordar(self):
            pass

        def orden(self):
            return modulo_app.ORDEN_PDF

    monkeypatch.setattr(modulo_app, "DialogoOrden", Orden)
    base = archivo.carpeta_escaneos()
    carpeta = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "gastos", base, nif=CLIENTE[1])
    taco = _taco(os.path.join(carpeta, "taco.pdf"), 3)
    v = modulo_app.VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nombre, v._cliente_nif = CLIENTE
    v._bloques = [{"nombre": "b1", "cliente": CLIENTE[0], "nif": CLIENTE[1],
                   "original": taco, "procesadas": [], "crudos": []}]
    for n, pag, manual in (("F-1", 1, None), ("INV-1", 2, "Bien de inversión"),
                           ("VIEJA", 3, "Sustituida por F-1")):
        f = _f(n, "PROVEEDOR PRUEBA", "10/02/2026", taco, pag, concepto="622",
               subclave="G13", verificacion="doble", tratamiento_manual=manual)
        v._anadir_fila(b"", f, "gasto", "622", "G13", "", "b1")
    v._revalidar_todo()
    v._exportar_todo()
    gastos = sorted(n for n in os.listdir(carpeta) if n.endswith(".pdf"))
    assert gastos == ["2026-02-10 PROVEEDOR PRUEBA F-1.pdf",
                      "2026-02-10 PROVEEDOR PRUEBA INV-1.pdf"]
