from facturas_excel import notas_version


def test_notas_se_marcan_como_vistas(monkeypatch):
    datos = {}
    monkeypatch.setattr(notas_version.ajustes, "leer",
                        lambda clave, defecto=None: datos.get(clave, defecto))
    monkeypatch.setattr(notas_version.ajustes, "guardar",
                        lambda clave, valor: datos.__setitem__(clave, valor))

    assert not notas_version.ya_vistas("1.13.0")
    notas_version.marcar_vistas("1.13.0")
    assert notas_version.ya_vistas("1.13.0")
    assert "Cola para lotes grandes" in notas_version.contenido("1.13.0")


def test_la_1_26_1_cuenta_lo_de_la_estimacion_directa():
    """Corta y en su idioma: qué cambia, que se pregunta una vez por cliente
    y que lo ya importado como «Sólo IVA» no cambia solo."""
    from facturas_excel import __version__
    assert __version__ == "1.26.1"
    texto = notas_version.contenido(__version__)
    assert "IRPF/IVA" in texto and "Sólo IVA" in texto
    assert "primera vez" in texto and "Régimen de IRPF de este cliente" in texto
    assert "no cambia solo" in texto
