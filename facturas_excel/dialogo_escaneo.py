"""Lo poco que hay que decir antes de escanear: de quien son las facturas y si
son gastos o ingresos. Con eso el PDF se nombra y se archiva solo.

El tipo aqui es SOLO para archivar: cada factura la sigue clasificando el
programa por el NIF (una venta colada en un taco de gastos se detecta igual).
"""

from __future__ import annotations

import os
from typing import List, Tuple

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QVBoxLayout,
)

from . import ajustes
from .escaner import DPI_POR_DEFECTO, carpeta_por_defecto


class DialogoEscaneo(QDialog):
    def __init__(self, escaneres: List[Tuple[str, str]], clientes: List[str],
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escanear facturas")
        self.setMinimumWidth(430)
        raiz = QVBoxLayout(self)

        formulario = QFormLayout()
        self.combo_escaner = QComboBox()
        for device_id, nombre in escaneres:
            self.combo_escaner.addItem(nombre, device_id)
        ultimo = ajustes.leer("escaner_id", "")
        i = self.combo_escaner.findData(ultimo)
        if i >= 0:
            self.combo_escaner.setCurrentIndex(i)
        formulario.addRow("Escáner:", self.combo_escaner)

        self.combo_cliente = QComboBox()
        self.combo_cliente.setEditable(True)
        self.combo_cliente.addItems(clientes)
        self.combo_cliente.setCurrentText("")
        self.combo_cliente.lineEdit().setPlaceholderText(
            "Nombre del cliente (para nombrar y archivar el PDF)")
        formulario.addRow("Cliente:", self.combo_cliente)

        self.combo_tipo = QComboBox()
        self.combo_tipo.addItem("Gastos", "gastos")
        self.combo_tipo.addItem("Ingresos", "ingresos")
        formulario.addRow("Tipo:", self.combo_tipo)

        self.chk_alimentador = QCheckBox("Usar el alimentador (taco de hojas)")
        self.chk_alimentador.setChecked(ajustes.leer("escaneo_alimentador", True))
        formulario.addRow("", self.chk_alimentador)
        self.chk_duplex = QCheckBox("Escanear las dos caras")
        self.chk_duplex.setChecked(ajustes.leer("escaneo_duplex", False))
        formulario.addRow("", self.chk_duplex)
        raiz.addLayout(formulario)

        carpeta = ajustes.leer("carpeta_escaneos", carpeta_por_defecto())
        aviso = QLabel(
            f"El PDF se guardará en:\n{os.path.join(carpeta, '<CLIENTE>')}\n"
            f"con el nombre CLIENTE_tipo_fecha.pdf, y entrará solo en el lote.")
        aviso.setObjectName("textoSuave")
        aviso.setWordWrap(True)
        raiz.addWidget(aviso)

        botones = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        botones.button(QDialogButtonBox.Ok).setText("Escanear")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        raiz.addWidget(botones)

    def valores(self) -> dict:
        return {
            "device_id": self.combo_escaner.currentData() or "",
            "cliente": self.combo_cliente.currentText().strip(),
            "tipo": self.combo_tipo.currentData(),
            "alimentador": self.chk_alimentador.isChecked(),
            "duplex": self.chk_duplex.isChecked(),
            "dpi": int(ajustes.leer("escaneo_dpi", DPI_POR_DEFECTO)),
            "carpeta": ajustes.leer("carpeta_escaneos", carpeta_por_defecto()),
        }

    def recordar(self) -> None:
        """Lo elegido se queda puesto para el siguiente escaneo."""
        v = self.valores()
        ajustes.guardar("escaner_id", v["device_id"])
        ajustes.guardar("escaneo_alimentador", v["alimentador"])
        ajustes.guardar("escaneo_duplex", v["duplex"])
