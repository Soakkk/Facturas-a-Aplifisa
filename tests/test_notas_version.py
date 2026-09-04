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
