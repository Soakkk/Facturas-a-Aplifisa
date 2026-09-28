"""Examen de precisión: se pulsa, dice lo que costará y enseña los aciertos."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import __version__, ajustes, examen
from .extraccion import modelos_configurados
from .estilo import DANGER, SUCCESS, WARNING


def _pct(valor) -> str:
    return "—" if valor is None else f"{valor:.1f} %".replace(".", ",")


def _corto(modelo: str) -> str:
    """«gemini-3.8-flash» -> «3.8-flash»: cabe en la tabla."""
    return str(modelo).replace("gemini-", "")


def _color(valor) -> str:
    if valor is None:
        return "#5D7084"
    return SUCCESS if valor >= 98 else WARNING if valor >= 90 else DANGER


class DialogoExamen(QDialog):
    def __init__(self, api_key: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Examen de precisión de la lectura")
        self.resize(880, 780)
        self.api_key = api_key
        self.modelos = modelos_configurados()
        self.ppp = int(ajustes.leer("lectura_ppp", 150) or 150)
        self.resultado = None

        capa = QVBoxLayout(self)
        texto = QLabel(
            "Se vuelven a leer facturas que usted ya revisó y exportó, con cada "
            "modelo por separado, y se compara lo leído con lo que quedó bueno. "
            "Así se sabe con números si una versión nueva o un cambio de modelo "
            "lee mejor o peor. Solo se usan facturas de una hoja que tengan su "
            "PDF en el archivo.")
        texto.setWordWrap(True)
        capa.addWidget(texto)

        fila = QHBoxLayout()
        fila.addWidget(QLabel("Facturas a examinar, como máximo:"))
        self.maximo = QSpinBox()
        self.maximo.setRange(3, 200)
        self.maximo.setValue(examen.MAXIMO_POR_DEFECTO)
        self.maximo.valueChanged.connect(self._preparar)
        fila.addWidget(self.maximo)
        fila.addStretch(1)
        self.btn_pasar = QPushButton()
        self.btn_pasar.setObjectName("primario")
        self.btn_pasar.clicked.connect(self._pasar)
        fila.addWidget(self.btn_pasar)
        capa.addLayout(fila)
        self.lbl_preparado = QLabel()
        self.lbl_preparado.setWordWrap(True)
        self.lbl_preparado.setObjectName("textoSuave")
        capa.addWidget(self.lbl_preparado)

        self.tabla = QTableWidget(0, 0)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.verticalHeader().setDefaultSectionSize(28)
        self.tabla.setMinimumHeight(8 * 28 + 34)
        capa.addWidget(self.tabla, 3)
        self.lbl_resumen = QLabel()
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setTextFormat(Qt.RichText)
        capa.addWidget(self.lbl_resumen)

        titulo = QLabel("Exámenes anteriores")
        titulo.setObjectName("tituloSeccion")
        capa.addWidget(titulo)
        self.historia = QTableWidget(0, 5)
        self.historia.setHorizontalHeaderLabels(
            ["Fecha", "Versión", "Facturas", "Aciertos por modelo",
             "Verificadas con error"])
        self.historia.verticalHeader().setVisible(False)
        self.historia.setEditTriggers(QTableWidget.NoEditTriggers)
        cabecera = self.historia.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(3, QHeaderView.Stretch)
        self.historia.setMinimumHeight(110)
        capa.addWidget(self.historia, 1)

        self.detalle = QPlainTextEdit()
        self.detalle.setReadOnly(True)
        self.detalle.setPlaceholderText("Aquí saldrá cada dato mal leído.")
        self.detalle.setMaximumHeight(90)
        capa.addWidget(self.detalle)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.accept)
        capa.addWidget(cerrar, 0, Qt.AlignRight)

        self._preparar()
        self._pintar_historia()

    # ------------------------------------------------------------ preparar
    def _preparar(self, *_):
        self.casos = examen.casos_disponibles(self.maximo.value())
        coste = examen.coste_estimado(len(self.casos), self.modelos, self.ppp)
        texto_coste = ("menos de 1 céntimo" if coste < 0.01
                       else f"unos {coste:.2f} €".replace(".", ","))
        if not self.casos:
            self.lbl_preparado.setText(
                "Todavía no hay facturas exportadas con su PDF en el archivo. "
                "Cuando exporte algún lote, podrá pasar el examen.")
        else:
            self.lbl_preparado.setText(
                f"{len(self.casos)} factura(s) × {len(self.modelos)} modelo(s) "
                f"({', '.join(self.modelos)}). Coste aproximado: {texto_coste}.")
        self.btn_pasar.setText(f"Pasar el examen ({texto_coste})")
        self.btn_pasar.setEnabled(bool(self.casos and self.api_key))
        if not self.api_key:
            self.btn_pasar.setToolTip("Falta la API key de Gemini.")

    # -------------------------------------------------------------- pasar
    def _pasar(self):
        from .dialogo_recogida import ejecutar_con_progreso
        if QMessageBox.question(
                self, "Examen de precisión",
                self.lbl_preparado.text() + "\n\n¿Pasar el examen ahora?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        lector = examen.lector_gemini(self.api_key)
        try:
            self.resultado = ejecutar_con_progreso(
                self, "Leyendo las facturas del examen…",
                lambda progreso: examen.pasar(self.casos, lector, self.modelos,
                                              self.ppp, progreso))
        except RuntimeError as e:
            QMessageBox.warning(self, "Examen de precisión", str(e))
            return
        examen.guardar(self.resultado, __version__)
        self._pintar_resultado(self.resultado)
        self._pintar_historia()

    def _pintar_resultado(self, r) -> None:
        self.tabla.setColumnCount(1 + len(r.modelos))
        self.tabla.setHorizontalHeaderLabels(["Dato", *r.modelos])
        filas = [*examen.CAMPOS, (None, "TODOS LOS DATOS")]
        self.tabla.setRowCount(len(filas))
        for i, (campo, etiqueta) in enumerate(filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(etiqueta))
            for j, modelo in enumerate(r.modelos, 1):
                valor = r.porcentaje(modelo, campo)
                par = r.por_campo.get(modelo, {}).get(campo) if campo else None
                texto = _pct(valor) + (f"  ({par[0]} de {par[1]})" if par else "")
                item = QTableWidgetItem(texto)
                item.setForeground(QColor(_color(valor)))
                item.setTextAlignment(Qt.AlignCenter)
                self.tabla.setItem(i, j, item)
        malas = len(r.verificadas_con_error)
        partes = [f"<b>{r.casos}</b> factura(s) examinadas."]
        if len(r.modelos) >= 2:
            partes.append(
                f"Con doble lectura habrían salido <b>{r.verificadas}</b> como "
                "«Verificada»; de ellas, "
                + (f"<b style='color:{DANGER}'>{malas} con algún dato mal</b> "
                   "(los dos modelos se equivocaron igual)." if malas else
                   f"<b style='color:{SUCCESS}'>ninguna con datos mal</b>."))
        if r.fallos_lectura:
            partes.append(f"{r.fallos_lectura} lectura(s) no salieron.")
        partes.append(f"Coste del examen: {r.coste:.4f} €".replace(".", ","))
        self.lbl_resumen.setText(" ".join(partes))
        self.detalle.setPlainText("\n".join(r.verificadas_con_error + r.detalles)
                                  or "Ningún dato mal leído.")

    def _pintar_historia(self) -> None:
        pasados = examen.anteriores()
        self.historia.setRowCount(len(pasados))
        for i, e in enumerate(pasados):
            aciertos = " · ".join(
                f"{_corto(m)}: {_pct(examen.porcentaje_guardado(e, m))}"
                for m in e.get("modelos", []))
            valores = [str(e.get("fecha", "")).replace("T", " ")[:16],
                       e.get("version", ""), str(e.get("casos", 0)), aciertos,
                       str(len(e.get("verificadas_con_error") or []))]
            for j, texto in enumerate(valores):
                self.historia.setItem(i, j, QTableWidgetItem(texto))
