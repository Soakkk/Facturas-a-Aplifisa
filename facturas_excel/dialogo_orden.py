"""En que orden salen los apuntes al Excel.

Importa mas de lo que parece: Aplifisa RENUMERA las facturas recibidas al
importarlas (1, 2, 3...), asi que el orden del Excel es el que decide con que
numero queda registrada cada factura.

  - ORDEN DEL PDF: el apunte nº 3 es la hoja 3 del escaneo. Es lo que hace falta
    en un requerimiento de Hacienda, donde el listado tiene que poder seguirse
    contra el taco de papel numerado a mano.
  - POR FECHA: lo normal en un registro trimestral.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout,
)

from . import ajustes

PDF = "pdf"
FECHA = "fecha"

OPCIONES = [
    (PDF, "En el orden del PDF escaneado",
     "El apunte nº 3 será la hoja 3 del escaneo. Es lo que hace falta en un "
     "requerimiento: el listado de Aplifisa se puede seguir contra el taco de "
     "papel."),
    (FECHA, "Por fecha de factura",
     "De la más antigua a la más reciente. Lo normal para el registro "
     "trimestral."),
]


class DialogoOrden(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Orden de los apuntes")
        self.setMinimumWidth(520)
        raiz = QVBoxLayout(self)

        intro = QLabel(
            "Aplifisa numera las facturas recibidas por el orden en que entran, "
            "así que este orden es el que tendrán en su registro.")
        intro.setWordWrap(True)
        raiz.addWidget(intro)

        guardado = ajustes.leer("orden_export", PDF)
        self.grupo = QButtonGroup(self)
        for i, (valor, titulo, explicacion) in enumerate(OPCIONES):
            boton = QRadioButton(titulo)
            boton.setChecked(valor == guardado)
            self.grupo.addButton(boton, i)
            raiz.addWidget(boton)
            detalle = QLabel("      " + explicacion)
            detalle.setObjectName("textoSuave")
            detalle.setWordWrap(True)
            raiz.addWidget(detalle)
        if self.grupo.checkedId() < 0:
            self.grupo.button(0).setChecked(True)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
                                   parent=self)
        botones.button(QDialogButtonBox.Ok).setText("Exportar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        raiz.addWidget(botones)

    def orden(self) -> str:
        i = self.grupo.checkedId()
        return OPCIONES[i][0] if 0 <= i < len(OPCIONES) else PDF

    def recordar(self) -> None:
        ajustes.guardar("orden_export", self.orden())
