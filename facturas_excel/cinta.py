"""La cinta de botones de arriba, por grupos, como en el resto de la suite.

Lo de cada día a la vista y en grande (Abrir, Escanear, Cuadrar, Exportar);
lo ocasional en pequeño al lado. En pantallas bajas la ventana la compacta y
la sube a la barra de menús (`_actualizar_barra_responsiva`).
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from facturas_excel import __version__
from facturas_excel.ventana_comun import ruta_recurso


def crear_cinta(v) -> None:
    """Crea `v.barra_rapida` con sus grupos y deja los botones en la ventana."""
    # Cinta de herramientas por grupos, como en el resto de la suite
    # (Generador de avisos 1.6): lo de cada día a la vista, en grande, y lo
    # ocasional en pequeño al lado. En pantallas bajas la cinta se compacta
    # y se sube a la barra de menús.
    v.barra_rapida = QWidget()
    v.barra_rapida.setObjectName("barraRapida")
    accesos = QHBoxLayout(v.barra_rapida)
    accesos.setContentsMargins(16, 6, 16, 0)
    accesos.setSpacing(0)
    marca_icono = QLabel("fa")
    marca_icono.setObjectName("marcaIcono")
    marca_icono.setAlignment(Qt.AlignCenter)
    marca_icono.setFixedSize(36, 36)
    marca_caja = QHBoxLayout()
    marca_caja.setContentsMargins(0, 0, 14, 6)
    marca_caja.setSpacing(10)
    marca_caja.addWidget(marca_icono)
    marca = QVBoxLayout()
    marca.setSpacing(0)
    titulo = QLabel("Facturas a Aplifisa")
    titulo.setObjectName("marca")
    subtitulo = QLabel(f"Mesa de revisión  ·  v{__version__}")
    subtitulo.setObjectName("textoSuave")
    marca.addWidget(titulo)
    marca.addWidget(subtitulo)
    marca_caja.addLayout(marca)
    v._marcas_barra = [marca_icono, titulo, subtitulo]
    accesos.addLayout(marca_caja)

    v._botones_grandes = []
    v._pilas_cinta = []
    v._etiquetas_grupo = []

    def grande(texto, icono, accion, ayuda, nombre="cintaGrande"):
        boton = QToolButton()
        boton.setObjectName(nombre)
        boton.setText(texto)
        boton.setIcon(QIcon(ruta_recurso(icono)))
        boton.setIconSize(QSize(26, 26))
        boton.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        boton.setToolTip(ayuda)
        boton.setAutoRaise(True)
        boton.clicked.connect(accion)
        v._botones_grandes.append(boton)
        return boton

    def pequeno(texto, icono, accion, ayuda=""):
        boton = QToolButton()
        boton.setObjectName("cintaPeque")
        boton.setText(texto)
        if icono:
            boton.setIcon(QIcon(ruta_recurso(icono)))
        boton.setIconSize(QSize(16, 16))
        boton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        boton.setToolTip(ayuda or texto)
        boton.setAutoRaise(True)
        boton.clicked.connect(accion)
        return boton

    def grupo(etiqueta, grandes, pequenos=()):
        caja = QFrame()
        caja.setObjectName("grupoCinta")
        capa = QVBoxLayout(caja)
        capa.setContentsMargins(8, 0, 8, 0)
        capa.setSpacing(0)
        fila = QHBoxLayout()
        fila.setSpacing(2)
        for boton in grandes:
            fila.addWidget(boton)
        if pequenos:
            pila = QWidget()
            capa_pila = QVBoxLayout(pila)
            capa_pila.setContentsMargins(2, 0, 0, 0)
            capa_pila.setSpacing(0)
            for boton in pequenos:
                capa_pila.addWidget(boton)
            capa_pila.addStretch(1)
            fila.addWidget(pila)
            v._pilas_cinta.append(pila)
        capa.addLayout(fila)
        lbl = QLabel(etiqueta)
        lbl.setObjectName("etiquetaGrupo")
        lbl.setAlignment(Qt.AlignCenter)
        capa.addWidget(lbl)
        v._etiquetas_grupo.append(lbl)
        accesos.addWidget(caja)
        return caja

    v.btn_cargar = grande(
        "Abrir PDF", "open-large.svg", v._cargar,
        "Abrir un PDF ya escaneado o fotos.  (Ctrl+O)")
    v.btn_escanear = grande(
        "Escanear", "scan-large.svg", v._escanear,
        "Escanea el taco y lo añade al lote completo.  (Ctrl+E)")
    v.btn_revisar_gemini = QPushButton("Revisar Gemini", v)
    v.btn_revisar_gemini.clicked.connect(v._preparar_revision_gemini)
    v.btn_revisar_gemini.hide()
    v.btn_vaciar = QPushButton("Vaciar todo", v)
    v.btn_vaciar.clicked.connect(v._vaciar_todo)
    v.btn_vaciar.hide()
    grupo("Documentos", [v.btn_cargar, v.btn_escanear], [
        pequeno("Vaciar todo", "trash.svg", v.btn_vaciar.click,
                "Empieza un lote nuevo."),
    ])
    v.btn_registro_facturas = grande(
        "Registro", "registro-large.svg", v._ver_registro_facturas,
        "Todas las facturas que han salido del programa: en qué paso "
        "están, en qué Excel salieron y dónde está su PDF.")
    grupo("Archivo", [v.btn_registro_facturas], [
        pequeno("Escaneos guardados", "folder.svg", v._ver_escaneos,
                "Los PDF ya escaneados y archivados.  (Ctrl+L)"),
        pequeno("Recoger sueltos…", "open.svg", v._recoger_sueltos,
                "Lleva a su carpeta los PDF de facturas y los Excel de "
                "Aplifisa que haya sueltos en el Escritorio y Descargas."),
        pequeno("Expedientes…", "printer.svg", v._ver_expedientes,
                "Un PDF de gastos, otro de ingresos, los Excel y un "
                "resumen por cliente y ejercicio."),
    ])

    v.btn_cuadrar = grande(
        "Cuadrar con Aplifisa", "balance.svg",
        lambda: v.btn_registro.trigger(),
        "Contrasta el lote con el listado de Aplifisa en PDF.  (Ctrl+R)")
    v.btn_registro.changed.connect(
        lambda: v.btn_cuadrar.setEnabled(v.btn_registro.isEnabled()))
    v.btn_cuadrar.setEnabled(v.btn_registro.isEnabled())
    v.btn_cambiar_cliente_cinta = pequeno(
        "Cambiar cliente…", "user.svg", lambda: v._cambiar_cliente(),
        "Si el cliente del lote se detectó mal, se rehace sin volver a "
        "pagar la lectura.")
    grupo("Comprobar", [v.btn_cuadrar], [
        v.btn_cambiar_cliente_cinta,
        pequeno("Listado PDF de totales", "printer.svg",
                lambda: v._guardar_listado_totales(),
                "Listado imprimible para puntear con Aplifisa."),
    ])
    grupo("Configurar", [], [
        pequeno("Modelos de lectura…", "settings.svg",
                v._configurar_modelos,
                "Modelo principal, respaldo y doble lectura."),
        pequeno("API key de Gemini…", "key.svg", v._configurar_key),
        pequeno("Revisar Gemini", "", v.btn_revisar_gemini.click,
                "Prepara una orden para revisar si conviene otro modelo."),
    ])
    accesos.addStretch(1)

    v.btn_gastos = grande(
        "Exportar a Aplifisa", "export-large.svg", v._exportar_todo,
        "Exporta el lote completo, no solo el resultado de la búsqueda. "
        "(Ctrl+G)", nombre="cintaPrimaria")
    v.btn_gastos.setEnabled(False)
    grupo("Aplifisa", [v.btn_gastos])
    v.btn_ventas = v.btn_gastos
