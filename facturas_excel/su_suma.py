"""«Cuadrar con su suma»: la cifra del usuario junto a la del programa.

El usuario lo pidió para comprobar su suma a mano (o el listado de Aplifisa)
con lo que da el programa sin comparar cifra a cifra con la vista: teclea su
base, su IVA o su total y al lado sale si cuadra o cuánto se separa.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QToolButton, QVBoxLayout, QWidget,
)

from . import ajustes
from .estilo import DANGER, MUTED, SUCCESS, WARNING
from .resumen import Totales, eur, eur_con_signo
from .tabla_facturas import parse_numero

# (clave, rótulo, importe del programa, siempre a la vista). Recargo,
# retención y suplidos solo salen si el programa tiene algo o se teclea algo.
CONCEPTOS = (
    ("base", "Base", lambda t: t.base, True),
    ("iva", "IVA", lambda t: t.iva, True),
    ("requiv", "Recargo", lambda t: t.requiv, False),
    ("irpf", "Retención", lambda t: -t.irpf, False),
    ("suplidos", "Suplidos", lambda t: t.suplidos, False),
    ("total", "Total", lambda t: t.total, True),
)
TIPOS = (("Gastos", "gasto"), ("Ingresos", "venta"))


def leer_importe(texto) -> float | None:
    """Lo tecleado como importe: «4.347,51», «4347.51», «−22,50 €»…"""
    if texto is None:
        return None
    limpio = str(texto).replace("−", "-").replace(" ", "").strip()
    return parse_numero(limpio) if limpio else None


def diferencia(clave: str, programa: float, suya: float) -> float:
    """Programa − su suma. La retención se compara sin signo: unos la
    escriben en negativo y otros no."""
    if clave == "irpf":
        return round(abs(programa) - abs(suya), 2)
    return round(programa - suya, 2)


class CajaSuSuma(QFrame):
    """Casillas para teclear la suma propia y ver al lado la diferencia."""

    # Para guardar lo tecleado en la sesión.
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
        self._filas = {}
        for i, (clave, rotulo, _importe, _siempre) in enumerate(CONCEPTOS, 1):
            etiqueta = QLabel(rotulo)
            campo = QLineEdit()
            campo.setObjectName("suSuma")
            campo.setPlaceholderText("su cifra")
            campo.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            campo.setFixedWidth(84)
            campo.setClearButtonEnabled(False)
            resultado = QLabel()
            resultado.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            resultado.setMinimumWidth(72)
            campo.textChanged.connect(self._al_teclear)
            rejilla.addWidget(etiqueta, i, 0)
            rejilla.addWidget(campo, i, 1)
            rejilla.addWidget(resultado, i, 2)
            self._filas[clave] = (etiqueta, campo, resultado)
        self.lbl_veredicto = QLabel()
        self.lbl_veredicto.setWordWrap(True)
        rejilla.addWidget(self.lbl_veredicto, len(CONCEPTOS) + 1, 0, 1, 3)
        rejilla.setColumnStretch(0, 1)
        capa.addWidget(self.cuerpo)

        # Lo tecleado, por tipo: al pasar de Gastos a Ingresos no se pierde.
        self._valores = {tipo: {} for _texto, tipo in TIPOS}
        # tipo -> (Totales, de qué son: «Gastos · Todo el lote»…)
        self._totales: dict[str, tuple[Totales, str]] = {}
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
        """`totales`: tipo -> (Totales, de qué son). Lo pinta de nuevo."""
        self._totales = dict(totales)
        self._pintar()

    def valores(self) -> dict:
        """Lo tecleado, para guardarlo en la sesión."""
        return {tipo: dict(campos) for tipo, campos in self._valores.items()}

    def poner_valores(self, valores) -> None:
        self._valores = {tipo: {} for _texto, tipo in TIPOS}
        for tipo, campos in (valores or {}).items():
            if tipo in self._valores and isinstance(campos, dict):
                self._valores[tipo] = {clave: str(texto) for clave, texto
                                       in campos.items() if clave in self._filas}
        self._cargar_campos()

    def limpiar(self) -> None:
        self.poner_valores({})

    # ------------------------------------------------------------ pantalla
    def _plegar(self, abierta: bool) -> None:
        self.cuerpo.setVisible(abierta)
        self.btn_plegar.setArrowType(Qt.DownArrow if abierta else Qt.RightArrow)
        ajustes.guardar("su_suma_abierta", bool(abierta))

    def _al_cambiar_tipo(self) -> None:
        self._cargar_campos()

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
        t, ambito = self._totales.get(self.tipo, (None, ""))
        self.lbl_ambito.setText(
            f"Se compara con: {ambito}." if t is not None else
            f"No hay {nombre} en el lote.")
        tecleadas = cuadran = 0
        for clave, rotulo, importe, siempre in CONCEPTOS:
            etiqueta, campo, resultado = self._filas[clave]
            programa = importe(t) if t is not None else 0.0
            texto = campo.text().strip()
            visible = siempre or abs(programa) >= 0.005 or bool(texto)
            for widget in (etiqueta, campo, resultado):
                widget.setVisible(visible)
            if not texto:
                resultado.setText("")
                resultado.setToolTip("")
                continue
            tecleadas += 1
            suya = leer_importe(texto)
            if suya is None:
                resultado.setText("¿cifra?")
                resultado.setStyleSheet(f"color: {WARNING};")
                resultado.setToolTip("Escriba un importe, por ejemplo 4.347,51")
                continue
            dif = diferencia(clave, programa, suya)
            if abs(dif) < 0.005:
                cuadran += 1
                resultado.setText("✓ cuadra")
                resultado.setStyleSheet(f"color: {SUCCESS}; font-weight: 600;")
                resultado.setToolTip(f"El programa también da {eur_con_signo(programa)}.")
            else:
                resultado.setText(f"{'+' if dif > 0 else '−'}{eur(abs(dif))}")
                resultado.setStyleSheet(f"color: {DANGER}; font-weight: 600;")
                resultado.setToolTip(
                    f"{rotulo}: el programa da {eur_con_signo(programa)}, "
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
            faltan = tecleadas - cuadran
            self.lbl_veredicto.setText(f"✗ {faltan} cifra(s) no cuadran.")
            self.lbl_veredicto.setStyleSheet(f"color: {DANGER}; font-weight: 600;")
            self.lbl_veredicto.setToolTip(
                "Busque la factura que falta o sobra: filtre por mes para "
                "acotarla y compare con el listado de Aplifisa.")
