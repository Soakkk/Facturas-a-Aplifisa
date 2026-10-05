"""Como se registran las facturas con recargo de equivalencia de este cliente.

Dos clientes pueden comprar los dos con recargo y llevarse de forma distinta,
porque lo que manda es SU regimen, no la factura:

  - MINORISTA en recargo: no presenta el 303 y no deduce IVA, asi que cada
    gasto se registra por el TOTAL de la factura, sin desglose.
  - MAYORISTA en estimacion directa: SI registra el IVA y el recargo, cada uno
    en su sitio, con el desglose normal.

El programa no puede adivinarlo de la factura (las dos traen recargo impreso),
asi que se pregunta la primera vez y se recuerda por NIF.

El minorista en recargo registra asi TODAS sus compras, tambien las que no
traen recargo impreso (telefono, reparaciones, publicidad...): no paga ni
deduce IVA.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout,
)

from .clientes import DESGLOSE, EXENTO, TOTAL

OPCIONES = [
    (TOTAL, "Minorista en recargo de equivalencia",
     "No presenta modelo 303 y no deduce el IVA. Cada gasto se registra por el "
     "TOTAL de la factura (base + IVA + recargo), sin desglose."),
    (DESGLOSE, "Mayorista en estimación directa (o régimen normal)",
     "Registra el IVA y el recargo por separado, con su desglose normal, como "
     "cualquier otra factura."),
    (EXENTO, "Actividad exenta, sin derecho a deducir",
     "Médicos, academias, seguros… (art. 20 de la Ley del IVA): no deduce el "
     "IVA de sus compras (art. 94). Cada gasto se registra por el TOTAL de la "
     "factura, sin desglose."),
]


class DialogoRecargo(QDialog):
    def __init__(self, cliente: str, cuantas: int, parent=None,
                 elegido: str = "", sin_recargo: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Facturas con recargo de equivalencia" if cuantas
                            else "Régimen de IVA del cliente")
        self.setMinimumWidth(560)
        raiz = QVBoxLayout(self)

        de_quien = f" de <b>{cliente}</b>" if cliente else ""
        if cuantas:
            texto = (f"En este lote hay <b>{cuantas} factura(s) con recargo de "
                     f"equivalencia</b>{de_quien}.<br>¿Cómo se registran las "
                     "suyas?")
        else:
            # Desde el menú: el cliente puede estar en recargo aunque ninguna
            # factura del lote lo lleve impreso (teléfono, reparaciones…).
            texto = (f"¿Cómo se registran las compras{de_quien}?<br>En "
                     "recargo de equivalencia o con actividad exenta van todas "
                     "por el total, también las que no traen recargo impreso.")
        intro = QLabel(texto)
        intro.setWordWrap(True)
        raiz.addWidget(intro)

        self.grupo = QButtonGroup(self)
        for i, (valor, titulo, explicacion) in enumerate(OPCIONES):
            boton = QRadioButton(titulo)
            boton.setChecked(valor == elegido if elegido else i == 0)
            if sin_recargo and valor == TOTAL:
                # Una sociedad no puede estar en recargo (art. 148).
                boton.setEnabled(False)
                explicacion += (" No es posible para una sociedad (art. 148 "
                                "de la Ley del IVA).")
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
