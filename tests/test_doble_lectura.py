"""Doble lectura con dos modelos y formato cerrado de respuesta (IA simulada)."""
import json
from types import SimpleNamespace

import pytest

from facturas_excel import extraccion
from facturas_excel.doble_lectura import comparar, es_dudosa
from facturas_excel.procesar import consolidar_paginas_factura, construir
from facturas_excel.validacion import REVISAR, validar

BASE = {
    "emisor_nombre": "PROVEEDOR PRUEBA SL", "emisor_nif": "B12345674",
    "receptor_nombre": "CLIENTE PRUEBA", "receptor_nif": "12345678Z",
    "num_factura": "F-7", "fecha": "10/02/2026", "fecha_operacion": None,
    "estado_pagina_factura": "unica",
    "lineas_iva": [{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0,
                    "pct_requiv": None, "cuota_requiv": None}],
    "base_irpf": None, "pct_irpf": None, "cuota_irpf": None, "suplidos": None,
    "es_bien_inversion": False, "total": 121.0, "sustituye_a": None,
    "manuscrito_en_importes": False, "cuenta_gasto": "629",
    "subclave_gxx": "G22", "cuenta_ingreso": None, "subclave_ingreso": None,
    "concepto_texto": "servicios", "confianza": "alta",
}


class ClienteFalso:
    """Contesta a cada modelo con su propia lectura y apunta las llamadas."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.llamadas = []
        self.models = SimpleNamespace(generate_content=self._generar)

    def _generar(self, model, contents, config):
        self.llamadas.append((model, config))
        respuesta = self.respuestas[model]
        if isinstance(respuesta, Exception):
            raise respuesta
        return SimpleNamespace(
            text=json.dumps(respuesta), model_version=model,
            usage_metadata=SimpleNamespace(prompt_token_count=1000,
                                           candidates_token_count=100,
                                           thoughts_token_count=20))


def _extractor(monkeypatch, respuestas, modo="siempre"):
    monkeypatch.setattr(extraccion.genai, "Client", lambda **kw: None)
    ex = extraccion.Extractor("clave", modelos=["modelo-a", "modelo-b"],
                              modo_doble=modo)
    ex.client = ClienteFalso(respuestas)
    return ex


def test_se_pide_formato_cerrado_y_pensamiento_bajo(monkeypatch):
    ex = _extractor(monkeypatch, {"modelo-a": BASE, "modelo-b": BASE}, "no")
    ex.extraer(b"img", "a.pdf", 1)
    _modelo, config = ex.client.llamadas[0]
    assert config.response_json_schema["properties"]["total"]["type"] == ["number", "null"]
    assert str(config.thinking_config.thinking_level).endswith("LOW")


def test_los_modelos_por_defecto_son_fijos_y_sin_alias():
    assert extraccion.MODELOS == ["gemini-3.8-flash", "gemini-3.7-flash"]
    assert not any("latest" in m for m in extraccion.MODELOS)


def test_dos_lecturas_iguales_quedan_verificadas(monkeypatch):
    ex = _extractor(monkeypatch, {"modelo-a": BASE, "modelo-b": dict(BASE)})
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert leido.crudo["_verificacion"] == "doble"
    assert leido.crudo["_discrepancias"] == []
    assert {c[0] for c in leido.consumos} == {"modelo-a", "modelo-b"}
    assert leido.tokens_entrada == 2000


def test_una_diferencia_se_senala_con_los_dos_valores(monkeypatch):
    otro = dict(BASE, total=131.0, emisor_nif="B12345675")
    ex = _extractor(monkeypatch, {"modelo-a": BASE, "modelo-b": otro})
    crudo = ex.extraer(b"img", "a.pdf", 1).crudo
    campos = {d["campo"] for d in crudo["_discrepancias"]}
    assert campos == {"total", "emisor_nif"}
    assert crudo["total"] == 121.0            # manda el principal, no se mezcla

    pr = construir(crudo, "12345678Z", "CLIENTE PRUEBA")
    f = pr.facturas[0]
    assert f.verificacion == "doble"
    res = validar(f)
    assert res.estado == REVISAR
    textos = [m for m in res.mensajes if m.startswith("Doble lectura")]
    assert len(textos) == 2
    assert any("131" in t and "121" in t for t in textos)
    assert {c for m in textos for c in m.campos} == {"total_impreso", "nif"}


def test_si_un_modelo_esta_retirado_se_lee_con_el_otro(monkeypatch):
    ex = _extractor(monkeypatch, {
        "modelo-a": RuntimeError("404 NOT_FOUND: model modelo-a is not found"),
        "modelo-b": BASE})
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert leido.crudo["_verificacion"] == "simple"
    assert leido.crudo["_modelo_1"] == "modelo-b"
    # La siguiente hoja ya no pide el retirado.
    ex.client.llamadas.clear()
    ex.extraer(b"img", "a.pdf", 2)
    assert [m for m, _ in ex.client.llamadas] == ["modelo-b"]


def test_modo_dudosas_solo_relee_lo_dudoso(monkeypatch):
    ex = _extractor(monkeypatch, {"modelo-a": BASE, "modelo-b": BASE}, "dudosas")
    assert ex.extraer(b"img", "a.pdf", 1).crudo["_verificacion"] == "simple"
    assert len(ex.client.llamadas) == 1
    dudosa = dict(BASE, confianza="media")
    ex = _extractor(monkeypatch, {"modelo-a": dudosa, "modelo-b": BASE}, "dudosas")
    crudo = ex.extraer(b"img", "a.pdf", 1).crudo
    assert crudo["_verificacion"] == "doble" and len(ex.client.llamadas) == 2


def test_es_dudosa():
    assert not es_dudosa(BASE)
    assert es_dudosa(dict(BASE, total=130.0))
    assert es_dudosa(dict(BASE, emisor_nif="B12345670"))
    assert not es_dudosa(dict(BASE, estado_pagina_factura="inicio",
                              total=None, lineas_iva=[]))


def test_json_roto_cuenta_lo_pagado(monkeypatch):
    monkeypatch.setattr(extraccion.genai, "Client", lambda **kw: None)
    ex = extraccion.Extractor("clave", modelos=["modelo-a"], modo_doble="no")
    ex.client = SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda **kw: SimpleNamespace(
            text="esto no es json", model_version="modelo-a",
            usage_metadata=SimpleNamespace(prompt_token_count=10,
                                           candidates_token_count=1,
                                           thoughts_token_count=0))))
    with pytest.raises(extraccion.ErrorLectura) as error:
        ex.extraer(b"img", "a.pdf", 1)
    assert len(error.value.consumos) == 3


def test_el_desglose_distinto_se_compara():
    otro = dict(BASE, lineas_iva=[{"base": 100.0, "tipo_iva": 10.0,
                                   "cuota_iva": 10.0}])
    difs = comparar(BASE, otro)
    assert [d["campo"] for d in difs] == ["lineas_iva"]
    assert "21" in difs[0]["valor_1"] and "10" in difs[0]["valor_2"]


def test_diferencia_del_subtotal_de_una_hoja_inicial_no_cuenta():
    inicio = dict(BASE, estado_pagina_factura="inicio", total=50.0,
                  lineas_iva=[{"base": 50.0}],
                  _verificacion="doble",
                  _discrepancias=[{"campo": "total", "etiqueta": "Total",
                                   "valor_1": 50.0, "valor_2": 60.0}])
    final = dict(BASE, estado_pagina_factura="final", receptor_nombre=None,
                 receptor_nif=None, _verificacion="doble",
                 _discrepancias=[{"campo": "fecha", "etiqueta": "Fecha",
                                  "valor_1": "10/02/2026",
                                  "valor_2": "10/02/2024"}])
    [(_, _, _, datos)] = consolidar_paginas_factura(
        [(b"", "a.pdf", 1, inicio), (b"", "a.pdf", 2, final)])
    assert [d["campo"] for d in datos["_discrepancias"]] == ["fecha"]


def test_hoja_no_leida_no_se_pega_ni_se_inventa_nombre():
    rota = {"emisor_nombre": None, "lineas_iva": [{}], "_error": "timeout"}
    inicio = dict(BASE, estado_pagina_factura="inicio")
    salida = consolidar_paginas_factura(
        [(b"", "a.pdf", 1, inicio), (b"", "a.pdf", 2, rota)])
    assert len(salida) == 2
    pr = construir(rota, "12345678Z", "CLIENTE PRUEBA")
    assert pr.facturas[0].nombre is None and "HOJA NO LEÍDA" in pr.aviso
