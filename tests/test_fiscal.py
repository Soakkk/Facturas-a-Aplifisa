"""1.24: lo que dice la ley de cada factura (datos de prueba, no reales)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from facturas_excel import fiscal
from facturas_excel.modelo import Factura
from facturas_excel.procesar import construir

CLIENTE = "12345678Z"
PROVEEDOR = "B12345674"


def _f(**extra):
    datos = dict(num_factura="F-1", fecha="03/09/2026", nombre="PROVEEDOR SL",
                 nif=PROVEEDOR, concepto="629", subclave="G22", base_iva=100.0,
                 pct_iva=21.0, cuota_iva=21.0, total_impreso=121.0)
    datos.update(extra)
    return Factura(**datos)


def _textos(f, tipo="gasto"):
    return " | ".join(t for t, _c, _g in fiscal.avisos(f, tipo))


def _datos(**extra):
    d = dict(emisor_nombre="PROVEEDOR SL", emisor_nif=PROVEEDOR,
             receptor_nombre="CLIENTE DE PRUEBA", receptor_nif=CLIENTE,
             num_factura="F-1", fecha="03/09/2026",
             lineas_iva=[{"base": 100.0, "tipo_iva": 21.0, "cuota_iva": 21.0}],
             total=121.0, cuenta_gasto="629", subclave_gxx="G22")
    d.update(extra)
    return d


# ------------------------------------------------------------- la lectura
def test_gemini_dice_que_documento_es_su_moneda_y_su_mencion_de_iva():
    from facturas_excel.extraccion import ESQUEMA
    for campo in ("tipo_documento", "moneda", "mencion_iva",
                  "posible_no_deducible"):
        assert campo in ESQUEMA["properties"] and campo in ESQUEMA["required"]

    [f] = construir(_datos(tipo_documento="proforma", moneda="usd",
                           mencion_iva="inversion_sujeto_pasivo",
                           posible_no_deducible="restauracion"),
                    CLIENTE, "CLIENTE DE PRUEBA").facturas
    assert (f.tipo_documento, f.moneda, f.mencion_iva, f.posible_no_deducible) \
        == ("proforma", "USD", "inversion_sujeto_pasivo", "restauracion")
    # Lo que no dice nada no se guarda.
    [g] = construir(_datos(tipo_documento="factura", mencion_iva="ninguna",
                           posible_no_deducible="no"),
                    CLIENTE, "CLIENTE DE PRUEBA").facturas
    assert (g.tipo_documento, g.mencion_iva, g.posible_no_deducible) \
        == (None, None, None)


def test_un_tique_sin_el_nif_del_cliente_se_sabe():
    [tique] = construir(_datos(receptor_nif=None, receptor_nombre=None),
                        CLIENTE, "CLIENTE DE PRUEBA").facturas
    assert tique.sin_nif_destinatario
    [completa] = construir(_datos(), CLIENTE, "CLIENTE DE PRUEBA").facturas
    assert not completa.sin_nif_destinatario
    # Una venta no: el NIF que falta sería el del comprador.
    [venta] = construir(_datos(emisor_nif=CLIENTE, emisor_nombre="CLIENTE DE "
                               "PRUEBA", receptor_nif=None, receptor_nombre="X"),
                        CLIENTE, "CLIENTE DE PRUEBA").facturas
    assert not venta.sin_nif_destinatario


# ------------------------------------------------------------- los avisos
def test_lo_que_no_es_una_factura_se_avisa():
    assert "PROFORMA" in _textos(_f(tipo_documento="proforma"))
    assert "ALBARÁN" in _textos(_f(tipo_documento="albaran"))
    assert "copia" in _textos(_f(tipo_documento="copia"))
    assert _textos(_f(tipo_documento="factura_simplificada")) == ""
    # Ámbar, no rojo: una lectura mala no puede dejarla sin salida.
    assert all(g == "revisar" for _t, _c, g in fiscal.avisos(
        _f(tipo_documento="proforma"), "gasto"))


def test_otra_moneda_se_pasa_a_euros():
    assert "USD" in _textos(_f(moneda="USD"))
    assert "art. 79" in _textos(_f(moneda="USD"))
    assert _textos(_f(moneda="EUR")) == _textos(_f(moneda=None)) == ""


def test_inversion_del_sujeto_pasivo_e_intracomunitarias():
    isp = _f(pct_iva=0.0, cuota_iva=0.0, mencion_iva="inversion_sujeto_pasivo")
    assert "84.Uno.2º" in _textos(isp, "gasto")
    assert "repercute y se lo deduce" in _textos(isp, "gasto")
    assert "lo declara el comprador" in _textos(isp, "venta")
    intra = _f(pct_iva=0.0, cuota_iva=0.0, mencion_iva="intracomunitaria")
    assert "349" in _textos(intra, "gasto") and "art. 25" in _textos(intra, "venta")
    assert "DUA" in _textos(_f(mencion_iva="exportacion"), "gasto")
    # Exenta o no sujeta (un seguro): nada que avisar.
    assert _textos(_f(pct_iva=0.0, cuota_iva=0.0, mencion_iva="exenta")) == ""


def test_iva_que_puede_no_deducirse_solo_en_gastos():
    restaurante = _f(posible_no_deducible="restauracion")
    assert "art. 96" in _textos(restaurante, "gasto")
    assert "Por el total" in _textos(restaurante, "gasto")
    # El restaurante que FACTURA (una venta del cliente) no.
    assert _textos(restaurante, "venta") == ""
    tique = _f(sin_nif_destinatario=True)
    assert "art. 97" in _textos(tique, "gasto")
    # Ya por el total, o sin cuota de IVA, no hay nada que decidir.
    assert _textos(_f(posible_no_deducible="regalo", no_deducible=True)) == ""
    assert _textos(_f(posible_no_deducible="regalo",
                      iva_incluido_en_base=True)) == ""
    assert _textos(_f(sin_nif_destinatario=True, pct_iva=0.0,
                      cuota_iva=0.0)) == ""


# ---------------------------------------------- en la ventana: por el total
def _ventana(monkeypatch, tmp_path, lista, regimen="", cliente=CLIENTE):
    from PySide6.QtWidgets import QApplication

    from facturas_excel import clientes
    from facturas_excel.app import VentanaPrincipal
    from facturas_excel.dialogo_cliente import DialogoCliente
    from facturas_excel.dialogo_recargo import DialogoRecargo
    from facturas_excel.procesar import preparar_lote

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(clientes, "dir_datos", lambda: str(tmp_path))
    monkeypatch.setattr(DialogoRecargo, "exec", lambda self: 0)
    monkeypatch.setattr(DialogoCliente, "exec", lambda self: 0)
    if regimen:
        clientes.guardar_regimen_recargo(cliente, regimen, "CLIENTE")
    crudos = [(b"", "taco.pdf", i + 1, d) for i, d in enumerate(lista)]
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._rutas_actuales = ["taco.pdf"]
    v._on_terminado(preparar_lote(crudos, "CLIENTE DE PRUEBA", cliente),
                    "CLIENTE DE PRUEBA", cliente, crudos)
    return v


def _bases(v):
    from facturas_excel.app import C_BASE, C_PCT
    return [(v.tabla.item(r, C_BASE).text(), v.tabla.item(r, C_PCT).text())
            for r in range(v.tabla.rowCount())]


def test_por_el_total_una_factura_cuyo_iva_no_se_deduce(monkeypatch, tmp_path):
    v = _ventana(monkeypatch, tmp_path, [
        _datos(num_factura="R-1", posible_no_deducible="restauracion"),
        _datos(num_factura="T-1")])
    restaurante = next(r for r in range(v.tabla.rowCount())
                       if v.filas[r].factura.num_factura == "R-1")
    assert "art. 96" in " ".join(str(m) for m in v.filas[restaurante]["mensajes"])

    v.tabla.selectRow(restaurante)
    v._alternar_por_el_total()

    assert sorted(_bases(v)) == [("100,00", "21,00"), ("121,00", "")]
    r = next(r for r in range(v.tabla.rowCount())
             if v.filas[r].factura.num_factura == "R-1")
    assert not any("art. 96" in str(m) for m in v.filas[r]["mensajes"])
    # Pulsar otra vez lo deshace.
    v.tabla.selectRow(r)
    v._alternar_por_el_total()
    assert sorted(_bases(v)) == [("100,00", "21,00"), ("100,00", "21,00")]


def test_por_el_total_conserva_la_retencion_y_no_toca_las_ventas(
        monkeypatch, tmp_path):
    from facturas_excel.app import C_CUOTA_IRPF
    v = _ventana(monkeypatch, tmp_path, [
        _datos(num_factura="A-1", base_irpf=100.0, pct_irpf=19.0,
               cuota_irpf=19.0, total=102.0),
        _datos(num_factura="V-1", emisor_nif=CLIENTE,
               emisor_nombre="CLIENTE DE PRUEBA", receptor_nif=PROVEEDOR,
               receptor_nombre="COMPRADOR SL", cuenta_ingreso="705",
               subclave_ingreso="I01")])
    v.tabla.selectAll()
    v._alternar_por_el_total()
    por_numero = {v.filas[r].factura.num_factura: r
                  for r in range(v.tabla.rowCount())}
    from facturas_excel.app import C_BASE
    assert v.tabla.item(por_numero["A-1"], C_BASE).text() == "121,00"
    assert v.tabla.item(por_numero["A-1"], C_CUOTA_IRPF).text() == "19,00"
    assert v.tabla.item(por_numero["V-1"], C_BASE).text() == "100,00"


def test_cliente_sin_derecho_a_deducir_todas_sus_compras_por_el_total(
        monkeypatch, tmp_path):
    """Actividad exenta (art. 20): no deduce el IVA de sus compras (art. 94).
    Una sociedad sí puede (una clínica S.L.)."""
    from facturas_excel.clientes import EXENTO
    v = _ventana(monkeypatch, tmp_path, [
        _datos(receptor_nif="B76543214", receptor_nombre="CLINICA SL")],
        EXENTO, cliente="B76543214")
    assert v._por_el_total()
    assert not v.fila_recargo.isHidden()
    assert v.lbl_hay_recargo.text() == "Cliente sin derecho a deducir"
    assert _bases(v) == [("121,00", "")]
    assert "sin derecho a deducir" in v.lbl_resumen_titulo.text()


def test_el_regimen_exento_se_elige_desde_el_menu(monkeypatch, tmp_path):
    from facturas_excel import clientes
    from facturas_excel.dialogo_recargo import DialogoRecargo
    v = _ventana(monkeypatch, tmp_path, [_datos()])
    assert _bases(v) == [("100,00", "21,00")]
    monkeypatch.setattr(DialogoRecargo, "exec", lambda self: 1)
    monkeypatch.setattr(DialogoRecargo, "elegido", lambda self: clientes.EXENTO)
    v._elegir_regimen_recargo()
    assert clientes.regimen_recargo(CLIENTE) == clientes.EXENTO
    assert _bases(v) == [("121,00", "")]


# ------------------------------------------ tipos según la fecha (art. 91)
def _validar(**extra):
    from facturas_excel.validacion import validar
    return " | ".join(str(m) for m in validar(_f(**extra)).mensajes)


def test_los_tipos_temporales_solo_valen_en_su_epoca():
    luz_2023 = _validar(fecha="15/03/2023", pct_iva=5.0, cuota_iva=5.0,
                        total_impreso=105.0)
    assert "solo se aplicó" not in luz_2023
    hoy = _validar(fecha="15/03/2026", pct_iva=5.0, cuota_iva=5.0,
                   total_impreso=105.0)
    assert "IVA del 5% solo se aplicó entre julio de 2022 y septiembre de " \
        "2024" in hoy
    assert "solo se aplicó" in _validar(fecha="15/03/2025", pct_iva=2.0,
                                        cuota_iva=2.0, total_impreso=102.0)
    assert "solo se aplicó" not in _validar(fecha="15/11/2024", pct_iva=7.5,
                                            cuota_iva=7.5, total_impreso=107.5)


def test_recargos_de_los_tipos_temporales():
    for tipo, recargo in ((2.0, 0.26), (7.5, 1.0)):
        texto = _validar(fecha="15/11/2024", pct_iva=tipo, cuota_iva=tipo,
                         base_requiv=100.0, pct_requiv=recargo,
                         cuota_requiv=recargo,
                         total_impreso=round(100 + tipo + recargo, 2))
        assert "recargo del" not in texto, (tipo, texto)


def test_retenciones_que_no_existen_y_bases_distintas():
    malo = _validar(base_irpf=100.0, pct_irpf=1.5, cuota_irpf=1.5,
                    total_impreso=119.5)
    assert "Retención del 1,5%" in malo
    for tipo in (1.0, 7.0, 15.0, 19.0, 24.0):
        cuota = tipo
        assert "Retención del" not in _validar(
            base_irpf=100.0, pct_irpf=tipo, cuota_irpf=cuota,
            total_impreso=round(121 - cuota, 2)), tipo
    otra_base = _validar(base_irpf=80.0, pct_irpf=15.0, cuota_irpf=12.0,
                         total_impreso=109.0)
    assert "La base de la retención (80.0) no es la base imponible" in otra_base


# ------------------------------------------ rectificativas y numeración
def test_una_rectificativa_en_positivo_se_avisa():
    assert "van en negativo" in _textos(_f(tipo_documento="rectificativa"))
    assert _textos(_f(tipo_documento="rectificativa", base_iva=-100.0,
                      cuota_iva=-21.0, total_impreso=-121.0)) == ""


def test_rectificativa_cuya_original_no_esta_en_el_lote(monkeypatch, tmp_path):
    """Antes salía en verde: un abono en positivo suma el gasto en vez de
    restarlo. Se busca la original en el registro."""
    from facturas_excel import historial
    v = _ventana(monkeypatch, tmp_path, [
        _datos(num_factura="AB-7", sustituye_a="F-100",
               tipo_documento="rectificativa")])
    texto = " ".join(str(m) for m in v.filas[0]["mensajes"])
    assert "Rectifica a la factura F-100" in texto
    assert "no consta en el registro" in texto
    assert "van en negativo" in texto

    historial.registrar(CLIENTE, {"gasto": [_f(num_factura="F-100",
                                                fecha="01/08/2026")]}, {})
    v._revalidar_todo()
    texto = " ".join(str(m) for m in v.filas[0]["mensajes"])
    assert "la original consta como exportada el" in texto


def test_falta_la_primera_venta_del_trimestre():
    """Los huecos se miraban solo dentro del lote: si faltaba la primera
    venta del trimestre (o la última del anterior), no se veía."""
    from facturas_excel.validacion import huecos_de_numeracion
    ventas = [_f(num_factura=f"V-{n}", nif=PROVEEDOR) for n in (43, 44, 45, 46)]
    tipos = ["venta"] * len(ventas)
    assert huecos_de_numeracion(ventas, tipos, "CLIENTE") == []
    avisos = huecos_de_numeracion(ventas, tipos, "CLIENTE",
                                  ventas_anteriores=["V-40", "V-41", "X-9"])
    assert len(avisos) == 1 and "FALTA la factura V-42" in avisos[0]
    # Con la serie seguida no falta nada.
    assert huecos_de_numeracion(ventas, tipos, "CLIENTE",
                                ventas_anteriores=["V-41", "V-42"]) == []
    # Otra serie (otro año) no cuenta.
    serie = [_f(num_factura=f"2026-{n:03d}") for n in (5, 6, 7)]
    assert huecos_de_numeracion(serie, ["venta"] * 3, "CLIENTE",
                                ventas_anteriores=["2025-001"]) == []


# ------------------------------------- lo que encontró la revisión de la 1.24
def _fila(v, numero):
    return next(r for r in range(v.tabla.rowCount())
                if v.filas[r].factura.num_factura == numero)


def _msgs(v, r):
    return " ".join(str(m) for m in v.filas[r]["mensajes"])


def test_un_recibo_no_dice_que_no_se_registra():
    """La prima del seguro, la cuota de comunidad o del colegio llegan como
    recibo y se registran así."""
    seguro = _f(tipo_documento="recibo", pct_iva=0.0, cuota_iva=0.0,
                concepto="625", subclave="G20", total_impreso=100.0)
    assert _textos(seguro) == ""


def test_la_mercancia_de_un_bar_o_una_joyeria_no_se_avisa():
    bebidas = _f(posible_no_deducible="alimentos_tabaco", concepto="600",
                 subclave="G01")
    assert _textos(bebidas) == ""
    joyas = _f(posible_no_deducible="joyas", concepto="600", subclave="G01")
    assert _textos(joyas) == ""
    # El consumo propio sí (una comida, un regalo: no son mercancía).
    assert "art. 96" in _textos(_f(posible_no_deducible="alimentos_tabaco"))
    assert "art. 96" in _textos(_f(posible_no_deducible="restauracion",
                                   concepto="600", subclave="G01"))


def test_la_copia_de_una_venta_propia_no_se_avisa():
    assert _textos(_f(tipo_documento="copia"), "venta") == ""
    assert "copia" in _textos(_f(tipo_documento="copia"), "gasto")


def test_la_moneda_euro_escrita_de_otra_forma_es_euros():
    for moneda in ("EURO", "Euros", "eur", "€"):
        assert _textos(_f(moneda=moneda)) == "", moneda


def test_isp_de_un_cliente_que_no_deduce_va_al_309():
    isp = _f(pct_iva=0.0, cuota_iva=0.0, mencion_iva="inversion_sujeto_pasivo")
    texto = " | ".join(t for t, _c, _g in fiscal.avisos(isp, "gasto",
                                                         sin_deducir=True))
    assert "309" in texto and "se lo deduce" not in texto
    venta = _textos(_f(mencion_iva="intracomunitaria"), "venta")
    assert "VIES" in venta and "ROI" not in venta and "art. 69" in venta


def test_una_post_facturacion_no_pide_registrar_la_original(
        monkeypatch, tmp_path):
    """«Sustituye al doc.n»: la original NO se registra (si se registran las
    dos, se deduce dos veces)."""
    from facturas_excel import historial
    v = _ventana(monkeypatch, tmp_path, [
        _datos(num_factura="9001", sustituye_a="4532023141")])
    texto = _msgs(v, 0)
    assert "Sustituye a la factura 4532023141" in texto
    assert "la original no se registra" in texto
    assert "compruebe que está registrada" not in texto
    historial.registrar(CLIENTE, {"gasto": [_f(num_factura="4532023141",
                                                fecha="01/08/2026")]}, {})
    v._revalidar_todo()
    assert "anúlela en Aplifisa" in _msgs(v, 0)


def test_huecos_con_una_venta_anterior_lejana_o_ya_exportada():
    from facturas_excel.validacion import huecos_de_numeracion
    lote = [_f(num_factura=f"V-{n}") for n in (50, 51, 52, 54, 55)]
    tipos = ["venta"] * len(lote)
    # La anterior muy lejos no tapa el hueco del lote.
    avisos = huecos_de_numeracion(lote, tipos, "C", ventas_anteriores=["V-10"])
    assert len(avisos) == 1 and "V-53" in avisos[0]
    # Si la 53 ya se exportó en otro lote, no falta.
    assert huecos_de_numeracion(lote, tipos, "C",
                                ventas_anteriores=["V-49", "V-53"]) == []


def test_la_revision_y_la_correccion_del_resumen_no_se_pierden(
        monkeypatch, tmp_path):
    v = _ventana(monkeypatch, tmp_path, [
        # Confianza media: queda en ámbar también por el total.
        _datos(num_factura="R-1", posible_no_deducible="restauracion",
               confianza="media"),
        _datos(num_factura="R-2", posible_no_deducible="restauracion")])
    v.tabla.clearSelection()
    v.tabla.selectRow(_fila(v, "R-1"))
    v._alternar_por_el_total()
    v._marcar_revisada(filas=[_fila(v, "R-1")])
    revisada = v.filas[_fila(v, "R-1")].factura
    assert revisada.revision_confirmada
    # Pulsar «Por el total» en otra no le quita la revisión a la primera.
    v.tabla.clearSelection()
    v.tabla.selectRow(_fila(v, "R-2"))
    v._alternar_por_el_total()
    assert v.filas[_fila(v, "R-1")].factura is revisada

    # Una corrección en la línea resumen sobrevive a quitar y volver a poner.
    r2 = _fila(v, "R-2")
    resumen = v.filas[r2].factura
    resumen.base_iva, resumen.edicion_manual = 130.0, True
    for _ in range(2):
        v.tabla.clearSelection()
        v.tabla.selectRow(_fila(v, "R-2"))
        v._alternar_por_el_total()
    assert v.filas[_fila(v, "R-2")].factura.base_iva == 130.0


def test_la_mencion_de_la_ultima_hoja_no_se_pierde_al_unir():
    from facturas_excel.procesar import _fusionar_datos_paginas
    primera = _datos(tipo_documento="factura", mencion_iva="ninguna",
                     moneda="EUR", posible_no_deducible="no")
    ultima = {"mencion_iva": "inversion_sujeto_pasivo", "moneda": "EUR",
              "tipo_documento": "factura", "posible_no_deducible": "no"}
    assert _fusionar_datos_paginas(primera, ultima)["mencion_iva"] \
        == "inversion_sujeto_pasivo"


def test_el_tipo_temporal_se_mira_en_el_devengo():
    # Entregas de diciembre de 2024 al 2 %, facturadas en enero de 2025.
    assert "solo se aplicó" not in _validar(
        fecha="03/01/2025", fecha_operacion="20/12/2024", pct_iva=2.0,
        cuota_iva=2.0, total_impreso=102.0)
    # El 5 % de octubre de 2024 ya no existía (pasó al 7,5 %).
    assert "solo se aplicó" in _validar(fecha="15/10/2024", pct_iva=5.0,
                                        cuota_iva=5.0, total_impreso=105.0)
