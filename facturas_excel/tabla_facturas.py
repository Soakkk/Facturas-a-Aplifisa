"""La tabla de revisión: enseña las `Fila` del lote y recoge lo que se corrige.

No decide nada: pinta lo que hay en cada factura y, cuando alguien escribe en
una celda, dice qué dato de la factura ha cambiado (`valor_de_celda`).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHeaderView, QTableWidget, QTableWidgetItem,
)

from .conceptos import SUBCLAVES_628
from .lote import CAMPOS_IRPF, CAMPOS_RECARGO, Fila, hay_datos
from .validacion import ERROR

# Un SUPLIDO no tiene columna propia: va como una linea mas del mismo apunte,
# con su base y sin % ni cuota de IVA (es como lo registra Aplifisa).
COLS = ["Estado", "Tipo", "Cuenta", "GXX", "Fecha", "Nº Factura", "Nombre",
        "NIF", "Base", "% IVA", "Cuota", "Base RE", "% RE", "Cuota RE",
        "Base IRPF", "% IRPF", "Retención", "Total", "Bloque"]
C_ESTADO, C_TIPO, C_CUENTA, C_GXX, C_FECHA, C_NUM, C_NOMBRE, C_NIF, \
C_BASE, C_PCT, C_CUOTA, C_BASE_RE, C_PCT_RE, C_CUOTA_RE, C_BASE_IRPF, \
    C_PCT_IRPF, C_CUOTA_IRPF, C_TOTAL, C_BLOQUE = range(len(COLS))
COLUMNAS_RECARGO = (C_BASE_RE, C_PCT_RE, C_CUOTA_RE)
COLUMNAS_IRPF = (C_BASE_IRPF, C_PCT_IRPF, C_CUOTA_IRPF)
# Qué columna muestra cada dato de la Factura (para señalar la celda culpable).
COLUMNA_DE_CAMPO = {
    "fecha": C_FECHA, "num_factura": C_NUM, "nombre": C_NOMBRE, "nif": C_NIF,
    "concepto": C_CUENTA, "subclave": C_GXX, "base_iva": C_BASE,
    "pct_iva": C_PCT, "cuota_iva": C_CUOTA, "base_requiv": C_BASE_RE,
    "pct_requiv": C_PCT_RE, "cuota_requiv": C_CUOTA_RE,
    "base_irpf": C_BASE_IRPF, "pct_irpf": C_PCT_IRPF,
    "cuota_irpf": C_CUOTA_IRPF, "total_impreso": C_TOTAL,
}
CAMPO_DE_COLUMNA = {c: campo for campo, c in COLUMNA_DE_CAMPO.items()}
COLUMNAS_IMPORTE = (C_BASE, C_PCT, C_CUOTA, C_BASE_RE, C_PCT_RE, C_CUOTA_RE,
                    C_BASE_IRPF, C_PCT_IRPF, C_CUOTA_IRPF, C_TOTAL)
COLUMNAS_DATO = tuple(sorted(CAMPO_DE_COLUMNA))
# La tabla con lo justo (distribución «una a una»): cabe en una lista
# estrecha; el resto de datos se ve en la factura, al lado.
COLUMNAS_COMPACTAS = (C_ESTADO, C_NOMBRE, C_TOTAL)
# Los anchos de partida, mientras no hay nada que medir (tabla vacía). Con
# facturas, cada columna mide lo que su contenido (ver `TablaFacturas.medir`).
ANCHOS = {
    C_ESTADO: 108, C_TIPO: 78, C_CUENTA: 58, C_GXX: 50,
    C_FECHA: 86, C_NUM: 100, C_NOMBRE: 160, C_NIF: 96,
    C_BASE: 78, C_PCT: 50, C_CUOTA: 70,
    C_BASE_RE: 78, C_PCT_RE: 50, C_CUOTA_RE: 72,
    C_BASE_IRPF: 78, C_PCT_IRPF: 56, C_CUOTA_IRPF: 74,
    C_TOTAL: 82,
}
# Si con recargo o retenciones no queda sitio, el nombre no baja de aquí
# (la tabla se desplaza en horizontal antes que dejarlo en «PRO…»).
ANCHO_MIN_NOMBRE = 140
# Cada columna, lo que su contenido más este aire, para que se lea bien.
HOLGURA = 22
# Lo de la cabecera (sus márgenes y la flecha de ordenar).
HOLGURA_CABECERA = 30
# Un nombre o un número de factura larguísimo no se come la tabla: se corta
# con «…» (entero en la ficha de la factura).
TOPE = {C_NOMBRE: 380, C_NUM: 200}
# Sin sitio para todo, las de texto se estrechan hasta aquí (los importes y
# las fechas, nunca: un importe cortado engaña).
MINIMO = {C_NOMBRE: ANCHO_MIN_NOMBRE, C_NUM: 96}
# Si sobra sitio, cada columna se lleva como mucho esto de más: repartido
# entre todas, no todo para el nombre (antes se quedaba media tabla en
# blanco al lado de nombres cortos).
AIRE_MAXIMO = 48


def parse_numero(texto):
    if texto is None:
        return None
    t = str(texto).strip()
    if not t:
        return None
    t = t.replace("€", "").replace(" ", "")
    if "," in t:
        # Formato español: 1.234,56
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or (
        t.count(".") == 1 and len(t.rsplit(".", 1)[1]) == 3
    ):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",")
    return str(v)


def texto_celda(fila: Fila, columna: int) -> str:
    if columna == C_BLOQUE:
        return fila.bloque or ""
    campo = CAMPO_DE_COLUMNA.get(columna)
    if not campo:
        return ""
    valor = getattr(fila.factura, campo)
    if columna in COLUMNAS_IMPORTE:
        return fmt(valor)
    return "" if valor is None else str(valor)


def valor_de_celda(columna: int, texto: str):
    """(campo, valor) de la factura que corresponde a lo escrito en la celda."""
    campo = CAMPO_DE_COLUMNA.get(columna)
    if not campo:
        return None, None
    if columna in COLUMNAS_IMPORTE:
        return campo, parse_numero(texto)
    if columna == C_GXX:
        return campo, (texto or "").strip().upper() or None
    return campo, texto or None


class _SinRueda:
    """Ignora la rueda del raton para que no cambie el valor sin querer.

    Bajando por el listado con la rueda, al pasar por encima de un desplegable
    este se tragaba el giro y cambiaba gasto<->venta en silencio. El valor solo
    debe cambiarse haciendo clic; la rueda tiene que seguir moviendo la tabla,
    asi que el evento se deja pasar al padre.
    """

    def wheelEvent(self, evento):
        evento.ignore()


class ComboSinRueda(_SinRueda, QComboBox):
    pass


AYUDA_GXX = ("Subclave del suministro. En Aplifisa la 628 NO puede ir sin ella:\n"
             + "\n".join(f"  {g} = {d}" for g, d in SUBCLAVES_628.items()))
AYUDA_SUPLIDO = ("SUPLIDO: se registra como una línea de base más del mismo "
                 "apunte, sin IVA (así lo pide Aplifisa).")


class TablaFacturas(QTableWidget):
    """La tabla de la mesa de revisión."""

    # Intro (sin editar una celda): a la siguiente pendiente.
    # Ctrl+Intro: dar por buena la que se ve y pasar a la siguiente.
    intro = Signal()
    ctrl_intro = Signal()
    # Una persona ha ensanchado o estrechado columnas: {título: ancho}.
    anchos_a_mano_cambiados = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(0, len(COLS), parent)
        self.setAlternatingRowColors(True)
        self.setHorizontalHeaderLabels(COLS)
        # Cada título, alineado como lo que tiene debajo (los importes a la
        # derecha): con columnas a su medida, un título centrado quedaba
        # descolgado de su texto.
        for c in range(len(COLS)):
            self.horizontalHeaderItem(c).setTextAlignment(
                Qt.AlignCenter if c == C_ESTADO else
                Qt.AlignRight | Qt.AlignVCenter if c in COLUMNAS_IMPORTE else
                Qt.AlignLeft | Qt.AlignVCenter)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setDefaultSectionSize(38)
        # Anchos: cada columna, lo que su contenido (`medir`); lo que una
        # persona ensancha a mano se queda así (`_a_mano`) y doble clic en
        # el borde la vuelve a ajustar al contenido.
        self._naturales = dict(ANCHOS)
        self._a_mano: dict[int, int] = {}
        self._ajustando = False
        self._arrastrando = False
        self._soltar_a_mano = False
        self._timer_medir = QTimer(self)
        self._timer_medir.setSingleShot(True)
        self._timer_medir.setInterval(0)
        self._timer_medir.timeout.connect(self.medir)
        self.model().rowsRemoved.connect(lambda *_: self._medida_pendiente())
        cabecera = self.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.Interactive)
        cabecera.setSectionsClickable(True)
        cabecera.setMinimumSectionSize(40)
        cabecera.setToolTip("Arrastre el borde de una columna para ensancharla. "
                            "Doble clic en el borde: ajustarla a lo que pone.")
        cabecera.viewport().installEventFilter(self)
        cabecera.sectionHandleDoubleClicked.connect(self.ajustar_al_contenido)
        for columna, ancho in ANCHOS.items():
            self.setColumnWidth(columna, ancho)
        # Bloque ya está en el filtro; recargo y retenciones se enseñan solo
        # cuando tocan (ver `columnas_visibles`).
        self.setColumnHidden(C_BLOQUE, True)
        for columna in COLUMNAS_RECARGO:
            self.setColumnHidden(columna, True)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        cabecera.sectionResized.connect(self._al_redimensionar_columna)

    def keyPressEvent(self, evento):
        # Mientras se edita una celda, Intro lo recibe el editor (confirma lo
        # escrito) y no llega aquí.
        if (evento.key() in (Qt.Key_Return, Qt.Key_Enter)
                and self.state() != QAbstractItemView.EditingState):
            modificadores = evento.modifiers() & ~Qt.KeypadModifier
            if modificadores == Qt.ControlModifier:
                self.ctrl_intro.emit()
                evento.accept()
                return
            if modificadores == Qt.NoModifier:
                self.intro.emit()
                evento.accept()
                return
        super().keyPressEvent(evento)

    # ------------------------------------------------------------ anchos
    def setColumnHidden(self, columna: int, oculta: bool) -> None:
        super().setColumnHidden(columna, oculta)
        self.repartir()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self.repartir()

    def eventFilter(self, objeto, evento):
        # Solo lo que se arrastra con el ratón cuenta como «a mano» (Qt
        # también avisa de lo que cambia él al ocultar o repartir).
        if objeto is self.horizontalHeader().viewport():
            tipo = evento.type()
            izquierdo = tipo in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease) \
                and evento.button() == Qt.LeftButton
            if tipo == QEvent.MouseButtonPress and izquierdo:
                self._arrastrando = True
            elif tipo == QEvent.MouseButtonRelease and izquierdo:
                self._arrastrando = False
                if self._soltar_a_mano:
                    self._soltar_a_mano = False
                    self.anchos_a_mano_cambiados.emit(self.anchos_a_mano())
                    self.repartir()
        return super().eventFilter(objeto, evento)

    def _al_redimensionar_columna(self, columna, _antes, ahora) -> None:
        if self._ajustando or not self._arrastrando:
            return
        self._a_mano[columna] = ahora
        self._soltar_a_mano = True

    def anchos_a_mano(self) -> dict:
        """{título de la columna: ancho} de las que ha puesto una persona."""
        return {COLS[c]: w for c, w in sorted(self._a_mano.items())}

    def poner_anchos_a_mano(self, anchos) -> None:
        """Los anchos que se guardaron (por título: sobrevive a columnas
        nuevas). Lo que no se reconoce se ignora."""
        self._a_mano = {}
        for titulo, ancho in (anchos or {}).items():
            if titulo in COLS and isinstance(ancho, (int, float)) and ancho >= 20:
                self._a_mano[COLS.index(titulo)] = int(ancho)
        self.repartir()

    def ajustar_al_contenido(self, columna: int | None = None) -> None:
        """Olvida lo puesto a mano (en esa columna o en todas)."""
        if columna is None:
            self._a_mano.clear()
        else:
            self._a_mano.pop(columna, None)
        self._arrastrando = self._soltar_a_mano = False
        self.anchos_a_mano_cambiados.emit(self.anchos_a_mano())
        self.repartir()

    def _medida_pendiente(self) -> None:
        if not self._timer_medir.isActive():
            self._timer_medir.start()

    def medir(self) -> None:
        """Lo que pide cada columna: su texto más largo (en negrita si va en
        negrita) o su título, con aire para que se lea bien."""
        if self.rowCount() == 0:
            self._naturales = dict(ANCHOS)
            self.repartir()
            return
        normal = QFont(self.font())
        negrita = QFont(normal)
        negrita.setBold(True)
        medidas = {False: QFontMetrics(normal), True: QFontMetrics(negrita)}
        cabecera = self.horizontalHeader().fontMetrics()
        naturales = {}
        for c in range(self.columnCount()):
            if c == C_BLOQUE:
                continue
            ancho = cabecera.horizontalAdvance(COLS[c]) + HOLGURA_CABECERA
            if c == C_TIPO:
                combo = self.cellWidget(0, C_TIPO)
                contenido = combo.sizeHint().width() if combo else ANCHOS[c]
            else:
                contenido = 0
                for r in range(self.rowCount()):
                    item = self.item(r, c)
                    if item is None or not item.text():
                        continue
                    medida = medidas[item.font().bold()]
                    contenido = max(contenido, medida.horizontalAdvance(item.text()))
                contenido += HOLGURA
            naturales[c] = min(max(ancho, contenido), TOPE.get(c, 10_000))
        self._naturales = naturales
        self.repartir()

    def ancho_natural(self, columna: int) -> int:
        return self._naturales.get(columna, ANCHOS.get(columna, 80))

    def repartir(self) -> None:
        """Cada columna a su medida (o la puesta a mano). Si no cabe todo, se
        estrechan el nombre y el número; si sobra, el aire se reparte entre
        todas las que no se han puesto a mano."""
        if self._ajustando:
            return
        visibles = [c for c in range(self.columnCount()) if not self.isColumnHidden(c)]
        if not visibles:
            return
        anchos = {c: self._a_mano.get(c, self.ancho_natural(c)) for c in visibles}
        libres = [c for c in visibles if c not in self._a_mano]
        sitio = self.viewport().width()
        total = sum(anchos.values())
        if total > sitio:
            holgura = {c: anchos[c] - MINIMO[c] for c in libres
                       if c in MINIMO and anchos[c] > MINIMO[c]}
            if holgura:
                parte = min(1.0, (total - sitio) / sum(holgura.values()))
                for c, h in holgura.items():
                    anchos[c] -= round(h * parte)
        elif libres:
            sobra = sitio - total
            aire = min(AIRE_MAXIMO, sobra // len(libres))
            for c in libres:
                anchos[c] += aire
            if aire < AIRE_MAXIMO:
                # Los últimos píxeles, al nombre (o a la última): sin rendija.
                resto = C_NOMBRE if C_NOMBRE in libres else libres[-1]
                anchos[resto] += sobra - aire * len(libres)
        self._ajustando = True
        try:
            for c, ancho in anchos.items():
                if self.columnWidth(c) != ancho:
                    self.setColumnWidth(c, ancho)
        finally:
            self._ajustando = False

    # ------------------------------------------------------------ filas
    def insertar(self, r: int, fila: Fila, al_cambiar_tipo) -> None:
        """Crea la fila `r` con sus celdas y su desplegable Gasto/Ingreso."""
        bloqueadas = self.signalsBlocked()
        self.blockSignals(True)
        self.insertRow(r)
        est = QTableWidgetItem("")
        est.setFlags(Qt.ItemIsEnabled)
        est.setTextAlignment(Qt.AlignCenter)
        self.setItem(r, C_ESTADO, est)
        combo = ComboSinRueda()
        combo.addItem("Gasto", "gasto")
        combo.addItem("Ingreso", "venta")
        combo.currentIndexChanged.connect(
            lambda _i, control=combo: al_cambiar_tipo(control))
        self.setCellWidget(r, C_TIPO, combo)
        for columna in (*COLUMNAS_DATO, C_BLOQUE):
            item = QTableWidgetItem("")
            if columna in COLUMNAS_IMPORTE:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if columna == C_BLOQUE:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setToolTip("Escaneo o PDF del que salió esta factura.")
            elif columna == C_GXX:
                item.setToolTip(AYUDA_GXX)
            elif columna == C_BASE and getattr(fila.factura, "es_suplido", False):
                item.setToolTip(AYUDA_SUPLIDO)
            self.setItem(r, columna, item)
        self.setRowHeight(r, 34)
        self.pintar(r, fila)
        self.blockSignals(bloqueadas)
        self._medida_pendiente()

    def pintar(self, r: int, fila: Fila, columnas=None) -> None:
        """Vuelca en la fila `r` lo que dice la factura (sin avisar a nadie)."""
        bloqueadas = self.signalsBlocked()
        self.blockSignals(True)
        for columna in columnas or (*COLUMNAS_DATO, C_BLOQUE):
            item = self.item(r, columna)
            if item is not None:
                item.setText(texto_celda(fila, columna))
        if columnas is None or C_TIPO in columnas:
            combo = self.cellWidget(r, C_TIPO)
            if combo is not None:
                combo.blockSignals(True)
                combo.setCurrentIndex(max(0, combo.findData(fila.tipo)))
                combo.blockSignals(False)
                aviso = (fila.aviso or "").lower()
                combo.setToolTip(
                    "Clasificación dudosa: compruebe si corresponde a Gasto o Ingreso."
                    if "dudoso" in aviso or "confirma" in aviso else
                    "Clasificación automática según el NIF y el papel del "
                    "cliente en la factura.")
        self.blockSignals(bloqueadas)
        self._medida_pendiente()

    def fila_del_combo(self, control) -> int:
        for r in range(self.rowCount()):
            if self.cellWidget(r, C_TIPO) is control:
                return r
        return -1

    # ---------------------------------------------------------- estado
    def pintar_estado(self, r: int, texto: str, color: QColor, fondo: str,
                      ayuda: str) -> None:
        celda = self.item(r, C_ESTADO)
        if celda is None:
            return
        bloqueadas = self.signalsBlocked()
        self.blockSignals(True)
        celda.setText(texto)
        celda.setForeground(color)
        celda.setBackground(QColor(fondo))
        fuente = celda.font()
        fuente.setBold(True)
        celda.setFont(fuente)
        celda.setToolTip(ayuda)
        self.blockSignals(bloqueadas)
        self._medida_pendiente()

    def resaltar(self, r: int, fila: Fila, estado: str, mensajes) -> None:
        """Colorea el dato concreto que explica el semáforo de la fila."""
        bloqueadas = self.signalsBlocked()
        self.blockSignals(True)
        for columna in COLUMNAS_DATO:
            item = self.item(r, columna)
            if not item:
                continue
            # QColor() se veía negro en algunos estilos de Windows. El rol
            # vacío permite que Qt vuelva a pintar el fondo normal/alterno y
            # el color de texto definido por el tema.
            item.setData(Qt.BackgroundRole, None)
            item.setData(Qt.ForegroundRole, None)
            fuente = item.font()
            fuente.setBold(False)
            item.setFont(fuente)
            # Ayudas permanentes: cuenta, GXX y suplido.
            if columna == C_GXX:
                item.setToolTip(AYUDA_GXX)
            elif columna == C_BASE and getattr(fila.factura, "es_suplido", False):
                item.setToolTip(AYUDA_SUPLIDO)
            elif columna != C_CUENTA:
                item.setToolTip("")

        por_columna = {}
        graves = set()

        def marcar(columna, mensaje, gravedad=None):
            por_columna.setdefault(columna, []).append(mensaje)
            if (gravedad or estado) == ERROR:
                graves.add(columna)

        for mensaje in mensajes:
            campos = getattr(mensaje, "campos", None)
            if campos is not None:
                # Aviso con su dato: se colorea exactamente esa celda.
                for campo in campos:
                    columna = COLUMNA_DE_CAMPO.get(campo)
                    if columna is not None:
                        marcar(columna, str(mensaje), mensaje.gravedad)
                continue
            # Avisos guardados como texto (lecturas y sesiones anteriores).
            texto = str(mensaje)
            bajo = texto.lower()
            if "año distinto" in bajo or "fuera del trimestre" in bajo:
                marcar(C_FECHA, texto)
            if "factura duplicada" in bajo:
                marcar(C_NUM, texto)
            if "nif" in bajo and ("copiado" in bajo or "memoria" in bajo
                                  or "guardado" in bajo):
                marcar(C_NIF, texto, "revisar")
            if "cuenta " in bajo and ("propuesta" in bajo or "descarte" in bajo
                                      or "subclave" in bajo):
                marcar(C_CUENTA, texto, "revisar")
            if "el total no cuadra" in bajo or "el signo no cuadra" in bajo:
                marcar(C_TOTAL, texto)

        for columna, detalles in por_columna.items():
            item = self.item(r, columna)
            if not item:
                continue
            grave = columna in graves
            item.setBackground(QColor("#ffcdd2" if grave else "#fff3cd"))
            item.setForeground(QColor("#7f0000" if grave else "#6b4f00"))
            fuente = item.font()
            fuente.setBold(True)
            item.setFont(fuente)
            ayuda_anterior = item.toolTip().strip()
            ayuda = "\n".join(dict.fromkeys(detalles))
            item.setToolTip(
                f"{ayuda_anterior}\n\n{ayuda}" if ayuda_anterior else ayuda)
        self.blockSignals(bloqueadas)
        self._medida_pendiente()


def _senaladas(filas, campos) -> bool:
    """Algún aviso apunta a uno de esos datos (hay que poder verlo)."""
    return any(c in campos for x in filas for m in (x.mensajes or ())
               for c in (getattr(m, "campos", None) or ()))


def columnas_visibles(filas, recargo_cliente: bool, irpf_cliente: bool,
                      ver_todas: bool) -> dict:
    """Qué columnas opcionales se enseñan: {columna: visible}.

    Recargo: si el cliente está en ese régimen o alguna factura lo trae.
    Retenciones: si alguna factura las trae o el cliente es de los que las
    llevan (transportistas). Nunca se esconde una columna con datos ni una
    que un aviso señala, y con «Ver todas» se enseña todo.
    """
    recargo = (ver_todas or recargo_cliente or hay_datos(filas, CAMPOS_RECARGO)
               or _senaladas(filas, CAMPOS_RECARGO))
    irpf = (ver_todas or irpf_cliente or hay_datos(filas, CAMPOS_IRPF)
            or _senaladas(filas, CAMPOS_IRPF))
    visibles = {c: recargo for c in COLUMNAS_RECARGO}
    visibles.update({c: irpf for c in COLUMNAS_IRPF})
    return visibles
