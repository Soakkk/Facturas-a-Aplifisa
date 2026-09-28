"""Consultar el registro de facturas: qué hay, en qué paso está y dónde."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import archivo, registro_facturas
from .registro_facturas import TEXTO_ESTADO

COLUMNAS = ["Estado", "Cliente", "Ejercicio", "Tipo", "Fecha", "Nº factura",
            "Proveedor o cliente", "NIF", "Total", "Excel", "PDF"]


def _eur(valor) -> str:
    if valor is None:
        return ""
    texto = f"{float(valor):,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


class DialogoRegistroFacturas(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Registro de facturas")
        self.resize(1240, 640)
        self.filas = []
        capa = QVBoxLayout(self)
        explicacion = QLabel(
            "Cada factura que sale del programa queda aquí con su recorrido "
            "(leída, revisada, exportada, archivada), el Excel en el que salió "
            "y su PDF. Doble clic para abrir el PDF.")
        explicacion.setWordWrap(True)
        capa.addWidget(explicacion)

        filtros = QHBoxLayout()
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText(
            "Proveedor o cliente, NIF, nº de factura o importe…")
        self.buscar.setClearButtonEnabled(True)
        filtros.addWidget(self.buscar, 1)
        self.ejercicio = QComboBox()
        self.ejercicio.addItem("Todos los ejercicios", None)
        for anio in registro_facturas.ejercicios():
            self.ejercicio.addItem(str(anio), anio)
        filtros.addWidget(self.ejercicio)
        capa.addLayout(filtros)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(True)
        self.tabla.setWordWrap(False)
        self.tabla.setTextElideMode(Qt.ElideRight)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.Interactive)
        cabecera.setSectionResizeMode(6, QHeaderView.Stretch)
        cabecera.setMinimumSectionSize(60)
        for columna, ancho in {0: 82, 1: 150, 2: 64, 3: 58, 4: 84, 5: 96,
                               7: 92, 8: 78, 9: 130, 10: 130}.items():
            self.tabla.setColumnWidth(columna, ancho)
        self.tabla.doubleClicked.connect(lambda *_: self._abrir_pdf())
        capa.addWidget(self.tabla, 1)

        pie = QHBoxLayout()
        self.resumen = QLabel()
        self.resumen.setObjectName("textoSuave")
        pie.addWidget(self.resumen, 1)
        abrir = QPushButton("Abrir el PDF")
        abrir.clicked.connect(self._abrir_pdf)
        pie.addWidget(abrir)
        carpeta = QPushButton("Abrir su carpeta")
        carpeta.clicked.connect(self._abrir_carpeta)
        pie.addWidget(carpeta)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.accept)
        pie.addWidget(cerrar)
        capa.addLayout(pie)

        self._espera = QTimer(self)
        self._espera.setSingleShot(True)
        self._espera.setInterval(250)
        self._espera.timeout.connect(self.actualizar)
        self.buscar.textChanged.connect(lambda *_: self._espera.start())
        self.ejercicio.currentIndexChanged.connect(lambda *_: self.actualizar())
        self.actualizar()

    def actualizar(self) -> None:
        self.filas = registro_facturas.consultar(
            self.buscar.text(), self.ejercicio.currentData())
        self.tabla.setSortingEnabled(False)
        self.tabla.setRowCount(len(self.filas))
        cuenta = {}
        for r, f in enumerate(self.filas):
            estado = TEXTO_ESTADO.get(f.get("estado"), f.get("estado") or "")
            cuenta[estado] = cuenta.get(estado, 0) + 1
            cliente = f.get("cliente_nombre") or f.get("cliente_nif") or ""
            valores = [estado, cliente, str(f.get("ejercicio") or ""),
                       "Ingreso" if f.get("tipo") == "venta" else "Gasto",
                       f.get("fecha") or "", f.get("num_factura") or "",
                       f.get("nombre") or "", f.get("nif") or "",
                       _eur(f.get("total")), f.get("excel") or "",
                       os.path.basename(f.get("pdf") or "")]
            for c, texto in enumerate(valores):
                item = QTableWidgetItem(str(texto))
                item.setData(Qt.UserRole, r)
                if c == 8:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 10 and f.get("pdf"):
                    item.setToolTip(f["pdf"])
                elif c in (1, 6, 9):
                    item.setToolTip(str(texto))
                self.tabla.setItem(r, c, item)
        self.tabla.setSortingEnabled(True)
        partes = [f"{n} {e.lower()}" for e, n in sorted(cuenta.items())]
        self.resumen.setText(
            f"{len(self.filas)} factura(s)" + (": " + ", ".join(partes) if partes else "")
            if self.filas else "No hay facturas que coincidan.")

    def _actual(self):
        item = self.tabla.item(self.tabla.currentRow(), 0)
        if item is None:
            return None
        return self.filas[item.data(Qt.UserRole)]

    def _abrir_pdf(self) -> None:
        f = self._actual()
        if not f:
            return
        ruta = f.get("pdf") or f.get("origen")
        if ruta and os.path.exists(ruta):
            archivo.abrir(ruta)
        else:
            self.resumen.setText("Esta factura no tiene PDF propio en el archivo "
                                 "(o se ha movido fuera del programa).")

    def _abrir_carpeta(self) -> None:
        f = self._actual()
        ruta = f and (f.get("pdf") or f.get("origen"))
        if ruta and os.path.isdir(os.path.dirname(ruta)):
            archivo.abrir(os.path.dirname(ruta))
