"""La tabla de revisión: enseña las `Fila` del lote y recoge lo que se corrige.

No decide nada: pinta lo que hay en cada factura y, cuando alguien escribe en
una celda, dice qué dato de la factura ha cambiado (`valor_de_celda`).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHeaderView, QTableWidget, QTableWidgetItem,
    QToolTip,
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
# Anchos desde la 1.19.1: cada columna mide lo que su texto más largo, con
# aire a los lados, entre un mínimo y un máximo. Antes el nombre se quedaba
# con todo el hueco (más de 500 px para «WÜRTH ESPAÑA, S.A.») mientras el
# número de factura salía cortado a 100 px. El ancho que se fija arrastrando
# un borde manda y se recuerda; doble clic en el borde vuelve al automático.
AIRE_CELDA = 18   # px que se suman al texto: ni pegado al borde ni hueco de sobra
LIMITES_ANCHO = {  # (mínimo, máximo) en px
    C_ESTADO: (96, 150), C_TIPO: (72, 110), C_CUENTA: (52, 90), C_GXX: (46, 70),
    C_FECHA: (80, 110), C_NUM: (90, 200), C_NOMBRE: (140, 380), C_NIF: (88, 130),
    C_BASE: (64, 130), C_PCT: (50, 74), C_CUOTA: (60, 120),
    C_BASE_RE: (64, 130), C_PCT_RE: (50, 74), C_CUOTA_RE: (60, 120),
    C_BASE_IRPF: (64, 130), C_PCT_IRPF: (50, 80), C_CUOTA_IRPF: (64, 120),
    C_TOTAL: (68, 130), C_BLOQUE: (80, 260),
}
# Si con recargo o retenciones no queda sitio, el nombre no baja de aquí
# (la tabla se desplaza en horizontal antes que dejarlo en «PRO…»).
ANCHO_MIN_NOMBRE = LIMITES_ANCHO[C_NOMBRE][0]
# Si no cabe todo, se estrechan estas (hasta su mínimo, en proporción a lo
# que les sobra) antes de que la tabla tenga que desplazarse en horizontal.
COLUMNAS_ELASTICAS = (C_NOMBRE, C_NUM)


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
    # Los anchos fijados a mano cambiaron: {título de columna: px}.
    anchos_cambiados = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(0, len(COLS), parent)
        self._listo = False
        self._anchos_usuario: dict[int, int] = {}   # columna -> px (a mano)
        self._contenido: dict[int, int] = {}        # columna -> px que pide
        self._contenido_sucio = True
        self._ajustando = False
        self.setAlternatingRowColors(True)
        self.setHorizontalHeaderLabels(COLS)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setDefaultSectionSize(38)
        cabecera = self.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.Interactive)
        cabecera.setSectionsClickable(True)
        cabecera.setMinimumSectionSize(40)
        # Bloque ya está en el filtro; recargo y retenciones se enseñan solo
        # cuando tocan (ver `columnas_visibles`).
        self.setColumnHidden(C_BLOQUE, True)
        for columna in COLUMNAS_RECARGO:
            self.setColumnHidden(columna, True)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Cualquier cambio de texto o de letra (negrita de un aviso) puede
        # pedir otro ancho: se recalcula una vez, al volver al bucle de eventos.
        self._timer_anchos = QTimer(self)
        self._timer_anchos.setSingleShot(True)
        self._timer_anchos.setInterval(0)
        self._timer_anchos.timeout.connect(self.ajustar_anchos)
        modelo = self.model()
        for senal in (modelo.dataChanged, modelo.rowsInserted,
                      modelo.rowsRemoved, modelo.modelReset):
            senal.connect(self._programar_anchos)
        cabecera.sectionResized.connect(self._al_redimensionar_columna)
        cabecera.sectionHandleDoubleClicked.connect(self._ancho_automatico)
        self._listo = True
        self.ajustar_anchos()

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

    # ----------------------------------------------------------- anchos
    def setColumnHidden(self, columna: int, oculta: bool) -> None:
        # Ocultar deja la sección a 0 px (y mostrarla la devuelve): eso no es
        # un ancho elegido por la persona y no debe recordarse.
        previo, self._ajustando = self._ajustando, True
        try:
            super().setColumnHidden(columna, oculta)
        finally:
            self._ajustando = previo
        self.ajustar_anchos()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self.ajustar_anchos()

    def _programar_anchos(self, *_) -> None:
        self._contenido_sucio = True
        self._timer_anchos.start()

    def _ancho_contenido(self, columna: int) -> int:
        """Lo que pide el texto más largo de la columna, cabecera incluida.

        Cuenta también las filas que esconde un filtro: así las columnas no
        bailan al filtrar por mes o por estado.
        """
        base = self.font()
        metricas = {}
        ancho = self.horizontalHeader().sectionSizeHint(columna) + 4
        for r in range(self.rowCount()):
            control = self.cellWidget(r, columna)
            if control is not None:
                ancho = max(ancho, control.sizeHint().width() + 6)
                continue
            item = self.item(r, columna)
            texto = item.text() if item is not None else ""
            if not texto:
                continue
            fuente = item.font().resolve(base)   # negrita de un aviso, etc.
            clave = fuente.key()
            if clave not in metricas:
                metricas[clave] = QFontMetrics(fuente)
            ancho = max(ancho, metricas[clave].horizontalAdvance(texto)
                        + AIRE_CELDA)
        return ancho

    def ajustar_anchos(self) -> None:
        """Cada columna a lo que pide su contenido (o a lo fijado a mano).

        Si no cabe todo, se estrechan las COLUMNAS_ELASTICAS hasta su mínimo,
        en proporción a lo que les sobra; si ni así cabe, la tabla se desplaza.
        """
        if not getattr(self, "_listo", False):
            return
        self._timer_anchos.stop()
        if self._contenido_sucio:
            self.ensurePolished()   # la letra de la hoja de estilos
            self._contenido = {c: self._ancho_contenido(c)
                               for c in range(self.columnCount())}
            self._contenido_sucio = False
        anchos = {}
        for c in range(self.columnCount()):
            if self.isColumnHidden(c):
                continue
            if c in self._anchos_usuario:
                anchos[c] = self._anchos_usuario[c]
            else:
                minimo, maximo = LIMITES_ANCHO.get(c, (48, 300))
                anchos[c] = max(minimo, min(maximo, self._contenido.get(c, 0)))
        falta = sum(anchos.values()) - self.viewport().width()
        elasticas = [c for c in COLUMNAS_ELASTICAS
                     if c in anchos and c not in self._anchos_usuario]
        holgura = {c: anchos[c] - LIMITES_ANCHO[c][0] for c in elasticas}
        total = sum(holgura.values())
        if falta > 0 and total > 0:
            quitar = restante = min(falta, total)
            for i, c in enumerate(elasticas):
                parte = (restante if i == len(elasticas) - 1
                         else round(quitar * holgura[c] / total))
                parte = min(parte, holgura[c], restante)
                anchos[c] -= parte
                restante -= parte
        self._ajustando = True
        try:
            for c, ancho in anchos.items():
                if self.columnWidth(c) != ancho:
                    self.setColumnWidth(c, ancho)
        finally:
            self._ajustando = False

    def _al_redimensionar_columna(self, columna, _antes, ahora) -> None:
        if (self._ajustando or not self._listo or ahora <= 0
                or self.isColumnHidden(columna)):
            return
        # La ha movido la persona arrastrando el borde: ese ancho manda (las
        # demás no se recolocan, para que no salten mientras arrastra).
        self._anchos_usuario[columna] = ahora
        self.anchos_cambiados.emit(self.anchos_usuario())

    def _ancho_automatico(self, columna: int) -> None:
        """Doble clic en el borde: esa columna vuelve a medir su contenido."""
        self._anchos_usuario.pop(columna, None)
        self.anchos_cambiados.emit(self.anchos_usuario())
        self.ajustar_anchos()

    def anchos_usuario(self) -> dict:
        """Los anchos fijados a mano, por título de columna (para guardarlos)."""
        return {COLS[c]: ancho for c, ancho in sorted(self._anchos_usuario.items())}

    def poner_anchos_usuario(self, anchos) -> None:
        """Recupera lo guardado con `anchos_usuario` (ignora lo que no encaje)."""
        self._anchos_usuario = {}
        if isinstance(anchos, dict):
            for titulo, ancho in anchos.items():
                if (titulo in COLS and isinstance(ancho, int)
                        and not isinstance(ancho, bool) and 20 <= ancho <= 2000):
                    self._anchos_usuario[COLS.index(titulo)] = ancho
        self.ajustar_anchos()

    def restablecer_anchos(self) -> None:
        """Todas las columnas vuelven a ajustarse a su contenido."""
        self._anchos_usuario = {}
        self.anchos_cambiados.emit({})
        self.ajustar_anchos()

    def texto_recortado(self, indice) -> str:
        """El texto entero de una celda que no cabe en su ancho ('' si cabe)."""
        item = self.itemFromIndex(indice) if indice.isValid() else None
        texto = item.text() if item is not None else ""
        if not texto:
            return ""
        metricas = QFontMetrics(item.font().resolve(self.font()))
        # Unos px de margen: los que deja el propio dibujo de la celda.
        cabe = metricas.horizontalAdvance(texto) + 8 <= self.columnWidth(indice.column())
        return "" if cabe else texto

    def viewportEvent(self, evento):
        # Una celda cortada («ESCAYOLAS LÓPEZ OTROS…») enseña su texto entero
        # al pasar el ratón, salvo que ya tenga su propia ayuda (un aviso).
        if evento.type() == QEvent.ToolTip:
            indice = self.indexAt(evento.pos())
            item = self.itemFromIndex(indice) if indice.isValid() else None
            entero = self.texto_recortado(indice)
            if entero and item is not None and not item.toolTip():
                QToolTip.showText(evento.globalPos(), entero, self.viewport(),
                                  self.visualRect(indice))
                return True
        return super().viewportEvent(evento)

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
