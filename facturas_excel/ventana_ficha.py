"""El documento original y la ficha de la factura seleccionada.

Parte de la ventana principal (app.py), separada para que cada tarea
viva en su sitio. Los métodos usan el estado de la ventana (self).
"""

from __future__ import annotations

import os


from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QLabel, QPushButton, QScrollArea, QVBoxLayout,
)


from facturas_excel.banda_avisos import EXITO
from facturas_excel.conceptos import descripcion_de
from facturas_excel.control_facturas import clave_documento
from facturas_excel.ficha_incidencias import FichaIncidencias
from facturas_excel.procesar import normaliza_nif
from facturas_excel.resumen import eur
from facturas_excel.lote import CAMPOS_NUMERO
from facturas_excel.tabla_facturas import COLUMNA_DE_CAMPO, C_ESTADO
from facturas_excel.validacion import OK, REVISAR



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
        self._zoom_visor = min(2.5, max(0.7, self._zoom_visor + incremento))
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
        for d in getattr(f, "discrepancias", ()) or ():
            aplicable = d.get("campo_factura") in COLUMNA_DE_CAMPO
            if d.get("campo") == "lineas_iva":
                l2 = [x for x in (d.get("lineas_2") or []) if isinstance(x, dict)]
                aplicable = len(l2) == 1 and len(filas_doc) == 1
            discrepancias.append(dict(d, aplicable=aplicable, textos=(
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
