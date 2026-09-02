"""Los textos que hay que configurar UNA VEZ en Aplifisa.

En Aplifisa: Importación de Excel -> «Parametrizar los textos de los Conceptos».
Alli se le dice que el texto GASOLEO es el concepto 628 (G16), etc. Hecho eso,
el Excel puede llevar el texto en vez del codigo y cada apunte entra con su
cuenta Y su subclave, sin tocar nada a mano ni con proveedores nuevos.

Esta ventana enseña la lista y la deja copiada para no tener que teclearla
mirando la pantalla del otro programa.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QDialogButtonBox,
    QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from . import ajustes
from .conceptos import tabla_textos

COLUMNAS = ["Concepto de Aplifisa", "Qué es", "Texto que escribe el programa"]


class DialogoTextos(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Textos de conceptos para Aplifisa")
        self.resize(720, 520)
        raiz = QVBoxLayout(self)

        intro = QLabel(
            "En Aplifisa: <b>Importación de Excel → Parametrizar los textos de "
            "los Conceptos</b>.<br>Para cada línea de abajo: elija el concepto "
            "en el desplegable, deje «IGUAL QUE» y escriba el texto de la "
            "tercera columna.<br>Es cosa de una vez. Después, cada apunte entra "
            "con su cuenta <b>y su subclave</b>, también con proveedores nuevos.")
        intro.setWordWrap(True)
        raiz.addWidget(intro)

        filas = tabla_textos()
        self.tabla = QTableWidget(len(filas), len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        for fila, (etiqueta, descripcion, texto) in enumerate(filas):
            for columna, valor in enumerate((etiqueta, descripcion, texto)):
                item = QTableWidgetItem(valor)
                if columna == 2:
                    fuente = item.font()
                    fuente.setBold(True)
                    item.setFont(fuente)
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        raiz.addWidget(self.tabla, 1)

        self.chk_usar = QCheckBox(
            "Ya lo tengo configurado en Aplifisa: escribir el TEXTO en el Excel")
        self.chk_usar.setToolTip(
            "Mientras esté sin marcar, el Excel lleva el código de la cuenta "
            "(628) y Aplifisa pedirá la subclave a mano la primera vez de cada "
            "proveedor.")
        self.chk_usar.setChecked(bool(ajustes.leer("concepto_texto", False)))
        raiz.addWidget(self.chk_usar)

        copiar = QPushButton("Copiar la lista")
        copiar.clicked.connect(self._copiar)
        raiz.addWidget(copiar, alignment=Qt.AlignLeft)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
                                   parent=self)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        raiz.addWidget(botones)

    def _copiar(self) -> None:
        lineas = ["\t".join(COLUMNAS)]
        lineas += ["\t".join(f for f in fila) for fila in tabla_textos()]
        QApplication.clipboard().setText("\n".join(lineas))

    def guardar(self) -> None:
        ajustes.guardar("concepto_texto", self.chk_usar.isChecked())
