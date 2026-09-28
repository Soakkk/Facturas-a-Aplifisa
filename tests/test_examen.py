"""Examen de precisión: se mide con facturas revisadas, sin Gemini de verdad."""

import fitz

from facturas_excel import examen, historial, registro_facturas
from facturas_excel.modelo import Factura


def _pdf(ruta, texto="FACTURA"):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), texto)
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


def _exportada(tmp_path, numero, nif, total, pdf=True, paginas=1):
    f = Factura(num_factura=numero, fecha="10/03/2026", nombre=f"PROV {nif}",
                nif=nif, base_iva=round(total / 1.21, 2),
                pct_iva=21.0, cuota_iva=round(total - round(total / 1.21, 2), 2),
                total_impreso=total)
    taco = _pdf(tmp_path / f"taco-{numero}.pdf")
    f.origen_imagen, f.pagina_origen, f.ultima_pagina_origen = taco, 1, paginas
    historial.registrar("12345678Z", {"gasto": [f]}, {}, "CLIENTE DE PRUEBA")
    if pdf:
        propio = _pdf(tmp_path / f"{numero}.pdf")
        registro_facturas.archivar("12345678Z", "CLIENTE DE PRUEBA",
                                   [("gasto", f, propio)])
    return f


def _lectura(f, total=None, nif=None):
    return {"emisor_nif": nif or f.nif, "receptor_nif": "12345678Z",
            "num_factura": f.num_factura, "fecha": f.fecha,
            "lineas_iva": [{"base": f.base_iva, "tipo_iva": 21, "cuota_iva": f.cuota_iva}],
            "total": total if total is not None else f.total_impreso}


def test_solo_entran_facturas_de_una_hoja_con_documento(tmp_path):
    _exportada(tmp_path, "F-1", "B12345674", 121.0)
    _exportada(tmp_path, "F-2", "B30048276", 242.0, paginas=2, pdf=False)
    casos = examen.casos_disponibles()
    assert [c.esperado["num_factura"] for c in casos] == ["F-1"]
    assert casos[0].ruta.endswith("F-1.pdf")


def test_se_varia_de_proveedor_antes_de_repetir(tmp_path):
    for i in range(4):
        _exportada(tmp_path, f"A-{i}", "B12345674", 121.0 + i)
    _exportada(tmp_path, "B-1", "B30048276", 50.0)
    casos = examen.casos_disponibles(maximo=2)
    assert {c.esperado["nif"] for c in casos} == {"B12345674", "B30048276"}


def test_porcentajes_por_modelo_y_verificadas_con_error(tmp_path):
    buena = _exportada(tmp_path, "F-1", "B12345674", 121.0)
    trampa = _exportada(tmp_path, "F-2", "B30048276", 242.0)
    casos = examen.casos_disponibles()
    por_numero = {"F-1": buena, "F-2": trampa}
    imagenes = {id(c): c.esperado["num_factura"] for c in casos}

    def lector(modelo, img):
        f = por_numero[img.decode()]
        if f is trampa:
            # Los dos modelos leen el mismo total equivocado: saldría verde.
            return _lectura(f, total=224.0), [(modelo, 1000, 100)]
        if modelo == "modelo-b":
            return _lectura(f, nif="B12345678"), [(modelo, 1000, 100)]
        return _lectura(f), [(modelo, 1000, 100)]

    r = examen.pasar(casos, lector, ["modelo-a", "modelo-b"],
                     imagen=lambda c: imagenes[id(c)].encode())
    assert r.casos == 2
    assert r.porcentaje("modelo-a", "nif") == 100.0
    assert r.porcentaje("modelo-b", "nif") == 50.0
    assert r.porcentaje("modelo-a", "total") == 50.0
    assert r.verificadas == 1
    assert len(r.verificadas_con_error) == 1 and "total" in r.verificadas_con_error[0]
    assert r.coste > 0

    examen.guardar(r, "1.17.0")
    [anterior] = examen.anteriores()
    assert anterior["version"] == "1.17.0"
    assert examen.porcentaje_guardado(anterior, "modelo-a") == r.porcentaje("modelo-a")


def test_una_hoja_que_no_se_lee_no_para_el_examen(tmp_path):
    _exportada(tmp_path, "F-1", "B12345674", 121.0)

    def lector(modelo, img):
        raise RuntimeError("sin respuesta")

    r = examen.pasar(examen.casos_disponibles(), lector, ["modelo-a"],
                     imagen=lambda c: b"x")
    assert r.casos == 0 and r.fallos_lectura == 1


def test_la_ventana_estima_el_coste_y_sin_clave_no_deja_pasar(tmp_path):
    from PySide6.QtWidgets import QApplication
    from facturas_excel.dialogo_examen import DialogoExamen
    QApplication.instance() or QApplication([])
    _exportada(tmp_path, "F-1", "B12345674", 121.0)
    d = DialogoExamen(api_key="")
    assert "1 factura(s)" in d.lbl_preparado.text()
    assert not d.btn_pasar.isEnabled()
    d = DialogoExamen(api_key="clave")
    assert d.btn_pasar.isEnabled()
