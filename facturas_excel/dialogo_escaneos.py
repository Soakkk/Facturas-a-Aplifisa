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
    QLineEdit, QComboBox, QDialogButtonBox, QFormLayout,
)

from . import archivo, identidad_archivo, clientes

COLUMNAS = ["Cliente", "NIF", "Ejercicio", "Tipo", "Fecha escaneo", "Archivo", "Tamaño"]


class DialogoEscaneos(QDialog):
    """Devuelve en `rutas_elegidas` lo que se quiera volver a meter en el lote."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escaneos guardados")
        self.resize(1120, 640)
        self.rutas_elegidas: List[str] = []
        self._escaneos: List[archivo.Escaneo] = []

        raiz = QVBoxLayout(self)
        self.lbl_carpeta = QLabel()
        self.lbl_carpeta.setObjectName("textoSuave")
        self.lbl_carpeta.setWordWrap(True)
        raiz.addWidget(self.lbl_carpeta)

        filtros = QHBoxLayout()
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText("Buscar cliente, NIF o archivo…")
        self.buscar.textChanged.connect(self._filtrar)
        filtros.addWidget(self.buscar, 1)
        self.filtro_tipo = QComboBox()
        self.filtro_tipo.addItems(["Todos los tipos", "Gastos", "Ingresos"])
        self.filtro_tipo.currentTextChanged.connect(self._filtrar)
        filtros.addWidget(self.filtro_tipo)
        organizar = QPushButton("Organizar carpetas…")
        organizar.clicked.connect(self._organizar)
        filtros.addWidget(organizar)
        deshacer = QPushButton("Deshacer organización")
        deshacer.clicked.connect(self._deshacer_organizacion)
        filtros.addWidget(deshacer)
        raiz.addLayout(filtros)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.Stretch)
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
        try:
            self._escaneos = archivo.listar(carpeta)
        except (OSError, ValueError) as e:
            self._escaneos = []
            self.tabla.setRowCount(0)
            self.lbl_carpeta.setText(f"No se pudo leer el archivo documental: {e}")
            return
        self.lbl_carpeta.setText(
            f"{len(self._escaneos)} escaneo(s) en {carpeta}"
            if self._escaneos else
            f"Todavía no hay escaneos en {carpeta}. Use «Escanear facturas».")
        self.tabla.setRowCount(len(self._escaneos))
        for fila, esc in enumerate(self._escaneos):
            valores = [esc.cliente, esc.nif or "Sin identificar", str(esc.ejercicio or "—"),
                       esc.tipo.capitalize() if esc.tipo else "—",
                       f"{esc.fecha:%d/%m/%Y}", esc.nombre, esc.tamano_texto]
            for columna, texto in enumerate(valores):
                item = QTableWidgetItem(texto)
                if columna == 6:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if esc.cliente == archivo.SIN_IDENTIFICAR:
                    item.setToolTip(
                        "Aún no se sabe de quién es. Se coloca solo al volver "
                        "a pasarlo por el programa, o con «Cambiar de cliente».")
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self._filtrar()

    def _filtrar(self):
        texto = self.buscar.text().casefold()
        tipo = self.filtro_tipo.currentText().lower()
        for fila, esc in enumerate(self._escaneos):
            coincide = texto in f"{esc.cliente} {esc.nif} {esc.nombre} {esc.ejercicio}".casefold()
            self.tabla.setRowHidden(fila, not coincide or (
                tipo != "todos los tipos" and esc.tipo != tipo))
        self.tabla.clearSelection()

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
        elegidos = self._seleccionados()
        if not elegidos or not self._puede_organizar():
            return
        d = QDialog(self)
        d.setWindowTitle(f"Cliente de {len(elegidos)} escaneo(s)")
        formulario = QFormLayout(d)
        nombre = QComboBox()
        nombre.setEditable(True)
        nombre.addItem("", "")
        for identificador, ficha in clientes._leer_todo().items():
            if isinstance(ficha, dict) and ficha.get("nombre"):
                nombre.addItem(ficha["nombre"], identificador)
        nif = QLineEdit()
        nombre.currentIndexChanged.connect(lambda: nif.setText(nombre.currentData() or ""))
        formulario.addRow("Cliente", nombre)
        formulario.addRow("NIF", nif)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(d.accept)
        botones.rejected.connect(d.reject)
        formulario.addRow(botones)
        if d.exec() != QDialog.Accepted:
            return
        from .validacion import validar_nif
        identificador = clientes._normaliza(nif.text())
        if not nombre.currentText().strip() or not validar_nif(identificador):
            QMessageBox.warning(self, "Cliente", "Indique un nombre y un NIF válido.")
            return
        try:
            for esc in elegidos:
                nueva = archivo.renombrar_cliente(esc.ruta, nombre.currentText().strip(), identificador)
                if nueva == esc.ruta and esc.nif != identificador:
                    raise OSError(f"No se pudo recolocar {esc.nombre}.")
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Archivo", str(e))
        self.recargar()

    def _puede_organizar(self):
        padre = self.parent()
        if padre and (getattr(padre, "_bloques", []) or getattr(padre, "_cola", [])
                      or getattr(padre, "_elemento_cola_actual", None)
                      or getattr(padre, "_escaneo_reciente", False)):
            QMessageBox.information(self, "Organizar carpetas",
                "Termine y exporte el lote actual y pulse «Vaciar todo» antes de mover "
                "los documentos. Así las vistas previas conservarán sus originales.")
            return False
        return True

    def _organizar(self):
        if not self._puede_organizar():
            return
        try:
            plan = identidad_archivo.planificar(archivo.carpeta_escaneos())
            d = QDialog(self)
            d.setWindowTitle("Revisar organización de carpetas")
            d.resize(960, 560)
            layout = QVBoxLayout(d)
            resumen = QLabel(f"{len(plan['movimientos'])} archivo(s) para organizar. "
                "Compruebe que cada carpeta corresponde al cliente indicado. "
                "Las copias idénticas se conservan en _Duplicados y puede deshacer los cambios.")
            resumen.setWordWrap(True)
            layout.addWidget(resumen)
            tabla = QTableWidget(len(plan["movimientos"]), 2)
            tabla.setHorizontalHeaderLabels(["Ubicación actual", "Ubicación propuesta"])
            tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            for fila, m in enumerate(plan["movimientos"]):
                for columna, campo in enumerate(("origen", "destino")):
                    item = QTableWidgetItem(m[campo])
                    item.setToolTip(m[campo])
                    tabla.setItem(fila, columna, item)
            layout.addWidget(tabla)
            if plan["pendientes"]:
                pendientes = QLabel("Sin correspondencia segura (se conservan): " + ", ".join(plan["pendientes"]))
                pendientes.setWordWrap(True)
                layout.addWidget(pendientes)
            botones = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
            botones.button(QDialogButtonBox.Apply).setText("Aplicar organización")
            botones.button(QDialogButtonBox.Apply).setEnabled(bool(plan["movimientos"]))
            botones.button(QDialogButtonBox.Apply).clicked.connect(d.accept)
            botones.rejected.connect(d.reject)
            layout.addWidget(botones)
            if d.exec() == QDialog.Accepted:
                identidad_archivo.aplicar(archivo.carpeta_escaneos(), plan)
                self.recargar()
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Organizar carpetas", f"{e}\nLos originales se conservan. "
                "Si hubo movimientos parciales, use «Deshacer organización».")

    def _deshacer_organizacion(self):
        if not self._puede_organizar():
            return
        try:
            if not identidad_archivo.deshacer_ultimo(archivo.carpeta_escaneos()):
                QMessageBox.information(self, "Archivo", "No hay una organización que deshacer.")
            self.recargar()
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Archivo", str(e))

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
                archivo.carpeta_escaneos(), esc.carpeta_cliente or esc.cliente, esc.ejercicio)
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
