"""Lo que le pasa a una fila, en una ficha que se abre al lado.

El aviso vivia solo en el globo de ayuda del semaforo: se leia mal, desaparecia
al mover el raton y no se podia copiar. Aqui va con su titulo, cada problema en
su linea y el color del estado, y se queda abierta hasta que se pulsa fuera.
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from .validacion import ERROR, OK, REVISAR

TITULOS = {
    OK: ("Todo correcto", "#2E6B43"),
    REVISAR: ("Hay que revisarla", "#A16207"),
    ERROR: ("No se puede registrar así", "#B42318"),
}
EXPLICACION = {
    OK: "Los importes cuadran y no falta nada obligatorio.",
    REVISAR: "Se puede exportar, pero conviene mirarla antes.",
    ERROR: "Aplifisa la rechazaría o entraría mal: corríjala.",
}
ANCHO = 460


class FichaIncidencias(QFrame):
    """Ficha flotante con los avisos de una fila."""

    def __init__(self, estado: str, mensajes: List[str], parent=None,
                 referencia: str = ""):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("ficha")
        self.setMaximumWidth(ANCHO)
        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(0)

        titulo_texto, color = TITULOS.get(estado, TITULOS[REVISAR])
        # Banda de color arriba: se ve de un golpe si es un aviso o un error.
        banda = QLabel(titulo_texto)
        banda.setObjectName("fichaTitulo")
        banda.setStyleSheet(
            f"background: {color}; color: white; padding: 9px 14px;"
            f"border-top-left-radius: 7px; border-top-right-radius: 7px;")
        caja.addWidget(banda)

        cuerpo = QVBoxLayout()
        cuerpo.setContentsMargins(14, 10, 14, 12)
        cuerpo.setSpacing(7)
        caja.addLayout(cuerpo)
        if referencia:
            # De que factura se habla, para no tener que mirar la fila.
            quien = QLabel(referencia)
            quien.setObjectName("fichaPie")
            quien.setWordWrap(True)
            cuerpo.addWidget(quien)

        for mensaje in mensajes:
            linea = QLabel("•  " + mensaje)
            linea.setObjectName("fichaLinea")
            linea.setWordWrap(True)
            linea.setMaximumWidth(ANCHO - 28)
            linea.setTextInteractionFlags(Qt.TextSelectableByMouse)
            cuerpo.addWidget(linea)

        pie = QLabel(EXPLICACION.get(estado, ""))
        pie.setObjectName("fichaPie")
        pie.setWordWrap(True)
        cuerpo.addWidget(pie)
        self.adjustSize()

    def mostrar_junto_a(self, widget, rect) -> None:
        """La abre pegada a la celda, sin salirse de la pantalla."""
        from PySide6.QtGui import QGuiApplication

        esquina = widget.mapToGlobal(rect.topRight())
        x, y = esquina.x() + 8, esquina.y()
        pantalla = QGuiApplication.screenAt(esquina) or QGuiApplication.primaryScreen()
        if pantalla:
            libre = pantalla.availableGeometry()
            x = min(x, libre.right() - self.width() - 8)
            y = min(max(y, libre.top() + 8), libre.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()
