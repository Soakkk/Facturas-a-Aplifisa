"""Facturas cuya cabecera y resumen fiscal estan en hojas distintas."""

from facturas_excel.procesar import consolidar_paginas_factura, preparar_lote


CLIENTE = ("CLIENTE DE EJEMPLO", "12345678Z")
DESTINATARIO = ("COMPRADOR DE EJEMPLO SL", "B12345674")


def cabecera(numero="F-100"):
    return {
        "emisor_nombre": CLIENTE[0], "emisor_nif": CLIENTE[1],
        "receptor_nombre": DESTINATARIO[0], "receptor_nif": DESTINATARIO[1],
        "num_factura": numero, "fecha": "01/04/2026",
        "lineas_iva": [{}], "total": None,
        "cuenta_ingreso": "700", "subclave_ingreso": "I01",
        "concepto_texto": "venta de mercancias", "confianza": "alta",
    }


def resumen(numero="F-100"):
    return {
        "emisor_nombre": CLIENTE[0], "emisor_nif": CLIENTE[1],
        "receptor_nombre": None, "receptor_nif": None,
        "num_factura": numero, "fecha": "01/04/2026",
        "lineas_iva": [
            {"base": 1009.73, "tipo_iva": 4, "cuota_iva": 40.39,
             "pct_requiv": None, "cuota_requiv": None},
            {"base": 74.37, "tipo_iva": 10, "cuota_iva": 7.44,
             "pct_requiv": None, "cuota_requiv": None},
        ],
        "total": 1131.93, "confianza": "media",
    }


def test_cabecera_y_resumen_en_dos_hojas_forman_un_solo_apunte():
    registros = [
        (b"cabecera", "taco.pdf", 5, cabecera()),
        (b"resumen", "taco.pdf", 6, resumen()),
    ]

    procesadas = preparar_lote(registros, CLIENTE[0], CLIENTE[1])

    assert len(procesadas) == 1
    imagen, pr = procesadas[0]
    assert imagen == b"cabecera" and pr.pagina == 5
    assert pr.tipo == "venta" and len(pr.facturas) == 2
    assert pr.facturas[0].nombre == DESTINATARIO[0]
    assert pr.facturas[0].nif == DESTINATARIO[1]
    assert [f.base_iva for f in pr.facturas] == [1009.73, 74.37]
    assert [f.pct_iva for f in pr.facturas] == [4.0, 10.0]
    assert all(f.total_impreso == 1131.93 for f in pr.facturas)
    assert all(f.confianza_ia == "media" for f in pr.facturas)


def test_dos_copias_completas_no_se_ocultan_como_multipagina():
    completa = resumen()
    completa.update({
        "receptor_nombre": DESTINATARIO[0],
        "receptor_nif": DESTINATARIO[1],
    })
    registros = [
        (b"uno", "taco.pdf", 1, completa),
        (b"dos", "taco.pdf", 2, completa),
    ]

    assert len(consolidar_paginas_factura(registros)) == 2


def test_mismo_numero_en_documentos_distintos_no_se_mezcla():
    registros = [
        (b"uno", "enero.pdf", 1, cabecera()),
        (b"dos", "febrero.pdf", 2, resumen()),
    ]

    assert len(consolidar_paginas_factura(registros)) == 2


def test_una_linea_fiscal_repetida_en_dos_hojas_no_se_duplica():
    primera = cabecera()
    primera["lineas_iva"] = [resumen()["lineas_iva"][0]]
    unidos = consolidar_paginas_factura([
        (b"uno", "taco.pdf", 1, primera),
        (b"dos", "taco.pdf", 2, resumen()),
    ])

    assert len(unidos) == 1
    assert len(unidos[0][3]["lineas_iva"]) == 2
