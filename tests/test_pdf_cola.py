import os

import fitz
import pytest

from facturas_excel import pdf


def _crear_pdf(ruta, paginas):
    doc = fitz.open()
    for numero in range(1, paginas + 1):
        pagina = doc.new_page()
        pagina.insert_text((72, 72), f"Pagina {numero}")
    doc.save(ruta)
    doc.close()
    return str(ruta)


@pytest.mark.parametrize("total,esperadas", [(70, [25, 25, 20]),
                                               (100, [25, 25, 25, 25])])
def test_divide_pdf_largo_en_partes_de_25(tmp_path, total, esperadas):
    original = _crear_pdf(tmp_path / "lote.pdf", total)
    partes = pdf.dividir_pdf(original, 25, str(tmp_path / "partes"))

    assert [pdf.numero_paginas(ruta) for ruta in partes] == esperadas
    assert all(os.path.isfile(ruta) for ruta in partes)
    assert "parte_01_de_" in os.path.basename(partes[0])


def test_pdf_pequeno_no_se_copia_ni_se_divide(tmp_path):
    original = _crear_pdf(tmp_path / "lote.pdf", 24)
    assert pdf.dividir_pdf(original) == [os.path.abspath(original)]


def test_rechaza_tamano_de_parte_invalido(tmp_path):
    original = _crear_pdf(tmp_path / "lote.pdf", 2)
    with pytest.raises(ValueError):
        pdf.dividir_pdf(original, 0)
