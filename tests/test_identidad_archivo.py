from pathlib import Path
import pytest

from facturas_excel import archivo, clientes, identidad_archivo as identidad


@pytest.fixture
def base(tmp_path, monkeypatch):
    carpeta = tmp_path / "archivo"
    carpeta.mkdir()
    monkeypatch.setattr(archivo, "carpeta_escaneos", lambda: str(carpeta))
    return carpeta


def pdf(base, ruta, datos=b"PDF sintetico"):
    destino = base / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)
    return destino


def test_nif_mantiene_carpeta_aunque_cambie_el_nombre_y_se_reinicie(base):
    a = archivo.carpeta_tipo_cliente("ANA LOPEZ PEREZ", 2026, "gastos", str(base), "12345678Z")
    b = archivo.carpeta_tipo_cliente("LOPEZ PEREZ ANA", 2026, "gastos", str(base), "12345678-Z")
    assert a == b
    assert "ANA LOPEZ PEREZ — 12345678Z" in a
    assert (Path(a).parent / "Ingresos").is_dir()
    otro = archivo.carpeta_tipo_cliente("ANA LOPEZ PEREZ", 2026, "gastos", str(base), "B12345674")
    assert a != otro


def test_reimportar_pdf_no_crea_copias_y_no_confunde_mismo_nombre(base, tmp_path):
    original = pdf(tmp_path, "externo/a.pdf")
    a = archivo.copiar_a_cliente(str(original), "ANA", ejercicio=2026, nif="12345678Z")
    b = archivo.copiar_a_cliente(str(original), "OTRA ESCRITURA", ejercicio=2026, nif="12345678Z")
    assert a == b and original.exists()
    original.write_bytes(b"PDF distinto con igual nombre")
    c = archivo.copiar_a_cliente(str(original), "ANA", ejercicio=2026, nif="12345678Z")
    assert c != a and Path(a).read_bytes() == b"PDF sintetico"


def test_plan_no_mueve_y_organizar_es_reversible_con_colisiones(base):
    clientes.marcar_cliente("12345678Z", "ANA LOPEZ PEREZ")
    rutas = [pdf(base, "ANA LOPEZ PEREZ/2026/Gastos/a.pdf"),
             pdf(base, "LOPEZ PEREZ ANA/2026/Gastos/a.pdf"),
             pdf(base, "PEREZ ANA LOPEZ/2026/Gastos/a.pdf", b"distinto")]
    anteriores = {str(p.relative_to(base)): p.read_bytes() for p in rutas}
    plan = identidad.planificar(base)
    assert len(plan["movimientos"]) == 3
    assert any(m["destino"].startswith(identidad.DUPLICADOS) for m in plan["movimientos"])
    assert all(p.exists() for p in rutas)
    identidad.aplicar(base, plan)
    assert all(not p.exists() for p in rutas)
    assert len(archivo.listar(str(base))) == 2
    assert identidad.deshacer_ultimo(base)
    assert all((base / p).read_bytes() == contenido for p, contenido in anteriores.items())
    assert not identidad.deshacer_ultimo(base)


def test_identidad_ambigua_no_propone_mezclar_clientes(base):
    clientes.marcar_cliente("12345678Z", "ANA LOPEZ PEREZ")
    clientes.marcar_cliente("B12345674", "ANA LOPEZ PEREZ")
    pdf(base, "LOPEZ PEREZ ANA/2026/Gastos/a.pdf")
    plan = identidad.planificar(base)
    assert not plan["movimientos"]
    assert plan["pendientes"] == ["LOPEZ PEREZ ANA"]


def test_deduplica_por_contenido_aunque_el_nombre_sea_distinto(base):
    clientes.marcar_cliente("12345678Z", "ANA LOPEZ PEREZ")
    a = pdf(base, "ANA LOPEZ PEREZ/2026/Ingresos/ventas.pdf")
    b = pdf(base, "LOPEZ PEREZ ANA/2026/Ingresos/ventas_2.pdf")
    plan = identidad.planificar(base)
    assert sum(m["destino"].startswith(identidad.DUPLICADOS) for m in plan["movimientos"]) == 1
    identidad.aplicar(base, plan)
    assert len(archivo.listar(str(base))) == 1
    assert not identidad.planificar(base)["movimientos"]
    assert identidad.deshacer_ultimo(base)
    assert a.exists() and b.exists()


def test_indice_danado_no_se_reemplaza(base):
    indice = base / identidad.INDICE
    indice.write_text('{"12345678Z": {}}', encoding="utf-8")
    with pytest.raises(ValueError):
        identidad.carpeta_cliente(base, "ANA", "12345678Z")
    assert indice.read_text(encoding="utf-8") == '{"12345678Z": {}}'


def test_deshacer_conserva_nuevos_escaneos_y_su_identidad(base):
    clientes.marcar_cliente("12345678Z", "ANA LOPEZ PEREZ")
    original = pdf(base, "LOPEZ PEREZ ANA/2026/Ingresos/ventas.pdf")
    identidad.aplicar(base, identidad.planificar(base))
    carpeta = identidad.carpeta_cliente(base, "ANA", "12345678Z")
    nuevo = pdf(base, carpeta + "/2026/Ingresos/nuevo.pdf", b"nuevo")
    assert identidad.deshacer_ultimo(base)
    assert original.exists() and nuevo.exists()
    assert identidad.carpeta_cliente(base, "OTRO NOMBRE", "12345678Z") == carpeta


def test_interfaz_filtra_por_nif_y_no_exporta_seleccion_oculta(base):
    from PySide6.QtWidgets import QApplication
    from facturas_excel.dialogo_escaneos import DialogoEscaneos
    app = QApplication.instance() or QApplication([])
    carpeta = archivo.carpeta_tipo_cliente("ANA", 2026, "gastos", str(base), "12345678Z")
    pdf(Path(carpeta), "a.pdf")
    d = DialogoEscaneos()
    assert d.tabla.item(0, 1).text() == "12345678Z"
    d.tabla.selectRow(0)
    d.buscar.setText("inexistente")
    assert d.tabla.isRowHidden(0) and not d._seleccionados()
    d.buscar.setText("12345678Z")
    assert not d.tabla.isRowHidden(0)


def test_no_aplica_archivo_modificado_desde_la_vista_previa(base):
    clientes.marcar_cliente("12345678Z", "ANA LOPEZ PEREZ")
    original = pdf(base, "LOPEZ PEREZ ANA/2026/Gastos/a.pdf")
    plan = identidad.planificar(base)
    original.write_bytes(b"actualizado")
    with pytest.raises(ValueError):
        identidad.aplicar(base, plan)
    assert original.read_bytes() == b"actualizado"


def test_no_sale_de_la_raiz_ni_sobrescribe_destinos(base, tmp_path):
    origen = pdf(base, "origen.pdf")
    destino = pdf(base, "destino.pdf", b"conservar")
    with pytest.raises(ValueError):
        identidad._trasladar(base, "origen.pdf", "../fuera.pdf", identidad.huella(origen))
    with pytest.raises(FileExistsError):
        identidad._trasladar(base, "origen.pdf", "destino.pdf", identidad.huella(origen))
    assert destino.read_bytes() == b"conservar" and origen.exists()


def test_fallo_parcial_se_puede_deshacer_sin_perder_originales(base, monkeypatch):
    clientes.marcar_cliente("12345678Z", "ANA LOPEZ PEREZ")
    a = pdf(base, "LOPEZ PEREZ ANA/2026/Ingresos/a.pdf")
    b = pdf(base, "LOPEZ PEREZ ANA/2026/Ingresos/b.pdf", b"segundo")
    plan = identidad.planificar(base)
    mover = identidad._trasladar
    def fallo(base, origen, destino, digest):
        if origen.endswith("b.pdf"):
            raise OSError("disco no disponible")
        return mover(base, origen, destino, digest)
    monkeypatch.setattr(identidad, "_trasladar", fallo)
    with pytest.raises(OSError):
        identidad.aplicar(base, plan)
    monkeypatch.setattr(identidad, "_trasladar", mover)
    assert identidad.deshacer_ultimo(base)
    assert a.exists() and b.exists()


def test_cambiar_cliente_conserva_tipo_de_la_carpeta(base):
    original = pdf(base, "Anterior/2024/Ingresos/Ventas enero.pdf")
    destino = archivo.renombrar_cliente(str(original), "ANA", "12345678Z")
    assert Path(destino).parent == base / "ANA — 12345678Z/2024/Ingresos"


def test_listado_y_zip_con_nombre_largo_conservan_nif(base):
    carpeta = archivo.carpeta_tipo_cliente("A" * 60, 2026, "ingresos", str(base), "12345678Z")
    pdf(Path(carpeta), "a.pdf")
    esc = archivo.listar(str(base))[0]
    assert esc.nif == "12345678Z"
    assert Path(archivo.comprimir_ejercicio(str(base), esc.carpeta_cliente, 2026)).exists()
