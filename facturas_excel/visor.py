"""El documento original, con recuadros sobre los datos que interesa mirar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from .ventana_comun import VisorClicable


@dataclass
class Recuadro:
    x0: float           # de 0 a 1 sobre la imagen
    y0: float
    x1: float
    y1: float
    color: str
    texto: str = ""
    destacado: bool = False
    discontinuo: bool = False


class VisorDocumento(VisorClicable):
    """La hoja escalada y centrada, con los recuadros dibujados encima."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._recuadros: List[Recuadro] = []

    def poner_recuadros(self, recuadros: List[Recuadro]) -> None:
        self._recuadros = list(recuadros or [])
        self.update()

    def recuadros(self) -> List[Recuadro]:
        return list(self._recuadros)

    def rect_imagen(self) -> Optional[QRectF]:
        """Dónde queda la imagen dentro del visor (está centrada)."""
        pix = self.pixmap()
        if pix is None or pix.isNull():
            return None
        area = self.contentsRect()
        x = area.x() + (area.width() - pix.width()) / 2
        y = area.y() + (area.height() - pix.height()) / 2
        return QRectF(x, y, pix.width(), pix.height())

    def rect_de(self, r: Recuadro) -> Optional[QRectF]:
        imagen = self.rect_imagen()
        if imagen is None:
            return None
        margen = 3
        return QRectF(imagen.x() + r.x0 * imagen.width() - margen,
                      imagen.y() + r.y0 * imagen.height() - margen,
                      (r.x1 - r.x0) * imagen.width() + 2 * margen,
                      (r.y1 - r.y0) * imagen.height() + 2 * margen)

    def paintEvent(self, evento):
        super().paintEvent(evento)
        if not self._recuadros:
            return
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)
        fuente = QFont(self.font())
        fuente.setPointSizeF(max(7.5, fuente.pointSizeF() - 1))
        fuente.setBold(True)
        pintor.setFont(fuente)
        for r in sorted(self._recuadros, key=lambda x: x.destacado):
            rect = self.rect_de(r)
            if rect is None:
                continue
            color = QColor(r.color)
            relleno = QColor(color)
            relleno.setAlpha(46 if r.destacado else 26)
            lapiz = QPen(color, 2.6 if r.destacado else 1.8)
            if r.discontinuo:
                lapiz.setStyle(Qt.DashLine)
            pintor.setPen(lapiz)
            pintor.setBrush(relleno)
            pintor.drawRoundedRect(rect, 3, 3)
            if r.texto:
                medida = pintor.fontMetrics().boundingRect(r.texto)
                etiqueta = QRectF(rect.x(), rect.y() - medida.height() - 4,
                                  medida.width() + 10, medida.height() + 4)
                if etiqueta.y() < 0:
                    etiqueta.moveTop(rect.bottom() + 2)
                fondo = QColor(color)
                pintor.setPen(Qt.NoPen)
                pintor.setBrush(fondo)
                pintor.drawRoundedRect(etiqueta, 3, 3)
                pintor.setPen(QColor("#FFFFFF"))
                pintor.drawText(etiqueta, Qt.AlignCenter, r.texto)
        pintor.end()
