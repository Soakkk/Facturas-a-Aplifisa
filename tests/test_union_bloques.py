"""Continuaciones sintéticas a ambos lados de una parte interna de PDF."""
import pytest
from facturas_excel.procesar import preparar_lote
from facturas_excel.union_bloques import unir_ultimo_bloque


def cabecera(numero="F-1", **extra):
    return dict(emisor_nombre="PROVEEDOR DE PRUEBA", emisor_nif="B12345674",
                receptor_nombre="CLIENTE DE EJEMPLO", receptor_nif="12345678Z",
                num_factura=numero, fecha="01/04/2026", lineas_iva=[{}],
                estado_pagina_factura="inicio", **extra)


def resumen(**extra):
    return dict(total=121, lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21)],
                estado_pagina_factura="final", **extra)


def bloque(hojas, nif="12345678Z", origen="lote.pdf"):
    crudos = [(b"imagen", origen, pagina, d) for pagina, d in hojas]
    return dict(cliente="CLIENTE DE EJEMPLO", nif=nif, crudos=crudos,
                procesadas=preparar_lote(crudos, "CLIENTE DE EJEMPLO", nif), muestras={"a": "id"})


def test_une_25_26_y_conserva_otras_facturas_corregidas():
    a = bloque([(1, cabecera("OTRA")), (25, cabecera())])
    b = bloque([(26, resumen()), (28, cabecera("ULTIMA"))])
    otras = [a["procesadas"][0][1], b["procesadas"][1][1]]
    otras[0].facturas[0].nombre = "CORRECCIÓN DE PRUEBA"
    mapas = [a["muestras"], b["muestras"]]
    assert unir_ultimo_bloque([a, b]) is True
    pr = a["procesadas"][-1][1]
    assert pr.pagina == 25 and pr.facturas[0].ultima_pagina_origen == 26
    assert pr.facturas[0].num_factura == "F-1" and pr.facturas[0].base_iva == 100
    assert [r[2] for r in a["crudos"]] == [1, 25, 26]
    assert [r[2] for r in b["crudos"]] == [28]
    assert a["procesadas"][0][1] is otras[0] and b["procesadas"][0][1] is otras[1]
    assert a["muestras"] is mapas[0] and b["muestras"] is mapas[1]
    assert "25, 26" in pr.aviso


def test_consume_todas_las_paginas_de_la_primera_factura_nueva():
    a = bloque([(25, cabecera())])
    b = bloque([(26, dict(estado_pagina_factura="intermedia")), (27, resumen())])
    assert len(b["procesadas"]) == 1
    assert unir_ultimo_bloque([a, b]) is True
    assert not b["procesadas"] and not b["crudos"]
    assert [r[2] for r in a["crudos"]] == [25, 26, 27]
    pr = a["procesadas"][0][1]
    assert pr.facturas[0].ultima_pagina_origen == 27
    assert "25, 26, 27" in pr.aviso


@pytest.mark.parametrize("campo,valor", [("edicion_manual", True), ("revision_confirmada", True), ("tipo_revision", "venta")])
@pytest.mark.parametrize("lado", [0, 1])
def test_no_pisa_candidato_editado_y_avisa(campo, valor, lado):
    bloques = [bloque([(25, cabecera())]), bloque([(26, resumen())])]
    candidato = bloques[lado]["procesadas"][0][1]
    setattr(candidato.facturas[0], campo, valor)
    assert unir_ultimo_bloque(bloques) is False
    assert bloques[lado]["procesadas"][0][1] is candidato
    assert "unión manual" in candidato.aviso
    assert all(len(b["crudos"]) == 1 for b in bloques)


@pytest.mark.parametrize("nif,origen,pagina", [("B12345674", "lote.pdf", 26), ("12345678Z", "otro.pdf", 26), ("12345678Z", "lote.pdf", 27)])
def test_no_une_cliente_origen_o_pagina_incompatible(nif, origen, pagina):
    bloques = [bloque([(25, cabecera())]), bloque([(pagina, resumen())], nif, origen)]
    assert unir_ultimo_bloque(bloques) is False
    assert all(len(b["crudos"]) == 1 for b in bloques)


@pytest.mark.parametrize("campo,valor", [("eliminada", True), ("tratamiento_manual", "Apartada para revisión")])
def test_no_resucita_factura_eliminada_o_apartada(campo, valor):
    bloques = [bloque([(25, cabecera())]), bloque([(26, resumen())])]
    candidato = bloques[0]["procesadas"][0][1]
    setattr(candidato.facturas[0], campo, valor)
    assert unir_ultimo_bloque(bloques) is False
    assert bloques[0]["procesadas"][0][1] is candidato
    assert getattr(candidato.facturas[0], campo) == valor


@pytest.mark.parametrize("id_a,id_b", [("original-prueba", "original-prueba"), ("original-prueba", ""), ("", "original-prueba")])
def test_union_conserva_identidad_inmutable_original(id_a, id_b):
    bloques = [bloque([(25, cabecera())]), bloque([(26, resumen())])]
    for bloque_, identidad in zip(bloques, (id_a, id_b)):
        for f in bloque_["procesadas"][0][1].facturas:
            f.original_id = identidad
    assert unir_ultimo_bloque(bloques) is True
    assert all(f.original_id == "original-prueba" for f in bloques[0]["procesadas"][0][1].facturas)


def test_no_une_ruta_reutilizada_para_originales_distintos():
    bloques = [bloque([(25, cabecera())]), bloque([(26, resumen())])]
    for bloque_, identidad in zip(bloques, ("original-uno", "original-dos")):
        for f in bloque_["procesadas"][0][1].facturas:
            f.original_id = identidad
    assert unir_ultimo_bloque(bloques) is False
    assert all(len(b["crudos"]) == 1 for b in bloques)


def test_tres_partes_salta_bloque_consumido_y_conserva_todas_las_paginas():
    a = bloque([(25, cabecera())])
    b = bloque([(p, dict(estado_pagina_factura="intermedia")) for p in range(26, 51)])
    c = bloque([(51, resumen())])
    for b_ in (a, b, c):
        b_["original_id"] = "original-prueba"
        for _, pr in b_["procesadas"]:
            for f in pr.facturas:
                f.original_id = "original-prueba"
    assert unir_ultimo_bloque([a, b]) is True
    assert not b["crudos"] and not b["procesadas"]
    assert unir_ultimo_bloque([a, b, c]) is True
    assert not c["crudos"] and not c["procesadas"]
    assert [r[2] for r in a["crudos"]] == list(range(25, 52))
    assert a["procesadas"][0][1].facturas[0].ultima_pagina_origen == 51


@pytest.mark.parametrize("cambio", [dict(nif="B12345674"), dict(original_id="otro-original"), dict(original="otro.pdf")])
def test_no_salta_bloque_consumido_de_cliente_u_original_distinto(cambio):
    a = bloque([(25, cabecera())])
    b = bloque([(26, dict(estado_pagina_factura="intermedia"))])
    c = bloque([(27, resumen())])
    for b_ in (a, b, c):
        b_.update(original_id="original-prueba", original="lote.pdf")
    assert unir_ultimo_bloque([a, b]) is True
    b.update(cambio)
    assert unir_ultimo_bloque([a, b, c]) is False


def test_no_salta_bloque_vacio_no_consumido_por_union():
    a = bloque([(25, cabecera())])
    vacio = bloque([])
    c = bloque([(26, resumen())])
    assert unir_ultimo_bloque([a, vacio, c]) is False
