"""Si el cliente esta en estimacion directa: como van sus apuntes a Aplifisa.

Aplifisa marca cada apunte importado como «IRPF/IVA» o «Sólo IVA», y un
cliente en estimacion directa necesita los suyos como «IRPF/IVA» para que
cuenten en su IRPF (si no, habia que cambiarlos a mano uno a uno). Al
importar lo decide solo la columna Base IRPF del Excel (ver
exportar.datos_para_aplifisa).

El programa no puede saberlo por las facturas, asi que se pregunta una vez
por cliente (al exportar, si aun no se sabe) y se recuerda por su NIF. Una
sociedad no tributa por el IRPF: a ella no se le pregunta.
"""

from __future__ import annotations

import html

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from .clientes import DIRECTA, OTRO

TITULO_DIRECTA = "Sí, estimación directa (IRPF/IVA)"
TITULO_OTRO = "No: módulos u otro (Sólo IVA)"


def texto_tipo_operacion(directa: bool, sin_cliente: bool = False) -> str:
    """La línea que dice, al exportar, cómo entrarán los apuntes."""
    if directa:
        return "Tipo de operación en Aplifisa: IRPF/IVA (estimación directa)"
    if sin_cliente:
        return ("Tipo de operación en Aplifisa: Sólo IVA (sin el NIF del "
                "cliente no se sabe si está en estimación directa)")
    return "Tipo de operación en Aplifisa: Sólo IVA"


class DialogoIrpf(QDialog):
    def __init__(self, cliente: str, parent=None, elegido: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Régimen de IRPF del cliente")
        self.setMinimumWidth(520)
        self._elegido = ""
        raiz = QVBoxLayout(self)

        quien = f"<b>{html.escape(cliente)}</b>" if cliente else "este cliente"
        pregunta = QLabel(f"¿Está {quien} en estimación directa? (sus apuntes "
                          "irán como IRPF/IVA)")
        pregunta.setWordWrap(True)
        raiz.addWidget(pregunta)

        detalle = QLabel(
            "En Aplifisa, los ingresos y gastos de un cliente en estimación "
            "directa (normal o simplificada) tienen que ir como «IRPF/IVA» "
            "para que cuenten en su IRPF; los de módulos, como «Sólo IVA». "
            "Las facturas con retención llevan su IRPF igual que siempre.")
        detalle.setObjectName("textoSuave")
        detalle.setWordWrap(True)
        raiz.addWidget(detalle)

        nota = QLabel("Se recuerda para este cliente. Se puede cambiar cuando "
                      "quiera en Configuración → Régimen de IRPF de este "
                      "cliente.")
        nota.setObjectName("textoSuave")
        nota.setWordWrap(True)
        raiz.addWidget(nota)

        # Cada respuesta, su botón (sin el «Aceptar» de siempre). ActionRole:
        # la caja no cierra sola el diálogo (con «No» lo daría por cancelado).
        botones = QDialogButtonBox(parent=self)
        self.boton_directa = botones.addButton(TITULO_DIRECTA,
                                               QDialogButtonBox.ActionRole)
        self.boton_otro = botones.addButton(TITULO_OTRO,
                                            QDialogButtonBox.ActionRole)
        cancelar = botones.addButton(QDialogButtonBox.Cancel)
        self.boton_directa.clicked.connect(lambda: self._elegir(DIRECTA))
        self.boton_otro.clicked.connect(lambda: self._elegir(OTRO))
        botones.rejected.connect(self.reject)
        # Desde Configuración, lo que ya tenía, a mano para el Intro. La
        # primera vez no hay nada que proponer: el Intro cancela (no se
        # exporta). Sin esto el foco caía en «Sí» y Qt lo daba por pulsado
        # con el Intro: el cliente quedaba en directa sin que nadie lo dijera.
        actual = {DIRECTA: self.boton_directa,
                  OTRO: self.boton_otro}.get(elegido, cancelar)
        actual.setDefault(True)
        actual.setFocus()
        raiz.addWidget(botones)

    def _elegir(self, regimen: str) -> None:
        self._elegido = regimen
        self.accept()

    def elegido(self) -> str:
        """DIRECTA, OTRO, o "" si se cerró sin elegir."""
        return self._elegido if self.result() == QDialog.Accepted else ""
