"""Configuración de los modelos de lectura y de la doble lectura."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QPushButton,
    QRadioButton, QVBoxLayout,
)

from . import ajustes, claves, costes
from .extraccion import (
    DOBLE_DUDOSAS, DOBLE_NO, DOBLE_SIEMPRE, ESFUERZO_CLAUDE_POR_DEFECTO,
    MODELO_CLAUDE, MODELO_PRINCIPAL, MODELO_RESPALDO, MODELOS_CONOCIDOS,
    PROVEEDOR_CLAUDE, PROVEEDOR_GEMINI, esfuerzo_claude, modelos_gemini,
    modo_doble_lectura, proveedor_lectura,
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

# Quién lee las facturas: el desplegable de arriba del todo.
TEXTOS_PROVEEDOR = {
    PROVEEDOR_GEMINI: ("Gemini (como hasta ahora)",
                       "Lee Gemini con los modelos de abajo, exactamente como "
                       "hasta ahora."),
    PROVEEDOR_CLAUDE: ("Claude Opus 5.5 + Gemini (prueba)",
                       f"La primera lectura la hace Claude Opus 5.5 "
                       f"({MODELO_CLAUDE}) con su API key; la segunda, y el "
                       "respaldo si Claude falla, el Gemini principal de abajo "
                       "con la API key de Gemini. Coste orientativo: unos "
                       "0,05 € por hoja de Claude (con esfuerzo medio) más la "
                       "lectura de Gemini. Los recuadros de «¿De dónde sale?» "
                       "los sigue pidiendo a Gemini."),
}

# Cuánto piensa Claude antes de contestar (en Opus 5.5 no se puede apagar).
TEXTOS_ESFUERZO = {
    "low": "Bajo (más barato y rápido)",
    "medium": "Medio (recomendado)",
    "high": "Alto (más detallado, más caro y lento)",
}


def pedir_api_key_claude(parent=None) -> bool:
    """Pide la API key de Claude y la guarda en el almacén seguro de Windows.
    Devuelve si se ha guardado una."""
    actual = claves.leer_api_key_claude() or ""
    pista = ("•••" + actual[-4:]) if actual else "(no configurada)"
    texto, ok = QInputDialog.getText(
        parent, "API key de Claude",
        "Pega tu API key de Claude (platform.claude.com → API keys;\n"
        f"empieza por «sk-ant-»).\nActual: {pista}")
    if ok and texto.strip():
        claves.guardar_api_key_claude(texto.strip())
        return True
    return False


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

        # --- Quién lee: Gemini como siempre, o Claude Opus 5.5 + Gemini.
        grupo_ia = QGroupBox("Quién lee las facturas")
        capa_ia = QVBoxLayout(grupo_ia)
        self.combo_proveedor = QComboBox()
        for proveedor, (titulo, _ayuda) in TEXTOS_PROVEEDOR.items():
            self.combo_proveedor.addItem(titulo, proveedor)
        self.combo_proveedor.setCurrentIndex(
            max(0, self.combo_proveedor.findData(proveedor_lectura())))
        capa_ia.addWidget(self.combo_proveedor)
        self.lbl_proveedor = QLabel()
        self.lbl_proveedor.setWordWrap(True)
        self.lbl_proveedor.setStyleSheet("color: #5D7084;")
        capa_ia.addWidget(self.lbl_proveedor)
        fila_claude = QHBoxLayout()
        fila_claude.addWidget(QLabel("Esfuerzo de Claude:"))
        self.combo_esfuerzo = QComboBox()
        for esfuerzo, titulo in TEXTOS_ESFUERZO.items():
            self.combo_esfuerzo.addItem(titulo, esfuerzo)
        self.combo_esfuerzo.setCurrentIndex(
            max(0, self.combo_esfuerzo.findData(esfuerzo_claude())))
        self.combo_esfuerzo.setToolTip(
            "Cuánto razona Claude cada hoja antes de contestar. Más esfuerzo "
            "suele leer mejor las hojas difíciles, pero cuesta más (lo que "
            "piensa se paga como respuesta) y tarda más.")
        fila_claude.addWidget(self.combo_esfuerzo, 1)
        self.btn_clave_claude = QPushButton("API key de Claude…")
        self.btn_clave_claude.clicked.connect(self._pedir_clave_claude)
        fila_claude.addWidget(self.btn_clave_claude)
        capa_ia.addLayout(fila_claude)
        self.lbl_clave_claude = QLabel()
        self.lbl_clave_claude.setWordWrap(True)
        capa_ia.addWidget(self.lbl_clave_claude)
        capa.addWidget(grupo_ia)
        self.combo_proveedor.currentIndexChanged.connect(self._pintar_proveedor)

        principal, *resto = modelos_gemini() + [""]
        formulario = QFormLayout()
        self.combo_principal = self._combo(principal or MODELO_PRINCIPAL)
        self.combo_respaldo = self._combo(resto[0] if resto else MODELO_RESPALDO)
        self.lbl_principal = QLabel("Modelo principal:")
        self.lbl_respaldo = QLabel("Respaldo y segunda lectura:")
        formulario.addRow(self.lbl_principal, self.combo_principal)
        formulario.addRow(self.lbl_respaldo, self.combo_respaldo)
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

        self.chk_localizar = QCheckBox(
            "Señalar en el documento los datos de las facturas en ámbar o rojo")
        self.chk_localizar.setChecked(bool(ajustes.leer("localizar_dudosas", True)))
        self.chk_localizar.setToolTip(
            "Al terminar de leer, se pregunta a Gemini dónde está escrito cada "
            "dato de las facturas dudosas, para verlo con un recuadro. Es una "
            "consulta aparte, más corta que la lectura, y solo para esas.")
        capa.addWidget(self.chk_localizar)

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
        for modelo in dict.fromkeys(MODELOS_CONOCIDOS + [MODELO_CLAUDE]):
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
        self._pintar_proveedor()

    def proveedor(self) -> str:
        return self.combo_proveedor.currentData() or PROVEEDOR_GEMINI

    def _pintar_proveedor(self, *_args) -> None:
        """La explicación de lo elegido, y lo de Claude solo si se elige."""
        claude = self.proveedor() == PROVEEDOR_CLAUDE
        self.lbl_proveedor.setText(TEXTOS_PROVEEDOR[self.proveedor()][1])
        self.combo_esfuerzo.setEnabled(claude)
        # Con Claude, el Gemini principal hace la segunda lectura y el otro
        # solo entra si ese falla.
        self.lbl_principal.setText("Segunda lectura (Gemini):" if claude
                                   else "Modelo principal:")
        self.lbl_respaldo.setText("Respaldo de Gemini:" if claude
                                  else "Respaldo y segunda lectura:")
        if not claude:
            self.lbl_clave_claude.setText("")
        elif claves.leer_api_key_claude():
            self.lbl_clave_claude.setText(
                "<span style='color:#2E7D32'>API key de Claude guardada.</span>")
        else:
            self.lbl_clave_claude.setText(
                "<span style='color:#C62828'>Falta la API key de Claude: pulsa "
                "«API key de Claude…» antes de leer.</span>")

    def _pedir_clave_claude(self) -> None:
        pedir_api_key_claude(self)
        self._pintar_proveedor()

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
        ajustes.guardar("proveedor_lectura", self.proveedor())
        ajustes.guardar("esfuerzo_claude",
                        self.combo_esfuerzo.currentData() or ESFUERZO_CLAUDE_POR_DEFECTO)
        ajustes.guardar("doble_lectura", self.modo())
        ajustes.guardar("localizar_dudosas", self.chk_localizar.isChecked())
        precios = {m: [e.value(), s.value()] for m, (e, s) in self.tarifas.items()
                   if e.value() or s.value()}
        ajustes.guardar("precios_modelos", precios)
        lee = (f"Lee Claude Opus 5.5 y después {principal}"
               if self.proveedor() == PROVEEDOR_CLAUDE
               else f"Modelos guardados: {principal}")
        return (lee
                + (f" y {respaldo} de respaldo" if respaldo else " sin respaldo")
                + f". Doble lectura: {TEXTOS_MODO[self.modo()][0].lower()}.")
