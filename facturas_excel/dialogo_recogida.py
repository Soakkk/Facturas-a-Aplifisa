"""Revisar lo encontrado en el Escritorio y Descargas antes de recogerlo."""

from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QProgressDialog, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import recoger

COLUMNAS = ["Recoger", "Archivo", "Dónde está", "Cliente", "Ejercicio", "Tipo",
            "Cómo se ha identificado / qué falta"]
SIN_CLIENTE = ""


class _Hilo(QThread):
    progreso = Signal(int, int)
    terminado = Signal(object)
    fallo = Signal(str)

    def __init__(self, funcion):
        super().__init__()
        self.funcion = funcion

    def run(self):
        try:
            self.terminado.emit(self.funcion(self.progreso.emit))
        except Exception as e:  # noqa: se enseña al usuario
            self.fallo.emit(str(e))


def ejecutar_con_progreso(parent, texto: str, funcion):
    """Ejecuta `funcion(progreso)` en segundo plano con una barra de progreso."""
    dialogo = QProgressDialog(texto, None, 0, 0, parent)
    dialogo.setWindowTitle("Un momento")
    dialogo.setMinimumDuration(300)
    dialogo.setWindowModality(Qt.WindowModal)
    resultado = {}
    hilo = _Hilo(funcion)
    hilo.progreso.connect(lambda a, t: (dialogo.setMaximum(t), dialogo.setValue(a)))
    hilo.terminado.connect(lambda r: resultado.setdefault("ok", r))
    hilo.fallo.connect(lambda e: resultado.setdefault("error", e))
    hilo.finished.connect(dialogo.close)
    hilo.start()
    dialogo.exec()
    hilo.wait()
    if "error" in resultado:
        raise RuntimeError(resultado["error"])
    return resultado.get("ok")


class DialogoRecogida(QDialog):
    """Enseña la propuesta; `resultado` queda con lo aplicado."""

    def __init__(self, candidatos: List[recoger.Candidato], base: str,
                 api_key: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recoger facturas sueltas")
        self.resize(1180, 620)
        self.base = base
        self.api_key = api_key
        self.candidatos = candidatos
        self.conocidos = recoger.clientes_conocidos(base)
        self.resultado = None

        capa = QVBoxLayout(self)
        self.lbl_resumen = QLabel()
        self.lbl_resumen.setWordWrap(True)
        capa.addWidget(self.lbl_resumen)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.doubleClicked.connect(self._abrir)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(6, QHeaderView.Stretch)
        capa.addWidget(self.tabla, 1)

        botones = QHBoxLayout()
        self.btn_gemini = QPushButton()
        self.btn_gemini.clicked.connect(self._leer_con_gemini)
        botones.addWidget(self.btn_gemini)
        abrir = QPushButton("Abrir el PDF")
        abrir.clicked.connect(self._abrir)
        botones.addWidget(abrir)
        botones.addStretch(1)
        self.btn_aplicar = QPushButton()
        self.btn_aplicar.setObjectName("primario")
        self.btn_aplicar.clicked.connect(self._aplicar)
        botones.addWidget(self.btn_aplicar)
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        botones.addWidget(cancelar)
        capa.addLayout(botones)
        self._pintar()

    # ------------------------------------------------------------ tabla
    def _pintar(self) -> None:
        # Vista previa del plan (no mueve ni crea nada): así se ven ya las
        # copias repetidas que irán a _Duplicados.
        recoger.planificar([c for c in self.candidatos if c.listo], self.base)
        self.tabla.setRowCount(len(self.candidatos))
        self._controles = []
        for fila, c in enumerate(self.candidatos):
            marca = QCheckBox()
            marca.setChecked(c.listo and c.clase != "listado")
            marca.setEnabled(c.clase != "listado")
            marca.toggled.connect(self._actualizar_resumen)
            caja = QWidget()
            capa = QHBoxLayout(caja)
            capa.setContentsMargins(8, 0, 0, 0)
            capa.addWidget(marca)
            self.tabla.setCellWidget(fila, 0, caja)

            nombre = QTableWidgetItem(os.path.basename(c.ruta))
            nombre.setToolTip(c.ruta)
            self.tabla.setItem(fila, 1, nombre)
            self.tabla.setItem(fila, 2, QTableWidgetItem(
                os.path.basename(os.path.dirname(c.ruta))))

            cliente = QComboBox()
            cliente.addItem("(sin identificar)", SIN_CLIENTE)
            primero = list(dict.fromkeys(c.opciones))
            for nif in primero + sorted(n for n in self.conocidos if n not in primero):
                cliente.addItem(f"{self.conocidos[nif]} — {nif}", nif)
            cliente.setCurrentIndex(max(0, cliente.findData(c.nif)))
            cliente.setEnabled(c.clase != "listado")
            self.tabla.setCellWidget(fila, 3, cliente)

            ejercicio = QSpinBox()
            ejercicio.setRange(1999, 2100)
            ejercicio.setSpecialValueText("—")
            ejercicio.setValue(c.ejercicio or 1999)
            ejercicio.setEnabled(c.clase != "listado")
            self.tabla.setCellWidget(fila, 4, ejercicio)

            tipo = QComboBox()
            tipo.addItem("Gastos", recoger.GASTOS)
            tipo.addItem("Ingresos", recoger.INGRESOS)
            tipo.setCurrentIndex(1 if c.tipo == recoger.INGRESOS else 0)
            tipo.setEnabled(c.clase != "listado")
            self.tabla.setCellWidget(fila, 5, tipo)

            texto = c.como or ""
            if c.dudas:
                texto = (texto + " · " if texto else "") + " · ".join(c.dudas)
            if c.clase == "excel":
                texto = "Excel de Aplifisa · " + texto
            if c.listo and c.accion == recoger.DUPLICADO:
                texto = (f"Copia idéntica de «{os.path.basename(c.duplicado_de)}»: "
                         "se apartará en _Duplicados · " + texto)
            detalle = QTableWidgetItem(texto)
            detalle.setToolTip(texto)
            color = ("#5D7084" if c.clase == "listado" else
                     "#86500A" if c.dudas else "#19724E")
            detalle.setForeground(QColor(color))
            self.tabla.setItem(fila, 6, detalle)
            for control in (cliente, tipo):
                control.currentIndexChanged.connect(
                    lambda _i, m=marca: m.setChecked(True))
            ejercicio.valueChanged.connect(lambda _v, m=marca: m.setChecked(True))
            self._controles.append((marca, cliente, ejercicio, tipo))
        self._actualizar_resumen()

    def _elegidos(self) -> List[recoger.Candidato]:
        """Los marcados, con lo que se haya corregido en la tabla."""
        elegidos = []
        for c, (marca, cliente, ejercicio, tipo) in zip(self.candidatos, self._controles):
            if not marca.isChecked():
                continue
            nif = cliente.currentData()
            c.nif = nif or ""
            c.nombre = self.conocidos.get(nif, "") if nif else ""
            c.ejercicio = ejercicio.value() if ejercicio.value() > 1999 else None
            c.tipo = tipo.currentData()
            elegidos.append(c)
        return elegidos

    def _actualizar_resumen(self, *_):
        marcados = sum(1 for m, *_ in self._controles if m.isChecked())
        dudosos = sum(1 for c in self.candidatos if c.dudas and c.clase != "listado")
        sin_texto = sum(1 for c in self.candidatos if c.sin_texto)
        self.lbl_resumen.setText(
            f"Encontrados {len(self.candidatos)} archivo(s) en el Escritorio y "
            f"Descargas. Marcados para recoger: {marcados}. Con algo que revisar "
            f"(en ámbar): {dudosos}. No se mueve nada hasta pulsar «Recoger». "
            "Las copias idénticas de algo ya archivado van a _Duplicados, y todo "
            "se puede deshacer.")
        self.btn_aplicar.setText(f"Recoger {marcados} archivo(s)")
        self.btn_aplicar.setEnabled(bool(marcados))
        estimado = recoger.coste_estimado_gemini(self.candidatos) if sin_texto else 0
        coste = ("menos de 1 céntimo" if estimado < 0.01
                 else f"~{estimado:.2f} €".replace(".", ","))
        self.btn_gemini.setText(
            f"Identificar {sin_texto} escaneado(s) con Gemini ({coste})"
            if sin_texto else "No hay escaneados sin texto")
        self.btn_gemini.setEnabled(bool(sin_texto and self.api_key))

    # ---------------------------------------------------------- acciones
    def _abrir(self, *_):
        fila = self.tabla.currentRow()
        if 0 <= fila < len(self.candidatos):
            from . import archivo
            archivo.abrir(self.candidatos[fila].ruta)

    def _leer_con_gemini(self):
        n = sum(1 for c in self.candidatos if c.sin_texto)
        estimado = recoger.coste_estimado_gemini(self.candidatos)
        if QMessageBox.question(
                self, "Leer con Gemini",
                f"Se leerá solo la primera página de {n} escaneado(s) para saber "
                f"de quién son. Coste aproximado: "
                f"{'menos de 1 céntimo' if estimado < 0.01 else f'{estimado:.2f} €'}. "
                "¿Continuar?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        try:
            gasto = ejecutar_con_progreso(
                self, "Identificando escaneados con Gemini…",
                lambda progreso: recoger.leer_con_gemini(
                    self.candidatos, self.base, self.api_key, progreso))
        except RuntimeError as e:
            QMessageBox.warning(self, "Leer con Gemini", str(e))
            return
        self._pintar()
        self.lbl_resumen.setText(self.lbl_resumen.text()
                                 + f" Lectura con Gemini: {gasto:.2f} €.")

    def _aplicar(self):
        elegidos = self._elegidos()
        incompletos = [c for c in elegidos if not (c.nif and c.ejercicio and c.tipo)]
        if incompletos:
            QMessageBox.warning(
                self, "Recoger",
                f"{len(incompletos)} archivo(s) marcados no tienen cliente o "
                "ejercicio. Complételos o desmárquelos.")
            return
        recoger.planificar(elegidos, self.base)
        try:
            self.resultado = recoger.aplicar(elegidos, self.base)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Recoger", f"{e}\nLo movido se puede deshacer.")
            return
        self.resultado["afectados"] = recoger.afectados(elegidos)
        self.accept()
