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
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QProgressDialog, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel import (
    __version__, ajustes, archivo, costes, escaner, pendientes, updater,
)
from facturas_excel.claves import guardar_api_key, leer_api_key
from facturas_excel.dialogo_calidad import DialogoCalidad
from facturas_excel.dialogo_cliente import DialogoCliente
from facturas_excel.dialogo_escaneo import DialogoEscaneo
from facturas_excel.dialogo_escaneos import DialogoEscaneos
from facturas_excel.dialogo_pendientes import DialogoPendientes
from facturas_excel.clientes import (
    en_recargo_equivalencia, guardar_recargo_equivalencia, marcar_cliente,
    nombres_conocidos, recordar_nombre,
)
from facturas_excel.conceptos import SUBCLAVES_628
from facturas_excel.config_columnas import leer_config
from facturas_excel.estilo import aplicar_tema
from facturas_excel.exportar import exportar_excel
from facturas_excel.extraccion import Extractor, SinCredito
from facturas_excel.modelo import Factura
from facturas_excel.pdf import cargar_imagenes
from facturas_excel.procesar import (
    a_total_factura, analizar_cliente, clave_proveedor, detectar_cliente,
    normaliza_nif, preparar_lote, recordar_nif,
)
from facturas_excel.resumen import eur, resumir, resumir_por_bloque
from facturas_excel.rutas import ruta_config
from facturas_excel.validacion import (
    ERROR, OK, REVISAR, encontrar_duplicados, huecos_de_numeracion,
    validar, validar_nif,
)

ESCRITORIO = os.path.join(os.path.expanduser("~"), "Desktop")

COLOR_ESTADO = {OK: QColor("#2e7d32"), REVISAR: QColor("#f9a825"), ERROR: QColor("#c62828")}
ICONO_ESTADO = {OK: "OK", REVISAR: "!", ERROR: "X"}

HILOS = 6  # facturas procesadas en paralelo (con key de pago se puede subir)
EXT_FACTURA = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

COLS = ["Estado", "Tipo", "Cuenta", "GXX", "Fecha", "Nº Factura", "Nombre",
        "NIF", "Base", "% IVA", "Cuota", "Total", "Bloque"]
C_ESTADO, C_TIPO, C_CUENTA, C_GXX, C_FECHA, C_NUM, C_NOMBRE, C_NIF, \
C_BASE, C_PCT, C_CUOTA, C_TOTAL, C_BLOQUE = range(len(COLS))

# Columnas del resumen por bloque (punto de control antes de exportar).
COLS_RESUMEN = ["Bloque", "Tipo", "Líneas", "Base", "IVA", "Recargo", "IRPF",
                "Total factura"]
TODOS_LOS_BLOQUES = "Todos los bloques"


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
    def __init__(self, comprobar_updates: bool = True):
        super().__init__()
        self.setWindowTitle(f"Facturas a Aplifisa — v{__version__}")
        self.setWindowIcon(QIcon(ruta_recurso("app.ico")))
        self.resize(1420, 820)
        self.setMinimumSize(1080, 680)
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
        self._escaneo_sin_identificar = False
        self._comprobar_updates = comprobar_updates
        self._crear_menu()

        self._crear_interfaz()
        self._crear_atajos()
        self._pintar_gasto()
        if self._comprobar_updates:
            QTimer.singleShot(
                1500, lambda: self._comprobar_actualizaciones(silencioso=True))

    def _crear_interfaz(self):
        central = QWidget()
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # Sin banner de cabecera: la marca y la version ya salen en el titulo de
        # la ventana, y el espacio se aprovecha para la tabla.
        cuerpo = QVBoxLayout()
        cuerpo.setContentsMargins(18, 14, 18, 12)
        cuerpo.setSpacing(12)

        acciones = QFrame()
        acciones.setObjectName("tarjeta")
        la = QHBoxLayout(acciones)
        la.setContentsMargins(16, 12, 16, 12)
        self.btn_escanear = QPushButton("Escanear facturas")
        self.btn_escanear.setObjectName("primario")
        self.btn_escanear.setMinimumHeight(40)
        self.btn_escanear.setToolTip(
            "Escanea el taco del alimentador, guarda el PDF con el nombre del "
            "cliente y lo mete en el lote.  (Ctrl+E)")
        self.btn_escanear.clicked.connect(self._escanear)
        self.btn_cargar = QPushButton("Abrir PDF o imágenes")
        self.btn_cargar.setMinimumHeight(40)
        self.btn_cargar.setToolTip("Abrir un PDF ya escaneado o fotos.  (Ctrl+O)")
        self.btn_cargar.clicked.connect(self._cargar)
        la.addWidget(self.btn_escanear)
        la.addWidget(self.btn_cargar)
        la.addSpacing(12)
        bloque_cliente = QVBoxLayout()
        etiqueta = QLabel("LOTE ACTUAL")
        etiqueta.setObjectName("textoSuave")
        self.lbl_cliente = QLabel("Cliente pendiente de detectar")
        self.lbl_cliente.setObjectName("cliente")
        bloque_cliente.addWidget(etiqueta)
        bloque_cliente.addWidget(self.lbl_cliente)
        self.btn_cliente = QPushButton("Cambiar cliente…")
        self.btn_cliente.setToolTip(
            "Quién es SU cliente en estas facturas. Si se detectó mal, se "
            "cambia aquí y el lote se rehace sin volver a pasar por Gemini.")
        self.btn_cliente.setEnabled(False)
        self.btn_cliente.clicked.connect(self._cambiar_cliente)
        bloque_cliente.addWidget(self.btn_cliente)
        self.chk_recargo = QCheckBox("En recargo de equivalencia (gastos por el total)")
        self.chk_recargo.setToolTip(
            "El cliente no deduce IVA: cada gasto se registra por el total de la\n"
            "factura (base + IVA + recargo), sin desglose. Se recuerda por NIF.")
        self.chk_recargo.setEnabled(False)
        self.chk_recargo.toggled.connect(self._on_recargo)
        bloque_cliente.addWidget(self.chk_recargo)
        la.addLayout(bloque_cliente, 1)

        self.btn_gastos = QPushButton("Exportar a Aplifisa…")
        self.btn_gastos.setObjectName("exito")
        self.btn_gastos.setEnabled(False)
        self.btn_gastos.clicked.connect(self._exportar_todo)
        self.btn_ventas = self.btn_gastos
        la.addWidget(self.btn_gastos)
        cuerpo.addWidget(acciones)

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
        titulo_tabla = QLabel("Datos extraídos")
        titulo_tabla.setObjectName("tituloSeccion")
        ayuda_tabla = QLabel(
            "El programa decide Gasto o Ingreso. Revise únicamente las filas ámbar o rojas.")
        ayuda_tabla.setObjectName("textoSuave")
        lt.addWidget(titulo_tabla)
        lt.addWidget(ayuda_tabla)

        herramientas = QHBoxLayout()
        herramientas.setSpacing(8)
        herramientas.addWidget(QLabel("Mostrar:"))
        self.combo_filtro_estado = ComboSinRueda()
        self.combo_filtro_estado.addItems(
            ["Todas", "Solo por revisar", "Solo con errores", "Solo correctas"])
        self.combo_filtro_estado.currentIndexChanged.connect(self._aplicar_filtro)
        herramientas.addWidget(self.combo_filtro_estado)
        self.combo_filtro_bloque = ComboSinRueda()
        self.combo_filtro_bloque.addItem(TODOS_LOS_BLOQUES)
        self.combo_filtro_bloque.setToolTip(
            "Cada escaneo o PDF cargado es un bloque. Puede revisarlos de uno "
            "en uno y exportarlos todos juntos.")
        self.combo_filtro_bloque.currentIndexChanged.connect(self._aplicar_filtro)
        herramientas.addWidget(self.combo_filtro_bloque)
        btn_siguiente = QPushButton("Siguiente incidencia")
        btn_siguiente.clicked.connect(self._siguiente_incidencia)
        herramientas.addWidget(btn_siguiente)
        herramientas.addStretch(1)
        self.btn_quitar_bloque = QPushButton("Quitar este bloque")
        self.btn_quitar_bloque.setObjectName("peligro")
        self.btn_quitar_bloque.setToolTip(
            "Quita del lote el bloque elegido en el desplegable (p.ej. si se ha "
            "cargado un PDF que no tocaba).")
        self.btn_quitar_bloque.clicked.connect(self._quitar_bloque)
        herramientas.addWidget(self.btn_quitar_bloque)
        self.btn_vaciar = QPushButton("Vaciar todo")
        self.btn_vaciar.setObjectName("peligro")
        self.btn_vaciar.clicked.connect(self._vaciar_todo)
        herramientas.addWidget(self.btn_vaciar)
        self.btn_deshacer_borrado = QPushButton("Deshacer eliminación")
        self.btn_deshacer_borrado.setEnabled(False)
        self.btn_deshacer_borrado.clicked.connect(self._deshacer_borrado)
        herramientas.addWidget(self.btn_deshacer_borrado)
        btn_eliminar = QPushButton("Eliminar selección")
        btn_eliminar.setObjectName("peligro")
        btn_eliminar.clicked.connect(self._eliminar_seleccion)
        herramientas.addWidget(btn_eliminar)
        lt.addLayout(herramientas)
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

        resumen_card = QFrame()
        resumen_card.setObjectName("tarjeta")
        lr = QVBoxLayout(resumen_card)
        lr.setContentsMargins(12, 10, 12, 10)
        lr.setSpacing(2)
        fila_titulo = QHBoxLayout()
        self.lbl_resumen_titulo = QLabel("Comprobación de totales por bloque")
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
        self.tabla_resumen = QTableWidget(0, len(COLS_RESUMEN))
        self.tabla_resumen.setHorizontalHeaderLabels(COLS_RESUMEN)
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

        ver = self.menuBar().addMenu("Ver")
        self.accion_resumen = ver.addAction("Comprobación de totales por bloque")
        self.accion_resumen.setCheckable(True)
        self.accion_resumen.setChecked(bool(ajustes.leer("ver_resumen", True)))
        self.accion_resumen.toggled.connect(self._ver_resumen)

        config = self.menuBar().addMenu("Configuración")
        config.addAction("API key de Gemini…", self._configurar_key)
        config.addAction("Tope de gasto al mes…", self._configurar_tope)
        config.addAction("Carpeta donde se guardan los escaneos…",
                         self._configurar_carpeta_escaneos)
        config.addAction("Calidad de lectura y coste…", self._configurar_calidad)

        menu = self.menuBar().addMenu("Ayuda")
        menu.addAction("Buscar actualizaciones",
                       lambda: self._comprobar_actualizaciones(silencioso=False))
        menu.addAction("Diagnóstico y sugerencias…",
                       lambda: self._mostrar_pendientes(al_arrancar=False))
        menu.addAction("Acerca de", self._acerca_de)

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

    def _ver_resumen(self, visible: bool):
        """El resumen es solo un punto de control: si estorba, se quita."""
        ajustes.guardar("ver_resumen", bool(visible))
        if hasattr(self, "resumen_card"):
            self.resumen_card.setVisible(bool(visible))
        if hasattr(self, "accion_resumen") and self.accion_resumen.isChecked() != visible:
            self.accion_resumen.setChecked(bool(visible))

    def _configurar_carpeta_escaneos(self):
        actual = ajustes.leer("carpeta_escaneos", escaner.carpeta_por_defecto())
        carpeta = QFileDialog.getExistingDirectory(
            self, "Carpeta donde guardar los PDF escaneados", actual)
        if carpeta:
            ajustes.guardar("carpeta_escaneos", carpeta)
            self.lbl_estado.setText(f"Los escaneos se guardarán en {carpeta}")

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
        self.procesar_rutas([ruta])

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
        self.lbl_estado.setText("No se pudo escanear.")
        QMessageBox.critical(self, "Error al escanear", mensaje)

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
        self.worker.gasto.connect(self._on_gasto)
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

    def _on_terminado(self, procesadas, nombre, nif, crudos=None):
        self.progreso.setVisible(False)
        self.btn_cargar.setEnabled(True)
        # Si el escaneo salió sin saber de quién era, ahora ya se sabe: el PDF
        # se muda solo a la carpeta del cliente antes de nombrar el bloque.
        self._recolocar_escaneo(nombre, procesadas)
        # Cada carga entra como un BLOQUE mas: asi se pueden juntar varios PDF
        # de escaner (25-30 hojas cada uno) en un unico Excel para Aplifisa.
        self._bloques.append({
            "nombre": self._nombre_bloque(),
            "procesadas": procesadas,
            # Lo leido por Gemini, tal cual: permite rehacer el lote con otro
            # cliente sin gastar otra lectura.
            "crudos": list(crudos or []),
            "cliente": nombre,
            "nif": nif,
        })
        self._avisar_si_otro_cliente(nombre, nif)
        # El nombre del cliente se guarda para proponerlo al escanear el
        # proximo taco suyo, sin tener que escribirlo otra vez.
        recordar_nombre(nif, nombre)
        self._cliente_nif, self._cliente_nombre = nif, nombre
        self._pintar_cliente()
        self.chk_recargo.blockSignals(True)
        self.chk_recargo.setEnabled(bool(nif))
        self.chk_recargo.setChecked(en_recargo_equivalencia(nif))
        self.chk_recargo.blockSignals(False)
        self._actualizar_combo_bloques()
        self._rellenar_tabla()
        self._revalidar_todo()
        hay_datos = self.tabla.rowCount() > 0
        self.btn_gastos.setEnabled(hay_datos)
        self.btn_ventas.setEnabled(hay_datos)
        self.btn_cliente.setEnabled(bool(self._bloques))
        if hay_datos:
            self.tabla.selectRow(0)
        # Un taco del mismo proveedor al mismo cliente deja las dos partes
        # empatadas: hay que preguntarlo o sale todo del reves.
        if self._analisis_del_lote().dudoso:
            self._cambiar_cliente(automatico=True)

    def _recolocar_escaneo(self, cliente, procesadas):
        """Muda el PDF recién escaneado a la carpeta de su cliente.

        Al escanear no hace falta decir de quién son las facturas: el programa
        lo averigua por el NIF que se repite y coloca el archivo despues. Si no
        lo averigua, el PDF se queda en «Sin identificar» y se puede colocar a
        mano desde «Escaneos guardados».
        """
        if not self._escaneo_sin_identificar or len(self._rutas_actuales) != 1:
            return
        ruta = self._rutas_actuales[0]
        if not cliente or not archivo.sin_identificar(ruta):
            return
        ventas = sum(1 for _, pr in procesadas if pr.tipo == "venta")
        tipo = "ingresos" if ventas > len(procesadas) / 2 else "gastos"
        nueva = archivo.mover_a_cliente(ruta, cliente, tipo)
        if nueva == ruta:
            return
        self._escaneo_sin_identificar = False
        self._rutas_actuales = [nueva]
        for _, pr in procesadas:     # que la miniatura siga apuntando al PDF
            pr.origen = nueva
            for f in pr.facturas:
                f.origen_imagen = nueva
        self.lbl_estado.setText(f"Escaneo guardado como {os.path.basename(nueva)}")

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
        self.chk_recargo.blockSignals(True)
        self.chk_recargo.setEnabled(bool(nif))
        self.chk_recargo.setChecked(en_recargo_equivalencia(nif))
        self.chk_recargo.blockSignals(False)
        self._rellenar_tabla()
        self._revalidar_todo()
        self.lbl_estado.setText(f"Lote rehecho con {nombre or nif} como cliente.")

    def _nombre_bloque(self) -> str:
        """Nombre corto del bloque: el del PDF cargado, sin repetirse."""
        rutas = self._rutas_actuales
        if not rutas:
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
        self.combo_filtro_bloque.setCurrentIndex(0)
        self._actualizar_combo_bloques()
        self._rellenar_tabla()
        self._revalidar_todo()
        hay_datos = self.tabla.rowCount() > 0
        self.btn_gastos.setEnabled(hay_datos)
        self.lbl_estado.setText(f"Bloque «{nombre}» quitado del lote.")

    def _vaciar_todo(self):
        if not self._bloques:
            return
        if QMessageBox.question(
                self, "Vaciar todo",
                f"¿Vaciar el lote entero ({len(self._bloques)} bloque(s), "
                f"{self.tabla.rowCount()} línea(s)) y empezar de cero?\n\n"
                "Lo leído se perderá y habría que volver a pasarlo por Gemini.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._bloques = []
        self._ultimo_borrado = []
        self._cliente_nif = self._cliente_nombre = ""
        self.btn_deshacer_borrado.setEnabled(False)
        self.chk_recargo.blockSignals(True)
        self.chk_recargo.setChecked(False)
        self.chk_recargo.setEnabled(False)
        self.chk_recargo.blockSignals(False)
        self._actualizar_combo_bloques()
        self._rellenar_tabla()
        self._revalidar_todo()
        self.btn_gastos.setEnabled(False)
        self.lbl_cliente.setText("Cliente pendiente de detectar")
        self.lbl_estado.setText("Lote vacío. Cargue o escanee facturas para empezar.")

    def _rellenar_tabla(self):
        recargo = self.chk_recargo.isChecked()
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(0)
        self.filas = []
        for bloque in self._bloques:
            for png, pr in bloque["procesadas"]:
                vista = a_total_factura(pr) if recargo else pr
                for f in vista.facturas:
                    self._anadir_fila(png, f, vista.tipo, vista.cuenta,
                                      vista.gxx, vista.aviso, bloque["nombre"])
        self.tabla.blockSignals(False)

    def _on_recargo(self, activo):
        """Marcar el recargo rehace la tabla: cambia como se registra cada gasto."""
        guardar_recargo_equivalencia(getattr(self, "_cliente_nif", ""), activo,
                                     getattr(self, "_cliente_nombre", ""))
        self._rellenar_tabla()
        self._revalidar_todo()

    def _anadir_fila(self, png, f: Factura, tipo, cuenta, gxx, aviso, bloque=""):
        senales_bloqueadas = self.tabla.signalsBlocked()
        self.tabla.blockSignals(True)
        r = self.tabla.rowCount()
        self.tabla.insertRow(r)
        self.filas.append({"png": png, "factura": f, "aviso": aviso,
                           "bloque": bloque})

        est = QTableWidgetItem("")
        est.setFlags(Qt.ItemIsEnabled)
        est.setTextAlignment(Qt.AlignCenter)
        self.tabla.setItem(r, C_ESTADO, est)

        combo = ComboSinRueda()
        combo.addItem("Gasto", "gasto")
        combo.addItem("Ingreso", "venta")
        combo.setCurrentIndex(max(0, combo.findData(tipo)))
        combo.setToolTip(
            "Clasificación dudosa: compruebe si corresponde a Gasto o Ingreso."
            if aviso and ("dudoso" in aviso.lower() or "confirma" in aviso.lower())
            else "Clasificación automática según el NIF y el papel del cliente en la factura.")
        combo.currentIndexChanged.connect(
            lambda _i, control=combo: self._revalidar_fila(
                self._fila_del_control_tipo(control)))
        self.tabla.setCellWidget(r, C_TIPO, combo)

        valores = {
            C_CUENTA: cuenta, C_GXX: gxx or "", C_FECHA: f.fecha, C_NUM: f.num_factura,
            C_NOMBRE: f.nombre, C_NIF: f.nif, C_BASE: fmt(f.base_iva),
            C_PCT: fmt(f.pct_iva), C_CUOTA: fmt(f.cuota_iva), C_TOTAL: fmt(f.total_impreso),
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
            if col == C_BLOQUE:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setToolTip("Escaneo o PDF del que salió esta factura.")
            self.tabla.setItem(r, col, item)
        self.tabla.setRowHeight(r, 34)
        self.tabla.blockSignals(senales_bloqueadas)

    # ---------- edicion / validacion ----------
    def _on_celda(self, item):
        aviso = self._nif_escrito_a_mano(item.row()) \
            if item.column() == C_NIF else ""
        self._revalidar_todo()
        if aviso:
            self.lbl_estado.setText(aviso)  # despues: _resumen pisa la barra

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
                or (opcion == 3 and estado == ICONO_ESTADO[OK])
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
            if self._estado_fila(fila) != ICONO_ESTADO[OK]:
                self.combo_filtro_estado.setCurrentIndex(0)
                self.tabla.selectRow(fila)
                self.tabla.scrollToItem(self.tabla.item(fila, C_ESTADO))
                return
        self.lbl_estado.setText("Todo el lote está correcto y listo para exportar.")

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
        self._revalidar_todo()
        self._aplicar_filtro()
        self.lbl_estado.setText(
            f"{len(filas)} línea(s) eliminada(s). Puede deshacer la operación.")

    def _deshacer_borrado(self) -> None:
        if not self._ultimo_borrado:
            return
        for borrada in self._ultimo_borrado:
            registro = borrada["registro"]
            self._anadir_fila(
                registro["png"], registro["factura"], borrada["tipo"],
                borrada["cuenta"], borrada["gxx"], registro["aviso"],
                registro.get("bloque", ""))
        cantidad = len(self._ultimo_borrado)
        self._ultimo_borrado = []
        self.btn_deshacer_borrado.setEnabled(False)
        self._revalidar_todo()
        self._aplicar_filtro()
        self.lbl_estado.setText(f"{cantidad} línea(s) restaurada(s).")

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
        if r in self._duplicados:
            # Rojo, no ambar: importar dos veces la misma factura la paga dos
            # veces. Que obligue a decidir, no que se quede en "ya lo miraré".
            msgs.append(f"FACTURA DUPLICADA: es la misma que la línea "
                        f"{self._duplicados[r] + 1} del lote (mismo nº, NIF, "
                        f"base y tipo de IVA). Bórrala o quedará registrada dos veces.")
            estado = ERROR
        celda = self.tabla.item(r, C_ESTADO)
        self.tabla.blockSignals(True)
        celda.setText(ICONO_ESTADO[estado])
        celda.setBackground(COLOR_ESTADO[estado])
        celda.setForeground(QColor("white"))
        celda.setToolTip("\n".join(msgs) if msgs else "Todo correcto")
        self.tabla.blockSignals(False)
        self._resumen()

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
        recargo = self.chk_recargo.isChecked()
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
        self.tabla_resumen.setRowCount(len(lineas))
        for r, (bloque, tipo, t, es_total) in enumerate(lineas):
            # En recargo el gasto va por el total factura: el desglose de IVA
            # no existe y ponerlo a 0,00 despistaria.
            solo_total = recargo and tipo == "Gastos"
            valores = [
                bloque, tipo, str(t.lineas),
                "" if solo_total else eur(t.base),
                "" if solo_total else eur(t.iva),
                eur(t.requiv) if t.tiene_requiv and not solo_total else "",
                f"−{eur(t.irpf)}" if t.tiene_irpf else "",
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
        filas = ["\t".join(COLS_RESUMEN)]
        for r in range(self.tabla_resumen.rowCount()):
            filas.append("\t".join(
                (self.tabla_resumen.item(r, c).text() if self.tabla_resumen.item(r, c)
                 else "")
                for c in range(self.tabla_resumen.columnCount())))
        QApplication.clipboard().setText("\n".join(filas))
        self.lbl_estado.setText("Resumen copiado al portapapeles.")

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
    def _exportar_todo(self):
        """Genera en una sola operación los Excel de gastos e ingresos."""
        por_tipo = {"gasto": [], "venta": []}
        for fila in range(self.tabla.rowCount()):
            por_tipo[self._tipo_fila(fila)].append(self._leer_fila(fila))
        if not any(por_tipo.values()):
            QMessageBox.warning(self, "Sin datos", "No hay facturas que exportar.")
            return

        problemas = []
        if self._duplicados:
            problemas.append(
                f"{len(self._duplicados)} factura(s) duplicada(s) que se registrarían dos veces")
        errores = sum(
            1 for facturas in por_tipo.values() for factura in facturas
            if validar(factura).estado == ERROR)
        if errores:
            problemas.append(f"{errores} línea(s) con errores")
        if problemas:
            respuesta = QMessageBox.question(
                self, "Revisión pendiente",
                "Antes de exportar se han detectado:\n\n  · "
                + "\n  · ".join(problemas)
                + "\n\n¿Quiere exportar de todas formas?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if respuesta != QMessageBox.Yes:
                self._siguiente_incidencia()
                return

        carpeta = QFileDialog.getExistingDirectory(
            self, "Carpeta para los Excel de Aplifisa", ESCRITORIO)
        if not carpeta:
            return
        generados = []
        for tipo, nombre, xml in (
            ("gasto", "gastos.xlsx", "gastos.xml"),
            ("venta", "ingresos.xlsx", "ingresos.xml"),
        ):
            if not por_tipo[tipo]:
                continue
            ruta = os.path.join(carpeta, nombre)
            exportar_excel(por_tipo[tipo], leer_config(ruta_config(xml)), ruta)
            generados.append(nombre)
        QMessageBox.information(
            self, "Exportación terminada",
            "Archivos preparados para Aplifisa:\n\n  · "
            + "\n  · ".join(generados)
            + f"\n\nCarpeta: {carpeta}")


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
