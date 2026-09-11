"""Resultado detallado del contraste con el listado de Aplifisa."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .registro import Informe, Registro
from .resumen import eur


COLOR_DIFERENCIA = QColor("#fee2e2")
COLOR_CUADRA = QColor("#dcfce7")


class DialogoRegistro(QDialog):
    """Enseña totales y diferencias; permite volver a la factura afectada."""

    def __init__(self, informe: Informe, registro: Registro, parent=None,
                 facturas=None):
        super().__init__(parent)
        self._fila_elegida = -1
        self._facturas = list(facturas or [])
        self.setWindowTitle("Comprobación fiscal con Aplifisa")
        self.resize(980, 680)
        raiz = QVBoxLayout(self)

        if not registro.bien_leido:
            diferencias = "\n".join(f"• {d}" for d in registro.diferencias_totales)
            aviso = QLabel(
                "⚠ El propio listado de Aplifisa no cuadra con las líneas "
                "leídas. El contraste puede ser incompleto.\n" + diferencias)
            aviso.setObjectName("alertaTitulo")
            aviso.setWordWrap(True)
            raiz.addWidget(aviso)

        titulo = QLabel(
            "<b>Todo cuadra.</b> El lote y Aplifisa coinciden en facturas, "
            "líneas e importes." if informe.todo_cuadra else
            "<b>Hay diferencias.</b> La tabla inferior dice qué factura falta, "
            "qué dato cambia o qué apunte sobra en Aplifisa.")
        titulo.setWordWrap(True)
        raiz.addWidget(titulo)

        self.tabla_totales = QTableWidget(0, 4)
        self.tabla_totales.setHorizontalHeaderLabels(
            ["Concepto", "En el lote", "En Aplifisa", "Diferencia"])
        self.tabla_totales.verticalHeader().setVisible(False)
        self.tabla_totales.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_totales.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabla_totales.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        for columna in range(1, 4):
            self.tabla_totales.horizontalHeader().setSectionResizeMode(
                columna, QHeaderView.ResizeToContents)
        self._rellenar_totales(informe)
        raiz.addWidget(self.tabla_totales)

        etiqueta = QLabel(
            "Diferencias localizadas" if not informe.todo_cuadra
            else "No se han encontrado diferencias línea a línea")
        etiqueta.setObjectName("seccionTitulo")
        raiz.addWidget(etiqueta)

        self.tabla_detalle = QTableWidget(0, 6)
        self.tabla_detalle.setHorizontalHeaderLabels(
            ["Resultado", "Línea", "Fecha", "Nº factura", "Contraparte", "Detalle"])
        self.tabla_detalle.verticalHeader().setVisible(False)
        self.tabla_detalle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_detalle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_detalle.setSelectionMode(QAbstractItemView.SingleSelection)
        cabecera = self.tabla_detalle.horizontalHeader()
        for columna in range(5):
            cabecera.setSectionResizeMode(columna, QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(5, QHeaderView.Stretch)
        self._rellenar_detalles(informe)
        self.tabla_detalle.itemSelectionChanged.connect(self._cambio_seleccion)
        self.tabla_detalle.itemDoubleClicked.connect(
            lambda _item: self._aceptar_seleccion())
        raiz.addWidget(self.tabla_detalle, 1)

        botones = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        self.boton_ver = botones.addButton(
            "Ver factura en el lote", QDialogButtonBox.ActionRole)
        self.boton_ver.setEnabled(False)
        self.boton_ver.clicked.connect(self._aceptar_seleccion)
        botones.rejected.connect(self.reject)
        raiz.addWidget(botones)

    def _rellenar_totales(self, informe: Informe) -> None:
        filas = (
            ("Facturas", informe.facturas_programa, informe.facturas_registro, False),
            ("Líneas fiscales", informe.lineas_programa, informe.lineas_registro, False),
            ("Base imponible", informe.base_programa, informe.base_registro, True),
            ("IVA", informe.cuota_programa, informe.cuota_registro, True),
            ("Recargo de equivalencia", informe.recargo_programa,
             informe.recargo_registro, True),
            ("Retenciones", informe.irpf_programa, informe.irpf_registro, True),
            ("Total factura", informe.total_programa, informe.total_registro, True),
        )
        self.tabla_totales.setRowCount(len(filas))
        for fila, (concepto, programa, aplifisa, es_importe) in enumerate(filas):
            diferencia = round(programa - aplifisa, 2)
            valores = (
                concepto,
                eur(programa) if es_importe else str(programa),
                eur(aplifisa) if es_importe else str(aplifisa),
                eur(diferencia) if es_importe else f"{diferencia:+g}",
            )
            fondo = COLOR_CUADRA if abs(diferencia) <= 0.02 else COLOR_DIFERENCIA
            for columna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if columna:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setBackground(QBrush(fondo))
                self.tabla_totales.setItem(fila, columna, item)
        self.tabla_totales.resizeRowsToContents()
        altura = (self.tabla_totales.horizontalHeader().height()
                  + sum(self.tabla_totales.rowHeight(fila)
                        for fila in range(self.tabla_totales.rowCount())) + 4)
        self.tabla_totales.setFixedHeight(altura)

    def _rellenar_detalles(self, informe: Informe) -> None:
        nombres = {
            "sin_registrar": "No registrada",
            "distinta": "Dato distinto",
            "dudosa": "Coincidencia dudosa",
        }
        for indice, estado in informe.resultados.items():
            if estado == "cuadra":
                continue
            factura = self._facturas[indice] if indice < len(self._facturas) else None
            self._anadir_detalle(
                indice,
                nombres.get(estado, estado),
                str(indice + 1),
                getattr(factura, "fecha", "") if factura else "",
                getattr(factura, "num_factura", "") if factura else "",
                getattr(factura, "nombre", "") if factura else "",
                " · ".join(informe.detalles.get(indice, [])),
            )
        for apunte in informe.apuntes_de_mas:
            numero = apunte.num_factura_proveedor or apunte.numero
            self._anadir_detalle(
                -1, "Solo en Aplifisa", "—", apunte.fecha, numero,
                apunte.nombre,
                "No está en el lote cargado; compruebe si pertenece a otro "
                "lote o si se registró por duplicado.",
            )
        if not self.tabla_detalle.rowCount():
            self._anadir_detalle(-1, "Correcto", "—", "", "", "",
                                 "Todas las líneas coinciden.")
        self.tabla_detalle.resizeRowsToContents()

    def _anadir_detalle(self, indice: int, *valores: str) -> None:
        fila = self.tabla_detalle.rowCount()
        self.tabla_detalle.insertRow(fila)
        for columna, valor in enumerate(valores):
            item = QTableWidgetItem(str(valor or ""))
            if columna == 0:
                item.setData(Qt.UserRole, indice)
            self.tabla_detalle.setItem(fila, columna, item)

    def _indice_seleccionado(self) -> int:
        fila = self.tabla_detalle.currentRow()
        if fila < 0:
            return -1
        item = self.tabla_detalle.item(fila, 0)
        return int(item.data(Qt.UserRole)) if item is not None else -1

    def _cambio_seleccion(self) -> None:
        self.boton_ver.setEnabled(self._indice_seleccionado() >= 0)

    def _aceptar_seleccion(self) -> None:
        indice = self._indice_seleccionado()
        if indice >= 0:
            self._fila_elegida = indice
            self.accept()

    def fila_seleccionada(self) -> int:
        return self._fila_elegida
