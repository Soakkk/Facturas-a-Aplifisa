"""Ventana principal de Facturas a Aplifisa.

Flujo: Cargar facturas (PDF/imagenes) -> Gemini extrae y clasifica en segundo
plano -> autodetecta el cliente -> tabla de revision con miniatura y semaforo
(editable, se puede cambiar gasto/venta) -> Exportar gastos.xlsx / ventas.xlsx.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel import __version__, updater
from facturas_excel.claves import guardar_api_key, leer_api_key
from facturas_excel.config_columnas import leer_config
from facturas_excel.exportar import exportar_excel
from facturas_excel.extraccion import Extractor, SinCredito
from facturas_excel.modelo import Factura
from facturas_excel.pdf import cargar_imagenes
from facturas_excel.procesar import construir, detectar_cliente
from facturas_excel.rutas import ruta_config
from facturas_excel.validacion import ERROR, OK, REVISAR, validar

ESCRITORIO = os.path.join(os.path.expanduser("~"), "Desktop")

COLOR_ESTADO = {OK: QColor("#2e7d32"), REVISAR: QColor("#f9a825"), ERROR: QColor("#c62828")}
ICONO_ESTADO = {OK: "OK", REVISAR: "!", ERROR: "X"}

HILOS = 6  # facturas procesadas en paralelo (con key de pago se puede subir)

COLS = ["Estado", "Tipo", "Cuenta", "GXX", "Fecha", "Nº Factura", "Nombre",
        "NIF", "Base", "% IVA", "Cuota", "Total"]
C_ESTADO, C_TIPO, C_CUENTA, C_GXX, C_FECHA, C_NUM, C_NOMBRE, C_NIF, \
    C_BASE, C_PCT, C_CUOTA, C_TOTAL = range(len(COLS))


def parse_numero(texto):
    if texto is None:
        return None
    t = str(texto).strip()
    if not t:
        return None
    t = t.replace(".", "").replace(",", ".") if "," in t else t
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


class VentanaPrincipal(QMainWindow):
    def __init__(self, comprobar_updates: bool = True):
        super().__init__()
        self.setWindowTitle(f"Facturas a Aplifisa — v{__version__}")
        self.resize(1250, 680)
        self.filas = []  # por fila: dict(png, factura, aviso)
        self._hilo_update = None
        self._comprobar_updates = comprobar_updates
        self._crear_menu()

        central = QWidget()
        layout = QVBoxLayout(central)

        # --- barra superior ---
        barra = QHBoxLayout()
        self.btn_cargar = QPushButton("📂 Cargar facturas")
        self.btn_cargar.clicked.connect(self._cargar)
        self.btn_key = QPushButton("🔑 API key")
        self.btn_key.clicked.connect(self._configurar_key)
        self.lbl_cliente = QLabel("Cliente: —")
        self.lbl_cliente.setStyleSheet("font-weight:bold;")
        barra.addWidget(self.btn_cargar)
        barra.addWidget(self.btn_key)
        barra.addSpacing(20)
        barra.addWidget(self.lbl_cliente)
        barra.addStretch()
        self.btn_gastos = QPushButton("💾 Exportar gastos")
        self.btn_gastos.clicked.connect(lambda: self._exportar("gasto"))
        self.btn_ventas = QPushButton("💾 Exportar ventas")
        self.btn_ventas.clicked.connect(lambda: self._exportar("venta"))
        barra.addWidget(self.btn_gastos)
        barra.addWidget(self.btn_ventas)
        layout.addLayout(barra)

        self.progreso = QProgressBar()
        self.progreso.setVisible(False)
        layout.addWidget(self.progreso)

        # --- splitter: tabla | miniatura ---
        split = QSplitter(Qt.Horizontal)
        self.tabla = QTableWidget(0, len(COLS))
        self.tabla.setHorizontalHeaderLabels(COLS)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tabla.itemChanged.connect(self._on_celda)
        self.tabla.itemSelectionChanged.connect(self._mostrar_miniatura)
        split.addWidget(self.tabla)

        self.lbl_img = QLabel("Selecciona una factura para ver la imagen")
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setMinimumWidth(320)
        self.lbl_img.setStyleSheet("background:#f4f4f4; color:#666;")
        split.addWidget(self.lbl_img)
        split.setSizes([900, 350])
        layout.addWidget(split, 1)

        self.lbl_estado = QLabel("Carga un PDF o imágenes de facturas para empezar.")
        layout.addWidget(self.lbl_estado)

        self.setCentralWidget(central)
        if self._comprobar_updates:
            self._comprobar_actualizaciones(silencioso=True)

    def esperar_hilos(self):
        """Espera a que terminen los hilos vivos (evita abortar al salir)."""
        for hilo in (getattr(self, "_hilo_update", None), getattr(self, "worker", None)):
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
            "Actualizaciones: github.com/Soakkk/Facturas-a-Aplifisa-releases")

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
            try:
                updater.descargar_y_lanzar(act)
                QApplication.quit()
            except Exception as e:
                QMessageBox.critical(self, "Error al descargar", str(e))

    def _on_update_error(self, msg):
        if not getattr(self, "_update_silencioso", True):
            QMessageBox.warning(self, "Actualizaciones",
                                f"No se pudo comprobar:\n{msg}")

    def closeEvent(self, ev):
        # No destruir QThreads vivos (abortaria el proceso)
        self.esperar_hilos()
        super().closeEvent(ev)

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
        api_key = leer_api_key()
        if not api_key:
            QMessageBox.warning(self, "Falta la API key",
                                "Configura primero tu API key de Gemini (botón 🔑).")
            return
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Elige facturas (PDF o imágenes)", ESCRITORIO,
            "Facturas (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if not rutas:
            return
        self.btn_cargar.setEnabled(False)
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
        QMessageBox.critical(self, "Error al procesar", msg)

    def _on_terminado(self, procesadas, nombre, nif):
        self.progreso.setVisible(False)
        self.btn_cargar.setEnabled(True)
        self.lbl_cliente.setText(f"Cliente: {nombre}  ({nif})")
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(0)
        self.filas = []
        for png, pr in procesadas:
            for f in pr.facturas:
                self._anadir_fila(png, f, pr.tipo, pr.cuenta, pr.gxx, pr.aviso)
        self.tabla.blockSignals(False)
        self._revalidar_todo()

    def _anadir_fila(self, png, f: Factura, tipo, cuenta, gxx, aviso):
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
            self.tabla.setItem(r, col, QTableWidgetItem("" if val is None else str(val)))

    # ---------- edicion / validacion ----------
    def _on_celda(self, item):
        self._revalidar_fila(item.row())

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
        celda = self.tabla.item(r, C_ESTADO)
        self.tabla.blockSignals(True)
        celda.setText(ICONO_ESTADO[estado])
        celda.setBackground(COLOR_ESTADO[estado])
        celda.setForeground(QColor("white"))
        celda.setToolTip("\n".join(msgs) if msgs else "Todo correcto")
        self.tabla.blockSignals(False)
        self._resumen()

    def _revalidar_todo(self):
        for r in range(self.tabla.rowCount()):
            self._revalidar_fila(r)

    def _resumen(self):
        estados = []
        for r in range(self.tabla.rowCount()):
            f = self.filas[r]["factura"]
            e = validar(f).estado
            if self.filas[r]["aviso"] and e == OK:
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
        pix = QPixmap()
        pix.loadFromData(png)
        if not pix.isNull():
            self.lbl_img.setPixmap(pix.scaled(
                self.lbl_img.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

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


def main():
    app = QApplication(sys.argv)
    v = VentanaPrincipal()
    app.aboutToQuit.connect(v.esperar_hilos)
    v.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
