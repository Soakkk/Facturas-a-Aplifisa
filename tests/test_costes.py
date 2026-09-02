"""Contador de gasto de Gemini: tarifa por modelo, acumulado del mes y tope.

Los tests parchean `dir_datos` con tmp_path para no tocar el gasto real del
usuario (mismo truco que en la memoria de proveedores).
"""

from datetime import date

import pytest

from facturas_excel import ajustes, costes


@pytest.fixture(autouse=True)
def datos_aparte(tmp_path, monkeypatch):
    monkeypatch.setattr(costes, "dir_datos", lambda: str(tmp_path))
    monkeypatch.setattr(ajustes, "dir_datos", lambda: str(tmp_path))


def test_la_tarifa_sale_del_nombre_real_del_modelo():
    # El nombre que devuelve Gemini lleva cola de version.
    (entrada, salida), conocido = costes.precio_de("gemini-2.5-flash-preview-05-20")
    assert (entrada, salida) == (0.30, 2.50) and conocido
    # flash-lite tiene su propia tarifa y no debe confundirse con flash
    (entrada, _), _ = costes.precio_de("gemini-2.5-flash-lite")
    assert entrada == 0.10


def test_un_modelo_desconocido_se_cobra_como_el_flash_mas_caro():
    (entrada, salida), conocido = costes.precio_de("gemini-9.9-turbo")
    assert not conocido
    assert (entrada, salida) == costes.PRECIO_DESCONOCIDO


def test_el_coste_de_una_factura_sale_de_sus_tokens(monkeypatch):
    monkeypatch.setattr(ajustes, "leer", lambda c, d=None: 1.0 if c == "euros_por_dolar" else d)
    # 1.548 tokens de entrada y 400 de salida con 2.5 Flash (0,30 / 2,50 $)
    esperado = 1548 / 1e6 * 0.30 + 400 / 1e6 * 2.50
    assert costes.coste("gemini-2.5-flash", 1548, 400) == round(esperado, 6)


def test_el_gasto_se_acumula_por_meses():
    costes.registrar("gemini-2.5-flash", 1548, 400, dia=date(2026, 9, 2))
    costes.registrar("gemini-2.5-flash", 1548, 400, dia=date(2026, 9, 15))
    costes.registrar("gemini-2.5-flash", 1548, 400, dia=date(2026, 10, 1))

    septiembre = costes.gasto_del_mes(date(2026, 9, 30))
    octubre = costes.gasto_del_mes(date(2026, 10, 31))
    assert costes.facturas_del_mes(date(2026, 9, 30)) == 2
    assert septiembre == round(2 * octubre, 6)


def test_el_tope_se_guarda_y_avisa_al_pasarse():
    costes.guardar_tope(5.0)
    assert costes.tope() == 5.0
    assert costes.aviso_tope() == ""          # recien empezado el mes

    costes.registrar("gemini-2.5-pro", 10_000_000, 1_000_000)   # un disparate
    assert costes.porcentaje_gastado() > 100
    assert "superado el tope" in costes.aviso_tope()


def test_avisa_tambien_al_acercarse_al_tope():
    costes.guardar_tope(1.0)
    # ~0,86 € con 2.5 Pro: pasa del 80 % sin llegar al 100 %
    costes.registrar("gemini-2.5-pro", 750_000, 0)
    assert 80 <= costes.porcentaje_gastado() < 100
    assert "% del tope" in costes.aviso_tope()


def test_el_resumen_dice_modelo_lote_y_mes():
    costes.guardar_tope(5.0)
    costes.registrar("gemini-2.5-flash", 1548, 400)
    texto = costes.resumen("gemini-2.5-flash", 0.0012)
    assert "gemini-2.5-flash" in texto
    assert "este lote" in texto and "mes:" in texto
    assert "5,00 €" in texto


def test_el_modelo_sin_tarifa_se_marca_como_estimado():
    assert "estimada" in costes.resumen("gemini-9.9-turbo")
    assert "estimada" not in costes.resumen("gemini-2.5-flash")


def test_importes_de_centimos_no_salen_como_cero():
    assert costes._eur(0.0034) == "0,0034 €"
    assert costes._eur(1.5) == "1,50 €"


# ---------------- lo que devuelve Gemini (si el SDK cambia, salta aqui) ------
class _Uso:
    prompt_token_count = 1548
    candidates_token_count = 300
    thoughts_token_count = 100


class _Respuesta:
    model_version = "gemini-2.5-flash-preview-05-20"
    usage_metadata = _Uso()


def test_se_leen_el_modelo_real_y_los_tokens_de_la_respuesta():
    from facturas_excel.extraccion import _consumo
    modelo, entrada, salida = _consumo(_Respuesta())
    assert modelo == "gemini-2.5-flash-preview-05-20"
    assert entrada == 1548
    assert salida == 400          # el "pensamiento" tambien se paga como salida


def test_si_la_respuesta_no_trae_consumo_no_se_rompe_nada():
    from facturas_excel.extraccion import _consumo
    assert _consumo(object()) == ("", 0, 0)
