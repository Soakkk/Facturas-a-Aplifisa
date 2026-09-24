"""Recoger facturas sueltas y crear el expediente del cliente (datos de prueba)."""
import os
import zipfile
from types import SimpleNamespace

import fitz
import pytest
from openpyxl import Workbook
from PySide6.QtWidgets import QApplication

from facturas_excel import clientes, expediente, historial, recoger
from facturas_excel.modelo import Factura

_app = QApplication.instance() or QApplication([])

CLIENTE = ("B12345674", "TALLERES PRUEBA SL")
PROVEEDOR = "12345678Z"


def _pdf(ruta, lineas, paginas=1):
    doc = fitz.open()
    for _ in range(paginas):
        pagina = doc.new_page()
        y = 72
        for linea in lineas:
            pagina.insert_text((72, y), linea, fontsize=11)
            y += 16
    doc.save(ruta)
    doc.close()
    return ruta


def _factura_texto(emisor_nif, receptor_nif, fecha="12/02/2026", num="F-1"):
    return [f"FACTURA {num}", f"Emisor NIF: {emisor_nif}", "Proveedor de ejemplo",
            f"Cliente: CIF {receptor_nif}", f"Fecha: {fecha}",
            "Base 100,00  IVA 21%  21,00  TOTAL 121,00 EUR"]


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    escritorio = casa / "Desktop"
    descargas = casa / "Downloads"
    for c in (escritorio, descargas):
        c.mkdir(parents=True)
    base = escritorio / "Documentación Facturas"
    base.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setenv("USERPROFILE", str(casa))
    clientes.marcar_cliente(*CLIENTE)
    return SimpleNamespace(escritorio=escritorio, descargas=descargas, base=str(base))


def test_origenes_son_escritorio_y_descargas(entorno):
    assert {os.path.basename(c) for c in recoger.carpetas_origen()} == {
        "Desktop", "Downloads"}


def test_identifica_gasto_ingreso_y_desconocido(entorno):
    gasto = _pdf(str(entorno.escritorio / "compra.pdf"),
                 _factura_texto(PROVEEDOR, CLIENTE[0]))
    venta = _pdf(str(entorno.descargas / "venta.pdf"),
                 _factura_texto(CLIENTE[0], PROVEEDOR, "03/11/2025", "V-9"))
    ajena = _pdf(str(entorno.escritorio / "otra.pdf"),
                 _factura_texto(PROVEEDOR, "X1234567L"))
    _pdf(str(entorno.escritorio / "escaneo.pdf"), [])
    # Lo que ya está en el archivo no se vuelve a recoger.
    _pdf(os.path.join(entorno.base, "ya.pdf"), _factura_texto(PROVEEDOR, CLIENTE[0]))

    encontrados = {os.path.basename(c.ruta): c for c in
                   recoger.buscar(recoger.carpetas_origen(), entorno.base)}
    assert set(encontrados) == {"compra.pdf", "venta.pdf", "otra.pdf", "escaneo.pdf"}
    c = encontrados["compra.pdf"]
    assert (c.nif, c.tipo, c.ejercicio, c.listo) == (CLIENTE[0], "gastos", 2026, True)
    v = encontrados["venta.pdf"]
    assert (v.nif, v.tipo, v.ejercicio) == (CLIENTE[0], "ingresos", 2025)
    assert not encontrados["otra.pdf"].nif and encontrados["otra.pdf"].dudas
    assert encontrados["escaneo.pdf"].sin_texto
    assert gasto and venta and ajena


def test_mover_apartar_duplicados_y_deshacer(entorno):
    a = _pdf(str(entorno.escritorio / "compra.pdf"), _factura_texto(PROVEEDOR, CLIENTE[0]))
    copia = entorno.descargas / "compra (1).pdf"
    copia.write_bytes(open(a, "rb").read())
    candidatos = recoger.buscar(recoger.carpetas_origen(), entorno.base)
    # Planificar no crea ninguna carpeta todavía.
    recoger.planificar(candidatos, entorno.base)
    assert os.listdir(entorno.base) == []
    acciones = sorted(c.accion for c in candidatos)
    assert acciones == ["duplicado", "mover"]
    resultado = recoger.aplicar(candidatos, entorno.base)
    assert (resultado["movidos"], resultado["duplicados"]) == (1, 1)
    assert not os.path.exists(a) and not copia.exists()
    destino = next(c.destino for c in candidatos if c.accion == "mover")
    assert os.sep.join(["2026", "Gastos"]) in destino and os.path.exists(destino)
    assert "B12345674" in destino
    assert recoger.deshacer_ultima(entorno.base) == 2
    assert os.path.exists(a) and copia.exists()


def test_excel_exportado_se_reconoce_y_va_a_su_carpeta(entorno):
    libro = Workbook()
    hoja = libro.active
    hoja.append(["Fecha", "Nº"])
    hoja.append(["15/03/2026", "F-1"])
    ruta = str(entorno.escritorio / "GASTOS_TALLERES PRUEBA SL.xlsx")
    libro.save(ruta)
    [c] = [c for c in recoger.buscar(recoger.carpetas_origen(), entorno.base)
           if c.clase == "excel"]
    assert (c.nif, c.tipo, c.ejercicio) == (CLIENTE[0], "gastos", 2026)
    recoger.planificar([c], entorno.base)
    assert c.destino.endswith(os.path.join("2026", "Excel Aplifisa",
                                           "GASTOS_TALLERES PRUEBA SL.xlsx"))


def test_expediente_une_pdf_resumen_y_zip(entorno):
    for n in range(3):
        _pdf(str(entorno.escritorio / f"compra{n}.pdf"),
             _factura_texto(PROVEEDOR, CLIENTE[0], num=f"F-{n}") + [f"doc {n}"],
             paginas=n + 1)
    _pdf(str(entorno.escritorio / "venta.pdf"), _factura_texto(CLIENTE[0], PROVEEDOR))
    candidatos = recoger.buscar(recoger.carpetas_origen(), entorno.base)
    recoger.aplicar(recoger.planificar(candidatos, entorno.base), entorno.base)
    historial.registrar(CLIENTE[0], {"gasto": [
        Factura(num_factura="F-0", fecha="12/02/2026", nombre="PROVEEDOR", nif=PROVEEDOR,
                base_iva=100, pct_iva=21, cuota_iva=21, total_impreso=121)]},
        {"gasto": "GASTOS.xlsx"}, CLIENTE[1])

    [e] = expediente.listar(entorno.base)
    assert (e.nif, e.ejercicio, e.documentos) == (CLIENTE[0], 2026, 4)
    resultado = expediente.crear(entorno.base, e)
    carpeta = resultado["carpeta"]
    assert sorted(os.listdir(carpeta)) == [
        "Gastos 2026.pdf", "Ingresos 2026.pdf", "Resumen 2026.pdf"]
    with fitz.open(os.path.join(carpeta, "Gastos 2026.pdf")) as doc:
        assert doc.page_count == 1 + 1 + 2 + 3          # índice + documentos
        toc = doc.get_toc()
        assert [t[1] for t in toc][0] == "Índice" and len(toc) == 4
        assert "pág. 2" in doc[0].get_text()
    assert resultado["facturas"] == 1
    with zipfile.ZipFile(resultado["zip"]) as z:
        assert "Expediente 2026/Resumen 2026.pdf" in z.namelist()
    # Rehacerlo no deja restos ni versiones a medias.
    expediente.crear(entorno.base, e)
    assert not [n for n in os.listdir(os.path.dirname(carpeta)) if n.startswith(".exp")]


def test_historial_suma_las_lineas_de_una_factura():
    lineas = [Factura(num_factura="F-5", fecha="01/02/2026", nombre="P", nif=PROVEEDOR,
                      base_iva=b, pct_iva=p, cuota_iva=c, total_impreso=131)
              for b, p, c in ((100, 21, 21), (100, 10, 10))]
    historial.registrar(CLIENTE[0], {"gasto": lineas}, {})
    [f] = historial.del_ejercicio(CLIENTE[0], 2026)
    assert (f["base"], f["cuota_iva"], f["total"]) == (200, 31, 131)


def test_exportar_guarda_el_excel_y_actualiza_el_expediente(entorno, monkeypatch):
    from PySide6.QtWidgets import QDialog
    import facturas_excel.app as modulo_app
    from facturas_excel import archivo

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
    v = modulo_app.VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nif, v._cliente_nombre = CLIENTE
    v._bloques = [{"nombre": "b1", "cliente": CLIENTE[1], "nif": CLIENTE[0]}]
    v._anadir_fila(b"", Factura(
        num_factura="F-1", fecha="10/02/2026", nombre="PROVEEDOR PRUEBA",
        nif=PROVEEDOR, concepto="622", subclave="G13", base_iva=100.0,
        pct_iva=21.0, cuota_iva=21.0, total_impreso=121.0, verificacion="doble",
        documento_id="d1"), "gasto", "622", "G13", "", "b1")
    v._revalidar_todo()
    v._exportar_todo()
    base = archivo.carpeta_escaneos()
    [e] = expediente.listar(base)
    excel = os.path.join(base, e.carpeta_cliente, "2026", "Excel Aplifisa")
    assert [n for n in os.listdir(excel) if n.startswith("GASTOS 2026")]
    carpeta = expediente.carpeta_expediente(base, e.carpeta_cliente, 2026)
    assert "Resumen 2026.pdf" in os.listdir(carpeta)
    assert "Expediente del cliente actualizado" in v.banda.historial[-1]


def test_ventana_de_recogida_marca_solo_lo_seguro_y_aplica(entorno):
    from facturas_excel.dialogo_recogida import DialogoRecogida
    _pdf(str(entorno.escritorio / "compra.pdf"), _factura_texto(PROVEEDOR, CLIENTE[0]))
    _pdf(str(entorno.escritorio / "ajena.pdf"), _factura_texto(PROVEEDOR, "X1234567L"))
    candidatos = recoger.buscar(recoger.carpetas_origen(), entorno.base)
    d = DialogoRecogida(candidatos, entorno.base)
    marcados = {os.path.basename(c.ruta): m.isChecked()
                for c, (m, *_r) in zip(d.candidatos, d._controles)}
    assert marcados == {"compra.pdf": True, "ajena.pdf": False}
    assert d.btn_aplicar.text() == "Recoger 1 archivo(s)"
    d._aplicar()
    assert d.resultado["movidos"] == 1
    assert d.resultado["afectados"] == [(CLIENTE[1], CLIENTE[0], 2026)]
    assert (entorno.escritorio / "ajena.pdf").exists()
