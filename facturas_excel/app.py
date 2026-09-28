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

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QProgressDialog, QScrollArea,
    QSizePolicy, QSplitter, QTableWidget, QVBoxLayout, QWidget, QListWidget,
    QListWidgetItem,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel import (
    __version__, ajustes, archivo, costes, escaner, notas_version, pendientes,
    revision_gemini, sesion, updater, muestras_revision,
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
    CHROME, CHROME_INK, MUTED, SUCCESS, WARNING, DANGER, aplicar_tema,
)
from facturas_excel.panel_ficha import PanelFicha
from facturas_excel.modelo import Factura
from facturas_excel.procesar import (
    a_total_factura, clave_proveedor, construir, normaliza_nif, quitar_aviso_cuenta,
    recordar_cuenta_proveedor, recordar_nif, recordar_nombre_proveedor,
)
from facturas_excel.lote import (
    CON_ERROR, POR_REVISAR, REVISADA, SIN_VERIFICAR, VERIFICADA, Fila,
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
from facturas_excel.validacion import ERROR, OK, REVISAR, validar_nif
from facturas_excel.ventana_comun import (  # noqa: F401
    ANCHO_LISTA_BLOQUES, COLS_RESUMEN_INICIO, COLS_RESUMEN_FIN, ESCRITORIO,
    ICONO_ESTADO, ICONO_MANUAL, ICONO_REVISADO, ICONO_SIN_VERIFICAR,
    TODOS_LOS_BLOQUES, VisorClicable, _cabeceras_resumen, ruta_recurso,
    rutas_factura_de_mime,
)
from facturas_excel.hilos import (  # noqa: F401
    HILOS, HiloActualizacion, HiloDescargaActualizacion, Worker, hilos_lectura,
)
from facturas_excel.cinta import crear_cinta
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

        # El lote ocupa una sola fila. Las acciones frecuentes viven junto al
        # menú para no robar altura ni encoger la tabla en portátiles.
        cliente_bar = QFrame()
        cliente_bar.setObjectName("barraCliente")
        bloque_cliente = QHBoxLayout(cliente_bar)
        bloque_cliente.setContentsMargins(12, 7, 12, 7)
        bloque_cliente.setSpacing(10)
        etiqueta = QLabel("Cliente")
        etiqueta.setObjectName("tituloSeccion")
        self.lbl_cliente = QLabel("Pendiente de detectar")
        self.lbl_cliente.setObjectName("cliente")
        self.lbl_cliente.setWordWrap(True)
        bloque_cliente.addWidget(etiqueta)
        bloque_cliente.addWidget(self.lbl_cliente, 1)
        self.btn_cliente = QPushButton("Cambiar")
        self.btn_cliente.setObjectName("compacto")
        self.btn_cliente.setMaximumWidth(110)
        self.btn_cliente.setToolTip(
            "Quién es SU cliente en estas facturas. Si se detectó mal, se "
            "cambia aquí y el lote se rehace sin volver a pasar por Gemini.")
        self.btn_cliente.setEnabled(False)
        self.btn_cliente.clicked.connect(self._cambiar_cliente)
        bloque_cliente.addWidget(self.btn_cliente)
        lbl_periodo = QLabel("Periodo")
        lbl_periodo.setObjectName("tituloSeccion")
        bloque_cliente.addWidget(lbl_periodo)
        self.combo_periodo = ComboSinRueda()
        self.combo_periodo.setMinimumWidth(150)
        self.combo_periodo.setToolTip(
            "Periodo fiscal esperado del lote. En automático detecta un "
            "trimestre dominante o un ejercicio anual. Las fechas que se "
            "salen del trimestre quedan señaladas para revisar.")
        self.combo_periodo.addItem("Automático", "auto")
        self.combo_periodo.currentIndexChanged.connect(self._on_periodo)
        bloque_cliente.addWidget(self.combo_periodo)
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
        raiz.addWidget(cliente_bar)
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
        for _ in range(4):
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
        self.combo_filtro_estado.currentIndexChanged.connect(self._aplicar_filtro)
        self.combo_filtro_bloque = ComboSinRueda()
        self.combo_filtro_bloque.addItem(TODOS_LOS_BLOQUES)
        self.combo_filtro_bloque.setToolTip(
            "Cada escaneo o PDF cargado es un bloque. Puede revisarlos de uno "
            "en uno y exportarlos todos juntos.")
        self.combo_filtro_bloque.currentIndexChanged.connect(self._aplicar_filtro)
        self.combo_filtro_bloque.currentIndexChanged.connect(
            lambda *_: self._pintar_lista_bloques())
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setObjectName("buscadorLote")
        self.txt_buscar.setMinimumWidth(260)
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
        barra_busqueda = QHBoxLayout()
        barra_busqueda.setSpacing(8)
        barra_busqueda.addWidget(self.txt_buscar, 1)
        for boton in self.botones_tipo.values():
            barra_busqueda.addWidget(boton)
        barra_busqueda.addWidget(self.combo_filtro_estado)
        cuerpo.addLayout(barra_busqueda)
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

        # Lista lateral de bloques: cada PDF o escaneo con lo que le queda
        # por revisar. Pulsar uno filtra la tabla; «Todo el lote» lo quita.
        lista_card = QFrame()
        self.lista_card = lista_card
        lista_card.setObjectName("tarjeta")
        lista_card.setMinimumWidth(150)
        ll = QVBoxLayout(lista_card)
        ll.setContentsMargins(8, 10, 8, 10)
        ll.setSpacing(6)
        titulo_lista = QLabel("Bloques del lote")
        titulo_lista.setObjectName("tituloSeccion")
        ll.addWidget(titulo_lista)
        self.lista_bloques = QListWidget()
        self.lista_bloques.setObjectName("listaBloques")
        self.lista_bloques.setWordWrap(True)
        self.lista_bloques.currentRowChanged.connect(self._on_lista_bloques)
        ll.addWidget(self.lista_bloques, 1)
        split.addWidget(lista_card)
        split.addWidget(tabla_card)

        visor_card = QFrame()
        visor_card.setObjectName("tarjeta")
        visor_card.setMinimumWidth(290)
        lv = QVBoxLayout(visor_card)
        lv.setContentsMargins(12, 12, 12, 12)
        titulo_visor = QLabel("Documento original")
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
        self.btn_senalar = QPushButton("¿De dónde sale?")
        self.btn_senalar.setObjectName("botonVisor")
        self.btn_senalar.setIcon(QIcon(ruta_recurso("search.svg")))
        self.btn_senalar.setToolTip(
            "Señala con recuadros en el documento dónde está escrito cada dato "
            "de la factura. Pulse después una celda de la tabla para ver solo "
            "ese dato. Las facturas en ámbar o rojo se señalan solas.")
        self.btn_senalar.clicked.connect(self._localizar_actual)
        barra_documento.addWidget(self.btn_senalar)
        self.btn_opciones_visor = QPushButton("⋮")
        self.btn_opciones_visor.setObjectName("botonVisor")
        menu_visor = QMenu(self.btn_opciones_visor)
        menu_visor.addAction("Abrir vista previa grande", self._abrir_vista_previa)
        self.btn_opciones_visor.setMenu(menu_visor)
        barra_documento.addWidget(self.btn_opciones_visor)
        self.lbl_img = VisorDocumento(
            "Suelte aquí las facturas\no use «Abrir PDF o imágenes»")
        self.lbl_img.setObjectName("visor")
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setMinimumWidth(250)
        self.lbl_img.setMinimumHeight(180)
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
        # Documento arriba y ficha de la factura debajo: lo leído, al lado de
        # donde se ha leído.
        self.split_visor = QSplitter(Qt.Vertical)
        self.split_visor.setObjectName("splitVisor")
        self.split_visor.setChildrenCollapsible(False)
        self.split_visor.setHandleWidth(8)
        self.split_visor.addWidget(self.visor_scroll)
        ficha_card = QWidget()
        lf = QVBoxLayout(ficha_card)
        lf.setContentsMargins(0, 4, 0, 0)
        lf.setSpacing(2)
        titulo_ficha = QLabel("Ficha de la factura")
        titulo_ficha.setObjectName("tituloSeccion")
        lf.addWidget(titulo_ficha)
        self.ficha = PanelFicha()
        self.ficha.discrepancia_resuelta.connect(self._resolver_discrepancia)
        lf.addWidget(self.ficha, 1)
        self.split_visor.addWidget(ficha_card)
        self.split_visor.setSizes(self._tamanos_divisor("split_visor", [280, 380]))
        self.split_visor.splitterMoved.connect(
            lambda *_: self._timer_divisores.start())
        lv.addWidget(self.split_visor, 1)
        split.addWidget(visor_card)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 7)
        split.setStretchFactor(2, 3)
        split.setSizes(self._tamanos_divisor("split_revision_v2", [180, 860, 400]))
        split.splitterMoved.connect(self._divisor_revision_movido)

        resumen_card = QFrame()
        resumen_card.setObjectName("tarjeta")
        lr = QVBoxLayout(resumen_card)
        lr.setContentsMargins(12, 10, 12, 10)
        lr.setSpacing(2)
        fila_titulo = QHBoxLayout()
        self.lbl_resumen_titulo = QLabel("Comprobación de totales")
        self.lbl_resumen_titulo.setObjectName("tituloSeccion")
        self.lbl_resumen_titulo.setWordWrap(True)
        fila_titulo.addWidget(self.lbl_resumen_titulo, 1)
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
        self.btn_listado_totales = QPushButton("Listado PDF")
        self.btn_listado_totales.setToolTip(
            "Guarda un listado imprimible con los totales y las facturas "
            "mostradas en la tabla.")
        self.btn_listado_totales.clicked.connect(self._guardar_listado_totales)
        fila_titulo.addWidget(self.btn_listado_totales)
        lr.addLayout(fila_titulo)
        self.tabla_resumen = QTableWidget(0, len(COLS_RESUMEN_INICIO) + 1
                                          + len(COLS_RESUMEN_FIN))
        self.tabla_resumen.setHorizontalHeaderLabels(
            _cabeceras_resumen([]))
        self.tabla_resumen.setShowGrid(False)
        self.tabla_resumen.verticalHeader().setVisible(False)
        self.tabla_resumen.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_resumen.setSelectionMode(QTableWidget.NoSelection)
        self.tabla_resumen.setAlternatingRowColors(True)
        # Sin ajuste de linea: un nombre de PDF largo no debe estirar la fila.
        self.tabla_resumen.setWordWrap(False)
        self.tabla_resumen.verticalHeader().setDefaultSectionSize(28)
        self.tabla_resumen.setMinimumHeight(60)
        self.tabla_resumen.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lr.addWidget(self.tabla_resumen, 1)
        self.resumen_card = resumen_card
        resumen_card.setVisible(bool(ajustes.leer("ver_resumen", True)))

        self.split_contenido = QSplitter(Qt.Vertical)
        self.split_contenido.setObjectName("splitContenido")
        self.split_contenido.setChildrenCollapsible(False)
        self.split_contenido.setHandleWidth(8)
        self.split_contenido.addWidget(split)
        self.split_contenido.addWidget(resumen_card)
        self.split_contenido.setStretchFactor(0, 1)
        self.split_contenido.setStretchFactor(1, 0)
        self.split_contenido.setSizes(
            self._tamanos_divisor("split_contenido", [610, 150]))
        self.split_contenido.splitterMoved.connect(
            lambda *_: self._timer_divisores.start())
        cuerpo.addWidget(self.split_contenido, 1)

        barra_estado = QFrame()
        barra_estado.setObjectName("barraEstado")
        pie = QHBoxLayout(barra_estado)
        pie.setContentsMargins(12, 4, 12, 4)
        pie.setSpacing(14)
        self.lbl_estado = QLabel("Cargue o escanee un lote de facturas para empezar.")
        self.lbl_estado.setObjectName("textoSuave")
        pie.addWidget(self.lbl_estado, 1)
        self.lbl_contadores = QLabel("")
        self.lbl_contadores.setObjectName("contadores")
        self.lbl_contadores.setToolTip(
            "Verificada: las dos lecturas coinciden y todo cuadra.\n"
            "Sin verificar: todo cuadra, pero solo la leyó un modelo.\n"
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
        QTimer.singleShot(
            0, lambda: self._distribuir_herramientas(self.width()))

    def _distribuir_herramientas(self, ancho: int):
        """Muestra todas las acciones habituales sin estirarlas ni ocultarlas."""
        if not hasattr(self, "tabla"):
            return
        elementos = (
            self.lbl_mostrar, self.combo_filtro_bloque, self.combo_filtro_registro,
            self.btn_siguiente, self.btn_revisada, self.btn_unir_hojas,
            self.btn_limpiar_filtros, self.btn_quitar_bloque,
            self.btn_eliminar, self.btn_deshacer_borrado,
        )
        for fila in self.filas_herramientas:
            for elemento in elementos:
                fila.removeWidget(elemento)
        self.combo_filtro_bloque.setMinimumWidth(135)
        self.combo_filtro_bloque.setMaximumWidth(220)
        ancho_tabla = min(ancho, self.tabla.parentWidget().width())
        disponible = max(320, ancho_tabla - 24)
        fila_actual = 0
        usado = 0
        habituales = (
            self.lbl_mostrar, self.combo_filtro_bloque, self.btn_siguiente,
            self.btn_revisada, self.btn_unir_hojas,
            self.btn_limpiar_filtros, self.btn_quitar_bloque,
            self.btn_eliminar, self.btn_deshacer_borrado,
        )
        for widget in habituales:
            if widget is self.btn_deshacer_borrado and not widget.isEnabled():
                continue
            maximo = widget.maximumWidth()
            preferido = max(widget.minimumWidth(), widget.sizeHint().width())
            if maximo < 16_777_215:
                preferido = min(preferido, maximo)
            necesario = preferido + (8 if usado else 0)
            if usado and usado + necesario > disponible and fila_actual < 3:
                fila_actual += 1
                usado = 0
                necesario = preferido
            fila = self.filas_herramientas[fila_actual]
            fila.insertWidget(fila.count() - 1, widget)
            usado += necesario
        fila_registro = min(fila_actual + 1, len(self.filas_herramientas) - 1)
        fila = self.filas_herramientas[fila_registro]
        fila.insertWidget(fila.count() - 1, self.combo_filtro_registro)

    def _actualizar_barra_responsiva(self, ancho: int):
        """En poca altura los accesos, sin marca duplicada, comparten el menú."""
        if not hasattr(self, "fila_barra_estrecha"):
            return
        compacta = self.height() < 760
        for marca in self._marcas_barra:
            marca.setVisible(not compacta)
        # Compacta: botones con el texto al lado y sin rótulos de grupo, para
        # caber en la barra de menús.
        for boton in self._botones_grandes:
            boton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if compacta
                                     else Qt.ToolButtonTextUnderIcon)
            boton.setIconSize(QSize(16, 16) if compacta else QSize(26, 26))
        for widget in self._pilas_cinta + self._etiquetas_grupo:
            widget.setVisible(not compacta)
        self.barra_rapida.layout().setContentsMargins(
            6 if compacta else 16, 0 if compacta else 6,
            8 if compacta else 16, 0)
        if compacta != getattr(self, "_barra_en_menu", False):
            if compacta:
                self.layout_barra_estrecha.removeWidget(self.barra_rapida)
                self.menuBar().setCornerWidget(self.barra_rapida, Qt.TopRightCorner)
            else:
                self.barra_rapida.setParent(self.fila_barra_estrecha)
                self.menuBar().setCornerWidget(None, Qt.TopRightCorner)
                self.layout_barra_estrecha.addWidget(self.barra_rapida)
            self._barra_en_menu = compacta
        self.barra_rapida.show()
        self.fila_barra_estrecha.setVisible(not compacta)
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
        if hasattr(self, "split_revision"):
            ajustes.guardar("split_revision_v2", self.split_revision.sizes())
        if hasattr(self, "split_contenido"):
            ajustes.guardar("split_contenido", self.split_contenido.sizes())
        if hasattr(self, "split_visor"):
            ajustes.guardar("split_visor", self.split_visor.sizes())

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
            getattr(self, "_hilo_localizar", None),
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
        self.accion_gestion_manual = comprobar.addAction(
            "Apartar selección para gestión manual…",
            self._alternar_gestion_manual)
        self.accion_olvidar_exportacion = comprobar.addAction(
            "Olvidar que la selección ya se exportó…",
            self._olvidar_exportacion)
        self.accion_olvidar_exportacion.setToolTip(
            "Si Aplifisa rechazó el Excel, quita esas facturas del historial "
            "de exportadas para poder exportarlas otra vez sin aviso.")
        self.accion_gestion_manual.setToolTip(
            "Uso excepcional: aparta o recupera facturas que no deben entrar "
            "en la exportación automática.")

        ver = self.menuBar().addMenu("Ver")
        self.accion_resumen = ver.addAction("Comprobación de totales del lote")
        self.accion_resumen.setCheckable(True)
        self.accion_resumen.setChecked(bool(ajustes.leer("ver_resumen", True)))
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
        """El resumen es solo un punto de control: si estorba, se quita."""
        ajustes.guardar("ver_resumen", bool(visible))
        if hasattr(self, "resumen_card"):
            self.resumen_card.setVisible(bool(visible))
            if visible and hasattr(self, "split_contenido"):
                tamanos = self.split_contenido.sizes()
                if len(tamanos) == 2 and tamanos[1] < 80:
                    total = max(sum(tamanos), 600)
                    self.split_contenido.setSizes([max(300, total - 150), 150])
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
    def _pintar_cliente(self):
        """Cliente del lote. Si hay bloques de varios, se dice claramente."""
        nifs = {b["nif"] for b in self._bloques if b["nif"]}
        if len(nifs) > 1:
            self.lbl_cliente.setText(f"⚠ VARIOS CLIENTES en el lote ({len(nifs)})")
            return
        self.lbl_cliente.setText(
            f"{self._cliente_nombre or 'Cliente no identificado'}"
            + (f"  ·  {self._cliente_nif}" if self._cliente_nif else ""))

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
            self._avisar("Para quitar un bloque, elíjalo primero en la lista "
                         "de bloques o en el desplegable.", AVISO)
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
        self.lbl_cliente.setText("Pendiente de detectar")
        self.lbl_estado.setText("Lote vacío. Cargue o escanee facturas para empezar.")
        sesion.borrar()

    def _por_el_total(self) -> bool:
        """El cliente registra sus compras con recargo por el total factura."""
        return (getattr(self, "_hay_recargo", False)
                and self.combo_recargo.currentData() == TOTAL)

    def _rellenar_tabla(self):
        self._invalidar_contraste_registro()
        self._poner_filas(filas_de_bloques(
            self._bloques, self._por_el_total(), a_total_factura))

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
        clave = clave_documento(self.filas[fila]["factura"])
        for registro in self.filas:
            if clave_documento(registro["factura"]) == clave:
                registro["factura"].revision_confirmada = False
                registro["factura"].edicion_manual = True
                for fuente in registro.get("fuentes", []):
                    fuente.revision_confirmada = False
                    fuente.edicion_manual = True

    def _on_celda(self, item):
        """Lo que se corrige a mano se guarda para ese proveedor.

        Si no, habria que volver a corregir lo mismo en cada lote: el nombre
        con el que se le llama, su NIF y la cuenta que le toca.
        """
        self._invalidar_contraste_registro()
        columna = item.column()
        if item.row() < len(self.filas):
            # Lo escrito pasa a la factura en el momento: la tabla solo enseña.
            campo, valor = valor_de_celda(columna, item.text())
            if campo:
                setattr(self.filas[item.row()].factura, campo, valor)
            self._invalidar_revision_documento(item.row())
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
        self._invalidar_contraste_registro()
        fila = self._fila_del_control_tipo(control)
        if 0 <= fila < len(self.filas):
            self._invalidar_revision_documento(fila)
            self.filas[fila].tipo = control.currentData()
            self.filas[fila]["factura"].tipo_revision = control.currentData()
            for fuente in self.filas[fila].get("fuentes", []):
                fuente.tipo_revision = control.currentData()
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
                or (opcion == 3 and estado in {VERIFICADA, SIN_VERIFICAR, REVISADA})
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
            registro = self.filas[fila]
            f = registro["factura"]
            pendiente = (registro.get("estado") == ERROR or
                         (registro.get("estado") == REVISAR
                          and not f.revision_confirmada
                          and not f.tratamiento_manual))
            if pendiente:
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
        """Da salida únicamente a avisos ámbar comprobados por una persona."""
        filas = self._filas_seleccionadas()
        if not filas:
            self._avisar("Seleccione una o varias filas ámbar.", AVISO)
            return
        confirmadas = []
        for fila in filas:
            registro = self.filas[fila]
            f = self._leer_fila(fila)
            if (registro.get("estado") == REVISAR
                    and not f.tratamiento_manual and not f.revision_confirmada):
                f.revision_confirmada = True
                confirmadas.append(f)
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
        else:
            self._avisar(
                "Solo se pueden confirmar avisos ámbar. Los errores rojos se "
                "corrigen y las operaciones manuales no se exportan.", AVISO)

    def _alternar_gestion_manual(self) -> None:
        """Aparta la factura completa, aunque tenga varias líneas de IVA."""
        seleccionadas = self._filas_seleccionadas()
        if not seleccionadas:
            self._avisar("Seleccione al menos una factura.", AVISO)
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

    def _pintar_lista_bloques(self) -> None:
        """Cada bloque con sus facturas y lo que queda por revisar."""
        if not hasattr(self, "lista_bloques"):
            return
        cuentas = {}
        for registro in self.filas:
            c = cuentas.setdefault(registro.get("bloque", ""), Counter())
            f = registro["factura"]
            estado = registro.get("estado", OK)
            c["lineas"] += 1
            if f.tratamiento_manual:
                c["manual"] += 1
            elif estado == ERROR:
                c["error"] += 1
            elif estado == REVISAR and not f.revision_confirmada:
                c["revisar"] += 1

        def texto(nombre, c):
            partes = [f"{c['lineas']} líneas"]
            if c["error"]:
                partes.append(f"✕ {c['error']}")
            if c["revisar"]:
                partes.append(f"! {c['revisar']}")
            if not c["error"] and not c["revisar"] and c["lineas"]:
                partes.append("✓ listo")
            return f"{nombre}\n" + " · ".join(partes)

        total = Counter()
        for c in cuentas.values():
            total.update(c)
        actual = self.combo_filtro_bloque.currentText()
        self.lista_bloques.blockSignals(True)
        self.lista_bloques.clear()
        entradas = [(TODOS_LOS_BLOQUES, "Todo el lote", total)]
        for i in range(1, self.combo_filtro_bloque.count()):
            nombre = self.combo_filtro_bloque.itemText(i)
            entradas.append((nombre, nombre, cuentas.get(nombre, Counter())))
        seleccion = 0
        for fila, (clave, nombre, c) in enumerate(entradas):
            item = QListWidgetItem(texto(nombre, c))
            item.setData(Qt.UserRole, clave)
            color = (DANGER if c["error"] else WARNING if c["revisar"]
                     else SUCCESS if c["lineas"] else MUTED)
            item.setForeground(QColor(color))
            item.setToolTip(f"{nombre}: {c['lineas']} líneas, "
                            f"{c['error']} con error, {c['revisar']} por revisar")
            self.lista_bloques.addItem(item)
            if clave == actual:
                seleccion = fila
        self.lista_bloques.setCurrentRow(seleccion)
        self.lista_bloques.blockSignals(False)

    def _on_lista_bloques(self, fila: int) -> None:
        item = self.lista_bloques.item(fila) if fila >= 0 else None
        if not item:
            return
        clave = item.data(Qt.UserRole)
        indice = self.combo_filtro_bloque.findText(clave)
        if indice >= 0 and indice != self.combo_filtro_bloque.currentIndex():
            self.combo_filtro_bloque.setCurrentIndex(indice)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        ancho = event.size().width()
        self._actualizar_barra_responsiva(ancho)
        # En ventanas estrechas la lista de bloques deja su sitio a la tabla:
        # el mismo filtro sigue en el desplegable «Todos los bloques».
        if hasattr(self, "lista_card"):
            self.lista_card.setVisible(ancho >= ANCHO_LISTA_BLOQUES)
        self._distribuir_herramientas(ancho)
        if self.tabla.currentRow() >= 0:
            self._mostrar_miniatura()

    # ---------- exportar ----------


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
