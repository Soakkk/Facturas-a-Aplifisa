"""Crear o actualizar el expediente de uno o varios clientes y ejercicios."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout,
)

from . import archivo, expediente


class DialogoExpedientes(QDialog):
    def __init__(self, base: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Expedientes por cliente y ejercicio")
        self.resize(640, 520)
        self.base = base
        self.creados = []
        capa = QVBoxLayout(self)
        explicacion = QLabel(
            "Cada expediente reúne en «Nombre — NIF / Ejercicio / Expediente»: "
            "un PDF con todos los gastos, otro con todos los ingresos (con "
            "índice y marcadores), los Excel exportados a Aplifisa y un resumen "
            "con los totales. Al lado queda un ZIP con todo para adjuntar. Los "
            "originales no se tocan; se puede rehacer cuantas veces quiera.")
        explicacion.setWordWrap(True)
        capa.addWidget(explicacion)
        self.lista = QListWidget()
        self.lista.itemDoubleClicked.connect(lambda *_: self._abrir())
        capa.addWidget(self.lista, 1)
        botones = QHBoxLayout()
        todos = QPushButton("Marcar todos")
        todos.clicked.connect(lambda: self._marcar(True))
        botones.addWidget(todos)
        ninguno = QPushButton("Ninguno")
        ninguno.clicked.connect(lambda: self._marcar(False))
        botones.addWidget(ninguno)
        abrir = QPushButton("Abrir carpeta")
        abrir.clicked.connect(self._abrir)
        botones.addWidget(abrir)
        botones.addStretch(1)
        self.btn_crear = QPushButton("Crear o actualizar")
        self.btn_crear.setObjectName("primario")
        self.btn_crear.clicked.connect(self._crear)
        botones.addWidget(self.btn_crear)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.accept)
        botones.addWidget(cerrar)
        capa.addLayout(botones)
        self.ejercicios = expediente.listar(base)
        for e in self.ejercicios:
            existe = os.path.isdir(expediente.carpeta_expediente(
                base, e.carpeta_cliente, e.ejercicio))
            item = QListWidgetItem(e.etiqueta + ("  · ya creado" if existe else ""))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.lista.addItem(item)
        if not self.ejercicios:
            self.lista.addItem("Todavía no hay documentos archivados por cliente.")
            self.btn_crear.setEnabled(False)

    def _marcar(self, valor: bool) -> None:
        for i in range(len(self.ejercicios)):
            self.lista.item(i).setCheckState(Qt.Checked if valor else Qt.Unchecked)

    def _abrir(self) -> None:
        fila = self.lista.currentRow()
        if 0 <= fila < len(self.ejercicios):
            e = self.ejercicios[fila]
            carpeta = expediente.carpeta_expediente(self.base, e.carpeta_cliente, e.ejercicio)
            archivo.abrir(carpeta if os.path.isdir(carpeta) else os.path.dirname(carpeta))

    def _crear(self) -> None:
        elegidos = [e for i, e in enumerate(self.ejercicios)
                    if self.lista.item(i).checkState() == Qt.Checked]
        if not elegidos and 0 <= self.lista.currentRow() < len(self.ejercicios):
            elegidos = [self.ejercicios[self.lista.currentRow()]]
        if not elegidos:
            QMessageBox.information(self, "Expedientes",
                                    "Marque los clientes y ejercicios que quiera.")
            return
        errores = []
        for e in elegidos:
            try:
                self.creados.append(expediente.crear(self.base, e))
            except (OSError, ValueError, RuntimeError) as error:
                errores.append(f"{e.etiqueta}: {error}")
        texto = f"{len(elegidos) - len(errores)} expediente(s) creados o actualizados."
        if errores:
            texto += "\n\nNo se pudieron crear:\n" + "\n".join(errores)
            QMessageBox.warning(self, "Expedientes", texto)
        else:
            QMessageBox.information(self, "Expedientes", texto)
        if len(elegidos) == 1 and not errores:
            archivo.abrir(self.creados[-1]["carpeta"])
