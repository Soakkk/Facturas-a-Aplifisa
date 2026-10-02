"""La cinta de botones de arriba: una sola fila, todo a la vista.

Desde la 1.18 no lleva logo, título ni rótulos de grupo (el usuario lo pidió:
ocupaban altura y no servían para nada). Lo que se usa a diario va a la
izquierda, el cliente y el periodo en el centro (antes era una fila aparte)
y «Exportar a Aplifisa» a la derecha. Lo ocasional (modelos, API key…) está
en los menús. Si no cabe todo con su nombre, los de uso ocasional se quedan solo con el
icono (`_actualizar_barra_responsiva`); nunca se corta un texto.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QPushButton, QSizePolicy, QToolButton, QWidget,
)

from facturas_excel.ventana_comun import ruta_recurso

ICONO_CINTA = 22
# Ancho mínimo de un botón con nombre: así los cortos no quedan apretados.
ANCHO_BOTON = 76


class BotonCinta(QToolButton):
    """Botón de la cinta que nunca se estrecha por debajo de su texto.

    El mínimo va en el propio botón y no en la hoja de estilo: un
    «min-width» de QSS deja al layout encoger el botón hasta ese mínimo
    aunque el texto no quepa, y la cinta calcularía mal cuándo pasar a
    solo icono.
    """

    def sizeHint(self) -> QSize:
        tam = super().sizeHint()
        if self.toolButtonStyle() != Qt.ToolButtonIconOnly:
            tam.setWidth(max(tam.width(), ANCHO_BOTON))
        return tam

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


def crear_cinta(v) -> None:
    """Crea `v.barra_rapida` y deja los botones en la ventana.

    `v.layout_cinta` y `v.posicion_cliente` dicen dónde va la caja del
    cliente y el periodo, que monta la ventana después.
    """
    v.barra_rapida = QWidget()
    v.barra_rapida.setObjectName("barraRapida")
    accesos = QHBoxLayout(v.barra_rapida)
    accesos.setContentsMargins(10, 4, 10, 4)
    accesos.setSpacing(2)
    v.layout_cinta = accesos
    v._botones_grandes = []
    # Compatibilidad: ya no hay marca, pilas ni rótulos que ocultar.
    v._marcas_barra = []
    v._pilas_cinta = []
    v._etiquetas_grupo = []

    def boton(texto, icono, accion, ayuda, nombre="cintaGrande"):
        b = BotonCinta()
        b.setObjectName(nombre)
        b.setText(texto)
        if icono:
            b.setIcon(QIcon(ruta_recurso(icono)))
        b.setIconSize(QSize(ICONO_CINTA, ICONO_CINTA))
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        b.setToolTip(ayuda)
        b.setAutoRaise(True)
        # Nunca más estrecho que su texto: si falta sitio, la cinta pasa
        # los ocasionales a solo icono (no se cortan a «Exp…isa»).
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        b.clicked.connect(accion)
        v._botones_grandes.append(b)
        accesos.addWidget(b)
        return b

    def separador():
        linea = QFrame()
        linea.setObjectName("separadorCinta")
        linea.setFrameShape(QFrame.VLine)
        accesos.addSpacing(4)
        accesos.addWidget(linea)
        accesos.addSpacing(4)

    # Botones ocultos que usan otras partes (y las pruebas) como gatillo.
    v.btn_revisar_gemini = QPushButton("Revisar Gemini", v)
    v.btn_revisar_gemini.clicked.connect(v._preparar_revision_gemini)
    v.btn_revisar_gemini.hide()
    v.btn_vaciar = QPushButton("Vaciar todo", v)
    v.btn_vaciar.clicked.connect(v._vaciar_todo)
    v.btn_vaciar.hide()

    # Documentos
    v.btn_cargar = boton(
        "Abrir PDF", "open-large.svg", v._cargar,
        "Abrir un PDF ya escaneado o fotos.  (Ctrl+O)")
    v.btn_escanear = boton(
        "Escanear", "scan-large.svg", v._escanear,
        "Escanea el taco y lo añade al lote completo.  (Ctrl+E)")
    v.btn_vaciar_cinta = boton(
        "Vaciar todo", "trash.svg", v.btn_vaciar.click,
        "Quita todo lo cargado y empieza un lote nuevo.")
    separador()
    # Archivo
    v.btn_registro_facturas = boton(
        "Registro", "registro-large.svg", v._ver_registro_facturas,
        "Todas las facturas que han salido del programa: en qué paso "
        "están, en qué Excel salieron y dónde está su PDF.")
    # Los de uso ocasional se quedan solo con el icono si falta ancho.
    v._botones_secundarios = [
        boton("Escaneos", "folder.svg", v._ver_escaneos,
              "Escaneos guardados: los PDF ya escaneados y archivados.  (Ctrl+L)"),
        boton("Recoger", "open.svg", v._recoger_sueltos,
              "Recoger sueltos: lleva a su carpeta los PDF de facturas y los "
              "Excel de Aplifisa que haya en el Escritorio y Descargas."),
        boton("Expedientes", "expediente.svg", v._ver_expedientes,
              "Expedientes: un PDF de gastos, otro de ingresos, los Excel y "
              "un resumen por cliente y ejercicio."),
    ]
    separador()
    # Comprobar
    v.btn_cuadrar = boton(
        "Cuadrar", "balance.svg", lambda: v.btn_registro.trigger(),
        "Cuadrar con Aplifisa: contrasta el lote con el listado de Aplifisa "
        "en PDF.  (Ctrl+R)")
    v.btn_registro.changed.connect(
        lambda: v.btn_cuadrar.setEnabled(v.btn_registro.isEnabled()))
    v.btn_cuadrar.setEnabled(v.btn_registro.isEnabled())
    v.btn_cuadre_anual = boton(
        "Cuadre año", "registro-large.svg", lambda: v._cuadre_anual(),
        "Cuadre con Aplifisa de lo guardado: el listado de Aplifisa del "
        "periodo que quiera (del 1 de enero a hoy, el año entero…) frente a "
        "todo lo que el programa tiene en PDF de ese cliente.  (Ctrl+Shift+R)")
    v._botones_secundarios.append(v.btn_cuadre_anual)
    v._botones_secundarios.append(
        boton("Listado PDF", "listado.svg", lambda: v._guardar_listado_totales(),
              "Listado PDF: listado imprimible de totales para puntear con "
              "Aplifisa."))
    separador()
    # Aquí la ventana pone el cliente y el periodo (antes una fila aparte),
    # que se queda con el sitio que sobre.
    v.posicion_cliente = accesos.count()

    v.btn_gastos = boton(
        "Exportar a Aplifisa", "export-large.svg", v._exportar_todo,
        "Exporta el lote completo, no solo el resultado de la búsqueda. "
        "(Ctrl+G)", nombre="cintaPrimaria")
    v.btn_gastos.setEnabled(False)
    v.btn_ventas = v.btn_gastos
