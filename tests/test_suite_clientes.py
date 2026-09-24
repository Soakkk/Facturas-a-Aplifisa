"""Directorio común de clientes compartido con los demás programas."""
import json
import os

from facturas_excel import clientes, procesar, suite


def _escribir(datos):
    ruta = suite.ruta_directorio()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(datos, fh)
    suite._cache.update(mtime=None, ruta=None, datos=None)
    return ruta


def _gasolinera(n):
    return {"emisor_nif": "B12345674", "emisor_nombre": "GASOLINERA PRUEBA SL",
            "receptor_nif": "12345678Z", "receptor_nombre": "J. PEREZ",
            "num_factura": f"G-{n}", "fecha": "10/02/2026"}


def test_un_cliente_de_la_suite_se_reconoce_sin_preguntar():
    _escribir({"schema_version": 1, "clientes": {
        "12345678Z": {"nif": "12345678Z", "nombre": "José Pérez"}}})
    analisis = procesar.analizar_cliente([_gasolinera(1), _gasolinera(2)])
    assert not analisis.dudoso
    assert analisis.mejor.nif == "12345678Z"
    assert analisis.mejor.nombre == "José Pérez"      # el nombre de la suite
    assert "José Pérez" in clientes.nombres_conocidos()


def test_sin_directorio_todo_sigue_igual():
    assert suite.clientes() == {}
    assert procesar.analizar_cliente([_gasolinera(1)]).dudoso


def test_confirmar_un_cliente_lo_apunta_en_la_suite():
    clientes.marcar_cliente("12345678Z", "José Pérez")
    with open(suite.ruta_directorio(), encoding="utf-8") as fh:
        datos = json.load(fh)
    ficha = datos["clientes"]["12345678Z"]
    assert datos["schema_version"] == 1
    assert ficha["nombre"] == "José Pérez"
    assert ficha["metadatos"]["nombre"]["origen"] == "facturas"


def test_un_nombre_distinto_no_pisa_el_de_la_suite():
    ruta = _escribir({"schema_version": 1, "clientes": {
        "12345678Z": {"nif": "12345678Z", "nombre": "Ana original",
                      "carpeta": "C:/Ana"}}, "otro": "se conserva"})
    assert suite.registrar_cliente("12345678Z", "Ana alternativa")
    with open(ruta, encoding="utf-8") as fh:
        datos = json.load(fh)
    ficha = datos["clientes"]["12345678Z"]
    assert ficha["nombre"] == "Ana original"
    assert ficha["carpeta"] == "C:/Ana" and datos["otro"] == "se conserva"
    assert ficha["conflictos"]["nombre"] == ["Ana original", "Ana alternativa"]
    # Con el nombre en conflicto no se elige ninguno.
    assert suite.nombre_de("12345678Z") == ""


def test_un_fichero_de_otro_formato_no_se_toca():
    ruta = _escribir({"version": 7, "cosas": []})
    assert not suite.registrar_cliente("12345678Z", "X")
    with open(ruta, encoding="utf-8") as fh:
        assert json.load(fh) == {"version": 7, "cosas": []}
