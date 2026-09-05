"""Ventana principal de Facturas a Aplifisa.

Flujo: Cargar facturas (PDF/imagenes) -> Gemini extrae y clasifica en segundo
plano -> autodetecta el cliente -> tabla de revision con miniatura y semaforo
(editable, se puede cambiar gasto/venta) -> Exportar gastos.xlsx / ventas.xlsx.
"""

from __future__ import annotations

import argparse
import os
import sys

from collections import Counter
from dataclasses import replace
from datetime import date

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QGridLayout, QHeaderView, QInputDialog, QLabel, QMainWindow, QMenu,
    QMessageBox, QProgressBar,
    QPushButton, QProgressDialog, QScrollArea, QSplitter, QStyle, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel import (
    __version__, ajustes, archivo, costes, escaner, notas_version, pendientes,
    sesion, updater,
)
from facturas_excel.claves import guardar_api_key, leer_api_key
from facturas_excel.dialogo_calidad import DialogoCalidad
from facturas_excel.dialogo_cliente import DialogoCliente
from facturas_excel.dialogo_escaneo import DialogoEscaneo
from facturas_excel.dialogo_escaneos import DialogoEscaneos
from facturas_excel.dialogo_pendientes import DialogoPendientes
from facturas_excel.dialogo_orden import (
    PDF as ORDEN_PDF, DialogoOrden,
)
from facturas_excel.dialogo_notas_version import DialogoNotasVersion
from facturas_excel.dialogo_recargo import DialogoRecargo
from facturas_excel.dialogo_registro import DialogoRegistro
from facturas_excel.dialogo_textos import DialogoTextos
from facturas_excel.clientes import (
    DESGLOSE, TOTAL, guardar_regimen_recargo, marcar_cliente, nombres_conocidos,
    recordar_nombre, regimen_recargo,
)
from facturas_excel.conceptos import (
    SUBCLAVES_628, descripcion_de, es_valido, texto_para,
)
from facturas_excel.config_columnas import leer_config
from facturas_excel.estilo import aplicar_tema
from facturas_excel.ficha_incidencias import (
    TITULOS as TITULOS_ESTADO, FichaIncidencias,
)
from facturas_excel.exportar import (
    exportar_excel, ordenar_para_exportar, totales_del_excel, verificar_excel,
)
from facturas_excel.extraccion import Extractor, SinCredito
from facturas_excel.modelo import Factura
from facturas_excel.pdf import PAGINAS_POR_BLOQUE, cargar_imagenes, dividir_pdf
from facturas_excel.procesar import (
    a_total_factura, analizar_cliente, clave_proveedor, detectar_cliente,
    normaliza_nif, preparar_lote, recordar_cuenta_proveedor, recordar_nif,
    recordar_nombre_proveedor,
)
from facturas_excel.registro import (
    contrastar, leer_registro, parece_listado,
)
from facturas_excel.resumen import (
    eur, porcentaje_iva, resumir, resumir_por_bloque,
)
from facturas_excel.rutas import dir_datos, ruta_config
from facturas_excel.validacion import (
    ERROR, OK, REVISAR, encontrar_duplicados, huecos_de_numeracion,
    fecha_de, validar, validar_nif,
)

ESCRITORIO = os.path.join(os.path.expanduser("~"), "Desktop")

COLOR_ESTADO = {OK: QColor("#2e7d32"), REVISAR: QColor("#f9a825"), ERROR: QColor("#c62828")}
ICONO_ESTADO = {OK: "OK", REVISAR: "!", ERROR: "X"}
COLOR_REVISADO = QColor("#1565c0")
COLOR_MANUAL = QColor("#616161")
ICONO_REVISADO = "✓"
ICONO_MANUAL = "M"

HILOS = 6  # facturas procesadas en paralelo (con key de pago se puede subir)
EXT_FACTURA = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

# Un SUPLIDO no tiene columna propia: va como una linea mas del mismo apunte,
# con su base y sin % ni cuota de IVA (es como lo registra Aplifisa).
COLS = ["Estado", "Tipo", "Cuenta", "GXX", "Fecha", "Nº Factura", "Nombre",
        "NIF", "Base", "% IVA", "Cuota", "Total", "Bloque"]
C_ESTADO, C_TIPO, C_CUENTA, C_GXX, C_FECHA, C_NUM, C_NOMBRE, C_NIF, \
C_BASE, C_PCT, C_CUOTA, C_TOTAL, C_BLOQUE = range(len(COLS))

# Columnas del resumen por bloque (punto de control antes de exportar). Las del
# IVA se calculan: una por cada tipo que haya en el lote, con el porcentaje en
# la cabecera ("IVA 21%") en vez de repetirlo dentro de cada celda.
COLS_RESUMEN_INICIO = ["Bloque", "Tipo", "Líneas", "Base"]
COLS_RESUMEN_FIN = ["Recargo", "IRPF", "Suplidos", "Total factura"]
TODOS_LOS_BLOQUES = "Todos los bloques"


def _ayuda_estado(estado, mensajes) -> str:
    """El globo del semaforo, con titulo y un punto por cada problema."""
    titulo, color = TITULOS_ESTADO.get(estado, TITULOS_ESTADO[REVISAR])
    if not mensajes:
        return f"<b style='color:{color}'>{titulo}</b>"
    puntos = "".join(f"<div style='margin-top:3px'>•&nbsp;{m}</div>"
                     for m in mensajes)
    return (f"<div style='max-width:420px'>"
            f"<b style='color:{color}'>{titulo}</b>{puntos}</div>")


def _cabeceras_resumen(tipos_iva) -> list:
    """Las columnas del resumen, con una de IVA por cada tipo que haya."""
    if tipos_iva:
        columnas_iva = [f"IVA {porcentaje_iva(p)}%" for p in tipos_iva]
    else:
        columnas_iva = ["IVA"]
    return [*COLS_RESUMEN_INICIO, *columnas_iva, *COLS_RESUMEN_FIN]


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


class VisorClicable(QLabel):
    """Miniatura que abre el documento a mayor tamaño con un clic."""

    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


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
    terminado = Signal(object, str, str, object)  # procesadas, nombre, nif, crudos
    gasto = Signal(str, float)             # modelo real, coste del lote en euros
    fallo = Signal(str)

    def __init__(self, rutas, api_key):
        super().__init__()
        self.rutas = rutas
        self.api_key = api_key
        self.fallos = []      # (archivo, pagina, motivo) de lo que no se leyó

    def run(self):
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            imagenes = cargar_imagenes(
                self.rutas, dpi=int(ajustes.leer('lectura_ppp', 150)))
            if not imagenes:
                raise ValueError("No se encontraron páginas o imágenes compatibles.")
            extractor = Extractor(self.api_key)
            total = len(imagenes)
            registros = [None] * total

            consumo = []   # (modelo, tokens entrada, tokens salida) por factura

            def tarea(idx):
                origen, pagina, img = imagenes[idx]
                try:
                    leido = extractor.extraer(img, origen, pagina)
                    consumo.append((leido.modelo, leido.tokens_entrada,
                                    leido.tokens_salida))
                    datos = leido.crudo
                except SinCredito:
                    raise  # detiene todo el lote con aviso
                except Exception as e:  # una factura ilegible no tumba el lote
                    datos = {"emisor_nombre": "(NO SE PUDO LEER)", "lineas_iva": [{}],
                             "_error": str(e)[:120]}
                    self.fallos.append((origen, pagina, str(e)[:120]))
                return idx, (img, origen, pagina, datos)

            hechas = 0
            with ThreadPoolExecutor(max_workers=HILOS) as ex:
                futuros = [ex.submit(tarea, i) for i in range(total)]
                for fut in as_completed(futuros):
                    idx, reg = fut.result()
                    registros[idx] = reg
                    hechas += 1
                    self.progreso.emit(hechas, total)

            # Lo gastado en Gemini, con los tokens reales de cada respuesta.
            modelo, coste_lote = "", 0.0
            for m, entrada, salida in consumo:
                modelo = m or modelo
                coste_lote += costes.registrar(m, entrada, salida)
            if consumo:
                self.gasto.emit(modelo, round(coste_lote, 6))

            nombre, nif = detectar_cliente([d for *_, d in registros])
            procesadas = preparar_lote(registros, nombre, nif)
            self.terminado.emit(procesadas, nombre, nif, registros)
        except Exception as e:  # noqa
            self.fallo.emit(str(e))


class HiloEscaneo(QThread):
    """El escaneo, fuera del hilo de la ventana: un taco de 30 hojas tarda."""
    progreso = Signal(int)      # hojas escaneadas hasta ahora
    terminado = Signal(str)     # ruta del PDF
    fallo = Signal(str)

    def __init__(self, destino, opciones):
        super().__init__()
        self.destino = destino
        self.opciones = opciones

    def run(self):
        try:
            ruta = escaner.escanear(
                self.destino, device_id=self.opciones["device_id"],
                dpi=self.opciones["dpi"],
                alimentador=self.opciones["alimentador"],
                duplex=self.opciones["duplex"],
                modo_color=self.opciones.get("modo_color", "color"),
                nombre_dispositivo=self.opciones.get("nombre_dispositivo", ""),
                progreso=self.progreso.emit)
            self.terminado.emit(ruta)
        except Exception as e:
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
    def __init__(self, comprobar_updates: bool = True,
                 restaurar_sesion: bool = True):
        super().__init__()
        self.setWindowTitle("Facturas a Aplifisa")
        self.setWindowIcon(QIcon(ruta_recurso("app.ico")))
        self.resize(1420, 820)
        self.setMinimumSize(1024, 640)
        self.setAcceptDrops(True)
        self.filas = []  # por fila: dict(png, factura, aviso, bloque)
        # Un bloque = un escaneo/carga. Se acumulan para poder meter en un solo
        # Excel varios PDF (un requerimiento no cabe en un escaneo de 25 hojas).
        # Cada uno: dict(nombre, procesadas, cliente, nif)
        self._bloques = []
        self._ultimo_borrado = []
        self._duplicados = set()
        self._rutas_actuales = []
        self._hilo_update = None
        self._hilo_descarga_update = None
        self._hilo_escaneo = None
        self._tipo_escaneo = "gastos"
        self._escaneo_reciente = False
        self._escaneo_sin_identificar = False
        self._cola = []
        self._cola_total = 0
        self._cola_completados = 0
        self._elemento_cola_actual = None
        self._decisiones_conflicto_nif = {}
        self._comprobar_updates = comprobar_updates
        self._crear_menu()

        self._crear_interfaz()
        self._crear_atajos()
        self._pintar_gasto()
        if restaurar_sesion:
            self._restaurar_sesion()
        QTimer.singleShot(500, self._mostrar_notas_version_al_arrancar)
        if self._comprobar_updates:
            QTimer.singleShot(
                1500, lambda: self._comprobar_actualizaciones(silencioso=True))

    def _crear_interfaz(self):
        central = QWidget()
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        self.fila_barra_estrecha = QFrame()
        self.fila_barra_estrecha.setObjectName("filaBarraEstrecha")
        self.layout_barra_estrecha = QHBoxLayout(self.fila_barra_estrecha)
        self.layout_barra_estrecha.setContentsMargins(0, 0, 0, 0)
        self.layout_barra_estrecha.addWidget(self.barra_rapida)
        raiz.addWidget(self.fila_barra_estrecha)

        # Sin banner de cabecera: la marca y la version ya salen en el titulo de
        # la ventana, y el espacio se aprovecha para la tabla.
        cuerpo = QVBoxLayout()
        cuerpo.setContentsMargins(10, 12, 10, 8)
        cuerpo.setSpacing(10)

        # El lote ocupa una sola fila. Las acciones frecuentes viven junto al
        # menú para no robar altura ni encoger la tabla en portátiles.
        cliente_bar = QFrame()
        cliente_bar.setObjectName("barraCliente")
        bloque_cliente = QHBoxLayout(cliente_bar)
        bloque_cliente.setContentsMargins(12, 7, 12, 7)
        bloque_cliente.setSpacing(10)
        etiqueta = QLabel("CLIENTE")
        etiqueta.setObjectName("tituloSeccion")
        self.lbl_cliente = QLabel("Pendiente de detectar")
        self.lbl_cliente.setObjectName("cliente")
        bloque_cliente.addWidget(etiqueta)
        bloque_cliente.addWidget(self.lbl_cliente)
        self.btn_cliente = QPushButton("Cambiar")
        self.btn_cliente.setObjectName("compacto")
        self.btn_cliente.setMaximumWidth(110)
        self.btn_cliente.setToolTip(
            "Quién es SU cliente en estas facturas. Si se detectó mal, se "
            "cambia aquí y el lote se rehace sin volver a pasar por Gemini.")
        self.btn_cliente.setEnabled(False)
        self.btn_cliente.clicked.connect(self._cambiar_cliente)
        bloque_cliente.addWidget(self.btn_cliente)
        bloque_cliente.addStretch(1)
        # Solo aparece si el lote trae facturas con recargo de equivalencia:
        # para el resto de clientes no significa nada y estorba.
        self.fila_recargo = QWidget()
        lr_recargo = QHBoxLayout(self.fila_recargo)
        lr_recargo.setContentsMargins(0, 0, 0, 0)
        lr_recargo.setSpacing(6)
        lbl_recargo = QLabel("Recargo de equivalencia:")
        lbl_recargo.setObjectName("textoSuave")
        lr_recargo.addWidget(lbl_recargo)
        self.chk_hay_recargo = QCheckBox("Factura(s) con recargo detectado")
        self.chk_hay_recargo.setChecked(True)
        self.chk_hay_recargo.setFocusPolicy(Qt.NoFocus)
        self.chk_hay_recargo.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.chk_hay_recargo.setStyleSheet("font-weight: 600; color: #A16207;")
        self.chk_hay_recargo.setToolTip(
            "Solo aparece cuando el lote contiene recargo de equivalencia.")
        lr_recargo.addWidget(self.chk_hay_recargo)
        self.combo_recargo = ComboSinRueda()
        self.combo_recargo.addItem(
            "registrar por el TOTAL factura (minorista)", TOTAL)
        self.combo_recargo.addItem(
            "registrar con DESGLOSE de IVA y recargo (mayorista)", DESGLOSE)
        self.combo_recargo.setToolTip(
            "Lo decide el régimen del cliente, no la factura:\n"
            "  · Minorista en recargo (sin modelo 303): no deduce IVA, así que "
            "el gasto va por el total.\n"
            "  · Mayorista en estimación directa: registra el IVA y el recargo "
            "por separado.\n"
            "Se recuerda por NIF.")
        self.combo_recargo.currentIndexChanged.connect(self._on_recargo)
        lr_recargo.addWidget(self.combo_recargo, 1)
        self.fila_recargo.setVisible(False)
        bloque_cliente.addWidget(self.fila_recargo)
        raiz.addWidget(cliente_bar)

        self.progreso = QProgressBar()
        self.progreso.setVisible(False)
        cuerpo.addWidget(self.progreso)

        # Alerta de duplicados: tiene que verse sin tener que pasar el raton
        # por encima de una celda (un duplicado importado se paga dos veces).
        self.alerta = QFrame()
        self.alerta.setObjectName("alerta")
        self.alerta.setVisible(False)
        lal = QVBoxLayout(self.alerta)
        lal.setContentsMargins(14, 10, 14, 10)
        lal.setSpacing(2)
        self.lbl_alerta_titulo = QLabel()
        self.lbl_alerta_titulo.setObjectName("alertaTitulo")
        self.lbl_alerta_texto = QLabel()
        self.lbl_alerta_texto.setObjectName("alertaTexto")
        self.lbl_alerta_texto.setWordWrap(True)
        lal.addWidget(self.lbl_alerta_titulo)
        lal.addWidget(self.lbl_alerta_texto)
        cuerpo.addWidget(self.alerta)

        split = QSplitter(Qt.Horizontal)
        tabla_card = QFrame()
        tabla_card.setObjectName("tarjeta")
        lt = QVBoxLayout(tabla_card)
        lt.setContentsMargins(12, 12, 12, 12)
        titulo_tabla = QLabel("DATOS EXTRAÍDOS")
        titulo_tabla.setObjectName("tituloSeccion")
        lt.addWidget(titulo_tabla)

        # En ventana ancha coincide con el prototipo: filtros y acciones en
        # una fila. En portátiles se reparten sin comprimir ni cortar textos.
        self.layout_herramientas = QGridLayout()
        self.layout_herramientas.setHorizontalSpacing(8)
        self.layout_herramientas.setVerticalSpacing(6)
        self.lbl_mostrar = QPushButton()
        self.lbl_mostrar.setObjectName("botonIcono")
        self.lbl_mostrar.setIcon(QIcon(ruta_recurso("filter.svg")))
        self.lbl_mostrar.setFixedWidth(30)
        self.lbl_mostrar.setToolTip("Filtrar las facturas mostradas")
        self.combo_filtro_estado = ComboSinRueda()
        self.combo_filtro_estado.addItems(
            ["Todas", "Solo por revisar", "Solo con errores", "Solo correctas"])
        self.combo_filtro_estado.currentIndexChanged.connect(self._aplicar_filtro)
        self.combo_filtro_bloque = ComboSinRueda()
        self.combo_filtro_bloque.addItem(TODOS_LOS_BLOQUES)
        self.combo_filtro_bloque.setToolTip(
            "Cada escaneo o PDF cargado es un bloque. Puede revisarlos de uno "
            "en uno y exportarlos todos juntos.")
        self.combo_filtro_bloque.currentIndexChanged.connect(self._aplicar_filtro)
        self.btn_siguiente = QPushButton("Siguiente incidencia")
        self.btn_siguiente.setObjectName("accionTabla")
        self.btn_siguiente.setIcon(QIcon(ruta_recurso("arrow-right.svg")))
        self.btn_siguiente.clicked.connect(self._siguiente_incidencia)
        self.btn_revisada = QPushButton("Marcar revisada")
        self.btn_revisada.setObjectName("accionTabla")
        self.btn_revisada.setIcon(QIcon(ruta_recurso("check.svg")))
        self.btn_revisada.setToolTip(
            "Confirma que ha comparado con el PDF las filas ámbar seleccionadas.")
        self.btn_revisada.clicked.connect(self._marcar_revisada)
        self.btn_manual = QPushButton("Gestión manual")
        self.btn_manual.setObjectName("accionTabla")
        self.btn_manual.setIcon(QIcon(ruta_recurso("edit.svg")))
        self.btn_manual.setToolTip(
            "Aparta o vuelve a incluir una factura esporádica en la exportación automática.")
        self.btn_manual.clicked.connect(self._alternar_gestion_manual)

        self.menu_acciones = QMenu(self)
        self.btn_quitar_bloque = self.menu_acciones.addAction("Quitar bloque")
        self.btn_quitar_bloque.setIcon(QIcon(ruta_recurso("trash.svg")))
        self.btn_quitar_bloque.setToolTip(
            "Quita del lote el bloque elegido en el desplegable (p.ej. si se ha "
            "cargado un PDF que no tocaba).")
        self.btn_quitar_bloque.triggered.connect(self._quitar_bloque)
        self.btn_eliminar = self.menu_acciones.addAction("Eliminar selección")
        self.btn_eliminar.setIcon(QIcon(ruta_recurso("trash.svg")))
        self.btn_eliminar.triggered.connect(self._eliminar_seleccion)
        self.menu_acciones.addSeparator()
        self.btn_deshacer_borrado = self.menu_acciones.addAction("Deshacer eliminación")
        self.btn_deshacer_borrado.setEnabled(False)
        self.btn_deshacer_borrado.setVisible(False)
        self.btn_deshacer_borrado.triggered.connect(self._deshacer_borrado)
        self.btn_mas_acciones = QPushButton("Más acciones")
        self.btn_mas_acciones.setObjectName("menuAcciones")
        self.btn_mas_acciones.setMenu(self.menu_acciones)
        self._distribuir_herramientas(self.width())
        lt.addLayout(self.layout_herramientas)
        self.tabla = QTableWidget(0, len(COLS))
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setHorizontalHeaderLabels([cabecera.upper() for cabecera in COLS])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.itemChanged.connect(self._on_celda)
        self.tabla.cellClicked.connect(self._abrir_ficha)
        self.tabla.itemSelectionChanged.connect(self._mostrar_miniatura)
        lt.addWidget(self.tabla, 1)
        split.addWidget(tabla_card)

        visor_card = QFrame()
        visor_card.setObjectName("tarjeta")
        visor_card.setMinimumWidth(360)
        lv = QVBoxLayout(visor_card)
        lv.setContentsMargins(12, 12, 12, 12)
        titulo_visor = QLabel("DOCUMENTO ORIGINAL")
        titulo_visor.setObjectName("tituloSeccion")
        self.lbl_origen = QLabel("Arrastre aquí un PDF o imágenes para comenzar")
        self.lbl_origen.setObjectName("textoSuave")
        self.lbl_origen.setWordWrap(True)
        barra_documento = QHBoxLayout()
        barra_documento.setSpacing(5)
        barra_documento.addWidget(self.lbl_origen, 1)
        self.lbl_pagina = QLabel("")
        self.lbl_pagina.setObjectName("textoSuave")
        barra_documento.addWidget(self.lbl_pagina)
        self.btn_zoom_menos = QPushButton()
        self.btn_zoom_menos.setObjectName("botonVisor")
        self.btn_zoom_menos.setIcon(QIcon(ruta_recurso("zoom-out.svg")))
        self.btn_zoom_menos.setToolTip("Alejar documento")
        self.btn_zoom_menos.clicked.connect(lambda: self._cambiar_zoom_visor(-0.15))
        barra_documento.addWidget(self.btn_zoom_menos)
        self.btn_zoom_mas = QPushButton()
        self.btn_zoom_mas.setObjectName("botonVisor")
        self.btn_zoom_mas.setIcon(QIcon(ruta_recurso("zoom-in.svg")))
        self.btn_zoom_mas.setToolTip("Acercar documento")
        self.btn_zoom_mas.clicked.connect(lambda: self._cambiar_zoom_visor(0.15))
        barra_documento.addWidget(self.btn_zoom_mas)
        self.btn_opciones_visor = QPushButton("⋮")
        self.btn_opciones_visor.setObjectName("botonVisor")
        menu_visor = QMenu(self.btn_opciones_visor)
        menu_visor.addAction("Abrir vista previa grande", self._abrir_vista_previa)
        self.btn_opciones_visor.setMenu(menu_visor)
        barra_documento.addWidget(self.btn_opciones_visor)
        self.lbl_img = VisorClicable(
            "Suelte aquí las facturas\no use «Abrir PDF o imágenes»")
        self.lbl_img.setObjectName("visor")
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setMinimumWidth(330)
        self.lbl_img.setMinimumHeight(430)
        self.lbl_img.setCursor(QCursor(Qt.PointingHandCursor))
        self.lbl_img.setToolTip("Haga clic para abrir una vista previa grande.")
        self.lbl_img.clicked.connect(self._abrir_vista_previa)
        self._pixmap_documento = QPixmap()
        self._zoom_visor = 1.0
        self.visor_scroll = QScrollArea()
        self.visor_scroll.setObjectName("visorScroll")
        self.visor_scroll.setWidgetResizable(True)
        self.visor_scroll.setWidget(self.lbl_img)
        lv.addWidget(titulo_visor)
        lv.addLayout(barra_documento)
        lv.addWidget(self.visor_scroll, 1)
        split.addWidget(visor_card)
        split.setStretchFactor(0, 7)
        split.setStretchFactor(1, 3)
        split.setSizes([980, 420])
        cuerpo.addWidget(split, 1)

        resumen_card = QFrame()
        resumen_card.setObjectName("tarjeta")
        lr = QVBoxLayout(resumen_card)
        lr.setContentsMargins(12, 10, 12, 10)
        lr.setSpacing(2)
        fila_titulo = QHBoxLayout()
        self.lbl_resumen_titulo = QLabel("⌄  COMPROBACIÓN DE TOTALES")
        self.lbl_resumen_titulo.setObjectName("tituloSeccion")
        fila_titulo.addWidget(self.lbl_resumen_titulo)
        fila_titulo.addStretch(1)
        btn_cerrar_resumen = QPushButton("Ocultar")
        btn_cerrar_resumen.setToolTip(
            "Es solo una comprobación. Se vuelve a ver en el menú Ver.")
        btn_cerrar_resumen.clicked.connect(lambda: self._ver_resumen(False))
        fila_titulo.addWidget(btn_cerrar_resumen)
        btn_copiar = QPushButton("Copiar resumen")
        btn_copiar.setToolTip(
            "Copia el resumen al portapapeles para pegarlo donde haga falta.")
        btn_copiar.clicked.connect(self._copiar_resumen)
        fila_titulo.addWidget(btn_copiar)
        lr.addLayout(fila_titulo)
        self.tabla_resumen = QTableWidget(0, len(COLS_RESUMEN_INICIO) + 1
                                          + len(COLS_RESUMEN_FIN))
        self.tabla_resumen.setHorizontalHeaderLabels(
            [cabecera.upper() for cabecera in _cabeceras_resumen([])])
        self.tabla_resumen.verticalHeader().setVisible(False)
        self.tabla_resumen.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_resumen.setSelectionMode(QTableWidget.NoSelection)
        self.tabla_resumen.setAlternatingRowColors(True)
        # Sin ajuste de linea: un nombre de PDF largo no debe estirar la fila.
        self.tabla_resumen.setWordWrap(False)
        self.tabla_resumen.verticalHeader().setDefaultSectionSize(26)
        self.tabla_resumen.setMaximumHeight(190)
        self.tabla_resumen.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lr.addWidget(self.tabla_resumen)
        self.resumen_card = resumen_card
        cuerpo.addWidget(resumen_card)
        resumen_card.setVisible(bool(ajustes.leer("ver_resumen", True)))

        pie = QHBoxLayout()
        self.lbl_estado = QLabel("Cargue o escanee un lote de facturas para empezar.")
        self.lbl_estado.setObjectName("textoSuave")
        pie.addWidget(self.lbl_estado, 1)
        self.lbl_gasto = QLabel()
        self.lbl_gasto.setObjectName("textoSuave")
        self.lbl_gasto.setToolTip(
            "Lo que cuesta leer las facturas con Gemini. Se calcula con los "
            "tokens reales de cada respuesta.\nGoogle no permite consultar el "
            "saldo de la cuenta desde el programa: esto es la cuenta que lleva "
            "el propio programa.")
        pie.addWidget(self.lbl_gasto)
        cuerpo.addLayout(pie)
        cont = QWidget()
        cont.setLayout(cuerpo)
        raiz.addWidget(cont, 1)
        self.setCentralWidget(central)
        self._actualizar_barra_responsiva(self.width())

    def _distribuir_herramientas(self, ancho: int):
        """Una fila como el diseño; dos si falta ancho para leer los textos."""
        if not hasattr(self, "layout_herramientas"):
            return
        elementos = (
            self.lbl_mostrar, self.combo_filtro_estado,
            self.combo_filtro_bloque, self.btn_siguiente,
            self.btn_revisada, self.btn_manual, self.btn_mas_acciones,
        )
        for elemento in elementos:
            self.layout_herramientas.removeWidget(elemento)
        for columna in range(8):
            self.layout_herramientas.setColumnStretch(columna, 0)

        if ancho >= 1200:
            posiciones = (
                (self.lbl_mostrar, 0, 0),
                (self.combo_filtro_estado, 0, 1),
                (self.combo_filtro_bloque, 0, 2),
                (self.btn_siguiente, 0, 4),
                (self.btn_revisada, 0, 5),
                (self.btn_manual, 0, 6),
                (self.btn_mas_acciones, 0, 7),
            )
            self.layout_herramientas.setColumnStretch(3, 1)
        else:
            posiciones = (
                (self.lbl_mostrar, 0, 0),
                (self.combo_filtro_estado, 0, 1),
                (self.combo_filtro_bloque, 0, 2, 2),
                (self.btn_siguiente, 1, 0, 2),
                (self.btn_revisada, 1, 2, 2),
                (self.btn_manual, 2, 0, 2),
                (self.btn_mas_acciones, 2, 2, 2),
            )
            self.layout_herramientas.setColumnStretch(0, 1)
            self.layout_herramientas.setColumnStretch(1, 1)
            self.layout_herramientas.setColumnStretch(2, 1)
            self.layout_herramientas.setColumnStretch(3, 1)
        for posicion in posiciones:
            widget, fila, columna = posicion[:3]
            expansion = posicion[3] if len(posicion) == 4 else 1
            self.layout_herramientas.addWidget(
                widget, fila, columna, 1, expansion)

    def _actualizar_barra_responsiva(self, ancho: int):
        """Comparte fila con los menús salvo cuando hacerlo recortaría texto."""
        if not hasattr(self, "fila_barra_estrecha"):
            return
        debe_ir_en_menu = ancho >= 1200
        esta_en_menu = getattr(self, "_barra_en_menu", False)
        if debe_ir_en_menu == esta_en_menu:
            self.fila_barra_estrecha.setVisible(not debe_ir_en_menu)
            return
        if debe_ir_en_menu:
            self.layout_barra_estrecha.removeWidget(self.barra_rapida)
            self.fila_barra_estrecha.hide()
            self.menuBar().setCornerWidget(self.barra_rapida, Qt.TopRightCorner)
        else:
            self.barra_rapida.setParent(self.fila_barra_estrecha)
            self.menuBar().setCornerWidget(None, Qt.TopRightCorner)
            self.layout_barra_estrecha.addWidget(self.barra_rapida)
            self.fila_barra_estrecha.show()
        self._barra_en_menu = debe_ir_en_menu

    def showEvent(self, evento):
        super().showEvent(evento)
        if sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        # Qt no pinta la barra nativa con QSS. Esta bandera documentada por DWM
        # hace que Windows use título y controles oscuros como en el prototipo.
        try:
            import ctypes
            valor = ctypes.c_int(1)
            for atributo in (20, 19):  # Windows 10 reciente / compilaciones antiguas
                resultado = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    int(self.winId()), atributo, ctypes.byref(valor),
                    ctypes.sizeof(valor))
                if resultado == 0:
                    break
            # La captura usa el mismo azul marino en título y barra de menús.
            for atributo, color in ((35, 0x003A1A07), (36, 0x00FFFFFF),
                                    (34, 0x003A1A07)):
                valor_color = ctypes.c_uint(color)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    int(self.winId()), atributo, ctypes.byref(valor_color),
                    ctypes.sizeof(valor_color))
        except (AttributeError, OSError):
            pass

    def esperar_hilos(self):
        """Espera a que terminen los hilos vivos (evita abortar al salir)."""
        for hilo in (
            getattr(self, "_hilo_update", None),
            getattr(self, "_hilo_descarga_update", None),
            getattr(self, "_hilo_escaneo", None),
            getattr(self, "worker", None),
        ):
            if hilo and hilo.isRunning():
                hilo.wait(5000)

    def _crear_atajos(self):
        """Lo que se usa cada dia, a un tecleo. No se tocan Supr ni Ctrl+Z:
        son de editar celdas."""
        for teclas, accion in (
            ("Ctrl+E", self._escanear),
            ("Ctrl+O", self._cargar),
            ("Ctrl+G", self._exportar_todo),
            ("Ctrl+L", self._ver_escaneos),
            ("Ctrl+R", lambda: self._contrastar_registro()),
        ):
            QShortcut(QKeySequence(teclas), self, activated=accion)

    # ---------- menu / actualizaciones ----------
    def _crear_menu(self):
        escaneos = self.menuBar().addMenu("Escaneos")
        escaneos.addAction("Escanear facturas	Ctrl+E", self._escanear)
        escaneos.addAction("Ver los escaneos guardados…	Ctrl+L",
                           self._ver_escaneos)
        escaneos.addAction("Abrir la carpeta de escaneos",
                           lambda: archivo.abrir(archivo.carpeta_escaneos()))

        comprobar = self.menuBar().addMenu("Comprobar")
        self.btn_registro = comprobar.addAction(
            "Comprobar registro de Aplifisa…\tCtrl+R",
            lambda: self._contrastar_registro())
        self.btn_registro.setEnabled(False)

        ver = self.menuBar().addMenu("Ver")
        self.accion_resumen = ver.addAction("Comprobación de totales por bloque")
        self.accion_resumen.setCheckable(True)
        self.accion_resumen.setChecked(bool(ajustes.leer("ver_resumen", True)))
        self.accion_resumen.toggled.connect(self._ver_resumen)

        config = self.menuBar().addMenu("Configuración")
        config.addAction("API key de Gemini…", self._configurar_key)
        config.addAction("Tope de gasto al mes…", self._configurar_tope)
        config.addAction("Carpeta de documentación digitalizada…",
                         self._configurar_carpeta_escaneos)
        config.addAction("Calidad de lectura y coste…", self._configurar_calidad)
        config.addAction("Textos de conceptos para Aplifisa…", self._configurar_textos)

        menu = self.menuBar().addMenu("Ayuda")
        menu.addAction("Buscar actualizaciones",
                       lambda: self._comprobar_actualizaciones(silencioso=False))
        menu.addAction("Novedades de esta versión…",
                       lambda: self._mostrar_notas_version(forzar=True))
        menu.addAction("Diagnóstico y sugerencias…",
                       lambda: self._mostrar_pendientes(al_arrancar=False))
        menu.addAction("Acerca de", self._acerca_de)

        # Accesos diarios en una franja compacta bajo los menús. Separarlos
        # evita que menús y botones se pisen a 1024 px de ancho.
        self.barra_rapida = QWidget()
        self.barra_rapida.setObjectName("barraRapida")
        accesos = QHBoxLayout(self.barra_rapida)
        accesos.setContentsMargins(6, 3, 8, 3)
        accesos.setSpacing(6)
        accesos.addStretch(1)

        self.btn_cargar = QPushButton("Abrir PDF")
        self.btn_cargar.setObjectName("accesoRapido")
        self.btn_cargar.setIcon(QIcon(ruta_recurso("open.svg")))
        self.btn_cargar.setToolTip("Abrir un PDF ya escaneado o fotos.  (Ctrl+O)")
        self.btn_cargar.clicked.connect(self._cargar)
        accesos.addWidget(self.btn_cargar)

        self.btn_escanear = QPushButton("Escanear")
        self.btn_escanear.setObjectName("accesoRapido")
        self.btn_escanear.setIcon(QIcon(ruta_recurso("scan.svg")))
        self.btn_escanear.setToolTip(
            "Escanea el taco del alimentador, guarda el PDF con el nombre del "
            "cliente y lo mete en el lote.  (Ctrl+E)")
        self.btn_escanear.clicked.connect(self._escanear)
        accesos.addWidget(self.btn_escanear)

        self.btn_vaciar = QPushButton("Vaciar todo")
        self.btn_vaciar.setObjectName("accesoPeligro")
        self.btn_vaciar.setIcon(QIcon(ruta_recurso("trash.svg")))
        self.btn_vaciar.setToolTip("Quita todas las facturas del lote actual.")
        self.btn_vaciar.clicked.connect(self._vaciar_todo)
        accesos.addWidget(self.btn_vaciar)

        self.btn_gastos = QPushButton("Exportar a Aplifisa")
        self.btn_gastos.setObjectName("accesoExito")
        self.btn_gastos.setIcon(QIcon(ruta_recurso("export.svg")))
        self.btn_gastos.setEnabled(False)
        self.btn_gastos.clicked.connect(self._exportar_todo)
        self.btn_ventas = self.btn_gastos
        accesos.addWidget(self.btn_gastos)


    def _mostrar_notas_version_al_arrancar(self):
        self._mostrar_notas_version(forzar=False)

    def _mostrar_notas_version(self, forzar: bool = False):
        if not forzar and notas_version.ya_vistas(__version__):
            return
        DialogoNotasVersion(__version__, self).exec()

    def _mostrar_pendientes(self, al_arrancar: bool):
        """Lo que hace falta saber para seguir afinando el programa, y un hueco
        para contestar. Al arrancar solo salta una vez por version."""
        if al_arrancar and (pendientes.ya_visto(__version__)
                            or not pendientes.leer_pendientes()):
            return
        DialogoPendientes(__version__, self, al_arrancar=al_arrancar).exec()

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

    def _guardar_sesion(self) -> None:
        """Conserva lote, correcciones, imágenes y bloques para la próxima vez."""
        if not self._bloques and not self.filas:
            sesion.borrar()
            return
        filas = []
        for fila in range(self.tabla.rowCount()):
            registro = self.filas[fila]
            filas.append({
                "png": registro["png"],
                "factura": self._leer_fila(fila),
                "aviso": registro.get("aviso", ""),
                "bloque": registro.get("bloque", ""),
                "fuentes": registro.get("fuentes", []),
                "tipo": self._tipo_fila(fila),
                "cuenta": self.tabla.item(fila, C_CUENTA).text(),
                "gxx": self.tabla.item(fila, C_GXX).text(),
            })
        sesion.guardar({
            "bloques": self._bloques,
            "filas": filas,
            "cliente_nif": getattr(self, "_cliente_nif", ""),
            "cliente_nombre": getattr(self, "_cliente_nombre", ""),
            "hay_recargo": getattr(self, "_hay_recargo", False),
            "regimen_recargo": self.combo_recargo.currentData(),
        })

    def _restaurar_sesion(self) -> None:
        datos = sesion.cargar()
        if not datos or not datos.get("bloques"):
            return
        try:
            self._bloques = datos["bloques"]
            self._cliente_nif = datos.get("cliente_nif", "")
            self._cliente_nombre = datos.get("cliente_nombre", "")
            self._hay_recargo = bool(datos.get("hay_recargo"))
            self.fila_recargo.setVisible(self._hay_recargo)
            self.chk_hay_recargo.setChecked(self._hay_recargo)
            regimen = datos.get("regimen_recargo", DESGLOSE)
            indice = self.combo_recargo.findData(regimen)
            self.combo_recargo.blockSignals(True)
            self.combo_recargo.setCurrentIndex(max(0, indice))
            self.combo_recargo.blockSignals(False)
            self._actualizar_combo_bloques()
            self.tabla.setRowCount(0)
            self.filas = []
            for fila in datos.get("filas", []):
                self._anadir_fila(
                    fila["png"], fila["factura"], fila["tipo"],
                    fila["cuenta"], fila["gxx"], fila.get("aviso", ""),
                    fila.get("bloque", ""), fila.get("fuentes"))
            self._pintar_cliente()
            self._revalidar_todo()
            hay_datos = self.tabla.rowCount() > 0
            self.btn_gastos.setEnabled(hay_datos)
            self.btn_registro.setEnabled(hay_datos)
            self.btn_cliente.setEnabled(bool(self._bloques))
            if hay_datos:
                self.tabla.selectRow(0)
            self.lbl_estado.setText(
                f"Sesión recuperada: {len(self._bloques)} bloque(s) y "
                f"{self.tabla.rowCount()} línea(s).")
        except Exception:
            # Una sesión antigua o dañada nunca debe impedir abrir el programa.
            self._bloques = []
            self.tabla.setRowCount(0)
            self.filas = []
            self._limpiar_visor()

    def closeEvent(self, ev):
        # No destruir QThreads vivos (abortaria el proceso)
        self.esperar_hilos()
        try:
            self._guardar_sesion()
        except Exception:
            pass
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

    def _configurar_tope(self):
        euros, ok = QInputDialog.getDouble(
            self, "Tope de gasto al mes",
            "Aviso cuando el gasto en Gemini del mes pase de (€):\n"
            "(solo avisa; el límite de verdad se pone en Google)",
            costes.tope(), 0.0, 1000.0, 2)
        if ok:
            costes.guardar_tope(euros)
            self._pintar_gasto()

    def _pintar_gasto(self, modelo="", coste_lote=0.0):
        """Modelo que ha contestado, coste del lote y gasto del mes."""
        self.lbl_gasto.setText(costes.resumen(modelo, coste_lote))

    def _on_gasto(self, modelo, coste_lote):
        self._pintar_gasto(modelo, coste_lote)
        aviso = costes.aviso_tope()
        if aviso and not getattr(self, "_aviso_tope_dado", False):
            # Una vez por sesion: recordarlo en cada lote seria un incordio.
            self._aviso_tope_dado = True
            QMessageBox.warning(self, "Gasto de Gemini", aviso)

    def _ofrecer_contraste(self, ruta):
        """Se ha soltado el listado de Aplifisa en vez de facturas."""
        if not self.tabla.rowCount():
            QMessageBox.information(
                self, "Listado de Aplifisa",
                f"«{os.path.basename(ruta)}» es el listado de apuntes de "
                f"Aplifisa, no un taco de facturas.\n\n"
                f"Cargue primero las facturas y luego pulse «Comprobar "
                f"registro» para cuadrarlas con él.")
            return
        if QMessageBox.question(
                self, "Listado de Aplifisa",
                f"«{os.path.basename(ruta)}» parece el listado de apuntes de "
                f"Aplifisa.\n\n¿Lo contrasto con las facturas del lote?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes) == QMessageBox.Yes:
            self._contrastar_registro(ruta)

    def _contrastar_registro(self, ruta=""):
        """El cuadre a tres bandas: factura -> Excel -> lo que quedo en Aplifisa.

        Se le pasa el PDF del "Listado de apuntes" de Aplifisa y se compara
        apunte a apunte con el lote. Es la unica forma de ver si algo se quedo
        sin importar o entro con otro importe.
        """
        if not self.tabla.rowCount():
            QMessageBox.information(
                self, "Contrastar con Aplifisa",
                "Cargue primero el lote de facturas que quiere comprobar.")
            return
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(
                self, "Listado de apuntes de Aplifisa (PDF)", ESCRITORIO,
                "Listado de Aplifisa (*.pdf)")
        if not ruta:
            return
        try:
            registro = leer_registro(ruta)
        except Exception as e:
            QMessageBox.critical(self, "No se pudo leer el listado", str(e))
            return
        if not registro.apuntes:
            QMessageBox.warning(
                self, "Sin apuntes",
                "No se han encontrado apuntes en ese PDF.\n\n"
                "Tiene que ser el listado que imprime Aplifisa. Un PDF de papel "
                "escaneado no sirve: hay que sacarlo del propio programa.")
            return
        facturas = [self._leer_fila(r) for r in range(self.tabla.rowCount())]
        informe = contrastar(facturas, registro)
        DialogoRegistro(informe, registro, self).exec()
        self.lbl_estado.setText(
            f"Contraste con Aplifisa: {informe.emparejadas} cuadran, "
            f"{len(informe.sin_registrar)} sin registrar, "
            f"{len(informe.de_mas)} de más, {len(informe.distintas)} distintas.")

    def _ver_resumen(self, visible: bool):
        """El resumen es solo un punto de control: si estorba, se quita."""
        ajustes.guardar("ver_resumen", bool(visible))
        if hasattr(self, "resumen_card"):
            self.resumen_card.setVisible(bool(visible))
        if hasattr(self, "accion_resumen") and self.accion_resumen.isChecked() != visible:
            self.accion_resumen.setChecked(bool(visible))

    def _configurar_textos(self):
        """La lista de textos que hay que parametrizar una vez en Aplifisa."""
        dialogo = DialogoTextos(self)
        if dialogo.exec() == QDialog.Accepted:
            dialogo.guardar()
            self.lbl_estado.setText(
                "El Excel llevará el TEXTO del concepto (Aplifisa le pondrá la "
                "subclave sola)."
                if ajustes.leer("concepto_texto", False) else
                "El Excel llevará el código de la cuenta.")

    def _configurar_carpeta_escaneos(self):
        actual = ajustes.leer("carpeta_escaneos", escaner.carpeta_por_defecto())
        carpeta = QFileDialog.getExistingDirectory(
            self, "Carpeta de documentación digitalizada", actual)
        if carpeta:
            ajustes.guardar("carpeta_escaneos", carpeta)
            self.lbl_estado.setText(
                f"Los PDF originales y Excel consolidados se guardarán en {carpeta}")

    def _configurar_calidad(self):
        """Con qué detalle se le manda cada factura a Gemini: es lo único que
        cambia el coste. La calidad del ESCANEO se elige al escanear."""
        dialogo = DialogoCalidad(self)
        if dialogo.exec() == QDialog.Accepted:
            dialogo.guardar()
            self.lbl_estado.setText(
                f"Las facturas se leerán a {dialogo.ppp()} ppp "
                f"({costes._eur(costes.coste_por_factura(dialogo.ppp()))} cada una).")

    # ---------- escaneo ----------
    def _escanear(self):
        if getattr(self, "_hilo_escaneo", None) and self._hilo_escaneo.isRunning():
            QMessageBox.information(self, "Escaneando",
                                    "Espere a que termine el escaneo en curso.")
            return
        disponibles = escaner.escaneres()
        if not disponibles:
            QMessageBox.warning(
                self, "Sin escáner",
                "Windows no ve ningún escáner.\n\nCompruebe que la impresora "
                "está encendida y conectada, y vuelva a intentarlo.\n\n"
                "Mientras tanto puede usar «Abrir PDF o imágenes».")
            return
        dialogo = DialogoEscaneo(disponibles, nombres_conocidos(), self)
        if dialogo.exec() != QDialog.Accepted:
            return
        dialogo.recordar()
        opciones = dialogo.valores()
        opciones["nombre_dispositivo"] = dialogo.combo_escaner.currentText()
        # Sin cliente no se para: el PDF nace en "Sin identificar" y se muda
        # solo a su carpeta cuando el programa averigua de quién es por el NIF.
        if opciones["cliente"]:
            destino = escaner.ruta_destino(
                opciones["carpeta"], opciones["cliente"], opciones["tipo"])
        else:
            destino = archivo.ruta_provisional(opciones["carpeta"],
                                               opciones["tipo"])
        self._tipo_escaneo = opciones["tipo"]
        self._escaneo_reciente = True
        self._hojas_puestas = opciones.get("hojas", 0)
        self._escaneo_sin_identificar = not opciones["cliente"]
        self.btn_escanear.setEnabled(False)
        self.btn_cargar.setEnabled(False)
        self.progreso.setVisible(True)
        self.progreso.setRange(0, 0)          # no se sabe cuántas hojas hay
        self.lbl_estado.setText("Escaneando… no retire las hojas del alimentador.")
        self._hilo_escaneo = HiloEscaneo(destino, opciones)
        self._hilo_escaneo.progreso.connect(
            lambda n: self.lbl_estado.setText(f"Escaneando… {n} hoja(s)."))
        self._hilo_escaneo.terminado.connect(self._on_escaneo_hecho)
        self._hilo_escaneo.fallo.connect(self._on_escaneo_fallo)
        self._hilo_escaneo.start()

    def _ver_escaneos(self):
        """Los PDF que va generando el escaneo: abrirlos, recolocarlos o
        volver a pasarlos por el programa."""
        dialogo = DialogoEscaneos(self)
        if dialogo.exec() == QDialog.Accepted and dialogo.rutas_elegidas:
            self.procesar_rutas(dialogo.rutas_elegidas)

    def _on_escaneo_hecho(self, ruta):
        self.progreso.setRange(0, 100)
        self.btn_escanear.setEnabled(True)
        self.lbl_estado.setText(f"Escaneado y guardado en {ruta}")
        self._avisar_hojas_perdidas(ruta)
        # Directo al lote: es el flujo que se pidio, sin pasar por abrir archivo.
        self.procesar_rutas([ruta], desde_escaner=True)

    def _avisar_hojas_perdidas(self, ruta):
        """El alimentador arrastra a veces dos hojas pegadas: salen menos
        páginas de las que se pusieron y esa factura no se registra."""
        puestas = getattr(self, "_hojas_puestas", 0)
        if not puestas:
            return
        try:
            import fitz
            with fitz.open(ruta) as doc:
                leidas = doc.page_count
        except Exception:
            return
        if leidas >= puestas:
            return
        QMessageBox.warning(
            self, "Faltan hojas",
            f"Puso {puestas} hojas y solo se han escaneado {leidas}.\n\n"
            f"El alimentador suele arrastrar dos hojas pegadas. Compruebe qué "
            f"factura falta (el programa avisa también si ve un salto en la "
            f"numeración) y escanee esas hojas aparte: se añadirán al lote.")

    def _on_escaneo_fallo(self, mensaje):
        self.progreso.setRange(0, 100)
        self.progreso.setVisible(False)
        self.btn_escanear.setEnabled(True)
        self.btn_cargar.setEnabled(True)
        self._escaneo_reciente = False
        self._escaneo_sin_identificar = False
        self.lbl_estado.setText("No se pudo escanear.")
        QMessageBox.critical(self, "Error al escanear", mensaje)

    # ---------- carga ----------
    def _cargar(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Elige facturas (PDF o imágenes)", ESCRITORIO,
            "Facturas (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if rutas:
            self.procesar_rutas(rutas)

    def procesar_rutas(self, rutas, desde_escaner: bool = False):
        """Añade documentos a la cola, dividiendo los PDF largos en bloques."""
        rutas = [os.path.abspath(r) for r in rutas
                 if os.path.isfile(r) and os.path.splitext(r)[1].lower() in EXT_FACTURA]
        if not rutas:
            QMessageBox.warning(self, "Archivos no compatibles",
                                "No se encontraron PDFs o imágenes válidas.")
            return
        sin_identificar = (len(rutas) == 1 and archivo.sin_identificar(rutas[0]))
        # Si lo que se ha soltado es el listado de Aplifisa, NO se manda a
        # Gemini: aqui se lee gratis y lo que se quiere es contrastarlo.
        listados = [r for r in rutas if r.lower().endswith(".pdf")
                    and parece_listado(r)]
        if listados:
            self._ofrecer_contraste(listados[0])
            rutas = [r for r in rutas if r not in listados]
            if not rutas:
                return
        api_key = leer_api_key()
        if not api_key:
            QMessageBox.warning(self, "Falta la API key",
                                "Configura primero tu API key de Gemini.")
            return
        elementos = []
        try:
            for ruta in rutas:
                if ruta.lower().endswith(".pdf"):
                    partes = dividir_pdf(ruta, PAGINAS_POR_BLOQUE)
                    for numero, parte in enumerate(partes, 1):
                        mover_original = bool(desde_escaner or sin_identificar)
                        elementos.append({
                            "rutas": [parte],
                            "original": ruta,
                            "etiqueta": os.path.splitext(os.path.basename(parte))[0],
                            "parte": numero,
                            "partes": len(partes),
                            # Todo PDF termina en el archivo documental. Los
                            # externos se COPIAN; solo se mueve el provisional
                            # creado por el escáner de la propia aplicación.
                            "archivar": True,
                            "mover_original": mover_original,
                            "desde_escaner": bool(desde_escaner),
                            "sin_identificar": bool(sin_identificar),
                            "tipo_escaneo": self._tipo_escaneo,
                        })
                else:
                    elementos.append({
                        "rutas": [ruta], "original": ruta,
                        "etiqueta": os.path.splitext(os.path.basename(ruta))[0],
                        "parte": 1, "partes": 1,
                        "archivar": False,
                        "mover_original": False,
                        "desde_escaner": bool(desde_escaner),
                        "sin_identificar": bool(sin_identificar),
                        "tipo_escaneo": self._tipo_escaneo,
                    })
        except Exception as e:
            QMessageBox.critical(
                self, "No se pudo preparar el PDF",
                f"No se ha añadido a la cola:\n\n{e}")
            return

        en_curso = bool(getattr(self, "worker", None) and self.worker.isRunning())
        if not en_curso and not self._cola:
            self._cola_total = 0
            self._cola_completados = 0
        self._cola.extend(elementos)
        self._cola_total += len(elementos)
        self.btn_gastos.setEnabled(False)
        self.btn_ventas.setEnabled(False)
        self.progreso.setVisible(True)
        self.progreso.setValue(0)
        if en_curso:
            self.lbl_estado.setText(
                f"Añadidos {len(elementos)} bloque(s). Cola total: "
                f"{self._cola_completados + 1}/{self._cola_total} en curso.")
            return
        self._iniciar_siguiente_cola(api_key)

    def _iniciar_siguiente_cola(self, api_key=None):
        if not self._cola:
            self._elemento_cola_actual = None
            self.progreso.setVisible(False)
            self.btn_cargar.setEnabled(True)
            hay_datos = self.tabla.rowCount() > 0
            self.btn_gastos.setEnabled(hay_datos)
            self.btn_registro.setEnabled(hay_datos)
            self.lbl_estado.setText(
                f"Cola terminada: {self._cola_completados} bloque(s) procesado(s).")
            return
        api_key = api_key or leer_api_key()
        if not api_key:
            self.lbl_estado.setText("Cola pendiente: falta la API key de Gemini.")
            return
        elemento = self._cola.pop(0)
        self._elemento_cola_actual = elemento
        self._rutas_actuales = list(elemento["rutas"])
        self._tipo_escaneo = elemento["tipo_escaneo"]
        self._escaneo_reciente = elemento["desde_escaner"]
        self._escaneo_sin_identificar = elemento["sin_identificar"]
        self.lbl_origen.setText(elemento["etiqueta"])
        actual = self._cola_completados + 1
        self.lbl_estado.setText(
            f"Cola {actual}/{self._cola_total}: leyendo {elemento['etiqueta']}…")
        self.worker = Worker(self._rutas_actuales, api_key)
        self.worker.progreso.connect(self._on_progreso)
        self.worker.gasto.connect(self._on_gasto)
        self.worker.terminado.connect(self._on_terminado)
        self.worker.fallo.connect(self._on_fallo)
        self.worker.start()

    def _on_progreso(self, actual, total):
        self.progreso.setMaximum(total)
        self.progreso.setValue(actual)
        bloque = self._cola_completados + 1
        self.lbl_estado.setText(
            f"Cola {bloque}/{self._cola_total} · páginas {actual}/{total}")

    def _on_fallo(self, msg):
        self._limpiar_parte_interna(self._elemento_cola_actual or {})
        self._cola_completados += 1
        self._escaneo_reciente = False
        QMessageBox.critical(
            self, "Error en un bloque",
            f"Este bloque no se pudo procesar, pero la cola continuará:\n\n{msg}")
        self._iniciar_siguiente_cola()

    def _on_terminado(self, procesadas, nombre, nif, crudos=None):
        elemento = self._elemento_cola_actual or {}
        rutas_parte = list(self._rutas_actuales)
        # Si el escaneo salió sin saber de quién era, ahora ya se sabe: el PDF
        # se muda solo a la carpeta del cliente antes de nombrar el bloque.
        if elemento.get("archivar"):
            original_anterior = elemento.get("original", "")
            self._rutas_actuales = [original_anterior]
            self._recolocar_escaneo(
                nombre, procesadas,
                copiar=not elemento.get("mover_original", False))
            original_nuevo = self._rutas_actuales[0]
            elemento["original"] = original_nuevo
            for pendiente in self._cola:
                if pendiente.get("original") == original_anterior:
                    pendiente["original"] = original_nuevo
                    pendiente["archivar"] = False
                    pendiente["mover_original"] = False
                    pendiente["desde_escaner"] = False
                    pendiente["sin_identificar"] = False
        elif not elemento:
            # También conserva el contrato de llamadas directas (pruebas y
            # pequeñas integraciones que entregan un bloque ya procesado).
            self._recolocar_escaneo(nombre, procesadas)
        if elemento:
            self._rutas_actuales = rutas_parte
            # Una parte interna no es documentación. Las filas y los datos
            # crudos deben apuntar siempre al PDF completo archivado y conservar
            # el número de página global para poder borrar la parte temporal.
            origen_documento = elemento.get("original", "")
            desplazamiento = ((elemento.get("parte", 1) - 1)
                              * PAGINAS_POR_BLOQUE)
            if origen_documento:
                for _, pr in procesadas:
                    pr.origen = origen_documento
                    pr.pagina += desplazamiento
                    for factura in pr.facturas:
                        factura.origen_imagen = origen_documento
                crudos = [
                    (imagen, origen_documento, pagina + desplazamiento, datos)
                    for imagen, _origen, pagina, datos in (crudos or [])
                ]
        # Cada carga entra como un BLOQUE mas: asi se pueden juntar varios PDF
        # de escaner (25-30 hojas cada uno) en un unico Excel para Aplifisa.
        self._bloques.append({
            "nombre": self._nombre_bloque(elemento.get("etiqueta")),
            "procesadas": procesadas,
            # Lo leido por Gemini, tal cual: permite rehacer el lote con otro
            # cliente sin gastar otra lectura.
            "crudos": list(crudos or []),
            "cliente": nombre,
            "nif": nif,
            # Lo que dijo el usuario al escanear ("gastos" o "ingresos"): sirve
            # para cazar una factura que sale del reves.
            "tipo_declarado": (self._tipo_escaneo
                               if self._escaneo_reciente else ""),
        })
        self._escaneo_reciente = False
        self._avisar_si_otro_cliente(nombre, nif)
        # El nombre del cliente se guarda para proponerlo al escanear el
        # proximo taco suyo, sin tener que escribirlo otra vez.
        recordar_nombre(nif, nombre)
        self._cliente_nif, self._cliente_nombre = nif, nombre
        self._pintar_cliente()
        # Primero se confirma quién es el cliente; solo después tiene sentido
        # decidir si la otra parte contradice un NIF guardado de proveedor.
        if self._analisis_del_lote().dudoso:
            self._cambiar_cliente(automatico=True)
        self._resolver_conflictos_nif()
        self._preparar_recargo()
        self._actualizar_combo_bloques()
        self._rellenar_tabla()
        self._revalidar_todo()
        hay_datos = self.tabla.rowCount() > 0
        self.btn_gastos.setEnabled(hay_datos)
        self.btn_ventas.setEnabled(hay_datos)
        self.btn_registro.setEnabled(hay_datos)
        self.btn_cliente.setEnabled(bool(self._bloques))
        if hay_datos and len(self._bloques) == 1:
            self.tabla.selectRow(0)
        self._avisar_paginas_no_leidas()
        self._limpiar_parte_interna(elemento)
        self._cola_completados += 1
        self._iniciar_siguiente_cola()

    @staticmethod
    def _quitar_aviso_conflicto(pr, mensaje: str) -> None:
        """Retira únicamente el aviso que acaba de quedar resuelto."""
        if pr.aviso == mensaje:
            pr.aviso = ""
        else:
            pr.aviso = " ".join(pr.aviso.replace(mensaje, "").split())

    def _decidir_conflicto_nif(self, nombre: str, guardado: str,
                               leido: str, cantidad: int) -> str:
        """Pregunta una vez cuando varias facturas contradicen la memoria."""
        cuadro = QMessageBox(self)
        cuadro.setWindowTitle("Confirmar CIF/NIF del proveedor")
        cuadro.setIcon(QMessageBox.Warning)
        cuadro.setText(
            f"Para {nombre} está guardado <b>{guardado}</b>, pero "
            f"{cantidad} facturas de este lote muestran <b>{leido}</b>.")
        cuadro.setInformativeText(
            "El programa no cambiará lo aprendido sin que usted lo confirme.")
        mantener = cuadro.addButton("Mantener el guardado", QMessageBox.AcceptRole)
        sustituir = cuadro.addButton("Usar el nuevo y recordarlo", QMessageBox.ActionRole)
        revisar = cuadro.addButton("Dejar pendiente", QMessageBox.RejectRole)
        cuadro.setDefaultButton(revisar)
        cuadro.exec()
        pulsado = cuadro.clickedButton()
        if pulsado is mantener:
            return "guardado"
        if pulsado is sustituir:
            return "nuevo"
        return "revisar"

    def _resolver_conflictos_nif(self) -> None:
        """Contrasta la memoria con la evidencia acumulada de todo el lote."""
        grupos = {}
        for bloque in self._bloques:
            for _imagen, pr in bloque.get("procesadas", []):
                conflicto = getattr(pr, "conflicto_nif", None)
                if not conflicto:
                    continue
                clave = (clave_proveedor(conflicto["nombre"]),
                         conflicto["guardado"], conflicto["leido"])
                grupos.setdefault(clave, []).append(pr)

        for clave_grupo, procesadas in grupos.items():
            _clave, guardado, leido = clave_grupo
            decision = self._decisiones_conflicto_nif.get(clave_grupo)
            if decision:
                self._aplicar_decision_conflicto_nif(
                    procesadas, decision, guardado, leido)
                continue
            # Una discrepancia aislada se ve en amarillo. Con evidencia
            # repetida se pregunta una sola vez por todo el grupo.
            if len(procesadas) < 3:
                continue
            if any(pr.conflicto_nif.get("consultado") for pr in procesadas):
                for pr in procesadas:
                    pr.conflicto_nif["consultado"] = True
                continue
            nombre = procesadas[0].conflicto_nif["nombre"]
            decision = self._decidir_conflicto_nif(
                nombre, guardado, leido, len(procesadas))
            self._decisiones_conflicto_nif[clave_grupo] = decision
            self._aplicar_decision_conflicto_nif(
                procesadas, decision, guardado, leido)

    def _aplicar_decision_conflicto_nif(self, procesadas, decision: str,
                                        guardado: str, leido: str) -> None:
        """Aplica la decisión a este grupo y a sus partes posteriores."""
        nombre = procesadas[0].conflicto_nif["nombre"]
        if decision == "guardado":
            recordar_nif(nombre, guardado, manual=True)
            for pr in procesadas:
                for factura in pr.facturas:
                    factura.nif = guardado
        elif decision == "nuevo":
            recordar_nif(nombre, leido, manual=True)
        for pr in procesadas:
            conflicto = pr.conflicto_nif
            if decision != "revisar":
                self._quitar_aviso_conflicto(pr, conflicto["mensaje"])
                pr.conflicto_nif = None
            else:
                conflicto["consultado"] = True

    def _avisar_paginas_no_leidas(self):
        """Detalla las páginas agotadas o ilegibles sin detener la cola."""
        fallos = getattr(getattr(self, "worker", None), "fallos", None)
        if not fallos:
            return
        salto = chr(10)
        detalle = salto.join(
            f"· {os.path.basename(ruta) or 'documento'}, página {pagina}: {motivo}"
            for ruta, pagina, motivo in fallos[:10])
        if len(fallos) > 10:
            detalle += f"{salto}· … y {len(fallos) - 10} más"
        QMessageBox.warning(
            self, "Páginas sin leer",
            f"{len(fallos)} página(s) no se han podido leer y están en rojo "
            f"en la tabla:{salto}{salto}{detalle}{salto}{salto}"
            "La cola continúa. Puede volver a cargar solo esas páginas.")

    def _limpiar_parte_interna(self, elemento: dict) -> None:
        """Borra una parte ya procesada, nunca el PDF original del usuario."""
        if int(elemento.get("partes", 1) or 1) <= 1:
            return
        raiz = os.path.abspath(os.path.join(dir_datos(), "cola_pdf"))
        for ruta in elemento.get("rutas", []):
            ruta_abs = os.path.abspath(ruta)
            if not os.path.normcase(ruta_abs).startswith(
                    os.path.normcase(raiz) + os.sep):
                continue
            try:
                os.remove(ruta_abs)
                carpeta = os.path.dirname(ruta_abs)
                if os.path.isdir(carpeta) and not os.listdir(carpeta):
                    os.rmdir(carpeta)
            except OSError:
                pass

    def _recolocar_escaneo(self, cliente, procesadas, copiar: bool = False):
        """Archiva el PDF original por cliente, ejercicio y tipo.

        Al escanear no hace falta decir de quién son las facturas: el programa
        lo averigua por el NIF que se repite y coloca el archivo despues. Si no
        lo averigua, el PDF se queda en «Sin identificar» y se puede colocar a
        mano desde «Escaneos guardados».
        """
        if (not copiar and not self._escaneo_reciente
                and not self._escaneo_sin_identificar) \
                or len(self._rutas_actuales) != 1:
            return
        ruta = self._rutas_actuales[0]
        if not cliente:
            return
        ventas = sum(1 for _, pr in procesadas if pr.tipo == "venta")
        tipo = "ingresos" if ventas > len(procesadas) / 2 else "gastos"
        ejercicios = []
        for _, pr in procesadas:
            if not pr.facturas:
                continue
            fecha = fecha_de(pr.facturas[0].fecha)
            if fecha:
                ejercicios.append(fecha.year)
        ejercicio = Counter(ejercicios).most_common(1)[0][0] if ejercicios else None
        if len(set(ejercicios)) > 1:
            aviso = ("El PDF mezcla varios ejercicios; se ha archivado en el "
                     f"{ejercicio}, que es el más frecuente. Revise su ubicación.")
            for _, pr in procesadas:
                pr.aviso = f"{pr.aviso} {aviso}".strip()
        if copiar:
            nueva = archivo.copiar_a_cliente(
                ruta, cliente, tipo, ejercicio=ejercicio)
        else:
            nueva = archivo.mover_a_cliente(
                ruta, cliente, tipo, ejercicio=ejercicio)
        if nueva == ruta:
            return
        self._escaneo_sin_identificar = False
        self._rutas_actuales = [nueva]
        for _, pr in procesadas:     # que la miniatura siga apuntando al PDF
            pr.origen = nueva
            for f in pr.facturas:
                f.origen_imagen = nueva
        self.lbl_estado.setText(
            f"Documento archivado en {cliente} / {ejercicio or 'ejercicio actual'} / "
            f"{'Ingresos' if tipo == 'ingresos' else 'Gastos'}")

    def _analisis_del_lote(self):
        """Las partes que salen en TODO el lote (todos los bloques)."""
        datos = [d for bloque in self._bloques for *_, d in bloque.get("crudos", [])]
        return analizar_cliente(datos)

    def _cambiar_cliente(self, automatico: bool = False):
        """Quien es el cliente de la asesoria en este lote.

        Al cambiarlo se rehace todo desde lo que ya leyo Gemini: no se vuelve a
        pagar ninguna lectura.
        """
        analisis = self._analisis_del_lote()
        if len(analisis.candidatos) < 2:
            if not automatico:
                QMessageBox.information(
                    self, "Cliente del lote",
                    "En estas facturas solo se ha identificado una parte con "
                    "NIF, así que no hay entre quién elegir.")
            return
        dialogo = DialogoCliente(analisis.candidatos, self,
                                 elegido=getattr(self, "_cliente_nif", ""))
        if dialogo.exec() != QDialog.Accepted:
            return
        elegido = dialogo.elegido()
        if not elegido or not elegido.nif:
            return
        # Lo que dice una persona manda y se recuerda; y a los demas del lote
        # se les apunta como proveedores, que es lo que son.
        marcar_cliente(elegido.nif, elegido.nombre)
        for otro in analisis.candidatos:
            if otro.nif != elegido.nif and otro.nombre and otro.nif:
                recordar_nif(otro.nombre, otro.nif, manual=True)
        self._rehacer_con_cliente(elegido.nombre, elegido.nif)

    def _rehacer_con_cliente(self, nombre, nif):
        """Vuelve a montar todos los bloques con otro cliente, sin Gemini."""
        for bloque in self._bloques:
            if bloque.get("crudos"):
                bloque["procesadas"] = preparar_lote(bloque["crudos"], nombre, nif)
                bloque["cliente"], bloque["nif"] = nombre, nif
        self._cliente_nif, self._cliente_nombre = nif, nombre
        self._pintar_cliente()
        self._preparar_recargo()
        self._rellenar_tabla()
        self._revalidar_todo()
        self.lbl_estado.setText(f"Lote rehecho con {nombre or nif} como cliente.")

    def _nombre_bloque(self, base_preferido: str = "") -> str:
        """Nombre corto del bloque: el del PDF cargado, sin repetirse."""
        rutas = self._rutas_actuales
        if base_preferido:
            base = base_preferido
        elif not rutas:
            base = f"Bloque {len(self._bloques) + 1}"
        elif len(rutas) == 1:
            base = os.path.splitext(os.path.basename(rutas[0]))[0]
        else:
            base = f"{os.path.splitext(os.path.basename(rutas[0]))[0]} +{len(rutas) - 1}"
        usados = {b["nombre"] for b in self._bloques}   # aun no se ha añadido
        nombre, n = base, 2
        while nombre in usados:
            nombre, n = f"{base} ({n})", n + 1
        return nombre

    def _avisar_si_otro_cliente(self, nombre, nif):
        """Mezclar clientes en un mismo Excel es un lio gordo: hay que verlo."""
        anteriores = {b["nif"] for b in self._bloques[:-1] if b["nif"]}
        if not anteriores or not nif or nif in anteriores:
            return
        previo = next(b for b in self._bloques[:-1] if b["nif"])
        QMessageBox.warning(
            self, "¿Facturas de otro cliente?",
            f"Este bloque parece de OTRO cliente:\n\n"
            f"  · Bloques anteriores: {previo['cliente'] or '?'} "
            f"({previo['nif']})\n"
            f"  · Bloque nuevo: {nombre or '?'} ({nif})\n\n"
            "Se ha añadido igualmente, pero el Excel saldría con facturas de "
            "los dos. Si es un error, use «Quitar este bloque».")

    def _pintar_cliente(self):
        """Cliente del lote. Si hay bloques de varios, se dice claramente."""
        nifs = {b["nif"] for b in self._bloques if b["nif"]}
        if len(nifs) > 1:
            self.lbl_cliente.setText(f"⚠ VARIOS CLIENTES en el lote ({len(nifs)})")
            return
        self.lbl_cliente.setText(
            f"{self._cliente_nombre or 'Cliente no identificado'}"
            + (f"  ·  {self._cliente_nif}" if self._cliente_nif else ""))

    def _actualizar_combo_bloques(self):
        actual = self.combo_filtro_bloque.currentText()
        self.combo_filtro_bloque.blockSignals(True)
        self.combo_filtro_bloque.clear()
        self.combo_filtro_bloque.addItem(TODOS_LOS_BLOQUES)
        for b in self._bloques:
            self.combo_filtro_bloque.addItem(b["nombre"])
        i = self.combo_filtro_bloque.findText(actual)
        self.combo_filtro_bloque.setCurrentIndex(max(0, i))
        self.combo_filtro_bloque.blockSignals(False)

    def _quitar_bloque(self):
        nombre = self.combo_filtro_bloque.currentText()
        if nombre == TODOS_LOS_BLOQUES or not self._bloques:
            QMessageBox.information(
                self, "Quitar un bloque",
                "Elija primero un bloque en el desplegable de al lado.")
            return
        if QMessageBox.question(
                self, "Quitar el bloque",
                f"¿Quitar del lote el bloque «{nombre}» y todas sus facturas?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._bloques = [b for b in self._bloques if b["nombre"] != nombre]
        self._ultimo_borrado = []
        self.btn_deshacer_borrado.setEnabled(False)
        self.btn_deshacer_borrado.setVisible(False)
        self.combo_filtro_bloque.setCurrentIndex(0)
        self._actualizar_combo_bloques()
        self._rellenar_tabla()
        self._revalidar_todo()
        hay_datos = self.tabla.rowCount() > 0
        self.btn_gastos.setEnabled(hay_datos)
        self.btn_registro.setEnabled(hay_datos)
        self.lbl_estado.setText(f"Bloque «{nombre}» quitado del lote.")

    def _vaciar_todo(self):
        if not self._bloques and not self.filas:
            self._limpiar_visor()
            sesion.borrar()
            return
        if QMessageBox.question(
                self, "Vaciar todo",
                f"¿Vaciar el lote entero ({len(self._bloques)} bloque(s), "
                f"{self.tabla.rowCount()} línea(s)) y empezar de cero?\n\n"
                "Lo leído se perderá y habría que volver a pasarlo por Gemini.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._bloques = []
        self._cola = []
        self._decisiones_conflicto_nif = {}
        self._ultimo_borrado = []
        self._rutas_actuales = []
        self._duplicados = {}
        self._escaneo_reciente = False
        self._escaneo_sin_identificar = False
        self._cliente_nif = self._cliente_nombre = ""
        self.btn_deshacer_borrado.setEnabled(False)
        self.btn_deshacer_borrado.setVisible(False)
        self.btn_cliente.setEnabled(False)
        self._hay_recargo = False
        self.fila_recargo.setVisible(False)
        self.chk_hay_recargo.setChecked(False)
        self.combo_filtro_estado.setCurrentIndex(0)
        self.combo_filtro_bloque.setCurrentIndex(0)
        self._actualizar_combo_bloques()
        self._rellenar_tabla()
        self.tabla.clearSelection()
        self._limpiar_visor()
        self._revalidar_todo()
        self.btn_gastos.setEnabled(False)
        self.btn_registro.setEnabled(False)
        self.lbl_cliente.setText("Pendiente de detectar")
        self.lbl_estado.setText("Lote vacío. Cargue o escanee facturas para empezar.")
        sesion.borrar()

    def _por_el_total(self) -> bool:
        """El cliente registra sus compras con recargo por el total factura."""
        return (getattr(self, "_hay_recargo", False)
                and self.combo_recargo.currentData() == TOTAL)

    def _rellenar_tabla(self):
        recargo = self._por_el_total()
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(0)
        self.filas = []
        for bloque in self._bloques:
            for png, pr in bloque["procesadas"]:
                fuentes = [f for f in pr.facturas if not f.eliminada]
                if not fuentes:
                    continue
                vista = a_total_factura(replace(pr, facturas=fuentes)) if recargo else pr
                visibles = vista.facturas if recargo else fuentes
                for f in visibles:
                    origenes = fuentes if recargo else [f]
                    self._anadir_fila(
                        png, f, f.tipo_revision or vista.tipo, vista.cuenta,
                        vista.gxx, vista.aviso, bloque["nombre"], origenes)
        self.tabla.blockSignals(False)

    def _on_recargo(self):
        """Cambiar el régimen rehace la tabla: cambia como se registra el gasto."""
        guardar_regimen_recargo(getattr(self, "_cliente_nif", ""),
                                self.combo_recargo.currentData(),
                                getattr(self, "_cliente_nombre", ""))
        self._rellenar_tabla()
        self._revalidar_todo()

    def _facturas_con_recargo(self) -> int:
        """Cuantas lineas del lote traen recargo de equivalencia."""
        return sum(1 for bloque in self._bloques
                   for _, pr in bloque["procesadas"]
                   for f in pr.facturas if f.cuota_requiv)

    def _preparar_recargo(self):
        """Enseña la eleccion solo si hace falta, y la pregunta la primera vez.

        Dos clientes con recargo se llevan distinto segun SU regimen (minorista
        sin 303 -> por el total; mayorista en estimacion directa -> con
        desglose), y eso no se ve en la factura: hay que preguntarlo.
        """
        cuantas = self._facturas_con_recargo()
        self._hay_recargo = bool(cuantas)
        self.fila_recargo.setVisible(self._hay_recargo)
        self.chk_hay_recargo.setChecked(self._hay_recargo)
        if not cuantas:
            return
        nif = getattr(self, "_cliente_nif", "")
        guardado = regimen_recargo(nif)
        if not guardado and nif:
            dialogo = DialogoRecargo(getattr(self, "_cliente_nombre", ""),
                                     cuantas, self)
            guardado = dialogo.elegido() if dialogo.exec() == QDialog.Accepted                 else DESGLOSE
            guardar_regimen_recargo(nif, guardado,
                                    getattr(self, "_cliente_nombre", ""))
        self.combo_recargo.blockSignals(True)
        self.combo_recargo.setCurrentIndex(
            max(0, self.combo_recargo.findData(guardado or DESGLOSE)))
        self.combo_recargo.blockSignals(False)

    def _anadir_fila(self, png, f: Factura, tipo, cuenta, gxx, aviso, bloque="",
                     fuentes=None):
        senales_bloqueadas = self.tabla.signalsBlocked()
        self.tabla.blockSignals(True)
        r = self.tabla.rowCount()
        self.tabla.insertRow(r)
        self.filas.append({"png": png, "factura": f, "aviso": aviso,
                           "bloque": bloque, "fuentes": list(fuentes or [f])})

        est = QTableWidgetItem("")
        est.setFlags(Qt.ItemIsEnabled)
        est.setTextAlignment(Qt.AlignCenter)
        self.tabla.setItem(r, C_ESTADO, est)

        combo = ComboSinRueda()
        combo.addItem("Gasto", "gasto")
        combo.addItem("Ingreso", "venta")
        combo.setCurrentIndex(max(0, combo.findData(f.tipo_revision or tipo)))
        combo.setToolTip(
            "Clasificación dudosa: compruebe si corresponde a Gasto o Ingreso."
            if aviso and ("dudoso" in aviso.lower() or "confirma" in aviso.lower())
            else "Clasificación automática según el NIF y el papel del cliente en la factura.")
        combo.currentIndexChanged.connect(
            lambda _i, control=combo: self._on_tipo_cambiado(control))
        self.tabla.setCellWidget(r, C_TIPO, combo)

        valores = {
            C_CUENTA: cuenta, C_GXX: gxx or "", C_FECHA: f.fecha, C_NUM: f.num_factura,
            C_NOMBRE: f.nombre, C_NIF: f.nif, C_BASE: fmt(f.base_iva),
            C_PCT: fmt(f.pct_iva), C_CUOTA: fmt(f.cuota_iva),
            C_TOTAL: fmt(f.total_impreso),
            C_BLOQUE: bloque,
        }
        for col, val in valores.items():
            item = QTableWidgetItem("" if val is None else str(val))
            if col == C_GXX:
                item.setToolTip(
                    "Subclave del suministro. En Aplifisa la 628 NO puede ir "
                    "sin ella:\n"
                    + "\n".join(f"  {g} = {d}"
                                for g, d in SUBCLAVES_628.items()))
            if col == C_BASE and getattr(f, "es_suplido", False):
                item.setToolTip(
                    "SUPLIDO: se registra como una línea de base más del mismo "
                    "apunte, sin IVA (así lo pide Aplifisa).")
            if col == C_BLOQUE:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setToolTip("Escaneo o PDF del que salió esta factura.")
            self.tabla.setItem(r, col, item)
        self.tabla.setRowHeight(r, 42)
        self.tabla.blockSignals(senales_bloqueadas)

    # ---------- edicion / validacion ----------
    def _on_celda(self, item):
        """Lo que se corrige a mano se guarda para ese proveedor.

        Si no, habria que volver a corregir lo mismo en cada lote: el nombre
        con el que se le llama, su NIF y la cuenta que le toca.
        """
        if item.row() < len(self.filas):
            self.filas[item.row()]["factura"].revision_confirmada = False
        columna = item.column()
        if columna == C_NIF:
            aviso = self._nif_escrito_a_mano(item.row())
        elif columna == C_NOMBRE:
            aviso = self._nombre_escrito_a_mano(item.row())
        elif columna in (C_CUENTA, C_GXX):
            aviso = self._cuenta_escrita_a_mano(item.row())
        else:
            aviso = ""
        self._revalidar_todo()
        if aviso:
            self.lbl_estado.setText(aviso)  # despues: _resumen pisa la barra

    def _on_tipo_cambiado(self, control) -> None:
        fila = self._fila_del_control_tipo(control)
        if 0 <= fila < len(self.filas):
            self.filas[fila]["factura"].revision_confirmada = False
            self.filas[fila]["factura"].tipo_revision = control.currentData()
            for fuente in self.filas[fila].get("fuentes", []):
                fuente.tipo_revision = control.currentData()
        self._revalidar_fila(fila)

    def _nombre_escrito_a_mano(self, r) -> str:
        """El nombre que pone una persona manda, y se copia al resto de
        facturas de ese proveedor (Aplifisa busca la cuenta por nombre EXACTO,
        asi que dos formas de escribirlo pueden acabar en dos cuentas)."""
        if r >= len(self.filas):
            return ""
        f = self._leer_fila(r)
        nif = normaliza_nif(f.nif)
        if not f.nombre or not nif:
            return ""
        if not recordar_nombre_proveedor(nif, f.nombre):
            return ""
        iguales = self._poner_en_las_del_mismo_nif(r, nif, C_NOMBRE, f.nombre)
        aviso = (f"Guardado: este proveedor se llamará «{f.nombre}» "
                 f"a partir de ahora.")
        return aviso + (f"  Puesto en {iguales} línea(s) más." if iguales else "")

    def _cuenta_escrita_a_mano(self, r) -> str:
        """La cuenta que se le pone a un proveedor se le queda puesta, igual
        que hace Aplifisa: sus proximas facturas ya entran con ese concepto."""
        if r >= len(self.filas) or self._tipo_fila(r) != "gasto":
            return ""
        f = self._leer_fila(r)
        cuenta = (self.tabla.item(r, C_CUENTA).text() or "").strip()
        gxx = (self.tabla.item(r, C_GXX).text() or "").strip().upper() or None
        if not f.nombre or not es_valido(cuenta, gxx):
            return ""
        if not recordar_cuenta_proveedor(normaliza_nif(f.nif), f.nombre,
                                         cuenta, gxx):
            return ""
        return (f"Guardado: las facturas de {f.nombre} irán a "
                f"{cuenta}{f' ({gxx})' if gxx else ''} "
                f"{descripcion_de(cuenta, gxx) or ''}".strip())

    def _poner_en_las_del_mismo_nif(self, r, nif, columna, valor) -> int:
        """Aplica un valor al resto de facturas del mismo proveedor del lote."""
        puestas = 0
        self.tabla.blockSignals(True)
        for otra in range(self.tabla.rowCount()):
            if otra == r or normaliza_nif(self._leer_fila(otra).nif) != nif:
                continue
            if self.tabla.item(otra, columna).text() != valor:
                self.tabla.item(otra, columna).setText(valor)
                puestas += 1
        self.tabla.blockSignals(False)
        return puestas

    def _nif_escrito_a_mano(self, r) -> str:
        """Un NIF escrito por una persona vale mas que cualquier lectura: se
        guarda para siempre y se pone ya en el resto de facturas de ese mismo
        proveedor que esten sin el, aqui y en los proximos lotes."""
        if r >= len(self.filas):
            return ""
        f = self._leer_fila(r)
        nif = normaliza_nif(f.nif)
        if not f.nombre or not validar_nif(nif):
            return ""                  # a medio escribir o ilegible: no guardar
        if not recordar_nif(f.nombre, nif, manual=True):
            return ""
        clave = clave_proveedor(f.nombre)
        aplicadas = []
        self.tabla.blockSignals(True)
        for otra in range(self.tabla.rowCount()):
            if otra == r:
                continue
            g = self._leer_fila(otra)
            if clave_proveedor(g.nombre) != clave or validar_nif(normaliza_nif(g.nif)):
                continue
            g.nif = nif
            self.tabla.item(otra, C_NIF).setText(nif)
            self.filas[otra]["aviso"] = (
                f"{self.filas[otra]['aviso']} NIF puesto a mano ({nif}) desde "
                f"otra factura de {f.nombre}.").strip()
            aplicadas.append(otra + 1)
        self.tabla.blockSignals(False)
        aviso = f"NIF {nif} guardado para {f.nombre}: ya no habrá que escribirlo más."
        if aplicadas:
            aviso += ("  Puesto también en la línea "
                      + ", ".join(str(n) for n in aplicadas) + ".")
        return aviso

    def _leer_fila(self, r):
        """Actualiza la Factura de la fila con lo que hay en las celdas."""
        d = self.filas[r]
        f = d["factura"]
        f.concepto = self.tabla.item(r, C_CUENTA).text() or None
        f.subclave = (self.tabla.item(r, C_GXX).text() or "").strip().upper() or None
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
        return w.currentData() if w else "gasto"

    def _fila_del_control_tipo(self, control) -> int:
        """Localiza la fila actual del desplegable incluso después de borrar filas."""
        for fila in range(self.tabla.rowCount()):
            if self.tabla.cellWidget(fila, C_TIPO) is control:
                return fila
        return -1

    def _estado_fila(self, fila: int) -> str:
        celda = self.tabla.item(fila, C_ESTADO)
        return celda.text() if celda else ""

    def _aplicar_filtro(self) -> None:
        opcion = self.combo_filtro_estado.currentIndex()
        bloque = self.combo_filtro_bloque.currentText()
        for fila in range(self.tabla.rowCount()):
            estado = self._estado_fila(fila)
            visible = (
                opcion == 0
                or (opcion == 1 and estado == ICONO_ESTADO[REVISAR])
                or (opcion == 2 and estado == ICONO_ESTADO[ERROR])
                or (opcion == 3 and estado in {ICONO_ESTADO[OK], ICONO_REVISADO})
            )
            if bloque != TODOS_LOS_BLOQUES and self.filas[fila]["bloque"] != bloque:
                visible = False
            self.tabla.setRowHidden(fila, not visible)

    def _siguiente_incidencia(self) -> None:
        total = self.tabla.rowCount()
        if not total:
            return
        inicio = self.tabla.currentRow()
        for salto in range(1, total + 1):
            fila = (inicio + salto) % total
            registro = self.filas[fila]
            f = registro["factura"]
            pendiente = (registro.get("estado") == ERROR or
                         (registro.get("estado") == REVISAR
                          and not f.revision_confirmada
                          and not f.tratamiento_manual))
            if pendiente:
                self.combo_filtro_estado.setCurrentIndex(0)
                self.tabla.selectRow(fila)
                self.tabla.scrollToItem(self.tabla.item(fila, C_ESTADO))
                return
        self.lbl_estado.setText("Todo el lote está correcto y listo para exportar.")

    def _filas_seleccionadas(self) -> list[int]:
        return sorted({i.row() for i in self.tabla.selectionModel().selectedRows()})

    def _marcar_revisada(self) -> None:
        """Da salida únicamente a avisos ámbar comprobados por una persona."""
        filas = self._filas_seleccionadas()
        if not filas:
            QMessageBox.information(
                self, "Revisión", "Seleccione una o varias filas ámbar.")
            return
        confirmadas = 0
        for fila in filas:
            registro = self.filas[fila]
            f = self._leer_fila(fila)
            if (registro.get("estado") == REVISAR
                    and not f.tratamiento_manual):
                f.revision_confirmada = True
                confirmadas += 1
        self._revalidar_todo()
        if confirmadas:
            self.lbl_estado.setText(
                f"{confirmadas} línea(s) revisada(s): ya pueden exportarse.")
        else:
            QMessageBox.information(
                self, "Revisión",
                "Solo se pueden confirmar avisos ámbar. Los errores rojos se "
                "corrigen y las operaciones manuales no se exportan.")

    def _alternar_gestion_manual(self) -> None:
        """Aparta la factura completa, aunque tenga varias líneas de IVA."""
        seleccionadas = self._filas_seleccionadas()
        if not seleccionadas:
            QMessageBox.information(
                self, "Gestión manual", "Seleccione al menos una factura.")
            return
        claves = set()
        for fila in seleccionadas:
            f = self._leer_fila(fila)
            claves.add((f.origen_imagen, f.num_factura, f.fecha, f.nif))
        candidatas = [self._leer_fila(i) for i in range(self.tabla.rowCount())
                      if (self.filas[i]["factura"].origen_imagen,
                          self.filas[i]["factura"].num_factura,
                          self.filas[i]["factura"].fecha,
                          self.filas[i]["factura"].nif) in claves]
        quitar_marca = all(f.tratamiento_manual == "Marcada por el usuario"
                           for f in candidatas)
        for f in candidatas:
            # Las exclusiones detectadas (suplido, bien de inversión o
            # sustituida) no se desactivan con un clic accidental.
            if quitar_marca:
                f.tratamiento_manual = None
            elif not f.tratamiento_manual:
                f.tratamiento_manual = "Marcada por el usuario"
            f.revision_confirmada = False
        self._revalidar_todo()
        self.lbl_estado.setText(
            f"{len(candidatas)} línea(s) "
            + ("devueltas al flujo automático." if quitar_marca
               else "apartadas para gestión manual."))

    def _eliminar_seleccion(self) -> None:
        filas = sorted({i.row() for i in self.tabla.selectionModel().selectedRows()},
                       reverse=True)
        if not filas:
            QMessageBox.information(
                self, "Eliminar facturas", "Seleccione una o varias filas completas.")
            return
        self._ultimo_borrado = []
        for fila in filas:
            registro = self.filas[fila]
            for fuente in registro.get("fuentes", [registro["factura"]]):
                fuente.eliminada = True
            self._ultimo_borrado.append({
                "registro": registro,
                "tipo": self._tipo_fila(fila),
                "cuenta": self.tabla.item(fila, C_CUENTA).text(),
                "gxx": self.tabla.item(fila, C_GXX).text(),
            })
            self.tabla.removeRow(fila)
            self.filas.pop(fila)
        self._ultimo_borrado.reverse()
        self.btn_deshacer_borrado.setEnabled(True)
        self.btn_deshacer_borrado.setVisible(True)
        self._revalidar_todo()
        self._aplicar_filtro()
        self.lbl_estado.setText(
            f"{len(filas)} línea(s) eliminada(s). Puede deshacer la operación.")

    def _deshacer_borrado(self) -> None:
        if not self._ultimo_borrado:
            return
        for borrada in self._ultimo_borrado:
            registro = borrada["registro"]
            for fuente in registro.get("fuentes", [registro["factura"]]):
                fuente.eliminada = False
            self._anadir_fila(
                registro["png"], registro["factura"], borrada["tipo"],
                borrada["cuenta"], borrada["gxx"], registro["aviso"],
                registro.get("bloque", ""), registro.get("fuentes"))
        cantidad = len(self._ultimo_borrado)
        self._ultimo_borrado = []
        self.btn_deshacer_borrado.setEnabled(False)
        self.btn_deshacer_borrado.setVisible(False)
        self._revalidar_todo()
        self._aplicar_filtro()
        self.lbl_estado.setText(f"{cantidad} línea(s) restaurada(s).")

    def _abrir_ficha(self, fila, columna):
        """Al pulsar el semáforo se abre la ficha con lo que le pasa a la fila.

        En el globo de ayuda se leia mal y desaparecia al mover el raton; asi
        se queda abierta, se puede leer con calma y se puede copiar.
        """
        if columna != C_ESTADO or fila >= len(self.filas):
            return
        registro = self.filas[fila]
        mensajes = registro.get("mensajes") or []
        if registro.get("estado", OK) == OK or not mensajes:
            return          # una fila correcta no tiene nada que contar
        f = registro["factura"]
        ficha = FichaIncidencias(
            registro["estado"], mensajes, self,
            referencia=f"Línea {fila + 1} · {f.num_factura or 'sin nº'} · "
                       f"{f.nombre or 'sin nombre'}")
        ficha.mostrar_junto_a(self.tabla.viewport(),
                              self.tabla.visualItemRect(
                                  self.tabla.item(fila, C_ESTADO)))

    def _revalidar_fila(self, r):
        if r < 0 or r >= len(self.filas):
            return
        f = self._leer_fila(r)
        res = validar(f)
        estado = res.estado
        msgs = list(res.mensajes)
        if self.filas[r]["aviso"]:
            msgs.append(self.filas[r]["aviso"])
            if estado == OK:
                estado = REVISAR
        aviso_tipo = self._aviso_tipo(r)
        if aviso_tipo:
            msgs.append(aviso_tipo)
            if estado == OK:
                estado = REVISAR
        if r in self._duplicados:
            # Rojo, no ambar: importar dos veces la misma factura la paga dos
            # veces. Que obligue a decidir, no que se quede en "ya lo miraré".
            msgs.append(f"FACTURA DUPLICADA: es la misma que la línea "
                        f"{self._duplicados[r] + 1} del lote (mismo nº, NIF, "
                        f"base y tipo de IVA). Bórrala o quedará registrada dos veces.")
            estado = ERROR
        confirmada = (estado == REVISAR and f.revision_confirmada
                      and not f.tratamiento_manual)
        if confirmada:
            msgs.append("Revisada y confirmada manualmente")
        self.filas[r]["estado"] = estado
        self.filas[r]["mensajes"] = msgs
        celda = self.tabla.item(r, C_ESTADO)
        self.tabla.blockSignals(True)
        celda.setText(ICONO_MANUAL if f.tratamiento_manual else
                      ICONO_REVISADO if confirmada else ICONO_ESTADO[estado])
        celda.setBackground(COLOR_MANUAL if f.tratamiento_manual else
                            COLOR_REVISADO if confirmada else COLOR_ESTADO[estado])
        celda.setForeground(QColor("white"))
        celda.setToolTip("\n".join(msgs) if msgs else "Todo correcto")
        self.tabla.blockSignals(False)
        self._resumen()

    def _aviso_tipo(self, r) -> str:
        """Comprueba por dos vias que la fila esta bien clasificada.

        Gasto o ingreso se decide por el NIF del cliente, que es lo fiable,
        pero si el NIF viene mal leido la factura se va al lado contrario sin
        que nadie se entere. Se contrasta con lo que dijo el usuario al
        escanear el taco y con lo que hace el resto de su bloque.
        """
        if r >= len(self.filas):
            return ""
        tipo = self._tipo_fila(r)
        bloque = self.filas[r]["bloque"]
        declarado = next((b.get("tipo_declarado", "") for b in self._bloques
                          if b["nombre"] == bloque), "")
        esperado = {"gastos": "gasto", "ingresos": "venta"}.get(declarado)
        if esperado and tipo != esperado:
            return (f"Dijo que este taco era de "
                    f"{'GASTOS' if esperado == 'gasto' else 'INGRESOS'} y esta "
                    f"factura sale como {'gasto' if tipo == 'gasto' else 'ingreso'}: "
                    f"compruebe si está bien")
        # Sin taco declarado: la que se sale de lo que hace todo su bloque.
        tipos = [self._tipo_fila(i) for i in range(len(self.filas))
                 if self.filas[i]["bloque"] == bloque]
        if len(tipos) >= 5 and tipos.count(tipo) == 1:
            return ("Es la única factura de su bloque que sale como "
                    f"{'gasto' if tipo == 'gasto' else 'ingreso'}: compruébela")
        return ""

    def _revalidar_todo(self):
        self._duplicados = encontrar_duplicados(
            [self._leer_fila(r) for r in range(self.tabla.rowCount())])
        for r in range(self.tabla.rowCount()):
            self._revalidar_fila(r)
        # El resumen se rehace SIEMPRE, tambien con la tabla vacia: si no, al
        # vaciar el lote se quedaban abajo los totales del lote anterior y
        # parecia que no se habia borrado nada.
        self._resumen()
        self._pintar_alerta()
        if hasattr(self, "combo_filtro_estado"):
            self._aplicar_filtro()

    def _pintar_alerta(self):
        """Banner rojo arriba con las duplicadas y las sustituidas: las dos
        acaban registrando dos veces el mismo gasto si se cuelan."""
        avisos = []
        for r, original in sorted(self._duplicados.items()):
            f = self.filas[r]["factura"]
            avisos.append(f"Línea {r + 1}: factura {f.num_factura or '?'} de "
                          f"{f.nombre or '?'} — repetida de la línea {original + 1}.")
        # Una hoja que se quedo pegada en el alimentador no da ningun error:
        # simplemente esa factura no esta. El salto de numeracion la delata.
        avisos += huecos_de_numeracion(
            [d["factura"] for d in self.filas])
        sustituidas = [r for r in range(len(self.filas))
                       if "SUSTITUIDA" in (self.filas[r]["aviso"] or "")]
        for r in sustituidas:
            f = self.filas[r]["factura"]
            avisos.append(f"Línea {r + 1}: factura {f.num_factura or '?'} de "
                          f"{f.nombre or '?'} — sustituida por otra del lote.")
        if not avisos:
            self.alerta.setVisible(False)
            return
        n = len(avisos)
        self.lbl_alerta_titulo.setText(
            f"⚠  ATENCIÓN: {n} cosa{'s' if n > 1 else ''} que revisar "
            f"antes de exportar")
        self.lbl_alerta_texto.setText(
            "\n".join(avisos[:6])
            + (f"\n… y {n - 6} más." if n > 6 else "")
            + "\n\nUna factura repetida se registra dos veces; una que falta "
              "no se registra nunca.")
        self.alerta.setVisible(True)

    def _resumen(self):
        estados = []
        for r in range(self.tabla.rowCount()):
            f = self.filas[r]["factura"]
            e = validar(f).estado
            if self.filas[r]["aviso"] and e == OK:
                e = REVISAR
            if r in self._duplicados:
                e = ERROR
            estados.append(e)
        n_g = sum(1 for r in range(self.tabla.rowCount()) if self._tipo_fila(r) == "gasto")
        self.lbl_estado.setText(
            "Lote vacío. Cargue o escanee facturas para empezar." if not estados else
            f"{len(estados)} líneas  ·  Gastos: {n_g}  ·  Ventas: {len(estados) - n_g}  ·  "
            f"🟢 {estados.count(OK)}  🟡 {estados.count(REVISAR)}  🔴 {estados.count(ERROR)}")
        self._pintar_resumen()

    def _pintar_resumen(self):
        """Listado para cuadrar: una linea por bloque escaneado y tipo, mas el
        total general. Suma TODO lo cargado (el programa vale igual para un
        trimestre que para un requerimiento de varios años, no se filtra por
        fechas). Es el punto de control contra el taco de papel."""
        filas_por_tipo = {"gasto": [], "venta": []}
        for r in range(self.tabla.rowCount()):
            filas_por_tipo[self._tipo_fila(r)].append(
                (self.filas[r]["bloque"] or "—", self.filas[r]["factura"]))
        # En recargo el gasto no tiene desglose de IVA: solo el total factura.
        recargo = self._por_el_total()
        self.lbl_resumen_titulo.setText(
            "Comprobación de totales por bloque"
            + ("  ·  cliente en recargo de equivalencia" if recargo else ""))

        lineas = []   # (bloque, tipo, Totales, es_total)
        for tipo, etiqueta in (("gasto", "Gastos"), ("venta", "Ingresos")):
            pares = filas_por_tipo[tipo]
            if not pares:
                continue
            por_bloque = resumir_por_bloque(pares)
            for nombre, t in por_bloque.items():
                lineas.append((nombre, etiqueta, t, False))
            if len(por_bloque) > 1:
                lineas.append(("TODOS LOS BLOQUES", etiqueta,
                               resumir([f for _, f in pares]), True))
        self._volcar_resumen(lineas, recargo)

    def _volcar_resumen(self, lineas, recargo):
        # Un IVA por columna, con su porcentaje en la cabecera: asi se leen los
        # totales de cada tipo de un vistazo, en vez de todos en una celda.
        tipos_iva = sorted({tipo for _, _, t, _ in lineas
                            for tipo in t.iva_por_tipo})
        self._tipos_iva_resumen = tipos_iva
        cabeceras = _cabeceras_resumen(tipos_iva)
        self.tabla_resumen.setColumnCount(len(cabeceras))
        self.tabla_resumen.setHorizontalHeaderLabels(
            [cabecera.upper() for cabecera in cabeceras])
        self.tabla_resumen.setRowCount(len(lineas))
        for r, (bloque, tipo, t, es_total) in enumerate(lineas):
            # En recargo el gasto va por el total factura: el desglose de IVA
            # no existe y ponerlo a 0,00 despistaria.
            solo_total = recargo and tipo == "Gastos"
            cuotas = ["" if solo_total or p not in t.iva_por_tipo
                      else eur(t.iva_por_tipo[p]) for p in tipos_iva]
            if not tipos_iva:
                cuotas = ["" if solo_total else eur(t.iva)]
            valores = [
                bloque, tipo, str(t.lineas),
                "" if solo_total else eur(t.base),
                *cuotas,
                eur(t.requiv) if t.tiene_requiv and not solo_total else "",
                f"−{eur(t.irpf)}" if t.tiene_irpf else "",
                eur(t.suplidos) if t.tiene_suplidos and not solo_total else "",
                eur(t.total),
            ]
            for c, texto in enumerate(valores):
                item = QTableWidgetItem(texto)
                if c >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if es_total:
                    fuente = item.font()
                    fuente.setBold(True)
                    item.setFont(fuente)
                self.tabla_resumen.setItem(r, c, item)

    def _copiar_resumen(self):
        """El resumen al portapapeles, para pegarlo al comprobar los totales."""
        filas = ["\t".join(
            _cabeceras_resumen(getattr(self, "_tipos_iva_resumen", [])))]
        for r in range(self.tabla_resumen.rowCount()):
            filas.append("\t".join(
                (self.tabla_resumen.item(r, c).text() if self.tabla_resumen.item(r, c)
                 else "")
                for c in range(self.tabla_resumen.columnCount())))
        QApplication.clipboard().setText("\n".join(filas))
        self.lbl_estado.setText("Resumen copiado al portapapeles.")

    # ---------- miniatura ----------
    def _limpiar_visor(self) -> None:
        self._pixmap_documento = QPixmap()
        self._zoom_visor = 1.0
        self.lbl_origen.setText("Arrastre aquí un PDF o imágenes para comenzar")
        self.lbl_pagina.clear()
        self.lbl_img.clear()
        self.lbl_img.setMinimumSize(330, 430)
        self.lbl_img.setText(
            "Suelte aquí las facturas\no use «Abrir PDF o imágenes»")

    def _pintar_pixmap_visor(self) -> None:
        if self._pixmap_documento.isNull():
            return
        viewport = self.visor_scroll.viewport().size()
        ancho = max(330, int(viewport.width() * self._zoom_visor))
        alto = max(430, int(viewport.height() * self._zoom_visor))
        self.lbl_img.setMinimumSize(ancho, alto)
        self.lbl_img.setPixmap(self._pixmap_documento.scaled(
            ancho, alto, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _cambiar_zoom_visor(self, incremento: float) -> None:
        if self._pixmap_documento.isNull():
            return
        self._zoom_visor = min(2.5, max(0.7, self._zoom_visor + incremento))
        self._pintar_pixmap_visor()

    def _mostrar_miniatura(self):
        r = self.tabla.currentRow()
        if r < 0 or r >= len(self.filas):
            self._limpiar_visor()
            return
        png = self.filas[r]["png"]
        factura = self.filas[r]["factura"]
        origen = os.path.basename(factura.origen_imagen or "")
        self.lbl_origen.setText(origen or "Documento cargado")
        self.lbl_pagina.setText("1 / 1")
        pix = QPixmap()
        pix.loadFromData(png)
        if not pix.isNull():
            self._pixmap_documento = pix
            self._pintar_pixmap_visor()
        else:
            self._pixmap_documento = QPixmap()

    def _abrir_vista_previa(self):
        """Muestra la página seleccionada grande y con barras de desplazamiento."""
        if self._pixmap_documento.isNull():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(self.lbl_origen.text() or "Documento original")
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)
        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(False)
        imagen = QLabel()
        imagen.setAlignment(Qt.AlignCenter)
        imagen.setPixmap(self._pixmap_documento)
        imagen.resize(self._pixmap_documento.size())
        scroll.setWidget(imagen)
        layout.addWidget(scroll, 1)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(dlg.accept)
        layout.addWidget(cerrar, 0, Qt.AlignRight)
        pantalla = QApplication.primaryScreen().availableGeometry()
        dlg.resize(int(pantalla.width() * 0.9), int(pantalla.height() * 0.9))
        dlg.exec()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        ancho = event.size().width()
        self._actualizar_barra_responsiva(ancho)
        self._distribuir_herramientas(ancho)
        if self.tabla.currentRow() >= 0:
            self._mostrar_miniatura()

    # ---------- exportar ----------
    def _para_aplifisa(self, facturas):
        """Traduce el concepto al texto que Aplifisa tiene parametrizado.

        Con el texto, el apunte entra con su cuenta Y su subclave puestas, que
        es lo unico que evita tener que elegir el GXX a mano en cada proveedor
        nuevo. Si no esta configurado, se exporta el codigo de siempre.
        """
        if not ajustes.leer("concepto_texto", False):
            return facturas
        traducidas = []
        for f in facturas:
            texto = texto_para(f.concepto, f.subclave)
            traducidas.append(replace(f, concepto=texto) if texto else f)
        return traducidas

    def _clasificar_exportacion(self):
        """Separa lo exportable, lo manual y lo que todavía bloquea el lote."""
        por_tipo = {"gasto": [], "venta": []}
        excluidas = []
        errores = []
        pendientes_revision = []
        for fila in range(self.tabla.rowCount()):
            f = self._leer_fila(fila)
            registro = self.filas[fila]
            if fila in self._duplicados:
                excluidas.append((fila, "duplicada"))
            elif f.tratamiento_manual:
                excluidas.append((fila, f.tratamiento_manual))
            elif registro.get("estado") == ERROR:
                errores.append(fila)
            elif registro.get("estado") == REVISAR and not f.revision_confirmada:
                pendientes_revision.append(fila)
            else:
                por_tipo[self._tipo_fila(fila)].append(f)
        return por_tipo, excluidas, errores, pendientes_revision

    def _nombre_cliente_archivo(self) -> str:
        nombre = (getattr(self, "_cliente_nombre", "") or
                  next((b.get("cliente", "") for b in self._bloques
                        if b.get("cliente")), "") or "Cliente")
        return escaner.sanear(nombre)

    @staticmethod
    def _ejercicio_exportacion(facturas) -> int:
        """Ejercicio predominante del lote para ordenar su documentación."""
        ejercicios = []
        for factura in facturas:
            fecha = fecha_de(factura.fecha)
            if fecha:
                ejercicios.append(fecha.year)
        return (Counter(ejercicios).most_common(1)[0][0]
                if ejercicios else date.today().year)

    def _exportar_todo(self):
        """Genera en una sola operación los Excel de gastos e ingresos."""
        self._revalidar_todo()
        clientes = {b.get("nif") or b.get("cliente") for b in self._bloques
                    if b.get("nif") or b.get("cliente")}
        if len(clientes) > 1:
            QMessageBox.critical(
                self, "Hay varios clientes",
                "No se puede crear un Excel con bloques de clientes distintos. "
                "Quite el bloque incorrecto o pulse «Vaciar todo» para empezar "
                "con otro cliente.")
            return
        por_tipo, excluidas, errores, pendientes_revision = \
            self._clasificar_exportacion()

        if errores or pendientes_revision:
            partes = []
            if errores:
                partes.append(f"{len(errores)} línea(s) roja(s) con errores")
            if pendientes_revision:
                partes.append(
                    f"{len(pendientes_revision)} línea(s) ámbar sin confirmar")
            QMessageBox.warning(
                self, "Revisión pendiente",
                "No se ha exportado nada. Corrija los errores y marque como "
                "revisados los avisos comprobados:\n\n  · "
                + "\n  · ".join(partes))
            self._siguiente_incidencia()
            return
        if not any(por_tipo.values()):
            QMessageBox.information(
                self, "Sin facturas rutinarias",
                "No hay facturas para exportar automáticamente. "
                f"Se han apartado {len(excluidas)} línea(s) para gestión manual.")
            return

        # El orden manda: Aplifisa renumera las facturas recibidas segun entran,
        # asi que este orden es el que tendran en el registro.
        dialogo_orden = DialogoOrden(self)
        if dialogo_orden.exec() != QDialog.Accepted:
            return
        dialogo_orden.recordar()
        orden = dialogo_orden.orden()
        for tipo in por_tipo:
            por_tipo[tipo] = ordenar_para_exportar(por_tipo[tipo], orden)
        problemas_export = []      # lo que no cuadre entre archivo y pantalla
        resumen_archivos = []      # (ruta, lineas, totales) para enseñarlo
        tipos_exportados = []      # los parciales se borran solo tras verificar
        cliente_archivo = self._nombre_cliente_archivo()
        for tipo, xml in (
            ("gasto", "gastos.xml"),
            ("venta", "ingresos.xml"),
        ):
            if not por_tipo[tipo]:
                continue
            ejercicio = self._ejercicio_exportacion(por_tipo[tipo])
            ruta = archivo.ruta_excel_consolidado(
                cliente_archivo, ejercicio, tipo)
            nombre = os.path.basename(ruta)
            config = leer_config(ruta_config(xml))
            listas = self._para_aplifisa(por_tipo[tipo])
            exportar_excel(listas, config, ruta)
            # DOBLE CONTRASTE: se vuelve a leer el archivo escrito y se compara
            # con lo que hay en pantalla. Es el ultimo paso antes de que los
            # apuntes entren en la contabilidad, y era el unico sin comprobar.
            fallos = verificar_excel(listas, config, ruta)
            problemas_export.extend(f"{nombre}: {p}" for p in fallos[:5])
            resumen_archivos.append(
                (ruta, len(listas), totales_del_excel(config, ruta)))
            tipos_exportados.append(tipo)

        if problemas_export:
            QMessageBox.critical(
                self, "El archivo NO coincide con la pantalla",
                "Al volver a leer lo escrito, esto no cuadra:\n\n  · "
                + "\n  · ".join(problemas_export)
                + "\n\nNO importe estos archivos en Aplifisa sin revisarlos.")
            return

        temporales_eliminados = sum(
            len(archivo.eliminar_excel_temporales(cliente_archivo, tipo))
            for tipo in tipos_exportados
        )
        detalle = "\n".join(
            f"  · {os.path.basename(ruta)}: {lineas} línea(s), "
            f"base {eur(t['base_iva'])}, "
            f"IVA {eur(t['cuota_iva'])}"
            for ruta, lineas, t in resumen_archivos)
        carpetas = "\n".join(
            f"  · {carpeta}" for carpeta in sorted({
                os.path.dirname(ruta) for ruta, _lineas, _totales in resumen_archivos
            }))
        QMessageBox.information(
            self, "Exportación terminada",
            f"Excel consolidados preparados para Aplifisa:\n\n{detalle}\n\n"
            f"Guardados en el Escritorio:\n{carpetas}\n\n"
            + ("En el orden del PDF escaneado.\n" if orden == ORDEN_PDF
               else "Por fecha de factura.\n")
            + (f"Apartadas de la exportación automática: {len(excluidas)} línea(s).\n"
               if excluidas else "")
            + (f"Eliminados {temporales_eliminados} Excel temporales de partes.\n"
               if temporales_eliminados else "")
            + "Comprobado: lo escrito en los archivos coincide con lo que ve "
              "en pantalla, línea por línea. No se han creado Excel parciales.")


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
