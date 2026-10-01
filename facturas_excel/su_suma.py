"""«Su suma a mano»: la cifra del usuario junto a la del programa.

El usuario lo pidió para comprobar su suma a mano (o el listado de Aplifisa)
con lo que da el programa sin comparar cifra a cifra con la vista: teclea su
base, su IVA o su total y al lado sale si cuadra o cuánto se separa.

Lo que nunca puede pasar: un «✓ cuadra» falso o una cifra leída a medias.
Por eso lo que no se entiende sin dudas («4,347» ¿cuatro mil o cuatro con
algo?, «Inf», «1e5») sale como «¿cifra?» en vez de adivinarse.
"""

from __future__ import annotations

import math
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QToolButton, QVBoxLayout, QWidget,
)

from . import ajustes
from .estilo import DANGER, MUTED, SUCCESS, WARNING
from .resumen import eur, eur_con_signo

# (clave, rótulo, importe del programa, siempre a la vista). Recargo,
# retención y suplidos salen si el programa tiene algo, si se teclea algo o
# si se piden con «+ recargo, retención y suplidos».
CONCEPTOS = (
    ("base", "Base", lambda t: t.base, True),
    ("iva", "IVA", lambda t: t.iva, True),
    ("requiv", "Recargo", lambda t: t.requiv, False),
    ("irpf", "Retención", lambda t: -t.irpf, False),
    ("suplidos", "Suplidos", lambda t: t.suplidos, False),
    ("total", "Total", lambda t: t.total, True),
)
# Lo que se compara cuando los gastos van por el total (recargo).
SOLO_TOTAL = ("irpf", "total")
TIPOS = (("Gastos", "gasto"), ("Ingresos", "venta"))
# Más de esto no es un importe de un lote de facturas: es un error al teclear.
IMPORTE_MAXIMO = 1e12


def _miles(parte: str, separador: str) -> bool:
    """¿Es `parte` un entero con separador de miles bien puesto (1.234.567)?"""
    return re.fullmatch(r"\d{1,3}(?:%s\d{3})+" % re.escape(separador),
                        parte) is not None


def leer_importe(texto) -> float | None:
    """Lo tecleado como importe, o None si no se entiende sin dudas.

    Vale «4.347,51», «4347,51 €», «4347.51», «4,347.51» (formato inglés:
    el último separador es el decimal), «−22,50» y «22,50-». Un punto con
    tres cifras detrás es de miles («4.347» = 4347), como en España. Más de
    dos decimales no es un importe en euros: «4,347» no se adivina.
    """
    if texto is None:
        return None
    t = (str(texto).replace("−", "-").replace(" ", "").replace(" ", "")
         .replace("€", "").strip())
    if t.endswith("-") and not t.startswith("-"):
        t = "-" + t[:-1]
    signo = 1.0
    if t[:1] in ("+", "-") and t:
        signo = -1.0 if t[0] == "-" else 1.0
        t = t[1:]
    if not t or not re.fullmatch(r"[\d.,]+", t) or not re.search(r"\d", t):
        return None
    comas, puntos = t.count(","), t.count(".")
    if comas and puntos:
        decimal = "," if t.rfind(",") > t.rfind(".") else "."
        miles = "." if decimal == "," else ","
        entero, _, fraccion = t.rpartition(decimal)
        if (t.count(decimal) != 1 or not fraccion.isdigit() or len(fraccion) > 2
                or not (_miles(entero, miles) or entero.isdigit())):
            return None
        valor = float(entero.replace(miles, "") + "." + fraccion)
    elif comas or puntos:
        separador = "," if comas else "."
        if t.count(separador) > 1:
            if not _miles(t, separador):
                return None
            valor = float(t.replace(separador, ""))
        else:
            entero, fraccion = t.split(separador)
            if not fraccion.isdigit() or not (entero.isdigit() or entero == ""):
                return None
            if (separador == "." and len(fraccion) == 3
                    and 1 <= len(entero) <= 3 and entero[0] != "0"):
                valor = float(entero + fraccion)        # 4.347 = cuatro mil
            elif len(fraccion) > 2:
                return None          # «4,347»: ¿cuatro mil o cuatro con algo?
            else:
                valor = float((entero or "0") + "." + fraccion)
    else:
        valor = float(t)
    valor *= signo
    if not math.isfinite(valor) or abs(valor) >= IMPORTE_MAXIMO:
        return None
    return valor


def comparar(clave: str, programa: float, suya: float) -> tuple[float, float]:
    """(cifra del programa tal como la escribe el usuario, programa − suya).

    La retención resta: la columna la enseña en negativo, pero mucha gente
    la escribe en positivo. Si la escribe en positivo se compara en positivo,
    y la diferencia y la ayuda hablan en ese mismo convenio.
    """
    if clave == "irpf" and suya >= 0:
        programa = -programa
    return programa, round(programa - suya, 2)


def diferencia(clave: str, programa: float, suya: float) -> float:
    """Programa − su suma (en el convenio de signo que use el usuario)."""
    return comparar(clave, programa, suya)[1]


class CajaSuSuma(QFrame):
    """Casillas para teclear la suma propia y ver al lado la diferencia."""

    # Se ha tecleado algo o se ha cambiado Gastos/Ingresos: la ventana lleva
    # la vista de totales al bloque con el que se compara.
    cambiado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cajaSuSuma")
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 6, 0, 2)
        capa.setSpacing(4)
        cabecera = QHBoxLayout()
        cabecera.setSpacing(6)
        self.btn_plegar = QToolButton()
        self.btn_plegar.setObjectName("plegarSeccion")
        self.btn_plegar.setText("Su suma a mano")
        self.btn_plegar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_plegar.setCheckable(True)
        self.btn_plegar.setAutoRaise(True)
        self.btn_plegar.setToolTip(
            "Escriba lo que le da a usted (a mano o en el listado de "
            "Aplifisa) y vea al lado si cuadra con el programa.")
        cabecera.addWidget(self.btn_plegar, 1)
        self.combo_tipo = QComboBox()
        for texto, tipo in TIPOS:
            self.combo_tipo.addItem(texto, tipo)
        self.combo_tipo.setToolTip("Qué totales quiere cuadrar.")
        self.combo_tipo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        cabecera.addWidget(self.combo_tipo)
        capa.addLayout(cabecera)

        self.cuerpo = QWidget()
        rejilla = QGridLayout(self.cuerpo)
        rejilla.setContentsMargins(4, 0, 0, 0)
        rejilla.setHorizontalSpacing(6)
        rejilla.setVerticalSpacing(3)
        self.lbl_ambito = QLabel()
        self.lbl_ambito.setWordWrap(True)
        self.lbl_ambito.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        rejilla.addWidget(self.lbl_ambito, 0, 0, 1, 3)
        # Encabezados: que «+35,55 €» se lea como «el programa da 35,55 más».
        for columna, texto in ((1, "Su cifra"), (2, "Programa da")):
            encabezado = QLabel(texto)
            encabezado.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
            rejilla.addWidget(encabezado, 1, columna)
        negrita = QFont(self.font())
        negrita.setBold(True)
        ancho_resultado = QFontMetrics(negrita).horizontalAdvance("−99.999,99 €") + 4
        self._filas = {}
        for i, (clave, rotulo, _importe, _siempre) in enumerate(CONCEPTOS, 2):
            etiqueta = QLabel(rotulo)
            campo = QLineEdit()
            campo.setObjectName("suSuma")
            campo.setPlaceholderText("su cifra")
            campo.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            campo.setFixedWidth(76)
            resultado = QLabel()
            # A la izquierda: si no cupiera, se corta el final, nunca el signo.
            resultado.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            resultado.setMinimumWidth(ancho_resultado)
            campo.textChanged.connect(self._al_teclear)
            rejilla.addWidget(etiqueta, i, 0)
            rejilla.addWidget(campo, i, 1)
            rejilla.addWidget(resultado, i, 2)
            self._filas[clave] = (etiqueta, campo, resultado)
        fila = len(CONCEPTOS) + 2
        self.btn_mas = QToolButton()
        self.btn_mas.setObjectName("enlaceSuSuma")
        self.btn_mas.setAutoRaise(True)
        self.btn_mas.setCheckable(True)
        self.btn_mas.setToolTip(
            "Comparar también el recargo, la retención y los suplidos, aunque "
            "el programa no tenga ninguno (por si se le ha escapado alguno).")
        self.btn_mas.setChecked(bool(ajustes.leer("su_suma_todas", False)))
        self.btn_mas.toggled.connect(self._al_pedir_mas)
        rejilla.addWidget(self.btn_mas, fila, 0, 1, 3)
        # Una sola línea: en una columna estrecha y baja, un texto de varias
        # líneas se montaría encima de lo de abajo. Lo largo, en el globo.
        self.lbl_veredicto = QLabel()
        rejilla.addWidget(self.lbl_veredicto, fila + 1, 0, 1, 3)
        rejilla.setColumnStretch(0, 1)
        capa.addWidget(self.cuerpo)

        # Lo tecleado, por tipo: al pasar de Gastos a Ingresos no se pierde.
        self._valores = {tipo: {} for _texto, tipo in TIPOS}
        # tipo -> (Totales, de qué son, ¿van por el total?)
        self._totales: dict = {}
        self._cargando = False
        self.combo_tipo.currentIndexChanged.connect(self._al_cambiar_tipo)
        self.btn_plegar.toggled.connect(self._plegar)
        self.btn_plegar.setChecked(bool(ajustes.leer("su_suma_abierta", True)))
        self._plegar(self.btn_plegar.isChecked())

    # ------------------------------------------------------------ datos
    @property
    def tipo(self) -> str:
        return self.combo_tipo.currentData()

    def actualizar(self, totales: dict) -> None:
        """`totales`: tipo -> (Totales, de qué son, ¿van por el total?)."""
        self._totales = dict(totales)
        self._pintar()

    def valores(self) -> dict:
        """Lo tecleado, para guardarlo en la sesión."""
        return {tipo: dict(campos) for tipo, campos in self._valores.items()}

    def poner_valores(self, valores) -> None:
        self._valores = {tipo: {} for _texto, tipo in TIPOS}
        if isinstance(valores, dict):
            for tipo, campos in valores.items():
                if tipo in self._valores and isinstance(campos, dict):
                    self._valores[tipo] = {
                        clave: str(texto) for clave, texto in campos.items()
                        if clave in self._filas}
        self._cargar_campos()

    def limpiar(self) -> None:
        self.poner_valores({})

    # ------------------------------------------------------------ pantalla
    def _plegar(self, abierta: bool) -> None:
        self.cuerpo.setVisible(abierta)
        self.btn_plegar.setArrowType(Qt.DownArrow if abierta else Qt.RightArrow)
        ajustes.guardar("su_suma_abierta", bool(abierta))

    def _al_pedir_mas(self, todas: bool) -> None:
        ajustes.guardar("su_suma_todas", bool(todas))
        self._pintar()

    def _al_cambiar_tipo(self) -> None:
        self._cargar_campos()
        self.cambiado.emit()

    def _cargar_campos(self) -> None:
        self._cargando = True
        try:
            for clave, (_etiqueta, campo, _resultado) in self._filas.items():
                campo.setText(self._valores[self.tipo].get(clave, ""))
        finally:
            self._cargando = False
        self._pintar()

    def _al_teclear(self) -> None:
        if self._cargando:
            return
        self._valores[self.tipo] = {
            clave: campo.text() for clave, (_e, campo, _r) in self._filas.items()
            if campo.text().strip()}
        self._pintar()
        self.cambiado.emit()

    def _pintar(self) -> None:
        nombre = self.combo_tipo.currentText().lower()
        t, ambito, solo_total = self._totales.get(self.tipo, (None, "", False))
        if t is None:
            self.lbl_ambito.setText(f"No hay {nombre} en el lote.")
        elif solo_total:
            self.lbl_ambito.setText(
                f"Se compara con: {ambito}. Cliente en recargo: los gastos van "
                "por el total factura; compare el total.")
        else:
            self.lbl_ambito.setText(f"Se compara con: {ambito}.")
        todas = self.btn_mas.isChecked()
        tecleadas = cuadran = 0
        signos = set()
        hay_ocultables = False
        for clave, rotulo, importe, siempre in CONCEPTOS:
            etiqueta, campo, resultado = self._filas[clave]
            programa = importe(t) if t is not None else 0.0
            texto = campo.text().strip()
            if solo_total and clave not in SOLO_TOTAL:
                visible = False                # no existe: va dentro del total
            else:
                visible = siempre or todas or abs(programa) >= 0.005 or bool(texto)
                hay_ocultables |= not siempre and not visible
            for widget in (etiqueta, campo, resultado):
                widget.setVisible(visible)
            if not texto or not visible:
                resultado.setText("")
                resultado.setToolTip("")
                continue
            tecleadas += 1
            suya = leer_importe(texto)
            if suya is None:
                resultado.setText("¿cifra?")
                resultado.setStyleSheet(f"color: {WARNING};")
                resultado.setToolTip(
                    "No se entiende sin dudas. Escriba un importe, por ejemplo "
                    "4.347,51")
                continue
            programa_suyo, dif = comparar(clave, programa, suya)
            if abs(dif) < 0.005:
                cuadran += 1
                resultado.setText("✓ cuadra")
                resultado.setStyleSheet(f"color: {SUCCESS}; font-weight: 600;")
                resultado.setToolTip(
                    f"El programa también da {eur_con_signo(programa_suyo)}.")
            else:
                signos.add(dif > 0)
                resultado.setText(f"{'+' if dif > 0 else '−'}{eur(abs(dif))}")
                resultado.setStyleSheet(f"color: {DANGER}; font-weight: 600;")
                resultado.setToolTip(
                    f"{rotulo}: el programa da {eur_con_signo(programa_suyo)}, "
                    f"{eur(abs(dif))} {'más' if dif > 0 else 'menos'} que su "
                    f"suma ({eur_con_signo(suya)}).")
        self.btn_mas.setVisible(not solo_total and (hay_ocultables or todas))
        self.btn_mas.setText("− menos cifras" if todas else
                             "+ recargo, retención y suplidos")
        if not tecleadas:
            self.lbl_veredicto.setText("")
            self.lbl_veredicto.setToolTip("")
        elif cuadran == tecleadas:
            self.lbl_veredicto.setText("✓ Todo lo que ha escrito cuadra.")
            self.lbl_veredicto.setStyleSheet(f"color: {SUCCESS}; font-weight: 600;")
            self.lbl_veredicto.setToolTip("")
        else:
            if signos == {True}:
                texto = "✗ El programa da más."
                ayuda = ("Puede que a su suma le falte una factura o que en "
                         "el lote sobre una. ")
            elif signos == {False}:
                texto = "✗ El programa da menos."
                ayuda = ("Puede que falte una factura en el lote o que su "
                         "suma tenga una de más. ")
            else:
                texto = f"✗ {tecleadas - cuadran} cifra(s) no cuadran."
                ayuda = ""
            self.lbl_veredicto.setText(texto)
            self.lbl_veredicto.setStyleSheet(f"color: {DANGER}; font-weight: 600;")
            self.lbl_veredicto.setToolTip(
                ayuda + "Filtre por mes para acotar la factura y compare con "
                "el listado de Aplifisa.")
