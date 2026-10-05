"""Configuración → Copias de seguridad: ver las copias, hacer una y restaurar."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout,
)

from . import archivo, copias


class DialogoCopias(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Copias de seguridad")
        self.resize(620, 460)
        self.restaurada = ""
        capa = QVBoxLayout(self)
        explicacion = QLabel(
            "Cada día, al abrir el programa, y antes de cada actualización, se "
            "copia lo que el programa recuerda: el registro de facturas (qué "
            "se exportó y dónde está su PDF), los clientes, los proveedores, "
            "las cuentas y sus notas. Se guardan las últimas "
            f"{copias.GUARDAR} en «{copias.CARPETA}», dentro de la carpeta "
            "de documentación. Los PDF no se copian aquí: ya están en esa "
            "carpeta.")
        explicacion.setWordWrap(True)
        capa.addWidget(explicacion)
        self.lista = QListWidget()
        capa.addWidget(self.lista, 1)
        botones = QHBoxLayout()
        self.btn_hacer = QPushButton("Hacer una copia ahora")
        self.btn_hacer.clicked.connect(self._hacer)
        botones.addWidget(self.btn_hacer)
        self.btn_restaurar = QPushButton("Restaurar la elegida…")
        self.btn_restaurar.clicked.connect(self._restaurar)
        botones.addWidget(self.btn_restaurar)
        abrir = QPushButton("Abrir la carpeta")
        abrir.clicked.connect(lambda: archivo.abrir(copias.carpeta()))
        botones.addWidget(abrir)
        botones.addStretch(1)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.accept)
        botones.addWidget(cerrar)
        capa.addLayout(botones)
        self._llenar()

    def _llenar(self) -> None:
        self.lista.clear()
        for copia in copias.listar():
            facturas = ("" if copia.facturas is None
                        else f" · {copia.facturas} factura(s) en el registro")
            motivo = "" if copia.motivo == "diaria" else f" · {copia.motivo}"
            item = QListWidgetItem(
                f"{copia.fecha:%d/%m/%Y %H:%M}{motivo}{facturas} · "
                f"{copia.tamano_legible}")
            item.setData(Qt.UserRole, copia.ruta)
            self.lista.addItem(item)
        if self.lista.count():
            self.lista.setCurrentRow(0)
        self.btn_restaurar.setEnabled(self.lista.count() > 0)

    def _hacer(self) -> None:
        try:
            copias.hacer("a mano")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Copia de seguridad",
                                f"No se pudo hacer la copia:\n{error}")
        self._llenar()

    def _restaurar(self) -> None:
        item = self.lista.currentItem()
        if not item:
            return
        if QMessageBox.question(
                self, "Restaurar copia",
                f"¿Volver a lo que había el {item.text().split(' · ')[0]}?\n\n"
                "Lo que el programa ha apuntado después (facturas exportadas, "
                "clientes, cuentas…) dejará de estar. Antes se hace una copia "
                "de lo de ahora, por si hay que volver atrás.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            copias.restaurar(item.data(Qt.UserRole))
        except Exception as error:      # también los de la base de datos
            QMessageBox.critical(self, "Restaurar copia",
                                 f"No se pudo restaurar:\n{error}")
            self._llenar()
            return
        self.restaurada = item.data(Qt.UserRole)
        QMessageBox.information(
            self, "Restaurar copia",
            "Copia restaurada. Cierre el programa y vuelva a abrirlo para "
            "que todo se vea al día.")
        self._llenar()
