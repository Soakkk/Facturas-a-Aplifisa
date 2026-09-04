"""Los PDF escaneados, en una lista: abrirlos, volver a pasarlos por el
programa, corregir de quien son o quitarlos de en medio.

Sin esto, los escaneos se van amontonando en una carpeta y hay que salir del
programa para saber que hay.
"""

from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import archivo

COLUMNAS = ["Cliente", "Ejercicio", "Tipo", "Fecha escaneo", "Archivo", "Tamaño"]


class DialogoEscaneos(QDialog):
    """Devuelve en `rutas_elegidas` lo que se quiera volver a meter en el lote."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escaneos guardados")
        self.resize(860, 480)
        self.rutas_elegidas: List[str] = []
        self._escaneos: List[archivo.Escaneo] = []

        raiz = QVBoxLayout(self)
        self.lbl_carpeta = QLabel()
        self.lbl_carpeta.setObjectName("textoSuave")
        self.lbl_carpeta.setWordWrap(True)
        raiz.addWidget(self.lbl_carpeta)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch)
        self.tabla.doubleClicked.connect(self._abrir)
        raiz.addWidget(self.tabla, 1)

        botones = QHBoxLayout()
        self.btn_anadir = QPushButton("Añadir al lote")
        self.btn_anadir.setObjectName("primario")
        self.btn_anadir.setToolTip(
            "Vuelve a leer estos PDF con Gemini y los añade al lote actual.")
        self.btn_anadir.clicked.connect(self._anadir)
        botones.addWidget(self.btn_anadir)
        for texto, accion in (("Abrir PDF", self._abrir),
                              ("Abrir su carpeta", self._abrir_carpeta),
                              ("Cambiar de cliente…", self._cambiar_cliente),
                              ("Crear ZIP del ejercicio", self._crear_zip)):
            b = QPushButton(texto)
            b.clicked.connect(accion)
            botones.addWidget(b)
        botones.addStretch(1)
        self.btn_quitar = QPushButton("Quitar de la lista")
        self.btn_quitar.setObjectName("peligro")
        self.btn_quitar.setToolTip(
            "No borra nada: mueve el PDF a la carpeta _Papelera, por si acaso.")
        self.btn_quitar.clicked.connect(self._quitar)
        botones.addWidget(self.btn_quitar)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.reject)
        botones.addWidget(cerrar)
        raiz.addLayout(botones)

        self.recargar()

    # ------------------------------------------------------------- listado
    def recargar(self) -> None:
        carpeta = archivo.carpeta_escaneos()
        self._escaneos = archivo.listar(carpeta)
        self.lbl_carpeta.setText(
            f"{len(self._escaneos)} escaneo(s) en {carpeta}"
            if self._escaneos else
            f"Todavía no hay escaneos en {carpeta}. Use «Escanear facturas».")
        self.tabla.setRowCount(len(self._escaneos))
        for fila, esc in enumerate(self._escaneos):
            valores = [esc.cliente, str(esc.ejercicio or "—"),
                       esc.tipo.capitalize() if esc.tipo else "—",
                       f"{esc.fecha:%d/%m/%Y}", esc.nombre, esc.tamano_texto]
            for columna, texto in enumerate(valores):
                item = QTableWidgetItem(texto)
                if columna == 5:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if esc.cliente == archivo.SIN_IDENTIFICAR:
                    item.setToolTip(
                        "Aún no se sabe de quién es. Se coloca solo al volver "
                        "a pasarlo por el programa, o con «Cambiar de cliente».")
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

    def _seleccionados(self) -> List[archivo.Escaneo]:
        filas = sorted({i.row() for i in self.tabla.selectionModel().selectedRows()})
        return [self._escaneos[f] for f in filas if f < len(self._escaneos)]

    def _uno(self) -> Optional[archivo.Escaneo]:
        elegidos = self._seleccionados()
        if not elegidos:
            QMessageBox.information(self, "Escaneos",
                                    "Elija primero un escaneo de la lista.")
            return None
        return elegidos[0]

    # ------------------------------------------------------------ acciones
    def _anadir(self) -> None:
        elegidos = self._seleccionados()
        if not elegidos:
            QMessageBox.information(
                self, "Escaneos", "Elija los escaneos que quiere añadir al lote.")
            return
        self.rutas_elegidas = [e.ruta for e in elegidos]
        self.accept()

    def _abrir(self) -> None:
        esc = self._uno()
        if esc:
            archivo.abrir(esc.ruta)

    def _abrir_carpeta(self) -> None:
        esc = self._uno()
        archivo.abrir(os.path.dirname(esc.ruta) if esc
                      else archivo.carpeta_escaneos())

    def _cambiar_cliente(self) -> None:
        esc = self._uno()
        if not esc:
            return
        nombre, ok = QInputDialog.getText(
            self, "Cambiar de cliente",
            "¿De qué cliente son estas facturas?\n"
            "El PDF se moverá a su carpeta y se le cambiará el nombre.",
            text="" if esc.cliente in (archivo.SIN_IDENTIFICAR, "—") else esc.cliente)
        if ok and nombre.strip():
            archivo.renombrar_cliente(esc.ruta, nombre.strip())
            self.recargar()

    def _crear_zip(self) -> None:
        esc = self._uno()
        if not esc:
            return
        if esc.cliente in (archivo.SIN_IDENTIFICAR, "—") or not esc.ejercicio:
            QMessageBox.warning(
                self, "Crear ZIP",
                "Antes debe identificar el cliente y el ejercicio del escaneo.")
            return
        try:
            ruta = archivo.comprimir_ejercicio(
                archivo.carpeta_escaneos(), esc.cliente, esc.ejercicio)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Crear ZIP", str(e))
            return
        QMessageBox.information(
            self, "ZIP preparado",
            f"Se ha creado:\n{ruta}\n\nYa puede adjuntarlo como documentación "
            "digitalizada en Aplifisa.")
        archivo.abrir(os.path.dirname(ruta))

    def _quitar(self) -> None:
        elegidos = self._seleccionados()
        if not elegidos:
            QMessageBox.information(self, "Escaneos",
                                    "Elija los escaneos que quiere quitar.")
            return
        if QMessageBox.question(
                self, "Quitar escaneos",
                f"¿Quitar {len(elegidos)} escaneo(s) de la lista?\n\n"
                f"No se borran: quedan en la carpeta «{archivo.PAPELERA}» "
                f"por si hicieran falta.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        fallos = 0
        for esc in elegidos:
            try:
                archivo.a_papelera(esc.ruta)
            except OSError:
                fallos += 1
        self.recargar()
        if fallos:
            QMessageBox.warning(
                self, "Escaneos",
                f"{fallos} archivo(s) no se pudieron mover (¿están abiertos "
                f"en otro programa?).")
