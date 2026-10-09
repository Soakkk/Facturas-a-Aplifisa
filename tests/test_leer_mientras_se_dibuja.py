"""Cada hoja se dibuja justo antes de leerla, en el hilo que la lee.

Antes el Worker dibujaba el bloque entero (25 hojas, de 3 a 5 s) antes de
mandar ninguna a Gemini, con todas sus imágenes en memoria y la ventana
parada a ratos. Ahora en memoria están solo las hojas que se están leyendo,
y lo demás sigue igual: el orden, el progreso, cerrar a mitad, «sin crédito»
y lo que se guarda de cada hoja.
"""

import threading
import time

import fitz
import pytest
from PySide6.QtCore import Qt

from facturas_excel import hilos, muestras_revision
from facturas_excel.extraccion import DatosFactura, SinCredito


def _taco(ruta, paginas):
    """Un PDF con texto (lo dibuja MuPDF, antes y ahora)."""
    documento = fitz.open()
    for numero in range(1, paginas + 1):
        hoja = documento.new_page(width=300, height=420)
        hoja.insert_text((30, 60), f"FACTURA DE PRUEBA {numero}", fontsize=9)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def _leida(pagina):
    return DatosFactura(crudo={"lineas_iva": [{}], "num_factura": f"F-{pagina}",
                               "receptor_nif": "12345678Z"},
                        pagina=pagina, consumos=[("gemini-falso", 1, 1)])


@pytest.fixture
def apunte(monkeypatch):
    """Lo que pasa, en orden: ("dibuja", página) y ("lee", página)."""
    sucesos = []
    candado = threading.Lock()
    original = fitz.Page.get_pixmap

    def dibujar(self, *a, **k):
        with candado:
            sucesos.append(("dibuja", self.number + 1))
        return original(self, *a, **k)
    monkeypatch.setattr(fitz.Page, "get_pixmap", dibujar)
    monkeypatch.setattr(hilos.costes, "registrar", lambda *a, **k: 0.0)
    return sucesos, candado


def _worker(monkeypatch, ruta, extraer, hilos_a_la_vez=1):
    class ExtractorFalso:
        def __init__(self, api_key):
            self.cancelado = threading.Event()

        def extraer(self, img, origen, pagina):
            return extraer(img, origen, pagina)
    monkeypatch.setattr(hilos, "Extractor", ExtractorFalso)
    monkeypatch.setattr(hilos, "hilos_lectura", lambda: hilos_a_la_vez)
    w = hilos.Worker([ruta], "clave")
    w.entregado, w.fallado, w.avances = [], [], []
    # Directas: alguna prueba lo corre en otro hilo, sin bucle de eventos.
    directa = Qt.ConnectionType.DirectConnection
    w.terminado.connect(lambda *a: w.entregado.append(a), directa)
    w.fallo.connect(w.fallado.append, directa)
    w.progreso.connect(lambda hechas, total: w.avances.append((hechas, total)), directa)
    return w


def test_cada_hoja_se_dibuja_justo_antes_de_leerla(tmp_path, monkeypatch, apunte):
    sucesos, candado = apunte

    def extraer(img, origen, pagina):
        with candado:
            sucesos.append(("lee", pagina))
        return _leida(pagina)
    w = _worker(monkeypatch, _taco(tmp_path / "taco.pdf", 3), extraer)
    w.run()
    assert not w.fallado and w.entregado
    # Con un solo hilo: dibuja una, la lee, dibuja la siguiente…
    assert sucesos == [("dibuja", 1), ("lee", 1), ("dibuja", 2), ("lee", 2),
                       ("dibuja", 3), ("lee", 3)]


def test_en_memoria_solo_las_hojas_que_se_estan_leyendo(tmp_path, monkeypatch, apunte):
    """Con Gemini tardando, no se dibujan más hojas que hilos leyendo; y
    cada imagen pasa a disco en cuanto se ha leído, no al acabar el bloque."""
    sucesos, candado = apunte
    seguir = threading.Event()
    en_disco = {}

    def extraer(img, origen, pagina):
        carpeta = muestras_revision.carpeta() / "imagenes"
        en_disco[pagina] = len(list(carpeta.glob("*.jpg"))) if carpeta.exists() else 0
        if pagina > 3:
            seguir.wait(10)
        return _leida(pagina)
    w = _worker(monkeypatch, _taco(tmp_path / "taco.pdf", 12), extraer, hilos_a_la_vez=3)
    hilo = threading.Thread(target=w.run)
    hilo.start()
    try:
        limite = time.monotonic() + 10
        while time.monotonic() < limite and len(sucesos) < 6:
            time.sleep(0.01)
        time.sleep(0.2)                 # por si dibujara alguna más
        with candado:
            dibujadas = [p for que, p in sucesos if que == "dibuja"]
    finally:
        seguir.set()
        hilo.join(30)
    assert sorted(dibujadas) == [1, 2, 3, 4, 5, 6]  # 3 leídas + 3 esperando a Gemini
    assert not w.fallado and len(w.entregado[0][3]) == 12
    # La hoja 4 solo se empieza cuando acaba otra, y esa ya está guardada en
    # las muestras (antes se guardaban todas al acabar el bloque).
    assert en_disco[4] >= 1


def test_al_cerrar_a_mitad_no_se_dibujan_ni_se_piden_mas_hojas(
        tmp_path, monkeypatch, apunte):
    sucesos, candado = apunte
    w = None

    def extraer(img, origen, pagina):
        with candado:
            sucesos.append(("lee", pagina))
        if pagina == 2:
            w.cancelar()                        # se cierra el programa
        return _leida(pagina)
    w = _worker(monkeypatch, _taco(tmp_path / "taco.pdf", 6), extraer)
    w.run()
    assert sucesos == [("dibuja", 1), ("lee", 1), ("dibuja", 2), ("lee", 2)]
    crudos = w.entregado[0][3]
    assert [d.get("num_factura") for *_, d in crudos[:2]] == ["F-1", "F-2"]
    assert all(d["_error"] == hilos.NO_LEIDA_AL_CERRAR for *_, d in crudos[2:])
    assert [p for _o, p, _m in w.fallos] == [3, 4, 5, 6]


def test_cerrar_antes_de_empezar_tambien_para_a_gemini(tmp_path, monkeypatch, apunte):
    sucesos, _candado = apunte
    w = _worker(monkeypatch, _taco(tmp_path / "taco.pdf", 3),
                lambda img, origen, pagina: _leida(pagina))
    w.cancelar()               # antes de que exista el lector de Gemini
    w.run()
    assert sucesos == []
    assert w._extractor.cancelado.is_set()


def test_una_hoja_que_no_se_puede_sacar_no_tumba_el_bloque(tmp_path, monkeypatch):
    """Antes una hoja que MuPDF no podía dibujar tiraba el bloque entero;
    ahora, con lo leído ya pagado, esa hoja queda en rojo y las demás se leen."""
    original = fitz.Page.get_pixmap

    def dibujar(self, *a, **k):
        if self.number == 1:
            raise RuntimeError("hoja rota")
        return original(self, *a, **k)
    monkeypatch.setattr(fitz.Page, "get_pixmap", dibujar)
    monkeypatch.setattr(hilos.costes, "registrar", lambda *a, **k: 0.0)
    leidas = []

    def extraer(img, origen, pagina):
        leidas.append(pagina)
        return _leida(pagina)
    w = _worker(monkeypatch, _taco(tmp_path / "taco.pdf", 3), extraer)
    w.run()
    assert not w.fallado and leidas == [1, 3]
    crudos = w.entregado[0][3]
    assert "hoja rota" in crudos[1][3]["_error"] and not crudos[1][0]
    assert [p for _o, p, _m in w.fallos] == [2]


def test_el_orden_el_progreso_y_las_imagenes_se_mantienen(
        tmp_path, monkeypatch, apunte):
    """Las hojas acaban desordenadas (la primera es la que más tarda): lo
    entregado va en su orden, el progreso cuenta todas y cada hoja se queda
    con su imagen en disco, también las que no se leyeron por el crédito."""
    from facturas_excel.imagen_hoja import ImagenHoja

    def extraer(img, origen, pagina):
        time.sleep(0.02 * (8 - pagina))
        if pagina == 8:
            raise SinCredito("Tu API key no tiene crédito")
        return _leida(pagina)
    w = _worker(monkeypatch, _taco(tmp_path / "taco.pdf", 8), extraer, hilos_a_la_vez=4)
    w.run()
    procesadas, _nombre, _nif, crudos = w.entregado[0]
    assert [p for _i, _o, p, _d in crudos] == list(range(1, 9))
    assert [d.get("num_factura") for *_, d in crudos[:7]] == [f"F-{n}" for n in range(1, 8)]
    assert "crédito" in crudos[7][3]["_error"]
    assert w.avances == [(n, 8) for n in range(1, 9)]
    assert all(isinstance(img, ImagenHoja) and bytes(img).startswith(b"\xff\xd8")
               for img, *_ in crudos)
    assert "crédito" in w.sin_credito
    assert procesadas[0][0] is crudos[0][0]


@pytest.mark.parametrize("acaba", ["terminado", "fallo"])
def test_el_pdf_esta_cerrado_cuando_la_ventana_se_entera(tmp_path, monkeypatch, acaba):
    """Al acabar el bloque la ventana mueve el original al archivo del
    cliente (o borra la parte); en Windows un fichero abierto no se puede
    mover, así que la lectura lo cierra antes de avisar."""
    from facturas_excel import pdf

    abiertas = []

    class HojasVigiladas(pdf.Hojas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            abiertas.append(self)

    def extraer(img, origen, pagina):
        if acaba == "fallo":
            raise SinCredito("Tu API key no tiene crédito")
        return _leida(pagina)
    w = _worker(monkeypatch, _taco(tmp_path / "taco.pdf", 2), extraer)
    monkeypatch.setattr(hilos, "Hojas", HojasVigiladas)
    monkeypatch.setattr(hilos.costes, "registrar", lambda *a, **k: 0.0)
    al_avisar = []
    getattr(w, acaba).connect(lambda *_a: al_avisar.append(
        [bool(h._abiertos) for h in abiertas]), Qt.ConnectionType.DirectConnection)
    w.run()
    assert al_avisar == [[False]]


def test_al_cerrar_el_pdf_se_suelta_sin_esperar_a_gemini(tmp_path, monkeypatch):
    """Al cerrar el programa la ventana espera 5 s a la lectura y luego
    borra la parte de la cola. Una petición a Gemini tarda más que eso: si el
    PDF siguiera abierto hasta que contestara, en Windows la parte no se
    podría borrar (antes se cerraba nada más dibujar el bloque)."""
    from facturas_excel import pdf

    abiertas = []

    class HojasVigiladas(pdf.Hojas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            abiertas.append(self)

    en_gemini, contesta = threading.Event(), threading.Event()

    def extraer(img, origen, pagina):
        en_gemini.set()
        contesta.wait(10)               # Gemini sin contestar todavía
        return _leida(pagina)
    w = _worker(monkeypatch, _taco(tmp_path / "taco.pdf", 4), extraer, hilos_a_la_vez=2)
    monkeypatch.setattr(hilos, "Hojas", HojasVigiladas)
    monkeypatch.setattr(hilos.costes, "registrar", lambda *a, **k: 0.0)
    hilo = threading.Thread(target=w.run)
    hilo.start()
    try:
        assert en_gemini.wait(10)
        w.cancelar()                    # se cierra el programa
        abiertos_al_cancelar = [bool(h._abiertos) for h in abiertas]
    finally:
        contesta.set()
        hilo.join(30)
    assert abiertos_al_cancelar == [False]
    assert not w.fallado and len(w.entregado[0][3]) == 4


def test_una_hoja_pedida_con_el_pdf_ya_cerrado_lo_dice(tmp_path):
    """Un hilo que llega tarde (se cerró el programa) no intenta abrir el
    PDF como si fuera una foto: dice que ya está cerrado."""
    from facturas_excel import pdf

    hojas = pdf.Hojas([_taco(tmp_path / "taco.pdf", 2)])
    hojas.cerrar()
    with pytest.raises(ValueError, match="cerrado"):
        hojas.imagen(1)
