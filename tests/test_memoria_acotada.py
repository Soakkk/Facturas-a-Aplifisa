"""Memoria acotada con PDF de 100-200 MB (200-450 hojas).

Lo que medía el banco de estrés con 450 hojas: la caché de MuPDF no se
vaciaba nunca (unos 250 MB fijos), la imagen de cada hoja vivía en memoria y
en cada guardado de la sesión (80 MB), la huella del original leía el PDF
entero de una vez (+200 MB) y «Vaciar todo» no soltaba nada. Estas pruebas
fijan cada arreglo; ninguno cambia lo que se ve ni lo que se decide.
"""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from facturas_excel import imagen_visor, pdf

_app = QApplication.instance() or QApplication([])


def _pdf(ruta, paginas=3):
    documento = fitz.open()
    for numero in range(paginas):
        hoja = documento.new_page(width=300, height=420)
        hoja.insert_text((30, 60), f"FACTURA DE PRUEBA {numero + 1}", fontsize=9)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


class WorkerFalso(QObject):
    """Un Worker que no lee nada ni arranca hilo ninguno."""
    progreso = Signal(int, int)
    terminado = Signal(object, str, str, object)
    gasto = Signal(str, float)
    fallo = Signal(str)

    def __init__(self, rutas, api_key):
        super().__init__()
        self.rutas = rutas
        self.fallos = []

    def start(self):
        pass

    def isRunning(self):
        return False


def _apuntar_vaciados(monkeypatch):
    """Cada vaciado de la caché de MuPDF, y si se hizo con el cerrojo."""
    vaciados = []
    monkeypatch.setattr(fitz.TOOLS, "store_shrink", lambda porcentaje: vaciados.append(
        (porcentaje, pdf.CERROJO.locked())))
    return vaciados


# ------------------------------------------------- la caché de MuPDF (P1)
def test_cada_hoja_que_se_lee_vacia_la_cache_de_mupdf(tmp_path, monkeypatch):
    ruta = _pdf(tmp_path / "taco.pdf", 3)
    vaciados = _apuntar_vaciados(monkeypatch)
    imagenes = pdf.paginas_pdf_a_jpg(ruta)
    assert len(imagenes) == 3 and all(i.startswith(b"\xff\xd8") for i in imagenes)
    # Una vez por hoja, entera y siempre con el cerrojo: MuPDF no admite dos
    # llamadas a la vez y el visor puede estar dibujando en otro hilo.
    assert vaciados == [(100, True)] * 3


def test_una_hoja_suelta_y_la_del_visor_tampoco_se_quedan_en_la_cache(
        tmp_path, monkeypatch):
    ruta = _pdf(tmp_path / "taco.pdf", 2)
    vaciados = _apuntar_vaciados(monkeypatch)
    assert pdf.pagina_a_jpg(ruta, 2).startswith(b"\xff\xd8")
    hoja = imagen_visor.hoja(ruta, 1, 600, 840)
    assert hoja is not None and hoja.ancho == 600
    assert vaciados == [(100, True), (100, True)]


def test_vaciar_la_cache_desde_fuera_no_espera_a_la_lectura(monkeypatch):
    vaciados = _apuntar_vaciados(monkeypatch)
    with pdf.CERROJO:
        # La lectura está dibujando: no se para la ventana esperándola (ella
        # vacía la caché al acabar su hoja).
        assert pdf.vaciar_cache() is False
    assert vaciados == []
    assert pdf.vaciar_cache() is True
    assert vaciados == [(100, True)]
    assert not pdf.CERROJO.locked()


def test_las_hojas_que_separar_dibuja_para_comparar_no_se_quedan_en_la_cache(
        tmp_path, monkeypatch):
    """Al exportar, si ya hay un PDF con el nombre de la factura y sin
    dibujar no se sabe si es el mismo, se comparan sus hojas dibujadas. Eso
    va en el hilo del archivo con el cerrojo de MuPDF cogido: lo dibujado
    tampoco se queda en la caché."""
    from facturas_excel import archivo, separar
    from facturas_excel.modelo import Factura
    cliente, nif = "TALLERES PRUEBA SL", "B12345674"
    base = str(tmp_path / "archivo")
    carpeta = archivo.carpeta_tipo_cliente(cliente, 2026, "gastos", base, nif=nif)
    os.makedirs(carpeta, exist_ok=True)
    taco = _pdf(Path(carpeta) / "taco.pdf", 2)

    def tique(origen, pagina, documento):
        # Dos tiques sin número de la misma gasolinera y día: mismo nombre.
        return Factura(num_factura="", nombre="GASOLINERA", fecha="12/02/2026",
                       nif="12345678Z", base_iva=100, pct_iva=21, cuota_iva=21,
                       total_impreso=121, origen_imagen=origen, pagina_origen=pagina,
                       ultima_pagina_origen=pagina, documento_id=documento)

    vaciados = _apuntar_vaciados(monkeypatch)
    primera = separar.separar({"gasto": [tique(taco, 1, "t1")]}, base, cliente, nif)
    assert len(primera["creados"]) == 1 and vaciados == []    # nada que comparar
    segunda = separar.separar({"gasto": [tique(primera["tacos"][taco], 2, "t2")]},
                              base, cliente, nif)
    [creado] = segunda["creados"]
    assert creado.endswith(" (2).pdf")       # otra hoja: lo de siempre
    # La hoja del PDF que ya estaba y la nueva, cada una con el cerrojo.
    assert vaciados == [(100, True)] * 2


# ------------------------------------------- el original en las muestras (P2)
def test_la_huella_y_la_copia_del_original_no_lo_cargan_en_memoria(tmp_path):
    import hashlib
    import tracemalloc
    from facturas_excel import muestras_revision

    grande = tmp_path / "taco grande.pdf"
    contenido = os.urandom(1 << 20) * 24          # 24 MB, como un PDF escaneado
    grande.write_bytes(contenido)
    tracemalloc.start()
    try:
        identificador = muestras_revision.guardar_original(str(grande))
        _actual, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # La misma huella y la misma copia que antes, sin leerlo entero de golpe.
    assert identificador == hashlib.sha256(contenido).hexdigest()
    copia = muestras_revision.carpeta() / "originales" / (identificador + ".pdf")
    assert copia.read_bytes() == contenido
    assert pico < 8 * (1 << 20), f"pico de {pico / (1 << 20):.0f} MB"


def test_soltar_un_pdf_no_espera_a_copiar_su_original(tmp_path, monkeypatch):
    import threading
    import time
    from facturas_excel import muestras_revision, ventana_lectura
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.clientes import marcar_cliente
    from facturas_excel.procesar import construir

    puede_acabar = threading.Event()
    hilos = []

    def copia_lenta(ruta, raiz=None):
        hilos.append(threading.current_thread().name)
        puede_acabar.wait(10)
        return "huella-del-original"
    monkeypatch.setattr(muestras_revision, "guardar_original", copia_lenta)
    monkeypatch.setattr(ventana_lectura, "Worker", WorkerFalso)
    monkeypatch.setattr(ventana_lectura, "leer_api_key", lambda: "clave-de-prueba")
    marcar_cliente("12345678Z", "CLIENTE PRUEBA")
    ruta = tmp_path / "taco.jpg"
    ruta.write_bytes(b"no se llega a leer")
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)

    inicio = time.monotonic()
    v.procesar_rutas([str(ruta)])
    # La ventana sigue a lo suyo mientras se copia (un PDF de 200 MB tardaba
    # 1,6 s y subía la memoria 200 MB).
    assert time.monotonic() - inicio < 5
    assert v._elemento_cola_actual is not None
    puede_acabar.set()

    datos = dict(num_factura="F-1", fecha="01/09/2026", emisor_nombre="PROVEEDOR PRUEBA",
                 emisor_nif="B12345674", receptor_nombre="CLIENTE PRUEBA",
                 receptor_nif="12345678Z", total=121,
                 lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21)])
    pr = construir(datos, "12345678Z", "CLIENTE PRUEBA", str(ruta), 1)
    v._on_terminado([(b"hoja", pr)], "CLIENTE PRUEBA", "12345678Z",
                    [(b"hoja", str(ruta), 1, datos)])
    # Al acabar el bloque la huella ya está y se apunta en la factura.
    assert hilos and hilos[0] != threading.current_thread().name
    assert v.filas[0]["factura"].original_id == "huella-del-original"


def test_si_la_copia_aparte_del_original_falla_se_avisa_y_se_sigue(
        tmp_path, monkeypatch):
    from facturas_excel import muestras_revision, ventana_lectura
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.clientes import marcar_cliente
    from facturas_excel.procesar import construir

    def disco_lleno(ruta, raiz=None):
        raise OSError("disco lleno")
    monkeypatch.setattr(muestras_revision, "guardar_original", disco_lleno)
    monkeypatch.setattr(ventana_lectura, "Worker", WorkerFalso)
    monkeypatch.setattr(ventana_lectura, "leer_api_key", lambda: "clave-de-prueba")
    avisos = []
    monkeypatch.setattr(VentanaPrincipal, "_avisar_error_muestras",
                        lambda self, error: avisos.append(str(error)))
    marcar_cliente("12345678Z", "CLIENTE PRUEBA")
    ruta = tmp_path / "taco.jpg"
    ruta.write_bytes(b"no se llega a leer")
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v.procesar_rutas([str(ruta)])
    datos = dict(num_factura="F-1", fecha="01/09/2026", emisor_nombre="PROVEEDOR PRUEBA",
                 emisor_nif="B12345674", total=121,
                 lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21)])
    pr = construir(datos, "12345678Z", "CLIENTE PRUEBA", str(ruta), 1)
    v._on_terminado([(b"hoja", pr)], "CLIENTE PRUEBA", "12345678Z",
                    [(b"hoja", str(ruta), 1, datos)])
    assert "disco lleno" in avisos
    assert v.tabla.rowCount() == 1


# ------------------------------------- la imagen de cada hoja en disco (P4)
def _jpeg(texto="hoja 1", ancho=600, alto=800):
    """Una imagen de lectura como las de Gemini (JPEG), distinta por texto."""
    import io
    from PIL import Image, ImageDraw
    imagen = Image.new("RGB", (ancho, alto), "white")
    ImageDraw.Draw(imagen).text((40, 40), texto, fill="black")
    salida = io.BytesIO()
    imagen.save(salida, format="JPEG", quality=80)
    return salida.getvalue()


def _datos(numero="F-1", total=121):
    return dict(num_factura=numero, fecha="01/09/2026", emisor_nombre="PROVEEDOR PRUEBA",
                emisor_nif="B12345674", receptor_nombre="CLIENTE PRUEBA",
                receptor_nif="12345678Z", cuenta_gasto="622", subclave_gxx="G13",
                total=total, lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21)])


def _ventana_con_hojas(tmp_path, hojas=2):
    """Un bloque leído como lo entrega la lectura, con la imagen en bytes."""
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.clientes import marcar_cliente
    from facturas_excel.procesar import preparar_lote

    marcar_cliente("12345678Z", "CLIENTE PRUEBA")
    ruta = tmp_path / "taco.pdf"
    _pdf(ruta, hojas)
    imagenes = [_jpeg(f"hoja {n}") for n in range(1, hojas + 1)]
    crudos = [(imagenes[n], str(ruta), n + 1, _datos(f"F-{n + 1}"))
              for n in range(hojas)]
    procesadas = preparar_lote(crudos, "CLIENTE PRUEBA", "12345678Z")
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._rutas_actuales = [str(ruta)]
    v._on_terminado(procesadas, "CLIENTE PRUEBA", "12345678Z", crudos)
    return v, imagenes


def _sesion_en_claro(ruta):
    import gzip
    with gzip.open(ruta, "rb") as fichero:
        return fichero.read()


def test_el_lote_guarda_un_asa_de_cada_imagen_y_no_sus_bytes(tmp_path):
    from facturas_excel.imagen_hoja import ImagenHoja

    v, imagenes = _ventana_con_hojas(tmp_path)
    asas = [fila.png for fila in v.filas]
    assert all(isinstance(asa, ImagenHoja) for asa in asas)
    # La misma hoja es el mismo objeto en lo leído, lo procesado y la fila.
    bloque = v._bloques[0]
    assert bloque["crudos"][0][0] is asas[0] and bloque["procesadas"][0][0] is asas[0]
    # Se compara y se lee como antes: es la misma imagen, ya en las muestras.
    assert asas[0] == imagenes[0] and asas[0] != imagenes[1]
    assert bytes(asas[1]) == imagenes[1] and asas[1].existe()
    # Y el visor la enseña.
    v.tabla.selectRow(1)
    v._mostrar_miniatura()
    assert not v._pixmap_documento.isNull()


def test_la_sesion_nueva_no_guarda_las_imagenes(tmp_path, monkeypatch):
    from facturas_excel import sesion

    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    v, imagenes = _ventana_con_hojas(tmp_path, 3)
    v._guardar_sesion()
    en_claro = _sesion_en_claro(ruta)
    assert not any(imagen[:4000] in en_claro for imagen in imagenes)
    assert len(en_claro) < 60_000
    # Se vuelve a abrir igual, con sus imágenes.
    from facturas_excel.app import VentanaPrincipal
    otra = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    assert otra.tabla.rowCount() == 3
    assert [bytes(fila.png) for fila in otra.filas] == imagenes


def test_una_sesion_de_antes_con_las_imagenes_se_abre_y_se_convierte(
        tmp_path, monkeypatch):
    """Lo que guardaba la 1.25: los bytes de cada imagen en el lote y en las
    filas, y los recuadros por el SHA1 de esos bytes."""
    import hashlib
    from facturas_excel import localizar, muestras_revision, sesion
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.clientes import marcar_cliente
    from facturas_excel.imagen_hoja import ImagenHoja
    from facturas_excel.procesar import preparar_lote

    ruta = tmp_path / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    marcar_cliente("12345678Z", "CLIENTE PRUEBA")
    imagen = _jpeg("hoja de una sesión vieja")
    crudos = [(imagen, str(tmp_path / "taco.pdf"), 1, _datos("F-9"))]
    procesadas = preparar_lote(crudos, "CLIENTE PRUEBA", "12345678Z")
    pr = procesadas[0][1]
    f = pr.facturas[0]
    caja = localizar.Caja("total_impreso", "121,00", 0.85, 0.7, 0.88, 0.9)
    sesion.guardar({
        "bloques": [{"nombre": "Taco 1", "procesadas": procesadas, "crudos": crudos,
                     "nif": "12345678Z", "cliente": "CLIENTE PRUEBA"}],
        "filas": [{"png": imagen, "factura": f, "aviso": pr.aviso, "bloque": "Taco 1",
                   "fuentes": [f], "tipo": "gasto", "cuenta": f.concepto or "",
                   "gxx": f.subclave or ""}],
        "cliente_nif": "12345678Z", "cliente_nombre": "CLIENTE PRUEBA",
        "hay_recargo": False, "regimen_recargo": None, "periodo_modo": "auto",
        "localizaciones": {hashlib.sha1(imagen).hexdigest():
                           localizar.a_guardar([caja])},
        "su_suma": None})
    assert imagen[:4000] in _sesion_en_claro(ruta)

    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)
    assert v.tabla.rowCount() == 1
    fila = v.filas[0]
    assert isinstance(fila.png, ImagenHoja) and bytes(fila.png) == imagen
    assert v._bloques[0]["crudos"][0][0] is fila.png
    assert (muestras_revision.carpeta() / "imagenes" / (fila.png.sha + ".jpg")).is_file()
    # Los recuadros de antes se siguen encontrando.
    assert v._localizaciones.get(localizar.clave_imagen(fila.png)) == [caja]
    v.tabla.selectRow(0)
    v._mostrar_miniatura()
    assert not v._pixmap_documento.isNull()
    # El siguiente guardado ya va sin la imagen.
    v._guardar_sesion()
    assert imagen[:4000] not in _sesion_en_claro(ruta)


def test_sin_la_carpeta_de_imagenes_nada_se_rompe(tmp_path, monkeypatch):
    import shutil
    from PySide6.QtCore import QCoreApplication
    from facturas_excel import claves, localizar, muestras_revision

    pedidas = []
    monkeypatch.setattr(localizar, "pedir", lambda *a: pedidas.append(a) or ([], []))
    monkeypatch.setattr(claves, "leer_api_key", lambda: "clave-de-prueba")
    v, _imagenes = _ventana_con_hojas(tmp_path)
    shutil.rmtree(muestras_revision.carpeta() / "imagenes")
    # La miniatura sale vacía, como una imagen que no se puede abrir.
    v.tabla.selectRow(1)
    v._mostrar_miniatura()
    assert v._pixmap_documento.isNull()
    assert "no disponible" in v.lbl_img.text()
    # «¿De dónde sale?» no manda una imagen vacía a Gemini: avisa y ya.
    v._localizar_actual()
    v._hilo_localizar.wait(5000)
    QCoreApplication.processEvents()
    assert pedidas == []
    assert "No se ha podido señalar" in v.banda.historial[-1]
    # Y el lote se sigue guardando y exportando como siempre.
    v._guardar_sesion()
    assert v._clasificar_exportacion()[0]["gasto"]


def test_la_lectura_deja_cada_imagen_en_disco_fuera_de_la_ventana(monkeypatch):
    from facturas_excel import hilos
    from facturas_excel.extraccion import DatosFactura
    from facturas_excel.imagen_hoja import ImagenHoja

    imagenes = [_jpeg("hoja 1"), _jpeg("hoja 2")]

    class ExtractorFalso:
        def __init__(self, api_key):
            pass

        def extraer(self, img, origen, pagina):
            assert img == imagenes[pagina - 1]     # Gemini recibe los bytes
            return DatosFactura(crudo=_datos(f"F-{pagina}"), pagina=pagina,
                                consumos=[("gemini-falso", 1, 1)])
    monkeypatch.setattr(hilos, "Extractor", ExtractorFalso)
    monkeypatch.setattr(hilos, "dibujar_hojas", lambda rutas, dpi, cancelado: [
        ("a.pdf", n, imagenes[n - 1]) for n in (1, 2)])
    monkeypatch.setattr(hilos.costes, "registrar", lambda *a, **k: 0.0)
    w = hilos.Worker(["a.pdf"], "clave")
    entregado = []
    w.terminado.connect(lambda *args: entregado.append(args))
    w.run()
    [(procesadas, _nombre, _nif, registros)] = entregado
    assert [type(r[0]) for r in registros] == [ImagenHoja, ImagenHoja]
    assert [bytes(r[0]) for r in registros] == imagenes
    assert procesadas[0][0] is registros[0][0]


def test_senalar_en_el_documento_lee_la_imagen_del_disco(tmp_path, monkeypatch):
    from facturas_excel import hilos, imagen_hoja

    asa = imagen_hoja.a_disco(_jpeg("hoja dudosa"))
    recibidas = []
    monkeypatch.setattr(hilos.costes, "registrar", lambda *a, **k: 0.0)

    def pedir(api_key, modelo, img, lista):
        recibidas.append(img)
        return [], [("modelo", 1, 1)]
    monkeypatch.setattr("facturas_excel.localizar.pedir", pedir)
    hilo = hilos.HiloLocalizar("clave", "modelo", [(asa.clave, asa, [("total", "1")])])
    hilo.run()
    assert recibidas == [bytes(asa)] and isinstance(recibidas[0], bytes)
    assert hilo.trabajos == []            # no se queda con lo pedido


def test_el_asa_se_compara_y_se_guarda_como_la_imagen():
    import pickle
    from facturas_excel import imagen_hoja, localizar

    imagen = _jpeg("hoja")
    asa = imagen_hoja.a_disco(imagen)
    assert asa == imagen and imagen == asa and asa == imagen_hoja.a_disco(imagen)
    assert asa != _jpeg("otra hoja") and asa != b"" and bool(asa)
    assert localizar.clave_imagen(asa) == localizar.clave_imagen(imagen)
    copia = pickle.loads(pickle.dumps(asa))
    assert copia == asa and bytes(copia) == imagen
    assert len(pickle.dumps(asa)) < 250
    assert imagen_hoja.como_bytes(asa) == imagen_hoja.como_bytes(imagen) == imagen
    assert imagen_hoja.como_bytes(None) == b""


# ------------------------------------------ «Vaciar todo» suelta el lote (P8)
def _datos_ambar(numero):
    """Una factura en ámbar: cuenta puesta por descarte (se puede revisar)."""
    datos = _datos(numero)
    datos.pop("cuenta_gasto")
    datos.pop("subclave_gxx")
    return datos


def _ventana_ambar(tmp_path, cuantas=3):
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.clientes import marcar_cliente
    from facturas_excel.procesar import preparar_lote

    marcar_cliente("12345678Z", "CLIENTE PRUEBA")
    ruta = str(tmp_path / "taco.pdf")
    crudos = [(_jpeg(f"hoja {n}"), ruta, n, _datos_ambar(f"F-{n}"))
              for n in range(1, cuantas + 1)]
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._rutas_actuales = [ruta]
    v._on_terminado(preparar_lote(crudos, "CLIENTE PRUEBA", "12345678Z"),
                    "CLIENTE PRUEBA", "12345678Z", crudos)
    assert [f.estado for f in v.filas] == ["revisar"] * cuantas
    return v


def test_vaciar_todo_suelta_las_filas_aunque_se_pudiera_deshacer(
        tmp_path, monkeypatch):
    import gc
    import weakref
    from PySide6.QtWidgets import QMessageBox

    v = _ventana_ambar(tmp_path)
    assert v._marcar_revisada([0, 1, 2]) is not None   # banda con «Deshacer»
    assert v.banda.isVisibleTo(v)
    vivas = [weakref.ref(fila) for fila in v.filas]
    vaciados = _apuntar_vaciados(monkeypatch)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    v._vaciar_todo()
    gc.collect()
    assert [r() for r in vivas] == [None, None, None]
    # El «Deshacer» de un lote que ya no está se va con él; y la caché de
    # MuPDF también se vacía.
    assert not v.banda.isVisibleTo(v)
    assert vaciados == [(100, True)]


def test_vaciar_todo_suelta_el_ultimo_senalar_en_el_documento(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from facturas_excel import claves, localizar

    monkeypatch.setattr(localizar, "pedir", lambda *a: ([], [("modelo", 1, 1)]))
    monkeypatch.setattr(claves, "leer_api_key", lambda: "clave-de-prueba")
    v = _ventana_ambar(tmp_path, 2)
    v._localizar_dudosas()
    v._hilo_localizar.wait(5000)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    v._vaciar_todo()
    assert v._hilo_localizar is None


def test_deshacer_marcar_revisada_solo_guarda_las_filas_que_cambian(tmp_path):
    import gc
    import weakref

    v = _ventana_ambar(tmp_path)
    deshacer = v._marcar_revisada([0])
    assert deshacer is not None
    otras = [weakref.ref(fila) for fila in v.filas[1:]]
    # El lote cambia (otro bloque, «Vaciar todo»…) mientras la banda aún
    # ofrece deshacer: las líneas que no se marcaron no se quedan retenidas.
    v._bloques = []
    v._rellenar_tabla()
    gc.collect()
    assert [r() for r in otras] == [None, None]


def test_deshacer_marcar_revisada_sigue_devolviendo_el_aviso(tmp_path):
    v = _ventana_ambar(tmp_path)
    avisos = [fila.aviso for fila in v.filas]
    deshacer = v._marcar_revisada([1])
    assert v.filas[1].factura.revision_confirmada
    deshacer()
    assert [fila.aviso for fila in v.filas] == avisos
    assert not any(fila.factura.revision_confirmada for fila in v.filas)


# ------------------------------------------ guardado automático de la sesión
def _contar_escrituras(monkeypatch, sesion, frenar=None):
    """Cuántas veces se escribe de verdad el fichero, y desde cuántos hilos
    a la vez (`frenar`: la primera escritura espera a ese aviso)."""
    import threading
    escribir = sesion._escribir
    escritas, a_la_vez, dentro = [], [], [0]
    cerrojo = threading.Lock()

    def contando(paquete, numero):
        with cerrojo:
            dentro[0] += 1
            a_la_vez.append(dentro[0])
        if frenar is not None and not escritas:
            frenar.wait(5)
        try:
            escribir(paquete, numero)
            escritas.append(pickle_dice(paquete))
        finally:
            with cerrojo:
                dentro[0] -= 1
    monkeypatch.setattr(sesion, "_escribir", contando)
    return escritas, a_la_vez


def pickle_dice(paquete):
    import pickle
    return pickle.loads(paquete)["datos"]["bloques"][0]


def test_el_guardado_automatico_no_reescribe_lo_que_no_ha_cambiado(
        tmp_path, monkeypatch):
    from facturas_excel import sesion

    monkeypatch.setattr(sesion, "_ruta", lambda: str(tmp_path / "sesion.pkl.gz"))
    escritas, _ = _contar_escrituras(monkeypatch, sesion)
    for _ in range(3):
        sesion.guardar_en_segundo_plano({"bloques": ["igual"]})
        sesion.esperar()
    assert escritas == ["igual"]
    sesion.guardar_en_segundo_plano({"bloques": ["cambiado"]})
    sesion.esperar()
    assert escritas == ["igual", "cambiado"]
    # Al cerrar, si en el disco ya está lo mismo, tampoco se reescribe.
    sesion.guardar({"bloques": ["cambiado"]})
    assert escritas == ["igual", "cambiado"]
    assert sesion.cargar() == {"bloques": ["cambiado"]}


def test_varios_guardados_seguidos_dejan_uno_pendiente_y_gana_el_ultimo(
        tmp_path, monkeypatch):
    import threading
    from facturas_excel import sesion

    monkeypatch.setattr(sesion, "_ruta", lambda: str(tmp_path / "sesion.pkl.gz"))
    soltar = threading.Event()
    escritas, a_la_vez = _contar_escrituras(monkeypatch, sesion, frenar=soltar)
    for n in range(5):
        sesion.guardar_en_segundo_plano({"bloques": [f"foto {n}"]})
    assert sum(h.is_alive() for h in sesion._hilos) <= 1
    soltar.set()
    sesion.esperar()
    # La primera ya estaba escribiéndose; de las demás, solo la última.
    assert escritas == ["foto 0", "foto 4"]
    assert max(a_la_vez) == 1
    assert sesion.cargar() == {"bloques": ["foto 4"]}


def test_un_guardado_que_falla_se_vuelve_a_intentar_y_vaciar_lo_olvida(
        tmp_path, monkeypatch):
    from facturas_excel import sesion

    ruta = tmp_path / "no-existe" / "sesion.pkl.gz"
    monkeypatch.setattr(sesion, "_ruta", lambda: str(ruta))
    sesion.guardar_en_segundo_plano({"bloques": ["lote"]})
    sesion.esperar()
    assert sesion.ultimo_error()
    ruta.parent.mkdir()
    sesion.guardar_en_segundo_plano({"bloques": ["lote"]})   # lo mismo: otra vez
    sesion.esperar()
    assert not sesion.ultimo_error() and sesion.cargar() == {"bloques": ["lote"]}
    sesion.borrar()
    sesion.guardar_en_segundo_plano({"bloques": ["lote"]})   # tras vaciar, se escribe
    sesion.esperar()
    assert sesion.cargar() == {"bloques": ["lote"]}


# ------------------------------------------ partes temporales de la cola
def _parte(carpeta, nombre, horas=0):
    import time
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    ruta.write_bytes(b"%PDF-1.4 parte")
    if horas:
        hace = time.time() - horas * 3600
        os.utime(ruta, (hace, hace))
        os.utime(carpeta, (hace, hace))
    return ruta


def test_al_arrancar_se_borran_las_partes_que_quedaron_de_otra_vez(tmp_path):
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.rutas import dir_datos

    cola = Path(dir_datos()) / "cola_pdf"
    vieja = _parte(cola / "taco_abc123", "taco_parte_02_de_08.pdf", horas=30)
    # Una recién hecha puede ser de otra copia del programa que la está
    # leyendo ahora: esa no se toca.
    nueva = _parte(cola / "otro_def456", "otro_parte_01_de_04.pdf")
    recien_creada = cola / "otro_ghi789"
    recien_creada.mkdir()
    VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    assert not vieja.exists() and not vieja.parent.exists()
    assert nueva.exists() and recien_creada.is_dir()


def test_al_cerrar_se_borran_las_partes_de_lo_que_quedaba_en_la_cola(tmp_path):
    from PySide6.QtGui import QCloseEvent
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.rutas import dir_datos

    cola = Path(dir_datos()) / "cola_pdf" / "taco_abc123"
    partes = [_parte(cola, f"taco_parte_0{n}_de_03.pdf") for n in (1, 2, 3)]
    original = _parte(tmp_path / "Escritorio", "taco.pdf")
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._elemento_cola_actual = {"rutas": [str(partes[1])], "partes": 3}
    v._cola = [{"rutas": [str(partes[2])], "partes": 3},
               {"rutas": [str(original)], "partes": 1}]
    v.closeEvent(QCloseEvent())
    assert not partes[1].exists() and not partes[2].exists()
    assert original.exists()               # el PDF del usuario, nunca


def test_sin_carpeta_de_ejemplos_el_pdf_entra_igual_en_la_cola(tmp_path, monkeypatch):
    from facturas_excel import muestras_revision, ventana_lectura
    from facturas_excel.app import VentanaPrincipal

    def sin_permiso():
        raise PermissionError("carpeta de ejemplos sin permiso")
    monkeypatch.setattr(muestras_revision, "carpeta", sin_permiso)
    monkeypatch.setattr(ventana_lectura, "Worker", WorkerFalso)
    monkeypatch.setattr(ventana_lectura, "leer_api_key", lambda: "clave-de-prueba")
    avisos = []
    monkeypatch.setattr(VentanaPrincipal, "_avisar_error_muestras",
                        lambda self, error: avisos.append(str(error)))
    ruta = tmp_path / "taco.jpg"
    ruta.write_bytes(b"no se llega a leer")
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v.procesar_rutas([str(ruta)])
    assert v._elemento_cola_actual and v._elemento_cola_actual["muestra_id"] is None
    assert avisos == ["carpeta de ejemplos sin permiso"]
