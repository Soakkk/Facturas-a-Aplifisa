"""Trabajo por bloques: varios PDF escaneados en un solo Excel.

Un requerimiento son muchas facturas y el escaner saca PDF de 25-30 hojas, asi
que cada carga se suma al lote en vez de sustituirlo.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from facturas_excel.app import (
    C_BLOQUE, ICONO_ESTADO, TODOS_LOS_BLOQUES, VentanaPrincipal,
)
from facturas_excel.modelo import Factura
from facturas_excel.procesar import FacturaProcesada
from facturas_excel.resumen import resumir_por_bloque
from facturas_excel.validacion import ERROR

_app = QApplication.instance() or QApplication([])


def factura(num="F-1", base=100.0, pct=21.0):
    return Factura(num_factura=num, fecha="16/07/2026", nombre="PROVEEDOR SL",
                   nif="B30048276", concepto="600", base_iva=base, pct_iva=pct,
                   cuota_iva=round(base * pct / 100, 2),
                   total_impreso=round(base * (1 + pct / 100), 2))


def procesada(f):
    return FacturaProcesada(tipo="gasto", facturas=[f], cuenta="600", gxx=None,
                            origen="escaneo.pdf", pagina=1)


def cargar_bloque(v, ruta, facturas, nif="12345678Z", cliente="CLIENTE UNO"):
    v._rutas_actuales = [ruta]
    v._on_terminado([(b"", procesada(f)) for f in facturas], cliente, nif)


def test_el_segundo_pdf_se_suma_al_lote_y_no_lo_sustituye():
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\escaneo1.pdf", [factura("F-1"), factura("F-2", 50)])
    cargar_bloque(v, r"C:\tmp\escaneo2.pdf", [factura("F-3", 70)])

    assert v.tabla.rowCount() == 3
    assert [b["nombre"] for b in v._bloques] == ["escaneo1", "escaneo2"]
    assert v.tabla.item(0, C_BLOQUE).text() == "escaneo1"
    assert v.tabla.item(2, C_BLOQUE).text() == "escaneo2"


def test_la_misma_factura_en_dos_bloques_se_marca_duplicada():
    # Al escanear en tacos es facil colar una hoja dos veces: si se importa,
    # el gasto se registra (y se paga) dos veces.
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\escaneo1.pdf", [factura("F-1")])
    cargar_bloque(v, r"C:\tmp\escaneo2.pdf", [factura("F-1")])

    assert v._duplicados == {1: 0}
    assert v.tabla.item(1, 0).text() == ICONO_ESTADO[ERROR]
    assert not v.alerta.isHidden()   # el banner rojo, con la ventana sin mostrar


def test_filtrar_por_bloque_esconde_los_demas():
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\escaneo1.pdf", [factura("F-1")])
    cargar_bloque(v, r"C:\tmp\escaneo2.pdf", [factura("F-2", 50)])

    v.combo_filtro_bloque.setCurrentText("escaneo2")
    assert v.tabla.isRowHidden(0) and not v.tabla.isRowHidden(1)
    v.combo_filtro_bloque.setCurrentText(TODOS_LOS_BLOQUES)
    assert not v.tabla.isRowHidden(0) and not v.tabla.isRowHidden(1)


def test_dos_pdf_con_el_mismo_nombre_no_se_pisan():
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\enero\escaneo.pdf", [factura("F-1")])
    cargar_bloque(v, r"C:\febrero\escaneo.pdf", [factura("F-2", 50)])
    assert [b["nombre"] for b in v._bloques] == ["escaneo", "escaneo (2)"]


def test_quitar_un_bloque_deja_intacto_el_otro(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\escaneo1.pdf", [factura("F-1")])
    cargar_bloque(v, r"C:\tmp\escaneo2.pdf", [factura("F-2", 50)])

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    v.combo_filtro_bloque.setCurrentText("escaneo1")
    v._quitar_bloque()

    assert [b["nombre"] for b in v._bloques] == ["escaneo2"]
    assert v.tabla.rowCount() == 1
    assert v.tabla.item(0, C_BLOQUE).text() == "escaneo2"


def test_vaciar_todo_deja_el_lote_a_cero(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\escaneo1.pdf", [factura("F-1")])
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    v._vaciar_todo()

    assert v._bloques == [] and v.tabla.rowCount() == 0
    assert not v.btn_gastos.isEnabled()


def test_avisa_si_el_segundo_bloque_es_de_otro_cliente(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: avisos.append(a[2])))
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\uno.pdf", [factura("F-1")], nif="12345678Z")
    cargar_bloque(v, r"C:\tmp\dos.pdf", [factura("F-2", 50)], nif="11111111H",
                  cliente="CLIENTE DOS")

    assert avisos and "otro cliente" in avisos[0].lower()
    assert "VARIOS CLIENTES" in v.lbl_cliente.text()


def test_el_resumen_cuadra_bloque_a_bloque():
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\escaneo1.pdf", [factura("F-1"), factura("F-2", 50)])
    cargar_bloque(v, r"C:\tmp\escaneo2.pdf", [factura("F-3", 70)])

    # Una linea por bloque + el total general (hay mas de un bloque).
    assert v.tabla_resumen.rowCount() == 3
    assert v.tabla_resumen.item(0, 0).text() == "escaneo1"
    assert v.tabla_resumen.item(0, 2).text() == "2"
    assert v.tabla_resumen.item(0, 8).text() == "181,50 €"   # 150 + 31,50
    assert v.tabla_resumen.item(1, 8).text() == "84,70 €"    # 70 + 14,70
    assert v.tabla_resumen.item(2, 0).text() == "TODOS LOS BLOQUES"
    assert v.tabla_resumen.item(2, 8).text() == "266,20 €"


def test_la_celda_iva_desglosa_varios_porcentajes_sin_anadir_columnas():
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\mixto.pdf",
                  [factura("F-1", 100, 10), factura("F-2", 200, 21)])

    assert v.tabla_resumen.columnCount() == 9
    assert v.tabla_resumen.item(0, 4).text() == (
        "10%: 10,00 € · 21%: 42,00 €")


def test_la_celda_iva_muestra_el_porcentaje_aunque_solo_haya_un_tipo():
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\un_tipo.pdf", [factura("F-1", 100, 21)])

    assert v.tabla_resumen.item(0, 4).text() == "21%: 21,00 €"


def test_el_resumen_muestra_los_suplidos_sin_mezclarlos_con_la_base():
    v = VentanaPrincipal(comprobar_updates=False)
    f = factura("F-1", 100, 21)
    f.suplidos = 109.08
    f.total_impreso = 230.08
    cargar_bloque(v, r"C:\tmp\suplidos.pdf", [f])

    assert v.tabla_resumen.item(0, 3).text() == "100,00 €"
    assert v.tabla_resumen.item(0, 7).text() == "109,08 €"
    assert v.tabla_resumen.item(0, 8).text() == "230,08 €"


def test_resumir_por_bloque_agrupa_y_redondea():
    totales = resumir_por_bloque([
        ("uno", factura("F-1", 53.02)),
        ("uno", factura("F-2", 200.0)),
        ("dos", factura("F-3", 100.0)),
    ])
    assert list(totales) == ["uno", "dos"]
    assert totales["uno"].lineas == 2
    assert totales["uno"].base == 253.02
    assert totales["dos"].base == 100.0


def test_una_hoja_pegada_en_el_alimentador_se_caza_por_la_numeracion():
    # Caso real: 13 hojas en el alimentador, 11 paginas escaneadas. La 09/25
    # no dio ningun error, simplemente no estaba. El salto la delata.
    v = VentanaPrincipal(comprobar_updates=False)
    facturas = [factura(f"{n:02d}/25", 100.0 + n)
                for n in (1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12)]
    cargar_bloque(v, r"C:\tmp\taco.pdf", facturas)

    assert not v.alerta.isHidden()
    assert "09/25" in v.lbl_alerta_texto.text()
    assert "FALTA" in v.lbl_alerta_texto.text()


def test_sin_saltos_no_molesta_con_avisos():
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\taco.pdf",
                  [factura(f"{n:02d}/25", 100.0 + n) for n in (1, 2, 3, 4)])
    assert v.alerta.isHidden()


def test_al_vaciar_el_lote_el_resumen_tambien_se_queda_a_cero(monkeypatch):
    # Se quedaban abajo los totales del lote anterior y parecia que "Vaciar
    # todo" no habia borrado nada.
    from PySide6.QtWidgets import QMessageBox
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\uno.pdf", [factura("F-1"), factura("F-2", 50)])
    assert v.tabla_resumen.rowCount() > 0

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    v._vaciar_todo()

    assert v.tabla.rowCount() == 0
    assert v.tabla_resumen.rowCount() == 0
    assert v.alerta.isHidden()
    assert "Cliente pendiente" in v.lbl_cliente.text()


def test_quitar_el_ultimo_bloque_tambien_limpia_el_resumen(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    v = VentanaPrincipal(comprobar_updates=False)
    cargar_bloque(v, r"C:\tmp\uno.pdf", [factura("F-1")])
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    v.combo_filtro_bloque.setCurrentText("uno")
    v._quitar_bloque()
    assert v.tabla_resumen.rowCount() == 0

