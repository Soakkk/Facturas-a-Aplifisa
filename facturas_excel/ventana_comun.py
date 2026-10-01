"""Constantes y ayudas que comparten las piezas de la ventana principal."""

from __future__ import annotations

import os
import re
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QLabel

from facturas_excel.estilo import ACCENT, SUCCESS, WARNING, DANGER
from facturas_excel.ficha_incidencias import TITULOS as TITULOS_ESTADO
from facturas_excel.resumen import porcentaje_iva
from facturas_excel.lote import (
    CON_ERROR, CORREGIDA, POR_REVISAR, REVISADA, SIN_VERIFICAR,
    TEXTO_PRESENTACION, VERIFICADA,
)
from facturas_excel.validacion import ERROR, OK, REVISAR


ESCRITORIO = os.path.join(os.path.expanduser("~"), "Desktop")

COLOR_ESTADO = {OK: QColor(SUCCESS), REVISAR: QColor(WARNING), ERROR: QColor(DANGER)}
# Estados que se ven en la tabla. «Verificada» exige que las dos lecturas de
# la IA coincidan y que todos los controles pasen; con una sola lectura, aunque
# todo cuadre, la fila es «Sin verificar» (se puede exportar, pero se sabe que
# nadie la ha contrastado). El programa decide por el código (lote.py).
ICONO_ESTADO = {OK: TEXTO_PRESENTACION[VERIFICADA],
                REVISAR: TEXTO_PRESENTACION[POR_REVISAR],
                ERROR: TEXTO_PRESENTACION[CON_ERROR]}
ICONO_SIN_VERIFICAR = TEXTO_PRESENTACION[SIN_VERIFICAR]
ICONO_REVISADO = TEXTO_PRESENTACION[REVISADA]
ICONO_CORREGIDO = TEXTO_PRESENTACION[CORREGIDA]
COLOR_CORREGIDA = "#2F6F6B"
# (texto, color, fondo) de cada presentación.
ESTILO_PRESENTACION = {
    VERIFICADA: (QColor(SUCCESS), "#E4F1EA"),
    SIN_VERIFICAR: (QColor("#3F5F7F"), "#EEF2F7"),
    POR_REVISAR: (QColor(WARNING), "#FBEFDC"),
    CON_ERROR: (QColor(DANGER), "#F8E1E1"),
    REVISADA: (QColor(ACCENT), "#E6EFF8"),
    CORREGIDA: (QColor(COLOR_CORREGIDA), "#E2F1EF"),
}
COLOR_CONTADOR = {VERIFICADA: SUCCESS, SIN_VERIFICAR: "#3F5F7F",
                  REVISADA: ACCENT, CORREGIDA: COLOR_CORREGIDA,
                  POR_REVISAR: WARNING, CON_ERROR: DANGER}

_AVISO_EJERCICIOS_ANTIGUO = re.compile(
    r"\s*El PDF mezcla varios ejercicios; se ha archivado en el \d{4}, "
    r"que es el más frecuente\. Revise su ubicación\.", re.IGNORECASE)


def _sin_aviso_ejercicios_antiguo(aviso: str) -> str:
    """Quita el aviso global que antes se copiaba en todas las facturas."""
    return _AVISO_EJERCICIOS_ANTIGUO.sub("", str(aviso or "")).strip()

EXT_FACTURA = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

# Columnas del resumen por bloque (punto de control antes de exportar). Las del
# IVA se calculan: una por cada tipo que haya en el lote, con el porcentaje en
# la cabecera ("IVA 21%") en vez de repetirlo dentro de cada celda.
COLS_RESUMEN_INICIO = ["Ámbito", "Tipo", "Facturas", "Líneas", "Base"]
COLS_RESUMEN_FIN = ["Recargo", "IRPF", "Suplidos", "Total factura"]
TODOS_LOS_BLOQUES = "Todos los bloques"


def _ayuda_estado(estado, mensajes) -> str:
    """El globo del semaforo, con titulo y un punto por cada problema."""
    titulo, color = TITULOS_ESTADO.get(estado, TITULOS_ESTADO[REVISAR])
    if not mensajes:
        return f"<b style='color:{color}'>{titulo}</b>"
    puntos = "".join(f"<div style='margin-top:3px'>•&nbsp;{m}</div>"
                     for m in mensajes)
    return (f"<div style='max-width:420px'>"
            f"<b style='color:{color}'>{titulo}</b>{puntos}</div>")


def _cabeceras_resumen(tipos_iva) -> list:
    """Las columnas del resumen, con una de IVA por cada tipo que haya."""
    if tipos_iva:
        columnas_iva = [f"IVA {porcentaje_iva(p)}%" for p in tipos_iva]
    else:
        columnas_iva = ["IVA"]
    return [*COLS_RESUMEN_INICIO, *columnas_iva, *COLS_RESUMEN_FIN]


class EtiquetaCliente(QLabel):
    """«NOMBRE  ·  NIF» en una línea: si no cabe, se recorta el nombre con
    «…» y el NIF se ve siempre entero. El texto completo va en el globo.

    `text()` sigue devolviendo el texto entero (lo usan otras partes)."""

    SEPARADOR = "  ·  "

    def minimumSizeHint(self) -> QSize:
        alto = super().minimumSizeHint().height()
        return QSize(min(super().sizeHint().width(), 140), alto)

    def sizeHint(self) -> QSize:
        tam = super().sizeHint()
        return QSize(min(tam.width(), 260), tam.height())

    def _visible(self, ancho: int) -> str:
        medida = self.fontMetrics()
        texto = self.text()
        if medida.horizontalAdvance(texto) <= ancho:
            return texto
        nombre, sep, nif = texto.rpartition(self.SEPARADOR)
        if not sep:
            return medida.elidedText(texto, Qt.ElideRight, ancho)
        cola = sep + nif
        resto = max(0, ancho - medida.horizontalAdvance(cola))
        return medida.elidedText(nombre, Qt.ElideRight, resto) + cola

    def paintEvent(self, evento):
        pintor = QPainter(self)
        pintor.setPen(self.palette().color(QPalette.WindowText))
        area = self.contentsRect()
        pintor.drawText(area, Qt.AlignLeft | Qt.AlignVCenter,
                        self._visible(area.width()))
        pintor.end()


def ruta_recurso(nombre):
    base = getattr(
        sys, "_MEIPASS",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", nombre)


def rutas_factura_de_mime(mime):
    """Rutas locales compatibles contenidas en un arrastre."""
    if not mime.hasUrls():
        return []
    rutas = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        ruta = url.toLocalFile()
        if os.path.splitext(ruta)[1].lower() in EXT_FACTURA:
            rutas.append(ruta)
    return rutas
