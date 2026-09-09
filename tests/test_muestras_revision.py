"""Muestras locales: solo documentos ficticios y almacenamiento temporal."""
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from facturas_excel import muestras_revision as muestras
from facturas_excel.modelo import Factura


@pytest.fixture(autouse=True)
def almacen(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


def documentos(tipo):
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in (muestras.carpeta() / tipo).glob("*.json")]


def test_original_deduplicado_se_conserva_tras_mover_fuente(tmp_path):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"%PDF-1.4 ficticio")
    identificador = muestras.guardar_original(str(pdf))
    assert muestras.guardar_original(str(pdf)) == identificador
    pdf.unlink()
    muestras.guardar_lecturas([(b"imagen ficticia", str(pdf), 1, {"total": 121})])
    assert documentos("lecturas")[0]["original_id"] == identificador
    originales = list((muestras.carpeta() / "originales").glob("*"))
    assert len(originales) == 1
    assert originales[0].read_bytes() == b"%PDF-1.4 ficticio"


def test_lecturas_no_pierden_otras_tandas_ni_relecturas(tmp_path):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"pdf ficticio")
    registros = [(b"pagina 1", str(pdf), 1, {"total": 121}),
                 (b"pagina 26", str(pdf), 26, {"total": 242})]
    muestras.guardar_lecturas(registros)
    muestras.guardar_lecturas(registros[:1])
    muestras.guardar_lecturas([(b"pagina 1", str(pdf), 1, {"total": 122})])
    lecturas = documentos("lecturas")
    assert len(lecturas) == 3
    assert sorted(l["datos"]["total"] for l in lecturas) == [121, 122, 242]
    assert len(list((muestras.carpeta() / "imagenes").glob("*"))) == 2


def test_mapping_asocia_original_aunque_ruta_se_reutilice(tmp_path):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"original primero")
    primero = muestras.guardar_original(str(pdf))
    pdf.write_bytes(b"original segundo")
    muestras.guardar_original(str(pdf))
    muestras.guardar_lecturas([(b"imagen", str(pdf), 1, {})],
                             originales={str(pdf): primero})
    assert documentos("lecturas")[0]["original_id"] == primero


def test_revision_preserva_versiones_y_fuentes_sin_duplicar_imagen(tmp_path):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"documento ficticio")
    original = muestras.guardar_original(str(pdf))
    muestras.guardar_lecturas([(b"imagen", str(pdf), 1, {"base": 100})])
    factura = Factura(nif="B12345674", base_iva=100, origen_imagen=str(pdf), pagina_origen=1)
    filas = [{"factura": factura, "tipo": "gasto", "aviso": "revisar",
              "mensajes": ["Comprobar base"], "bloque": "lote", "fuentes": [factura],
              "imagen": b"no serializar UI"}]
    muestras.guardar_revision(filas)
    muestras.guardar_revision(filas)
    factura.base_iva = 110
    factura.revision_confirmada = True
    muestras.guardar_revision(filas)
    revisiones = documentos("revisiones")
    assert len(revisiones) == 2
    assert sorted(r["filas"][0]["factura"]["base_iva"] for r in revisiones) == [100, 110]
    assert all(r["filas"][0]["original_id"] == original for r in revisiones)
    assert all(r["filas"][0]["fuentes"][0]["nif"] == "B12345674" for r in revisiones)
    assert len(list((muestras.carpeta() / "imagenes").glob("*"))) == 1
    assert documentos("lecturas")[0]["datos"] == {"base": 100}


def test_zip_incluye_solo_muestras_y_es_legible(tmp_path):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"documento ficticio")
    muestras.guardar_lecturas([(b"imagen", str(pdf), 1, {"nif": "12345678Z"})])
    (muestras.carpeta().parent / "ajustes.json").write_text('{"api_key":"no exportar"}')
    destino = tmp_path / "entrega.zip"
    assert muestras.exportar_zip(str(destino)) == str(destino)
    with ZipFile(destino) as archivo:
        assert archivo.testzip() is None
        assert any(n.startswith("originales/") for n in archivo.namelist())
        assert any(n.startswith("lecturas/") for n in archivo.namelist())
        assert not any("ajustes" in n for n in archivo.namelist())


def test_error_disco_no_se_oculta_ni_destruye_zip_previo(tmp_path, monkeypatch):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"documento ficticio")
    muestras.guardar_original(str(pdf))
    destino = tmp_path / "entrega.zip"
    destino.write_bytes(b"zip anterior")
    def fallo(*args, **kwargs):
        raise OSError("disco lleno")
    monkeypatch.setattr(muestras.os, "replace", fallo)
    with pytest.raises(OSError, match="disco lleno"):
        muestras.exportar_zip(str(destino))
    assert destino.read_bytes() == b"zip anterior"


def test_lectura_sin_original_conserva_imagen_y_avisa_ausencia(tmp_path):
    muestras.guardar_lecturas([(b"imagen recuperada", str(tmp_path / "ya-no-existe.pdf"), 2, {})])
    lectura = documentos("lecturas")[0]
    assert lectura["original_id"] is None
    assert lectura["imagen_id"]
    imagenes = list((muestras.carpeta() / "imagenes").glob("*"))
    assert imagenes[0].read_bytes() == b"imagen recuperada"


def test_fallo_escritura_no_deja_lectura_parcial(tmp_path, monkeypatch):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"documento ficticio")
    muestras.guardar_lecturas([(b"imagen", str(pdf), 1, {"total": 121})])
    originales = documentos("lecturas")
    replace = muestras.os.replace
    def fallo_lectura(origen, destino):
        if Path(destino).parent.name == "lecturas":
            raise OSError("disco lleno")
        replace(origen, destino)
    monkeypatch.setattr(muestras.os, "replace", fallo_lectura)
    with pytest.raises(OSError, match="disco lleno"):
        muestras.guardar_lecturas([(b"imagen", str(pdf), 1, {"total": 122})])
    assert documentos("lecturas") == originales
    assert not list(muestras.carpeta().rglob(".tmp-*"))


def test_mapping_registra_origen_archivado_para_revision_sin_pdf(tmp_path):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"documento ficticio")
    original = muestras.guardar_original(str(pdf))
    archivado = str(tmp_path / "archivo" / "ficticia.pdf")
    muestras.guardar_lecturas([(b"imagen", archivado, 1, {})],
                             originales={archivado: original})
    factura = Factura(origen_imagen=archivado, pagina_origen=1, eliminada=True)
    muestras.guardar_revision([{"factura": factura, "fuentes": [factura]}])
    revision = documentos("revisiones")[0]["filas"][0]
    assert revision["original_id"] == original
    assert revision["fuentes"][0]["eliminada"] is True


def test_snapshots_identifican_version_y_conservan_cambios_de_version(tmp_path, monkeypatch):
    import facturas_excel
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"documento ficticio")
    registros = [(b"imagen", str(pdf), 1, {"total": 121})]
    muestras.guardar_lecturas(registros)
    lectura = documentos("lecturas")[0]
    assert lectura["version_app"] == facturas_excel.__version__
    assert lectura["schema_version"] == 1
    monkeypatch.setattr(facturas_excel, "__version__", "99.0.0-test")
    muestras.guardar_lecturas(registros)
    assert len(documentos("lecturas")) == 2
    assert any(l["version_app"] == "99.0.0-test" for l in documentos("lecturas"))


def test_zip_no_reexporta_zips_ni_archivos_ajenos_dentro_almacen(tmp_path):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"documento ficticio")
    muestras.guardar_lecturas([(b"imagen", str(pdf), 1, {})])
    raiz = muestras.carpeta()
    muestras.exportar_zip(str(raiz / "originales" / "previo.zip"))
    (raiz / "lecturas" / "ajeno.txt").write_text("no es una lectura")
    (raiz / "originales" / "ajeno.json").write_text("{}")
    destino = tmp_path / "entrega.zip"
    muestras.exportar_zip(str(destino))
    with ZipFile(destino) as archivo:
        assert not any(n.endswith(".zip") for n in archivo.namelist())
        assert not any("ajeno" in n for n in archivo.namelist())
        assert any(n.startswith("originales/") for n in archivo.namelist())


def test_revision_antigua_conserva_id_explicito_si_ruta_se_reutiliza(tmp_path):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"documento ficticio A")
    original_a = muestras.guardar_original(str(pdf))
    factura_a = {"origen_imagen": str(pdf), "original_id": original_a}
    pdf.write_bytes(b"documento ficticio B")
    original_b = muestras.guardar_original(str(pdf))
    assert original_b != original_a
    muestras.guardar_revision([{"factura": factura_a, "fuentes": [factura_a]}])
    fila = documentos("revisiones")[0]["filas"][0]
    assert fila["original_id"] == original_a
    assert fila["originales_fuentes"] == [original_a]


def test_revision_prioriza_id_fila_sobre_factura_y_alias(tmp_path):
    pdf = tmp_path / "ficticia.pdf"
    pdf.write_bytes(b"documento ficticio A")
    original_a = muestras.guardar_original(str(pdf))
    pdf.write_bytes(b"documento ficticio B")
    original_b = muestras.guardar_original(str(pdf))
    muestras.guardar_revision([{"original_id": original_a,
                               "factura": {"origen_imagen": str(pdf),
                                           "original_id": original_b}}])
    assert documentos("revisiones")[0]["filas"][0]["original_id"] == original_a
