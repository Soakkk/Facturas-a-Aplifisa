"""Ficha de la factura seleccionada, junto al documento original.

De un vistazo: qué se ha leído, qué está comprobado (✓) y qué hay que mirar
(!), agrupado como se lee una factura: identificación, importes y
contabilidad. El cuadre se enseña como una cuenta («100,00 + 21,00 = 121,00»)
y, si los dos modelos de lectura no coinciden, se ven los dos valores con un
botón para quedarse con cada uno.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .estilo import ACCENT, BORDER, DANGER, INK, MUTED, SUCCESS, WARNING

VERDE, AMBAR, ROJO = SUCCESS, WARNING, DANGER


def _eur(valor) -> str:
    if valor is None:
        return "—"
    texto = f"{float(valor):,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(valor) -> str:
    if valor is None:
        return "—"
    v = float(valor)
    return (str(int(v)) if v.is_integer() else f"{v:g}".replace(".", ",")) + " %"


class PanelFicha(QScrollArea):
    """Se rellena con `mostrar(datos)`; emite lo que el usuario decide."""

    # (fila, índice de la discrepancia, qué lectura se queda: 1 o 2)
    discrepancia_resuelta = Signal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panelFicha")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._contenido = QWidget()
        self._contenido.setObjectName("panelFichaContenido")
        self._capa = QVBoxLayout(self._contenido)
        self._capa.setContentsMargins(2, 4, 6, 4)
        self._capa.setSpacing(6)
        self.setWidget(self._contenido)
        self.botones_discrepancia: list[QPushButton] = []
        self.vacio()

    # ------------------------------------------------------------ utilidades
    def _limpiar(self) -> None:
        self.botones_discrepancia = []
        while self._capa.count():
            item = self._capa.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._vaciar_layout(item.layout())

    def _vaciar_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._vaciar_layout(item.layout())

    def _etiqueta(self, texto: str, estilo: str = "", rico: bool = False) -> QLabel:
        lbl = QLabel(texto)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText if rico else Qt.PlainText)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if estilo:
            lbl.setStyleSheet(estilo)
        return lbl

    def _seccion(self, titulo: str) -> None:
        lbl = self._etiqueta(
            titulo.upper(),
            f"color: {MUTED}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1px; padding-top: 6px; "
            f"border-bottom: 1px solid {BORDER};")
        lbl.setObjectName("fichaSeccion")
        self._capa.addWidget(lbl)

    def _dato(self, nombre: str, valor: str, marcas: list) -> None:
        """Una línea «Nombre   valor   ✓/!» con los motivos debajo."""
        if marcas:
            color = ROJO if any(g == "error" for g, _ in marcas) else AMBAR
            simbolo = "✕" if color == ROJO else "!"
        else:
            color, simbolo = VERDE, "✓"
        fila = QHBoxLayout()
        fila.setSpacing(6)
        marca = self._etiqueta(
            simbolo, f"color: {color}; font-weight: 800; min-width: 14px;")
        fila.addWidget(marca)
        fila.addWidget(self._etiqueta(nombre, f"color: {MUTED}; min-width: 86px;"))
        fila.addWidget(self._etiqueta(
            valor or "(vacío)",
            f"color: {INK if valor else MUTED}; font-weight: 600;"), 1)
        self._capa.addLayout(fila)
        for _gravedad, texto in marcas:
            self._capa.addWidget(self._etiqueta(
                texto, f"color: {color}; padding-left: 20px; font-size: 11px;"))

    # --------------------------------------------------------------- mostrar
    def vacio(self, texto: str = "Seleccione una factura para ver su ficha.") -> None:
        self._limpiar()
        self._capa.addWidget(self._etiqueta(texto, f"color: {MUTED};"))
        self._capa.addStretch(1)

    def mostrar(self, d: dict) -> None:
        """`d` lo prepara la ventana (ver VentanaPrincipal._datos_ficha)."""
        self._limpiar()
        fila = d["fila"]
        texto_estado, color_estado, fondo_estado = d["estado"]
        cabecera = self._etiqueta(
            f"<span style='background:{fondo_estado}; color:{color_estado.name()};"
            f" font-weight:700; padding:2px 6px;'>&nbsp;{html.escape(texto_estado)}"
            f"&nbsp;</span>&nbsp; <b>{html.escape(d['titulo'])}</b>", rico=True)
        cabecera.setObjectName("fichaCabecera")
        self._capa.addWidget(cabecera)
        marcas = d["marcas"]

        self._seccion("Identificación")
        self._dato(d["rol"], d["nombre"], marcas.get("nombre", []))
        self._dato("NIF", d["nif"], marcas.get("nif", []))
        self._dato("Nº factura", d["num"], marcas.get("num_factura", []))
        self._dato("Fecha", d["fecha"], marcas.get("fecha", []))

        self._seccion("Importes")
        for linea in d["lineas"]:
            partes = f"Base {_eur(linea['base'])} al {_pct(linea['pct'])} → " \
                     f"IVA {_eur(linea['cuota'])}"
            if linea.get("cuota_re") is not None:
                partes += f" · RE {_pct(linea.get('pct_re'))} {_eur(linea['cuota_re'])}"
            if linea.get("suplido"):
                partes = f"Suplido {_eur(linea['base'])} (sin IVA)"
            self._dato("Línea", partes, linea["marcas"])
        if d.get("irpf") is not None:
            self._dato("Retención", f"− {_eur(d['irpf'])}", marcas.get("cuota_irpf", []))
        cuenta = d["cuadre"]
        if cuenta:
            ok = cuenta["ok"]
            color = VERDE if ok else (AMBAR if cuenta["impreso"] is not None else ROJO)
            simbolo = "✓" if ok else "≠"
            self._capa.addWidget(self._etiqueta(
                f"<span style='color:{MUTED}'>Cuadre:</span> "
                f"{html.escape(cuenta['formula'])} = <b>{_eur(cuenta['calculado'])}</b>"
                f" &nbsp; <span style='color:{color}; font-weight:800'>{simbolo}</span>"
                f" &nbsp;Total impreso <b>{_eur(cuenta['impreso'])}</b>"
                + ("" if ok or cuenta["impreso"] is None else
                   f" <span style='color:{color}'>(diferencia "
                   f"{_eur(cuenta['calculado'] - cuenta['impreso'])})</span>"),
                f"background: #F5F8FC; border: 1px solid {BORDER}; padding: 5px;",
                rico=True))

        self._seccion("Contabilidad")
        self._dato("Tipo", d["tipo"], [])
        self._dato("Cuenta", d["cuenta"], marcas.get("concepto", []))

        self._seccion("Lectura de la IA")
        self._capa.addWidget(self._etiqueta(
            d["lectura"], f"color: {INK if d['doble'] else MUTED};"))
        for indice, disc in enumerate(d["discrepancias"]):
            caja = QFrame()
            caja.setObjectName("fichaDiscrepancia")
            caja.setStyleSheet(
                f"QFrame#fichaDiscrepancia {{ background: #FBEFDC; border: 1px "
                f"solid {AMBAR}; border-radius: 4px; }} QLabel {{ border: none; "
                f"background: transparent; }}")
            capa = QVBoxLayout(caja)
            capa.setContentsMargins(8, 6, 8, 6)
            capa.setSpacing(4)
            capa.addWidget(self._etiqueta(
                f"<b>{html.escape(disc['etiqueta'])}</b> no coincide", rico=True))
            for lectura, clave in ((1, "valor_1"), (2, "valor_2")):
                modelo = disc.get(f"modelo_{lectura}") or f"Lectura {lectura}"
                linea = QHBoxLayout()
                linea.addWidget(self._etiqueta(
                    f"<span style='color:{MUTED}'>{html.escape(modelo)}:</span> "
                    f"<b>{html.escape(disc['textos'][lectura - 1])}</b>", rico=True), 1)
                boton = QPushButton("Usar este" if lectura == 2 else "Es correcto")
                boton.setObjectName("fichaBoton")
                boton.setStyleSheet(
                    f"QPushButton#fichaBoton {{ color: {ACCENT}; background: white;"
                    f" border: 1px solid {ACCENT}; border-radius: 3px;"
                    f" padding: 2px 8px; font-weight: 600; }}")
                boton.setEnabled(lectura == 1 or disc.get("aplicable", True))
                if lectura == 2 and not disc.get("aplicable", True):
                    boton.setToolTip("Este dato no se puede copiar solo: "
                                     "corríjalo en la tabla.")
                boton.clicked.connect(
                    lambda _c=False, f=fila, i=indice, l=lectura:
                    self.discrepancia_resuelta.emit(f, i, l))
                self.botones_discrepancia.append(boton)
                linea.addWidget(boton)
                capa.addLayout(linea)
            self._capa.addWidget(caja)

        otros = d["otros_motivos"]
        if otros:
            self._seccion("Otros avisos")
            for gravedad, texto in otros:
                color = ROJO if gravedad == "error" else AMBAR
                self._capa.addWidget(self._etiqueta(
                    f"• {texto}", f"color: {color}; font-size: 11px;"))
        self._capa.addStretch(1)
