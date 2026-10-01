"""La tabla de revisión: enseña las `Fila` del lote y recoge lo que se corrige.

No decide nada: pinta lo que hay en cada factura y, cuando alguien escribe en
una celda, dice qué dato de la factura ha cambiado (`valor_de_celda`).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QHeaderView, QTableWidget, QTableWidgetItem

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
# Algo más estrechas desde la 1.18: la tabla comparte la pantalla con el
# documento y la ficha (tres columnas) y así cabe sin desplazarse en 1920.
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

    def __init__(self, parent=None):
        super().__init__(0, len(COLS), parent)
        self.setAlternatingRowColors(True)
        self.setHorizontalHeaderLabels(COLS)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setDefaultSectionSize(38)
        cabecera = self.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.Interactive)
        cabecera.setSectionResizeMode(C_NOMBRE, QHeaderView.Stretch)
        cabecera.setSectionsClickable(True)
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

    # ------------------------------------------------------- ancho nombre
    def setColumnHidden(self, columna: int, oculta: bool) -> None:
        super().setColumnHidden(columna, oculta)
        self.ajustar_nombre()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self.ajustar_nombre()

    def _al_redimensionar_columna(self, columna, _antes, _ahora) -> None:
        if columna != C_NOMBRE:
            self.ajustar_nombre()

    def ajustar_nombre(self) -> None:
        """El nombre ocupa lo que sobra, pero nunca menos de ANCHO_MIN_NOMBRE."""
        cabecera = self.horizontalHeader()
        otras = sum(self.columnWidth(c) for c in range(self.columnCount())
                    if c != C_NOMBRE and not self.isColumnHidden(c))
        if self.viewport().width() - otras >= ANCHO_MIN_NOMBRE:
            modo = QHeaderView.Stretch
        else:
            modo = QHeaderView.Interactive
        if cabecera.sectionResizeMode(C_NOMBRE) != modo:
            cabecera.setSectionResizeMode(C_NOMBRE, modo)
        if modo == QHeaderView.Interactive \
                and self.columnWidth(C_NOMBRE) < ANCHO_MIN_NOMBRE:
            self.setColumnWidth(C_NOMBRE, ANCHO_MIN_NOMBRE)

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
