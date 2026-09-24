"""Configuración de los modelos de lectura y de la doble lectura."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QRadioButton, QVBoxLayout,
)

from . import ajustes, costes
from .extraccion import (
    DOBLE_DUDOSAS, DOBLE_NO, DOBLE_SIEMPRE, MODELO_PRINCIPAL, MODELO_RESPALDO,
    MODELOS_CONOCIDOS, modelos_configurados, modo_doble_lectura,
)

TEXTOS_MODO = {
    DOBLE_SIEMPRE: ("Siempre (recomendado)",
                    "Cada hoja la leen los dos modelos y se comparan dato a "
                    "dato. Cuesta aproximadamente el doble."),
    DOBLE_DUDOSAS: ("Solo las dudosas",
                    "La segunda lectura solo se pide si la primera no cuadra, "
                    "trae un NIF inválido o su confianza no es alta."),
    DOBLE_NO: ("No",
               "Una sola lectura. Las facturas correctas quedan «Sin "
               "verificar»."),
}


class DialogoModelos(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modelos de lectura")
        self.setMinimumWidth(520)
        capa = QVBoxLayout(self)

        intro = QLabel(
            "Los modelos van fijados por su nombre: nunca se usa un alias "
            "«latest» que cambie solo de modelo y de precio. Si el principal "
            "deja de estar disponible, se lee con el de respaldo y se avisa.")
        intro.setWordWrap(True)
        capa.addWidget(intro)

        principal, *resto = modelos_configurados() + [""]
        formulario = QFormLayout()
        self.combo_principal = self._combo(principal or MODELO_PRINCIPAL)
        self.combo_respaldo = self._combo(resto[0] if resto else MODELO_RESPALDO)
        formulario.addRow("Modelo principal:", self.combo_principal)
        formulario.addRow("Respaldo y segunda lectura:", self.combo_respaldo)
        capa.addLayout(formulario)

        grupo = QGroupBox("Doble lectura")
        capa_grupo = QVBoxLayout(grupo)
        self.botones_modo = QButtonGroup(self)
        actual = modo_doble_lectura()
        for modo, (titulo, ayuda) in TEXTOS_MODO.items():
            boton = QRadioButton(titulo)
            boton.setProperty("modo", modo)
            boton.setChecked(modo == actual)
            self.botones_modo.addButton(boton)
            capa_grupo.addWidget(boton)
            explicacion = QLabel(ayuda)
            explicacion.setWordWrap(True)
            explicacion.setStyleSheet("color: #5D7084; padding-left: 22px;")
            capa_grupo.addWidget(explicacion)
        capa.addWidget(grupo)

        tarifas = QGroupBox("Tarifas (dólares por millón de tokens)")
        capa_tarifas = QFormLayout(tarifas)
        nota = QLabel(
            "Solo para calcular el gasto. Si un modelo no tiene tarifa, el "
            "gasto se estima y la barra inferior lo indica. Deje 0 para usar "
            "la tabla del programa.")
        nota.setWordWrap(True)
        capa_tarifas.addRow(nota)
        self.tarifas = {}
        propias = ajustes.leer("precios_modelos", {}) or {}
        for modelo in dict.fromkeys(MODELOS_CONOCIDOS):
            entrada, salida = self._spin(), self._spin()
            valor = propias.get(modelo) if isinstance(propias, dict) else None
            if valor:
                entrada.setValue(float(valor[0]))
                salida.setValue(float(valor[1]))
            fila = QHBoxLayout()
            fila.addWidget(QLabel("entrada"))
            fila.addWidget(entrada)
            fila.addWidget(QLabel("salida"))
            fila.addWidget(salida)
            (_p, conocido) = costes.precio_de(modelo)
            capa_tarifas.addRow(f"{modelo}{'' if conocido else ' (sin tarifa)'}:",
                                fila)
            self.tarifas[modelo] = (entrada, salida)
        capa.addWidget(tarifas)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)

    @staticmethod
    def _combo(valor: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        for modelo in MODELOS_CONOCIDOS:
            combo.addItem(modelo)
        combo.setCurrentText(valor)
        return combo

    @staticmethod
    def _spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(3)
        spin.setRange(0, 1000)
        spin.setSingleStep(0.05)
        return spin

    def modo(self) -> str:
        boton = self.botones_modo.checkedButton()
        return boton.property("modo") if boton else DOBLE_SIEMPRE

    def guardar(self) -> str:
        """Guarda lo elegido y devuelve un resumen para la banda de avisos."""
        principal = self.combo_principal.currentText().strip() or MODELO_PRINCIPAL
        respaldo = self.combo_respaldo.currentText().strip()
        if "latest" in principal:
            principal = MODELO_PRINCIPAL
        if "latest" in respaldo or respaldo == principal:
            respaldo = ""
        ajustes.guardar("modelo_principal", principal)
        ajustes.guardar("modelo_respaldo", respaldo)
        ajustes.guardar("doble_lectura", self.modo())
        precios = {m: [e.value(), s.value()] for m, (e, s) in self.tarifas.items()
                   if e.value() or s.value()}
        ajustes.guardar("precios_modelos", precios)
        return (f"Modelos guardados: {principal}"
                + (f" y {respaldo} de respaldo" if respaldo else " sin respaldo")
                + f". Doble lectura: {TEXTOS_MODO[self.modo()][0].lower()}.")
