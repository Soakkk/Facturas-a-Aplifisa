"""El expediente del ejercicio se une sin abrir todo lo archivado a la vez.

expediente._unir abría todos los PDF del ejercicio a la vez y el PDF unido
crecía entero en memoria: con 404 MB archivados, 557 MB de pico (y crece con
todo lo del año). Ahora cada PDF se abre, se inserta y se cierra, y lo unido
se vuelca al disco cada poco. Solo datos inventados.
"""

import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pdf(ruta, paginas):
    documento = fitz.open()
    for numero in range(1, paginas + 1):
        documento.new_page(width=300, height=420).insert_text(
            (30, 60), f"FACTURA DE PRUEBA {numero}", fontsize=9)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def test_unir_el_expediente_no_abre_todo_el_ejercicio(tmp_path, monkeypatch):
    from facturas_excel import expediente
    pdfs = [_pdf(tmp_path / f"2026-01-{n:02d} factura.pdf", 2) for n in range(1, 9)]
    vivos, maximo = set(), [0]
    abrir, cerrar = fitz.open, fitz.Document.close

    def abrir_contando(*a, **k):
        documento = abrir(*a, **k)
        vivos.add(id(documento))
        maximo[0] = max(maximo[0], len(vivos))
        return documento

    def cerrar_contando(self):
        vivos.discard(id(self))
        return cerrar(self)
    monkeypatch.setattr(fitz, "open", abrir_contando)
    monkeypatch.setattr(fitz.Document, "close", cerrar_contando)
    # Lo unido se vuelca al disco tras cada PDF (en el programa, cada 64 MB).
    monkeypatch.setattr(expediente, "TOPE_UNIR_EN_MEMORIA", 1, raising=False)
    destino = str(tmp_path / "Gastos 2026.pdf")

    paginas = expediente._unir(pdfs, destino, "Gastos 2026 · CLIENTE PRUEBA")

    assert maximo[0] <= 2          # el unido y uno de origen, nunca todos
    assert paginas == 1 + 16
    with abrir(destino) as unido:
        assert unido.page_count == 17
        assert [t[1] for t in unido.get_toc()] == ["Índice"] + [
            os.path.basename(p) for p in pdfs]
        indice = unido[0].get_text()
        assert "Gastos 2026" in indice and "2026-01-08 factura.pdf" in indice
        assert "FACTURA DE PRUEBA 2" in unido[16].get_text()


@pytest.mark.parametrize("tope", [None, 1], ids=["en_memoria", "volcando"])
def test_un_pdf_que_falla_a_mitad_no_deja_hojas_sueltas(tmp_path, monkeypatch, tope):
    # Uno cifrado (o cortado) puede fallar al unirlo con alguna hoja ya
    # metida: el índice decía «no se pudo abrir» y esas hojas quedaban en
    # medio, sin marcador, entre las de los documentos de al lado.
    from facturas_excel import expediente
    if tope:
        monkeypatch.setattr(expediente, "TOPE_UNIR_EN_MEMORIA", tope)
    antes = _pdf(tmp_path / "2026-01-01 a.pdf", 2)
    cifrado = str(tmp_path / "2026-02-01 cifrado.pdf")
    with fitz.open(_pdf(tmp_path / "claro.pdf", 3)) as documento:
        documento.save(cifrado, encryption=fitz.PDF_ENCRYPT_AES_256,
                       user_pw="clave", owner_pw="duena")
    despues = _pdf(tmp_path / "2026-03-01 b.pdf", 1)
    destino = str(tmp_path / "Gastos 2026.pdf")

    paginas = expediente._unir([antes, cifrado, despues], destino,
                               "Gastos 2026 · CLIENTE PRUEBA")

    assert paginas == 1 + 2 + 1
    with fitz.open(destino) as unido:
        assert unido.page_count == 4
        assert unido.get_toc() == [[1, "Índice", 1], [1, "2026-01-01 a.pdf", 2],
                                   [1, "2026-03-01 b.pdf", 4]]
        assert "no se pudo abrir" in unido[0].get_text()
        assert "FACTURA DE PRUEBA 2" in unido[2].get_text()     # la última de «a»
        assert "FACTURA DE PRUEBA 1" in unido[3].get_text()     # la de «b»


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="el pico de memoria se lee en /proc")
def test_unir_el_expediente_no_sube_la_memoria_con_lo_archivado(tmp_path):
    guion = tmp_path / "medir.py"
    guion.write_text('''
import io, os, sys
sys.path.insert(0, sys.argv[2])
import fitz
from PIL import Image
from facturas_excel import expediente
carpeta = sys.argv[1]
foto = io.BytesIO()
Image.effect_noise((1100, 1550), 60).convert("RGB").save(foto, "JPEG", quality=92)
pdfs = []
for n in range(40):                     # unos 50 MB de facturas del año
    documento = fitz.open()
    hoja = documento.new_page(width=595, height=842)
    hoja.insert_image(hoja.rect, stream=foto.getvalue())
    pdfs.append(os.path.join(carpeta, "%02d.pdf" % n))
    documento.save(pdfs[-1])
    documento.close()
def leer(clave):
    for linea in open("/proc/self/status"):
        if linea.startswith(clave):
            return int(linea.split()[1]) / 1024
expediente.TOPE_UNIR_EN_MEMORIA = 8 * 2 ** 20
open("/proc/self/clear_refs", "w").write("5")     # el pico, desde aquí
antes = leer("VmRSS:")
expediente._unir(pdfs, os.path.join(carpeta, "unido.pdf"), "Prueba")
print(round(leer("VmHWM:") - antes))
''', encoding="utf-8")
    raiz = os.environ.get("RAIZ_PROGRAMA") or RAIZ
    salida = subprocess.run([sys.executable, str(guion), str(tmp_path), raiz],
                            capture_output=True, text=True, timeout=120)
    assert salida.returncode == 0, salida.stderr[-800:]
    subida = int(salida.stdout.strip().splitlines()[-1])
    # Antes subía tanto como los PDF (unos 50 MB); ahora, el tope y uno.
    assert subida < 25, f"{subida} MB"
