"""El documento original, con recuadros sobre los datos que interesa mirar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QAbstractScrollArea, QLabel


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


class VisorDocumento(QLabel):
    """La hoja escalada y centrada, con los recuadros dibujados encima.

    Antes un clic abría la hoja en una ventana casi a pantalla completa que
    tapaba la tabla. Ahora todo se hace aquí mismo: se arrastra para moverse
    por la hoja, Ctrl + rueda acerca o aleja donde está el ratón y un doble
    clic acerca ese punto (o vuelve a la hoja entera).
    """

    zoom_pedido = Signal(float, QPointF)   # factor, punto (en el visor)
    doble_clic = Signal(QPointF)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._recuadros: List[Recuadro] = []
        self._arrastre = None
        self._movible = False

    # ---------- moverse por la hoja ----------
    def poner_movible(self, movible: bool) -> None:
        """Mano para arrastrar solo si la hoja no cabe entera a la vista."""
        self._movible = bool(movible)
        if self._arrastre is None:
            self.setCursor(Qt.OpenHandCursor if self._movible else Qt.ArrowCursor)

    def _tiene_imagen(self) -> bool:
        pix = self.pixmap()
        return pix is not None and not pix.isNull()

    def _barras(self):
        """Las barras de desplazamiento del visor que contiene la hoja."""
        padre = self.parentWidget()
        while padre is not None and not isinstance(padre, QAbstractScrollArea):
            padre = padre.parentWidget()
        if padre is None:
            return None, None
        return padre.horizontalScrollBar(), padre.verticalScrollBar()

    def mousePressEvent(self, evento):
        horizontal, vertical = self._barras()
        if (evento.button() == Qt.LeftButton and self._tiene_imagen()
                and horizontal is not None):
            self._arrastre = (evento.globalPosition(), horizontal.value(),
                              vertical.value())
            self.setCursor(Qt.ClosedHandCursor)
            evento.accept()
            return
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento):
        if self._arrastre is not None:
            inicio, x0, y0 = self._arrastre
            movido = evento.globalPosition() - inicio
            horizontal, vertical = self._barras()
            if horizontal is not None:
                horizontal.setValue(round(x0 - movido.x()))
                vertical.setValue(round(y0 - movido.y()))
            evento.accept()
            return
        super().mouseMoveEvent(evento)

    def mouseReleaseEvent(self, evento):
        if self._arrastre is not None and evento.button() == Qt.LeftButton:
            self._arrastre = None
            self.poner_movible(self._movible)
            evento.accept()
            return
        super().mouseReleaseEvent(evento)

    def mouseDoubleClickEvent(self, evento):
        if evento.button() == Qt.LeftButton and self._tiene_imagen():
            self.doble_clic.emit(evento.position())
            evento.accept()
            return
        super().mouseDoubleClickEvent(evento)

    def wheelEvent(self, evento):
        # Sin Ctrl, la rueda desplaza la hoja como siempre (lo hace el visor).
        if evento.modifiers() & Qt.ControlModifier and self._tiene_imagen():
            pasos = evento.angleDelta().y() / 120
            if pasos:
                self.zoom_pedido.emit(1.25 ** pasos, evento.position())
            evento.accept()
            return
        super().wheelEvent(evento)

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
        # En pantallas con escala (125 %, 150 %…) la imagen lleva más puntos
        # que el sitio que ocupa: cuenta su tamaño en pantalla, no en puntos.
        tam = pix.deviceIndependentSize()
        area = self.contentsRect()
        x = area.x() + (area.width() - tam.width()) / 2
        y = area.y() + (area.height() - tam.height()) / 2
        return QRectF(x, y, tam.width(), tam.height())

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
