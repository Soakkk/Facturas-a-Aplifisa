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

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QWidget,
)

from .estilo import DANGER, MUTED, SUCCESS, WARNING
from .ventana_comun import EtiquetaRecortada
from .resumen import eur, eur_con_signo, porcentaje_iva

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


# Columnas de la tabla de totales (y de «Su suma», debajo, alineada con
# ellas): (clave, cabecera, importe del programa). El IVA va además por tipo.
COLUMNAS_FIJAS = (
    ("base", "Base imponible", lambda t: t.base),
    ("iva", "Total IVA", lambda t: t.iva),
    ("requiv", "Recargo", lambda t: t.requiv),
    ("irpf", "Retención", lambda t: -t.irpf),
    ("suplidos", "Suplidos", lambda t: t.suplidos),
    ("total", "Total", lambda t: t.total),
)
# Lo que se compara cuando los gastos van por el total (recargo).
SOLO_TOTAL = ("irpf", "total")
# Antes de los importes: el ámbito («Gastos · Todo el lote») y el nº.
PRIMERA_COLUMNA_IMPORTE = 2


def columnas_totales(tipos_iva, sin_tipo: bool = False) -> list:
    """Las columnas de importes, con una de IVA por tipo (de mayor a menor)."""
    columnas = [COLUMNAS_FIJAS[0]]
    for p in sorted(tipos_iva, reverse=True):
        texto = porcentaje_iva(p)
        columnas.append((f"iva_{texto}", f"IVA {texto} %",
                         lambda t, p=p: t.iva_por_tipo.get(p, 0.0)))
    if sin_tipo:
        columnas.append(("iva_sin_tipo", "IVA sin tipo",
                         lambda t: t.iva_sin_tipo))
    columnas.extend(COLUMNAS_FIJAS[1:])
    return columnas


class TablaTotales(QTableWidget):
    """Los totales como el listado de Aplifisa (la rellena la ventana).

    Avisa cuando cambia su ancho útil: la primera columna se queda con lo
    que sobra, pero nunca menos que su texto, y «Su suma» va igual.
    """

    redimensionada = Signal()

    def viewportEvent(self, evento):
        if evento.type() == QEvent.Resize:
            self.redimensionada.emit()
        return super().viewportEvent(evento)


class TablaSuSuma(QTableWidget):
    """«Su suma a mano»: una fila de casillas bajo la tabla de totales.

    Cada casilla queda debajo de su columna (base, cada IVA, recargo,
    retención, suplidos, total) y en la fila de abajo sale si cuadra o
    cuánto da de más o de menos el programa. Compara con la fila de los
    totales que se ve resaltada: con un filtro, lo filtrado.
    """

    # Se ha tecleado algo o se ha cambiado Gastos/Ingresos.
    cambiado = Signal()

    def __init__(self, parent=None):
        super().__init__(2, PRIMERA_COLUMNA_IMPORTE, parent)
        self.setObjectName("tablaSuSuma")
        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setVisible(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setShowGrid(False)
        # El tabulador va de casilla en casilla y sale de la tabla (no se
        # queda dando vueltas por celdas que no se pueden elegir).
        self.setTabKeyNavigation(False)
        # Se desplaza a la vez que los totales, píxel a píxel.
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalHeader().setDefaultSectionSize(30)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        # Primera columna: «Su suma» con Gastos/Ingresos; y «Programa da».
        primera = QWidget()
        capa = QHBoxLayout(primera)
        capa.setContentsMargins(6, 0, 4, 0)
        capa.setSpacing(6)
        # Corto: en una pantalla de 1024 la columna es estrecha.
        rotulo = QLabel("Su suma")
        rotulo.setStyleSheet("font-weight: 600;")
        rotulo.setToolTip(
            "Su suma a mano (o la del listado de Aplifisa), columna por "
            "columna, para compararla con la del programa.")
        capa.addWidget(rotulo)
        self.combo_tipo = QComboBox()
        for texto, tipo in TIPOS:
            self.combo_tipo.addItem(texto, tipo)
        self.combo_tipo.setToolTip("Qué totales quiere cuadrar.")
        capa.addWidget(self.combo_tipo)
        capa.addStretch(1)
        self.setCellWidget(0, 0, primera)
        diferencia = QTableWidgetItem("Programa da")
        diferencia.setToolTip(
            "Lo que da el programa menos lo que ha escrito usted: «+35,55 €» "
            "es que el programa da 35,55 € más.")
        diferencia.setForeground(QColor(MUTED))
        self.setItem(1, 0, diferencia)
        # Fuera de la tabla (la ventana los coloca en la cabecera).
        self.lbl_ambito = EtiquetaRecortada()
        self.lbl_ambito.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        self.lbl_veredicto = QLabel()
        # Lo tecleado, por tipo y por columna: al pasar de Gastos a Ingresos,
        # o al cambiar las columnas de IVA, no se pierde.
        self._valores = {tipo: {} for _texto, tipo in TIPOS}
        self._columnas = []                      # [(clave, cabecera, importe)]
        self._hueco = 0                          # ancho de la columna de relleno
        self._campos = {}                        # clave -> QLineEdit
        # tipo -> (Totales, de qué son, ¿van por el total?)
        self._totales: dict = {}
        self._cargando = False
        self.combo_tipo.currentIndexChanged.connect(self._al_cambiar_tipo)
        # La barra de desplazamiento (si no cabe a lo ancho) va debajo de
        # las dos filas, sin taparlas.
        self.horizontalScrollBar().rangeChanged.connect(
            lambda *_: self._ajustar_alto())
        self._ajustar_alto()

    def _ajustar_alto(self) -> None:
        barra = self.horizontalScrollBar()
        extra = barra.sizeHint().height() if barra.maximum() > 0 else 0
        alto = 2 * 30 + 2 * self.frameWidth() + extra
        if self.height() != alto or self.minimumHeight() != alto:
            self.setFixedHeight(alto)

    # ------------------------------------------------------------ datos
    @property
    def tipo(self) -> str:
        return self.combo_tipo.currentData()

    def configurar(self, columnas) -> None:
        """Pone una casilla bajo cada columna de importe de los totales."""
        claves = [c[0] for c in columnas]
        if claves == [c[0] for c in self._columnas]:
            self._columnas = list(columnas)
            return
        self._columnas = list(columnas)
        # Las casillas de antes, fuera ya: se sueltan de su celda (si no, la
        # tabla las vuelve a enseñar) y se ocultan, porque Qt las borra más
        # tarde y mientras tanto se verían donde estaban.
        for c in range(PRIMERA_COLUMNA_IMPORTE, self.columnCount()):
            self.removeCellWidget(0, c)
        for campo in self._campos.values():
            campo.hide()
            campo.deleteLater()
        self.setColumnCount(PRIMERA_COLUMNA_IMPORTE + len(columnas)
                            + (1 if self._hueco else 0))
        self._campos = {}
        for i, (clave, cabecera, _importe) in enumerate(columnas):
            c = PRIMERA_COLUMNA_IMPORTE + i
            campo = QLineEdit()
            campo.setObjectName("suSuma")
            campo.setPlaceholderText("su cifra")
            campo.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            campo.setToolTip(f"{cabecera}: escriba lo que le da a usted.")
            campo.textChanged.connect(self._al_teclear)
            self.setCellWidget(0, c, campo)
            resultado = QTableWidgetItem("")
            resultado.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.setItem(1, c, resultado)
            self._campos[clave] = campo
        self._cargar_campos()

    def actualizar(self, totales: dict) -> None:
        """`totales`: tipo -> (Totales, de qué son, ¿van por el total?)."""
        self._totales = dict(totales)
        self._pintar()

    def dejar_hueco(self, ancho: int) -> None:
        """Una columna vacía al final del ancho de la barra de los totales
        de encima: así las dos tablas se desplazan lo mismo a lo ancho y
        cada casilla sigue bajo su columna también al final."""
        ancho = max(0, int(ancho))
        columnas = PRIMERA_COLUMNA_IMPORTE + len(self._columnas)
        self._hueco = ancho
        if self.columnCount() != columnas + (1 if ancho else 0):
            self.setColumnCount(columnas + (1 if ancho else 0))
        if ancho:
            self.horizontalHeader().setSectionResizeMode(columnas, QHeaderView.Fixed)
            if self.columnWidth(columnas) != ancho:
                self.setColumnWidth(columnas, ancho)

    def campo(self, clave: str) -> QLineEdit:
        return self._campos[clave]

    def resultado(self, clave: str) -> str:
        c = PRIMERA_COLUMNA_IMPORTE + [k for k, *_ in self._columnas].index(clave)
        return self.item(1, c).text()

    def valores(self) -> dict:
        """Lo tecleado, para guardarlo en la sesión."""
        return {tipo: dict(campos) for tipo, campos in self._valores.items()}

    def poner_valores(self, valores) -> None:
        self._valores = {tipo: {} for _texto, tipo in TIPOS}
        if isinstance(valores, dict):
            for tipo, campos in valores.items():
                if tipo in self._valores and isinstance(campos, dict):
                    self._valores[tipo] = {
                        str(clave): str(texto) for clave, texto in campos.items()
                        if str(texto).strip()}
        self._cargar_campos()

    def limpiar(self) -> None:
        self.poner_valores({})

    # ------------------------------------------------------------ pantalla
    def _al_cambiar_tipo(self) -> None:
        self._cargar_campos()
        self.cambiado.emit()

    def _cargar_campos(self) -> None:
        self._cargando = True
        try:
            for clave, campo in self._campos.items():
                campo.setText(self._valores[self.tipo].get(clave, ""))
        finally:
            self._cargando = False
        self._pintar()

    def _al_teclear(self) -> None:
        if self._cargando:
            return
        propios = {clave: campo.text() for clave, campo in self._campos.items()
                   if campo.text().strip()}
        # Lo de columnas que ahora no se ven (otro tipo de IVA) se conserva.
        otros = {clave: texto for clave, texto in self._valores[self.tipo].items()
                 if clave not in self._campos}
        self._valores[self.tipo] = {**otros, **propios}
        self._pintar()
        self.cambiado.emit()

    def _pintar(self) -> None:
        nombre = self.combo_tipo.currentText().lower()
        t, ambito, solo_total = self._totales.get(self.tipo, (None, "", False))
        if t is None:
            self.lbl_ambito.setText(f"No hay {nombre} en el lote.")
        elif solo_total:
            self.lbl_ambito.setText(
                f"Su suma se compara con: {ambito}. Cliente en recargo: los "
                "gastos van por el total factura; compare el total.")
        else:
            self.lbl_ambito.setText(f"Su suma se compara con: {ambito}.")
        tecleadas = cuadran = 0
        signos = set()
        for i, (clave, cabecera, importe) in enumerate(self._columnas):
            c = PRIMERA_COLUMNA_IMPORTE + i
            campo, resultado = self._campos[clave], self.item(1, c)
            fuera = bool(solo_total and clave not in SOLO_TOTAL)
            campo.setEnabled(not fuera)
            campo.setPlaceholderText("—" if fuera else "su cifra")
            texto = campo.text().strip()
            resultado.setText("")
            resultado.setToolTip("")
            resultado.setFont(QFont(self.font()))
            if not texto or fuera:
                continue
            tecleadas += 1
            suya = leer_importe(texto)
            negrita = QFont(self.font())
            negrita.setBold(True)
            resultado.setFont(negrita)
            if suya is None:
                resultado.setText("¿cifra?")
                resultado.setForeground(QColor(WARNING))
                resultado.setToolTip(
                    "No se entiende sin dudas. Escriba un importe, por ejemplo "
                    "4.347,51")
                continue
            programa = importe(t) if t is not None else 0.0
            programa_suyo, dif = comparar(clave, programa, suya)
            if abs(dif) < 0.005:
                cuadran += 1
                resultado.setText("✓ cuadra")
                resultado.setForeground(QColor(SUCCESS))
                resultado.setToolTip(
                    f"El programa también da {eur_con_signo(programa_suyo)}.")
            else:
                signos.add(dif > 0)
                resultado.setText(f"{'+' if dif > 0 else '−'}{eur(abs(dif))}")
                resultado.setForeground(QColor(DANGER))
                resultado.setToolTip(
                    f"{cabecera}: el programa da {eur_con_signo(programa_suyo)}, "
                    f"{eur(abs(dif))} {'más' if dif > 0 else 'menos'} que su "
                    f"suma ({eur_con_signo(suya)}).")
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
