"""Como se registran las facturas con recargo de equivalencia de este cliente.

Dos clientes pueden comprar los dos con recargo y llevarse de forma distinta,
porque lo que manda es SU regimen, no la factura:

  - MINORISTA en recargo: no presenta el 303 y no deduce IVA, asi que cada
    gasto se registra por el TOTAL de la factura, sin desglose.
  - MAYORISTA en estimacion directa: SI registra el IVA y el recargo, cada uno
    en su sitio, con el desglose normal.

El programa no puede adivinarlo de la factura (las dos traen recargo impreso),
asi que se pregunta la primera vez y se recuerda por NIF.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout,
)

from .clientes import DESGLOSE, TOTAL

OPCIONES = [
    (TOTAL, "Minorista en recargo de equivalencia",
     "No presenta modelo 303 y no deduce el IVA. Cada gasto se registra por el "
     "TOTAL de la factura (base + IVA + recargo), sin desglose."),
    (DESGLOSE, "Mayorista en estimación directa",
     "Registra el IVA y el recargo por separado, con su desglose normal, como "
     "cualquier otra factura."),
]


class DialogoRecargo(QDialog):
    def __init__(self, cliente: str, cuantas: int, parent=None,
                 elegido: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Facturas con recargo de equivalencia")
        self.setMinimumWidth(560)
        raiz = QVBoxLayout(self)

        intro = QLabel(
            f"En este lote hay <b>{cuantas} factura(s) con recargo de "
            f"equivalencia</b>" + (f" de <b>{cliente}</b>" if cliente else "")
            + ".<br>¿Cómo se registran las suyas?")
        intro.setWordWrap(True)
        raiz.addWidget(intro)

        self.grupo = QButtonGroup(self)
        for i, (valor, titulo, explicacion) in enumerate(OPCIONES):
            boton = QRadioButton(titulo)
            boton.setChecked(valor == elegido if elegido else i == 0)
            self.grupo.addButton(boton, i)
            raiz.addWidget(boton)
            detalle = QLabel("      " + explicacion)
            detalle.setObjectName("textoSuave")
            detalle.setWordWrap(True)
            raiz.addWidget(detalle)

        nota = QLabel(
            "Se recuerda para este cliente. Se puede cambiar cuando quiera en "
            "el desplegable de arriba: el lote se rehace al momento, sin volver "
            "a leer las facturas.")
        nota.setObjectName("textoSuave")
        nota.setWordWrap(True)
        raiz.addWidget(nota)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
                                   parent=self)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        raiz.addWidget(botones)

    def elegido(self) -> str:
        i = self.grupo.checkedId()
        return OPCIONES[i][0] if 0 <= i < len(OPCIONES) else ""
