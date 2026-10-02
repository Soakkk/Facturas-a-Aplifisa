"""Cuadre con Aplifisa del periodo que se quiera (del 1 de enero a hoy, 6 o
9 meses, el año entero): el listado de Aplifisa frente a lo que el programa
tiene guardado en PDF de ese cliente."""

from __future__ import annotations

import html
import os
import re
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QDialog, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from . import archivo, cuadre_anual
from .cuadre_anual import (
    BIEN, DISTINTA, DUPLICADA, FALTA_APLIFISA, FALTA_PROGRAMA, ORDEN_ESTADO,
    SIN_PDF, TEXTO_ESTADO,
)
from .registro import leer_registro

COLORES = {
    BIEN: ("#19724E", "#E6F4EC"), FALTA_APLIFISA: ("#B43737", "#FBE9E9"),
    FALTA_PROGRAMA: ("#B43737", "#FBE9E9"), SIN_PDF: ("#86500A", "#FBEFDC"),
    DUPLICADA: ("#B43737", "#FBE9E9"), DISTINTA: ("#86500A", "#FBEFDC"),
}
COLUMNAS = ["Resultado", "Tipo", "Fecha", "Nº factura", "Proveedor o cliente",
            "Base", "IVA", "Total", "Nº Aplifisa", "PDF", "Qué pasa"]
CLASE = {"gasto": "Gastos", "venta": "Ingresos"}
# Para el resumen («2 faltan en el programa · 1 falta el PDF…»).
EN_FRASE = {                    # (una, varias)
    BIEN: ("bien", "bien"),
    FALTA_APLIFISA: ("falta en Aplifisa", "faltan en Aplifisa"),
    FALTA_PROGRAMA: ("falta en el programa", "faltan en el programa"),
    SIN_PDF: ("sin PDF guardado", "sin PDF guardado"),
    DUPLICADA: ("duplicada", "duplicadas"),
    DISTINTA: ("con un dato distinto", "con un dato distinto"),
}


def _eur(valor) -> str:
    if valor is None:
        return ""
    texto = f"{float(valor):,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _pydate(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


class DialogoCuadre(QDialog):
    """`lote`: [(factura, tipo, fila)] del lote abierto y de qué cliente es
    (nif, nombre): entra en el cuadre si se cuadra ese cliente."""

    def __init__(self, parent=None, cliente=("", ""), lote=None):
        super().__init__(parent)
        self.setWindowTitle("Cuadre con Aplifisa")
        self.resize(1180, 760)
        self._cliente_lote = tuple(cliente)
        self._lote = list(lote or [])
        self._listados = {}            # tipo -> Registro
        self._rutas = {}
        self.cuadre = None
        self._fila_elegida = -1
        raiz = QVBoxLayout(self)

        explicacion = QLabel(
            "Saque de Aplifisa el listado de lo que quiere comprobar (compras, "
            "ventas o los dos) y el programa le dice si es lo que tiene guardado "
            "en PDF: qué está bien, qué falta en Aplifisa, qué falta por "
            "escanear y qué está repetido.")
        explicacion.setWordWrap(True)
        raiz.addWidget(explicacion)

        fila_cliente = QHBoxLayout()
        fila_cliente.addWidget(QLabel("Cliente"))
        self.combo_cliente = QComboBox()
        self.combo_cliente.setMinimumWidth(320)
        clientes = list(cuadre_anual.clientes_guardados())
        if any(self._cliente_lote) and not any(
                cuadre_anual.mismo_cliente(c, self._cliente_lote) for c in clientes):
            clientes.insert(0, self._cliente_lote)
        for nif, nombre in clientes:
            self.combo_cliente.addItem(
                f"{nombre or 'Sin nombre'}" + (f" · {nif}" if nif else ""), (nif, nombre))
        actual = next((i for i, c in enumerate(clientes)
                       if cuadre_anual.mismo_cliente(c, self._cliente_lote)), 0)
        self.combo_cliente.setCurrentIndex(actual)
        fila_cliente.addWidget(self.combo_cliente, 1)
        raiz.addLayout(fila_cliente)

        # Cada listado con su periodo: el que se pidió a Aplifisa.
        self.botones_listado, self.etiquetas_listado = {}, {}
        self.desde, self.hasta = {}, {}
        hoy = date.today()
        for tipo, texto in (("gasto", "Listado de compras…"),
                            ("venta", "Listado de ventas…")):
            fila = QHBoxLayout()
            boton = QPushButton(texto)
            boton.clicked.connect(lambda _c=False, t=tipo: self._elegir_listado(t))
            etiqueta = QLabel("Sin cargar")
            etiqueta.setObjectName("textoSuave")
            self.botones_listado[tipo] = boton
            self.etiquetas_listado[tipo] = etiqueta
            fila.addWidget(boton)
            fila.addWidget(etiqueta, 1)
            fila.addWidget(QLabel("del"))
            self.desde[tipo] = QDateEdit(_qdate(date(hoy.year, 1, 1)))
            self.hasta[tipo] = QDateEdit(_qdate(hoy))
            for editor in (self.desde[tipo], self.hasta[tipo]):
                editor.setCalendarPopup(True)
                editor.setDisplayFormat("dd/MM/yyyy")
                editor.setEnabled(False)
                editor.dateChanged.connect(lambda *_: self._invalidar())
            fila.addWidget(self.desde[tipo])
            fila.addWidget(QLabel("al"))
            fila.addWidget(self.hasta[tipo])
            raiz.addLayout(fila)

        fila_periodo = QHBoxLayout()
        ayuda = QLabel("Ponga en cada listado las mismas fechas que pidió a "
                       "Aplifisa: lo guardado de esas fechas que no esté en "
                       "Aplifisa saldrá como «falta».")
        ayuda.setObjectName("textoSuave")
        ayuda.setWordWrap(True)
        fila_periodo.addWidget(ayuda, 1)
        self.boton_cuadrar = QPushButton("Cuadrar")
        self.boton_cuadrar.setObjectName("primario")
        self.boton_cuadrar.setEnabled(False)
        self.boton_cuadrar.clicked.connect(self.cuadrar)
        fila_periodo.addWidget(self.boton_cuadrar)
        raiz.addLayout(fila_periodo)

        self.resumen = QLabel("Cargue el listado de Aplifisa que quiere comprobar.")
        self.resumen.setWordWrap(True)
        self.resumen.setTextFormat(Qt.RichText)
        raiz.addWidget(self.resumen)

        self.tabla_trimestres = QTableWidget(0, 9)
        self.tabla_trimestres.setHorizontalHeaderLabels(
            ["Periodo", "Facturas programa", "Facturas Aplifisa", "Base programa",
             "Base Aplifisa", "IVA programa", "IVA Aplifisa", "Total programa",
             "Total Aplifisa"])
        self.tabla_trimestres.verticalHeader().setVisible(False)
        self.tabla_trimestres.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_trimestres.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabla_trimestres.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.tabla_trimestres.horizontalHeader().setStretchLastSection(True)
        raiz.addWidget(self.tabla_trimestres)

        fila_filtro = QHBoxLayout()
        fila_filtro.addWidget(QLabel("Ver"))
        self.combo_filtro = QComboBox()
        fila_filtro.addWidget(self.combo_filtro)
        fila_filtro.addStretch(1)
        raiz.addLayout(fila_filtro)
        self.combo_filtro.currentIndexChanged.connect(lambda *_: self._pintar_detalle())

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setWordWrap(False)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(len(COLUMNAS) - 1, QHeaderView.Stretch)
        self.tabla.itemSelectionChanged.connect(self._seleccion)
        self.tabla.itemDoubleClicked.connect(lambda *_: self._abrir_pdf())
        raiz.addWidget(self.tabla, 1)

        botones = QHBoxLayout()
        self.boton_pdf = QPushButton("Abrir su PDF")
        self.boton_pdf.clicked.connect(self._abrir_pdf)
        self.boton_lote = QPushButton("Ver en el lote")
        self.boton_lote.clicked.connect(self._ver_en_lote)
        self.boton_informe = QPushButton("Guardar informe PDF…")
        self.boton_informe.clicked.connect(self._guardar_informe)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.reject)
        for b in (self.boton_pdf, self.boton_lote, self.boton_informe):
            b.setEnabled(False)
            botones.addWidget(b)
        botones.addStretch(1)
        botones.addWidget(cerrar)
        raiz.addLayout(botones)
        self.combo_cliente.currentIndexChanged.connect(lambda *_: self._invalidar())

    # ------------------------------------------------------------ cliente
    def cliente(self):
        return self.combo_cliente.currentData() or ("", "")

    def _invalidar(self) -> None:
        self.cuadre = None
        self.tabla.setRowCount(0)
        self.tabla_trimestres.setRowCount(0)
        self.boton_informe.setEnabled(False)
        if self._listados:
            self.resumen.setText("Pulse «Cuadrar».")

    # ------------------------------------------------------------ listados
    def _elegir_listado(self, tipo: str) -> None:
        texto = "compras" if tipo == "gasto" else "ventas"
        ruta, _ = QFileDialog.getOpenFileName(
            self, f"Listado de {texto} de Aplifisa (PDF)", "",
            "Listado de Aplifisa (*.pdf)")
        if ruta:
            self.cargar_listado(ruta, tipo)

    def cargar_listado(self, ruta: str, tipo: str = "") -> bool:
        """Lee el listado. Si dice de qué es (compras/ventas), manda eso."""
        try:
            registro = leer_registro(ruta)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo leer el listado", str(error))
            return False
        if not registro.apuntes:
            QMessageBox.warning(
                self, "Sin apuntes",
                "No se han encontrado apuntes en ese PDF. Tiene que ser el "
                "listado que saca Aplifisa (no un papel escaneado).")
            return False
        tipo = registro.tipo or tipo or "gasto"
        registro.tipo = tipo
        self._listados[tipo] = registro
        self._rutas[tipo] = ruta
        if not registro.bien_leido:
            aviso = " · ⚠ sus totales no cuadran"
        elif cuadre_anual.sin_totales(registro):
            aviso = " · ⚠ sin sus totales"
        else:
            aviso = ""
        self.etiquetas_listado[tipo].setText(
            f"{os.path.basename(ruta)}: {registro.facturas} facturas" + aviso)
        self._elegir_cliente_del_listado(registro)
        inicio, fin = cuadre_anual.periodo_de_listado(registro)
        if inicio:
            self.desde[tipo].setDate(_qdate(inicio))
            self.hasta[tipo].setDate(_qdate(fin))
        self.desde[tipo].setEnabled(True)
        self.hasta[tipo].setEnabled(True)
        self.boton_cuadrar.setEnabled(True)
        self._invalidar()
        return True

    def _elegir_cliente_del_listado(self, registro) -> None:
        """El listado dice de qué cliente es (su NIF en la cabecera): se
        elige ese, si el programa lo tiene."""
        if not registro.cliente_nif:
            return
        for i in range(self.combo_cliente.count()):
            nif, nombre = self.combo_cliente.itemData(i) or ("", "")
            if cuadre_anual.mismo_cliente((nif, ""), (registro.cliente_nif, "")):
                self.combo_cliente.setCurrentIndex(i)
                return

    def periodos(self) -> dict:
        salida = {}
        for tipo in self._listados:
            desde = _pydate(self.desde[tipo].date())
            hasta = _pydate(self.hasta[tipo].date())
            salida[tipo] = (min(desde, hasta), max(desde, hasta))
        return salida

    # ------------------------------------------------------------ cuadrar
    def cuadrar(self) -> None:
        if not self._listados:
            return
        periodos = self.periodos()
        aplifisa = []
        for tipo, registro in self._listados.items():
            aplifisa += cuadre_anual.facturas_aplifisa(registro, tipo)
        # Todas las líneas del listado se comprueban: se leen los años de
        # todas, no solo los del periodo.
        primero, ultimo = cuadre_anual.anios_a_cargar(periodos, aplifisa)
        nif, nombre = self.cliente()
        programa = cuadre_anual.facturas_del_registro(nif, nombre, primero, ultimo)
        if self._lote and cuadre_anual.mismo_cliente((nif, nombre), self._cliente_lote):
            programa = cuadre_anual.juntar(
                programa, cuadre_anual.facturas_del_lote(self._lote))
        self.cuadre = cuadre_anual.cuadrar(programa, aplifisa, periodos)
        for registro in self._listados.values():
            otro = cuadre_anual.aviso_de_cliente(registro, (nif, nombre))
            if otro:
                self.cuadre.avisos.append(otro)
            self.cuadre.avisos += cuadre_anual.avisos_de_listado(registro)
            self.cuadre.notas += cuadre_anual.notas_de_listado(registro)
        self._pintar()

    def _texto_periodo(self) -> str:
        c = self.cuadre
        return " y ".join(f"{CLASE[t].lower()} del {d:%d/%m/%Y} al {h:%d/%m/%Y}"
                          for t, (d, h) in c.periodos.items())

    def _pintar(self) -> None:
        c = self.cuadre
        cuenta = c.cuenta()
        periodo = self._texto_periodo()
        if not c.lineas:
            cabecera = (f"No hay facturas ({periodo}) ni en el listado ni en el "
                        "programa: compruebe el periodo y el cliente.")
        elif c.todo_bien and any(cuadre_anual.listado_sin_numero(r)
                                 for r in self._listados.values()):
            cabecera = (f"<b style='color:#19724E'>✓ Todo cuadra</b> por fecha, importes "
                        "y proveedor (este listado no trae el nº de factura). "
                        f"{periodo.capitalize()}: lo de Aplifisa es lo que tiene guardado "
                        "en PDF.")
        elif c.todo_bien:
            cabecera = (f"<b style='color:#19724E'>✓ Todo bien.</b> {periodo.capitalize()}: "
                        "lo de Aplifisa es lo que tiene guardado en PDF.")
        else:
            partes = [f"<b>{cuenta[e]}</b> {EN_FRASE[e][cuenta[e] > 1]}"
                      for e in ORDEN_ESTADO if cuenta[e]]
            cabecera = f"{periodo.capitalize()}: " + " · ".join(partes) + "."
        for aviso in c.avisos:
            cabecera += f"<br><span style='color:#B43737'>⚠ {html.escape(aviso)}</span>"
        if c.sin_fecha:
            cabecera += (f"<br><span style='color:#B43737'>⚠ {c.sin_fecha} del "
                         "programa sin fecha legible: corríjala en el lote para "
                         "poder cuadrarla.</span>")
        for nota in c.notas:
            cabecera += f"<br><span style='color:#86500A'>{html.escape(nota)}</span>"
        otros = [CLASE[t].lower() for t in ("gasto", "venta") if t not in c.tipos]
        if otros:
            cabecera += (f"<br><span style='color:#5D7084'>Los {otros[0]} no se "
                         "comprueban: cargue también su listado.</span>")
        if c.fuera_de_periodo:
            # Puede ser una registrada tarde… o que el periodo puesto no es el
            # que se pidió a Aplifisa: que se vea.
            cabecera += (f"<br><span style='color:#86500A'>{c.fuera_de_periodo} "
                         "línea(s) del listado son de fuera del periodo que ha puesto "
                         "(se han comprobado igual). Si pidió a Aplifisa esas fechas, "
                         "cambie el periodo: lo guardado de ellas no se está "
                         "reclamando.</span>")
        if c.fuera_programa:
            cabecera += (f"<br><span style='color:#5D7084'>{c.fuera_programa} "
                         "guardada(s) en el programa de otras fechas no se "
                         "reclaman.</span>")
        self.resumen.setText(cabecera)
        self._pintar_trimestres()
        self.combo_filtro.blockSignals(True)
        self.combo_filtro.clear()
        problemas = sum(n for e, n in cuenta.items() if e != BIEN)
        self.combo_filtro.addItem(f"Solo lo que falla ({problemas})", "fallos")
        self.combo_filtro.addItem(f"Todo ({len(c.lineas)})", "todo")
        for estado in ORDEN_ESTADO:
            if cuenta[estado]:
                self.combo_filtro.addItem(
                    f"{TEXTO_ESTADO[estado]} ({cuenta[estado]})", estado)
        self.combo_filtro.setCurrentIndex(0 if problemas else 1)
        self.combo_filtro.blockSignals(False)
        self._pintar_detalle()
        self.boton_informe.setEnabled(True)

    def _pintar_trimestres(self) -> None:
        tabla, c = self.tabla_trimestres, self.cuadre
        filas = []
        for tipo in c.tipos:
            totales = {"programa": [0.0, 0.0, 0.0, 0], "aplifisa": [0.0, 0.0, 0.0, 0]}
            for (tipo_t, anio, trimestre), datos in sorted(c.trimestres.items()):
                if tipo_t != tipo:
                    continue
                filas.append((f"{CLASE[tipo]} · {trimestre}T {anio}", datos))
                for lado in totales:
                    for i in range(4):
                        totales[lado][i] += datos[lado][i]
            filas.append((f"{CLASE[tipo]} · periodo", totales))
        tabla.setRowCount(len(filas))
        for r, (titulo, datos) in enumerate(filas):
            p, a = datos["programa"], datos["aplifisa"]
            valores = [titulo, str(p[3]), str(a[3]), _eur(p[0]), _eur(a[0]),
                       _eur(p[1]), _eur(a[1]), _eur(p[2]), _eur(a[2])]
            cuadra = p[3] == a[3] and all(abs(p[i] - a[i]) <= 0.02 for i in range(3))
            for col, texto in enumerate(valores):
                item = QTableWidgetItem(texto)
                if col:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if titulo.endswith("periodo"):
                    fuente = item.font()
                    fuente.setBold(True)
                    item.setFont(fuente)
                if not cuadra and col:
                    item.setForeground(QColor("#B43737"))
                tabla.setItem(r, col, item)
        # Lo justo para sus filas: el resto, para el detalle.
        tabla.resizeRowsToContents()
        alto = tabla.horizontalHeader().sizeHint().height() + 2 * tabla.frameWidth() + 2
        alto += sum(tabla.rowHeight(r) for r in range(tabla.rowCount()))
        tabla.setFixedHeight(alto)

    def lineas_visibles(self):
        filtro = self.combo_filtro.currentData()
        lineas = self.cuadre.lineas if self.cuadre else []
        if filtro == "fallos":
            return [l for l in lineas if l.estado != BIEN]
        if filtro in TEXTO_ESTADO:
            return [l for l in lineas if l.estado == filtro]
        return list(lineas)

    def _pintar_detalle(self) -> None:
        lineas = self.lineas_visibles()
        self._visibles = lineas
        self.tabla.setRowCount(len(lineas))
        for r, l in enumerate(lineas):
            p, a = l.programa, l.aplifisa
            fuente_datos = p or a
            base = p.base if p else a.base
            cuota = p.cuota if p else a.cuota
            total = (p.total if p and p.total is not None else
                     (a.neto if a else base + (cuota or 0)))
            pdf = (os.path.basename(p.pdf) if p and p.pdf_guardado else
                   ("no está" if p else "—"))
            valores = [TEXTO_ESTADO[l.estado], CLASE[fuente_datos.tipo][:-1],
                       fuente_datos.fecha, p.num_factura if p else (a.num_proveedor or ""),
                       fuente_datos.nombre, _eur(base), _eur(cuota), _eur(total),
                       a.numero if a else "", pdf, l.detalle]
            color, fondo = COLORES[l.estado]
            for col, texto in enumerate(valores):
                item = QTableWidgetItem(str(texto or ""))
                if col in (5, 6, 7):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == 0:
                    item.setForeground(QColor(color))
                    item.setBackground(QColor(fondo))
                    negrita = item.font()
                    negrita.setBold(True)
                    item.setFont(negrita)
                if col in (4, 10):
                    item.setToolTip(str(texto or ""))
                self.tabla.setItem(r, col, item)
        self._seleccion()

    # ------------------------------------------------------------ acciones
    def _actual(self):
        r = self.tabla.currentRow()
        lineas = getattr(self, "_visibles", [])
        return lineas[r] if 0 <= r < len(lineas) else None

    def _seleccion(self) -> None:
        l = self._actual()
        self.boton_pdf.setEnabled(bool(l and l.programa and l.programa.pdf_guardado))
        self.boton_lote.setEnabled(bool(l and l.programa and l.programa.fila is not None))

    def _abrir_pdf(self) -> None:
        l = self._actual()
        if l and l.programa and l.programa.pdf_guardado:
            archivo.abrir(l.programa.pdf)

    def _ver_en_lote(self) -> None:
        l = self._actual()
        if l and l.programa and l.programa.fila is not None:
            self._fila_elegida = l.programa.fila
            self.accept()

    def fila_seleccionada(self) -> int:
        return self._fila_elegida

    # ------------------------------------------------------------ informe
    def html_informe(self) -> str:
        c = self.cuadre
        nif, nombre = self.cliente()
        filas_trimestre = []
        for r in range(self.tabla_trimestres.rowCount()):
            celdas = [html.escape(self.tabla_trimestres.item(r, col).text())
                      for col in range(self.tabla_trimestres.columnCount())]
            filas_trimestre.append(
                "<tr>" + "".join(f"<td{' align=right' if i else ''}>{t}</td>"
                                 for i, t in enumerate(celdas)) + "</tr>")
        filas = []
        for l in c.lineas:
            p, a = l.programa, l.aplifisa
            d = p or a
            filas.append(
                f"<tr><td>{TEXTO_ESTADO[l.estado]}</td><td>{CLASE[d.tipo][:-1]}</td>"
                f"<td>{html.escape(d.fecha)}</td>"
                f"<td>{html.escape((p.num_factura if p else a.num_proveedor) or '')}</td>"
                f"<td>{html.escape(d.nombre or '')}</td>"
                f"<td align=right>{_eur(p.total if p and p.total is not None else (a.neto if a else p.base))}</td>"
                f"<td>{html.escape(a.numero if a else '')}</td>"
                f"<td>{html.escape(l.detalle)}</td></tr>")
        cabeceras_t = "".join(f"<th>{html.escape(self.tabla_trimestres.horizontalHeaderItem(i).text())}</th>"
                              for i in range(self.tabla_trimestres.columnCount()))
        return (
            "<html><body style='font-family:sans-serif; font-size:9pt'>"
            f"<h2>Cuadre con Aplifisa · {html.escape(nombre or nif or 'Cliente')}</h2>"
            f"<p>{html.escape(self._texto_periodo().capitalize())} · "
            f"hecho el {date.today():%d/%m/%Y}</p>"
            f"<p>{self.resumen.text()}</p>"
            "<table border=1 cellspacing=0 cellpadding=3>"
            f"<tr>{cabeceras_t}</tr>{''.join(filas_trimestre)}</table><br>"
            "<table border=1 cellspacing=0 cellpadding=3><tr><th>Resultado</th>"
            "<th>Tipo</th><th>Fecha</th><th>Nº factura</th><th>Proveedor o cliente</th>"
            "<th>Total</th><th>Nº Aplifisa</th><th>Qué pasa</th></tr>"
            + "".join(filas) + "</table></body></html>")

    def guardar_informe(self, ruta: str) -> str:
        if not ruta.lower().endswith(".pdf"):
            ruta += ".pdf"
        documento = QTextDocument(self)
        documento.setHtml(self.html_informe())
        escritor = QPdfWriter(ruta)
        escritor.setResolution(150)
        escritor.setPageSize(QPageSize(QPageSize.A4))
        escritor.setPageOrientation(QPageLayout.Landscape)
        documento.print_(escritor)
        del escritor
        return ruta

    def _guardar_informe(self) -> None:
        if not self.cuadre:
            return
        from .ventana_comun import ESCRITORIO
        nif, nombre = self.cliente()
        limpio = re.sub(r"[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ -]+", "", nombre or nif or "CLIENTE").strip()
        desde = min(d for d, _h in self.cuadre.periodos.values())
        hasta = max(h for _d, h in self.cuadre.periodos.values())
        sugerido = os.path.join(
            ESCRITORIO, f"CUADRE APLIFISA {limpio} "
            f"{desde:%d-%m-%Y} a {hasta:%d-%m-%Y}.pdf")
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar informe del cuadre", sugerido, "Documento PDF (*.pdf)")
        if ruta:
            ruta = self.guardar_informe(ruta)
            self.resumen.setText(self.resumen.text() + f"<br>Informe guardado: "
                                 f"{html.escape(ruta)}")
