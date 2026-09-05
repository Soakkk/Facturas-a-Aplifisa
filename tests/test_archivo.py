"""Gestion de los PDF que va generando el escaneo.

Lo importante: un escaneo puede nacer sin saber de quien es y colocarse solo
cuando el programa detecta al cliente, y nada se borra de verdad.
"""

import os
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from facturas_excel import ajustes, archivo
from facturas_excel import app as app_mod
from facturas_excel.app import C_BLOQUE, VentanaPrincipal
from facturas_excel.modelo import Factura
from facturas_excel.procesar import FacturaProcesada

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def escaneos(tmp_path, monkeypatch):
    """Carpeta de escaneos de mentira, para no tocar la del usuario."""
    carpeta = tmp_path / "escaneos"
    carpeta.mkdir()
    monkeypatch.setattr(archivo, "carpeta_escaneos", lambda: str(carpeta))
    monkeypatch.setattr(ajustes, "leer",
                        lambda clave, defecto=None:
                        str(carpeta) if clave == "carpeta_escaneos" else defecto)
    return str(carpeta)


def _pdf(ruta, contenido=b"%PDF-1.4 de prueba"):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as fh:
        fh.write(contenido)
    return ruta


def test_un_escaneo_sin_cliente_nace_en_sin_identificar(escaneos):
    ruta = archivo.ruta_provisional(escaneos, "gastos", date(2026, 9, 2))
    assert archivo.SIN_IDENTIFICAR in ruta
    assert os.path.basename(ruta) == "Escaneo_gastos_2026-09-02.pdf"
    assert archivo.sin_identificar(ruta)


def test_al_saber_el_cliente_el_pdf_se_muda_a_su_carpeta(escaneos):
    ruta = _pdf(archivo.ruta_provisional(escaneos, "gastos", date(2026, 9, 2)))
    nueva = archivo.mover_a_cliente(ruta, "CLIENTE EJEMPLO", "gastos",
                                    date(2026, 9, 2))

    assert os.path.exists(nueva) and not os.path.exists(ruta)
    assert nueva.endswith(os.path.join("CLIENTE EJEMPLO", "2026", "Gastos",
                                       "CLIENTE EJEMPLO_gastos_2026-09-02.pdf"))
    # la carpeta "Sin identificar" se queda vacia y se recoge
    assert not os.path.isdir(os.path.join(escaneos, archivo.SIN_IDENTIFICAR))


def test_mover_sin_cliente_no_toca_nada(escaneos):
    ruta = _pdf(os.path.join(escaneos, archivo.SIN_IDENTIFICAR, "x.pdf"))
    assert archivo.mover_a_cliente(ruta, "") == ruta
    assert os.path.exists(ruta)


def test_un_pdf_externo_se_copia_y_el_original_no_se_mueve(escaneos):
    origen = _pdf(os.path.join(os.path.dirname(escaneos), "PDF de HP.pdf"))

    copia = archivo.copiar_a_cliente(
        origen, "CLIENTE EJEMPLO", "gastos", ejercicio=2025)

    assert os.path.exists(origen)
    assert os.path.exists(copia)
    assert copia != origen
    assert copia.endswith(os.path.join(
        "CLIENTE EJEMPLO", "2025", "Gastos", "PDF de HP.pdf"))


def test_excel_consolidado_va_al_escritorio_con_nombre_para_aplifisa(escaneos):
    primero = archivo.ruta_excel_consolidado(
        "CLIENTE", 2025, "gasto", escaneos)
    segundo = archivo.ruta_excel_consolidado(
        "CLIENTE", 2025, "gasto", escaneos)

    assert primero == os.path.join(escaneos, "GASTOS_CLIENTE.xlsx")
    assert segundo == primero


def test_al_consolidar_solo_borra_los_excel_de_partes_del_mismo_cliente(escaneos):
    temporales = [
        os.path.join(escaneos, "CLIENTE_gastos_parte_01_de_04.xlsx"),
        os.path.join(escaneos, "GASTOS_CLIENTE_parte_02_de_04.xlsx"),
    ]
    conservar = [
        os.path.join(escaneos, "GASTOS_CLIENTE.xlsx"),
        os.path.join(escaneos, "OTRO_gastos_parte_01_de_02.xlsx"),
        os.path.join(escaneos, "CLIENTE_ingresos_parte_01_de_02.xlsx"),
    ]
    for ruta in temporales + conservar:
        with open(ruta, "wb") as fh:
            fh.write(b"xlsx")

    borrados = archivo.eliminar_excel_temporales(
        "CLIENTE", "gasto", escaneos)

    assert set(borrados) == set(temporales)
    assert not any(os.path.exists(ruta) for ruta in temporales)
    assert all(os.path.exists(ruta) for ruta in conservar)


def test_el_listado_ordena_por_fecha_y_dice_de_quien_es(escaneos):
    _pdf(os.path.join(escaneos, "CLIENTE A", "2025", "Gastos",
                      "CLIENTE A_gastos_2026-09-01.pdf"))
    _pdf(os.path.join(escaneos, "CLIENTE B", "2026", "Ingresos",
                      "CLIENTE B_ingresos_2026-09-02.pdf"))
    os.utime(os.path.join(escaneos, "CLIENTE A", "2025", "Gastos",
                          "CLIENTE A_gastos_2026-09-01.pdf"),
             (1_600_000_000, 1_600_000_000))   # mas antiguo

    lista = archivo.listar(escaneos)
    assert [e.cliente for e in lista] == ["CLIENTE B", "CLIENTE A"]
    assert [(e.ejercicio, e.tipo) for e in lista] == [
        (2026, "ingresos"), (2025, "gastos")]
    assert lista[0].tamano_texto.endswith("KB")


def test_quitar_un_escaneo_no_lo_borra_lo_manda_a_la_papelera(escaneos):
    ruta = _pdf(os.path.join(escaneos, "CLIENTE", "uno.pdf"))
    destino = archivo.a_papelera(ruta)

    assert not os.path.exists(ruta)
    assert os.path.exists(destino)
    assert archivo.PAPELERA in destino
    # y la papelera no sale en el listado
    assert archivo.listar(escaneos) == []


def test_la_papelera_no_pisa_dos_archivos_iguales(escaneos):
    archivo.a_papelera(_pdf(os.path.join(escaneos, "A", "uno.pdf")))
    segundo = archivo.a_papelera(_pdf(os.path.join(escaneos, "B", "uno.pdf")))
    assert os.path.basename(segundo) == "uno_2.pdf"


def test_corregir_a_mano_de_quien_es_un_escaneo(escaneos):
    ruta = _pdf(os.path.join(escaneos, archivo.SIN_IDENTIFICAR,
                             "Escaneo_ingresos_2026-09-02.pdf"))
    nueva = archivo.renombrar_cliente(ruta, "Quien Era")
    assert "Quien Era_ingresos_" in os.path.basename(nueva)


# --------------------------------------------------- integrado con la ventana
def _procesada(tipo="gasto"):
    f = Factura(num_factura="F-1", fecha="16/07/2026", nombre="PROVEEDOR SL",
                nif="B30048276", concepto="600", base_iva=100.0, pct_iva=21.0,
                cuota_iva=21.0, total_impreso=121.0)
    return FacturaProcesada(tipo=tipo, facturas=[f], cuenta="600", gxx=None,
                            origen="x.pdf", pagina=1)


def test_el_escaneo_se_coloca_solo_al_detectar_al_cliente(escaneos):
    ruta = _pdf(archivo.ruta_provisional(escaneos, "gastos", date(2026, 9, 2)))
    v = VentanaPrincipal(comprobar_updates=False)
    v._rutas_actuales = [ruta]
    v._escaneo_sin_identificar = True

    v._on_terminado([(b"", _procesada())], "CLIENTE DETECTADO", "12345678Z")

    assert not os.path.exists(ruta)
    colocado = v._rutas_actuales[0]
    assert "CLIENTE DETECTADO_gastos_" in os.path.basename(colocado)
    assert os.path.join("CLIENTE DETECTADO", "2026", "Gastos") in colocado
    # el bloque toma el nombre nuevo y la factura apunta al PDF movido
    assert v.tabla.item(0, C_BLOQUE).text().startswith("CLIENTE DETECTADO")
    assert v.filas[0]["factura"].origen_imagen == colocado


def test_un_taco_de_ventas_se_archiva_como_ingresos(escaneos):
    ruta = _pdf(archivo.ruta_provisional(escaneos, "gastos", date(2026, 9, 2)))
    v = VentanaPrincipal(comprobar_updates=False)
    v._rutas_actuales = [ruta]
    v._escaneo_sin_identificar = True

    v._on_terminado([(b"", _procesada("venta")), (b"", _procesada("venta"))],
                    "CLIENTE", "12345678Z")

    assert "_ingresos_" in os.path.basename(v._rutas_actuales[0])


def test_se_archiva_en_el_ejercicio_de_la_factura_no_en_el_del_escaneo(escaneos):
    ruta = _pdf(archivo.ruta_provisional(escaneos, "gastos", date(2026, 9, 2)))
    v = VentanaPrincipal(comprobar_updates=False)
    v._rutas_actuales = [ruta]
    v._escaneo_sin_identificar = True

    pr = _procesada()
    pr.facturas[0].fecha = "31/12/2024"
    v._on_terminado([(b"", pr)], "CLIENTE", "12345678Z")

    assert os.path.join("CLIENTE", "2024", "Gastos") in v._rutas_actuales[0]


def test_si_no_se_detecta_el_cliente_el_pdf_se_queda_donde_esta(escaneos):
    ruta = _pdf(archivo.ruta_provisional(escaneos, "gastos", date(2026, 9, 2)))
    v = VentanaPrincipal(comprobar_updates=False)
    v._rutas_actuales = [ruta]
    v._escaneo_sin_identificar = True

    v._on_terminado([(b"", _procesada())], "", "")

    assert os.path.exists(ruta)          # se puede colocar luego a mano
    assert v._escaneo_sin_identificar


def test_pdf_largo_externo_archiva_el_original_y_borra_solo_la_parte_interna(
        escaneos, tmp_path, monkeypatch):
    original = _pdf(os.path.join(str(tmp_path), "lote HP de 100 hojas.pdf"))
    datos_app = tmp_path / "datos_app"
    carpeta_partes = datos_app / "cola_pdf" / "lote_interno"
    parte = _pdf(str(carpeta_partes / "lote_parte_02_de_04.pdf"))
    monkeypatch.setattr(app_mod, "dir_datos", lambda: str(datos_app))

    pr = _procesada()
    pr.origen = parte
    pr.pagina = 1
    pr.facturas[0].origen_imagen = parte
    v = VentanaPrincipal(comprobar_updates=False, restaurar_sesion=False)
    v._elemento_cola_actual = {
        "rutas": [parte], "original": original,
        "etiqueta": "lote_parte_02_de_04", "parte": 2, "partes": 4,
        "archivar": True, "mover_original": False,
        "desde_escaner": False, "sin_identificar": False,
        "tipo_escaneo": "gastos",
    }
    v._rutas_actuales = [parte]

    v._on_terminado(
        [(b"imagen", pr)], "CLIENTE", "12345678Z",
        [(b"imagen", parte, 1, {})])

    copia = v.filas[0]["factura"].origen_imagen
    assert os.path.exists(original)           # el PDF elegido no se mueve
    assert os.path.exists(copia)              # copia documental completa
    assert os.path.join("CLIENTE", "2026", "Gastos") in copia
    assert not os.path.exists(parte)           # solo era una parte de trabajo
    assert pr.pagina == 26                     # página real del PDF de 100 hojas
    assert v._bloques[0]["crudos"][0][1:3] == (copia, 26)


def test_la_fecha_sale_del_nombre_no_de_cuando_se_movio(escaneos):
    # Al mudar un PDF a la carpeta del cliente cambia su fecha de archivo; la
    # buena es la del escaneo, que va en el nombre.
    ruta = _pdf(os.path.join(escaneos, "CLIENTE",
                             "CLIENTE_gastos_2026-01-15.pdf"))
    assert archivo._fecha_de_archivo(ruta) == date(2026, 1, 15)


def test_comprime_ingresos_y_gastos_del_ejercicio_para_aplifisa(escaneos):
    gasto = _pdf(os.path.join(escaneos, "CLIENTE", "2025", "Gastos", "g.pdf"))
    ingreso = _pdf(os.path.join(escaneos, "CLIENTE", "2025", "Ingresos", "i.pdf"))

    destino = archivo.comprimir_ejercicio(escaneos, "CLIENTE", 2025)

    assert os.path.exists(destino)
    with zipfile.ZipFile(destino) as comprimido:
        assert set(comprimido.namelist()) == {
            "Gastos/", "Ingresos/", "Gastos/g.pdf", "Ingresos/i.pdf"}
    assert os.path.exists(gasto) and os.path.exists(ingreso)


def test_no_crea_un_zip_vacio(escaneos):
    os.makedirs(os.path.join(escaneos, "CLIENTE", "2025", "Gastos"))
    with pytest.raises(ValueError):
        archivo.comprimir_ejercicio(escaneos, "CLIENTE", 2025)
