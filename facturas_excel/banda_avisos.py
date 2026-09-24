"""Avisos dentro de la ventana, con «Deshacer» cuando se puede.

Las ventanas emergentes interrumpen y obligan a pulsar «Aceptar» para cosas
que solo informan («3 líneas eliminadas», «Exportación terminada»). Esta banda
aparece encima de la tabla, no bloquea nada, se va sola al rato (salvo los
avisos que conviene leer con calma) y ofrece deshacer la última operación.
Las ventanas emergentes quedan para las decisiones de verdad.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

INFO, EXITO, AVISO, ERROR = "info", "exito", "aviso", "error"

_ESTILOS = {
    INFO: ("#EAF3FC", "#326FA6", "#24384D"),
    EXITO: ("#E4F1EA", "#19724E", "#154B35"),
    AVISO: ("#FBEFDC", "#86500A", "#5C3907"),
    ERROR: ("#F8E1E1", "#B43737", "#6E1F1F"),
}


class BandaAvisos(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bandaAvisos")
        fila = QHBoxLayout(self)
        fila.setContentsMargins(12, 6, 8, 6)
        fila.setSpacing(10)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fila.addWidget(self.lbl, 1)
        self.btn_deshacer = QPushButton("Deshacer")
        self.btn_deshacer.setObjectName("bandaDeshacer")
        self.btn_deshacer.clicked.connect(self._deshacer)
        fila.addWidget(self.btn_deshacer)
        self.btn_cerrar = QPushButton("✕")
        self.btn_cerrar.setObjectName("bandaCerrar")
        self.btn_cerrar.setToolTip("Cerrar el aviso")
        self.btn_cerrar.setFixedWidth(28)
        self.btn_cerrar.clicked.connect(self.ocultar)
        fila.addWidget(self.btn_cerrar)
        self._accion_deshacer: Optional[Callable] = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.ocultar)
        self.historial: list[str] = []      # para pruebas y diagnóstico
        self.hide()

    def mostrar(self, texto: str, tipo: str = INFO,
                deshacer: Optional[Callable] = None, segundos: int = 10) -> None:
        """Enseña el aviso. `segundos=0` lo deja fijo hasta cerrarlo."""
        fondo, borde, tinta = _ESTILOS.get(tipo, _ESTILOS[INFO])
        self.setStyleSheet(
            f"QFrame#bandaAvisos {{ background: {fondo}; border: 1px solid {borde};"
            f" border-left: 4px solid {borde}; border-radius: 4px; }}"
            f"QFrame#bandaAvisos QLabel {{ color: {tinta}; font-weight: 600;"
            f" background: transparent; border: none; }}"
            f"QPushButton#bandaDeshacer {{ color: {borde}; font-weight: 700;"
            f" background: white; border: 1px solid {borde}; padding: 3px 10px;"
            f" border-radius: 3px; }}"
            f"QPushButton#bandaCerrar {{ color: {tinta}; background: transparent;"
            f" border: none; }}")
        self.lbl.setText(texto)
        self.historial.append(texto)
        self._accion_deshacer = deshacer
        self.btn_deshacer.setVisible(deshacer is not None)
        self.show()
        if segundos:
            self._timer.start(segundos * 1000)
        else:
            self._timer.stop()

    def ocultar(self) -> None:
        self._timer.stop()
        self._accion_deshacer = None
        self.hide()

    def _deshacer(self) -> None:
        accion = self._accion_deshacer
        self.ocultar()
        if accion:
            accion()
