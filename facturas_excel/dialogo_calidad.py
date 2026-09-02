"""Con qué calidad se le manda cada factura a Gemini.

Esto es lo UNICO que cambia el coste: Gemini cobra por los puntos de la imagen
(la parte en cuadros de 768x768 y cobra cada uno), asi que a mas puntos por
pulgada, mas caro. El color del escaneo o lo que pese el PDF no cambian nada.

A menos calidad se ahorra, pero si la letra no se lee la factura sale mal y
corregirla a mano cuesta mucho mas que unos centimos. Por eso el dialogo enseña
las dos cosas a la vez: lo que se ahorra y lo que se arriesga.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout,
)

from . import ajustes, costes

PPP_POR_DEFECTO = 150

# (ppp, titulo, explicacion)
OPCIONES = [
    (100, "Ahorro", "Solo para facturas con letra grande y bien impresas. "
                    "Si la letra es pequeña, se leerá mal."),
    (150, "Normal (recomendado)", "Es con lo que se han leído bien todas las "
                                  "facturas hasta ahora, incluidas las de gasolinera."),
    (200, "Alta", "Para facturas con letra pequeña o algo borrosas. "
                  "Cuesta el doble que la normal."),
    (300, "Máxima", "Para facturas muy malas o escritas muy pequeñas. "
                    "Cuesta más del triple que la normal."),
]


class DialogoCalidad(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calidad de lectura y coste")
        self.setMinimumWidth(560)
        raiz = QVBoxLayout(self)

        intro = QLabel(
            "Con qué detalle se le manda cada factura a Gemini para que la lea.\n"
            "Es lo único que cambia lo que cuesta: el color del escáner y el "
            "tamaño del PDF no influyen.")
        intro.setWordWrap(True)
        raiz.addWidget(intro)

        actual = int(ajustes.leer("lectura_ppp", PPP_POR_DEFECTO))
        self.grupo = QButtonGroup(self)
        for ppp, titulo, explicacion in OPCIONES:
            boton = QRadioButton(f"{titulo} — {ppp} ppp   ·   "
                                 f"{self._coste_texto(ppp)}")
            boton.setChecked(ppp == actual)
            self.grupo.addButton(boton, ppp)
            raiz.addWidget(boton)
            detalle = QLabel("      " + explicacion)
            detalle.setObjectName("textoSuave")
            detalle.setWordWrap(True)
            raiz.addWidget(detalle)

        modelo = costes.ultimo_modelo()
        pie = QLabel(
            ("Precios del modelo que usó la última vez: " + modelo
             if modelo else
             "Aún no se ha leído ningún lote: los precios son una estimación "
             "con la tarifa más cara.")
            + f"\nGasto de este mes: {costes._eur(costes.gasto_del_mes())} "
              f"de {costes._eur(costes.tope())}.")
        pie.setObjectName("textoSuave")
        pie.setWordWrap(True)
        raiz.addWidget(pie)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
                                   parent=self)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        raiz.addWidget(botones)

    @staticmethod
    def _coste_texto(ppp: int) -> str:
        cien = costes.coste_por_factura(ppp) * 100
        return (f"{costes._eur(costes.coste_por_factura(ppp))} por factura   "
                f"({costes._eur(cien)} cada 100)")

    def ppp(self) -> int:
        return self.grupo.checkedId()

    def guardar(self) -> None:
        ajustes.guardar("lectura_ppp", self.ppp())
