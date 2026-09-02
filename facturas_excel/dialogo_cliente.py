"""De quien son las facturas del lote.

Normalmente se sabe solo (el NIF que sale en todas), pero hay un caso en el que
no hay forma de adivinarlo: un taco de facturas de un mismo proveedor a un mismo
cliente. Ahi las dos partes salen exactamente las mismas veces y elegir al azar
sale caro: el proveedor se registraria como cliente y todas las facturas del
reves (gastos por ventas y la contraparte cambiada).

Asi que se pregunta, se recuerda la respuesta, y a la otra parte se le apunta
como proveedor. La proxima vez ya no hace falta preguntar.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout,
)

from .procesar import Candidato


class DialogoCliente(QDialog):
    def __init__(self, candidatos: List[Candidato], parent=None,
                 elegido: str = ""):
        super().__init__(parent)
        self.setWindowTitle("¿De quién son estas facturas?")
        self.setMinimumWidth(560)
        self._candidatos = candidatos
        raiz = QVBoxLayout(self)

        intro = QLabel(
            "El programa no puede deducirlo solo: las dos partes salen las "
            "mismas veces en todo el lote.\n"
            "Marque cuál es SU cliente (el de la asesoría). La otra parte "
            "pasará a ser la contraparte de cada factura.")
        intro.setWordWrap(True)
        raiz.addWidget(intro)

        self.grupo = QButtonGroup(self)
        for i, c in enumerate(candidatos):
            boton = QRadioButton(f"{c.nombre or '(sin nombre)'}   ·   "
                                 f"{c.nif or 'sin NIF'}")
            boton.setChecked(c.nif == elegido if elegido else i == 0)
            self.grupo.addButton(boton, i)
            raiz.addWidget(boton)
            detalle = QLabel(f"      Sale en {c.veces} factura(s) del lote; "
                             f"{c.papel}." + self._pistas(c))
            detalle.setObjectName("textoSuave")
            detalle.setWordWrap(True)
            raiz.addWidget(detalle)

        nota = QLabel(
            "Se recordará: la próxima vez que aparezca este NIF, el programa ya "
            "sabrá que es su cliente y no volverá a preguntar.")
        nota.setObjectName("textoSuave")
        nota.setWordWrap(True)
        raiz.addWidget(nota)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
                                   parent=self)
        botones.button(QDialogButtonBox.Ok).setText("Es este")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        raiz.addWidget(botones)

    @staticmethod
    def _pistas(c: Candidato) -> str:
        if c.cliente_confirmado:
            return "  Ya lo marcó como cliente suyo."
        if c.proveedor_conocido:
            return "  Le consta como proveedor de otras veces."
        return ""

    def elegido(self) -> Optional[Candidato]:
        i = self.grupo.checkedId()
        return self._candidatos[i] if 0 <= i < len(self._candidatos) else None
