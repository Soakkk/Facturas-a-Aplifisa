"""Ventana principal de Facturas a Aplifisa.

Flujo: Cargar facturas (PDF/imagenes) -> Gemini extrae y clasifica en segundo
plano -> autodetecta el cliente -> tabla de revision con miniatura y semaforo
(editable, se puede cambiar gasto/venta) -> Exportar gastos.xlsx / ventas.xlsx.
"""

from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QProgressDialog, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel import __version__, updater
from facturas_excel.claves import guardar_api_key, leer_api_key
from facturas_excel.config_columnas import leer_config
from facturas_excel.estilo import aplicar_tema
from facturas_excel.exportar import exportar_excel
from facturas_excel.extraccion import Extractor, SinCredito
from facturas_excel.modelo import Factura
from facturas_excel.pdf import cargar_imagenes
from facturas_excel.procesar import construir, detectar_cliente
from facturas_excel.rutas import ruta_config
from facturas_excel.validacion import ERROR, OK, REVISAR, encontrar_duplicados, validar

ESCRITORIO = os.path.join(os.path.expanduser("~"), "Desktop")

COLOR_ESTADO = {OK: QColor("#2e7d32"), REVISAR: QColor("#f9a825"), ERROR: QColor("#c62828")}
ICONO_ESTADO = {OK: "OK", REVISAR: "!", ERROR: "X"}

HILOS = 6  # facturas procesadas en paralelo (con key de pago se puede subir)
EXT_FACTURA = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

COLS = ["Estado", "Tipo", "Cuenta", "GXX", "Fecha", "Nº Factura", "Nombre",
        "NIF", "Base", "% IVA", "Cuota", "Total"]
C_ESTADO, C_TIPO, C_CUENTA, C_GXX, C_FECHA, C_NUM, C_NOMBRE, C_NIF, \
C_BASE, C_PCT, C_CUOTA, C_TOTAL = range(len(COLS))


def ruta_recurso(nombre):
    base = getattr(
        sys, "_MEIPASS",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", nombre)


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


def rutas_factura_de_mime(mime):
    """Rutas locales compatibles contenidas en un arrastre."""
    if not mime.hasUrls():
        return []
    rutas = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        ruta = url.toLocalFile()
        if os.path.splitext(ruta)[1].lower() in EXT_FACTURA:
            rutas.append(ruta)
    return rutas


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",")
    return str(v)


class Worker(QThread):
    progreso = Signal(int, int)
    terminado = Signal(object, str, str)   # lista[(png, FacturaProcesada)], nombre, nif
    fallo = Signal(str)

    def __init__(self, rutas, api_key):
        super().__init__()
        self.rutas = rutas
        self.api_key = api_key

    def run(self):
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            imagenes = cargar_imagenes(self.rutas, dpi=150)
            if not imagenes:
                raise ValueError("No se encontraron páginas o imágenes compatibles.")
            extractor = Extractor(self.api_key)
            total = len(imagenes)
            registros = [None] * total

            def tarea(idx):
                origen, pagina, img = imagenes[idx]
                try:
                    datos = extractor.extraer(img, origen, pagina).crudo
                except SinCredito:
                    raise  # detiene todo el lote con aviso
                except Exception as e:  # una factura ilegible no tumba el lote
                    datos = {"emisor_nombre": "(NO SE PUDO LEER)", "lineas_iva": [{}],
                             "_error": str(e)[:120]}
                return idx, (img, origen, pagina, datos)

            hechas = 0
            with ThreadPoolExecutor(max_workers=HILOS) as ex:
                futuros = [ex.submit(tarea, i) for i in range(total)]
                for fut in as_completed(futuros):
                    idx, reg = fut.result()
                    registros[idx] = reg
                    hechas += 1
                    self.progreso.emit(hechas, total)

            nombre, nif = detectar_cliente([d for *_, d in registros])
            procesadas = [(img, construir(datos, nif, nombre, origen, pag))
                          for img, origen, pag, datos in registros]
            self.terminado.emit(procesadas, nombre, nif)
        except Exception as e:  # noqa
            self.fallo.emit(str(e))


class HiloActualizacion(QThread):
    resultado = Signal(object)   # Actualizacion o None
    error = Signal(str)

    def run(self):
        try:
            self.resultado.emit(updater.comprobar())
        except Exception as e:  # sin red, API caida, etc.
            self.error.emit(str(e))


class HiloDescargaActualizacion(QThread):
    progreso = Signal(int)
    terminado = Signal(str)
    error = Signal(str)

    def __init__(self, actualizacion):
        super().__init__()
        self.actualizacion = actualizacion

    def run(self):
        try:
            ruta = updater.descargar(
                self.actualizacion, progreso=self.progreso.emit)
            self.terminado.emit(ruta)
        except Exception as e:
            self.error.emit(str(e))


class VentanaPrincipal(QMainWindow):
    def __init__(self, comprobar_updates: bool = True):
        super().__init__()
        self.setWindowTitle(f"Facturas a Aplifisa — v{__version__}")
        self.setWindowIcon(QIcon(ruta_recurso("app.ico")))
        self.resize(1420, 820)
        self.setMinimumSize(1080, 680)
        self.setAcceptDrops(True)
        self.filas = []  # por fila: dict(png, factura, aviso)
        self._duplicados = set()
        self._rutas_actuales = []
        self._hilo_update = None
        self._hilo_descarga_update = None
        self._comprobar_updates = comprobar_updates
        self._crear_menu()

        self._crear_interfaz()
        if self._comprobar_updates:
            QTimer.singleShot(
                1500, lambda: self._comprobar_actualizaciones(silencioso=True))

    def _crear_interfaz(self):
        central = QWidget()
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        cabecera = QFrame()
        cabecera.setObjectName("cabecera")
        cabecera.setFixedHeight(92)
        lc = QHBoxLayout(cabecera)
        lc.setContentsMargins(24, 14, 24, 14)
        logo = QLabel()
        logo.setPixmap(QPixmap(ruta_recurso("app.png")).scaled(
            52, 52, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        logo.setFixedSize(56, 56)
        lc.addWidget(logo)
        marca = QVBoxLayout()
        titulo = QLabel("Facturas a Aplifisa")
        titulo.setObjectName("marca")
        subtitulo = QLabel("Preparar, revisar y exportar facturas para captura masiva")
        subtitulo.setObjectName("marcaSubtitulo")
        marca.addWidget(titulo)
        marca.addWidget(subtitulo)
        lc.addLayout(marca)
        lc.addStretch()
        for texto, activo in (("1  Cargar", True), ("2  Revisar", False),
                              ("3  Exportar", False)):
            paso = QLabel(texto)
            paso.setObjectName("pasoActivo" if activo else "pasoInactivo")
            lc.addWidget(paso)
        raiz.addWidget(cabecera)

        cuerpo = QVBoxLayout()
        cuerpo.setContentsMargins(18, 16, 18, 12)
        cuerpo.setSpacing(12)

        acciones = QFrame()
        acciones.setObjectName("tarjeta")
        la = QHBoxLayout(acciones)
        la.setContentsMargins(16, 12, 16, 12)
        self.btn_cargar = QPushButton("Abrir PDF o imágenes")
        self.btn_cargar.setObjectName("primario")
        self.btn_cargar.setMinimumHeight(40)
        self.btn_cargar.clicked.connect(self._cargar)
        self.btn_key = QPushButton("Configurar Gemini")
        self.btn_key.clicked.connect(self._configurar_key)
        la.addWidget(self.btn_cargar)
        la.addWidget(self.btn_key)
        la.addSpacing(12)
        bloque_cliente = QVBoxLayout()
        etiqueta = QLabel("LOTE ACTUAL")
        etiqueta.setObjectName("textoSuave")
        self.lbl_cliente = QLabel("Cliente pendiente de detectar")
        self.lbl_cliente.setObjectName("cliente")
        bloque_cliente.addWidget(etiqueta)
        bloque_cliente.addWidget(self.lbl_cliente)
        la.addLayout(bloque_cliente, 1)
        self.btn_gastos = QPushButton("Exportar gastos")
        self.btn_gastos.setObjectName("exito")
        self.btn_gastos.setEnabled(False)
        self.btn_gastos.clicked.connect(lambda: self._exportar("gasto"))
        self.btn_ventas = QPushButton("Exportar ventas")
        self.btn_ventas.setEnabled(False)
        self.btn_ventas.clicked.connect(lambda: self._exportar("venta"))
        la.addWidget(self.btn_gastos)
        la.addWidget(self.btn_ventas)
        cuerpo.addWidget(acciones)

        self.progreso = QProgressBar()
        self.progreso.setVisible(False)
        cuerpo.addWidget(self.progreso)

        split = QSplitter(Qt.Horizontal)
        tabla_card = QFrame()
        tabla_card.setObjectName("tarjeta")
        lt = QVBoxLayout(tabla_card)
        lt.setContentsMargins(12, 12, 12, 12)
        titulo_tabla = QLabel("Datos extraídos")
        titulo_tabla.setObjectName("tituloSeccion")
        ayuda_tabla = QLabel("Revise las celdas en ámbar o rojo antes de exportar")
        ayuda_tabla.setObjectName("textoSuave")
        lt.addWidget(titulo_tabla)
        lt.addWidget(ayuda_tabla)
        self.tabla = QTableWidget(0, len(COLS))
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setHorizontalHeaderLabels(COLS)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.itemChanged.connect(self._on_celda)
        self.tabla.itemSelectionChanged.connect(self._mostrar_miniatura)
        lt.addWidget(self.tabla, 1)
        split.addWidget(tabla_card)

        visor_card = QFrame()
        visor_card.setObjectName("tarjeta")
        lv = QVBoxLayout(visor_card)
        lv.setContentsMargins(12, 12, 12, 12)
        titulo_visor = QLabel("Documento original")
        titulo_visor.setObjectName("tituloSeccion")
        self.lbl_origen = QLabel("Arrastre aquí un PDF o imágenes para comenzar")
        self.lbl_origen.setObjectName("textoSuave")
        self.lbl_origen.setWordWrap(True)
        self.lbl_img = QLabel("Suelte aquí las facturas\no use «Abrir PDF o imágenes»")
        self.lbl_img.setObjectName("visor")
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setMinimumWidth(330)
        self.lbl_img.setMinimumHeight(430)
        lv.addWidget(titulo_visor)
        lv.addWidget(self.lbl_origen)
        lv.addWidget(self.lbl_img, 1)
        split.addWidget(visor_card)
        split.setSizes([980, 380])
        cuerpo.addWidget(split, 1)

        self.lbl_estado = QLabel("Cargue un lote de facturas para empezar.")
        self.lbl_estado.setObjectName("textoSuave")
        cuerpo.addWidget(self.lbl_estado)
        cont = QWidget()
        cont.setLayout(cuerpo)
        raiz.addWidget(cont, 1)
        self.setCentralWidget(central)

    def esperar_hilos(self):
        """Espera a que terminen los hilos vivos (evita abortar al salir)."""
        for hilo in (
            getattr(self, "_hilo_update", None),
            getattr(self, "_hilo_descarga_update", None),
            getattr(self, "worker", None),
        ):
            if hilo and hilo.isRunning():
                hilo.wait(5000)

    # ---------- menu / actualizaciones ----------
    def _crear_menu(self):
        menu = self.menuBar().addMenu("Ayuda")
        menu.addAction("Buscar actualizaciones",
                       lambda: self._comprobar_actualizaciones(silencioso=False))
        menu.addAction("Acerca de", self._acerca_de)

    def _acerca_de(self):
        QMessageBox.about(
            self, "Acerca de",
            f"<b>Facturas a Aplifisa</b> v{__version__}<br><br>"
            "Lee facturas escaneadas con IA (Gemini), detecta al cliente, "
            "clasifica gastos y ventas y genera el Excel que importa Aplifisa.<br><br>"
            "Actualizaciones: github.com/Soakkk/Facturas-a-Aplifisa/releases")

    def _comprobar_actualizaciones(self, silencioso: bool):
        if self._hilo_update and self._hilo_update.isRunning():
            return
        self._update_silencioso = silencioso
        self._hilo_update = HiloActualizacion()
        self._hilo_update.resultado.connect(self._on_update)
        self._hilo_update.error.connect(self._on_update_error)
        self._hilo_update.start()

    def _on_update(self, act):
        if act is None:
            if not getattr(self, "_update_silencioso", True):
                QMessageBox.information(self, "Actualizaciones",
                                        f"Ya tienes la última versión (v{__version__}).")
            return
        r = QMessageBox.question(
            self, "Actualización disponible",
            f"Hay una versión nueva: <b>v{act.version}</b> (tienes v{__version__}).<br><br>"
            "¿Descargar e instalar ahora? El programa se cerrará para actualizarse.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r == QMessageBox.Yes:
            self._descargar_actualizacion(act)

    def _descargar_actualizacion(self, act):
        dialogo = QProgressDialog(
            "Descargando actualización…", None, 0, 100, self)
        dialogo.setWindowTitle("Actualizando")
        dialogo.setMinimumDuration(0)
        dialogo.setAutoClose(False)
        dialogo.setAutoReset(False)
        dialogo.setValue(0)
        self._dialogo_update = dialogo

        hilo = HiloDescargaActualizacion(act)
        self._hilo_descarga_update = hilo
        hilo.progreso.connect(dialogo.setValue)

        def terminado(ruta):
            dialogo.close()
            try:
                updater.lanzar_instalador(ruta)
            except Exception as e:
                QMessageBox.critical(
                    self, "Actualización", f"No se pudo abrir el instalador:\n{e}")
                return
            QApplication.quit()

        def error(mensaje):
            dialogo.close()
            QMessageBox.critical(
                self, "Actualización",
                f"No se pudo descargar la actualización:\n{mensaje}")

        hilo.terminado.connect(terminado)
        hilo.error.connect(error)
        hilo.start()
        dialogo.show()

    def _on_update_error(self, msg):
        if not getattr(self, "_update_silencioso", True):
            QMessageBox.warning(self, "Actualizaciones",
                                f"No se pudo comprobar:\n{msg}")

    def closeEvent(self, ev):
        # No destruir QThreads vivos (abortaria el proceso)
        self.esperar_hilos()
        super().closeEvent(ev)

    def dragEnterEvent(self, event):
        if rutas_factura_de_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        rutas = rutas_factura_de_mime(event.mimeData())
        if rutas:
            event.acceptProposedAction()
            self.procesar_rutas(rutas)

    # ---------- API key ----------
    def _configurar_key(self):
        actual = leer_api_key() or ""
        pista = ("•••" + actual[-4:]) if actual else "(no configurada)"
        texto, ok = QInputDialog.getText(
            self, "API key de Gemini",
            f"Pega tu API key de Google AI Studio.\nActual: {pista}")
        if ok and texto.strip():
            guardar_api_key(texto.strip())
            QMessageBox.information(self, "Guardada",
                                    "API key guardada de forma segura.")

    # ---------- carga ----------
    def _cargar(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Elige facturas (PDF o imágenes)", ESCRITORIO,
            "Facturas (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if rutas:
            self.procesar_rutas(rutas)

    def procesar_rutas(self, rutas):
        """Procesa rutas recibidas por diálogo, arrastre o Escáner Fotos."""
        rutas = [os.path.abspath(r) for r in rutas
                 if os.path.isfile(r) and os.path.splitext(r)[1].lower() in EXT_FACTURA]
        if not rutas:
            QMessageBox.warning(self, "Archivos no compatibles",
                                "No se encontraron PDFs o imágenes válidas.")
            return
        api_key = leer_api_key()
        if not api_key:
            QMessageBox.warning(self, "Falta la API key",
                                "Configura primero tu API key de Gemini.")
            return
        if getattr(self, "worker", None) and self.worker.isRunning():
            QMessageBox.information(self, "Procesando",
                                    "Espera a que termine el lote actual.")
            return
        self._rutas_actuales = rutas
        self.lbl_origen.setText(
            f"{len(rutas)} archivo{'s' if len(rutas) != 1 else ''}: "
            + ", ".join(os.path.basename(r) for r in rutas[:3])
            + ("…" if len(rutas) > 3 else ""))
        self.btn_cargar.setEnabled(False)
        self.btn_gastos.setEnabled(False)
        self.btn_ventas.setEnabled(False)
        self.progreso.setVisible(True)
        self.progreso.setValue(0)
        self.lbl_estado.setText("Leyendo facturas con Gemini…")
        self.worker = Worker(rutas, api_key)
        self.worker.progreso.connect(self._on_progreso)
        self.worker.terminado.connect(self._on_terminado)
        self.worker.fallo.connect(self._on_fallo)
        self.worker.start()

    def _on_progreso(self, actual, total):
        self.progreso.setMaximum(total)
        self.progreso.setValue(actual)
        self.lbl_estado.setText(f"Leyendo facturas con Gemini… {actual}/{total}")

    def _on_fallo(self, msg):
        self.progreso.setVisible(False)
        self.btn_cargar.setEnabled(True)
        self.lbl_estado.setText("No se pudo procesar el lote.")
        QMessageBox.critical(self, "Error al procesar", msg)

    def _on_terminado(self, procesadas, nombre, nif):
        self.progreso.setVisible(False)
        self.btn_cargar.setEnabled(True)
        self.lbl_cliente.setText(
            f"{nombre or 'Cliente no identificado'}"
            + (f"  ·  {nif}" if nif else ""))
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(0)
        self.filas = []
        for png, pr in procesadas:
            for f in pr.facturas:
                self._anadir_fila(png, f, pr.tipo, pr.cuenta, pr.gxx, pr.aviso)
        self.tabla.blockSignals(False)
        self._revalidar_todo()
        hay_datos = self.tabla.rowCount() > 0
        self.btn_gastos.setEnabled(hay_datos)
        self.btn_ventas.setEnabled(hay_datos)
        if hay_datos:
            self.tabla.selectRow(0)

    def _anadir_fila(self, png, f: Factura, tipo, cuenta, gxx, aviso):
        senales_bloqueadas = self.tabla.signalsBlocked()
        self.tabla.blockSignals(True)
        r = self.tabla.rowCount()
        self.tabla.insertRow(r)
        self.filas.append({"png": png, "factura": f, "aviso": aviso})

        est = QTableWidgetItem("")
        est.setFlags(Qt.ItemIsEnabled)
        est.setTextAlignment(Qt.AlignCenter)
        self.tabla.setItem(r, C_ESTADO, est)

        combo = QComboBox()
        combo.addItems(["gasto", "venta"])
        combo.setCurrentText(tipo)
        combo.currentTextChanged.connect(lambda _t, row=r: self._revalidar_fila(row))
        self.tabla.setCellWidget(r, C_TIPO, combo)

        valores = {
            C_CUENTA: cuenta, C_GXX: gxx or "", C_FECHA: f.fecha, C_NUM: f.num_factura,
            C_NOMBRE: f.nombre, C_NIF: f.nif, C_BASE: fmt(f.base_iva),
            C_PCT: fmt(f.pct_iva), C_CUOTA: fmt(f.cuota_iva), C_TOTAL: fmt(f.total_impreso),
        }
        for col, val in valores.items():
            item = QTableWidgetItem("" if val is None else str(val))
            if col == C_GXX:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setToolTip("Subclave orientativa; Aplifisa la recuerda por proveedor.")
            self.tabla.setItem(r, col, item)
        self.tabla.setRowHeight(r, 34)
        self.tabla.blockSignals(senales_bloqueadas)

    # ---------- edicion / validacion ----------
    def _on_celda(self, item):
        self._revalidar_todo()

    def _leer_fila(self, r):
        """Actualiza la Factura de la fila con lo que hay en las celdas."""
        d = self.filas[r]
        f = d["factura"]
        f.concepto = self.tabla.item(r, C_CUENTA).text() or None
        f.fecha = self.tabla.item(r, C_FECHA).text() or None
        f.num_factura = self.tabla.item(r, C_NUM).text() or None
        f.nombre = self.tabla.item(r, C_NOMBRE).text() or None
        f.nif = self.tabla.item(r, C_NIF).text() or None
        f.base_iva = parse_numero(self.tabla.item(r, C_BASE).text())
        f.pct_iva = parse_numero(self.tabla.item(r, C_PCT).text())
        f.cuota_iva = parse_numero(self.tabla.item(r, C_CUOTA).text())
        f.total_impreso = parse_numero(self.tabla.item(r, C_TOTAL).text())
        return f

    def _tipo_fila(self, r):
        w = self.tabla.cellWidget(r, C_TIPO)
        return w.currentText() if w else "gasto"

    def _revalidar_fila(self, r):
        if r >= len(self.filas):
            return
        f = self._leer_fila(r)
        res = validar(f)
        estado = res.estado
        msgs = list(res.mensajes)
        if self.filas[r]["aviso"]:
            msgs.append(self.filas[r]["aviso"])
            if estado == OK:
                estado = REVISAR
        if r in self._duplicados:
            msgs.append("Posible duplicado dentro del lote (mismo nº, NIF y base).")
            if estado == OK:
                estado = REVISAR
        celda = self.tabla.item(r, C_ESTADO)
        self.tabla.blockSignals(True)
        celda.setText(ICONO_ESTADO[estado])
        celda.setBackground(COLOR_ESTADO[estado])
        celda.setForeground(QColor("white"))
        celda.setToolTip("\n".join(msgs) if msgs else "Todo correcto")
        self.tabla.blockSignals(False)
        self._resumen()

    def _revalidar_todo(self):
        self._duplicados = set(encontrar_duplicados(
            [self._leer_fila(r) for r in range(self.tabla.rowCount())]))
        for r in range(self.tabla.rowCount()):
            self._revalidar_fila(r)

    def _resumen(self):
        estados = []
        for r in range(self.tabla.rowCount()):
            f = self.filas[r]["factura"]
            e = validar(f).estado
            if self.filas[r]["aviso"] and e == OK:
                e = REVISAR
            if r in self._duplicados and e == OK:
                e = REVISAR
            estados.append(e)
        n_g = sum(1 for r in range(self.tabla.rowCount()) if self._tipo_fila(r) == "gasto")
        self.lbl_estado.setText(
            f"{len(estados)} líneas  ·  Gastos: {n_g}  ·  Ventas: {len(estados) - n_g}  ·  "
            f"🟢 {estados.count(OK)}  🟡 {estados.count(REVISAR)}  🔴 {estados.count(ERROR)}")

    # ---------- miniatura ----------
    def _mostrar_miniatura(self):
        r = self.tabla.currentRow()
        if r < 0 or r >= len(self.filas):
            return
        png = self.filas[r]["png"]
        factura = self.filas[r]["factura"]
        origen = os.path.basename(factura.origen_imagen or "")
        self.lbl_origen.setText(origen or "Documento cargado")
        pix = QPixmap()
        pix.loadFromData(png)
        if not pix.isNull():
            self.lbl_img.setPixmap(pix.scaled(
                self.lbl_img.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.tabla.currentRow() >= 0:
            self._mostrar_miniatura()

    # ---------- exportar ----------
    def _exportar(self, tipo):
        facturas = [self.filas[r]["factura"] for r in range(self.tabla.rowCount())
                    if self._tipo_fila(r) == tipo]
        if not facturas:
            QMessageBox.warning(self, "Sin datos", f"No hay {tipo}s que exportar.")
            return
        errores = sum(1 for f in facturas if validar(f).estado == ERROR)
        if errores:
            r = QMessageBox.question(
                self, "Hay errores",
                f"{errores} línea(s) con errores (rojo). ¿Exportar de todas formas?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        xml = "gastos.xml" if tipo == "gasto" else "ingresos.xml"
        cfg = leer_config(ruta_config(xml))
        nombre = "gastos.xlsx" if tipo == "gasto" else "ventas.xlsx"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar Excel", os.path.join(ESCRITORIO, nombre), "Excel (*.xlsx)")
        if not ruta:
            return
        exportar_excel(facturas, cfg, ruta)
        QMessageBox.information(self, "Exportado", f"Generado:\n{ruta}")


def _argumentos(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--import", dest="importar", nargs="+")
    args, _ = parser.parse_known_args(argv[1:])
    return args


def main():
    args = _argumentos(sys.argv)
    app = QApplication([sys.argv[0]])
    app.setWindowIcon(QIcon(ruta_recurso("app.ico")))
    aplicar_tema(app)
    v = VentanaPrincipal()
    app.aboutToQuit.connect(v.esperar_hilos)
    v.show()
    if args.importar:
        QTimer.singleShot(200, lambda: v.procesar_rutas(args.importar))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
