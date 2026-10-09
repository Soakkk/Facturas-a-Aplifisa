"""Lecturas imposibles de la IA: ni paran la cola ni se pierden facturas (1.26).

Lo que encontró el fuzzing «lecturas absurdas» (09/10/2026, semilla
20261009): un NaN, un infinito o un 10**400 donde va un importe paraban la
cola y el lote no se recuperaba; una lista donde va un nombre tiraba el bloque
entero de 25 hojas ya pagadas; cientos de líneas de IVA congelaban la ficha…
Cada prueba falla sin su arreglo. Solo datos inventados (NIF de prueba).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import math

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from facturas_excel import clientes, procesar, sesion, suite, ventana_lectura
from facturas_excel.extraccion import _num
from facturas_excel.modelo import Factura
from facturas_excel.resumen import eur
from facturas_excel.tabla_facturas import parse_numero
from facturas_excel.validacion import ERROR, OK, validar

_app = QApplication.instance() or QApplication([])

NAN, INF = float("nan"), float("inf")
CLIENTE = ("ANTONIO PRUEBA EJEMPLO", "12345678Z")
PROVEEDORES = [("PROVEEDOR UNO SL", "B12345674"), ("PROVEEDOR DOS SA", "A12345674")]


@pytest.fixture(autouse=True)
def cliente_conocido():
    suite._cache.update(mtime=None, ruta=None, datos=None)
    clientes.marcar_cliente(CLIENTE[1], CLIENTE[0])


def lectura(i: int = 0, **cambios) -> dict:
    """Lo que devolvería Gemini de la factura i: completa y correcta."""
    nombre, nif = PROVEEDORES[i % len(PROVEEDORES)]
    base = round(50 + i * 37.13, 2)
    cuota = round(base * 0.21, 2)
    datos = {
        "emisor_nombre": nombre, "emisor_nif": nif,
        "receptor_nombre": CLIENTE[0], "receptor_nif": CLIENTE[1],
        "num_factura": f"F26/{100 + i:05d}", "fecha": f"{1 + i % 28:02d}/03/2026",
        "fecha_operacion": None, "estado_pagina_factura": "unica",
        "lineas_iva": [{"base": base, "tipo_iva": 21.0, "cuota_iva": cuota,
                        "pct_requiv": None, "cuota_requiv": None}],
        "base_irpf": None, "pct_irpf": None, "cuota_irpf": None, "suplidos": None,
        "es_bien_inversion": False, "total": round(base + cuota, 2),
        "sustituye_a": None, "manuscrito_en_importes": False,
        "cuenta_gasto": "629", "subclave_gxx": "G22", "cuenta_ingreso": "705",
        "subclave_ingreso": "I01", "concepto_texto": "material de oficina",
        "tipo_documento": "factura", "moneda": "EUR", "mencion_iva": "ninguna",
        "posible_no_deducible": "no", "confianza": "alta",
    }
    datos.update(cambios)
    return datos


def crudos_de(*lecturas, origen="taco.pdf"):
    return [(b"", origen, i + 1, d) for i, d in enumerate(lecturas)]


def lote(*lecturas):
    return procesar.preparar_lote(crudos_de(*lecturas), *CLIENTE)


def factura_correcta(**cambios) -> Factura:
    f = Factura(num_factura="F-1", fecha="02/03/2026", concepto="629",
                subclave="G22", nombre="PROVEEDOR UNO SL", nif="B12345674",
                base_iva=100.0, pct_iva=21.0, cuota_iva=21.0, total_impreso=121.0)
    for campo, valor in cambios.items():
        setattr(f, campo, valor)
    return f


# =====================================================================
# n.º 1 — Importes imposibles: NaN, infinito, 1e999, 10**400, un billón
# =====================================================================
IMPOSIBLES = ["NaN", "nan", "inf", "-inf", "Infinity", "1e999", NAN, INF, -INF,
              10 ** 400, -10 ** 400, 2e9, "2000000000", 1e300]


def corto(valor) -> str:
    """El nombre de un caso: un entero de 400 cifras no cabe en una línea."""
    if isinstance(valor, int) and abs(valor) > 10 ** 30:
        return f"{'-' if valor < 0 else ''}entero_de_{len(str(abs(valor)))}_cifras"
    texto = ascii(valor)
    return texto if len(texto) <= 40 else f"{texto[:30]}…{len(texto)}"


@pytest.mark.parametrize("valor", IMPOSIBLES, ids=corto)
def test_num_no_deja_pasar_un_importe_imposible(valor):
    assert _num(valor) is None


@pytest.mark.parametrize("valor", IMPOSIBLES, ids=corto)
def test_una_celda_con_un_importe_imposible_queda_vacia(valor):
    texto = valor if isinstance(valor, str) else str(valor)
    assert parse_numero(texto) is None


def test_los_importes_normales_siguen_igual():
    assert _num("1.234,56") == 1234.56
    assert _num("15,51-") == -15.51
    assert _num(1e9) == 1e9 and _num(-121) == -121.0
    assert parse_numero("1.234,56") == 1234.56
    assert parse_numero("-22,50") == -22.5


@pytest.mark.parametrize("valor", [NAN, INF, -INF, None])
def test_eur_no_lanza_con_un_importe_imposible(valor):
    assert eur(valor) == "— €"
    assert eur(-1234.5) == "-1.234,50 €"


@pytest.mark.parametrize("campo", ["base_iva", "cuota_iva", "total_impreso",
                                   "suplidos", "cuota_irpf"])
@pytest.mark.parametrize("valor", [NAN, INF, 2e9])
def test_validar_deja_en_rojo_un_importe_imposible(campo, valor):
    # Una sesión de antes de la 1.26 puede traerlo: con NaN ninguna cuenta
    # descuadraba y la fila salía en verde.
    assert validar(factura_correcta()).estado == OK
    resultado = validar(factura_correcta(**{campo: valor}))
    assert resultado.estado == ERROR
    assert any("Importe imposible" in m for m in resultado.mensajes)


def test_exportar_nunca_escribe_nan_ni_inf(tmp_path):
    from openpyxl import load_workbook

    from facturas_excel.config_columnas import leer_config
    from facturas_excel.exportar import (MODO_NUMERO, MODO_TEXTO, exportar_excel,
                                         verificar_excel)
    from facturas_excel.rutas import ruta_config

    facturas = [factura_correcta(base_iva=NAN, cuota_iva=INF, total_impreso=-INF),
                factura_correcta()]
    config = leer_config(ruta_config("gastos.xml"))
    for modo in (MODO_TEXTO, MODO_NUMERO):
        ruta = str(tmp_path / f"gastos_{modo}.xlsx")
        exportar_excel(facturas, config, ruta, modo)
        if modo == MODO_TEXTO:          # el que usa el programa
            assert verificar_excel(facturas, config, ruta, modo) == []
        libro = load_workbook(ruta)
        celdas = [str(x).lower() for fila in libro.active.iter_rows(values_only=True)
                  for x in fila if x is not None]
        libro.close()
        assert not [c for c in celdas if c in ("nan", "inf", "-inf")
                    or c.startswith(("nan", "inf", "-inf"))], celdas


class WorkerFalso(QObject):
    """Un Worker que no lee nada ni arranca hilo ninguno."""
    progreso = Signal(int, int)
    terminado = Signal(object, str, str, object)
    gasto = Signal(str, float)
    fallo = Signal(str)
    creados = []

    def __init__(self, rutas, api_key):
        super().__init__()
        self.rutas = rutas
        self.fallos = []
        self._corriendo = False
        WorkerFalso.creados.append(self)

    def start(self):
        self._corriendo = True

    def isRunning(self):
        return self._corriendo


@pytest.fixture
def ventana(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    from facturas_excel.app import VentanaPrincipal
    # El aviso de las muestras (n.º 12) tiene sus propias pruebas más abajo.
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    WorkerFalso.creados = []
    monkeypatch.setattr(ventana_lectura, "Worker", WorkerFalso)
    monkeypatch.setattr(ventana_lectura, "leer_api_key", lambda: "clave-de-prueba")
    monkeypatch.setattr(sesion, "_ruta", lambda: str(tmp_path / "sesion.pkl.gz"))
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._cola = []
    return v


def _dos_tacos_en_cola(v, tmp_path):
    """Dos documentos: el primero «leyéndose» y el segundo esperando turno."""
    rutas = []
    for i in range(2):
        ruta = tmp_path / f"taco {i + 1}.jpg"
        ruta.write_bytes(b"no se llega a leer")
        rutas.append(str(ruta))
    v.procesar_rutas(rutas)
    WorkerFalso.creados[0]._corriendo = False
    assert len(WorkerFalso.creados) == 1 and len(v._cola) == 1
    assert not v.btn_gastos.isEnabled()      # mientras se lee, Exportar apagado
    return rutas


def _recuperar(tmp_path):
    from facturas_excel.app import VentanaPrincipal
    return VentanaPrincipal(comprobar_updates=False, restaurar_sesion=True)


def test_un_bloque_con_suplidos_nan_no_para_la_cola(ventana, tmp_path):
    _dos_tacos_en_cola(ventana, tmp_path)
    crudos = crudos_de(lectura(0, suplidos=NAN), lectura(1))
    ventana._on_terminado(procesar.preparar_lote(crudos, *CLIENTE), *CLIENTE, crudos)

    assert len(WorkerFalso.creados) == 2          # la cola sigue con el 2.º
    assert ventana._cola_completados == 1
    assert ventana.btn_gastos.isEnabled()          # Exportar vuelve
    assert ventana._timer_sesion.isActive()        # el guardado automático, armado
    assert not any(math.isnan(x) for fila in ventana.filas
                   for x in (fila.factura.base_iva, fila.factura.suplidos)
                   if isinstance(x, float))
    ventana._guardar_sesion()
    recuperada = _recuperar(tmp_path)
    assert recuperada.tabla.rowCount() == ventana.tabla.rowCount() > 0
    assert not sesion.apartada()


def test_una_sesion_vieja_con_nan_se_recupera_y_la_fila_sale_en_rojo(
        ventana, tmp_path):
    procesadas = lote(lectura(0), lectura(1))
    procesadas[0][1].facturas[0].base_iva = NAN     # como la dejaba la 1.25
    ventana._rutas_actuales = ["taco.pdf"]
    ventana._on_terminado(procesadas, *CLIENTE)
    assert ventana.filas[0].estado == ERROR
    ventana._guardar_sesion()

    recuperada = _recuperar(tmp_path)
    assert recuperada.tabla.rowCount() == 2
    assert recuperada.filas[0].estado == ERROR
    assert not sesion.apartada()


def test_si_poner_un_bloque_falla_la_cola_sigue_y_queda_apuntado(
        ventana, tmp_path, monkeypatch):
    from facturas_excel import errores
    from facturas_excel.rutas import dir_datos

    _dos_tacos_en_cola(ventana, tmp_path)
    original = type(ventana)._revalidar_todo
    veces = []

    def revalidar_que_falla(self):
        veces.append(1)
        if len(veces) == 1:
            raise RuntimeError("fallo inventado al pintar el resumen")
        return original(self)
    monkeypatch.setattr(type(ventana), "_revalidar_todo", revalidar_que_falla)
    crudos = crudos_de(lectura(0), lectura(1))

    ventana._on_terminado(procesar.preparar_lote(crudos, *CLIENTE), *CLIENTE, crudos)

    assert len(WorkerFalso.creados) == 2           # pasa al bloque siguiente
    assert ventana._cola_completados == 1
    assert ventana.btn_gastos.isEnabled()
    assert ventana._timer_sesion.isActive() and ventana._timer_muestras.isActive()
    with open(os.path.join(dir_datos(), errores.FICHERO), encoding="utf-8") as fh:
        assert "fallo inventado al pintar el resumen" in fh.read()


def test_un_fallo_despues_de_pasar_al_siguiente_no_arranca_otro(
        ventana, tmp_path, monkeypatch):
    _dos_tacos_en_cola(ventana, tmp_path)
    original = type(ventana)._iniciar_siguiente_cola

    def iniciar_y_fallar(self, *a, **k):
        original(self, *a, **k)
        raise RuntimeError("fallo inventado al final")
    monkeypatch.setattr(type(ventana), "_iniciar_siguiente_cola", iniciar_y_fallar)
    crudos = crudos_de(lectura(0))

    ventana._on_terminado(procesar.preparar_lote(crudos, *CLIENTE), *CLIENTE, crudos)

    assert len(WorkerFalso.creados) == 2           # uno solo más, no dos
    assert ventana._cola_completados == 1


# =====================================================================
# n.º 4 — Una hoja rara no tira el bloque; una lectura desbocada no tira
#          la otra, que era buena
# =====================================================================
def anidado(niveles: int):
    valor = []
    for _ in range(niveles):
        valor = [valor]
    return valor


@pytest.mark.parametrize("texto,esperado", [
    ('{"total": NaN, "suplidos": Infinity, "base_irpf": -Infinity}',
     {"total": None, "suplidos": None, "base_irpf": None}),
    ('{"total": 1e999, "pct_irpf": 15}', {"total": None, "pct_irpf": 15}),
    ('{"total": ' + "9" * 5000 + '}', {"total": None}),
    ('{"total": ' + "9" * 400 + '.5}', {"total": None}),
    ('{"total": 9999999999999999}', {"total": None}),
], ids=["literales", "1e999", "entero_5000_cifras", "decimal_400_cifras",
        "entero_16_cifras"])
def test_el_json_de_gemini_sin_numeros_imposibles(texto, esperado):
    from facturas_excel.extraccion import _parse_json_tolerante
    assert _parse_json_tolerante(texto) == esperado


@pytest.mark.parametrize("texto", [
    "[" * 100_000 + "]" * 100_000,
    '{"concepto_texto": ' + "[" * 3000 + "]" * 3000 + "}",
    '{"total": 1' + "9" * 5000,                     # cortada en mitad del número
], ids=["100000_niveles", "3000_niveles_dentro", "cortada_en_un_numero"])
def test_el_json_desbocado_no_lanza(texto):
    from facturas_excel.extraccion import _parse_json_tolerante
    assert _parse_json_tolerante(texto) is None      # se vuelve a pedir


class ClienteGemini:
    """Contesta a cada modelo con un TEXTO fijo y apunta las llamadas."""

    def __init__(self, textos):
        from types import SimpleNamespace
        self.textos = textos
        self.llamadas = []
        self.models = SimpleNamespace(generate_content=self._generar)

    def _generar(self, model, contents, config):
        from types import SimpleNamespace
        self.llamadas.append(model)
        return SimpleNamespace(
            text=self.textos[model], model_version=model,
            usage_metadata=SimpleNamespace(prompt_token_count=1000,
                                           candidates_token_count=100,
                                           thoughts_token_count=20))


def extractor(monkeypatch, textos, modo="siempre"):
    from facturas_excel import extraccion
    monkeypatch.setattr(extraccion.genai, "Client", lambda **kw: None)
    ex = extraccion.Extractor("clave", modelos=["modelo-a", "modelo-b"],
                              modo_doble=modo)
    ex.client = ClienteGemini(textos)
    return ex


@pytest.mark.parametrize("desbocada", [
    "[" * 100_000 + "]" * 100_000,
    '{"total": ' + "9" * 5000 + ', "lineas_iva": [',
    '{"total": 1' + "9" * 5000,
], ids=["100000_niveles", "entero_5000_cifras_cortada", "cortada_en_un_numero"])
def test_una_lectura_desbocada_no_tira_la_otra(monkeypatch, desbocada):
    buena = json.dumps(lectura(0))
    ex = extractor(monkeypatch, {"modelo-a": desbocada, "modelo-b": buena})

    leido = ex.extraer(b"img", "taco.pdf", 1)

    assert leido.crudo["num_factura"] == "F26/00100"   # la del otro modelo
    assert leido.crudo.get("_error_2")                 # y se dice que la 1.ª falló
    assert ex.client.llamadas.count("modelo-a") == 3   # se reintentó, se pagó
    assert len(leido.consumos) == 4


def test_una_lectura_con_un_entero_enorme_se_queda(monkeypatch):
    rara = json.dumps(lectura(0))[:-1] + ', "suplidos": ' + "9" * 5000 + "}"
    ex = extractor(monkeypatch, {"modelo-a": rara, "modelo-b": rara}, modo="no")
    leido = ex.extraer(b"img", "taco.pdf", 1)
    assert leido.crudo["suplidos"] is None and leido.crudo["total"] == 60.5
    assert ex.client.llamadas == ["modelo-a"]


RARAS = {
    "lineas_texto": dict(lineas_iva="21%"),
    "lineas_con_none": dict(lineas_iva=[None]),
    "lineas_con_numero": dict(lineas_iva=[5]),
    "lineas_numero": dict(lineas_iva=5),
    "lineas_dict": dict(lineas_iva={"base": 10}),
    "ultima_pagina_texto": dict(_ultima_pagina_consolidada="abc"),
    "union_manual_rara": dict(_paginas_union_manual=[[1, 2, 3]]),
    "anidado_900": dict(concepto_texto=anidado(900)),
}


@pytest.mark.parametrize("cambios", list(RARAS.values()), ids=list(RARAS))
def test_una_hoja_rara_no_tira_el_bloque_de_25(cambios):
    lecturas = [lectura(i) for i in range(25)]
    lecturas[6] = lectura(6, **cambios)

    procesadas = procesar.preparar_lote(crudos_de(*lecturas), *CLIENTE)

    assert len(procesadas) == 25
    assert sorted(pr.pagina for _, pr in procesadas) == list(range(1, 26))
    rara = next(pr for _, pr in procesadas if pr.pagina == 7)
    otras = [pr for _, pr in procesadas if pr.pagina != 7]
    assert not any("HOJA NO LEÍDA" in pr.aviso for pr in otras)
    assert all(pr.facturas[0].num_factura for pr in otras)
    if "HOJA NO LEÍDA" in rara.aviso:            # la rara, en rojo con su motivo
        assert validar(rara.facturas[0]).estado == ERROR


@pytest.mark.parametrize("nombre", [["PROVEEDOR", "UNO"], {"nombre": "X"}, 12345],
                         ids=["lista", "dict", "numero"])
def test_un_nombre_raro_no_impide_saber_el_cliente(nombre):
    lecturas = [lectura(i) for i in range(25)]
    lecturas[6] = lectura(6, emisor_nombre=nombre)
    lecturas[7] = lectura(7, receptor_nombre=nombre, receptor_nif=["12345678Z"])
    assert procesar.detectar_cliente(lecturas) == CLIENTE


@pytest.mark.parametrize("lineas", ["21%", 5, {"base": 10}, None],
                         ids=["texto", "numero", "dict", "nada"])
def test_comparar_dos_lecturas_con_lineas_raras_no_lanza(lineas):
    from facturas_excel.doble_lectura import comparar, es_dudosa
    rara = lectura(0, lineas_iva=lineas)
    diferencias = comparar(lectura(0), rara)
    assert [d["campo"] for d in diferencias] == ["lineas_iva"]
    assert es_dudosa(rara)                  # sin desglose, que la mire otro
