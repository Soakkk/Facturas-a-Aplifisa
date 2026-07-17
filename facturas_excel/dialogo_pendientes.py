"""Panel «Para mejorar el programa»: lo que hace falta saber, y un hueco para
que el usuario conteste sin salir de la aplicacion.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit,
    QTextBrowser, QVBoxLayout,
)

from . import pendientes


class DialogoPendientes(QDialog):
    def __init__(self, version: str, parent=None, al_arrancar: bool = False):
        super().__init__(parent)
        self.version = version
        self.setWindowTitle("Para mejorar el programa")
        self.resize(760, 640)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(18, 16, 18, 14)
        raiz.setSpacing(10)

        titulo = QLabel("Para mejorar el programa")
        titulo.setObjectName("tituloSeccion")
        raiz.addWidget(titulo)
        sub = QLabel(f"Versión {version}  ·  lo que necesito saber para seguir "
                     f"afinándolo con tus casos reales")
        sub.setObjectName("textoSuave")
        sub.setWordWrap(True)
        raiz.addWidget(sub)

        self.visor = QTextBrowser()
        self.visor.setOpenExternalLinks(True)
        texto = pendientes.leer_pendientes()
        if texto:
            self.visor.setMarkdown(texto)
        else:
            self.visor.setPlainText("(nada pendiente en esta versión)")
        raiz.addWidget(self.visor, 3)

        etiqueta = QLabel("Tus notas  ·  se guardan en tu equipo y se leen en la "
                          "próxima sesión de trabajo")
        etiqueta.setObjectName("textoSuave")
        raiz.addWidget(etiqueta)
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(pendientes.leer_notas())
        raiz.addWidget(self.editor, 2)

        fila = QHBoxLayout()
        self.chk_no_mostrar = QCheckBox(f"No volver a mostrarlo en la v{version}")
        self.chk_no_mostrar.setChecked(al_arrancar)
        fila.addWidget(self.chk_no_mostrar)
        fila.addStretch()
        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        botones.button(QDialogButtonBox.Save).setText("Guardar notas")
        botones.button(QDialogButtonBox.Close).setText("Cerrar")
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)
        fila.addWidget(botones)
        raiz.addLayout(fila)

        self.ruta = QLabel(pendientes.ruta_notas())
        self.ruta.setObjectName("textoSuave")
        self.ruta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        raiz.addWidget(self.ruta)

    def _guardar(self):
        pendientes.guardar_notas(self.editor.toPlainText())
        self.accept()

    def closeEvent(self, ev):
        self._recordar_visto()
        super().closeEvent(ev)

    def done(self, resultado):
        self._recordar_visto()
        super().done(resultado)

    def _recordar_visto(self):
        if self.chk_no_mostrar.isChecked():
            pendientes.marcar_visto(self.version)
