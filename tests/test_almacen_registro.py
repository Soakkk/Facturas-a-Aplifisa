"""La base de datos local y el registro de facturas (versión 1.17)."""

import json
import os
import threading

from facturas_excel import (
    ajustes, almacen, clientes, costes, historial, pendientes, proveedores,
    registro_facturas,
)
from facturas_excel.modelo import Factura
from facturas_excel.rutas import dir_datos


def _factura(numero, nif="B12345674", fecha="10/03/2026", base=100.0, iva=21.0):
    return Factura(num_factura=numero, fecha=fecha, nombre="PROVEEDOR PRUEBA SL",
                   nif=nif, base_iva=base, pct_iva=21.0, cuota_iva=iva,
                   total_impreso=round(base + iva, 2))


def _escribir(nombre, datos):
    ruta = os.path.join(dir_datos(), nombre)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(datos, fh)
    return ruta


def _sin_base_de_datos():
    """Como al instalar la 1.17: los JSON existen y la base de datos no."""
    for sufijo in ("", "-wal", "-shm"):
        try:
            os.remove(almacen.ruta(dir_datos()) + sufijo)
        except OSError:
            pass
    almacen._preparadas.clear()
    almacen._migradas.clear()
    registro_facturas._migrados.clear()
    registro_facturas._claves_migradas.clear()


# ------------------------------------------------------------ migración
def test_los_json_antiguos_se_copian_una_vez_y_no_se_tocan():
    _sin_base_de_datos()
    rutas = [
        _escribir("ajustes.json", {"lectura_ppp": 200, "pendientes_vistos": "1.16.0"}),
        _escribir("proveedores.json", {"PROVEEDOR PRUEBA": {
            "nif": "B12345674", "nombre": "PROVEEDOR PRUEBA SL", "manual": True}}),
        _escribir("clientes.json", {"12345678Z": {"nombre": "CLIENTE DE PRUEBA",
                                                  "regimen_recargo": "total"}}),
        _escribir("gasto.json", {"meses": {"2026-09": {"facturas": 3, "coste": 0.5,
                                                       "tokens_entrada": 1,
                                                       "tokens_salida": 1}}}),
    ]
    antes = [open(r, encoding="utf-8").read() for r in rutas]

    assert ajustes.leer("lectura_ppp") == 200
    assert pendientes.ya_visto("1.16.0")
    assert proveedores.leer("PROVEEDOR PRUEBA")["nif"] == "B12345674"
    assert clientes.regimen_recargo("12345678Z") == clientes.TOTAL
    assert "CLIENTE DE PRUEBA" in clientes.nombres_conocidos()
    assert costes.facturas_del_mes(__import__("datetime").date(2026, 9, 1)) == 3

    # Lo nuevo va a la base de datos; los JSON quedan como estaban.
    ajustes.guardar("lectura_ppp", 150)
    proveedores.guardar("OTRO", "B30048276", "OTRO SL")
    clientes.marcar_cliente("12345678Z", "CLIENTE DE PRUEBA")
    assert ajustes.leer("lectura_ppp") == 150
    assert [open(r, encoding="utf-8").read() for r in rutas] == antes
    assert os.path.exists(almacen.ruta(dir_datos()))

    # Un JSON que cambie después ya no se vuelve a copiar encima.
    _escribir("ajustes.json", {"lectura_ppp": 999})
    assert ajustes.leer("lectura_ppp") == 150


def test_sin_json_antiguo_todo_empieza_vacio():
    assert ajustes.leer("no_existe", "defecto") == "defecto"
    assert proveedores.leer_todo() == {}
    assert costes.gasto_del_mes() == 0


def test_el_gasto_de_varios_hilos_a_la_vez_no_se_pierde():
    hilos = [threading.Thread(target=costes.registrar,
                              args=("gemini-3.7-flash", 1000, 100))
             for _ in range(12)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert costes.facturas_del_mes() == 12


def test_un_proveedor_escrito_a_mano_no_lo_pisa_una_lectura():
    proveedores.guardar("CLAVE", "B12345674", "PROV", manual=True)
    assert not proveedores.guardar("CLAVE", "B99999999", "PROV")
    assert proveedores.leer("CLAVE")["nif"] == "B12345674"


# ------------------------------------------------------------ registro
def test_el_historial_antiguo_pasa_al_registro():
    _sin_base_de_datos()
    _escribir("facturas_exportadas.json", {"version": 1, "clientes": {
        "12345678Z": {"gasto|B12345674|F1|2026-03-10": {
            "exportada": "11/03/2026 09:30", "archivo": "GASTOS 2026.xlsx",
            "tipo": "gasto", "num_factura": "F-1", "nombre": "PROVEEDOR PRUEBA SL",
            "nif": "B12345674", "fecha": "10/03/2026", "total": 121.0,
            "base": 100.0, "cuota_iva": 21.0, "cuota_requiv": 0.0,
            "cuota_irpf": 0.0}}}})
    info = historial.buscar("12345678Z", _factura("F-1"), "gasto")
    assert info["exportada"] == "11/03/2026 09:30"
    assert info["archivo"] == "GASTOS 2026.xlsx"
    assert "YA EXPORTADA el 11/03/2026 09:30" in historial.texto_aviso(info)


def test_recorrido_completo_de_una_factura(tmp_path):
    f = _factura("F-7")
    nuevas = historial.registrar("12345678Z", {"gasto": [f]},
                                 {"gasto": "C:/x/GASTOS 2026.xlsx"}, "CLIENTE DE PRUEBA",
                                 leidas_en={id(f): "2026-03-11T08:00:00"})
    assert nuevas == 1
    [ficha] = registro_facturas.consultar("F-7")
    assert ficha["estado"] == registro_facturas.EXPORTADA
    assert ficha["leida_en"] == "2026-03-11T08:00:00"
    assert ficha["revisada_en"] and ficha["exportada_en"]
    assert ficha["excel"] == "GASTOS 2026.xlsx"
    assert ficha["ejercicio"] == 2026

    pdf = tmp_path / "2026-03-10 PROVEEDOR PRUEBA SL F-7.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert registro_facturas.archivar("12345678Z", "CLIENTE DE PRUEBA",
                                      [("gasto", f, str(pdf))]) == 1
    [ficha] = registro_facturas.consultar("proveedor prueba")
    assert ficha["estado"] == registro_facturas.ARCHIVADA
    assert ficha["pdf"] == str(pdf)

    # Volver a exportar no la baja de «archivada» ni cuenta como nueva.
    assert historial.registrar("12345678Z", {"gasto": [f]}, {}, "CLIENTE DE PRUEBA") == 0
    assert registro_facturas.consultar("F-7")[0]["estado"] == registro_facturas.ARCHIVADA

    # Aplifisa la rechaza: deja de estar exportada, pero conserva su PDF.
    assert historial.olvidar("12345678Z", {"gasto": [f]}) == 1
    assert historial.buscar("12345678Z", f, "gasto") is None
    [ficha] = registro_facturas.consultar("F-7")
    assert ficha["pdf"] == str(pdf) and not ficha["exportada_en"]
    assert historial.registrar("12345678Z", {"gasto": [f]}, {}, "CLIENTE DE PRUEBA") == 1


def test_varias_lineas_de_iva_son_una_sola_ficha():
    a = _factura("F-8", base=100.0, iva=21.0)
    b = _factura("F-8", base=50.0, iva=5.0)
    b.total_impreso = a.total_impreso = 176.0
    historial.registrar("12345678Z", {"gasto": [a, b]}, {})
    [ficha] = historial.del_ejercicio("12345678Z", 2026)
    assert ficha["base"] == 150.0 and ficha["cuota_iva"] == 26.0


def test_sin_numero_o_sin_fecha_no_se_apunta():
    assert historial.registrar("12345678Z", {"gasto": [_factura("")]}, {}) == 0
    assert historial.registrar("12345678Z", {"gasto": [_factura("F-1", fecha="")]}, {}) == 0
    assert registro_facturas.consultar() == []


def test_consultar_por_importe_y_por_ejercicio():
    historial.registrar("12345678Z", {"gasto": [_factura("F-1", base=200.0, iva=42.0)]}, {})
    historial.registrar("12345678Z", {"venta": [_factura("V-1", fecha="02/01/2025")]}, {})
    assert [f["num_factura"] for f in registro_facturas.consultar("242,00")] == ["F-1"]
    assert [f["num_factura"] for f in registro_facturas.consultar(ejercicio=2025)] == ["V-1"]
    assert registro_facturas.ejercicios() == [2026, 2025]


def test_exportadas_de_devuelve_todo_el_cliente_de_una_vez():
    historial.registrar("12345678Z", {"gasto": [_factura("F-1"), _factura("F-2")]}, {})
    historial.registrar("B30048276", {"gasto": [_factura("F-3")]}, {})
    ya = historial.exportadas_de("12345678Z")
    assert len(ya) == 2
    assert historial.clave(_factura("F-2"), "gasto") in ya


def test_un_documento_movido_se_sigue_encontrando(tmp_path):
    f = _factura("F-9")
    f.origen_imagen = str(tmp_path / "taco.pdf")
    historial.registrar("12345678Z", {"gasto": [f]}, {})
    registro_facturas.cambiar_ruta(str(tmp_path / "taco.pdf"),
                                   str(tmp_path / "Tacos escaneados" / "taco.pdf"))
    assert registro_facturas.consultar("F-9")[0]["origen"].endswith(
        os.path.join("Tacos escaneados", "taco.pdf"))


def test_la_ventana_del_registro_busca_y_cuenta():
    from PySide6.QtWidgets import QApplication
    from facturas_excel.dialogo_registro_facturas import DialogoRegistroFacturas
    QApplication.instance() or QApplication([])
    historial.registrar("12345678Z", {"gasto": [_factura("F-1"), _factura("F-2")]},
                        {"gasto": "GASTOS 2026.xlsx"}, "CLIENTE DE PRUEBA")
    d = DialogoRegistroFacturas()
    assert d.tabla.rowCount() == 2
    assert "2 exportada" in d.resumen.text()
    d.buscar.setText("F-2")
    d.actualizar()
    assert d.tabla.rowCount() == 1
    assert d.tabla.item(0, 5).text() == "F-2"
    assert d.tabla.item(0, 9).text() == "GASTOS 2026.xlsx"


def test_un_json_antiguo_con_forma_rara_no_rompe_nada():
    _sin_base_de_datos()
    _escribir("facturas_exportadas.json", {"clientes": {"X": ["no", "es", "dict"],
                                                        "Y": {"k": "tampoco"}}})
    _escribir("gasto.json", {"meses": ["roto"]})
    assert historial.buscar("12345678Z", _factura("F-1"), "gasto") is None
    assert costes.gasto_del_mes() == 0
    historial.registrar("12345678Z", {"gasto": [_factura("F-1")]}, {})
    assert historial.buscar("12345678Z", _factura("F-1"), "gasto")


def test_mover_un_taco_actualiza_tambien_sus_paginas(tmp_path):
    f = _factura("F-9")
    viejo = str(tmp_path / "Gastos" / "taco.pdf")
    f.origen_imagen, f.pagina_origen, f.ultima_pagina_origen = viejo, 2, 2
    historial.registrar("12345678Z", {"gasto": [f]}, {})
    nuevo = str(tmp_path / "Tacos escaneados" / "taco.pdf")
    registro_facturas.cambiar_ruta(str(tmp_path / "Gastos" / "." / "taco.pdf"), nuevo)
    [ficha] = registro_facturas.consultar("F-9")
    assert ficha["origen"] == nuevo
    assert json.loads(ficha["paginas"]) == [[nuevo, 2]]


def test_sin_iva_el_registro_no_inventa_un_cero():
    f = _factura("F-5", iva=0.0)
    f.pct_iva = f.cuota_iva = None
    historial.registrar("12345678Z", {"gasto": [f]}, {})
    assert registro_facturas.consultar("F-5")[0]["cuota_iva"] is None


# ------------------------------------------------- 1.22: facturas sin NIF
def _sin_nif(numero, nombre, base=10.0, iva=2.1, fecha="15/01/2026"):
    f = _factura(numero, nif="", fecha=fecha, base=base, iva=iva)
    f.nombre = nombre
    return f


def test_dos_tiques_sin_nif_de_dos_tiendas_son_dos_fichas():
    """Antes la clave era NIF + número + fecha: sin NIF, el tique «1» de un
    bar y el «1» de una ferretería del mismo día eran una sola ficha (en el
    mismo Excel se sumaban; en dos, la segunda pisaba a la primera)."""
    bar = _sin_nif("1", "BAR ESQUINA")
    ferreteria = _sin_nif("1", "FERRETERIA CENTRAL", base=30.0, iva=6.3)
    assert historial.registrar("12345678Z", {"gasto": [bar, ferreteria]}, {}) == 2
    assert sorted((f["nombre"], f["base"]) for f in
                  historial.del_ejercicio("12345678Z", 2026)) == \
        [("BAR ESQUINA", 10.0), ("FERRETERIA CENTRAL", 30.0)]
    historial.registrar("12345678Z", {"gasto": [_sin_nif("2", "BAR ESQUINA",
                                                         fecha="16/01/2026")]}, {})
    historial.registrar("12345678Z", {"gasto": [_sin_nif("2", "PAPELERIA SUR", 5.0, 1.05,
                                                         fecha="16/01/2026")]}, {})
    assert len(historial.del_ejercicio("12345678Z", 2026)) == 4
    # La misma escrita de otra forma sigue siendo la misma («ya exportada»).
    assert historial.buscar("12345678Z", _sin_nif("1", "Bar La Esquina, S.L."), "gasto")
    assert not historial.buscar("12345678Z", _sin_nif("1", "BAR CENTRAL"), "gasto")
    # Las líneas de IVA de una factura sin NIF siguen siendo una ficha.
    historial.registrar("12345678Z", {"gasto": [_sin_nif("9", "BAR ESQUINA", 10.0, 2.1),
                                                _sin_nif("9", "BAR ESQUINA", 5.0, 0.5)]}, {})
    assert [f["base"] for f in historial.del_ejercicio("12345678Z", 2026)
            if f["num_factura"] == "9"] == [15.0]


def test_las_fichas_sin_nif_de_antes_se_siguen_encontrando():
    """Una ficha sin NIF guardada con la clave de antes de la 1.22 pasa una
    vez a la nueva: la factura sigue saliendo como «ya exportada»."""
    f = _sin_nif("7", "BAR ESQUINA")
    historial.registrar("12345678Z", {"gasto": [f]}, {"gasto": "C:/x/G 2026.xlsx"})
    with almacen.conexion(dir_datos()) as con:
        con.execute("UPDATE facturas SET id = ? WHERE id = ?",
                    ("12345678Z#gasto||7|2026-01-15",
                     "12345678Z#gasto|~BAR-ESQUINA|7|2026-01-15"))
        con.execute("DELETE FROM migraciones WHERE coleccion = 'claves_sin_nif'")
    registro_facturas._claves_migradas.clear()
    assert historial.buscar("12345678Z", f, "gasto")["archivo"] == "G 2026.xlsx"
    assert len(historial.del_ejercicio("12345678Z", 2026)) == 1
    # Una sola vez: lo que se guarde luego con la clave vieja ya no se toca.
    with almacen.conexion(dir_datos()) as con:
        assert con.execute("SELECT origen FROM migraciones WHERE coleccion = ?",
                           ("claves_sin_nif",)).fetchone()[0] == "1 fichas"


def test_la_clave_sin_nif_es_fija():
    """La clave se guarda: si cambiara su forma, lo guardado dejaría de
    encontrarse. Estas claves no pueden cambiar nunca."""
    for nombre, esperada in (("Bar La Esquina, S.L.", "~BAR-ESQUINA"),
                             ("GASOLINERA Ñ.  PEREZ S. A.", "~GASOLINERA-N-PEREZ"),
                             ("H&M Hennes", "~HENNES-HM"), ("S.L.", ""), ("", "")):
        assert registro_facturas._quien("", nombre) == esperada, nombre
    assert registro_facturas.clave(_sin_nif("F/0012", "Bar La Esquina"), "gasto") == \
        "gasto|~BAR-ESQUINA|F0012|2026-01-15"
    assert registro_facturas.clave(_factura("F-1"), "venta") == \
        "venta|B12345674|F1|2026-03-10"
