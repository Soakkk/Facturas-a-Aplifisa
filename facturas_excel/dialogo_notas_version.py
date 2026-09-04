"""Ventana sencilla de novedades de la versión instalada."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from . import notas_version


class DialogoNotasVersion(QDialog):
    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.version = version
        self.setWindowTitle(f"Novedades de Facturas a Aplifisa v{version}")
        self.resize(620, 430)
        layout = QVBoxLayout(self)
        texto = QTextBrowser()
        texto.setOpenExternalLinks(True)
        texto.setHtml(notas_version.contenido(version))
        layout.addWidget(texto)
        botones = QDialogButtonBox(QDialogButtonBox.Close)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

    def done(self, resultado):
        notas_version.marcar_vistas(self.version)
        super().done(resultado)
