"""Control de hojas ausentes sin falsos avisos en series de ingresos."""

from facturas_excel.modelo import Factura
from facturas_excel.validacion import huecos_de_numeracion


def factura(numero, nombre, nif, lineas=1):
    return Factura(num_factura=numero, nombre=nombre, nif=nif,
                   lineas_factura=lineas)


def test_los_ingresos_se_comprueban_por_emisor_no_por_cada_comprador():
    facturas, tipos = [], []
    for numero in range(350, 360):
        comprador = "COMPRADOR A SL" if numero % 2 else "COMPRADOR B SL"
        nif = "B12345674" if numero % 2 else "A58818501"
        # Algunas facturas tienen dos tipos de IVA y, por tanto, dos filas.
        repeticiones = 2 if numero in (354, 355, 357) else 1
        for _ in range(repeticiones):
            facturas.append(factura(f"FAC00{numero}", comprador, nif,
                                    repeticiones))
            tipos.append("venta")

    assert huecos_de_numeracion(
        facturas, tipos, "CLIENTE EMISOR DE EJEMPLO") == []


def test_un_hueco_real_en_la_serie_global_de_ingresos_si_se_avisa():
    numeros = (350, 351, 352, 354, 355)
    facturas = [factura(f"FAC00{n}", f"COMPRADOR {n}", "B12345674")
                for n in numeros]

    avisos = huecos_de_numeracion(
        facturas, ["venta"] * len(facturas), "CLIENTE EMISOR")

    assert len(avisos) == 1
    assert "FAC00353" in avisos[0]
    assert "CLIENTE EMISOR" in avisos[0]


def test_las_lineas_de_iva_repetidas_cuentan_como_una_factura():
    # Solo hay dos facturas: aunque cada una tenga dos lineas, no alcanza las
    # tres facturas necesarias para afirmar que existe una serie.
    facturas = [
        factura("FAC001", "COMPRADOR A", "B12345674", 2),
        factura("FAC001", "COMPRADOR A", "B12345674", 2),
        factura("FAC003", "COMPRADOR B", "A58818501", 2),
        factura("FAC003", "COMPRADOR B", "A58818501", 2),
    ]

    assert huecos_de_numeracion(facturas, ["venta"] * 4, "EMISOR") == []


def test_en_gastos_cada_proveedor_conserva_su_propia_serie():
    facturas = [
        *(factura(f"A-{n}", "PROVEEDOR A", "B12345674") for n in (1, 2, 3)),
        *(factura(f"A-{n}", "PROVEEDOR B", "A58818501") for n in (10, 11, 12)),
    ]

    assert huecos_de_numeracion(facturas, ["gasto"] * len(facturas)) == []
