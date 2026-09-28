"""El documento original y la ficha de la factura seleccionada.

Parte de la ventana principal (app.py), separada para que cada tarea
viva en su sitio. Los métodos usan el estado de la ventana (self).
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QLabel, QPushButton, QScrollArea, QVBoxLayout,
)

from facturas_excel import ajustes, localizar
from facturas_excel.banda_avisos import AVISO, EXITO, INFO
from facturas_excel.conceptos import descripcion_de
from facturas_excel.control_facturas import clave_documento
from facturas_excel.ficha_incidencias import FichaIncidencias
from facturas_excel.procesar import normaliza_nif
from facturas_excel.resumen import eur
from facturas_excel.lote import CAMPOS_NUMERO
from facturas_excel.estilo import ACCENT, DANGER, WARNING
from facturas_excel.tabla_facturas import CAMPO_DE_COLUMNA, COLUMNA_DE_CAMPO, C_ESTADO
from facturas_excel.validacion import ERROR, OK, REVISAR
from facturas_excel.visor import Recuadro

ZOOM_MAXIMO = 4.0
ETIQUETA_DATO = {
    "nif": "NIF", "nombre": "Nombre", "num_factura": "Nº", "fecha": "Fecha",
    "base_iva": "Base", "cuota_iva": "IVA", "pct_iva": "% IVA",
    "cuota_requiv": "Recargo", "cuota_irpf": "Retención", "total_impreso": "Total",
}


class FichaMixin:
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

    def _limpiar_visor(self) -> None:
        self.lbl_img.poner_recuadros([])
        self._pixmap_documento = QPixmap()
        self._zoom_visor = 1.0
        self.lbl_origen.setText("Arrastre aquí un PDF o imágenes para comenzar")
        self.lbl_pagina.clear()
        self.lbl_img.clear()
        self.lbl_img.setMinimumSize(250, 180)
        self.lbl_img.setText(
            "Suelte aquí las facturas\no use «Abrir PDF o imágenes»")

    def _pintar_pixmap_visor(self) -> None:
        if self._pixmap_documento.isNull():
            return
        viewport = self.visor_scroll.viewport().size()
        ancho = max(250, int(viewport.width() * self._zoom_visor))
        alto = max(180, int(viewport.height() * self._zoom_visor))
        self.lbl_img.setMinimumSize(ancho, alto)
        self.lbl_img.setPixmap(self._pixmap_documento.scaled(
            ancho, alto, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _cambiar_zoom_visor(self, incremento: float) -> None:
        if self._pixmap_documento.isNull():
            return
        self._zoom_visor = min(ZOOM_MAXIMO, max(0.7, self._zoom_visor + incremento))
        self._pintar_pixmap_visor()

    def _mostrar_miniatura(self):
        r = self.tabla.currentRow()
        self._refrescar_ficha()
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
            self._pintar_recuadros()
        else:
            self._limpiar_visor()
            self.lbl_origen.setText(origen or "Documento cargado")
            self.lbl_img.setText("Vista previa no disponible para esta factura")

    # ---------- ficha de la factura ----------

    def _filas_del_documento(self, fila: int) -> list[int]:
        clave = clave_documento(self.filas[fila]["factura"])
        return [r for r in range(len(self.filas))
                if clave_documento(self.filas[r]["factura"]) == clave]

    def _datos_ficha(self, fila: int) -> dict:
        """Lo que enseña la ficha, a partir de la fila y de sus avisos."""
        from facturas_excel.doble_lectura import _fmt as fmt_lectura
        registro = self.filas[fila]
        f = registro["factura"]
        tipo = self._tipo_fila(fila)
        estado = registro.get("estado", OK)
        confirmada = (estado == REVISAR and f.revision_confirmada
                      and not f.tratamiento_manual)
        de_linea = {"base_iva", "pct_iva", "cuota_iva", "base_requiv",
                    "pct_requiv", "cuota_requiv"}

        def repartir(mensajes):
            marcas, linea, otros = {}, [], []
            for m in mensajes:
                campos = getattr(m, "campos", None) or ()
                gravedad = getattr(m, "gravedad", REVISAR)
                texto = str(m)
                if texto == "Revisada y confirmada manualmente":
                    continue
                destino = [c for c in campos if c not in ("total_impreso",)]
                if not destino:
                    otros.append((gravedad, texto))
                    continue
                for campo in destino:
                    if campo in de_linea:
                        linea.append((gravedad, texto))
                    else:
                        clave = "concepto" if campo == "subclave" else campo
                        marcas.setdefault(clave, []).append((gravedad, texto))
            return marcas, linea, otros

        marcas, _linea, otros = repartir(registro.get("mensajes") or [])
        filas_doc = self._filas_del_documento(fila)
        lineas = []
        vistos = set()
        for r in filas_doc:
            g = self.filas[r]["factura"]
            _m, marcas_linea, _o = repartir(self.filas[r].get("mensajes") or [])
            marcas_linea = [x for x in marcas_linea if x not in vistos]
            vistos.update(marcas_linea)
            lineas.append({"base": g.base_iva, "pct": g.pct_iva,
                           "cuota": g.cuota_iva, "pct_re": g.pct_requiv,
                           "cuota_re": g.cuota_requiv,
                           "suplido": getattr(g, "es_suplido", False),
                           "marcas": marcas_linea})
        docs = [self.filas[r]["factura"] for r in filas_doc]
        irpf = next((g.cuota_irpf for g in docs if g.cuota_irpf is not None), None)
        partes = []
        calculado = 0.0
        for g in docs:
            for valor in (g.base_iva, g.cuota_iva, g.cuota_requiv, g.suplidos):
                if valor is not None:
                    calculado += valor
                    partes.append(eur(valor).replace(" €", ""))
        if irpf:
            calculado -= irpf
        formula = " + ".join(partes) + (f" − {eur(irpf).replace(' €', '')}"
                                         if irpf else "")
        impreso = f.total_impreso
        cuadre = {"formula": formula or "—", "calculado": round(calculado, 2),
                  "impreso": impreso,
                  "ok": impreso is not None and abs(round(calculado, 2) - impreso) <= 0.02
                  } if partes else None
        # Las diferencias de la doble lectura tienen su propio recuadro.
        otros = [x for x in otros if not x[1].startswith("Doble lectura")]
        if impreso is not None and cuadre and not cuadre["ok"]:
            otros = [x for x in otros if "total no cuadra" not in x[1].lower()]
        discrepancias = []
        cajas = self._localizaciones.get(localizar.clave_imagen(registro.png))
        for d in getattr(f, "discrepancias", ()) or ():
            aplicable = d.get("campo_factura") in COLUMNA_DE_CAMPO
            if d.get("campo") == "lineas_iva":
                l2 = [x for x in (d.get("lineas_2") or []) if isinstance(x, dict)]
                aplicable = len(l2) == 1 and len(filas_doc) == 1
            # Si ya se sabe dónde está cada dato: ¿aparece cada valor en la hoja?
            en_hoja = (None, None)
            campo_hoja = localizar.DE_DOBLE_LECTURA.get(d.get("campo"))
            if cajas is not None and campo_hoja:
                en_hoja = tuple(bool(localizar.cajas_de(cajas, campo_hoja, d.get(v)))
                                for v in ("valor_1", "valor_2"))
            discrepancias.append(dict(d, aplicable=aplicable, en_hoja=en_hoja, textos=(
                fmt_lectura(d.get("valor_1")), fmt_lectura(d.get("valor_2")))))
        verificacion = getattr(f, "verificacion", "")
        if verificacion == "doble":
            lectura = ("Leída por dos modelos: coinciden en todo."
                       if not discrepancias else
                       f"Leída por dos modelos: {len(discrepancias)} dato(s) no "
                       "coinciden. Elija el bueno mirando el documento.")
        elif verificacion == "simple":
            lectura = "Leída por un solo modelo: sin contrastar con otra lectura."
        else:
            lectura = "Lectura anterior a la doble lectura (sin contrastar)."
        cuenta = f.concepto or ""
        if f.subclave:
            cuenta += f" ({f.subclave})"
        descripcion = descripcion_de(f.concepto, f.subclave) if f.concepto else ""
        if descripcion:
            cuenta += f" · {descripcion}"
        return {
            "fila": fila,
            "estado": self._presentacion_estado(estado, f, confirmada),
            "titulo": f"Línea {fila + 1} · {f.num_factura or 'sin nº'}",
            "rol": "Proveedor" if tipo == "gasto" else "Cliente",
            "nombre": f.nombre or "", "nif": f.nif or "",
            "num": f.num_factura or "", "fecha": f.fecha or "",
            "lineas": lineas, "irpf": irpf, "cuadre": cuadre,
            "tipo": "Gasto (factura recibida)" if tipo == "gasto"
                    else "Ingreso (factura emitida)",
            "cuenta": cuenta, "marcas": marcas, "otros_motivos": otros,
            "lectura": lectura, "doble": verificacion == "doble",
            "discrepancias": discrepancias,
        }

    def _refrescar_ficha(self) -> None:
        if not hasattr(self, "ficha"):
            return
        r = self.tabla.currentRow()
        if r < 0 or r >= len(self.filas) or self.tabla.isRowHidden(r):
            self.ficha.vacio()
            return
        self.ficha.mostrar(self._datos_ficha(r))

    def _resolver_discrepancia(self, fila: int, indice: int, lectura: int) -> None:
        """Se queda con una de las dos lecturas de un dato en disputa."""
        if fila >= len(self.filas):
            return
        f = self.filas[fila]["factura"]
        discrepancias = list(getattr(f, "discrepancias", ()) or ())
        if indice >= len(discrepancias):
            return
        d = discrepancias[indice]
        filas_doc = self._filas_del_documento(fila)
        if lectura == 2:
            from facturas_excel.extraccion import _num
            if d.get("campo") == "lineas_iva":
                linea = next(x for x in d.get("lineas_2") or []
                             if isinstance(x, dict))
                cambios = [(fila, campo, _num(linea.get(clave)))
                           for campo, clave in (("base_iva", "base"),
                                                ("pct_iva", "tipo_iva"),
                                                ("cuota_iva", "cuota_iva"),
                                                ("pct_requiv", "pct_requiv"),
                                                ("cuota_requiv", "cuota_requiv"))]
            else:
                campo = d["campo_factura"]
                valor = d.get("valor_2")
                if campo in CAMPOS_NUMERO:
                    valor = _num(valor)
                elif campo == "nif":
                    valor = normaliza_nif(valor) or None
                else:
                    valor = None if valor in (None, "") else str(valor)
                cambios = [(r, campo, valor) for r in filas_doc]
            for r, campo, valor in cambios:
                setattr(self.filas[r].factura, campo,
                        round(valor, 2) if isinstance(valor, float) else valor)
                self.tabla.pintar(r, self.filas[r], (COLUMNA_DE_CAMPO[campo],))
            self._invalidar_contraste_registro()
            self._invalidar_revision_documento(fila)
            if d.get("campo_factura") == "nif":
                self._nif_escrito_a_mano(fila)
        campo = d.get("campo")
        for r in filas_doc:
            registro = self.filas[r]
            for factura in [registro["factura"], *registro.get("fuentes", [])]:
                factura.discrepancias = tuple(
                    x for x in (getattr(factura, "discrepancias", ()) or ())
                    if x.get("campo") != campo)
        self._revalidar_todo()
        elegido = (d.get(f"modelo_{lectura}") or f"lectura {lectura}")
        self._avisar(f"{d.get('etiqueta')}: se queda el valor de {elegido}.",
                     EXITO)

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

    # ---------- dónde está cada dato en la hoja ----------
    def _recuadros_de_fila(self, r: int, columna=None) -> list:
        """Recuadros para el visor: el dato pulsado, o lo que tiene avisos."""
        if not (0 <= r < len(self.filas)):
            return []
        fila = self.filas[r]
        cajas = self._localizaciones.get(localizar.clave_imagen(fila.png))
        if not cajas:
            return []
        f = fila.factura
        salida = []

        def poner(campo, valor, color, texto, destacado=False, discontinuo=False,
                  sin_valor=False):
            encontradas = localizar.cajas_de(cajas, campo, valor)
            if not encontradas and sin_valor:
                encontradas = localizar.cajas_de(cajas, campo)
            for c in encontradas:
                salida.append(Recuadro(c.x0, c.y0, c.x1, c.y1, color, texto,
                                       destacado, discontinuo))

        disputas = {}
        for d in getattr(f, "discrepancias", ()) or ():
            campo = localizar.DE_DOBLE_LECTURA.get(d.get("campo"))
            if campo:
                disputas[campo] = d
        campo_pulsado = CAMPO_DE_COLUMNA.get(columna) if columna is not None else None
        if campo_pulsado in localizar.CAMPOS:
            etiqueta = ETIQUETA_DATO.get(campo_pulsado, campo_pulsado)
            d = disputas.get(campo_pulsado)
            if d:
                poner(campo_pulsado, d.get("valor_1"), WARNING, f"{etiqueta} · lectura 1",
                      destacado=True)
                poner(campo_pulsado, d.get("valor_2"), WARNING, f"{etiqueta} · lectura 2",
                      destacado=True, discontinuo=True)
            else:
                poner(campo_pulsado, getattr(f, campo_pulsado), ACCENT, etiqueta,
                      destacado=True, sin_valor=True)
            return salida
        if self._columna_senalada == "todo":
            # «¿De dónde sale?»: todos los datos de la factura.
            for campo in localizar.CAMPOS:
                if campo not in disputas:
                    poner(campo, getattr(f, campo), ACCENT,
                          ETIQUETA_DATO.get(campo, campo))
        # Los datos con aviso, en su color, y las disputas.
        graves = {}
        for m in fila.mensajes or ():
            for campo in getattr(m, "campos", None) or ():
                if campo in localizar.CAMPOS:
                    grave = getattr(m, "gravedad", REVISAR) == ERROR
                    graves[campo] = graves.get(campo, False) or grave
        for campo, grave in graves.items():
            if campo in disputas:
                continue
            salida[:] = [x for x in salida
                         if x.texto != ETIQUETA_DATO.get(campo, campo)]
            poner(campo, getattr(f, campo), DANGER if grave else WARNING,
                  ETIQUETA_DATO.get(campo, campo), sin_valor=True)
        for campo, d in disputas.items():
            etiqueta = ETIQUETA_DATO.get(campo, campo)
            poner(campo, d.get("valor_1"), WARNING, f"{etiqueta} · 1")
            poner(campo, d.get("valor_2"), WARNING, f"{etiqueta} · 2", discontinuo=True)
        return salida

    def _pintar_recuadros(self) -> None:
        r = self.tabla.currentRow()
        columna = self._columna_senalada if isinstance(self._columna_senalada, int) else None
        recuadros = self._recuadros_de_fila(r, columna)
        if self._columna_senalada == "todo" and self._zoom_visor != 1.0:
            # Todos los datos: la hoja entera a la vista.
            self._zoom_visor = 1.0
            self._pintar_pixmap_visor()
        self.lbl_img.poner_recuadros(recuadros)
        destacado = next((x for x in recuadros if x.destacado), None)
        if not destacado:
            return
        # Si en el tamaño actual el dato no se leería, se acerca la hoja.
        rect = self.lbl_img.rect_de(destacado)
        if rect is not None and rect.height() < 22:
            self._zoom_visor = min(ZOOM_MAXIMO, self._zoom_visor * 26 / max(rect.height(), 1))
            self._pintar_pixmap_visor()

        def centrar():
            caja = self.lbl_img.rect_de(destacado)
            if caja is not None:
                self.visor_scroll.ensureVisible(int(caja.center().x()),
                                                int(caja.center().y()), 120, 90)
        QTimer.singleShot(0, centrar)

    def _senalar_celda(self, fila: int, columna: int) -> None:
        """Al pulsar una celda, el visor señala de dónde sale ese dato."""
        self._columna_senalada = columna if columna in CAMPO_DE_COLUMNA else None
        if fila == self.tabla.currentRow():
            self._pintar_recuadros()

    def _peticiones_de_imagen(self, png: bytes) -> list:
        """Lo que hay que buscar en esa hoja: todas sus líneas y sus disputas."""
        filas = [x for x in self.filas if x.png == png]
        return localizar.peticiones(
            [x.factura for x in filas],
            [d for x in filas for d in (getattr(x.factura, "discrepancias", ()) or ())])

    def _localizar(self, trabajos: list, en_silencio: bool) -> bool:
        from facturas_excel.claves import leer_api_key
        from facturas_excel.hilos import HiloLocalizar
        if not trabajos:
            return False
        if self._hilo_localizar and self._hilo_localizar.isRunning():
            if not en_silencio:
                self._avisar("Ya se están señalando datos en el documento; "
                             "espere un momento.", INFO)
            return False
        try:
            api_key = leer_api_key() or ""
        except Exception:
            api_key = ""
        modelo = localizar.principal()
        if not api_key or not modelo:
            if not en_silencio:
                self._avisar("Falta la API key de Gemini.", AVISO)
            return False
        self._localizando.update(clave for clave, *_ in trabajos)
        hilo = HiloLocalizar(api_key, modelo, trabajos)
        hilo.hecho.connect(self._on_localizado)
        hilo.gasto.connect(self._on_gasto)
        hilo.terminado.connect(
            lambda bien, mal: self._on_localizacion_terminada(bien, mal, en_silencio))
        self._hilo_localizar = hilo
        hilo.start()
        return True

    def _localizar_dudosas(self) -> None:
        """Señala solas las facturas en ámbar o rojo (se puede desactivar)."""
        if not ajustes.leer("localizar_dudosas", True):
            return
        trabajos = {}
        for fila in self.filas:
            f = fila.factura
            if fila.estado not in (REVISAR, ERROR) or f.tratamiento_manual:
                continue
            if fila.estado == REVISAR and f.revision_confirmada:
                continue
            if not fila.png:
                continue
            clave = localizar.clave_imagen(fila.png)
            if clave in self._localizaciones or clave in self._localizando \
                    or clave in trabajos:
                continue
            lista = self._peticiones_de_imagen(fila.png)
            if lista:
                trabajos[clave] = (clave, fila.png, lista)
        if self._localizar(list(trabajos.values()), en_silencio=True):
            self.lbl_estado.setText(
                f"Señalando en el documento los datos de {len(trabajos)} "
                "hoja(s) dudosa(s)…")

    def _localizar_actual(self) -> None:
        r = self.tabla.currentRow()
        if not (0 <= r < len(self.filas)) or not self.filas[r].png:
            self._avisar("Elija primero una factura de la tabla.", AVISO)
            return
        fila = self.filas[r]
        clave = localizar.clave_imagen(fila.png)
        if clave in self._localizaciones:
            # Ya se sabe: se enseñan todos sus datos.
            self._columna_senalada = "todo"
            self._pintar_recuadros()
            return
        if self._localizar([(clave, fila.png, self._peticiones_de_imagen(fila.png))],
                           en_silencio=False):
            self._columna_senalada = "todo"
            self.lbl_estado.setText("Buscando en el documento dónde está cada dato…")

    def _on_localizado(self, clave: str, cajas) -> None:
        self._localizando.discard(clave)
        self._localizaciones[clave] = list(cajas or [])
        r = self.tabla.currentRow()
        if 0 <= r < len(self.filas) and \
                localizar.clave_imagen(self.filas[r].png) == clave:
            self._refrescar_ficha()      # «está / no aparece en la hoja»
            self._pintar_recuadros()

    def _on_localizacion_terminada(self, bien: int, mal: int, en_silencio: bool) -> None:
        self._localizando.clear()
        if bien:
            texto = (f"Datos señalados en el documento ({bien} hoja(s)). Pulse "
                     "una celda para ver de dónde sale.")
            self.lbl_estado.setText(texto)
            if not en_silencio:
                self._avisar(texto, EXITO)
        elif mal and not en_silencio:
            self._avisar("No se ha podido señalar nada en el documento.", AVISO)

