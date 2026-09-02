"""Lo poco que hay que decir antes de escanear.

Ni eso hace falta: si no se pone cliente, el PDF nace en "Sin identificar" y se
muda solo a la carpeta del cliente en cuanto el programa lo averigua por el NIF
que se repite en las facturas.

El tipo es SOLO para archivar y nombrar: cada factura la sigue clasificando el
programa por el NIF (una venta colada en un taco de gastos se detecta igual).

La calidad (color y ppp) se elige aqui porque cambia de un taco a otro: unas
facturas amarillentas de gasolinera piden mas que un albaran limpio. OJO: esto
NO cambia lo que cuesta Gemini (eso es «Calidad de lectura», en Configuracion);
esto cambia lo que tarda el escaner y lo que ocupa el PDF.
"""

from __future__ import annotations

import os
from typing import List, Tuple

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QSpinBox, QVBoxLayout,
)

from . import ajustes
from .escaner import DPI_POR_DEFECTO, carpeta_por_defecto

# (etiqueta, valor). El orden va de lo mas rapido a lo mas fiel.
COLORES = [
    ("Blanco y negro — lo más rápido y ligero", "bn"),
    ("Escala de grises — recomendado para facturas", "grises"),
    ("Color", "color"),
]
CALIDADES = [
    ("75 ppp — muy rápido, solo si la letra es grande", 75),
    ("150 ppp — rápido", 150),
    ("200 ppp — recomendado", 200),
    ("300 ppp — lento, para letra muy pequeña o borrosa", 300),
]


class DialogoEscaneo(QDialog):
    def __init__(self, escaneres: List[Tuple[str, str]], clientes: List[str],
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escanear facturas")
        self.setMinimumWidth(470)
        raiz = QVBoxLayout(self)

        formulario = QFormLayout()
        self.combo_escaner = QComboBox()
        for device_id, nombre in escaneres:
            self.combo_escaner.addItem(nombre, device_id)
        i = self.combo_escaner.findData(ajustes.leer("escaner_id", ""))
        if i >= 0:
            self.combo_escaner.setCurrentIndex(i)
        formulario.addRow("Escáner:", self.combo_escaner)

        self.combo_cliente = QComboBox()
        self.combo_cliente.setEditable(True)
        self.combo_cliente.addItems(clientes)
        self.combo_cliente.setCurrentText("")
        self.combo_cliente.lineEdit().setPlaceholderText(
            "Déjelo vacío y lo detecta el programa")
        self.combo_cliente.setToolTip(
            "Si lo deja vacío, el PDF se guarda como «Sin identificar» y se "
            "muda solo a la carpeta del cliente cuando el programa lo detecta "
            "por el NIF de las facturas.")
        formulario.addRow("Cliente:", self.combo_cliente)

        self.combo_tipo = QComboBox()
        self.combo_tipo.addItem("Gastos", "gastos")
        self.combo_tipo.addItem("Ingresos", "ingresos")
        formulario.addRow("Tipo:", self.combo_tipo)

        self.combo_color = QComboBox()
        for etiqueta, valor in COLORES:
            self.combo_color.addItem(etiqueta, valor)
        self._elegir(self.combo_color, ajustes.leer("escaneo_color", "grises"))
        self.combo_color.setToolTip(
            "En escala de grises se escanea antes y el PDF pesa un tercio.\n"
            "El color solo hace falta si necesita ver sellos o marcas de color.")
        formulario.addRow("Color:", self.combo_color)

        self.combo_calidad = QComboBox()
        for etiqueta, valor in CALIDADES:
            self.combo_calidad.addItem(etiqueta, valor)
        self._elegir(self.combo_calidad,
                     int(ajustes.leer("escaneo_dpi", DPI_POR_DEFECTO)))
        self.combo_calidad.setToolTip(
            "Más ppp = el escáner tarda más y el PDF pesa más.\n"
            "No cambia lo que cuesta leer las facturas con Gemini.")
        formulario.addRow("Calidad:", self.combo_calidad)

        self.spin_hojas = QSpinBox()
        self.spin_hojas.setRange(0, 500)
        self.spin_hojas.setSpecialValueText("no las he contado")
        self.spin_hojas.setValue(0)
        self.spin_hojas.setToolTip(
            "Si dice cuántas hojas pone, el programa avisa si salen menos:\n"
            "el alimentador arrastra a veces dos hojas pegadas y esa factura\n"
            "no se registraría (no da ningún error, simplemente no está).")
        formulario.addRow("Hojas que pone:", self.spin_hojas)

        self.chk_alimentador = QCheckBox("Usar el alimentador (taco de hojas)")
        self.chk_alimentador.setChecked(ajustes.leer("escaneo_alimentador", True))
        formulario.addRow("", self.chk_alimentador)
        self.chk_duplex = QCheckBox("Escanear las dos caras")
        self.chk_duplex.setChecked(ajustes.leer("escaneo_duplex", False))
        formulario.addRow("", self.chk_duplex)
        raiz.addLayout(formulario)

        carpeta = ajustes.leer("carpeta_escaneos", carpeta_por_defecto())
        aviso = QLabel(
            f"El PDF se guardará en {os.path.join(carpeta, '<CLIENTE>')} con el "
            f"nombre CLIENTE_tipo_fecha.pdf y entrará solo en el lote.\n"
            f"Sin cliente, se guarda como «Sin identificar» y se coloca solo "
            f"cuando el programa averigüe de quién es.")
        aviso.setObjectName("textoSuave")
        aviso.setWordWrap(True)
        raiz.addWidget(aviso)

        botones = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        botones.button(QDialogButtonBox.Ok).setText("Escanear")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        raiz.addWidget(botones)

    @staticmethod
    def _elegir(combo: QComboBox, valor) -> None:
        i = combo.findData(valor)
        if i >= 0:
            combo.setCurrentIndex(i)

    def valores(self) -> dict:
        return {
            "device_id": self.combo_escaner.currentData() or "",
            "cliente": self.combo_cliente.currentText().strip(),
            "tipo": self.combo_tipo.currentData(),
            "alimentador": self.chk_alimentador.isChecked(),
            "duplex": self.chk_duplex.isChecked(),
            "modo_color": self.combo_color.currentData(),
            "hojas": self.spin_hojas.value(),
            "dpi": self.combo_calidad.currentData(),
            "carpeta": ajustes.leer("carpeta_escaneos", carpeta_por_defecto()),
        }

    def recordar(self) -> None:
        """Lo elegido se queda puesto para el siguiente escaneo."""
        v = self.valores()
        for clave, valor in (("escaner_id", v["device_id"]),
                             ("escaneo_alimentador", v["alimentador"]),
                             ("escaneo_duplex", v["duplex"]),
                             ("escaneo_color", v["modo_color"]),
                             ("escaneo_dpi", v["dpi"])):
            ajustes.guardar(clave, valor)
