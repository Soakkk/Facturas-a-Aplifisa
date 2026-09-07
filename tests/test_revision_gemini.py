"""Orden de mantenimiento del modelo Gemini preparada desde la aplicacion."""

from facturas_excel import revision_gemini


def test_la_orden_prioriza_calidad_y_fuentes_oficiales():
    texto = revision_gemini.texto_solicitud("1.2.3")

    assert "gemini-3.7-flash" in texto
    assert "v1.2.3" in texto
    assert "NO quiero bajar calidad" in texto
    assert "documentación oficial" in texto
    assert "no preview" in texto
    assert "No uses aliases latest" in texto


def test_la_orden_se_guarda_en_los_datos_del_usuario(tmp_path, monkeypatch):
    monkeypatch.setattr(revision_gemini, "dir_datos", lambda: str(tmp_path))

    texto, ruta = revision_gemini.guardar_solicitud("1.2.3")

    assert ruta == str(tmp_path / revision_gemini.FICHERO_SOLICITUD)
    assert (tmp_path / revision_gemini.FICHERO_SOLICITUD).read_text(
        encoding="utf-8") == texto
