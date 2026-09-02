"""Escaneo desde el propio programa: nombre del PDF, taco del alimentador y
armado del PDF. El aparato se simula: los tests no pueden mover papel.
"""

import os
from datetime import date

import pytest

from facturas_excel import escaner


# ------------------------------------------------ nombre y sitio del archivo
def test_el_pdf_se_nombra_con_cliente_tipo_y_fecha(tmp_path):
    ruta = escaner.ruta_destino(str(tmp_path), "Pérez Martínez S.L.", "gastos",
                                date(2026, 9, 2))
    # sin acentos y sin el punto final (Windows no admite nombres acabados en .)
    assert os.path.basename(ruta) == "Perez Martinez S.L_gastos_2026-09-02.pdf"
    # y en su propia carpeta, ya creada
    assert os.path.isdir(os.path.join(str(tmp_path), "Perez Martinez S.L"))


def test_dos_escaneos_el_mismo_dia_no_se_pisan(tmp_path):
    uno = escaner.ruta_destino(str(tmp_path), "CLIENTE", "ingresos", date(2026, 9, 2))
    open(uno, "wb").close()
    dos = escaner.ruta_destino(str(tmp_path), "CLIENTE", "ingresos", date(2026, 9, 2))
    assert os.path.basename(uno) == "CLIENTE_ingresos_2026-09-02.pdf"
    assert os.path.basename(dos) == "CLIENTE_ingresos_2026-09-02_2.pdf"


def test_sanear_quita_lo_que_windows_no_admite():
    assert escaner.sanear('Cliente / "raro" *?') == "Cliente raro"
    assert escaner.sanear("") == "Sin nombre"
    assert escaner.sanear("Ñoño Gutiérrez") == "Nono Gutierrez"


# ------------------------------------------------ escaner de mentira
class PropFalsa:
    def __init__(self, prop_id, valor=0):
        self.PropertyID = prop_id
        self.Value = valor


class ImagenFalsa:
    def __init__(self, datos):
        self.datos = datos

    def SaveFile(self, ruta):
        with open(ruta, "wb") as fh:
            fh.write(self.datos)


class SinPapel(Exception):
    def __init__(self):
        super().__init__(-2147217405, "sin papel", (0, "", "", 0, 0x80210003), 0)
        self.hresult = -2147217405


class ItemFalso:
    def __init__(self, hojas, datos):
        self.Properties = [PropFalsa(p) for p in
                           (escaner.P_TIPO_DATO, escaner.P_RES_H, escaner.P_RES_V,
                            escaner.P_ANCHO, escaner.P_ALTO)]
        self.restantes = hojas
        self.datos = datos

    def Transfer(self, formato):
        if self.restantes <= 0:
            raise SinPapel()
        self.restantes -= 1
        return ImagenFalsa(self.datos)


class EscanerFalso:
    def __init__(self, hojas=3, datos=b"jpeg", papel=True):
        self.Properties = [PropFalsa(escaner.P_MANEJO_PAPEL),
                           PropFalsa(escaner.P_PAGINAS),
                           PropFalsa(escaner.P_ESTADO_PAPEL,
                                     escaner.PAPEL_LISTO if papel else 0)]
        self.Items = {1: ItemFalso(hojas, datos)}


def test_el_alimentador_se_vacia_y_se_paran_las_hojas(tmp_path):
    hojas = escaner.capturar_paginas(EscanerFalso(hojas=3), str(tmp_path))
    assert len(hojas) == 3
    assert all(os.path.exists(h) for h in hojas)


def test_avisa_si_el_alimentador_esta_vacio(tmp_path):
    with pytest.raises(escaner.ErrorEscaneo) as e:
        escaner.capturar_paginas(EscanerFalso(hojas=0, papel=False), str(tmp_path))
    assert "alimentador está vacío" in str(e.value)


def test_va_avisando_de_las_hojas_que_lleva(tmp_path):
    vistas = []
    escaner.capturar_paginas(EscanerFalso(hojas=4), str(tmp_path),
                             progreso=vistas.append)
    assert vistas == [1, 2, 3, 4]


def test_por_el_cristal_solo_escanea_una_hoja(tmp_path):
    hojas = escaner.capturar_paginas(EscanerFalso(hojas=5), str(tmp_path),
                                     alimentador=False)
    assert len(hojas) == 1


def test_el_pdf_sale_con_una_pagina_por_hoja(tmp_path):
    import fitz
    from PIL import Image

    paginas = []
    for i in range(3):
        ruta = tmp_path / f"hoja{i}.jpg"
        Image.new("RGB", (600, 850), "white").save(ruta)
        paginas.append(str(ruta))
    destino = str(tmp_path / "salida" / "lote.pdf")
    escaner.armar_pdf(paginas, destino)

    assert os.path.exists(destino)
    with fitz.open(destino) as doc:
        assert doc.page_count == 3


def test_sin_escaner_conectado_lo_dice_claro(monkeypatch):
    monkeypatch.setattr(escaner, "escaneres", lambda: [])
    monkeypatch.setattr(escaner, "_gestor", lambda: object())
    with pytest.raises(escaner.SinEscaner) as e:
        escaner._conectar(None)
    assert "escáner" in str(e.value)
