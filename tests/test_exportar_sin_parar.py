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


# ------------------------------------- 3. el expediente, solo si ha cambiado
def _contar(monkeypatch, modulo, nombre):
    llamadas = []
    original = getattr(modulo, nombre)

    def contar(*a, **k):
        llamadas.append(a)
        return original(*a, **k)
    monkeypatch.setattr(modulo, nombre, contar)
    return llamadas


def _contenido(carpeta):
    salida = {}
    for raiz, _c, archivos in os.walk(carpeta):
        for nombre in archivos:
            ruta = os.path.join(raiz, nombre)
            with open(ruta, "rb") as fh:
                salida[os.path.relpath(ruta, carpeta)] = (fh.read(),
                                                          os.stat(ruta).st_mtime_ns)
    return salida


def test_el_expediente_que_no_ha_cambiado_no_se_rehace(tmp_path, monkeypatch):
    base = str(tmp_path / "archivo")
    e = _archivo_con_facturas(base)
    primero = expediente.crear(base, e)
    antes = _contenido(os.path.dirname(primero["carpeta"]))
    unidos = _contar(monkeypatch, expediente, "_unir")
    resumenes = _contar(monkeypatch, expediente, "_pdf_desde_html")

    segundo = expediente.crear(base, e)

    assert unidos == [] and resumenes == []
    assert segundo == primero
    # Ni la carpeta ni el ZIP se han tocado.
    assert _contenido(os.path.dirname(primero["carpeta"])) == antes


def test_si_solo_cambian_los_ingresos_los_gastos_se_aprovechan(tmp_path, monkeypatch):
    base = str(tmp_path / "archivo")
    e = _archivo_con_facturas(base)
    primero = expediente.crear(base, e)
    gastos = os.path.join(primero["carpeta"], "Gastos 2026.pdf")
    with open(gastos, "rb") as fh:
        gastos_antes = fh.read()
    ingresos = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "ingresos", base, nif=CLIENTE[1])
    _pdf_escaneado(os.path.join(ingresos, "2026-03-20 CLIENTE V-9.pdf"), [77, 78])
    unidos = _contar(monkeypatch, expediente, "_unir")

    segundo = expediente.crear(base, e)

    assert [os.path.basename(a[1]) for a in unidos] == ["Ingresos 2026.pdf"]
    assert segundo["documentos"]["Gastos"] == primero["documentos"]["Gastos"] == (
        3, 1 + 3, "Gastos 2026.pdf")                      # índice + 3 hojas
    assert segundo["documentos"]["Ingresos"] == (3, 1 + 1 + 1 + 2, "Ingresos 2026.pdf")
    with open(gastos, "rb") as fh:
        assert fh.read() == gastos_antes
    with zipfile.ZipFile(segundo["zip"]) as z, \
            fitz.open("pdf", z.read("Expediente 2026/Ingresos 2026.pdf")) as doc:
        assert doc.page_count == 5
        assert z.read("Expediente 2026/Gastos 2026.pdf") == gastos_antes


def test_si_se_toca_el_expediente_a_mano_se_rehace_entero(tmp_path, monkeypatch):
    base = str(tmp_path / "archivo")
    e = _archivo_con_facturas(base)
    primero = expediente.crear(base, e)
    os.remove(os.path.join(primero["carpeta"], "Resumen 2026.pdf"))
    unidos = _contar(monkeypatch, expediente, "_unir")
    expediente.crear(base, e)
    assert len(unidos) == 2
    assert "Resumen 2026.pdf" in os.listdir(primero["carpeta"])

    os.remove(primero["zip"])             # sin el ZIP, también
    expediente.crear(base, e)
    assert len(unidos) == 4 and os.path.exists(primero["zip"])


def test_si_falla_al_rehacerlo_el_expediente_de_antes_queda_entero(tmp_path, monkeypatch):
    import pytest
    base = str(tmp_path / "archivo")
    e = _archivo_con_facturas(base)
    primero = expediente.crear(base, e)
    antes = _contenido(primero["carpeta"])
    ingresos = archivo.carpeta_tipo_cliente(CLIENTE[0], 2026, "ingresos", base, nif=CLIENTE[1])
    _pdf_escaneado(os.path.join(ingresos, "2026-03-20 CLIENTE V-9.pdf"), [77])

    def roto(*_a):
        raise OSError("disco lleno")
    resumen = expediente._pdf_desde_html
    monkeypatch.setattr(expediente, "_pdf_desde_html", roto)
    with pytest.raises(OSError):
        expediente.crear(base, e)

    assert _contenido(primero["carpeta"]) == antes      # los gastos, en su sitio
    assert not [n for n in os.listdir(os.path.dirname(primero["carpeta"]))
                if n.startswith(".expediente-")]
    # (Sin monkeypatch.undo(): desharía también el perfil aislado de conftest.)
    monkeypatch.setattr(expediente, "_pdf_desde_html", resumen)
    segundo = expediente.crear(base, e)
    assert segundo["documentos"]["Ingresos"] == (3, 1 + 3, "Ingresos 2026.pdf")


# ------------------------------------- 4. el archivo, en segundo plano
class _Orden:
    def __init__(self, parent):
        pass

    def exec(self):
        from PySide6.QtWidgets import QDialog
        return QDialog.Accepted

    def recordar(self):
        pass

    def orden(self):
        from facturas_excel import ventana_aplifisa
        return ventana_aplifisa.ORDEN_PDF


def _ventana_con_taco(monkeypatch, hojas=2):
    """Una ventana con un taco escaneado en el archivo y una factura por hoja,
    lista para exportar (como test_separar_facturas)."""
    import facturas_excel.app as modulo_app
    from facturas_excel import ventana_aplifisa
    monkeypatch.setattr(ventana_aplifisa, "DialogoOrden", _Orden)
    base = archivo.carpeta_escaneos()
    taco = _taco_escaneado(base, hojas)
    v = modulo_app.VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cliente_nombre, v._cliente_nif = CLIENTE
    v._bloques = [{"nombre": "b1", "cliente": CLIENTE[0], "nif": CLIENTE[1],
                   "original": taco, "procesadas": [], "crudos": []}]
    for pag in range(1, hojas + 1):
        f = _f(f"F-{pag}", "PROVEEDOR PRUEBA", "10/02/2026", taco, pag)
        f.concepto, f.subclave, f.verificacion = "622", "G13", "doble"
        v._anadir_fila(b"", f, "gasto", "622", "G13", "", "b1")
    v._revalidar_todo()
    return v, os.path.dirname(taco)


def _separar_que_espera(monkeypatch):
    """separar.separar se queda esperando a que la prueba le deje seguir, y
    apunta desde qué hilo se llamó y qué decía la ventana en ese momento."""
    import threading
    from facturas_excel import separar
    original = separar.separar
    seguir, visto = threading.Event(), {}

    def esperando(*a, **k):
        visto["hilo_principal"] = threading.current_thread() is threading.main_thread()
        visto["avisado"] = list(_ventana_de_la_prueba[0].banda.historial)
        seguir.wait(10)
        return original(*a, **k)
    monkeypatch.setattr(separar, "separar", esperando)
    return seguir, visto


_ventana_de_la_prueba = [None]


def test_exportar_avisa_del_excel_y_archiva_sin_parar_la_ventana(monkeypatch):
    """Con 800 líneas la ventana se quedaba 19 s parada: casi todo era el
    archivo del cliente. Ahora se avisa de que el Excel está listo, y el
    archivo se hace en otro hilo mientras la ventana sigue respondiendo."""
    from PySide6.QtCore import QCoreApplication
    v, gastos = _ventana_con_taco(monkeypatch)
    _ventana_de_la_prueba[0] = v
    seguir, visto = _separar_que_espera(monkeypatch)

    v._exportar_todo()              # vuelve aunque el archivo no ha acabado
    for _ in range(100):
        QCoreApplication.processEvents()
        if "hilo_principal" in visto:
            break
        import time
        time.sleep(0.01)
    assert visto["hilo_principal"] is False
    # El Excel se anunció antes de empezar a archivar…
    assert "Exportación terminada y comprobada" in visto["avisado"][-1]
    assert v.archivando() and "Guardando" in v.lbl_estado.text()
    # …y lo archivado se cuenta al terminar, en el mismo aviso.
    assert "guardadas en su propio PDF" not in v.banda.historial[-1]
    seguir.set()
    v._esperar_archivo()
    QCoreApplication.processEvents()        # los «cómo va» que llegan tarde
    final = v.banda.historial[-1]
    assert final.startswith(visto["avisado"][-1])
    assert "2 factura(s) guardadas en su propio PDF" in final
    assert "Expediente del cliente actualizado (1)." in final
    assert not v.archivando()
    assert "Guardando" not in v.lbl_estado.text()
    assert "Poniendo al día" not in v.lbl_estado.text()
    assert sorted(n for n in os.listdir(gastos) if n.endswith(".pdf")) == [
        "2026-02-10 PROVEEDOR PRUEBA F-1.pdf", "2026-02-10 PROVEEDOR PRUEBA F-2.pdf"]
    # La ventana sabe dónde ha quedado el taco (lo apartó el otro hilo).
    nuevo = v.filas[0]["factura"].origen_imagen
    assert "Tacos escaneados" in nuevo and os.path.exists(nuevo)
    assert v._bloques[0]["original"] == nuevo


def test_cerrar_el_programa_espera_a_que_acabe_el_archivo(monkeypatch):
    """Cerrar a mitad dejaría facturas sin su PDF y el expediente a medias:
    se espera, y la sesión se guarda ya con el taco en su sitio nuevo."""
    import threading
    from facturas_excel import hilos, sesion
    v, gastos = _ventana_con_taco(monkeypatch)
    _ventana_de_la_prueba[0] = v
    seguir, _visto = _separar_que_espera(monkeypatch)
    v._exportar_todo()
    threading.Timer(0.3, seguir.set).start()

    v.close()

    assert not v.archivando() and not hilos.VIVOS
    assert len([n for n in os.listdir(gastos) if n.endswith(".pdf")]) == 2
    nuevo = v._bloques[0]["original"]
    assert "Tacos escaneados" in nuevo
    sesion.esperar()
    guardada = sesion.cargar()
    assert guardada["bloques"][0]["original"] == nuevo


def test_un_fallo_al_archivar_se_apunta_y_se_avisa(monkeypatch):
    from facturas_excel import registro_facturas
    from facturas_excel.rutas import dir_datos
    v, _gastos = _ventana_con_taco(monkeypatch)

    def bloqueada(*_a, **_k):
        raise RuntimeError("base de datos bloqueada")
    monkeypatch.setattr(registro_facturas, "archivar", bloqueada)
    v._exportar_todo()
    v._esperar_archivo()

    final = v.banda.historial[-1]
    assert final.startswith("Exportación terminada y comprobada")
    assert ("OJO: el Excel está bien, pero no se pudo poner al día el archivo "
            "del cliente (base de datos bloqueada)") in final
    with open(os.path.join(dir_datos(), "errores.log"), encoding="utf-8") as fh:
        assert "base de datos bloqueada" in fh.read()
    # Lo que sí se hizo antes del fallo (apartar el taco) la ventana lo sabe.
    assert "Tacos escaneados" in v._bloques[0]["original"]


def test_si_mientras_se_archiva_se_avisa_de_otra_cosa_no_se_tapa(monkeypatch):
    """Un aviso con «Deshacer» que sale mientras se archiva no lo tapa lo
    archivado (si todo ha ido bien): eso va a la barra de estado."""
    v, _gastos = _ventana_con_taco(monkeypatch)
    _ventana_de_la_prueba[0] = v
    seguir, _visto = _separar_que_espera(monkeypatch)
    v._exportar_todo()
    v._avisar("1 línea(s) eliminada(s).", deshacer=lambda: None)
    seguir.set()
    v._esperar_archivo()
    assert v.banda.historial[-1] == "1 línea(s) eliminada(s)."
    assert "2 factura(s) guardadas en su propio PDF" in v.lbl_estado.text()
