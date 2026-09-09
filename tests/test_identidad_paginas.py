"""Identidades sintéticas y continuaciones que deben quedar revisables."""
import pytest
from facturas_excel.procesar import construir, consolidar_paginas_factura, marcar_sustituidas, a_total_factura


def datos(**extra):
    d = dict(emisor_nombre="PROVEEDOR DE PRUEBA", emisor_nif="B12345674",
             receptor_nombre="CLIENTE DE EJEMPLO", receptor_nif="12345678Z",
             num_factura="F-1", fecha="01/04/2026", total=121,
             lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21)])
    d.update(extra)
    return d


def procesar(d):
    return construir(d, "12345678Z", "CLIENTE DE EJEMPLO", "lote.pdf", 1)


def unir(*hojas):
    return consolidar_paginas_factura([(b"imagen", "lote.pdf", i, d) for i, d in enumerate(hojas, 1)])


def test_nombre_cliente_no_silencia_nif_valido_distinto():
    pr = procesar(datos(receptor_nif="B12345674"))
    assert "NIF" in pr.aviso and "distinto" in pr.aviso


@pytest.mark.parametrize("cambio", [dict(emisor_nif="12345678Z"), dict(num_factura="OTRA-2")])
def test_marcadores_no_superan_identidad_contradictoria(cambio):
    primera = datos(total=None, lineas_iva=[{}], estado_pagina_factura="inicio")
    segunda = datos(estado_pagina_factura="final", **cambio)
    assert len(unir(primera, segunda)) == 2


def test_copias_completas_con_marcador_no_se_ocultan():
    assert len(unir(datos(estado_pagina_factura="inicio"), datos(estado_pagina_factura="final"))) == 2


def test_resumen_solo_importes_se_une_con_aviso_y_no_absorbe_tercera():
    primera = datos(total=None, lineas_iva=[{}], estado_pagina_factura="inicio")
    resumen = dict(total=121, lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21)], estado_pagina_factura="final")
    resultado = unir(primera, resumen, resumen)
    assert len(resultado) == 2
    crudo = resultado[0][3]
    assert crudo["_union_inferida"] is True
    assert crudo["_motivo_union_inferida"]
    assert crudo["_paginas_union_inferida"] == [1, 2]
    assert "inferida" in procesar(crudo).aviso and "1, 2" in procesar(crudo).aviso


@pytest.mark.parametrize("cambio", [dict(nif="12345678Z"), dict(fecha="02/04/2026"), dict(fecha=None)])
def test_sustitucion_no_cruza_contraparte_o_contexto_temporal(cambio):
    vieja, nueva = procesar(datos()), procesar(datos(num_factura="F-2", sustituye_a="F-1"))
    for campo, valor in cambio.items():
        setattr(vieja.facturas[0], campo, valor)
    assert marcar_sustituidas([vieja, nueva]) == 0
    assert not vieja.sustituida_por


def test_sustitucion_no_cruza_tipo():
    vieja, nueva = procesar(datos()), procesar(datos(num_factura="F-2", sustituye_a="F-1"))
    vieja.tipo = "venta"
    assert marcar_sustituidas([vieja, nueva]) == 0


def test_identificador_comun_unico_y_colapso_una_linea():
    d = datos(lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21), dict(base=10, tipo_iva=10, cuota_iva=1)], total=132)
    pr, otro = procesar(d), procesar(d)
    assert pr.facturas[0].documento_id
    assert pr.facturas[0].documento_id == pr.facturas[1].documento_id
    assert pr.facturas[0].documento_id != otro.facturas[0].documento_id
    total = a_total_factura(pr)
    assert total.facturas[0].lineas_factura == 1
    assert pr.facturas[0].lineas_factura == 2
    assert total.facturas[0].documento_id == pr.facturas[0].documento_id


def test_sustitucion_numero_reutilizado_es_ambigua():
    vieja = procesar(datos(fecha="01/04/2024"))
    repetida = procesar(datos())
    nueva = procesar(datos(num_factura="F-2", sustituye_a="F-1"))
    assert marcar_sustituidas([vieja, repetida, nueva]) == 0
    assert "ambigua" in nueva.aviso.lower()


def test_aviso_union_inferida_incluye_todas_las_paginas_de_la_cadena():
    primera = datos(total=None, lineas_iva=[{}], estado_pagina_factura="inicio")
    segunda = dict(num_factura="F-1", estado_pagina_factura="intermedia")
    ultima = dict(total=121, lineas_iva=[dict(base=100, tipo_iva=21, cuota_iva=21)], estado_pagina_factura="final")
    resultado = unir(primera, segunda, ultima)
    assert len(resultado) == 1
    assert resultado[0][3]["_paginas_union_inferida"] == [1, 2, 3]
