"""Lectura con «Claude Opus 5.5 + Gemini» (prueba de 2026-10): Claude simulado.

Con Gemini elegido (lo de siempre) nada cambia; con Claude, la primera lectura
la hace Claude Opus 5.5 y la segunda el Gemini principal. Ninguna prueba llama
de verdad a Claude ni gasta crédito.
"""
import json
from types import SimpleNamespace

import pytest

from facturas_excel import ajustes, claves, costes, extraccion, localizar

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
    "concepto_texto": "servicios", "tipo_documento": "factura", "moneda": "EUR",
    "mencion_iva": "ninguna", "posible_no_deducible": "no", "confianza": "alta",
}
# Lo mismo como lo devuelve Claude: los textos que faltan, vacíos.
BASE_CLAUDE = dict(BASE, fecha_operacion="", sustituye_a="",
                   cuenta_ingreso="", subclave_ingreso="")


def _respuesta_claude(datos, stop_reason="end_turn", entrada=3000,
                      escrito=0, releido=0, salida=900):
    return SimpleNamespace(
        model="claude-opus-5-5", stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=json.dumps(datos))],
        usage=SimpleNamespace(input_tokens=entrada,
                              cache_creation_input_tokens=escrito,
                              cache_read_input_tokens=releido,
                              output_tokens=salida))


class ClaudeFalso:
    """Hace de anthropic.Anthropic: contesta lo que se le diga y apunta."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []
        self.messages = SimpleNamespace(create=self._crear)

    def _crear(self, **kw):
        self.peticiones.append(kw)
        respuesta = self.respuestas.pop(0) if len(self.respuestas) > 1 \
            else self.respuestas[0]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class GeminiFalso:
    def __init__(self, datos):
        self.datos = datos
        self.llamadas = []
        self.models = SimpleNamespace(generate_content=self._generar)

    def _generar(self, model, contents, config):
        self.llamadas.append(model)
        if isinstance(self.datos, Exception):
            raise self.datos
        return SimpleNamespace(
            text=json.dumps(self.datos), model_version=model,
            usage_metadata=SimpleNamespace(prompt_token_count=1000,
                                           candidates_token_count=100,
                                           thoughts_token_count=20))


class ErrorClaude(Exception):
    """Como los errores del SDK de Claude: traen status_code."""

    def __init__(self, mensaje, status_code, cabeceras=None):
        super().__init__(mensaje)
        self.status_code = status_code
        self.response = SimpleNamespace(headers=cabeceras or {})


def _con_claude(monkeypatch, respuestas_claude, datos_gemini=BASE, modo="siempre"):
    ajustes.guardar("proveedor_lectura", "claude")
    monkeypatch.setattr(extraccion.genai, "Client", lambda **kw: None)
    monkeypatch.setattr(extraccion.time, "sleep", lambda s: None)
    ex = extraccion.Extractor("clave-gemini", modo_doble=modo,
                              clave_claude="clave-claude")
    ex.client = GeminiFalso(datos_gemini)
    ex._cliente_claude = ClaudeFalso(respuestas_claude)
    return ex


# ----------------------------------------------------------- el desplegable
def test_por_defecto_se_lee_con_gemini_como_siempre():
    assert extraccion.proveedor_lectura() == "gemini"
    assert extraccion.modelos_configurados() == ["gemini-3.8-flash",
                                                 "gemini-3.7-flash"]


def test_con_claude_lee_primero_opus_y_despues_gemini():
    ajustes.guardar("proveedor_lectura", "claude")
    assert extraccion.modelos_configurados() == [
        "claude-opus-5-5", "gemini-3.8-flash", "gemini-3.7-flash"]
    # Los Gemini que se configuran son los mismos de siempre.
    assert extraccion.modelos_gemini() == ["gemini-3.8-flash", "gemini-3.7-flash"]


def test_un_valor_raro_en_los_ajustes_vuelve_a_gemini():
    ajustes.guardar("proveedor_lectura", "otra-cosa")
    assert extraccion.proveedor_lectura() == "gemini"
    ajustes.guardar("esfuerzo_claude", "infinito")
    assert extraccion.esfuerzo_claude() == "medium"


def test_los_recuadros_los_sigue_pidiendo_gemini():
    ajustes.guardar("proveedor_lectura", "claude")
    assert localizar.principal() == "gemini-3.8-flash"


# --------------------------------------------------- lo que se le pide a Claude
def _uniones(nodo) -> int:
    if isinstance(nodo, dict):
        propio = 1 if "anyOf" in nodo or isinstance(nodo.get("type"), list) else 0
        return propio + sum(_uniones(v) for v in nodo.values())
    if isinstance(nodo, list):
        return sum(_uniones(v) for v in nodo)
    return 0


def _objetos_cerrados(nodo) -> bool:
    if isinstance(nodo, dict):
        if nodo.get("type") == "object" and nodo.get("additionalProperties") is not False:
            return False
        return all(_objetos_cerrados(v) for v in nodo.values())
    if isinstance(nodo, list):
        return all(_objetos_cerrados(v) for v in nodo)
    return True


def _sin_listas_de_tipos(nodo) -> bool:
    if isinstance(nodo, dict):
        if isinstance(nodo.get("type"), list):
            return False
        return all(_sin_listas_de_tipos(v) for v in nodo.values())
    if isinstance(nodo, list):
        return all(_sin_listas_de_tipos(v) for v in nodo)
    return True


def test_el_formato_cerrado_cumple_los_limites_de_claude():
    """Claude rechaza («Schema is too complex») más de 16 datos de dos tipos
    y cualquier objeto sin additionalProperties: false."""
    esquema = extraccion.ESQUEMA_CLAUDE
    assert _uniones(esquema) <= 16
    assert _objetos_cerrados(esquema)
    assert _sin_listas_de_tipos(esquema)
    # Todo sigue siendo obligatorio (Claude limita los opcionales a 24).
    assert set(esquema["required"]) == set(esquema["properties"])
    # Los importes conservan el null; los textos van como texto.
    total = esquema["properties"]["total"]
    assert {"type": "null"} in total["anyOf"]
    assert esquema["properties"]["emisor_nif"] == {"type": "string"}
    # El de Gemini no se toca.
    assert extraccion.ESQUEMA["properties"]["total"]["type"] == ["number", "null"]


def test_la_peticion_a_claude(monkeypatch):
    ex = _con_claude(monkeypatch, [_respuesta_claude(BASE_CLAUDE)], modo="no")
    ex.extraer(b"\xff\xd8imagen", "a.pdf", 1)
    peticion = ex._cliente_claude.peticiones[0]
    assert peticion["model"] == "claude-opus-5-5"
    # Las instrucciones de siempre, guardadas para la hoja siguiente.
    sistema = peticion["system"][0]
    assert sistema["text"] == extraccion._PROMPT
    assert sistema["cache_control"] == {"type": "ephemeral"}
    imagen, texto = peticion["messages"][0]["content"]
    assert imagen["type"] == "image"
    assert imagen["source"]["media_type"] == "image/jpeg"
    assert texto["type"] == "text"
    salida = peticion["output_config"]
    assert salida["effort"] == "medium"
    assert salida["format"] == {"type": "json_schema",
                                "schema": extraccion.ESQUEMA_CLAUDE}
    assert peticion["max_tokens"] == extraccion.MAX_TOKENS_SALIDA
    # Opus 5.5 no admite apagar el pensamiento ni temperatura: no se mandan.
    assert "thinking" not in peticion and "temperature" not in peticion


def test_el_esfuerzo_elegido_llega_a_claude(monkeypatch):
    ajustes.guardar("esfuerzo_claude", "high")
    ex = _con_claude(monkeypatch, [_respuesta_claude(BASE_CLAUDE)], modo="no")
    ex.extraer(b"img", "a.pdf", 1)
    assert ex._cliente_claude.peticiones[0]["output_config"]["effort"] == "high"


def test_con_gemini_elegido_no_se_crea_claude(monkeypatch):
    monkeypatch.setattr(extraccion.genai, "Client", lambda **kw: None)
    ex = extraccion.Extractor("clave-gemini", modo_doble="siempre")
    ex.client = GeminiFalso(BASE)
    monkeypatch.setattr(ex, "_claude", lambda: pytest.fail("no toca Claude"))
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert set(ex.client.llamadas) == {"gemini-3.8-flash", "gemini-3.7-flash"}
    assert leido.crudo["_verificacion"] == "doble"


# -------------------------------------------------------------- la lectura
def test_claude_y_gemini_coinciden_y_queda_verificada(monkeypatch):
    ex = _con_claude(monkeypatch, [_respuesta_claude(BASE_CLAUDE)])
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert leido.crudo["_verificacion"] == "doble"
    assert leido.crudo["_discrepancias"] == []
    assert leido.crudo["_modelo_1"] == "claude-opus-5-5"
    assert ex.client.llamadas == ["gemini-3.8-flash"]   # la segunda, Gemini
    # Los textos que Claude deja vacíos vuelven a null, como en Gemini.
    assert leido.crudo["sustituye_a"] is None
    assert leido.crudo["fecha_operacion"] is None


def test_si_claude_y_gemini_discrepan_se_ve(monkeypatch):
    otro = dict(BASE, total=131.0)
    ex = _con_claude(monkeypatch, [_respuesta_claude(BASE_CLAUDE)], datos_gemini=otro)
    crudo = ex.extraer(b"img", "a.pdf", 1).crudo
    campos = {d["campo"] for d in crudo["_discrepancias"]}
    assert "total" in campos


def test_el_gasto_de_claude_cuenta_lo_guardado_a_su_precio(monkeypatch):
    respuesta = _respuesta_claude(BASE_CLAUDE, entrada=3000, escrito=0,
                                  releido=4000, salida=900)
    ex = _con_claude(monkeypatch, [respuesta], modo="no")
    leido = ex.extraer(b"img", "a.pdf", 1)
    modelo, entrada, salida = leido.consumos[0]
    assert modelo == "claude-opus-5-5"
    assert entrada == 3000 + round(4000 * extraccion.CACHE_LECTURA)
    assert salida == 900
    assert costes.precio_de("claude-opus-5-5") == ((4.0, 20.0), True)


def test_si_claude_falla_lee_gemini_y_la_hoja_no_se_pierde(monkeypatch):
    ex = _con_claude(monkeypatch, [ErrorClaude("Error code: 400 - algo raro", 400)])
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert leido.crudo["total"] == 121.0
    assert leido.crudo["_modelo_1"] == "gemini-3.8-flash"


def test_sin_api_key_de_claude_lee_gemini(monkeypatch):
    monkeypatch.setattr(claves, "leer_api_key_claude", lambda: None)
    ajustes.guardar("proveedor_lectura", "claude")
    monkeypatch.setattr(extraccion.genai, "Client", lambda **kw: None)
    ex = extraccion.Extractor("clave-gemini", modo_doble="siempre")
    ex.client = GeminiFalso(BASE)
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert leido.crudo["total"] == 121.0
    assert "claude-opus-5-5" in ex._retirados


def test_si_claude_se_niega_no_se_repite_y_lee_gemini(monkeypatch):
    ex = _con_claude(monkeypatch, [_respuesta_claude({}, stop_reason="refusal")])
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert len(ex._cliente_claude.peticiones) == 1
    assert leido.crudo["total"] == 121.0
    # Lo pagado por la negativa también cuenta.
    assert any(c[0] == "claude-opus-5-5" for c in leido.consumos)


def test_respuesta_cortada_se_pide_con_mas_margen(monkeypatch):
    cortada = _respuesta_claude({}, stop_reason="max_tokens")
    cortada.content = [SimpleNamespace(type="text", text='{"total": 12')]
    ex = _con_claude(monkeypatch, [cortada, _respuesta_claude(BASE_CLAUDE)], modo="no")
    leido = ex.extraer(b"img", "a.pdf", 1)
    topes = [p["max_tokens"] for p in ex._cliente_claude.peticiones]
    assert topes == [extraccion.MAX_TOKENS_SALIDA, extraccion.MAX_TOKENS_AMPLIADO]
    assert leido.crudo["total"] == 121.0


def test_si_claude_no_acepta_el_formato_sigue_sin_el(monkeypatch):
    ex = _con_claude(monkeypatch, [
        ErrorClaude("Error code: 400 - Schema is too complex for compilation", 400),
        _respuesta_claude(BASE_CLAUDE)], modo="no")
    ex.extraer(b"img", "a.pdf", 1)
    primera, segunda = ex._cliente_claude.peticiones
    assert "format" in primera["output_config"]
    assert "format" not in segunda["output_config"]
    assert ex._con_esquema is True          # Gemini sigue con su formato


# ---------------------------------------------------------------- errores
@pytest.mark.parametrize("modo", ["siempre", "no"])
def test_sin_credito_de_claude_sigue_gemini_y_lo_dice(monkeypatch, modo):
    """Sin saldo en Claude no se para la lectura: la API key de Gemini sigue
    valiendo. Claude se deja de pedir en el bloque y se avisa de por qué."""
    ex = _con_claude(monkeypatch, [ErrorClaude(
        "Error code: 400 - Your credit balance is too low to access the "
        "Anthropic API.", 400)], modo=modo)
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert leido.crudo["total"] == 121.0
    assert "claude-opus-5-5" in ex._retirados
    assert "gemini-3.8-flash" in {c[0] for c in leido.consumos}
    assert "no tiene crédito" in ex.aviso_claude()
    assert "1 hoja(s)" in ex.aviso_claude()
    # La hoja siguiente ya no se le pide a Claude.
    ex.extraer(b"img", "a.pdf", 2)
    assert len(ex._cliente_claude.peticiones) == 1
    assert "2 hoja(s)" in ex.aviso_claude()


def test_api_key_de_claude_mala_sigue_gemini_y_lo_dice(monkeypatch):
    ex = _con_claude(monkeypatch, [ErrorClaude(
        "Error code: 401 - invalid x-api-key", 401)])
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert leido.crudo["total"] == 121.0
    assert "API key de Claude no es válida" in ex.aviso_claude()


def test_si_gemini_se_queda_sin_credito_lo_pagado_a_claude_cuenta(monkeypatch):
    """Gemini sin saldo sí para el bloque (como siempre), pero la lectura de
    Claude de esa hoja ya se pagó y su gasto viaja con el aviso."""
    ex = _con_claude(monkeypatch, [_respuesta_claude(BASE_CLAUDE)],
                     datos_gemini=RuntimeError("400 credit balance depleted"))
    with pytest.raises(extraccion.SinCredito) as aviso:
        ex.extraer(b"img", "a.pdf", 1)
    assert [c[0] for c in aviso.value.consumos] == ["claude-opus-5-5"]


def test_con_claude_al_dia_no_hay_aviso(monkeypatch):
    ex = _con_claude(monkeypatch, [_respuesta_claude(BASE_CLAUDE)])
    ex.extraer(b"img", "a.pdf", 1)
    assert ex.aviso_claude() == ""


def test_claude_ocupado_se_reintenta(monkeypatch):
    ex = _con_claude(monkeypatch, [
        ErrorClaude("Error code: 529 - overloaded_error", 529),
        _respuesta_claude(BASE_CLAUDE)], modo="no")
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert len(ex._cliente_claude.peticiones) == 2
    assert leido.crudo["_modelo_1"] == "claude-opus-5-5"


def test_si_claude_pide_calma_gemini_no_se_para(monkeypatch):
    """El 429 de Claude solo frena a Claude: Gemini sigue leyendo, y cuando
    Claude se da por parado las hojas siguientes las leen los dos Gemini."""
    ex = _con_claude(monkeypatch, [ErrorClaude(
        "Error code: 429 - rate_limit_error", 429, {"retry-after": "7"})])
    monkeypatch.setattr(ex, "_esperar_pausa", lambda ia="gemini": None)
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert ex._sin_cuota.get("claude")
    assert not ex._sin_cuota.get("gemini")
    assert ex._pausa_hasta.get("claude", 0) > 0
    assert "gemini" not in ex._pausa_hasta
    assert leido.crudo["total"] == 121.0     # la leyó Gemini
    siguiente = ex.extraer(b"img", "a.pdf", 2)
    assert {siguiente.crudo["_modelo_1"], siguiente.crudo["_modelo_2"]} == {
        "gemini-3.8-flash", "gemini-3.7-flash"}
    assert "2 hoja(s)" in ex.aviso_claude()


def test_el_limite_de_gasto_de_claude_para_sin_esperar(monkeypatch):
    """El tope mensual de la cuenta de Claude no vuelve esperando: ni se
    espera ni se insiste, y se dice que es el límite de gasto."""
    error = ErrorClaude("Error code: 429 - rate_limit_error", 429)
    error.body = {"type": "error", "error": {
        "type": "rate_limit_error", "message": "spend limit",
        "details": {"error_code": "enforced_spend_limit_reached"}}}
    ex = _con_claude(monkeypatch, [error])
    monkeypatch.setattr(ex, "_pausar",
                        lambda *a, **k: pytest.fail("no se espera al tope de gasto"))
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert len(ex._cliente_claude.peticiones) == 1
    assert "límite de gasto mensual" in ex._sin_cuota["claude"]
    assert leido.crudo["total"] == 121.0


def test_con_el_tope_ampliado_claude_tiene_mas_tiempo(monkeypatch):
    cortada = _respuesta_claude({}, stop_reason="max_tokens")
    cortada.content = [SimpleNamespace(type="text", text='{"total": 12')]
    ex = _con_claude(monkeypatch, [cortada, _respuesta_claude(BASE_CLAUDE)], modo="no")
    ex.extraer(b"img", "a.pdf", 1)
    tiempos = [p["timeout"] for p in ex._cliente_claude.peticiones]
    assert tiempos == [extraccion.TIEMPO_LIMITE_CLAUDE,
                       extraccion.TIEMPO_LIMITE_CLAUDE_AMPLIADO]


def test_el_cliente_de_claude_lleva_su_tiempo_limite(monkeypatch):
    import anthropic
    creado = {}

    class Falso:
        def __init__(self, **kw):
            creado.update(kw)
    monkeypatch.setattr(anthropic, "Anthropic", Falso)
    monkeypatch.setattr(extraccion.genai, "Client", lambda **kw: None)
    ex = extraccion.Extractor("clave-gemini", clave_claude="sk-ant-prueba")
    ex._claude()
    assert creado == {"api_key": "sk-ant-prueba",
                      "timeout": extraccion.TIEMPO_LIMITE_CLAUDE,
                      "max_retries": 0}


def test_la_peticion_es_valida_para_el_sdk_de_claude(monkeypatch):
    """Lo que se manda pasa por el SDK de verdad hasta justo antes de salir
    a internet (se para en el transporte): nombres y forma correctos."""
    import anthropic
    import httpx2
    enviado = {}

    def transporte(peticion):
        enviado["url"] = str(peticion.url)
        enviado["cuerpo"] = json.loads(peticion.content)
        enviado["cabeceras"] = dict(peticion.headers)
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant",
            "model": "claude-opus-5-5", "stop_reason": "end_turn",
            "stop_sequence": None,
            "content": [{"type": "text", "text": json.dumps(BASE_CLAUDE)}],
            "usage": {"input_tokens": 3000, "output_tokens": 800,
                      "cache_creation_input_tokens": 3500,
                      "cache_read_input_tokens": 0}})

    cliente = anthropic.Anthropic(
        api_key="sk-ant-prueba", max_retries=0,
        http_client=anthropic.DefaultHttpxClient(
            transport=httpx2.MockTransport(transporte)))
    ajustes.guardar("proveedor_lectura", "claude")
    monkeypatch.setattr(extraccion.genai, "Client", lambda **kw: None)
    ex = extraccion.Extractor("clave-gemini", modo_doble="no",
                              clave_claude="sk-ant-prueba")
    ex._cliente_claude = cliente
    leido = ex.extraer(b"\xff\xd8imagen", "a.pdf", 1)
    assert enviado["url"].endswith("/v1/messages")
    assert enviado["cabeceras"]["x-api-key"] == "sk-ant-prueba"
    cuerpo = enviado["cuerpo"]
    assert cuerpo["model"] == "claude-opus-5-5"
    assert cuerpo["output_config"]["format"]["type"] == "json_schema"
    assert cuerpo["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert leido.crudo["total"] == 121.0
    assert leido.consumos[0][1] == 3000 + round(3500 * extraccion.CACHE_ESCRITURA)


# ------------------------------------------------------------------ coste
def test_coste_orientativo_de_una_hoja_con_claude():
    euros = costes.coste_por_factura(150, "claude-opus-5-5")
    assert 0.03 < euros < 0.08
    # Gemini sigue estimándose como siempre.
    assert costes.coste_por_factura(150, "gemini-3.7-flash") < 0.01


# ------------------------------------------------- el desplegable en pantalla
def _dialogo():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from facturas_excel.dialogo_modelos import DialogoModelos
    return DialogoModelos()


def test_el_desplegable_viene_en_gemini_y_guarda_claude(monkeypatch):
    monkeypatch.setattr(claves, "leer_api_key_claude", lambda: "sk-ant-prueba")
    d = _dialogo()
    assert d.proveedor() == "gemini"
    assert not d.combo_esfuerzo.isEnabled()
    assert [d.combo_proveedor.itemData(i) for i in range(d.combo_proveedor.count())] \
        == ["gemini", "claude"]
    d.combo_proveedor.setCurrentIndex(d.combo_proveedor.findData("claude"))
    assert d.combo_esfuerzo.isEnabled()
    assert "guardada" in d.lbl_clave_claude.text()
    d.combo_esfuerzo.setCurrentIndex(d.combo_esfuerzo.findData("high"))
    resumen = d.guardar()
    assert "Claude Opus 5.5" in resumen
    assert extraccion.proveedor_lectura() == "claude"
    assert extraccion.esfuerzo_claude() == "high"
    # Los modelos de Gemini no se tocan al elegir Claude.
    assert ajustes.leer("modelo_principal") == "gemini-3.8-flash"
    # Al volver a abrir, sale lo guardado; y se puede volver a Gemini.
    d2 = _dialogo()
    assert d2.proveedor() == "claude"
    assert d2.combo_principal.currentText() == "gemini-3.8-flash"
    d2.combo_proveedor.setCurrentIndex(d2.combo_proveedor.findData("gemini"))
    d2.guardar()
    assert extraccion.modelos_configurados() == ["gemini-3.8-flash",
                                                 "gemini-3.7-flash"]


def test_el_desplegable_avisa_si_falta_la_clave_de_claude(monkeypatch):
    monkeypatch.setattr(claves, "leer_api_key_claude", lambda: None)
    d = _dialogo()
    d.combo_proveedor.setCurrentIndex(d.combo_proveedor.findData("claude"))
    assert "Falta la API key de Claude" in d.lbl_clave_claude.text()


def test_la_clave_de_claude_se_guarda_aparte(monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from facturas_excel import dialogo_modelos
    guardadas = {}
    monkeypatch.setattr(claves.keyring, "set_password",
                        lambda servicio, usuario, clave: guardadas.update(
                            {(servicio, usuario): clave}))
    monkeypatch.setattr(claves, "leer_api_key_claude", lambda: None)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(
        lambda *a, **k: ("  sk-ant-nueva  ", True)))
    assert dialogo_modelos.pedir_api_key_claude() is True
    assert guardadas == {("FacturasAExcel", "claude_api_key"): "sk-ant-nueva"}


def test_sin_clave_de_claude_no_empieza_a_leer_y_lo_dice(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    from facturas_excel import app, ventana_lectura
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda _p, titulo, texto: avisos.append((titulo, texto)))
    monkeypatch.setattr(ventana_lectura, "leer_api_key", lambda: "clave-gemini")
    monkeypatch.setattr(ventana_lectura, "leer_api_key_claude", lambda: None)
    monkeypatch.setattr(ventana_lectura, "Worker",
                        lambda *a, **k: pytest.fail("no debe empezar a leer"))
    ajustes.guardar("proveedor_lectura", "claude")
    ruta = tmp_path / "factura.png"
    ruta.write_bytes(b"imagen-ficticia")
    v = app.VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    try:
        v.procesar_rutas([str(ruta)])
        assert avisos and avisos[0][0] == "Falta la API key de Claude"
        assert not v._cola
    finally:
        v.close()
        v.deleteLater()


def test_con_gemini_elegido_no_hace_falta_la_clave_de_claude(monkeypatch):
    from facturas_excel import ventana_lectura
    monkeypatch.setattr(ventana_lectura, "leer_api_key_claude", lambda: None)
    assert ventana_lectura.falta_clave_claude() is False
    ajustes.guardar("proveedor_lectura", "claude")
    assert ventana_lectura.falta_clave_claude() is True
    monkeypatch.setattr(ventana_lectura, "leer_api_key_claude", lambda: "sk-ant-x")
    assert ventana_lectura.falta_clave_claude() is False


# ----------------------------------------------- gasto, avisos y recogida
def test_el_gasto_del_bloque_se_desglosa_por_ia_y_por_hoja():
    from facturas_excel import hilos
    w = hilos.Worker([], "clave-gemini")
    emitido = []
    w.gasto.connect(lambda modelo, coste: emitido.append((modelo, coste)))
    w._leidas = [0, 1]
    w._registrar_consumo([("claude-opus-5-5", 3000, 900),
                          ("gemini-3.8-flash", 1000, 120),
                          ("claude-opus-5-5", 3000, 900),
                          ("gemini-3.8-flash", 1000, 120)])
    assert w.desglose_gasto.startswith("Claude ")
    assert "+ Gemini " in w.desglose_gasto and "en 2 hoja(s)" in w.desglose_gasto
    assert emitido and emitido[0][0] == "claude-opus-5-5"


def test_con_gemini_el_gasto_no_cambia():
    from facturas_excel import hilos
    w = hilos.Worker([], "clave-gemini")
    w._leidas = [0]
    w._registrar_consumo([("gemini-3.8-flash", 1000, 120)])
    assert w.desglose_gasto == ""


def test_la_ventana_avisa_de_las_hojas_sin_claude(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from facturas_excel import app
    v = app.VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    avisos = []
    monkeypatch.setattr(v, "_avisar", lambda texto, *a, **k: avisos.append(texto))
    try:
        v._avisar_hojas_sin_claude(SimpleNamespace(aviso_claude=""))
        assert avisos == []
        v._avisar_hojas_sin_claude(SimpleNamespace(
            aviso_claude="Claude no ha leído 3 hoja(s) de este bloque"))
        assert avisos == ["Claude no ha leído 3 hoja(s) de este bloque"]
    finally:
        v.close()
        v.deleteLater()


def test_identificar_escaneos_sigue_con_gemini(monkeypatch):
    from facturas_excel import recoger
    creados = []

    class ExtractorFalso:
        def __init__(self, api_key, modelos=None, modo_doble=None, **kw):
            creados.append(modelos)
    monkeypatch.setattr(extraccion, "Extractor", ExtractorFalso)
    ajustes.guardar("proveedor_lectura", "claude")
    recoger.leer_con_gemini([], "", "clave-gemini")
    assert creados == [["gemini-3.8-flash", "gemini-3.7-flash"]]
    assert recoger.coste_estimado_gemini([]) == 0


def test_el_coste_estimado_con_claude_suma_las_dos_lecturas():
    ajustes.guardar("proveedor_lectura", "claude")
    juntas = costes.coste_por_factura(150)
    solo_claude = costes.coste_por_factura(150, "claude-opus-5-5")
    assert juntas > solo_claude > 0.03
    ajustes.guardar("doble_lectura", "no")
    assert costes.coste_por_factura(150) == solo_claude


def test_el_aviso_del_tope_no_promete_lo_de_google_con_claude():
    costes.guardar_tope(0.01)
    costes.registrar("claude-opus-5-5", 3000, 900)
    ajustes.guardar("proveedor_lectura", "claude")
    assert "Google" not in costes.aviso_tope()
    ajustes.guardar("proveedor_lectura", "gemini")
    assert "Google" in costes.aviso_tope()


# ------------------------------------------ segunda revisión (13/10/2026)
def test_el_402_de_claude_lo_retira_y_sigue_gemini(monkeypatch):
    error = ErrorClaude("Error code: 402 - payment declined", 402)
    ex = _con_claude(monkeypatch, [error])
    leido = ex.extraer(b"img", "a.pdf", 1)
    assert "claude-opus-5-5" in ex._retirados
    assert leido.crudo["total"] == 121.0
    assert "cobro" in ex.aviso_claude()


def test_el_motivo_que_apaga_claude_manda_sobre_el_de_una_hoja(monkeypatch):
    ex = _con_claude(monkeypatch, [
        _respuesta_claude({}, stop_reason="refusal"),
        ErrorClaude("Error code: 400 - Your credit balance is too low", 400)])
    ex.extraer(b"img", "a.pdf", 1)          # Claude se niega con esta hoja
    ex.extraer(b"img", "a.pdf", 2)          # y luego se queda sin saldo
    ex.extraer(b"img", "a.pdf", 3)          # ya ni se le pide
    aviso = ex.aviso_claude()
    assert "3 hoja(s)" in aviso and "no tiene crédito" in aviso


def test_el_429_de_claude_no_dice_que_la_hoja_se_pierde(monkeypatch):
    ex = _con_claude(monkeypatch, [ErrorClaude("Error code: 429 - rate", 429)])
    monkeypatch.setattr(ex, "_esperar_pausa", lambda ia="gemini": None)
    ex.extraer(b"img", "a.pdf", 1)
    assert "lo lee Gemini" in ex._sin_cuota["claude"]
    assert "no se ha leído" not in ex.aviso_claude()


@pytest.mark.parametrize("modo", ["dudosas", "no"])
def test_lo_pagado_a_claude_cuenta_si_gemini_para_en_otros_modos(monkeypatch, modo):
    dudosa = dict(BASE_CLAUDE, confianza="baja")
    respuesta = (_respuesta_claude(dudosa) if modo == "dudosas"
                 else _respuesta_claude({}, stop_reason="refusal"))
    ex = _con_claude(monkeypatch, [respuesta], modo=modo,
                     datos_gemini=RuntimeError("400 credit balance depleted"))
    with pytest.raises(extraccion.SinCredito) as aviso:
        ex.extraer(b"img", "a.pdf", 1)
    assert [c[0] for c in aviso.value.consumos] == ["claude-opus-5-5"]


def _ventana():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from facturas_excel import app
    return app.VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)


def test_con_paginas_sin_leer_el_aviso_de_claude_va_dentro(monkeypatch):
    v = _ventana()
    avisos = []
    monkeypatch.setattr(v, "_avisar", lambda texto, *a, **k: avisos.append(texto))
    try:
        worker = SimpleNamespace(
            fallos=[("a.pdf", 2, "No leída")], sin_credito="",
            aviso_claude="Claude no ha leído 1 hoja(s) de este bloque")
        v._avisar_paginas_no_leidas(worker)
        v._avisar_hojas_sin_claude(worker)
        assert len(avisos) == 1
        assert "Páginas sin leer" in avisos[0] and "Claude no ha leído" in avisos[0]
    finally:
        v.close()
        v.deleteLater()


def test_los_recuadros_no_borran_el_desglose_del_bloque(monkeypatch):
    from PySide6.QtCore import QObject
    v = _ventana()
    try:
        lectura = QObject()
        lectura.desglose_gasto = "Claude 0,10 € + Gemini 0,01 € en 2 hoja(s)"
        recuadros = QObject()
        monkeypatch.setattr(v, "sender", lambda: lectura)
        v._on_gasto("claude-opus-5-5", 0.11)
        assert "Claude 0,10 €" in v.lbl_gasto.text()
        monkeypatch.setattr(v, "sender", lambda: recuadros)
        v._on_gasto("gemini-3.8-flash", 0.001)
        assert "último bloque: Claude 0,10 €" in v.lbl_gasto.text()
        # Un bloque leído solo con Gemini lo quita.
        solo_gemini = QObject()
        solo_gemini.desglose_gasto = ""
        monkeypatch.setattr(v, "sender", lambda: solo_gemini)
        v._on_gasto("gemini-3.8-flash", 0.002)
        assert "Claude" not in v.lbl_gasto.text()
    finally:
        v.close()
        v.deleteLater()


def test_con_gemini_lo_ultimo_de_claude_no_cambia_la_estimacion():
    antes = costes.coste_por_factura(150)
    costes.registrar("claude-opus-5-5", 3000, 900)
    assert costes.ultimo_modelo() == "claude-opus-5-5"
    assert costes.coste_por_factura(150) < 0.01
    assert costes.coste_por_factura(150) == costes.coste_por_factura(
        150, "gemini-3.8-flash")
    assert antes < 0.01


# ------------------------------------- tope de 20 € (pedido el 13/10/2026)
def test_el_tope_del_mes_pasa_a_20_euros_una_sola_vez():
    ajustes.guardar("tope_mensual", 5.0)          # lo que tenía antes
    assert costes.tope() == 20.0                  # al actualizar, 20 €
    costes.guardar_tope(12.0)                     # si luego lo cambia…
    assert costes.tope() == 12.0                  # …manda lo suyo


def test_sin_tope_guardado_tambien_son_20_euros():
    assert costes.tope() == 20.0
