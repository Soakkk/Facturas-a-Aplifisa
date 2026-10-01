"""Ventana principal de Facturas a Aplifisa.

Flujo: Cargar facturas (PDF/imagenes) -> Gemini extrae y clasifica en segundo
plano -> autodetecta el cliente -> tabla de revision con miniatura y semaforo
(editable, se puede cambiar gasto/venta) -> Exportar gastos.xlsx / ventas.xlsx.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback

from PySide6.QtCore import QSize, Qt, QThread, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QProgressDialog, QScrollArea,
    QSizePolicy, QSplitter, QTableWidget, QTextBrowser, QVBoxLayout, QWidget,
    QGridLayout,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel import (
    __version__, ajustes, archivo, costes, errores, escaner, notas_version,
    pendientes, revision_gemini, sesion, updater, muestras_revision,
)
from facturas_excel.banda_avisos import AVISO, EXITO, INFO, BandaAvisos
from facturas_excel.claves import guardar_api_key, leer_api_key
from facturas_excel.dialogo_calidad import DialogoCalidad
from facturas_excel.dialogo_modelos import DialogoModelos
from facturas_excel.dialogo_pendientes import DialogoPendientes
from facturas_excel.dialogo_notas_version import DialogoNotasVersion
from facturas_excel.dialogo_recargo import DialogoRecargo
from facturas_excel.dialogo_textos import DialogoTextos
from facturas_excel.clientes import (
    DESGLOSE, TOTAL, guardar_regimen_recargo, regimen_recargo,
)
from facturas_excel.conceptos import descripcion_de, es_valido
from facturas_excel.control_facturas import clave_documento
from facturas_excel.consulta import (
    PeriodoLote, coincide_busqueda, detectar_periodo, facturas_unicas, periodo_manual,
)
from facturas_excel.estilo import (
    CHROME, CHROME_INK, aplicar_tema,
)
from facturas_excel.panel_ficha import PanelFicha
from facturas_excel.modelo import Factura
from facturas_excel.procesar import (
    a_total_factura, clave_proveedor, construir, normaliza_nif, quitar_aviso_cuenta,
    recordar_cuenta_proveedor, recordar_nif, recordar_nombre_proveedor,
)
from facturas_excel.lote import (
    CON_ERROR, CORREGIDA, PENDIENTES, POR_REVISAR, REVISADA, SIN_VERIFICAR,
    VERIFICADA, Fila,
    filas_de_bloques, ordenar as ordenar_filas,
)
# Las columnas, los estados y el Worker se siguen importando desde aquí en
# otros módulos y en las pruebas: por eso algunos nombres no se usan dentro.
from facturas_excel.tabla_facturas import (  # noqa: F401
    CAMPO_DE_COLUMNA, COLS, COLUMNAS_IRPF, C_BASE, C_BASE_IRPF, C_BASE_RE,
    C_BLOQUE, C_CUENTA, C_CUOTA, C_CUOTA_IRPF, C_CUOTA_RE, C_ESTADO, C_FECHA,
    C_GXX, C_NIF, C_NOMBRE, C_NUM, C_PCT, C_PCT_IRPF, C_PCT_RE, C_TIPO, C_TOTAL,
    ComboSinRueda, TablaFacturas, fmt, parse_numero, valor_de_celda,
)
from facturas_excel.validacion import REVISAR, validar_nif
from facturas_excel.ventana_validacion import MENSAJES_DE_ESTADO

# Datos de la cabecera de una factura (iguales en todas sus líneas).
CAMPOS_CABECERA = ("num_factura", "fecha", "nombre", "nif", "concepto", "subclave")
# Anchos de partida de las tres columnas (facturas | factura | totales).
TAMANOS_COLUMNAS = [1080, 480, 300]
from facturas_excel.ventana_comun import (  # noqa: F401
    COLS_RESUMEN_INICIO, COLS_RESUMEN_FIN, ESCRITORIO, EtiquetaCliente,
    ICONO_CORREGIDO, ICONO_ESTADO, ICONO_REVISADO, ICONO_SIN_VERIFICAR,
    TODOS_LOS_BLOQUES, _cabeceras_resumen, ruta_recurso,
    rutas_factura_de_mime,
)
from facturas_excel.hilos import (  # noqa: F401
    HILOS, HiloActualizacion, HiloDescargaActualizacion, Worker, hilos_lectura,
)
from facturas_excel.cinta import ICONO_CINTA, crear_cinta
from facturas_excel import localizar
from facturas_excel.visor import VisorDocumento
from facturas_excel.ventana_aplifisa import AplifisaMixin
from facturas_excel.ventana_archivo import ArchivoMixin
from facturas_excel.ventana_ficha import FichaMixin
from facturas_excel.ventana_lectura import LecturaMixin
from facturas_excel.ventana_validacion import ValidacionMixin


class VentanaPrincipal(LecturaMixin, ArchivoMixin, AplifisaMixin, ValidacionMixin,
                        FichaMixin, QMainWindow):
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
        self._ejercicio_lote = None
        self._periodo_lote = PeriodoLote()
        self._periodo_manual_valor = "auto"
        self._informe_registro = None
        self._columna_orden = None
        self._orden_ascendente = True
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
        # Dónde está cada dato en cada hoja: {clave de la imagen: [Caja]}.
        self._localizaciones = {}
        self._localizando = set()
        self._hilo_localizar = None
        self._columna_senalada = None
        self._error_muestras = ""
        self._timer_muestras = QTimer(self)
        self._timer_muestras.setSingleShot(True)
        self._timer_muestras.setInterval(800)
        self._timer_muestras.timeout.connect(self._guardar_muestra_revision)
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
        self._timer_divisores = QTimer(self)
        self._timer_divisores.setSingleShot(True)
        self._timer_divisores.setInterval(350)
        self._timer_divisores.timeout.connect(self._guardar_divisores)
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

        # Mesa de revisión: cabecera clara, buscador global, tabla + original
        # y comprobación debajo. Ningún filtro cambia el alcance del exportador.
        cuerpo = QVBoxLayout()
        cuerpo.setContentsMargins(12, 8, 12, 8)
        cuerpo.setSpacing(8)

        # Cliente y periodo van dentro de la cinta, en el hueco que quedaba
        # vacío entre los botones y «Exportar» (antes eran una fila aparte).
        cliente_bar = QFrame()
        cliente_bar.setObjectName("cajaCliente")
        bloque_cliente = QGridLayout(cliente_bar)
        bloque_cliente.setContentsMargins(6, 0, 6, 0)
        bloque_cliente.setHorizontalSpacing(8)
        bloque_cliente.setVerticalSpacing(2)
        etiqueta = QLabel("Cliente")
        etiqueta.setObjectName("textoSuave")
        self.lbl_cliente = EtiquetaCliente("Pendiente de detectar")
        self.lbl_cliente.setObjectName("cliente")
        self.lbl_cliente.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        bloque_cliente.addWidget(etiqueta, 0, 0)
        bloque_cliente.addWidget(self.lbl_cliente, 0, 1)
        self.btn_cliente = QPushButton("Cambiar")
        self.btn_cliente.setObjectName("compacto")
        self.btn_cliente.setMaximumWidth(110)
        self.btn_cliente.setToolTip(
            "Quién es SU cliente en estas facturas. Si se detectó mal, se "
            "cambia aquí y el lote se rehace sin volver a pasar por Gemini.")
        self.btn_cliente.setEnabled(False)
        self.btn_cliente.clicked.connect(self._cambiar_cliente)
        bloque_cliente.addWidget(self.btn_cliente, 0, 2)
        lbl_periodo = QLabel("Periodo")
        lbl_periodo.setObjectName("textoSuave")
        bloque_cliente.addWidget(lbl_periodo, 1, 0)
        self.combo_periodo = ComboSinRueda()
        self.combo_periodo.setMinimumWidth(150)
        self.combo_periodo.setToolTip(
            "Periodo fiscal esperado del lote. En automático detecta un "
            "trimestre dominante o un ejercicio anual. Las fechas que se "
            "salen del trimestre quedan señaladas para revisar.")
        self.combo_periodo.addItem("Automático", "auto")
        self.combo_periodo.currentIndexChanged.connect(self._on_periodo)
        bloque_cliente.addWidget(self.combo_periodo, 1, 1, 1, 2, Qt.AlignLeft)
        # Lo que sobre, después de «Cambiar» (que va pegado al nombre).
        bloque_cliente.setColumnStretch(3, 1)
        self.combo_periodo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._rotulos_cliente = (etiqueta, lbl_periodo)
        # El cliente se queda con el sitio que sobre en la cinta.
        self.layout_cinta.insertWidget(self.posicion_cliente, cliente_bar, 1)
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
        cuerpo.addWidget(self.fila_recargo)

        # Se conserva el contador para la lógica interna, pero no se duplica en
        # pantalla: el encabezado de Datos extraídos ya informa del lote visible.
        self.lbl_lote = QLabel("Lote completo · sin facturas cargadas", self)
        self.lbl_lote.hide()

        self.btn_revisar_lote = QPushButton("1 · Revisar facturas", self)
        self.btn_revisar_lote.setObjectName("paso")
        self.btn_revisar_lote.setCheckable(True)
        self.btn_revisar_lote.setChecked(True)
        self.btn_revisar_lote.clicked.connect(self._volver_a_revision)
        self.btn_revisar_lote.hide()

        self.progreso = QProgressBar()
        self.progreso.setVisible(False)
        cuerpo.addWidget(self.progreso)

        # Alerta de duplicados: tiene que verse sin tener que pasar el raton
        # por encima de una celda (un duplicado importado se paga dos veces).
        self.alerta = QFrame()
        self.alerta.setObjectName("alerta")
        self.alerta.setVisible(False)
        lal = QVBoxLayout(self.alerta)
        lal.setContentsMargins(14, 8, 14, 8)
        lal.setSpacing(2)
        self.lbl_alerta_titulo = QLabel()
        self.lbl_alerta_titulo.setObjectName("alertaTitulo")
        self.lbl_alerta_texto = QLabel()
        self.lbl_alerta_texto.setObjectName("alertaTexto")
        self.lbl_alerta_texto.setWordWrap(True)
        fila_alerta = QHBoxLayout()
        fila_alerta.addWidget(self.lbl_alerta_titulo, 1)
        self.btn_ver_incidencias = QPushButton("Ver incidencias")
        self.btn_ver_incidencias.clicked.connect(self._siguiente_incidencia)
        fila_alerta.addWidget(self.btn_ver_incidencias)
        lal.addLayout(fila_alerta)
        lal.addWidget(self.lbl_alerta_texto)

        split = QSplitter(Qt.Horizontal)
        self.split_revision = split
        split.setObjectName("splitRevision")
        split.setChildrenCollapsible(False)
        split.setHandleWidth(8)
        tabla_card = QFrame()
        tabla_card.setObjectName("tarjeta")
        lt = QVBoxLayout(tabla_card)
        lt.setContentsMargins(12, 10, 12, 10)
        fila_datos = QHBoxLayout()
        titulo_tabla = QLabel("Datos extraídos")
        titulo_tabla.setObjectName("tituloSeccion")
        fila_datos.addWidget(titulo_tabla)
        self.lbl_resultados = QLabel("Sin facturas")
        self.lbl_resultados.setObjectName("textoSuave")
        fila_datos.addWidget(self.lbl_resultados, 1, Qt.AlignRight)
        lt.addLayout(fila_datos)

        # En ventana ancha coincide con el prototipo: filtros y acciones en
        # una fila. En portátiles se reparten sin comprimir ni cortar textos.
        self.layout_herramientas = QVBoxLayout()
        self.layout_herramientas.setSpacing(6)
        self.layout_herramientas.setContentsMargins(0, 0, 0, 0)
        self.filas_herramientas = []
        # Filas de sobra: con la letra de Windows los filtros pueden ocupar
        # cuatro o cinco filas en un portátil y las acciones necesitan las
        # suyas (una fila vacía no ocupa sitio).
        for _ in range(10):
            fila_herramientas = QHBoxLayout()
            fila_herramientas.setSpacing(8)
            fila_herramientas.setContentsMargins(0, 0, 0, 0)
            fila_herramientas.addStretch(1)
            self.layout_herramientas.addLayout(fila_herramientas)
            self.filas_herramientas.append(fila_herramientas)
        self.lbl_mostrar = QPushButton()
        self.lbl_mostrar.setObjectName("botonIcono")
        self.lbl_mostrar.setIcon(QIcon(ruta_recurso("filter.svg")))
        self.lbl_mostrar.setFixedWidth(30)
        self.lbl_mostrar.setToolTip("Filtrar las facturas mostradas")
        self.combo_filtro_estado = ComboSinRueda()
        self.combo_filtro_estado.addItems(
            ["Todas las facturas", "Solo por revisar", "Solo con errores",
             "Solo correctas", "Fuera del trimestre"])
        self.combo_filtro_estado.setToolTip("Qué facturas se ven en la tabla.")
        self.combo_filtro_estado.currentIndexChanged.connect(self._aplicar_filtro)
        self.combo_filtro_bloque = ComboSinRueda()
        self.combo_filtro_bloque.addItem(TODOS_LOS_BLOQUES)
        self.combo_filtro_bloque.setToolTip(
            "Cada escaneo o PDF cargado es un bloque. Puede revisarlos de uno "
            "en uno y exportarlos todos juntos.")
        self.combo_filtro_bloque.currentIndexChanged.connect(self._aplicar_filtro)
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setObjectName("buscadorLote")
        # Tamaño de buscador, no de barra: antes ocupaba todo el ancho.
        self.txt_buscar.setFixedWidth(280)
        self.txt_buscar.addAction(
            QIcon(ruta_recurso("search.svg")), QLineEdit.LeadingPosition)
        self.txt_buscar.setPlaceholderText(
            "Proveedor o cliente, NIF, nº de factura o importe…")
        self.txt_buscar.setClearButtonEnabled(True)
        self.txt_buscar.setToolTip(
            "Busca en todo el lote cargado. Si escribe un importe con dos "
            "decimales, busca en base, IVA, retención y total.")
        self.txt_buscar.textChanged.connect(self._aplicar_filtro)
        self.grupo_tipo = QButtonGroup(self)
        self.botones_tipo = {}
        for valor, texto in (("todos", "Todos"), ("gasto", "Gastos"),
                             ("venta", "Ingresos")):
            boton = QPushButton(texto)
            boton.setObjectName("filtroTipo")
            boton.setCheckable(True)
            boton.setProperty("tipoFiltro", valor)
            self.grupo_tipo.addButton(boton)
            self.botones_tipo[valor] = boton
        self.botones_tipo["todos"].setChecked(True)
        self.grupo_tipo.buttonClicked.connect(self._aplicar_filtro)
        # Todos / Gastos / Ingresos, pequeños y juntos (al final salen dos
        # Excel distintos: es solo para mirar).
        self.caja_tipo = QWidget()
        capa_tipo = QHBoxLayout(self.caja_tipo)
        capa_tipo.setContentsMargins(0, 0, 0, 0)
        capa_tipo.setSpacing(2)
        for boton in self.botones_tipo.values():
            capa_tipo.addWidget(boton)
        cuerpo.addWidget(self.alerta)
        self.banda = BandaAvisos(self)
        cuerpo.addWidget(self.banda)
        self.combo_filtro_registro = ComboSinRueda()
        self.combo_filtro_registro.addItem("Aplifisa: todas", "todas")
        self.combo_filtro_registro.setToolTip(
            "Resultado de la última comparación con el listado de Aplifisa.")
        self.combo_filtro_registro.currentIndexChanged.connect(self._aplicar_filtro)
        self.combo_filtro_registro.setVisible(False)
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
        self.btn_unir_hojas = QPushButton("Unir hojas")
        self.btn_unir_hojas.setObjectName("accionTabla")
        self.btn_unir_hojas.setIcon(QIcon(ruta_recurso("link.svg")))
        self.btn_unir_hojas.setToolTip(
            "Seleccione las filas que pertenecen a la misma factura. La primera "
            "aporta la cabecera y la última, el resumen fiscal.")
        self.btn_unir_hojas.clicked.connect(self._unir_hojas_seleccionadas)
        self.btn_limpiar_filtros = QPushButton("Limpiar filtros")
        self.btn_limpiar_filtros.setObjectName("accionTabla")
        self.btn_limpiar_filtros.clicked.connect(self._limpiar_filtros)
        self.btn_quitar_bloque = QPushButton("Quitar bloque")
        self.btn_quitar_bloque.setObjectName("accionPeligrosa")
        self.btn_quitar_bloque.setIcon(QIcon(ruta_recurso("trash.svg")))
        self.btn_quitar_bloque.setToolTip(
            "Quita del lote el bloque elegido en el desplegable (p.ej. si se ha "
            "cargado un PDF que no tocaba).")
        self.btn_quitar_bloque.clicked.connect(self._quitar_bloque)
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_eliminar.setObjectName("accionPeligrosa")
        self.btn_eliminar.setIcon(QIcon(ruta_recurso("trash.svg")))
        self.btn_eliminar.setToolTip("Elimina del lote las filas seleccionadas.")
        self.btn_eliminar.clicked.connect(self._eliminar_seleccion)
        self.btn_deshacer_borrado = QPushButton("Deshacer")
        self.btn_deshacer_borrado.setObjectName("accionTabla")
        self.btn_deshacer_borrado.setEnabled(False)
        self.btn_deshacer_borrado.setVisible(False)
        self.btn_deshacer_borrado.clicked.connect(self._deshacer_borrado)
        for boton in (
                self.btn_siguiente, self.btn_revisada, self.btn_unir_hojas,
                self.btn_limpiar_filtros, self.btn_quitar_bloque,
                self.btn_eliminar, self.btn_deshacer_borrado):
            boton.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        lt.addLayout(self.layout_herramientas)
        # Orden contable estable: clasificación y cuenta primero, identificación
        # después e importes fiscales al final (tabla_facturas.py).
        self.tabla = TablaFacturas()
        cabecera_tabla = self.tabla.horizontalHeader()
        cabecera_tabla.sectionClicked.connect(self._ordenar_tabla_por)
        cabecera_tabla.setContextMenuPolicy(Qt.CustomContextMenu)
        cabecera_tabla.customContextMenuRequested.connect(self._menu_columnas)
        self.tabla.itemChanged.connect(self._on_celda)
        self.tabla.cellClicked.connect(self._abrir_ficha)
        self.tabla.cellClicked.connect(self._senalar_celda)
        self.tabla.currentCellChanged.connect(
            lambda fila, columna, *_: self._senalar_celda(fila, columna))
        self.tabla.itemSelectionChanged.connect(self._mostrar_miniatura)
        lt.addWidget(self.tabla, 1)

        split.addWidget(tabla_card)

        # Columna central: la factura entera en una sola tarjeta. Arriba la
        # hoja escaneada y debajo lo que ha leído la IA (antes eran dos
        # columnas; el usuario las quería unidas para dejar sitio a los
        # totales).
        visor_card = QFrame()
        visor_card.setObjectName("tarjeta")
        visor_card.setMinimumWidth(290)
        self.factura_card = visor_card
        lv = QVBoxLayout(visor_card)
        lv.setContentsMargins(12, 12, 12, 10)
        titulo_visor = QLabel("Factura")
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
        self.btn_zoom_menos.clicked.connect(lambda: self._cambiar_zoom_visor(-1))
        barra_documento.addWidget(self.btn_zoom_menos)
        self.btn_zoom_mas = QPushButton()
        self.btn_zoom_mas.setObjectName("botonVisor")
        self.btn_zoom_mas.setIcon(QIcon(ruta_recurso("zoom-in.svg")))
        self.btn_zoom_mas.setToolTip("Acercar documento")
        self.btn_zoom_mas.clicked.connect(lambda: self._cambiar_zoom_visor(1))
        barra_documento.addWidget(self.btn_zoom_mas)
        self.btn_senalar = QPushButton("¿De dónde sale?")
        self.btn_senalar.setObjectName("botonSenalar")
        self.btn_senalar.setIcon(QIcon(ruta_recurso("search.svg")))
        self.btn_senalar.setToolTip(
            "Señala con recuadros en el documento dónde está escrito cada dato "
            "de la factura. Pulse después una celda de la tabla para ver solo "
            "ese dato. Las facturas en ámbar o rojo se señalan solas.")
        self.btn_senalar.clicked.connect(self._localizar_actual)
        self.lbl_origen.setMinimumWidth(40)
        barra_documento.addWidget(self.btn_senalar)
        self.btn_opciones_visor = QPushButton("⋮")
        self.btn_opciones_visor.setObjectName("botonVisor")
        menu_visor = QMenu(self.btn_opciones_visor)
        # Sin «vista previa grande»: tapaba toda la ventana. La hoja se
        # acerca y se mueve aquí mismo.
        menu_visor.addAction("Ver la hoja entera", self._ver_hoja_entera)
        menu_visor.addAction("Ajustar al ancho", self._ajustar_al_ancho)
        self.btn_opciones_visor.setMenu(menu_visor)
        barra_documento.addWidget(self.btn_opciones_visor)
        self.lbl_img = VisorDocumento(
            "Suelte aquí las facturas\no use «Abrir PDF o imágenes»")
        self.lbl_img.setObjectName("visor")
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setMinimumWidth(250)
        self.lbl_img.setMinimumHeight(180)
        self.lbl_img.setToolTip(
            "Arrastre para moverse por la hoja. Ctrl + rueda o doble clic "
            "para acercar; otro doble clic vuelve a la hoja entera.")
        self.lbl_img.zoom_pedido.connect(self._zoom_en)
        self.lbl_img.doble_clic.connect(self._zoom_doble_clic)
        self._pixmap_documento = QPixmap()
        self._png_visor = None
        self._fuente_visor = None
        self._nitida = None
        self._sin_nitida = set()
        self._zoom_visor = 1.0
        # La hoja fina se saca cuando el zoom (o el tamaño) se queda quieto.
        self._timer_nitida = QTimer(self)
        self._timer_nitida.setSingleShot(True)
        self._timer_nitida.timeout.connect(self._pintar_nitida)
        self._timer_visor = QTimer(self)
        self._timer_visor.setSingleShot(True)
        self._timer_visor.setInterval(60)
        self._timer_visor.timeout.connect(self._pintar_pixmap_visor)
        self.visor_scroll = QScrollArea()
        self.visor_scroll.setObjectName("visorScroll")
        self.visor_scroll.setWidgetResizable(True)
        self.visor_scroll.setWidget(self.lbl_img)
        # Al mover el divisor del visor, la hoja se vuelve a encajar.
        self.visor_scroll.installEventFilter(self)
        lv.addWidget(titulo_visor)
        lv.addLayout(barra_documento)
        # Hoja arriba, lectura debajo; el divisor decide cuánto de cada.
        self.split_factura = QSplitter(Qt.Vertical)
        self.split_factura.setObjectName("splitFactura")
        self.split_factura.setChildrenCollapsible(False)
        self.split_factura.setHandleWidth(8)
        self.split_factura.addWidget(self.visor_scroll)
        lectura = QWidget()
        lf = QVBoxLayout(lectura)
        lf.setContentsMargins(0, 4, 0, 0)
        lf.setSpacing(2)
        titulo_ficha = QLabel("Lo que ha leído la IA")
        titulo_ficha.setObjectName("tituloSubseccion")
        lf.addWidget(titulo_ficha)
        self.ficha = PanelFicha()
        self.ficha.setMinimumHeight(110)
        self.ficha.discrepancia_resuelta.connect(self._resolver_discrepancia)
        lf.addWidget(self.ficha, 1)
        self.split_factura.addWidget(lectura)
        self.split_factura.setStretchFactor(0, 3)
        self.split_factura.setStretchFactor(1, 2)
        self.split_factura.setSizes(
            self._tamanos_divisor("split_factura", [520, 320]))
        self.split_factura.splitterMoved.connect(
            lambda *_: self._timer_divisores.start())
        lv.addWidget(self.split_factura, 1)
        split.addWidget(visor_card)

        # Tercera columna, a toda la altura: los totales con el desglose
        # completo, para cuadrar con la suma a mano y con Aplifisa.
        lado_card = QFrame()
        lado_card.setObjectName("tarjeta")
        lado_card.setMinimumWidth(250)
        self.lado_card = lado_card
        lado = QVBoxLayout(lado_card)
        lado.setContentsMargins(12, 12, 12, 10)

        resumen_card = QWidget()
        lr = QVBoxLayout(resumen_card)
        lr.setContentsMargins(0, 0, 0, 0)
        lr.setSpacing(4)
        self.lbl_resumen_titulo = QLabel("Comprobación de totales")
        self.lbl_resumen_titulo.setObjectName("tituloSeccion")
        self.lbl_resumen_titulo.setWordWrap(True)
        cabecera_totales = QHBoxLayout()
        cabecera_totales.setSpacing(4)
        cabecera_totales.addWidget(self.lbl_resumen_titulo, 1)
        # Ocultar, como una ✕ junto al título: abajo no cabía con los otros
        # dos botones en una columna estrecha.
        btn_cerrar_resumen = QPushButton("✕")
        btn_cerrar_resumen.setObjectName("botonVisor")
        btn_cerrar_resumen.setFixedWidth(26)
        btn_cerrar_resumen.setToolTip(
            "Ocultar los totales. Es solo una comprobación: se vuelven a ver "
            "en el menú Ver.")
        btn_cerrar_resumen.clicked.connect(lambda: self._ver_resumen(False))
        cabecera_totales.addWidget(btn_cerrar_resumen, 0, Qt.AlignTop)
        lr.addLayout(cabecera_totales)
        # Los totales, en vertical: un bloque por gastos e ingresos (y por
        # periodo o filtro), con una línea por importe.
        self.vista_totales = QTextBrowser()
        self.vista_totales.setObjectName("vistaTotales")
        self.vista_totales.setOpenLinks(False)
        self.vista_totales.setFrameShape(QFrame.NoFrame)
        lr.addWidget(self.vista_totales, 1)
        fila_botones = QHBoxLayout()
        fila_botones.setSpacing(6)
        btn_copiar = QPushButton("Copiar")
        btn_copiar.setObjectName("compacto")
        btn_copiar.setToolTip(
            "Copia el resumen al portapapeles para pegarlo donde haga falta.")
        btn_copiar.clicked.connect(self._copiar_resumen)
        fila_botones.addWidget(btn_copiar)
        self.btn_listado_totales = QPushButton("Listado PDF")
        self.btn_listado_totales.setObjectName("compacto")
        self.btn_listado_totales.setToolTip(
            "Guarda un listado imprimible con los totales y las facturas "
            "mostradas en la tabla.")
        self.btn_listado_totales.clicked.connect(self._guardar_listado_totales)
        fila_botones.addWidget(self.btn_listado_totales)
        fila_botones.addStretch(1)
        lr.addLayout(fila_botones)
        # La tabla de siempre sigue siendo el dato (Copiar, Listado PDF y
        # las pruebas la leen); en pantalla se ve la versión vertical.
        self.tabla_resumen = QTableWidget(0, len(COLS_RESUMEN_INICIO) + 1
                                          + len(COLS_RESUMEN_FIN), resumen_card)
        self.tabla_resumen.setHorizontalHeaderLabels(
            _cabeceras_resumen([]))
        self.tabla_resumen.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_resumen.hide()
        self.resumen_card = resumen_card
        lado.addWidget(resumen_card, 1)
        split.addWidget(lado_card)
        # «Ocultar» quita la columna entera; se vuelve a ver en el menú Ver.
        lado_card.setVisible(bool(ajustes.leer("ver_totales_lado", True)))
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 2)
        split.setSizes(self._tamanos_divisor("split_revision_v4", TAMANOS_COLUMNAS))
        split.splitterMoved.connect(self._divisor_revision_movido)
        cuerpo.addWidget(split, 1)

        barra_estado = QFrame()
        barra_estado.setObjectName("barraEstado")
        pie = QHBoxLayout(barra_estado)
        pie.setContentsMargins(12, 4, 12, 4)
        pie.setSpacing(14)
        self.lbl_estado = QLabel("Cargue o escanee un lote de facturas para empezar.")
        self.lbl_estado.setObjectName("textoSuave")
        # Un mensaje largo no ensancha la ventana: se recorta por la derecha.
        self.lbl_estado.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lbl_estado.setMinimumWidth(0)
        pie.addWidget(self.lbl_estado, 1)
        self.lbl_contadores = QLabel("")
        self.lbl_contadores.setObjectName("contadores")
        self.lbl_contadores.setToolTip(
            "Verificada: las dos lecturas coinciden y todo cuadra.\n"
            "Sin verificar: todo cuadra, pero solo la leyó un modelo.\n"
            "Revisada: la ha confirmado usted con «Marcar revisada».\n"
            "Corregida: ha cambiado usted algún dato; cuenta como revisada.\n"
            "Revisar: hay algo que mirar antes de exportar.\n"
            "Error: no se puede exportar hasta corregirlo.")
        pie.addWidget(self.lbl_contadores)
        self.lbl_gasto = QLabel()
        self.lbl_gasto.setObjectName("textoSuave")
        self.lbl_gasto.setToolTip(
            "Lo que cuesta leer las facturas con Gemini. Se calcula con los "
            "tokens reales de cada respuesta.\nGoogle no permite consultar el "
            "saldo de la cuenta desde el programa: esto es la cuenta que lleva "
            "el propio programa.")
        pie.addWidget(self.lbl_gasto)
        cont = QWidget()
        cont.setLayout(cuerpo)
        raiz.addWidget(cont, 1)
        raiz.addWidget(barra_estado)
        self.setCentralWidget(central)
        self._actualizar_barra_responsiva(self.width())
        self._distribuir_herramientas(self.width())
        # Tras el primer layout Qt ya conoce el ancho real del panel izquierdo.
        # Temporizador hijo de la ventana: si se cierra antes, no salta.
        self._timer_herramientas = QTimer(self)
        self._timer_herramientas.setSingleShot(True)
        self._timer_herramientas.timeout.connect(
            lambda: self._distribuir_herramientas(self.width()))
        self._timer_herramientas.start(0)

    def _distribuir_herramientas(self, ancho: int):
        """Filtros a la izquierda y, debajo, las acciones, sin cortar textos.

        Con tres columnas la de la tabla es más estrecha: lo que no cabe en
        una fila pasa a la siguiente (nunca se encoge ni se oculta nada).
        """
        if not hasattr(self, "tabla"):
            return
        if hasattr(self, "btn_senalar"):
            # En un visor estrecho el botón se abrevia en vez de cortarse.
            visor = self.visor_scroll.parentWidget()
            texto = ("¿De dónde sale?" if visor is not None and visor.width() >= 430
                     else "¿Dónde?")
            if self.btn_senalar.text() != texto:
                self.btn_senalar.setText(texto)
            self.btn_senalar.setMinimumWidth(self.btn_senalar.sizeHint().width())
        filtros = (
            self.lbl_mostrar, self.combo_filtro_estado, self.caja_tipo,
            self.txt_buscar, self.combo_filtro_bloque, self.combo_filtro_registro,
        )
        acciones = (
            self.btn_siguiente, self.btn_revisada, self.btn_unir_hojas,
            self.btn_limpiar_filtros, self.btn_quitar_bloque,
            self.btn_eliminar, self.btn_deshacer_borrado,
        )
        for fila in self.filas_herramientas:
            for elemento in filtros + acciones:
                fila.removeWidget(elemento)
        self.combo_filtro_bloque.setMinimumWidth(135)
        self.combo_filtro_bloque.setMaximumWidth(220)
        ancho_tabla = min(ancho, self.tabla.parentWidget().width())
        disponible = max(320, ancho_tabla - 24)
        def oculto(widget) -> bool:
            # Ocultado a propósito (no solo porque la ventana aún no se ve).
            return (widget.testAttribute(Qt.WA_WState_ExplicitShowHide)
                    and widget.testAttribute(Qt.WA_WState_Hidden))

        fila_actual = -1
        ultima = len(self.filas_herramientas) - 1
        for grupo in (filtros, acciones):
            fila_actual = min(fila_actual + 1, ultima)
            usado = 0
            for widget in grupo:
                if widget is self.btn_deshacer_borrado and not widget.isEnabled():
                    continue
                if oculto(widget):
                    # En su sitio pero sin contar: no ocupa hasta que se vea.
                    fila = self.filas_herramientas[fila_actual]
                    fila.insertWidget(fila.count() - 1, widget)
                    continue
                maximo = widget.maximumWidth()
                preferido = max(widget.minimumWidth(), widget.sizeHint().width())
                if maximo < 16_777_215:
                    preferido = min(preferido, maximo)
                necesario = preferido + (8 if usado else 0)
                if usado and usado + necesario > disponible and fila_actual < ultima:
                    fila_actual += 1
                    usado = 0
                    necesario = preferido
                fila = self.filas_herramientas[fila_actual]
                fila.insertWidget(fila.count() - 1, widget)
                usado += necesario

    def _actualizar_barra_responsiva(self, ancho: int):
        """Nunca se cortan los textos de la cinta.

        En ventanas estrechas los botones de uso ocasional se quedan solo con
        el icono (su nombre sale al pasar el ratón); en poca altura, iconos
        algo más pequeños.
        """
        if not hasattr(self, "fila_barra_estrecha"):
            return
        baja = self.height() < 760
        icono = QSize(18, 18) if baja else QSize(ICONO_CINTA, ICONO_CINTA)
        principales = (self.btn_cargar, self.btn_escanear, self.btn_gastos)

        def aplicar(nivel: int) -> None:
            # 0: todo con su nombre; 1: los ocasionales solo con el icono;
            # 2: también el resto, menos Abrir, Escanear y Exportar.
            for boton in self._botones_grandes:
                boton.setIconSize(icono)
                solo = ((nivel >= 1 and boton in self._botones_secundarios)
                        or (nivel >= 2 and boton not in principales))
                boton.setToolButtonStyle(Qt.ToolButtonIconOnly if solo
                                         else Qt.ToolButtonTextUnderIcon)
                if boton.property("soloIcono") != solo:
                    boton.setProperty("soloIcono", solo)
                    boton.style().unpolish(boton)
                    boton.style().polish(boton)
            for rotulo in getattr(self, "_rotulos_cliente", ()):
                rotulo.setVisible(nivel < 2)

        # Se quitan nombres solo si de verdad no caben: así nunca se corta un
        # texto ni se pierden sin necesidad. Antes de recortar el nombre del
        # cliente se pasan a icono los ocasionales (el cliente importa más).
        disponible = max(ancho, self.minimumWidth())
        etiqueta = getattr(self, "lbl_cliente", None)
        # Hasta 420 px de nombre: uno larguísimo no manda los ocasionales a
        # icono en ventanas grandes (se recorta con «…» y sale en el globo).
        holgura = 0 if etiqueta is None else max(
            0, min(etiqueta.sizeHint().width(), 420)
            - etiqueta.minimumSizeHint().width())
        for nivel in (0, 1, 2):
            aplicar(nivel)
            necesario = self.barra_rapida.layout().minimumSize().width()
            if nivel < 1:
                necesario += holgura
            if necesario <= disponible:
                break
        self.barra_rapida.layout().setContentsMargins(
            8, 2 if baja else 4, 8, 2 if baja else 4)
        self.barra_rapida.show()
        self.fila_barra_estrecha.setVisible(True)
        if hasattr(self, "tabla_resumen"):
            self._ajustar_altura_resumen()

    def _ajustar_altura_resumen(self):
        # La altura la decide ahora el usuario arrastrando el divisor vertical.
        # Solo se recalcula la geometría interna cuando cambia el número de filas.
        self.tabla_resumen.updateGeometry()

    def _volver_a_revision(self):
        self.btn_revisar_lote.setChecked(True)
        self.tabla.setFocus()

    @staticmethod
    def _tamanos_divisor(clave: str, por_defecto: list[int]) -> list[int]:
        valor = ajustes.leer(clave, por_defecto)
        if (isinstance(valor, list) and len(valor) == len(por_defecto)
                and all(isinstance(n, int) and n > 0 for n in valor)):
            return valor
        return por_defecto

    def _divisor_revision_movido(self, *_):
        self._distribuir_herramientas(self.width())
        self._timer_divisores.start()

    def _guardar_divisores(self):
        # Claves nuevas en la 1.18: los tamaños de antes eran de otras
        # columnas (con la lista de bloques) y no deben heredarse.
        if hasattr(self, "split_revision"):
            tamanos = self.split_revision.sizes()
            # Con los totales ocultos su columna mide 0: se guarda el ancho
            # que tenían y las otras dos, en proporción, sin ese sitio.
            if len(tamanos) == 3 and tamanos[2] == 0:
                ancho = self._tamanos_divisor(
                    "split_revision_v4", TAMANOS_COLUMNAS)[2]
                resto = tamanos[0] + tamanos[1]
                if resto > 2 * ancho:
                    escala = (resto - ancho) / resto
                    tamanos = [round(tamanos[0] * escala),
                               round(tamanos[1] * escala), ancho]
                else:
                    tamanos[2] = ancho
            ajustes.guardar("split_revision_v4", tamanos)
        if hasattr(self, "split_factura"):
            ajustes.guardar("split_factura", self.split_factura.sizes())

    def showEvent(self, evento):
        super().showEvent(evento)
        if sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        # Mantiene el acabado claro incluso si Windows usa modo oscuro.
        try:
            import ctypes
            valor = ctypes.c_int(0)
            for atributo in (20, 19):
                resultado = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    int(self.winId()), atributo, ctypes.byref(valor),
                    ctypes.sizeof(valor))
                if resultado == 0:
                    break
            # DWM recibe COLORREF (0x00BBGGRR).
            # Barra de título oscura de la suite (#1F3550), la misma que usa
            # Generador de avisos con su titleBarOverlay.
            for atributo, tono in ((35, CHROME), (36, CHROME_INK), (34, CHROME)):
                qcolor = QColor(tono)
                valor_color = ctypes.c_uint(
                    qcolor.red() | (qcolor.green() << 8) | (qcolor.blue() << 16))
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
        escaneos.addSeparator()
        escaneos.addAction("Recoger facturas sueltas del Escritorio y Descargas…",
                           self._recoger_sueltos)
        escaneos.addAction("Deshacer la última recogida", self._deshacer_recogida)
        escaneos.addAction("Expedientes por cliente y ejercicio…",
                           self._ver_expedientes)
        escaneos.addAction("Registro de facturas…", self._ver_registro_facturas)

        comprobar = self.menuBar().addMenu("Comprobar")
        self.btn_registro = comprobar.addAction(
            "Comprobar registro de Aplifisa…\tCtrl+R",
            lambda: self._contrastar_registro())
        self.btn_registro.setEnabled(False)
        # Ya no hay «Apartar para gestión manual»: lo dudoso queda en ámbar y
        # se exporta tras «Marcar revisada» (las apartadas no se registraban).
        self.accion_olvidar_exportacion = comprobar.addAction(
            "Olvidar que la selección ya se exportó…",
            self._olvidar_exportacion)
        self.accion_olvidar_exportacion.setToolTip(
            "Si Aplifisa rechazó el Excel, quita esas facturas del historial "
            "de exportadas para poder exportarlas otra vez sin aviso.")

        ver = self.menuBar().addMenu("Ver")
        self.accion_resumen = ver.addAction("Comprobación de totales del lote")
        self.accion_resumen.setCheckable(True)
        self.accion_resumen.setChecked(bool(ajustes.leer("ver_totales_lado", True)))
        self.accion_resumen.toggled.connect(self._ver_resumen)
        self.accion_detalle_bloques = ver.addAction("Desglosar totales por escaneo")
        self.accion_detalle_bloques.setCheckable(True)
        self.accion_detalle_bloques.toggled.connect(self._pintar_resumen)
        # Recargo y retenciones se ven solo cuando tocan a este cliente o a
        # este lote; con esto se ven siempre todas.
        self.accion_todas_columnas = ver.addAction("Ver todas las columnas")
        self.accion_todas_columnas.setCheckable(True)
        self.accion_todas_columnas.setChecked(
            bool(ajustes.leer("ver_todas_columnas", False)))
        self.accion_todas_columnas.toggled.connect(self._ver_todas_columnas)
        config =self.menuBar().addMenu("Configuración")
        config.addAction("API key de Gemini…", self._configurar_key)
        config.addAction("Tope de gasto al mes…", self._configurar_tope)
        config.addAction("Carpeta de documentación digitalizada…",
                         self._configurar_carpeta_escaneos)
        config.addAction("Modelos de lectura y doble lectura…",
                         self._configurar_modelos)
        config.addAction("Examen de precisión de la lectura…",
                         self._examen_precision)
        config.addAction("Calidad de lectura y coste…", self._configurar_calidad)
        config.addAction("Textos de conceptos para Aplifisa…", self._configurar_textos)

        menu = self.menuBar().addMenu("Ayuda")
        menu.addAction("Buscar actualizaciones",
                       lambda: self._comprobar_actualizaciones(silencioso=False))
        menu.addAction("Pedir revisión del modelo Gemini",
                       self._preparar_revision_gemini)
        menu.addAction("Novedades de esta versión…",
                       lambda: self._mostrar_notas_version(forzar=True))
        menu.addAction("Diagnóstico y sugerencias…",
                       lambda: self._mostrar_pendientes(al_arrancar=False))
        menu.addAction("Examen de precisión de la lectura…", self._examen_precision)
        menu.addAction("Abrir carpeta de ejemplos para revisión", self._abrir_muestras)
        menu.addAction("Preparar ZIP de ejemplos para revisión…", self._exportar_muestras)
        menu.addAction("Acerca de", self._acerca_de)

        crear_cinta(self)

    def _avisar(self, texto: str, tipo: str = INFO, deshacer=None,
                segundos: int = 10) -> None:
        """Aviso dentro de la ventana, sin bloquear (ver banda_avisos)."""
        if hasattr(self, "banda"):
            self.banda.mostrar(texto, tipo, deshacer=deshacer, segundos=segundos)

    def _mostrar_notas_version_al_arrancar(self):
        self._mostrar_notas_version(forzar=False)

    def _preparar_revision_gemini(self):
        """Deja una orden lista para pegar en Codex, sin cambios automáticos."""
        try:
            texto, ruta = revision_gemini.guardar_solicitud(__version__)
            QApplication.clipboard().setText(texto)
        except OSError as error:
            QMessageBox.warning(
                self, "Revisar Gemini",
                f"No se pudo preparar la solicitud:\n{error}")
            return
        QMessageBox.information(
            self, "Revisar Gemini",
            f"Modelo principal actual: <b>{revision_gemini.modelo_principal()}</b>"
            "<br><br>La orden de revisión se ha copiado al portapapeles. "
            "Abra Codex y péguela en una tarea: comprobará disponibilidad, "
            "retirada, precio y modelos estables, sin cambiar a uno que reduzca "
            "la calidad.<br><br>También se ha guardado en:<br>"
            f"<small>{ruta}</small>")

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

    def _avisar_error_muestras(self, error):
        mensaje = str(error)
        if mensaje != self._error_muestras:
            QMessageBox.warning(
                self, "No se ha guardado el ejemplo para revisión",
                "El trabajo con las facturas puede continuar, pero no se ha podido "
                "conservar una muestra local:\n\n" + mensaje
                + "\n\nCompruebe el espacio disponible y la carpeta de ejemplos.")
        self._error_muestras = mensaje

    def _capturar_original(self, ruta):
        try:
            return muestras_revision.guardar_original(ruta)
        except (OSError, ValueError) as error:
            self._avisar_error_muestras(error)
            return None

    def _guardar_muestra_revision(self):
        self._timer_muestras.stop()
        try:
            filas = [{**registro, "factura": self._leer_fila(i),
                      "tipo": self._tipo_fila(i)}
                     for i, registro in enumerate(self.filas)]
            filas += [{**borrada["registro"], "tipo": borrada["tipo"]}
                      for borrada in self._ultimo_borrado]
            muestras_revision.guardar_revision(filas)
            return True
        except (OSError, ValueError) as error:
            self._avisar_error_muestras(error)
            return False

    def _abrir_muestras(self):
        try:
            archivo.abrir(str(muestras_revision.carpeta()))
        except OSError as error:
            self._avisar_error_muestras(error)

    def _exportar_muestras(self):
        self._revalidar_todo()
        if not self._guardar_muestra_revision():
            return
        destino, _ = QFileDialog.getSaveFileName(
            self, "Guardar ejemplos para adjuntar a la revisión",
            "Ejemplos-Facturas-Aplifisa.zip", "Archivo ZIP (*.zip)")
        if not destino:
            return
        if not destino.lower().endswith(".zip"):
            destino += ".zip"
        try:
            muestras_revision.exportar_zip(destino)
        except (OSError, ValueError) as error:
            self._avisar_error_muestras(error)
            return
        QMessageBox.information(
            self, "Ejemplos preparados",
            "ZIP guardado en:\n" + destino
            + "\n\nIncluye los originales guardados, sus lecturas y las revisiones. "
            "Adjunte este ZIP en la conversación para revisar casos reales. "
            "No se ha enviado automáticamente.")

    def _guardar_sesion(self) -> None:
        """Conserva lote, correcciones, imágenes y bloques para la próxima vez."""
        if not self._bloques and not self.filas:
            sesion.borrar()
            return
        self._guardar_muestra_revision()
        filas = [{
            "png": registro.png, "factura": registro.factura,
            "aviso": registro.aviso or "", "bloque": registro.bloque or "",
            "fuentes": registro.fuentes, "tipo": registro.tipo,
            "cuenta": registro.factura.concepto or "",
            "gxx": registro.factura.subclave or "",
        } for registro in self.filas]
        sesion.guardar({
            "bloques": self._bloques,
            "filas": filas,
            "cliente_nif": getattr(self, "_cliente_nif", ""),
            "cliente_nombre": getattr(self, "_cliente_nombre", ""),
            "hay_recargo": getattr(self, "_hay_recargo", False),
            "regimen_recargo": self.combo_recargo.currentData(),
            "periodo_modo": getattr(self, "_periodo_manual_valor", "auto"),
            "localizaciones": {clave: localizar.a_guardar(cajas) for clave, cajas
                               in self._localizaciones.items()},
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
            self._periodo_manual_valor = datos.get("periodo_modo", "auto")
            self._localizaciones = {
                clave: localizar.de_guardado(cajas)
                for clave, cajas in (datos.get("localizaciones") or {}).items()}
            self.fila_recargo.setVisible(self._hay_recargo)
            self.chk_hay_recargo.setChecked(self._hay_recargo)
            regimen = datos.get("regimen_recargo", DESGLOSE)
            indice = self.combo_recargo.findData(regimen)
            self.combo_recargo.blockSignals(True)
            self.combo_recargo.setCurrentIndex(max(0, indice))
            self.combo_recargo.blockSignals(False)
            self._actualizar_combo_bloques()
            self._reparar_abonos_emitidos_guardados(datos.get("filas", []))
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

    @staticmethod
    def _numero_guardado(valor) -> str:
        return "".join(c for c in str(valor or "") if c.isalnum()).upper()

    def _reparar_abonos_emitidos_guardados(self, filas_guardadas) -> None:
        """Deshace la conversión errónea a gasto de la versión 1.13.14.

        Solo actúa con prueba fuerte: total negativo y NIF del cliente como
        emisor en los datos originales. Las elecciones sin esa prueba no se
        tocan.
        """
        cliente_nif = normaliza_nif(getattr(self, "_cliente_nif", ""))
        if not cliente_nif:
            return
        bloques = {b.get("nombre", ""): b for b in self._bloques}
        for fila in filas_guardadas:
            factura = fila.get("factura")
            if not factura or factura.total_impreso is None \
                    or factura.total_impreso >= 0:
                continue
            bloque = bloques.get(fila.get("bloque", ""), {})
            numero = self._numero_guardado(factura.num_factura)
            datos = next((registro[-1] for registro in bloque.get("crudos", [])
                          if registro and isinstance(registro[-1], dict)
                          and self._numero_guardado(
                              registro[-1].get("num_factura")) == numero), None)
            if not datos or normaliza_nif(datos.get("emisor_nif")) != cliente_nif \
                    or normaliza_nif(datos.get("receptor_nif")) == cliente_nif:
                continue
            correcta = construir(datos, cliente_nif,
                                 getattr(self, "_cliente_nombre", ""))
            if correcta.tipo != "venta":
                continue
            fila["tipo"], fila["cuenta"], fila["gxx"] = (
                "venta", correcta.cuenta, correcta.gxx)
            factura.tipo_revision = "venta"
            factura.concepto, factura.subclave = correcta.cuenta, correcta.gxx
            for fuente in fila.get("fuentes", []):
                fuente.tipo_revision = "venta"
                fuente.concepto, fuente.subclave = correcta.cuenta, correcta.gxx
            for _png, pr in bloque.get("procesadas", []):
                if not pr.facturas or self._numero_guardado(
                        pr.facturas[0].num_factura) != numero:
                    continue
                pr.tipo, pr.cuenta, pr.gxx = "venta", correcta.cuenta, correcta.gxx
                for linea in pr.facturas:
                    linea.tipo_revision = "venta"
                    linea.concepto, linea.subclave = correcta.cuenta, correcta.gxx

    def closeEvent(self, ev):
        # Lo que se estaba señalando en el documento no hace falta ya.
        if getattr(self, "_hilo_localizar", None):
            self._hilo_localizar.cancelar()
        # No destruir QThreads vivos (abortaria el proceso)
        self.esperar_hilos()
        try:
            self._guardar_divisores()
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
            self._avisar("API key guardada de forma segura.", EXITO)

    def _configurar_modelos(self):
        dialogo = DialogoModelos(self)
        if dialogo.exec() == QDialog.Accepted:
            self._avisar(dialogo.guardar(), EXITO)
            self._pintar_gasto()

    def _examen_precision(self):
        from facturas_excel.dialogo_examen import DialogoExamen
        DialogoExamen(leer_api_key() or "", self).exec()
        self._pintar_gasto()

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

    def _ver_resumen(self, visible: bool):
        """Los totales son un punto de control: si estorban, se quitan."""
        ajustes.guardar("ver_totales_lado", bool(visible))
        if hasattr(self, "lado_card"):
            if visible and not self.lado_card.isVisible():
                # Antes de enseñarla, los filtros ya para la tabla más
                # estrecha: en una sola fila, su mínimo no dejaría estrecharla
                # y el sitio saldría de la factura.
                ancho = self._tamanos_divisor(
                    "split_revision_v4", TAMANOS_COLUMNAS)[2]
                self._distribuir_herramientas(
                    self.tabla.parentWidget().width() - max(ancho, 250))
            # QSplitter recuerda el ancho de la columna oculta y lo devuelve.
            self.lado_card.setVisible(bool(visible))
            if not hasattr(self, "_timer_tras_resumen"):
                self._timer_tras_resumen = QTimer(self)
                self._timer_tras_resumen.setSingleShot(True)
                self._timer_tras_resumen.timeout.connect(self._tras_ver_resumen)
            self._timer_tras_resumen.start(0)
        if hasattr(self, "accion_resumen") and self.accion_resumen.isChecked() != visible:
            self.accion_resumen.setChecked(bool(visible))

    def _tras_ver_resumen(self) -> None:
        """Ya colocadas las columnas: totales legibles y filtros recolocados."""
        tamanos = self.split_revision.sizes()
        if self.lado_card.isVisible() and len(tamanos) == 3 and tamanos[2] < 200:
            tamanos[0] = max(400, tamanos[0] - (300 - tamanos[2]))
            tamanos[2] = 300
            self.split_revision.setSizes(tamanos)
        self._distribuir_herramientas(self.width())

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
    def _pintar_cliente(self):
        """Cliente del lote. Si hay bloques de varios, se dice claramente."""
        nifs = {b["nif"] for b in self._bloques if b["nif"]}
        if len(nifs) > 1:
            self._poner_cliente(f"⚠ VARIOS CLIENTES en el lote ({len(nifs)})")
            return
        self._poner_cliente(
            f"{self._cliente_nombre or 'Cliente no identificado'}"
            + (f"  ·  {self._cliente_nif}" if self._cliente_nif else ""))

    def _poner_cliente(self, texto: str) -> None:
        """El cliente en la cinta, con el texto entero en el globo (en una
        ventana estrecha el nombre se recorta)."""
        self.lbl_cliente.setText(texto)
        self.lbl_cliente.setToolTip(texto)
        # La caja del cliente rehace ya su tamaño (si no, la cinta mediría
        # con el del texto anterior): un nombre más largo puede pedir pasar
        # los ocasionales a icono.
        self.lbl_cliente.parentWidget().layout().activate()
        self._actualizar_barra_responsiva(self.width())

    def _actualizar_selector_periodo(self) -> None:
        """Propone trimestre/anual y conserva cualquier elección manual."""
        facturas = [self._leer_fila(r) for r in range(self.tabla.rowCount())]
        automatico = detectar_periodo(facturas)
        ejercicio = automatico.ejercicio
        actual = getattr(self, "_periodo_manual_valor", "auto")
        self.combo_periodo.blockSignals(True)
        self.combo_periodo.clear()
        self.combo_periodo.addItem(
            f"Automático: {automatico.etiqueta}", "auto")
        if ejercicio is not None:
            for trimestre in range(1, 5):
                self.combo_periodo.addItem(
                    f"{trimestre}T {ejercicio}", str(trimestre))
            self.combo_periodo.addItem(f"Anual {ejercicio}", "anual")
        indice = self.combo_periodo.findData(actual)
        if indice < 0:
            actual, indice = "auto", 0
        self.combo_periodo.setCurrentIndex(indice)
        self.combo_periodo.blockSignals(False)
        self._periodo_manual_valor = actual
        self._periodo_lote = (
            automatico if actual == "auto" or ejercicio is None
            else periodo_manual(ejercicio, actual)
        )

    def _on_periodo(self) -> None:
        self._periodo_manual_valor = self.combo_periodo.currentData() or "auto"
        self._revalidar_todo()

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
            self._avisar("Para quitar un bloque, elíjalo primero en el "
                         "desplegable «Todos los bloques».", AVISO)
            return
        # Sin «¿Seguro?»: se quita y se ofrece deshacerlo en la banda.
        quitados = [(i, b) for i, b in enumerate(self._bloques)
                    if b["nombre"] == nombre]
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

        def deshacer():
            for indice, bloque in quitados:
                self._bloques.insert(min(indice, len(self._bloques)), bloque)
            self._actualizar_combo_bloques()
            self._rellenar_tabla()
            self._revalidar_todo()
            hay = self.tabla.rowCount() > 0
            self.btn_gastos.setEnabled(hay)
            self.btn_registro.setEnabled(hay)
            self._avisar(f"Bloque «{nombre}» recuperado.", EXITO)
        self._avisar(f"Bloque «{nombre}» quitado del lote.", INFO,
                     deshacer=deshacer)

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
        self._guardar_muestra_revision()
        self._bloques = []
        self._cola = []
        self._decisiones_conflicto_nif = {}
        self._localizaciones = {}
        self._ultimo_borrado = []
        self._rutas_actuales = []
        self._duplicados = {}
        self._escaneo_reciente = False
        self._escaneo_sin_identificar = False
        self._cliente_nif = self._cliente_nombre = ""
        self._periodo_manual_valor = "auto"
        self._periodo_lote = PeriodoLote()
        self.txt_buscar.clear()
        self._invalidar_contraste_registro()
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
        self._poner_cliente("Pendiente de detectar")
        self.lbl_estado.setText("Lote vacío. Cargue o escanee facturas para empezar.")
        sesion.borrar()

    def _por_el_total(self) -> bool:
        """El cliente registra sus compras con recargo por el total factura."""
        return (getattr(self, "_hay_recargo", False)
                and self.combo_recargo.currentData() == TOTAL)

    def _rellenar_tabla(self):
        self._invalidar_contraste_registro()
        filas = filas_de_bloques(
            self._bloques, self._por_el_total(), a_total_factura)
        self._conservar_resumenes_corregidos(filas)
        self._poner_filas(filas)

    def _conservar_resumenes_corregidos(self, filas) -> None:
        """Recargo «por el total»: la línea a la vista es una copia que se
        rehace desde sus líneas originales (`fuentes`) cada vez que se monta
        la tabla (otro taco, quitar un bloque, unir hojas…). Si una persona
        corrigió un importe en ella, se conserva su corrección en vez de
        volver en silencio a lo que leyó la IA."""
        def clave(fila):
            return tuple(id(x) for x in fila.fuentes)

        def es_copia(fila):
            return bool(fila.fuentes) and not any(
                x is fila.factura for x in fila.fuentes)

        antes = {}
        for fila in self.filas:
            if es_copia(fila):
                antes.setdefault(clave(fila), []).append(fila.factura)
        ahora = {}
        for fila in filas:
            if es_copia(fila):
                ahora.setdefault(clave(fila), []).append(fila)
        for k, grupo in ahora.items():
            previas = antes.get(k)
            if previas and len(previas) == len(grupo) and any(
                    f.edicion_manual for f in previas):
                for fila, factura in zip(grupo, previas):
                    fila.factura = factura

    def _poner_filas(self, filas) -> None:
        """Sustituye las filas del lote y las pinta de nuevo."""
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(0)
        self.filas = []
        for fila in filas:
            self._insertar_fila(fila)
        self.tabla.blockSignals(False)

    def _insertar_fila(self, fila: Fila, posicion: int | None = None) -> None:
        r = len(self.filas) if posicion is None else posicion
        self.filas.insert(r, fila)
        self.tabla.insertar(r, fila, self._on_tipo_cambiado)
        self._actualizar_columnas()

    def _on_recargo(self):
        """Cambiar el régimen rehace la tabla: cambia como se registra el gasto."""
        guardar_regimen_recargo(getattr(self, "_cliente_nif", ""),
                                self.combo_recargo.currentData(),
                                getattr(self, "_cliente_nombre", ""))
        self._perfil_columnas = (None,)
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
            self._perfil_columnas = (None,)
        self.combo_recargo.blockSignals(True)
        self.combo_recargo.setCurrentIndex(
            max(0, self.combo_recargo.findData(guardado or DESGLOSE)))
        self.combo_recargo.blockSignals(False)

    def _anadir_fila(self, png, f: Factura, tipo, cuenta, gxx, aviso, bloque="",
                     fuentes=None):
        """Añade una línea al final (sesiones guardadas, deshacer, pruebas)."""
        f.concepto = cuenta if cuenta not in ("", None) else None
        f.subclave = gxx or None
        self._insertar_fila(Fila(png, f, f.tipo_revision or tipo, aviso or "",
                                 bloque or "", list(fuentes or [f])))

    # ---------- edicion / validacion ----------
    def _invalidar_revision_documento(self, fila):
        """Un cambio que no hizo la persona en ESTA factura (se propagó
        desde otra): vuelve a estar pendiente de revisar."""
        self._marcar_documento(fila, corregida=False)

    def _marcar_corregida_documento(self, fila):
        """La persona ha corregido un dato: la factura entera (todas sus
        líneas) pasa a «✎ Corregida» y cuenta como revisada."""
        self._marcar_documento(fila, corregida=True)

    def _marcar_documento(self, fila, corregida: bool,
                          incluir_fuentes: bool = True):
        clave = clave_documento(self.filas[fila]["factura"])
        filas_doc = [r for r in self.filas
                     if clave_documento(r["factura"]) == clave]
        # Lo que la persona tenía delante al corregir: solo eso se da por
        # visto (los avisos de la última revisión de sus líneas).
        vistos = tuple(sorted({
            str(m) for r in filas_doc for m in (r.get("mensajes") or [])
            if str(m) not in MENSAJES_DE_ESTADO})) if corregida else ()
        for registro in filas_doc:
            facturas = [registro["factura"]]
            if incluir_fuentes:
                facturas += registro.get("fuentes", [])
            for factura in facturas:
                factura.revision_confirmada = False
                factura.revision_corregida = corregida
                factura.avisos_vistos = vistos
                factura.edicion_manual = True

    def _on_celda(self, item):
        """Lo que se corrige a mano se guarda para ese proveedor.

        Si no, habria que volver a corregir lo mismo en cada lote: el nombre
        con el que se le llama, su NIF y la cuenta que le toca.
        """
        self._invalidar_contraste_registro()
        columna = item.column()
        cambiado = False
        a_las_fuentes = True
        if item.row() < len(self.filas):
            # Lo escrito pasa a la factura en el momento: la tabla solo enseña.
            campo, valor = valor_de_celda(columna, item.text())
            if campo:
                registro = self.filas[item.row()]
                factura = registro.factura
                cambiado = getattr(factura, campo, None) != valor
                setattr(factura, campo, valor)
                fuentes = registro.get("fuentes") or []
                if not any(x is factura for x in fuentes):
                    # Recargo «por el total»: la línea a la vista es un
                    # resumen y se rehace desde sus líneas originales. Los
                    # datos de la cabecera pasan a ellas; un importe no
                    # (no hay a qué línea ponerlo), y la marca tampoco.
                    if campo in CAMPOS_CABECERA:
                        for fuente in fuentes:
                            setattr(fuente, campo, valor)
                    else:
                        a_las_fuentes = False
        if columna == C_NIF:
            aviso = self._nif_escrito_a_mano(item.row())
        elif columna == C_NOMBRE:
            aviso = self._nombre_escrito_a_mano(item.row())
        elif columna in (C_CUENTA, C_GXX):
            aviso = self._cuenta_escrita_a_mano(item.row())
        else:
            aviso = ""
        # Al final, después de copiar el dato a otras facturas (eso las deja
        # pendientes): ESTA queda «Corregida», que cuenta como revisada. Si
        # se escribe lo mismo que había, no cambia nada.
        if cambiado and item.row() < len(self.filas):
            self._marcar_documento(item.row(), corregida=True,
                                   incluir_fuentes=a_las_fuentes)
        self._revalidar_todo()
        if aviso:
            self.lbl_estado.setText(aviso)  # despues: _resumen pisa la barra

    def _on_tipo_cambiado(self, control) -> None:
        self._invalidar_contraste_registro()
        fila = self._fila_del_control_tipo(control)
        if 0 <= fila < len(self.filas):
            self._marcar_corregida_documento(fila)
            self.filas[fila].tipo = control.currentData()
            self.filas[fila]["factura"].tipo_revision = control.currentData()
            for fuente in self.filas[fila].get("fuentes", []):
                fuente.tipo_revision = control.currentData()
            if self._por_el_total():
                # En recargo «por el total» solo los gastos van resumidos: al
                # cambiar el tipo, la línea se rehace desde las originales
                # (una venta recupera su IVA; un gasto se resume).
                self._rellenar_tabla()
        self._revalidar_todo()

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
        if r >= len(self.filas):
            return ""
        # La cuenta la ha puesto una persona: sobra el aviso de «cuenta
        # propuesta» en todas las líneas de esa factura.
        clave = clave_documento(self.filas[r]["factura"])
        for registro in self.filas:
            if clave_documento(registro["factura"]) == clave:
                registro["aviso"] = quitar_aviso_cuenta(registro["aviso"])
        if self._tipo_fila(r) != "gasto":
            return ""
        f = self._leer_fila(r)
        cuenta = (f.concepto or "").strip()
        gxx = (f.subclave or "").strip().upper() or None
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
        campo = CAMPO_DE_COLUMNA[columna]
        puestas = 0
        for otra, registro in enumerate(self.filas):
            if otra == r or normaliza_nif(registro.factura.nif) != nif:
                continue
            if getattr(registro.factura, campo) != valor:
                self._invalidar_revision_documento(otra)
                setattr(registro.factura, campo, valor)
                self.tabla.pintar(otra, registro, (columna,))
                puestas += 1
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
        for otra, registro in enumerate(self.filas):
            if otra == r:
                continue
            g = registro.factura
            if clave_proveedor(g.nombre) != clave or validar_nif(normaliza_nif(g.nif)):
                continue
            self._invalidar_revision_documento(otra)
            g.nif = nif
            self.tabla.pintar(otra, registro, (C_NIF,))
            registro.aviso = (
                f"{registro.aviso} NIF puesto a mano ({nif}) desde "
                f"otra factura de {f.nombre}.").strip()
            aplicadas.append(otra + 1)
        aviso = f"NIF {nif} guardado para {f.nombre}: ya no habrá que escribirlo más."
        if aplicadas:
            aviso += ("  Puesto también en la línea "
                      + ", ".join(str(n) for n in aplicadas) + ".")
        return aviso

    def _leer_fila(self, r):
        """La factura de la fila (lo que vale es la factura, no la celda)."""
        return self.filas[r].factura

    def _ordenar_tabla_por(self, columna: int) -> None:
        """Ordena el lote por una columna; las filas se mueven con su factura."""
        if self.tabla.rowCount() < 2 or columna == C_BLOQUE:
            return
        self._invalidar_contraste_registro()
        if self._columna_orden == columna:
            ascendente = not self._orden_ascendente
        else:
            # En retenciones interesa ver primero las facturas que sí tienen.
            ascendente = columna not in COLUMNAS_IRPF
        self._columna_orden = columna
        self._orden_ascendente = ascendente
        campo = {C_ESTADO: "estado", C_TIPO: "tipo"}.get(
            columna, CAMPO_DE_COLUMNA.get(columna, "num_factura"))
        self._poner_filas(ordenar_filas(self.filas, campo, ascendente))
        orden_qt = (Qt.AscendingOrder if ascendente else Qt.DescendingOrder)
        self.tabla.horizontalHeader().setSortIndicator(columna, orden_qt)
        self.tabla.horizontalHeader().setSortIndicatorShown(True)
        self._revalidar_todo()
        if self.tabla.rowCount():
            self.tabla.selectRow(0)

    def _tipo_fila(self, r):
        return self.filas[r].tipo if 0 <= r < len(self.filas) else "gasto"

    def _fila_del_control_tipo(self, control) -> int:
        """Localiza la fila actual del desplegable incluso después de borrar filas."""
        return self.tabla.fila_del_combo(control)

    def _aplicar_filtro(self) -> None:
        opcion = self.combo_filtro_estado.currentIndex()
        bloque = self.combo_filtro_bloque.currentText()
        busqueda = self.txt_buscar.text()
        filtro_registro = self.combo_filtro_registro.currentData() or "todas"
        tipo = self.grupo_tipo.checkedButton().property("tipoFiltro")
        self.txt_buscar.setPlaceholderText({
            "gasto": "Proveedor, NIF, nº de factura o importe…",
            "venta": "Cliente, NIF, nº de factura o importe…",
            "todos": "Proveedor o cliente, NIF, nº de factura o importe…",
        }[tipo])
        for fila in range(self.tabla.rowCount()):
            estado = self.filas[fila].presentacion
            visible = (
                opcion == 0
                or (opcion == 1 and estado == POR_REVISAR)
                or (opcion == 2 and estado == CON_ERROR)
                or (opcion == 3 and estado in {VERIFICADA, SIN_VERIFICAR,
                                               REVISADA, CORREGIDA})
                or (opcion == 4 and self._periodo_lote.es_trimestre
                    and not self._periodo_lote.contiene(self.filas[fila]["factura"]))
            )
            if tipo != "todos" and self._tipo_fila(fila) != tipo:
                visible = False
            if bloque != TODOS_LOS_BLOQUES and self.filas[fila]["bloque"] != bloque:
                visible = False
            if visible and not coincide_busqueda(self._leer_fila(fila), busqueda):
                visible = False
            if visible and filtro_registro != "todas":
                estado_registro = self.filas[fila].get("registro_estado")
                if filtro_registro == "diferencias":
                    visible = estado_registro in {
                        "sin_registrar", "distinta", "dudosa"}
                elif estado_registro != filtro_registro:
                    visible = False
            self.tabla.setRowHidden(fila, not visible)
        visibles = [self.filas[r]["factura"] for r in range(self.tabla.rowCount())
                    if not self.tabla.isRowHidden(r)]
        self.lbl_resultados.setText(
            f"{facturas_unicas(visibles)} facturas · {len(visibles)} líneas visibles")
        if self.tabla.currentRow() >= 0 and self.tabla.isRowHidden(self.tabla.currentRow()):
            self.tabla.clearSelection()
        if not self.tabla.selectionModel().selectedRows():
            primera = next((r for r in range(self.tabla.rowCount())
                            if not self.tabla.isRowHidden(r)), None)
            if primera is not None:
                self.tabla.selectRow(primera)
            else:
                self._limpiar_visor()
        self._pintar_resumen()

    def _hay_filtro_activo(self) -> bool:
        return bool(
            self.combo_filtro_estado.currentIndex()
            or not self.botones_tipo["todos"].isChecked()
            or self.combo_filtro_bloque.currentText() != TODOS_LOS_BLOQUES
            or self.txt_buscar.text().strip()
            or (self.combo_filtro_registro.isVisible()
                and self.combo_filtro_registro.currentData() != "todas")
        )

    def _siguiente_incidencia(self) -> None:
        total = self.tabla.rowCount()
        if not total:
            return
        inicio = self.tabla.currentRow()
        for salto in range(1, total + 1):
            fila = (inicio + salto) % total
            # Lo revisado y lo corregido a mano ya no son incidencias.
            if self.filas[fila].presentacion in PENDIENTES:
                # Una búsqueda no debe esconder la incidencia que se visita.
                self._limpiar_filtros()
                self.tabla.selectRow(fila)
                self.tabla.scrollToItem(self.tabla.item(fila, C_ESTADO))
                return
        self.lbl_estado.setText("Todo el lote está correcto y listo para exportar.")

    def _limpiar_filtros(self):
        for control in (self.txt_buscar, self.combo_filtro_estado,
                        self.combo_filtro_bloque, self.combo_filtro_registro):
            control.blockSignals(True)
        self.txt_buscar.clear()
        self.combo_filtro_estado.setCurrentIndex(0)
        self.combo_filtro_bloque.setCurrentIndex(0)
        self.combo_filtro_registro.setCurrentIndex(0)
        self.botones_tipo["todos"].setChecked(True)
        for control in (self.txt_buscar, self.combo_filtro_estado,
                        self.combo_filtro_bloque, self.combo_filtro_registro):
            control.blockSignals(False)
        self._aplicar_filtro()

    def _filas_seleccionadas(self) -> list[int]:
        return sorted({i.row() for i in self.tabla.selectionModel().selectedRows()})

    def _marcar_revisada(self) -> None:
        """Da salida únicamente a avisos ámbar comprobados por una persona.

        Se revisa la factura, no la línea: una factura con suplido o con
        varios tipos de IVA tiene varias líneas y basta con pulsar una.
        """
        seleccionadas = self._filas_seleccionadas()
        if not seleccionadas:
            self._avisar("Seleccione una o varias filas ámbar.", AVISO)
            return
        filas = sorted({r for fila in seleccionadas
                        for r in self._filas_del_documento(fila)})
        confirmadas = []
        for fila in filas:
            registro = self.filas[fila]
            f = self._leer_fila(fila)
            if registro.get("estado") == REVISAR and not f.revision_confirmada \
                    and registro.presentacion != CORREGIDA:
                f.revision_confirmada = True
                confirmadas.append(f)
        ya_corregidas = any(self.filas[fila].presentacion == CORREGIDA
                            for fila in filas)
        self._revalidar_todo()
        if confirmadas:
            texto = (f"{len(confirmadas)} línea(s) revisada(s): ya pueden "
                     "exportarse.")
            self.lbl_estado.setText(texto)

            def deshacer():
                for factura in confirmadas:
                    factura.revision_confirmada = False
                self._revalidar_todo()
                self._avisar("Revisión deshecha: vuelven a estar pendientes.",
                             INFO)
            self._avisar(texto, EXITO, deshacer=deshacer)
        elif ya_corregidas:
            self._avisar("Ya cuenta como revisada (corregida a mano): puede "
                         "exportarse.", INFO)
        else:
            self._avisar(
                "Solo se pueden confirmar avisos ámbar. Los errores rojos se "
                "corrigen en la tabla.", AVISO)

    def _eliminar_seleccion(self) -> None:
        filas = sorted({i.row() for i in self.tabla.selectionModel().selectedRows()},
                       reverse=True)
        if not filas:
            self._avisar("Seleccione una o varias filas completas para "
                         "eliminarlas.", AVISO)
            return
        self._guardar_muestra_revision()
        self._invalidar_contraste_registro()
        self._ultimo_borrado = []
        for fila in filas:
            registro = self.filas[fila]
            for fuente in registro.get("fuentes", [registro["factura"]]):
                fuente.eliminada = True
            self._ultimo_borrado.append({
                "registro": registro, "tipo": registro.tipo, "posicion": fila})
            self.tabla.removeRow(fila)
            self.filas.pop(fila)
        self._ultimo_borrado.reverse()
        self.btn_deshacer_borrado.setEnabled(True)
        self.btn_deshacer_borrado.setVisible(True)
        self._distribuir_herramientas(self.width())
        self._revalidar_todo()
        self._aplicar_filtro()
        self.lbl_estado.setText(
            f"{len(filas)} línea(s) eliminada(s). Puede deshacer la operación.")
        self._avisar(f"{len(filas)} línea(s) eliminada(s) del lote.", INFO,
                     deshacer=self._deshacer_borrado)

    def _deshacer_borrado(self) -> None:
        if not self._ultimo_borrado:
            return
        self._invalidar_contraste_registro()
        for borrada in self._ultimo_borrado:
            registro = borrada["registro"]
            for fuente in registro.get("fuentes", [registro["factura"]]):
                fuente.eliminada = False
            # Vuelve a su sitio, no al final del lote.
            self._insertar_fila(registro, min(borrada.get("posicion", len(self.filas)),
                                              len(self.filas)))
        cantidad = len(self._ultimo_borrado)
        self._ultimo_borrado = []
        self.btn_deshacer_borrado.setEnabled(False)
        self.btn_deshacer_borrado.setVisible(False)
        self._distribuir_herramientas(self.width())
        self._revalidar_todo()
        self._aplicar_filtro()
        self.lbl_estado.setText(f"{cantidad} línea(s) restaurada(s).")
        self._avisar(f"{cantidad} línea(s) restaurada(s).", EXITO)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        ancho = event.size().width()
        self._actualizar_barra_responsiva(ancho)
        self._distribuir_herramientas(ancho)
        if self.tabla.currentRow() >= 0:
            self._mostrar_miniatura()

    # ---------- exportar ----------


def _argumentos(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--import", dest="importar", nargs="+")
    args, _ = parser.parse_known_args(argv[1:])
    return args


FICHERO_ERRORES = errores.FICHERO


def _aviso_de_error(tipo, valor, rastro) -> None:
    """Ningún fallo pasa en silencio.

    En el .exe no hay consola: un error inesperado (al exportar, por ejemplo)
    no enseñaba nada y parecía que el botón no hacía caso. Ahora se apunta en
    errores.log, en la carpeta de datos, y se avisa con un mensaje.
    """
    if issubclass(tipo, KeyboardInterrupt):
        sys.__excepthook__(tipo, valor, rastro)
        return
    errores.apuntar("".join(traceback.format_exception(tipo, valor, rastro)))
    try:
        sys.__excepthook__(tipo, valor, rastro)
    except Exception:
        pass                     # sin consola (el .exe) no hay dónde escribir
    app = QApplication.instance()
    # Solo desde el hilo de la ventana: una ventana abierta desde un hilo de
    # lectura tumbaría el programa. Allí basta con dejarlo apuntado.
    if app is not None and QThread.currentThread() is app.thread():
        try:
            QMessageBox.critical(
                None, "Algo ha fallado",
                f"No se ha podido terminar lo que estaba haciendo:\n\n{valor}"
                f"\n\nEl detalle queda apuntado en {FICHERO_ERRORES}, en la "
                "carpeta de datos del programa (%APPDATA%\\FacturasAplifisa). "
                "Lo que ya estaba hecho no se ha perdido.")
        except Exception:
            pass


def main():
    args = _argumentos(sys.argv)
    sys.excepthook = _aviso_de_error
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
