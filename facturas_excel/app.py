"""Ventana principal de Facturas a Aplifisa.

Flujo: Cargar facturas (PDF/imagenes) -> Gemini extrae y clasifica en segundo
plano -> autodetecta el cliente -> tabla de revision con miniatura y semaforo
(editable, se puede cambiar gasto/venta) -> Exportar gastos.xlsx / ventas.xlsx.
"""

from __future__ import annotations

import argparse
import gc
import os
import sys
import time
import traceback

from PySide6.QtCore import QEvent, QItemSelectionModel, QSize, Qt, QThread, QTimer
from PySide6.QtGui import QActionGroup, QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QButtonGroup, QComboBox, QDialog,
    QFileDialog, QFrame, QHeaderView,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QProgressDialog, QScrollArea,
    QSizePolicy, QSplitter, QTableWidget, QToolButton,
    QVBoxLayout, QWidget, QGridLayout,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel import (
    __version__, ajustes, archivo, copias, costes, errores, escaner, imagen_hoja,
    notas_version, pdf, pendientes, proveedores, revision_gemini, sesion, updater,
    muestras_revision,
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
    DESGLOSE, EXENTO, TOTAL, guardar_regimen_recargo, puede_estar_en_recargo,
    regimen_recargo,
)
from facturas_excel.conceptos import descripcion_de, es_valido
from facturas_excel.control_facturas import clave_documento
from facturas_excel.consulta import (
    SIN_FECHA, PeriodoLote, coincide_busqueda, detectar_periodo, en_el_mes,
    facturas_unicas, mes_de, nombre_mes, periodo_manual,
)
from facturas_excel.estilo import (
    CHROME, CHROME_INK, aplicar_tema,
)
from facturas_excel.panel_ficha import PanelFicha
from facturas_excel import distribucion
from facturas_excel.su_suma import ALTO_FILA_COLUMNA, TablaSuSuma, TablaTotales
from facturas_excel.modelo import Factura
from facturas_excel.texto import tiene_invisibles
from facturas_excel.procesar import (
    a_total_factura, clave_proveedor, construir, nombre_preferido,
    nombres_guardados, normaliza_nif,
    ficha_de_cuenta, nombre_sin_letra, quitar_aviso_cuenta,
    recordar_cuenta_proveedor, recordar_nif,
    recordar_nombre_proveedor, unificar_nombres_por_nif,
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
from facturas_excel.ventana_validacion import MENSAJES_DE_ESTADO, aviso_sin_calculados

# Datos de la cabecera de una factura (iguales en todas sus líneas).
CAMPOS_CABECERA = ("num_factura", "fecha", "nombre", "nif", "concepto", "subclave")
TODOS_LOS_MESES = "Todos los meses"
# Las tres tarjetas (facturas, factura, totales), con el mismo aire y el
# título a la misma altura en cualquier distribución.
MARGENES_TARJETA = (12, 10, 12, 10)
ALTO_TITULO_TARJETA = 32
from facturas_excel.ventana_comun import (  # noqa: F401
    COLS_RESUMEN_INICIO, COLS_RESUMEN_FIN, ESCRITORIO, Divisor, EtiquetaCliente,
    EtiquetaRecortada,
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


# Como mucho, una muestra de revisión automática por minuto (segundos).
MUESTRA_CADA_S = 60


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
        # Por fila: Fila(png, factura, aviso, bloque…). `png` es el asa de la
        # imagen de la hoja (imagen_hoja), que vive en disco.
        self.filas = []
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
        self._timer_muestras.timeout.connect(self._guardar_muestra_revision_automatica)
        # La muestra de revisión que se guarda sola tras cada cambio, como
        # mucho una por minuto (ver _guardar_muestra_revision_automatica).
        self._ultima_muestra = float("-inf")
        self._timer_muestra_minuto = QTimer(self)
        self._timer_muestra_minuto.setSingleShot(True)
        self._timer_muestra_minuto.timeout.connect(
            self._guardar_muestra_revision_automatica)
        # El lote se guarda solo poco después de cada cambio (no solo al
        # cerrar): un apagón no se lleva la revisión ni lecturas ya pagadas.
        self._timer_sesion = QTimer(self)
        self._timer_sesion.setSingleShot(True)
        self._timer_sesion.setInterval(3000)
        self._timer_sesion.timeout.connect(self._guardar_sesion_automatica)
        self._aviso_sesion_dado = False
        self._comprobar_updates = comprobar_updates
        self._crear_menu()

        self._crear_interfaz()
        self._crear_atajos()
        self._pintar_gasto()
        if restaurar_sesion:
            self._restaurar_sesion()
        # Las partes de la cola de otra vez (se cerró a mitad) ya no sirven.
        try:
            pdf.limpiar_partes_huerfanas()
        except OSError:
            pass
        QTimer.singleShot(500, self._mostrar_notas_version_al_arrancar)
        # La copia de seguridad del día, con el programa ya en pantalla.
        QTimer.singleShot(4000, self._copia_diaria)
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
        # Solo aparece si el lote trae facturas con recargo de equivalencia o
        # el cliente registra sus compras por el total (en recargo, o sin
        # derecho a deducir): para el resto no significa nada y estorba.
        self.fila_recargo = QWidget()
        lr_recargo = QHBoxLayout(self.fila_recargo)
        lr_recargo.setContentsMargins(0, 0, 0, 0)
        lr_recargo.setSpacing(6)
        lbl_recargo = QLabel("IVA de sus compras:")
        lbl_recargo.setObjectName("textoSuave")
        lr_recargo.addWidget(lbl_recargo)
        # Por qué está a la vista: el lote trae recargo, o el cliente está en
        # recargo aunque ninguna factura del lote lo lleve impreso.
        self.lbl_hay_recargo = QLabel()
        self.lbl_hay_recargo.setStyleSheet("font-weight: 600; color: #A16207;")
        lr_recargo.addWidget(self.lbl_hay_recargo)
        self.combo_recargo = ComboSinRueda()
        self.combo_recargo.addItem(
            "registrar por el TOTAL factura (minorista)", TOTAL)
        self.combo_recargo.addItem(
            "registrar con DESGLOSE de IVA y recargo (mayorista)", DESGLOSE)
        self.combo_recargo.addItem(
            "registrar por el TOTAL factura (actividad exenta, sin derecho a "
            "deducir)", EXENTO)
        self.combo_recargo.setToolTip(
            "Lo decide el régimen del cliente, no la factura:\n"
            "  · Minorista en recargo (sin modelo 303): no deduce IVA, así que "
            "el gasto va por el total.\n"
            "  · Mayorista en estimación directa: registra el IVA y el recargo "
            "por separado.\n"
            "  · Actividad exenta (médico, academia…, art. 20 de la Ley del "
            "IVA): no deduce el IVA de sus compras (art. 94), todas por el "
            "total.\n"
            "Se recuerda por NIF. Al minorista se le registran así TODAS las "
            "compras, también las que no traen recargo (teléfono, "
            "reparaciones, publicidad…).")
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
        self.btn_ver_incidencias.clicked.connect(lambda: self._siguiente_incidencia())
        fila_alerta.addWidget(self.btn_ver_incidencias)
        lal.addLayout(fila_alerta)
        lal.addWidget(self.lbl_alerta_texto)

        split = Divisor(Qt.Horizontal)
        self.split_revision = split
        split.setObjectName("splitRevision")
        tabla_card = QFrame()
        tabla_card.setObjectName("tarjeta")
        self.tabla_card = tabla_card
        lt = QVBoxLayout(tabla_card)
        lt.setContentsMargins(*MARGENES_TARJETA)
        fila_datos = QHBoxLayout()
        titulo_tabla = QLabel("Datos extraídos")
        titulo_tabla.setObjectName("tituloSeccion")
        # Las tres tarjetas, con el título a la misma altura y del mismo
        # alto (la de la factura lleva botones en esa línea).
        titulo_tabla.setMinimumHeight(ALTO_TITULO_TARJETA)
        fila_datos.addWidget(titulo_tabla)
        # Se recorta con «…» antes que ensanchar la tarjeta (en Windows esta
        # línea pedía más ancho que toda la columna estrecha).
        self.lbl_resultados = EtiquetaRecortada("Sin facturas", minimo=60,
                                                alineacion=Qt.AlignRight)
        self.lbl_resultados.setObjectName("textoSuave")
        fila_datos.addWidget(self.lbl_resultados, 1)
        lt.addLayout(fila_datos)

        # En ventana ancha coincide con el prototipo: filtros y acciones en
        # una fila. En portátiles se reparten sin comprimir ni cortar textos.
        # En su propia caja, que no impone ancho mínimo: si la tabla se
        # estrecha (restaurar una ventana maximizada, el divisor), los
        # filtros se reparten de nuevo en vez de quitarle sitio a la hoja.
        self.caja_herramientas = QWidget()
        self.caja_herramientas.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.caja_herramientas.setMinimumWidth(300)
        self.layout_herramientas = QVBoxLayout(self.caja_herramientas)
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
        # Por mes: para cuadrar mes a mes con el listado de Aplifisa (los
        # totales de «Lo que se ve» son los de ese mes).
        self.combo_filtro_mes = ComboSinRueda()
        self.combo_filtro_mes.addItem(TODOS_LOS_MESES, None)
        self.combo_filtro_mes.setToolTip(
            "Ver solo las facturas de un mes, por su fecha. En los totales, "
            "«Lo que se ve» suma ese mes: compárelo con el listado de "
            "Aplifisa filtrado por el mismo mes.")
        self.combo_filtro_mes.currentIndexChanged.connect(self._aplicar_filtro)
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
        self.btn_siguiente.clicked.connect(lambda: self._siguiente_incidencia())
        self.btn_revisada = QPushButton("Marcar revisada")
        self.btn_revisada.setObjectName("accionTabla")
        self.btn_revisada.setIcon(QIcon(ruta_recurso("check.svg")))
        self.btn_revisada.setToolTip(
            "Confirma que ha comparado con el PDF las filas ámbar seleccionadas.")
        self.btn_revisada.clicked.connect(lambda: self._marcar_revisada())
        self.btn_unir_hojas = QPushButton("Unir hojas")
        self.btn_unir_hojas.setObjectName("accionTabla")
        self.btn_unir_hojas.setIcon(QIcon(ruta_recurso("link.svg")))
        self.btn_unir_hojas.setToolTip(
            "Seleccione las filas que pertenecen a la misma factura. La primera "
            "aporta la cabecera y la última, el resumen fiscal.")
        self.btn_unir_hojas.clicked.connect(self._unir_hojas_seleccionadas)
        # Una factura de gasto cuyo IVA no se puede deducir (un tique sin los
        # datos del cliente, un restaurante, un regalo…): por el total.
        self.btn_por_el_total = QPushButton("Por el total")
        self.btn_por_el_total.setObjectName("accionTabla")
        self.btn_por_el_total.setToolTip(
            "El IVA de las facturas de gasto seleccionadas no se puede deducir "
            "(arts. 96 y 97 de la Ley del IVA): se registran por el total, con "
            "el IVA dentro del gasto. Pulsar otra vez lo deshace.")
        self.btn_por_el_total.clicked.connect(self._alternar_por_el_total)
        self.btn_limpiar_filtros = QPushButton("Limpiar filtros")
        self.btn_limpiar_filtros.setObjectName("accionTabla")
        self.btn_limpiar_filtros.setIcon(QIcon(ruta_recurso("filter-x.svg")))
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
                self.btn_por_el_total, self.btn_limpiar_filtros,
                self.btn_quitar_bloque, self.btn_eliminar,
                self.btn_deshacer_borrado):
            boton.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            boton.setAccessibleName(boton.text())
        # Nombre completo, abreviado y globo de cada acción: si no caben en
        # una fila, se acortan antes de pasar a otra (cada fila de botones
        # es una factura menos a la vista).
        self._nombres_acciones = {
            boton: (boton.text(), corto, boton.toolTip())
            for boton, corto in (
                (self.btn_siguiente, "Siguiente"),
                (self.btn_revisada, "Revisada"),
                (self.btn_unir_hojas, ""), (self.btn_por_el_total, "Total"),
                (self.btn_limpiar_filtros, ""),
                (self.btn_quitar_bloque, ""), (self.btn_eliminar, ""))}
        lt.addWidget(self.caja_herramientas)
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
        # Intro: a la siguiente pendiente (sin marcar nada; quien viene de
        # Excel pulsa Intro sin pensar). Ctrl+Intro: correcta y siguiente.
        self.tabla.intro.connect(lambda: self._siguiente_incidencia())
        self.tabla.ctrl_intro.connect(self._correcta_y_siguiente)
        lt.addWidget(self.tabla, 1)

        split.addWidget(tabla_card)

        # Columna central: la factura entera en una sola tarjeta. Arriba la
        # hoja escaneada y debajo lo que ha leído la IA (antes eran dos
        # columnas; el usuario las quería unidas para dejar sitio a los
        # totales).
        visor_card = QFrame()
        visor_card.setObjectName("tarjeta")
        # Sin mínimo fijo: el de su contenido (la hoja y lo leído, lado a
        # lado), para que la hoja nunca se quede en una tira.
        self.factura_card = visor_card
        lv = QVBoxLayout(visor_card)
        lv.setContentsMargins(*MARGENES_TARJETA)
        titulo_visor = QLabel("Factura")
        titulo_visor.setObjectName("tituloSeccion")
        titulo_visor.setMinimumHeight(ALTO_TITULO_TARJETA)
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
        # Lo que ha leído la IA va a la derecha de la hoja; se puede quitar
        # para dar a la hoja todo el ancho (queda una línea con el motivo).
        self.btn_plegar_lectura = QToolButton()
        self.btn_plegar_lectura.setObjectName("plegarSeccion")
        self.btn_plegar_lectura.setText("Lectura IA")
        self.btn_plegar_lectura.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_plegar_lectura.setAutoRaise(True)
        self.btn_plegar_lectura.setCheckable(True)
        self.btn_plegar_lectura.setToolTip(
            "Ocultar o ver lo que ha leído la IA al lado de la hoja. Oculto, "
            "se ve solo el estado y el motivo, y la hoja gana ancho.")
        barra_documento.addWidget(self.btn_plegar_lectura)
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
        self.visor_scroll.setMinimumWidth(240)
        # Al mover el divisor del visor, la hoja se vuelve a encajar.
        self.visor_scroll.installEventFilter(self)
        # «Revisar» va en la línea del título: así la hoja gana esa fila.
        self.titulo_visor = titulo_visor
        fila_titulo_visor = QHBoxLayout()
        fila_titulo_visor.setSpacing(6)
        fila_titulo_visor.addWidget(titulo_visor)
        fila_titulo_visor.addStretch(1)
        lv.addLayout(fila_titulo_visor)
        lv.addLayout(barra_documento)
        # Con la lectura oculta: una línea con el estado y el motivo.
        self.lbl_lectura_resumen = QLabel()
        self.lbl_lectura_resumen.setObjectName("lecturaResumen")
        self.lbl_lectura_resumen.setTextFormat(Qt.RichText)
        self.lbl_lectura_resumen.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lbl_lectura_resumen.setCursor(Qt.PointingHandCursor)
        self.lbl_lectura_resumen.setToolTip("Pulse para ver lo leído.")
        self.lbl_lectura_resumen.mousePressEvent = (
            lambda _e: self.btn_plegar_lectura.setChecked(False))
        self.lbl_lectura_resumen.installEventFilter(self)
        lv.addWidget(self.lbl_lectura_resumen)
        # La hoja a la izquierda y lo leído a su derecha: la tarjeta es ancha
        # y baja (los totales van abajo, a lo ancho).
        self.split_factura = Divisor(Qt.Horizontal)
        self.split_factura.setObjectName("splitFactura")
        self.split_factura.addWidget(self.visor_scroll)
        lectura = QWidget()
        self.panel_lectura = lectura
        lf = QVBoxLayout(lectura)
        lf.setContentsMargins(4, 0, 0, 0)
        lf.setSpacing(2)
        titulo_ficha = QLabel("Lo que ha leído la IA")
        titulo_ficha.setObjectName("tituloSubseccion")
        lf.addWidget(titulo_ficha)
        self.ficha = PanelFicha()
        self.ficha.setMinimumWidth(220)
        self.ficha.discrepancia_resuelta.connect(self._resolver_discrepancia)
        lf.addWidget(self.ficha, 1)
        self.split_factura.addWidget(lectura)
        self.split_factura.setStretchFactor(0, 1)
        self.split_factura.setStretchFactor(1, 1)
        self.split_factura.splitterMoved.connect(
            lambda *_: self._timer_divisores.start())
        self.btn_plegar_lectura.toggled.connect(self._plegar_lectura)
        self.btn_plegar_lectura.setChecked(bool(ajustes.leer("lectura_plegada", False)))
        self._plegar_lectura(self.btn_plegar_lectura.isChecked(), guardar=False)
        lv.addWidget(self.split_factura, 1)
        # Revisar sin ir a la tabla: donde está la vista.
        fila_revisar = fila_titulo_visor
        # Texto corto: en un portátil la columna de la factura es estrecha.
        self.btn_revisada_factura = QPushButton("Revisada")
        self.btn_revisada_factura.setObjectName("accionTabla")
        self.btn_revisada_factura.setIcon(QIcon(ruta_recurso("check.svg")))
        self.btn_revisada_factura.setToolTip(
            "Marcar revisada: confirma que ha comparado esta factura (en "
            "ámbar) con la hoja. Se queda en ella.")
        self.btn_revisada_factura.clicked.connect(self._marcar_revisada_actual)
        self.btn_revisada_factura.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        fila_revisar.addWidget(self.btn_revisada_factura)
        self.btn_correcta_siguiente = QPushButton("Correcta · siguiente")
        self.btn_correcta_siguiente.setObjectName("accionPrincipal")
        self.btn_correcta_siguiente.setIcon(QIcon(ruta_recurso("arrow-right-blanco.svg")))
        self.btn_correcta_siguiente.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_correcta_siguiente.setToolTip(
            "Da por buena esta factura (si está en ámbar, cuenta como "
            "revisada) y pasa a la siguiente pendiente.  (Ctrl+Intro)\n"
            "Intro en la tabla pasa a la siguiente pendiente sin marcar nada.")
        self.btn_correcta_siguiente.clicked.connect(self._correcta_y_siguiente)
        fila_revisar.addWidget(self.btn_correcta_siguiente)
        split.addWidget(visor_card)

        split.splitterMoved.connect(self._divisor_revision_movido)

        # Abajo, a todo lo ancho: los totales como el listado de Aplifisa
        # (una fila por ámbito, una columna por importe) y, debajo, «Su suma
        # a mano» con una casilla bajo cada columna.
        totales_card = QFrame()
        totales_card.setObjectName("tarjeta")
        self.totales_card = totales_card
        lr = QVBoxLayout(totales_card)
        lr.setContentsMargins(*MARGENES_TARJETA)
        lr.setSpacing(4)
        # «Una a una»: cuántas facturas están listas y cuántas faltan.
        self.panel_progreso = QFrame()
        self.panel_progreso.setObjectName("progresoLote")
        capa_progreso = QVBoxLayout(self.panel_progreso)
        capa_progreso.setContentsMargins(0, 0, 0, 8)
        capa_progreso.setSpacing(4)
        fila_progreso = QHBoxLayout()
        self.lbl_progreso = QLabel("Sin facturas")
        self.lbl_progreso.setObjectName("tituloSeccion")
        self.lbl_progreso.setMinimumHeight(ALTO_TITULO_TARJETA)
        fila_progreso.addWidget(self.lbl_progreso, 1)
        self.lbl_faltan = QLabel()
        self.lbl_faltan.setObjectName("faltanLote")
        fila_progreso.addWidget(self.lbl_faltan)
        capa_progreso.addLayout(fila_progreso)
        self.barra_progreso = QProgressBar()
        self.barra_progreso.setObjectName("barraProgresoLote")
        self.barra_progreso.setTextVisible(False)
        self.barra_progreso.setToolTip(
            "Listas: verificadas, sin verificar, revisadas o corregidas. "
            "Faltan: las que están por revisar o con error.")
        capa_progreso.addWidget(self.barra_progreso)
        self.lbl_progreso_detalle = QLabel()
        self.lbl_progreso_detalle.setWordWrap(True)
        self.lbl_progreso_detalle.setObjectName("contadores")
        capa_progreso.addWidget(self.lbl_progreso_detalle)
        self.panel_progreso.setVisible(False)
        lr.addWidget(self.panel_progreso)
        cabecera_totales = QHBoxLayout()
        cabecera_totales.setSpacing(10)
        # Con filtros y recargo el título es largo: se recorta con «…».
        self.lbl_resumen_titulo = EtiquetaRecortada("Comprobación de totales",
                                                    minimo=170)
        self.lbl_resumen_titulo.setObjectName("tituloSeccion")
        self.lbl_resumen_titulo.setMinimumHeight(ALTO_TITULO_TARJETA)
        cabecera_totales.addWidget(self.lbl_resumen_titulo)
        self.tabla_su_suma = TablaSuSuma()
        self.tabla_su_suma.cambiado.connect(self._resaltar_fila_comparada)
        self.tabla_su_suma.medida_cambiada.connect(
            lambda: hasattr(self, "tabla_totales") and self._ajustar_alto_totales())
        cabecera_totales.addWidget(self.tabla_su_suma.lbl_ambito, 1)
        cabecera_totales.addWidget(self.tabla_su_suma.lbl_veredicto)
        self.btn_ver_su_suma = QToolButton()
        self.btn_ver_su_suma.setObjectName("plegarSeccion")
        self.btn_ver_su_suma.setText("Su suma a mano")
        self.btn_ver_su_suma.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_ver_su_suma.setAutoRaise(True)
        self.btn_ver_su_suma.setCheckable(True)
        self.btn_ver_su_suma.setToolTip(
            "Ver u ocultar la fila donde escribir su suma (a mano o del "
            "listado de Aplifisa) para compararla con el programa.")
        self.btn_ver_su_suma.toggled.connect(self._ver_su_suma)
        cabecera_totales.addWidget(self.btn_ver_su_suma)
        btn_copiar = QPushButton("Copiar")
        btn_copiar.setObjectName("compacto")
        btn_copiar.setToolTip(
            "Copia el resumen al portapapeles para pegarlo donde haga falta.")
        btn_copiar.clicked.connect(self._copiar_resumen)
        self.btn_copiar_totales = btn_copiar
        cabecera_totales.addWidget(btn_copiar)
        self.btn_listado_totales = QPushButton("Listado PDF")
        self.btn_listado_totales.setObjectName("compacto")
        self.btn_listado_totales.setToolTip(
            "Guarda un listado imprimible con los totales y las facturas "
            "mostradas en la tabla.")
        self.btn_listado_totales.clicked.connect(self._guardar_listado_totales)
        cabecera_totales.addWidget(self.btn_listado_totales)
        btn_cerrar_resumen = QPushButton("✕")
        btn_cerrar_resumen.setObjectName("botonVisor")
        btn_cerrar_resumen.setFixedWidth(26)
        btn_cerrar_resumen.setToolTip(
            "Ocultar los totales. Es solo una comprobación: se vuelven a ver "
            "en el menú Ver.")
        btn_cerrar_resumen.clicked.connect(lambda: self._ver_resumen(False))
        self.btn_cerrar_totales = btn_cerrar_resumen
        cabecera_totales.addWidget(btn_cerrar_resumen)
        lr.addLayout(cabecera_totales)
        # En columna no cabe todo en la cabecera: el veredicto va debajo y
        # los botones, al pie (como en los prototipos 1, 2 y 5).
        self.cabecera_totales = cabecera_totales
        self.fila_info_totales = QHBoxLayout()
        self.fila_info_totales.setSpacing(8)
        lr.addLayout(self.fila_info_totales)
        self.tabla_totales = TablaTotales(0, 0)
        self.tabla_totales.redimensionada.connect(
            lambda: self._anchos_totales(getattr(self, "_columnas_totales", [])))
        self.tabla_totales.setObjectName("tablaTotales")
        self.tabla_totales.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_totales.setSelectionMode(QTableWidget.NoSelection)
        self.tabla_totales.setFocusPolicy(Qt.NoFocus)
        self.tabla_totales.verticalHeader().setVisible(False)
        self.tabla_totales.verticalHeader().setDefaultSectionSize(24)
        self.tabla_totales.setShowGrid(False)
        # En una pantalla baja las filas se desplazan (con anchos fijos, cada
        # casilla de «Su suma» sigue bajo su columna aunque salga la barra).
        self.tabla_totales.verticalScrollBar().rangeChanged.connect(
            lambda *_: self._ajustar_alto_totales())
        self.tabla_totales.setTabKeyNavigation(False)
        # La barra la lleva «Su suma» (debajo, o a la derecha con los totales
        # en columna; si se oculta, la de los totales) y las dos se mueven
        # juntas, píxel a píxel, se desplace la que se desplace: cada casilla
        # sigue con su importe.
        self.tabla_totales.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.tabla_totales.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        for vertical in (False, True):
            barra_totales = (self.tabla_totales.verticalScrollBar() if vertical
                             else self.tabla_totales.horizontalScrollBar())
            barra_suma = (self.tabla_su_suma.verticalScrollBar() if vertical
                          else self.tabla_su_suma.horizontalScrollBar())
            barra_suma.valueChanged.connect(
                lambda valor, b=barra_totales, v=vertical: self._mover_barra(b, valor, v))
            barra_totales.valueChanged.connect(
                lambda valor, b=barra_suma, v=vertical: self._mover_barra(b, valor, v))
        self.tabla_totales.horizontalScrollBar().rangeChanged.connect(
            lambda *_: self._ajustar_alto_totales())
        # Una encima de otra (totales abajo) o una al lado de otra (en columna).
        self.capa_tablas_totales = QBoxLayout(QBoxLayout.TopToBottom)
        self.capa_tablas_totales.setSpacing(lr.spacing())
        self.capa_tablas_totales.addWidget(self.tabla_totales, 1)
        self.capa_tablas_totales.addWidget(self.tabla_su_suma)
        lr.addLayout(self.capa_tablas_totales)
        lr.addStretch(1)
        self.capa_totales = lr
        self.fila_botones_totales = QHBoxLayout()
        self.fila_botones_totales.setSpacing(8)
        lr.addLayout(self.fila_botones_totales)
        # La tabla de siempre sigue siendo el dato de Copiar, el Listado PDF
        # y las pruebas; en pantalla se ve tabla_totales.
        self.tabla_resumen = QTableWidget(0, len(COLS_RESUMEN_INICIO) + 1
                                          + len(COLS_RESUMEN_FIN), totales_card)
        self.tabla_resumen.setHorizontalHeaderLabels(
            _cabeceras_resumen([]))
        self.tabla_resumen.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_resumen.hide()
        self.resumen_card = totales_card
        self.btn_ver_su_suma.setChecked(bool(ajustes.leer("su_suma_abierta", True)))
        self._ver_su_suma(self.btn_ver_su_suma.isChecked())

        self.split_principal = Divisor(Qt.Vertical)
        self.split_principal.setObjectName("splitPrincipal")
        self.split_principal.addWidget(split)
        self.split_principal.addWidget(totales_card)
        # Mientras no se mueva el divisor a mano, los totales ocupan lo que
        # sus filas (hasta el 40 % del alto); movido, se respeta y se recuerda.
        self._alto_totales_a_mano = bool(ajustes.leer("alto_totales_a_mano", False))
        self.split_principal.splitterMoved.connect(self._divisor_totales_movido)
        # Con la tabla arriba, debajo van la factura y los totales.
        self.split_inferior = Divisor(Qt.Horizontal)
        self.split_inferior.setObjectName("splitInferior")
        self.split_inferior.splitterMoved.connect(
            lambda *_: self._timer_divisores.start())
        # Doble clic en un asa: ese divisor, como venía en la distribución.
        for nombre, divisor in self._divisores():
            divisor.doble_clic.connect(
                lambda nombre=nombre: self._restablecer_divisor(nombre))
        # Los anchos de columna que se ponen a mano, por distribución.
        self.tabla.anchos_a_mano_cambiados.connect(self._guardar_anchos_columnas)
        # «Ocultar» quita los totales; se vuelven a ver en el menú Ver.
        totales_card.setVisible(bool(ajustes.leer("ver_totales_lado", True)))
        cuerpo.addWidget(self.split_principal, 1)

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
        # La tabla cambia de ancho por lo que sea: se reparte otra vez.
        tabla_card.installEventFilter(self)
        # Cada pieza en su sitio según la distribución elegida (sin lote
        # todavía: las columnas de siempre, sin filas, con el alto justo).
        self._aplicar_distribucion(
            ajustes.leer("distribucion", distribucion.POR_DEFECTO), al_arrancar=True)

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
            # Y «Lectura IA» se queda con la flecha (su nombre, en el globo).
            estilo = (Qt.ToolButtonTextBesideIcon if self.factura_card.width() >= 470
                      else Qt.ToolButtonIconOnly)
            if self.btn_plegar_lectura.toolButtonStyle() != estilo:
                self.btn_plegar_lectura.setToolButtonStyle(estilo)
        if hasattr(self, "btn_revisada_factura"):
            # Y «Revisada» se queda en solo el ✓ antes que cortar «Correcta ·
            # siguiente» (su nombre sigue en el globo). Con los anchos reales:
            # dependen de la letra de cada equipo.
            boton = self.btn_revisada_factura
            if boton.text() != "Revisada":
                boton.setText("Revisada")
            margenes = self.factura_card.layout().contentsMargins()
            necesario = (self.titulo_visor.sizeHint().width() + 6
                         + boton.sizeHint().width() + 6
                         + self.btn_correcta_siguiente.sizeHint().width()
                         + margenes.left() + margenes.right())
            if self.factura_card.width() < necesario:
                boton.setText("")
        filtros = (
            self.lbl_mostrar, self.combo_filtro_estado, self.combo_filtro_mes,
            self.caja_tipo, self.txt_buscar, self.combo_filtro_bloque,
            self.combo_filtro_registro,
        )
        acciones = (
            self.btn_siguiente, self.btn_revisada, self.btn_unir_hojas,
            self.btn_por_el_total, self.btn_limpiar_filtros,
            self.btn_quitar_bloque, self.btn_eliminar, self.btn_deshacer_borrado,
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

        self._compactar_acciones(acciones, disponible)
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

    def eventFilter(self, objeto, evento):
        if (objeto is getattr(self, "tabla_card", None)
                and evento.type() == QEvent.Resize
                and hasattr(self, "_timer_herramientas")):
            self._timer_herramientas.start(0)
        return super().eventFilter(objeto, evento)

    def _compactar_acciones(self, acciones, disponible: int) -> None:
        """Las acciones de la tabla, en una fila si se puede.

        Primero con su nombre; si no caben, las de uso ocasional se quedan
        con el icono; y si aún no, las dos de revisar se abrevian. El nombre
        completo sale siempre al pasar el ratón.
        """
        def ancho() -> int:
            # Las ocultas a propósito no cuentan (antes de verse la ventana
            # todas están ocultas, pero no a propósito).
            visibles = [b for b in acciones if not (
                b.testAttribute(Qt.WA_WState_ExplicitShowHide)
                and b.testAttribute(Qt.WA_WState_Hidden))
                and (b is not self.btn_deshacer_borrado or b.isEnabled())]
            return (sum(b.sizeHint().width() for b in visibles)
                    + 8 * max(0, len(visibles) - 1))

        for paso in range(3):
            for boton, (nombre, corto, globo) in self._nombres_acciones.items():
                abreviado = paso == 2 or (paso == 1 and not corto)
                texto = corto if abreviado else nombre
                if boton.text() != texto:
                    boton.setText(texto)
                if abreviado:
                    boton.setToolTip(f"{nombre}\n{globo}" if globo else nombre)
                elif boton.toolTip() != globo:
                    boton.setToolTip(globo)
            if ancho() <= disponible:
                return

    def _actualizar_barra_responsiva(self, ancho: int):
        """Nunca se cortan los textos de la cinta.

        En ventanas estrechas los botones de uso ocasional se quedan solo con
        el icono (su nombre sale al pasar el ratón); en poca altura, iconos
        algo más pequeños.
        """
        if not hasattr(self, "fila_barra_estrecha"):
            return
        # Al cambiar los botones, Windows puede redimensionar la ventana en
        # el acto (resizeEvent dentro de esta misma llamada) y esa llamada
        # anidada pisaría la decisión a medias. Se aplaza y se repite luego
        # con el ancho real.
        if getattr(self, "_ajustando_barra", False):
            self._barra_pendiente = True
            return
        self._ajustando_barra = True
        try:
            self._ajustar_barra(ancho)
        finally:
            self._ajustando_barra = False
        if getattr(self, "_barra_pendiente", False):
            self._barra_pendiente = False
            if not hasattr(self, "_timer_barra"):
                self._timer_barra = QTimer(self)
                self._timer_barra.setSingleShot(True)
                self._timer_barra.timeout.connect(
                    lambda: self._actualizar_barra_responsiva(self.width()))
            self._timer_barra.start(0)

    def _ajustar_barra(self, ancho: int) -> None:
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
        """Cada distribución recuerda sus divisores. Con algo oculto (los
        totales, lo leído) su sitio mide 0: se queda lo de antes."""
        if not hasattr(self, "_distribucion"):
            return
        for nombre, split in self._divisores():
            if not self._divisor_en_uso(nombre):
                continue
            if any(split.widget(i).isHidden() for i in range(split.count())):
                continue
            ajustes.guardar(self._clave_divisor(nombre), split.sizes())

    # ---------- distribución de la pantalla ----------
    def _divisores(self):
        return (("principal", self.split_principal),
                ("revision", self.split_revision),
                ("inferior", self.split_inferior),
                ("factura", self.split_factura))

    def _divisor_en_uso(self, nombre: str) -> bool:
        if nombre == "principal":
            return self.split_principal.count() > 1
        if nombre == "revision":
            return self.split_revision.parent() is not None
        if nombre == "inferior":
            return self.split_inferior.parent() is not None
        return True

    def _clave_divisor(self, nombre: str) -> str:
        # La 4 sigue con las claves de antes.
        if self._distribucion.clave == "cuadre":
            return {"principal": "split_principal", "revision": "split_revision_v5",
                    "factura": "split_factura_h"}.get(nombre, f"split_{nombre}")
        return f"divisor_{self._distribucion.clave}_{nombre}"

    def _elegir_distribucion(self, clave: str) -> None:
        """Desde Ver → Distribución de la pantalla (se recuerda)."""
        actual = getattr(self, "_distribucion", None)
        if actual is not None and actual.clave == clave:
            return
        self._guardar_divisores()
        ajustes.guardar("distribucion", clave)
        self._aplicar_distribucion(clave)
        self.lbl_estado.setText(
            f"Distribución {self._distribucion.titulo}: {self._distribucion.descripcion}")

    def _aplicar_distribucion(self, clave: str, al_arrancar: bool = False) -> None:
        """Pone cada pieza (facturas, factura, totales) donde va en esa
        distribución, y la factura y los totales con su forma."""
        d = distribucion.buscar(clave)
        self._distribucion = d
        self._colocar_piezas(d.colocacion)
        # La factura: la hoja arriba y lo leído debajo, o uno al lado del otro.
        self.split_factura.setOrientation(
            Qt.Vertical if d.factura_vertical else Qt.Horizontal)
        self.panel_lectura.layout().setContentsMargins(
            *((0, 4, 0, 0) if d.factura_vertical else (4, 0, 0, 0)))
        self._datos_sobre_hoja = d.datos_sobre_hoja
        self.panel_progreso.setVisible(d.progreso)
        if not al_arrancar and self.btn_plegar_lectura.isChecked() != d.lectura_plegada:
            # Al elegirla, lo leído como en su prototipo (se puede cambiar).
            self.btn_plegar_lectura.setChecked(d.lectura_plegada)
        else:
            self._aplicar_plegado(self._plegado_efectivo())
        self._poner_totales_en_columna(d.totales_en_columna)
        self._actualizar_columnas()
        self.tabla.poner_anchos_a_mano(ajustes.leer(f"columnas_{d.clave}", {}))
        self._poner_tamanos_distribucion()
        accion = self.acciones_distribucion.get(d.clave)
        if accion is not None and not accion.isChecked():
            accion.setChecked(True)
        if al_arrancar:
            # Aún sin colocar: los divisores se reparten al verse la ventana
            # (si no, irían tal cual y Qt dejaría en su mínimo lo que estira).
            self._tamanos_al_mostrar = True
            self._pintar_tabla_totales([], False, [])
            return
        self._pintar_resumen()
        self._distribuir_herramientas(self.width())
        if 0 <= self.tabla.currentRow() < len(self.filas):
            self._pintar_recuadros()

    def _colocar_piezas(self, colocacion: str) -> None:
        principal, revision = self.split_principal, self.split_revision
        inferior = self.split_inferior
        tabla, factura, totales = self.tabla_card, self.factura_card, self.totales_card
        # Lo que no se usa se descuelga (sin borrarlo) para no dejar huecos.
        if colocacion == distribucion.TABLA_ARRIBA:
            inferior.insertWidget(0, factura)
            inferior.insertWidget(1, totales)
            principal.insertWidget(0, tabla)
            principal.insertWidget(1, inferior)
            revision.setParent(None)
            estiramiento = {principal: (1, 1), inferior: (1, 0)}
        else:
            revision.insertWidget(0, tabla)
            revision.insertWidget(1, factura)
            if colocacion == distribucion.COLUMNAS:
                revision.insertWidget(2, totales)
                principal.insertWidget(0, revision)
                estiramiento = {principal: (1,), revision: (1, 1, 0)}
            else:
                principal.insertWidget(0, revision)
                principal.insertWidget(1, totales)
                estiramiento = {principal: (1, 0), revision: (1, 1)}
            inferior.setParent(None)
        for split, factores in estiramiento.items():
            for i, factor in enumerate(factores):
                split.setStretchFactor(i, factor)

    def _restablecer_divisor(self, nombre: str) -> None:
        """Ese divisor, como venía en la distribución (olvida lo movido)."""
        if not self._divisor_en_uso(nombre):
            return
        if nombre == "principal" \
                and self._distribucion.colocacion == distribucion.TOTALES_ABAJO:
            # Los totales vuelven a medir lo justo para sus filas.
            self._alto_totales_a_mano = False
            ajustes.guardar("alto_totales_a_mano", False)
        ajustes.guardar(self._clave_divisor(nombre), None)
        self._poner_tamanos_distribucion(solo=nombre)
        self._guardar_divisores()

    def _restablecer_pantalla(self) -> None:
        """Ver → Volver al reparto de esta distribución: los divisores y los
        anchos de las columnas, como venían."""
        for nombre, _divisor in self._divisores():
            self._restablecer_divisor(nombre)
        self.tabla.ajustar_al_contenido()
        self.lbl_estado.setText(
            f"Distribución {self._distribucion.titulo}: tamaños como venían.")

    def _guardar_anchos_columnas(self, anchos: dict) -> None:
        if hasattr(self, "_distribucion"):
            ajustes.guardar(f"columnas_{self._distribucion.clave}", anchos or None)

    def _poner_tamanos_distribucion(self, solo: str | None = None) -> None:
        d = self._distribucion
        for nombre, split in self._divisores():
            if not self._divisor_en_uso(nombre) or solo not in (None, nombre):
                continue
            defecto = list(d.tamanos.get(nombre) or [600] * split.count())
            if nombre == "principal" and d.colocacion == distribucion.TOTALES_ABAJO:
                # Los totales, lo justo para sus filas (salvo si se movió).
                defecto = [620, 240]
                tamanos = (self._tamanos_divisor(self._clave_divisor(nombre), defecto)
                           if self._alto_totales_a_mano else defecto)
            else:
                tamanos = self._tamanos_divisor(self._clave_divisor(nombre), defecto)
            if len(tamanos) != split.count():
                continue
            # En proporción al sitio de ahora (Qt, si no, quita lo que sobra
            # solo de las piezas que estiran y las deja en su mínimo).
            actual = sum(split.sizes())
            if actual > 0:
                escala = actual / sum(tamanos)
                tamanos = [max(1, round(t * escala)) for t in tamanos]
            split.setSizes(tamanos)
        self._encajar_totales()

    def _poner_totales_en_columna(self, en_columna: bool) -> None:
        """Los totales a lo ancho (una fila por ámbito, «Su suma» debajo) o
        en columna (un importe por fila, «Su suma» al lado)."""
        self.tabla_su_suma.poner_vertical(en_columna)
        filas = self.tabla_totales.verticalHeader()
        cabecera = self.tabla_totales.horizontalHeader()
        if en_columna:
            filas.setSectionResizeMode(QHeaderView.Fixed)
            filas.setDefaultSectionSize(ALTO_FILA_COLUMNA)
            self.capa_tablas_totales.setDirection(QBoxLayout.LeftToRight)
            alineacion = Qt.AlignTop
        else:
            filas.setSectionResizeMode(QHeaderView.Interactive)
            filas.setDefaultSectionSize(24)
            cabecera.setMinimumHeight(0)
            cabecera.setMaximumHeight(16_777_215)
            self.capa_tablas_totales.setDirection(QBoxLayout.TopToBottom)
            alineacion = Qt.Alignment()
        for widget in (self.tabla_totales, self.tabla_su_suma):
            self.capa_tablas_totales.setAlignment(widget, alineacion)
        # En columna, las tablas se quedan el alto que haya (hasta el de sus
        # filas); a lo ancho, lo justo y el resto queda debajo.
        capa = self.capa_totales
        indice = capa.indexOf(self.capa_tablas_totales)
        capa.setStretch(indice, 1 if en_columna else 0)
        capa.setStretch(indice + 1, 0 if en_columna else 1)
        self._colocar_cabecera_totales(en_columna)
        self._politica_barras_totales()

    def _colocar_cabecera_totales(self, en_columna: bool) -> None:
        """A lo ancho, todo en la cabecera. En columna no cabe: el veredicto
        va debajo del título y los botones, al pie."""
        titulo, cerrar = self.lbl_resumen_titulo, self.btn_cerrar_totales
        ambito = self.tabla_su_suma.lbl_ambito
        veredicto = self.tabla_su_suma.lbl_veredicto
        ver_suma, copiar = self.btn_ver_su_suma, self.btn_copiar_totales
        listado = self.btn_listado_totales
        for capa in (self.cabecera_totales, self.fila_info_totales,
                     self.fila_botones_totales):
            while capa.count():
                capa.takeAt(0)
        # En columna no cabe «Su suma a mano» con Copiar y Listado PDF.
        ver_suma.setText("Su suma" if en_columna else "Su suma a mano")
        if en_columna:
            self.cabecera_totales.addWidget(titulo, 1)
            self.cabecera_totales.addWidget(cerrar)
            self.fila_info_totales.addWidget(veredicto)
            self.fila_info_totales.addWidget(ambito, 1)
            self.fila_botones_totales.addWidget(ver_suma)
            self.fila_botones_totales.addStretch(1)
            self.fila_botones_totales.addWidget(copiar)
            self.fila_botones_totales.addWidget(listado)
        else:
            for widget, estirar in ((titulo, 0), (ambito, 1), (veredicto, 0),
                                    (ver_suma, 0), (copiar, 0), (listado, 0),
                                    (cerrar, 0)):
                self.cabecera_totales.addWidget(widget, estirar)

    def _politica_barras_totales(self) -> None:
        """La barra que va con «Su suma» la lleva ella; sin «Su suma», los
        totales llevan las dos."""
        tabla = self.tabla_totales
        con_suma = self.btn_ver_su_suma.isChecked()
        if self.tabla_su_suma.vertical:
            tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            tabla.setVerticalScrollBarPolicy(
                Qt.ScrollBarAlwaysOff if con_suma else Qt.ScrollBarAsNeeded)
        else:
            tabla.setHorizontalScrollBarPolicy(
                Qt.ScrollBarAlwaysOff if con_suma else Qt.ScrollBarAsNeeded)
            tabla.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def _mover_barra(self, barra, valor: int, vertical: bool) -> None:
        """Las dos tablas de los totales, juntas en el sentido de «Su suma»."""
        if self.tabla_su_suma.vertical == vertical:
            barra.setValue(valor)

    def showEvent(self, evento):
        super().showEvent(evento)
        if getattr(self, "_tamanos_al_mostrar", False):
            self._tamanos_al_mostrar = False
            self._poner_tamanos_distribucion()
        self._encajar_totales()
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
        # El listado de Aplifisa del periodo que se quiera (del 1 de enero a
        # hoy, el año entero…) frente a todo lo guardado en PDF del cliente.
        self.accion_cuadre_anual = comprobar.addAction(
            "Cuadre con Aplifisa: lo guardado en PDF…",
            lambda: self._cuadre_anual())
        self.accion_cuadre_anual.setShortcut(QKeySequence("Ctrl+Shift+R"))
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
        ver.addSeparator()
        # Los cinco prototipos del lienzo, para elegir el que mejor vaya.
        menu_distribucion = ver.addMenu("Distribución de la pantalla")
        menu_distribucion.setToolTipsVisible(True)
        self.grupo_distribucion = QActionGroup(self)
        self.grupo_distribucion.setExclusive(True)
        self.acciones_distribucion = {}
        for d in distribucion.DISTRIBUCIONES:
            accion = menu_distribucion.addAction(d.titulo_menu)
            accion.setCheckable(True)
            accion.setToolTip(d.descripcion)
            accion.setStatusTip(d.descripcion)
            accion.setShortcut(QKeySequence(f"Ctrl+{d.numero}"))
            accion.triggered.connect(
                lambda _marcada=False, clave=d.clave: self._elegir_distribucion(clave))
            self.grupo_distribucion.addAction(accion)
            self.acciones_distribucion[d.clave] = accion
        # Cada pieza se ensancha arrastrando su asa y cada columna, su borde;
        # esto lo deja todo como venía.
        self.accion_ajustar_columnas = ver.addAction(
            "Ajustar las columnas a lo que ponen", lambda: self.tabla.ajustar_al_contenido())
        self.accion_ajustar_columnas.setStatusTip(
            "Olvida los anchos de columna puestos a mano: cada una, lo que su contenido.")
        self.accion_restablecer = ver.addAction(
            "Volver al reparto de esta distribución", self._restablecer_pantalla)
        self.accion_restablecer.setStatusTip(
            "Los divisores y las columnas, como venían en la distribución elegida.")
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
        config.addAction("Régimen de IVA de este cliente…",
                         self._elegir_regimen_recargo)
        config.addAction("Copias de seguridad…", self._copias_de_seguridad)

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

    def _copia_diaria(self) -> None:
        """Una copia de seguridad al día de lo que el programa recuerda.

        Con el registro vacío y una copia que sí tiene facturas (otro
        ordenador, o se estropeó), se ofrece restaurarla: una vez por cada
        equipo del que venga, para no repetirlo cada día a quien comparte la
        carpeta con otro ordenador a propósito."""
        try:
            buena = copias.mejor_que_la_actual()
            avisados = ajustes.leer("registro_vacio_avisado", []) or []
            if buena and buena.equipo not in avisados:
                ajustes.guardar("registro_vacio_avisado",
                                list(avisados) + [buena.equipo])
                self._avisar(
                    "El registro de facturas de este ordenador está vacío, "
                    f"pero hay una copia de seguridad del {buena.fecha:%d/%m/%Y} "
                    f"con {buena.facturas} factura(s). Si ha cambiado de "
                    "ordenador o se ha estropeado, restáurela en "
                    "Configuración → Copias de seguridad.", AVISO, segundos=0)
            copias.diaria()
        except Exception as error:
            errores.apuntar("Copia de seguridad diaria:\n"
                            + traceback.format_exc())
            self._avisar(f"No se pudo hacer la copia de seguridad de hoy "
                         f"({error}). Se intentará al volver a abrir; también "
                         "puede hacerla en Configuración → Copias de "
                         "seguridad.", AVISO, segundos=0)

    def _copias_de_seguridad(self) -> None:
        from facturas_excel.dialogo_copias import DialogoCopias
        DialogoCopias(self).exec()

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
                copias.hacer("antes de actualizar")
            except Exception:
                errores.apuntar("Copia antes de actualizar:\n"
                                + traceback.format_exc())
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

    def _guardar_muestra_revision_automatica(self) -> None:
        """La muestra de revisión de después de cada cambio, como mucho una
        por minuto: con un lote grande es una foto de todas las líneas (unos
        MB) y se hacía en la ventana 0,8 s después de cada corrección y de
        cada bloque leído. Lo que se cambie mientras tanto entra en la del
        minuto siguiente. Antes de vaciar, eliminar, unir hojas o exportar,
        y al cerrar, se sigue guardando en el momento."""
        falta = self._ultima_muestra + MUESTRA_CADA_S - time.monotonic()
        if falta > 0:
            # No se reinicia con cada cambio: así llega aunque no se pare.
            if not self._timer_muestra_minuto.isActive():
                self._timer_muestra_minuto.start(int(falta * 1000) + 1)
            return
        self._guardar_muestra_revision()

    def _guardar_muestra_revision(self):
        self._timer_muestras.stop()
        self._timer_muestra_minuto.stop()
        self._ultima_muestra = time.monotonic()
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
        self._timer_sesion.stop()
        datos = self._datos_sesion()
        if datos is None:
            sesion.borrar()
            return
        self._guardar_muestra_revision()
        sesion.guardar(datos)

    def _guardar_sesion_automatica(self) -> None:
        """El guardado de cada poco: la foto del lote se toma aquí y se
        escribe aparte, sin parar la pantalla. Si falla, se avisa una vez."""
        error = sesion.ultimo_error()
        try:
            datos = self._datos_sesion()
            if datos is None:
                sesion.borrar()
            else:
                sesion.guardar_en_segundo_plano(datos)
        except Exception as fallo:     # p. ej. algo del lote que no se guarda
            error = str(fallo) or type(fallo).__name__
            errores.apuntar("Guardado automático del lote:\n"
                            + traceback.format_exc())
        if error and not self._aviso_sesion_dado:
            self._aviso_sesion_dado = True
            self._avisar("No se puede guardar el lote mientras trabaja "
                         f"({error}). Se intentará otra vez al cerrar; "
                         "exporte lo revisado en cuanto pueda.", AVISO,
                         segundos=0)

    def _datos_sesion(self) -> dict | None:
        """Lo que se guarda del lote (None si está vacío)."""
        if not self._bloques and not self.filas:
            return None
        filas = [{
            "png": registro.png, "factura": registro.factura,
            "aviso": registro.aviso or "", "bloque": registro.bloque or "",
            "fuentes": registro.fuentes, "tipo": registro.tipo,
            "cuenta": registro.factura.concepto or "",
            "gxx": registro.factura.subclave or "",
        } for registro in self.filas]
        return {
            "bloques": self._bloques,
            "filas": filas,
            "cliente_nif": getattr(self, "_cliente_nif", ""),
            "cliente_nombre": getattr(self, "_cliente_nombre", ""),
            "hay_recargo": getattr(self, "_hay_recargo", False),
            "regimen_recargo": self.combo_recargo.currentData(),
            "periodo_modo": getattr(self, "_periodo_manual_valor", "auto"),
            "localizaciones": {clave: localizar.a_guardar(cajas) for clave, cajas
                               in self._localizaciones.items()},
            "su_suma": self.tabla_su_suma.valores(),
        }

    def _avisar_sesion_apartada(self, ruta: str) -> None:
        if not ruta:
            return
        self._avisar(
            "No se pudo abrir el lote de la última vez (puede ser de otra "
            "versión). No se ha borrado: queda guardado aparte como "
            f"«{os.path.basename(ruta)}», en la carpeta de datos del "
            "programa, para poder recuperarlo.", AVISO, segundos=0)

    def _restaurar_sesion(self) -> None:
        datos = sesion.cargar()
        if datos is None:
            self._avisar_sesion_apartada(sesion.apartada())
            if sesion.intocable():
                self._avisar(
                    "No se pudo abrir el lote de la última vez, y su fichero "
                    "está bloqueado (¿otra copia del programa abierta, o el "
                    "antivirus?). No se toca: cierre el programa y vuelva a "
                    "abrirlo.", AVISO, segundos=0)
        if not datos or not datos.get("bloques"):
            return
        try:
            self._bloques = datos["bloques"]
            # Las sesiones de versiones anteriores traen la imagen de cada
            # hoja en bytes: se pasan a disco (una sola vez; el próximo
            # guardado ya va sin ellas) y el lote se queda con su asa.
            convertir = imagen_hoja.Conversor()
            convertir.bloques(self._bloques)
            for fila in datos.get("filas", []):
                fila["png"] = convertir(fila.get("png"))
            self._cliente_nif = datos.get("cliente_nif", "")
            self._cliente_nombre = datos.get("cliente_nombre", "")
            self._periodo_manual_valor = datos.get("periodo_modo", "auto")
            self._localizaciones = {
                clave: localizar.de_guardado(cajas)
                for clave, cajas in (datos.get("localizaciones") or {}).items()}
            # El régimen del lote guardado; si no traía recargo, el del cliente
            # (que puede estar en recargo aunque el lote no lo lleve impreso).
            if datos.get("hay_recargo"):
                regimen = datos.get("regimen_recargo", DESGLOSE)
            else:
                regimen = regimen_recargo(self._cliente_nif)
            self._hay_recargo = bool(datos.get("hay_recargo")) or (
                regimen == TOTAL and puede_estar_en_recargo(self._cliente_nif)
            ) or regimen == EXENTO
            self._mostrar_recargo(regimen)
            # Un lote guardado con otro criterio (de antes de la 1.22.1: un
            # minorista sin recargo impreso, o una sociedad «por el total»)
            # se rehace desde lo leído al abrirlo.
            antes_por_el_total = bool(datos.get("hay_recargo")) and \
                datos.get("regimen_recargo") in (TOTAL, EXENTO)
            self._actualizar_combo_bloques()
            self._reparar_abonos_emitidos_guardados(datos.get("filas", []))
            # Lotes de antes: el mismo NIF podía quedarse con dos nombres.
            unificadas = unificar_nombres_por_nif(
                [x for fila in datos.get("filas", [])
                 for x in (fila["factura"], *(fila.get("fuentes") or ()))]
                + [f for bloque in self._bloques
                   for _, pr in bloque.get("procesadas", []) for f in pr.facturas],
                nombres_guardados(solo_a_mano=True))
            # Lotes de la 1.24.0: una línea «revisada» con un nombre que trae
            # un carácter invisible se revisó sin el aviso del nombre (no
            # existía) y saldría a Aplifisa sin esa letra: vuelve a pendiente.
            for fila in datos.get("filas", []):
                for x in (fila["factura"], *(fila.get("fuentes") or ())):
                    if tiene_invisibles(x.nombre):
                        x.revision_confirmada = False
            # Todas las líneas de una vez (de una en una, abrir con 800
            # líneas tardaba más de 5 segundos).
            self._poner_filas([
                self._fila_guardada(
                    fila["png"], fila["factura"], fila["tipo"],
                    fila["cuenta"], fila["gxx"], fila.get("aviso", ""),
                    fila.get("bloque", ""), fila.get("fuentes"))
                for fila in datos.get("filas", [])])
            if self._por_el_total() != antes_por_el_total:
                self._rellenar_tabla()
            self._pintar_cliente()
            self._revalidar_todo()
            # Lo tecleado en «Su suma», aparte: nunca puede tirar el lote.
            try:
                self.tabla_su_suma.poner_valores(datos.get("su_suma"))
            except Exception:
                self.tabla_su_suma.limpiar()
            hay_datos = self.tabla.rowCount() > 0
            self.btn_gastos.setEnabled(hay_datos)
            self.btn_registro.setEnabled(hay_datos)
            self.btn_cliente.setEnabled(bool(self._bloques))
            if hay_datos:
                self.tabla.selectRow(0)
            cambiadas = {id(f) for f, _antes, _despues in unificadas}
            n_nombres = sum(1 for fila in datos.get("filas", [])
                            if id(fila["factura"]) in cambiadas)
            self.lbl_estado.setText(
                f"Sesión recuperada: {len(self._bloques)} bloque(s) y "
                f"{self.tabla.rowCount()} línea(s)."
                + (f"  {n_nombres} línea(s) con el nombre unificado por NIF."
                   if n_nombres else ""))
        except Exception:
            # Una sesión antigua o dañada nunca debe impedir abrir el programa,
            # pero tampoco se pierde: se aparta y se avisa.
            errores.apuntar("Recuperar el lote de la última vez:\n"
                            + traceback.format_exc())
            self._bloques = []
            self.tabla.setRowCount(0)
            self.filas = []
            self._limpiar_visor()
            self._avisar_sesion_apartada(sesion.apartar())

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
        # Una lectura esperando a Gemini (pide ir más despacio) deja de
        # esperar: si no, la ventana se quedaba colgada al cerrar.
        worker = getattr(self, "worker", None)
        if worker is not None and worker.isRunning() and hasattr(worker, "cancelar"):
            worker.cancelar()
        # No destruir QThreads vivos (abortaria el proceso)
        self.esperar_hilos()
        try:
            # Lo que quedaba en la cola no se va a leer (la cola no se
            # guarda): sus partes temporales no se quedan ocupando disco.
            for elemento in [self._elemento_cola_actual, *self._cola]:
                if elemento:
                    self._limpiar_parte_interna(elemento)
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
        if hasattr(self, "totales_card"):
            # QSplitter recuerda el alto de los totales ocultos y lo devuelve.
            self.totales_card.setVisible(bool(visible))
            if not hasattr(self, "_timer_tras_resumen"):
                self._timer_tras_resumen = QTimer(self)
                self._timer_tras_resumen.setSingleShot(True)
                self._timer_tras_resumen.timeout.connect(self._tras_ver_resumen)
            self._timer_tras_resumen.start(0)
        if hasattr(self, "accion_resumen") and self.accion_resumen.isChecked() != visible:
            self.accion_resumen.setChecked(bool(visible))

    def _tras_ver_resumen(self) -> None:
        """Ya colocado todo: totales con alto para leerse."""
        if self._distribucion.colocacion != distribucion.TOTALES_ABAJO:
            return
        if not self._alto_totales_a_mano:
            self._encajar_totales()
            return
        tamanos = self.split_principal.sizes()
        necesario = self.totales_card.sizeHint().height()
        if self.totales_card.isVisible() and len(tamanos) == 2 \
                and tamanos[1] < min(necesario, 160):
            total = sum(tamanos)
            self.split_principal.setSizes([max(200, total - necesario), necesario])

    def _divisor_totales_movido(self, *_):
        """Movido a mano: desde ahora manda el usuario (y se recuerda)."""
        if (self._distribucion.colocacion == distribucion.TOTALES_ABAJO
                and not self._alto_totales_a_mano):
            self._alto_totales_a_mano = True
            ajustes.guardar("alto_totales_a_mano", True)
        self._timer_divisores.start()

    def _encajar_totales(self) -> None:
        """Los totales, con el alto de sus filas (al filtrar salen más),
        pero nunca más del 40 % del alto: en un portátil la tabla de
        facturas y la hoja necesitan sitio. Si el usuario ha movido el
        divisor, no se toca.

        Se hace en cuanto Qt ha recolocado lo cambiado (si no, el divisor
        se queda con el mínimo de antes) y una sola vez aunque se pida
        varias."""
        if not hasattr(self, "_timer_encajar"):
            self._timer_encajar = QTimer(self)
            self._timer_encajar.setSingleShot(True)
            self._timer_encajar.timeout.connect(self._encajar_totales_ahora)
        self._timer_encajar.start(0)

    def _encajar_totales_ahora(self) -> None:
        if (not hasattr(self, "split_principal")
                or getattr(self, "_alto_totales_a_mano", True)
                or getattr(self, "_distribucion", None) is None
                or self._distribucion.colocacion != distribucion.TOTALES_ABAJO
                or self.tabla_su_suma.vertical
                or not self.totales_card.isVisible()):
            return
        tamanos = self.split_principal.sizes()
        total = sum(tamanos)
        if len(tamanos) != 2 or total <= 0:
            return
        # Lo justo para todas las filas: cabecera, tabla entera y «Su suma»
        # (con las medidas de ahora: el mínimo que da Qt puede ir atrasado).
        capa = self.totales_card.layout()
        margenes = capa.contentsMargins()
        # Lo que se ve encima de las tablas (cabecera y, si las hay, las
        # líneas de progreso y del veredicto) y «Su suma» debajo.
        partes = [capa.itemAt(i).sizeHint().height() for i in range(capa.count())
                  if not capa.itemAt(i).isEmpty()
                  and capa.itemAt(i).spacerItem() is None
                  and capa.itemAt(i).layout() is not self.capa_tablas_totales]
        if not self.tabla_su_suma.isHidden():
            partes.append(self.tabla_su_suma.maximumHeight())
        resto = (margenes.top() + margenes.bottom() + sum(partes)
                 + capa.spacing() * len(partes)
                 + 2 * self.totales_card.frameWidth())
        alto = max(resto + self.tabla_totales.minimumHeight(),
                   min(resto + self.tabla_totales.maximumHeight(), int(total * 0.4)))
        if abs(alto - tamanos[1]) > 2:
            self.split_principal.setSizes([total - alto, alto])

    def _ver_su_suma(self, visible: bool) -> None:
        """«Su suma a mano» se puede quitar si no se usa (se recuerda)."""
        ajustes.guardar("su_suma_abierta", bool(visible))
        self.tabla_su_suma.setVisible(bool(visible))
        self.tabla_su_suma.lbl_ambito.setVisible(bool(visible))
        self.tabla_su_suma.lbl_veredicto.setVisible(bool(visible))
        self.btn_ver_su_suma.setArrowType(Qt.DownArrow if visible else Qt.RightArrow)
        if hasattr(self, "tabla_totales"):
            # Sin «Su suma», las barras para llegar a todo son las de los totales.
            self._politica_barras_totales()
            self._ajustar_alto_totales()
        self._encajar_totales()

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
            self.tabla_su_suma.limpiar()
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
        self._cliente_elegido_lote = ""
        self._periodo_manual_valor = "auto"
        self._periodo_lote = PeriodoLote()
        self.txt_buscar.clear()
        self._invalidar_contraste_registro()
        self.btn_deshacer_borrado.setEnabled(False)
        self.btn_deshacer_borrado.setVisible(False)
        self.btn_cliente.setEnabled(False)
        self._hay_recargo = False
        self.fila_recargo.setVisible(False)
        self.combo_filtro_estado.setCurrentIndex(0)
        self.combo_filtro_bloque.setCurrentIndex(0)
        self.combo_filtro_mes.setCurrentIndex(0)
        self.tabla_su_suma.limpiar()
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
        self._soltar_lote_vaciado()

    def _soltar_lote_vaciado(self) -> None:
        """Que «Vaciar todo» devuelva de verdad la memoria del lote.

        Antes se quedaba casi toda: el «Deshacer» de la banda de avisos
        retenía todas las filas, el último «¿De dónde sale?» sus hojas, y la
        caché de MuPDF lo que se hubiera dibujado (con 337 líneas, de 670 MB
        solo se soltaban 9)."""
        if hasattr(self, "banda"):
            # Deshacer algo del lote vaciado ya no tiene sentido.
            self.banda.olvidar_deshacer()
        hilo = getattr(self, "_hilo_localizar", None)
        if hilo is not None and not hilo.isRunning():
            self._hilo_localizar = None
        pdf.vaciar_cache()
        gc.collect()

    def _por_el_total(self) -> bool:
        """El cliente registra sus compras por el total factura: minorista en
        recargo (nunca una sociedad: la ley no la deja estar en recargo) o
        actividad exenta, sin derecho a deducir. Todas, traigan o no el
        recargo impreso."""
        if not getattr(self, "_hay_recargo", False):
            return False
        regimen = self.combo_recargo.currentData()
        return regimen == EXENTO or (
            regimen == TOTAL
            and puede_estar_en_recargo(getattr(self, "_cliente_nif", "")))

    def _motivo_por_el_total(self) -> str:
        """Por qué el cliente registra sus compras por el total (texto)."""
        if self.combo_recargo.currentData() == EXENTO:
            return "cliente sin derecho a deducir el IVA"
        return "cliente en recargo de equivalencia"

    def _rellenar_tabla(self):
        self._invalidar_contraste_registro()
        # Un NIF, un nombre, también entre tacos leídos por separado.
        unificar_nombres_por_nif(
            [f for bloque in self._bloques for _, pr in bloque["procesadas"]
             for f in pr.facturas], nombres_guardados(solo_a_mano=True))
        filas = filas_de_bloques(
            self._bloques, self._por_el_total(), a_total_factura)
        self._conservar_resumenes_corregidos(filas)
        # Una línea resumen conservada (recargo «por el total») trae el
        # nombre de antes: con el de sus líneas y el resto del NIF.
        unificar_nombres_por_nif(
            [x for fila in filas for x in (fila.factura, *(fila.fuentes or ()))],
            nombres_guardados(solo_a_mano=True))
        if self._solo_se_anaden(filas):
            self._anadir_filas(filas)
        else:
            self._poner_filas(filas)

    def _solo_se_anaden(self, filas) -> bool:
        """Si las líneas de ahora son el principio de `filas` tal cual: entonces
        basta con añadir las que faltan (un bloque más de la cola) en vez de
        rehacer la tabla entera, que con 800 líneas tardaba segundos en cada
        bloque.

        Tal cual quiere decir que rehaciéndola saldría lo mismo: cada línea
        con la misma factura (el mismo objeto, no una copia), la misma hoja,
        el mismo tipo, aviso (sin lo que ya calcula cada revisión) y bloque y
        las mismas líneas originales. Si no, se rehace entera como siempre:
        un cambio de cliente vuelve a montar las facturas, «por el total»
        las vuelve a resumir, una unión de hojas entre bloques cambia la
        última del bloque anterior, una decisión sobre un NIF cambia los
        avisos, la tabla está ordenada por una columna, se quitó un bloque…"""
        viejas = self.filas
        if not viejas or len(filas) < len(viejas) \
                or self.tabla.rowCount() != len(viejas):
            return False
        if self.tabla.editando():
            # Rehacerla cierra la celda que se está escribiendo sin apuntar
            # lo escrito; añadiendo, se apuntaría a medias.
            return False
        for vieja, nueva in zip(viejas, filas):
            if (vieja.factura is not nueva.factura or vieja.png != nueva.png
                    or vieja.tipo != nueva.tipo or vieja.bloque != nueva.bloque
                    or vieja.aviso not in (nueva.aviso, aviso_sin_calculados(nueva.aviso))
                    or len(vieja.fuentes) != len(nueva.fuentes)
                    or any(x is not y for x, y in zip(vieja.fuentes, nueva.fuentes))):
                return False
        return True

    def _anadir_filas(self, filas) -> None:
        """Pone `filas` sin rehacer la tabla: las celdas de las líneas que ya
        estaban se quedan y solo se crean las de las nuevas, al final.

        Queda lo mismo que rehaciéndola: el lote pasa a ser `filas` (líneas
        recién hechas, que la revisión que sigue vuelve a comprobar), las
        de antes se repintan con ellas (un nombre unificado por NIF en el
        bloque nuevo también cambia facturas de antes) y la selección y el
        desplazamiento vuelven al principio, como al rehacerla (la primera
        fila que se ve la elige el filtro)."""
        tabla = self.tabla
        antes = len(self.filas)
        tabla.blockSignals(True)
        self.filas = list(filas)
        for r in range(antes):
            tabla.pintar(r, self.filas[r])
        tabla.selectionModel().clear()
        tabla.verticalScrollBar().setValue(0)
        tabla.anadir_filas(self.filas[antes:], self._on_tipo_cambiado)
        self._actualizar_columnas()
        tabla.blockSignals(False)

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

        def tocada(f):
            # Corregida o revisada por una persona: eso no se rehace.
            return (f.edicion_manual or f.revision_confirmada
                    or getattr(f, "revision_corregida", False))

        guardados = getattr(self, "_resumenes_guardados", None)
        if guardados is None:
            guardados = self._resumenes_guardados = {}
        antes = {}
        for fila in self.filas:
            if es_copia(fila):
                antes.setdefault(clave(fila), []).append(fila.factura)
        ahora = {}
        for fila in filas:
            if es_copia(fila):
                ahora.setdefault(clave(fila), []).append(fila)
        # Una línea resumen que deja de estar («Por el total» quitado, su
        # deshacer…) se guarda por si vuelve: con su corrección o revisión.
        for k, previas in antes.items():
            if k not in ahora and any(tocada(f) for f in previas):
                guardados[k] = previas
        for k, grupo in ahora.items():
            previas = antes.get(k) or guardados.get(k)
            if previas and len(previas) == len(grupo) and any(
                    tocada(f) for f in previas):
                for fila, factura in zip(grupo, previas):
                    fila.factura = factura
                guardados.pop(k, None)

    def _poner_filas(self, filas) -> None:
        """Sustituye las filas del lote y las pinta de nuevo.

        Todas de una vez y las columnas de recargo y retenciones una sola
        vez al final: antes, por cada fila, se insertaba una fila más en la
        tabla y se volvía a recorrer el lote entero para decidir las
        columnas (con 800 líneas, más de 4 segundos)."""
        self.tabla.blockSignals(True)
        self.filas = list(filas)
        self.tabla.poner_filas(self.filas, self._on_tipo_cambiado)
        if self.filas:
            self._actualizar_columnas()
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

        El minorista en recargo no presenta el 303: no paga ni deduce IVA, asi
        que TODAS sus compras van por el total, tambien las que no traen
        recargo impreso (telefono, reparaciones, publicidad...). Lo mismo el
        cliente con actividad exenta (sin derecho a deducir). Por eso manda el
        regimen guardado del cliente, no solo lo que traiga el lote.
        """
        cuantas = self._facturas_con_recargo()
        nif = getattr(self, "_cliente_nif", "")
        sociedad = not puede_estar_en_recargo(nif)
        guardado = regimen_recargo(nif)
        if sociedad and guardado == TOTAL:
            # Una sociedad no puede estar en recargo (art. 148 de la Ley del
            # IVA), aunque se guardara así en una versión anterior.
            guardado = DESGLOSE
        if cuantas and not guardado and nif and not sociedad:
            dialogo = DialogoRecargo(getattr(self, "_cliente_nombre", ""),
                                     cuantas, self)
            guardado = (dialogo.elegido() if dialogo.exec() == QDialog.Accepted
                        else DESGLOSE)
            guardar_regimen_recargo(nif, guardado,
                                    getattr(self, "_cliente_nombre", ""))
            self._perfil_columnas = (None,)
        self._hay_recargo = bool(cuantas) or guardado in (TOTAL, EXENTO)
        self._mostrar_recargo(guardado)

    def _mostrar_recargo(self, regimen: str) -> None:
        """La fila del régimen de IVA, con el porqué de que esté a la vista."""
        self.fila_recargo.setVisible(self._hay_recargo)
        sociedad = not puede_estar_en_recargo(getattr(self, "_cliente_nif", ""))
        # Una sociedad no puede elegir el recargo (sí la actividad exenta).
        modelo = self.combo_recargo.model()
        opcion_total = modelo.item(self.combo_recargo.findData(TOTAL))
        if opcion_total is not None:
            opcion_total.setEnabled(not sociedad)
        if sociedad and regimen == TOTAL:
            regimen = DESGLOSE
        if regimen == EXENTO:
            self.lbl_hay_recargo.setText("Cliente sin derecho a deducir")
            self.lbl_hay_recargo.setToolTip(
                "Actividad exenta (médico, academia…, art. 20 de la Ley del "
                "IVA): no deduce el IVA de sus compras (art. 94), así que todas "
                "van por el total factura.")
        elif sociedad and self._facturas_con_recargo():
            self.lbl_hay_recargo.setText(
                "Recargo cobrado a una sociedad: no le corresponde")
            self.lbl_hay_recargo.setToolTip(
                "La Ley del IVA (art. 148) deja el recargo de equivalencia solo "
                "a personas físicas y comunidades de bienes. Sus compras van "
                "con el desglose normal; el recargo que le haya cobrado un "
                "proveedor no corresponde: pídale la factura rectificada.")
        elif self._facturas_con_recargo():
            self.lbl_hay_recargo.setText("Factura(s) con recargo detectado")
            self.lbl_hay_recargo.setToolTip(
                "El lote trae facturas con recargo de equivalencia.")
        else:
            self.lbl_hay_recargo.setText("Cliente en recargo")
            self.lbl_hay_recargo.setToolTip(
                "Ninguna factura del lote trae recargo impreso, pero el cliente "
                "está en recargo de equivalencia: no presenta el 303 ni deduce "
                "el IVA, así que todas sus compras van por el total factura.")
        self.combo_recargo.blockSignals(True)
        self.combo_recargo.setCurrentIndex(
            max(0, self.combo_recargo.findData(regimen or DESGLOSE)))
        self.combo_recargo.blockSignals(False)

    def _elegir_regimen_recargo(self) -> None:
        """Configuración → Régimen de IVA del cliente: decirlo sin esperar a
        que llegue una factura con recargo impreso."""
        nif = getattr(self, "_cliente_nif", "")
        nombre = getattr(self, "_cliente_nombre", "")
        if not nif:
            self._avisar("Primero cargue o escanee facturas del cliente: su "
                         "régimen de IVA se recuerda por su NIF.", INFO)
            return
        sociedad = not puede_estar_en_recargo(nif)
        actual = regimen_recargo(nif) or DESGLOSE
        if sociedad and actual == TOTAL:
            actual = DESGLOSE
        dialogo = DialogoRecargo(nombre, self._facturas_con_recargo(), self,
                                 elegido=actual, sin_recargo=sociedad)
        if dialogo.exec() != QDialog.Accepted or not dialogo.elegido():
            return
        guardar_regimen_recargo(nif, dialogo.elegido(), nombre)
        self._perfil_columnas = (None,)
        self._preparar_recargo()
        self._rellenar_tabla()
        self._revalidar_todo()

    def _anadir_fila(self, png, f: Factura, tipo, cuenta, gxx, aviso, bloque="",
                     fuentes=None):
        """Añade una línea al final (deshacer, pruebas)."""
        self._insertar_fila(self._fila_guardada(png, f, tipo, cuenta, gxx, aviso,
                                                bloque, fuentes))

    @staticmethod
    def _fila_guardada(png, f: Factura, tipo, cuenta, gxx, aviso, bloque="",
                       fuentes=None) -> Fila:
        """La línea de una sesión guardada (o de una prueba), con su cuenta."""
        f.concepto = cuenta if cuenta not in ("", None) else None
        f.subclave = gxx or None
        return Fila(png, f, f.tipo_revision or tipo, aviso or "",
                    bloque or "", list(fuentes or [f]))

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
                                         cuenta, gxx,
                                         getattr(self, "_cliente_nif", ""),
                                         guardar_nombre=not nombre_sin_letra(f)):
            return ""
        return (f"Guardado: las facturas de {f.nombre} irán a "
                f"{cuenta}{f' ({gxx})' if gxx else ''} "
                f"{descripcion_de(cuenta, gxx) or ''}".strip())

    def _unificar_nombres_en_tabla(self, fila_editada: int | None = None) -> str:
        """Un NIF, un nombre en todo el lote. Al corregir el NIF de una
        factura, es ella la que toma el nombre con el que ya está ese NIF (o
        el que se puso a mano); si cambia alguna otra, vuelve a pendiente,
        como al copiar un dato desde otra factura."""
        preferidos = nombres_guardados(solo_a_mano=True)
        editadas = set()
        if fila_editada is not None and 0 <= fila_editada < len(self.filas):
            clave = clave_documento(self.filas[fila_editada].factura)
            editadas = {r for r, registro in enumerate(self.filas)
                        if clave_documento(registro.factura) == clave}
            nif = normaliza_nif(self.filas[fila_editada].factura.nif)
            otros = [str(registro.factura.nombre).strip()
                     for r, registro in enumerate(self.filas)
                     if r not in editadas
                     and normaliza_nif(registro.factura.nif) == nif
                     and str(registro.factura.nombre or "").strip()]
            if nif and otros and nif not in preferidos:
                preferidos = {**preferidos, nif: nombre_preferido(otros)}
        facturas = [x for registro in self.filas
                    for x in (registro.factura, *(registro.get("fuentes") or ()))]
        cambiadas = {id(f) for f, _antes, _despues in
                     unificar_nombres_por_nif(facturas, preferidos)}
        filas = [r for r, registro in enumerate(self.filas)
                 if any(id(x) in cambiadas for x in
                        (registro.factura, *(registro.get("fuentes") or ())))]
        otras = [r for r in filas if r not in editadas]
        for r in filas:
            self.tabla.pintar(r, self.filas[r], (C_NOMBRE,))
        for r in otras:
            self._invalidar_revision_documento(r)
        if not filas:
            return ""
        nombre = self.filas[filas[0]].factura.nombre
        return (f"Nombre unificado por NIF: «{nombre}»."
                + (f" {len(otras)} línea(s) más cambian de nombre y quedan "
                   f"pendientes de revisar." if otras else ""))

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
        proveedor que esten sin el, aqui y en los proximos lotes. Y con ese
        NIF, el nombre con el que ya está en el lote."""
        aviso = self._guardar_nif_escrito(r)
        unificado = self._unificar_nombres_en_tabla(r) if r < len(self.filas) else ""
        return "  ".join(x for x in (aviso, unificado) if x)

    def _guardar_nif_escrito(self, r) -> str:
        if r >= len(self.filas):
            return ""
        f = self._leer_fila(r)
        nif = normaliza_nif(f.nif)
        if not f.nombre or not validar_nif(nif):
            return ""                  # a medio escribir o ilegible: no guardar
        if not recordar_nif(f.nombre, nif, manual=True,
                            guardar_nombre=not nombre_sin_letra(f)):
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

    def _actualizar_combo_meses(self) -> None:
        """Los meses que hay en el lote (y «Sin fecha» si alguna no la tiene).

        El mes elegido se conserva aunque ya no quede ninguna factura suya:
        así no se quita el filtro sin que nadie lo pida.
        """
        actual = self.combo_filtro_mes.currentData()
        meses = {mes_de(fila.factura) for fila in self.filas}
        sin_fecha = None in meses
        meses = sorted(m for m in meses if m is not None)
        if actual not in (None, SIN_FECHA) and tuple(actual) not in meses:
            meses = sorted(meses + [tuple(actual)])
        opciones = [(nombre_mes(m), m) for m in meses]
        if sin_fecha or actual == SIN_FECHA:
            opciones.append((nombre_mes(SIN_FECHA), SIN_FECHA))
        ya = [(self.combo_filtro_mes.itemText(i), self.combo_filtro_mes.itemData(i))
              for i in range(1, self.combo_filtro_mes.count())]
        if ya == opciones:
            return
        self.combo_filtro_mes.blockSignals(True)
        self.combo_filtro_mes.clear()
        self.combo_filtro_mes.addItem(TODOS_LOS_MESES, None)
        for texto, dato in opciones:
            self.combo_filtro_mes.addItem(texto, dato)
        indice = next((i for i in range(self.combo_filtro_mes.count())
                       if self.combo_filtro_mes.itemData(i) == actual), 0)
        self.combo_filtro_mes.setCurrentIndex(indice)
        self.combo_filtro_mes.blockSignals(False)

    def _aplicar_filtro(self) -> None:
        self._actualizar_combo_meses()
        mes = self.combo_filtro_mes.currentData()
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
            if visible and not en_el_mes(self.filas[fila].factura, mes):
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
            # Solo si cambia: cada revisión del lote vuelve a filtrar y casi
            # nunca cambia nada.
            if self.tabla.isRowHidden(fila) == visible:
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
            or self.combo_filtro_mes.currentData() is not None
            or not self.botones_tipo["todos"].isChecked()
            or self.combo_filtro_bloque.currentText() != TODOS_LOS_BLOQUES
            or self.txt_buscar.text().strip()
            or (self.combo_filtro_registro.isVisible()
                and self.combo_filtro_registro.currentData() != "todas")
        )

    def _seleccionar_fila(self, fila: int) -> None:
        """Deja seleccionada solo esa fila y la hace la actual.

        Sin selectRow: con Ctrl pulsado (Ctrl+Intro) selectRow alterna la
        fila en vez de seleccionarla."""
        modelo = self.tabla.model()
        indice = modelo.index(fila, C_ESTADO)
        self.tabla.selectionModel().setCurrentIndex(
            indice, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        self.tabla.scrollTo(indice)

    def _siguiente_incidencia(self, desde: int | None = None) -> None:
        """La siguiente factura pendiente después de `desde` (o de la actual).

        Primero entre las que se ven: si se está cuadrando un mes, se queda
        en ese mes. Solo si ahí no queda ninguna se quitan los filtros, y se
        dice.
        """
        total = self.tabla.rowCount()
        if not total:
            return
        inicio = self.tabla.currentRow() if desde is None else desde
        orden = [(inicio + salto) % total for salto in range(1, total + 1)]
        # Lo revisado y lo corregido a mano ya no son incidencias.
        pendientes = [f for f in orden if self.filas[f].presentacion in PENDIENTES]
        if not pendientes:
            self.lbl_estado.setText(
                "Todo el lote está correcto y listo para exportar.")
            return
        visibles = [f for f in pendientes if not self.tabla.isRowHidden(f)]
        if visibles:
            fila = visibles[0]
        else:
            fila = pendientes[0]
            filtro = self._texto_filtro() if self._hay_filtro_activo() else ""
            self._limpiar_filtros()
            if filtro:
                self._avisar(f"No quedan pendientes con el filtro ({filtro}): "
                             "se ha quitado para ir a la siguiente.", INFO)
        self._seleccionar_fila(fila)

    def _limpiar_filtros(self):
        for control in (self.txt_buscar, self.combo_filtro_estado,
                        self.combo_filtro_bloque, self.combo_filtro_registro,
                        self.combo_filtro_mes):
            control.blockSignals(True)
        self.txt_buscar.clear()
        self.combo_filtro_estado.setCurrentIndex(0)
        self.combo_filtro_mes.setCurrentIndex(0)
        self.combo_filtro_bloque.setCurrentIndex(0)
        self.combo_filtro_registro.setCurrentIndex(0)
        self.botones_tipo["todos"].setChecked(True)
        for control in (self.txt_buscar, self.combo_filtro_estado,
                        self.combo_filtro_bloque, self.combo_filtro_registro,
                        self.combo_filtro_mes):
            control.blockSignals(False)
        self._aplicar_filtro()

    def _alternar_por_el_total(self) -> None:
        """«Por el total»: el IVA de esas facturas de gasto no se deduce. Se
        registran por el importe entero, sin desglose (la retención, si la
        hay, se conserva). Pulsar otra vez lo deshace."""
        seleccionadas = self._filas_seleccionadas()
        if not seleccionadas:
            self._avisar("Seleccione la factura de gasto cuyo IVA no se puede "
                         "deducir.", AVISO)
            return
        if self._por_el_total():
            self._avisar(f"Este {self._motivo_por_el_total()}: ya registra "
                         "todas sus compras por el total.", INFO)
            return
        del_documento = self._filas_de_los_documentos(seleccionadas)
        fuentes = []
        for fila in del_documento:
            if self._tipo_fila(fila) != "gasto":
                continue
            registro = self.filas[fila]
            for f in registro.get("fuentes") or [registro["factura"]]:
                if not any(f is x for x in fuentes):
                    fuentes.append(f)
        if not fuentes:
            self._avisar("Solo los gastos se registran por el total: una "
                         "venta lleva siempre su IVA.", AVISO)
            return
        poner = not all(getattr(f, "no_deducible", False) for f in fuentes)

        def aplicar(valor):
            for f in fuentes:
                f.no_deducible = valor
            self._rellenar_tabla()
            self._revalidar_todo()
        exportadas = any(self.filas[r].get("ya_exportada") for r in del_documento)
        aplicar(poner)
        documentos = len({clave_documento(f) for f in fuentes})
        texto = (f"{documentos} factura(s) por el total: su IVA no se deduce y "
                 "va dentro del gasto." if poner else
                 f"{documentos} factura(s) otra vez con su IVA desglosado.")
        if exportadas:
            texto += (" OJO: ya estaba exportada a Aplifisa con el desglose "
                      "anterior: corríjala allí también.")
        self._avisar(texto, AVISO if exportadas else EXITO,
                     deshacer=lambda: aplicar(not poner))

    def _filas_seleccionadas(self) -> list[int]:
        return sorted({i.row() for i in self.tabla.selectionModel().selectedRows()})

    def _marcar_revisada(self, filas=None):
        """Da salida únicamente a avisos ámbar comprobados por una persona.

        Se revisa la factura, no la línea: una factura con suplido o con
        varios tipos de IVA tiene varias líneas y basta con pulsar una.
        `filas`: las que se marcan (si no, las seleccionadas). Devuelve la
        función que lo deshace, o None si no se ha marcado nada.
        """
        seleccionadas = (list(filas) if filas is not None
                         else self._filas_seleccionadas())
        if not seleccionadas:
            self._avisar("Seleccione una o varias filas ámbar.", AVISO)
            return None
        filas = self._filas_de_los_documentos(seleccionadas)
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
        # Revisar una cuenta que venía de otro cliente es decir que en este
        # también va ahí: se recuerda para este cliente y no vuelve a salir.
        # Lo de antes se guarda por si se deshace (el aviso y la ficha).
        # Solo las de estas facturas (las únicas que cambian aquí): el
        # «Deshacer» de la banda no se queda con el lote entero.
        avisos_antes = [(self.filas[fila], self.filas[fila]["aviso"])
                        for fila in filas]
        fichas_antes = {}
        for fila in filas:
            if "en otro cliente" in (self.filas[fila]["aviso"] or ""):
                f = self._leer_fila(fila)
                clave, ficha = ficha_de_cuenta(f.nif, f.nombre)
                fichas_antes.setdefault(clave, ficha)
                self._cuenta_escrita_a_mano(fila)
        self._revalidar_todo()
        if confirmadas:
            texto = (f"{len(confirmadas)} línea(s) revisada(s): ya pueden "
                     "exportarse.")
            self.lbl_estado.setText(texto)

            def deshacer():
                for factura in confirmadas:
                    factura.revision_confirmada = False
                for registro, aviso in avisos_antes:
                    registro["aviso"] = aviso
                for clave, ficha in fichas_antes.items():
                    proveedores.reponer(clave, ficha)
                self._revalidar_todo()
                self._avisar("Revisión deshecha: vuelven a estar pendientes.",
                             INFO)
            self._avisar(texto, EXITO, deshacer=deshacer)
            return deshacer
        if ya_corregidas:
            self._avisar("Ya cuenta como revisada (corregida a mano): puede "
                         "exportarse.", INFO)
        else:
            self._avisar(
                "Solo se pueden confirmar avisos ámbar. Los errores rojos se "
                "corrigen en la tabla.", AVISO)
        return None

    def _fila_que_se_ve(self) -> int:
        """La factura de la tarjeta, o -1 si no se ve ninguna (un filtro
        puede esconder la fila actual: esa no se marca sin verla)."""
        r = self.tabla.currentRow()
        if 0 <= r < len(self.filas) and not self.tabla.isRowHidden(r):
            return r
        return -1

    def _marcar_revisada_actual(self) -> None:
        """«Revisada» de la tarjeta de la factura: solo la que se ve."""
        r = self._fila_que_se_ve()
        if r < 0:
            self._avisar("Seleccione la factura que ha revisado.", AVISO)
            return
        self._marcar_revisada(filas=[r])

    def _correcta_y_siguiente(self) -> None:
        """Da por buena la factura que se ve y pasa a la siguiente pendiente.

        Una en ámbar queda revisada (como «Marcar revisada»); una en rojo no
        se puede dar por buena: se corrige antes en la tabla. Si no se ve
        ninguna, solo se pasa a la siguiente.
        """
        r = self._fila_que_se_ve()
        deshacer = None
        if r >= 0:
            presentacion = self.filas[r].presentacion
            if presentacion == CON_ERROR:
                self._avisar("Esta factura tiene un error (en rojo): corríjalo "
                             "en la tabla antes de darla por buena.", AVISO)
                return
            if presentacion == POR_REVISAR:
                deshacer = self._marcar_revisada(filas=[r])
        if self.filas and not any(f.presentacion in PENDIENTES for f in self.filas):
            # Un solo aviso, con su «Deshacer» si se acaba de marcar: si no,
            # el de «no queda ninguna» taparía el de la revisión.
            self._avisar("No queda ninguna factura pendiente: ya puede "
                         "exportar a Aplifisa.", EXITO, deshacer=deshacer)
            return
        self._siguiente_incidencia(desde=r if r >= 0 else None)

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
        # Sin avisar de cada fila que se quita: cada una cambiaba la selección
        # y volvía a cargar la hoja y la ficha (64 filas, más de un segundo).
        # Se hace una vez al final, con la fila en la que se queda.
        fila_antes, columna_antes = self._fila_actual()
        bloqueadas = self.tabla.blockSignals(True)
        try:
            for fila in filas:
                registro = self.filas[fila]
                for fuente in registro.get("fuentes", [registro["factura"]]):
                    fuente.eliminada = True
                self._ultimo_borrado.append({
                    "registro": registro, "tipo": registro.tipo, "posicion": fila})
                self.tabla.removeRow(fila)
                self.filas.pop(fila)
        finally:
            self.tabla.blockSignals(bloqueadas)
        fila_ahora, columna_ahora = self._fila_actual()
        if fila_ahora is not fila_antes or columna_ahora != columna_antes:
            self._senalar_celda(self.tabla.currentRow(), columna_ahora)
        self._mostrar_miniatura()
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

    def _fila_actual(self):
        """La línea (y la columna) en la que está la tabla, o None."""
        r = self.tabla.currentRow()
        return (self.filas[r] if 0 <= r < len(self.filas) else None,
                self.tabla.currentColumn())

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
        if event.size().height() != event.oldSize().height():
            self._encajar_totales()
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


def _texto_del_error(tipo, valor) -> str:
    """Lo que se le dice a la persona. Un error sin mensaje (el de memoria
    lo es) dejaba la ventana con un hueco en blanco."""
    if issubclass(tipo, MemoryError):
        return ("El programa se ha quedado sin memoria. Guarde lo que esté "
                "haciendo, cierre otros programas y vuelva a intentarlo.")
    texto = str(valor).strip()
    return texto or f"Error interno del programa ({tipo.__name__})."


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
                "No se ha podido terminar lo que estaba haciendo:\n\n"
                f"{_texto_del_error(tipo, valor)}"
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
