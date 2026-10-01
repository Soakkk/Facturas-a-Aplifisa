"""El documento original y la ficha de la factura seleccionada.

Parte de la ventana principal (app.py), separada para que cada tarea
viva en su sitio. Los métodos usan el estado de la ventana (self).
"""

from __future__ import annotations

import html
import os

from PySide6.QtCore import QEvent, QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPixmap

from facturas_excel import ajustes, imagen_visor, localizar
from facturas_excel.banda_avisos import AVISO, EXITO, INFO
from facturas_excel.conceptos import descripcion_de
from facturas_excel.control_facturas import clave_documento
from facturas_excel.ficha_incidencias import FichaIncidencias
from facturas_excel.procesar import normaliza_nif
from facturas_excel.resumen import eur
from facturas_excel.lote import CAMPOS_NUMERO, CORREGIDA, PENDIENTES, REVISADA
from facturas_excel.estilo import ACCENT, DANGER, MUTED, WARNING
from facturas_excel.tabla_facturas import CAMPO_DE_COLUMNA, COLUMNA_DE_CAMPO, C_ESTADO
from facturas_excel.validacion import ERROR, OK, REVISAR
from facturas_excel.ventana_validacion import MENSAJE_CORREGIDA, MENSAJE_REVISADA
from facturas_excel.visor import Recuadro

# El zoom se cuenta sobre la hoja entera a la vista (1 = hoja entera). Se
# puede acercar hasta 4 veces eso, o hasta 3 veces el ancho del visor si el
# visor es bajo y ancho (la hoja entera ahí se ve muy pequeña).
ZOOM_MAXIMO = 4.0
ZOOM_TOPE = 12.0
PASO_ZOOM = 1.25
# Lo que se espera desde el último cambio de zoom antes de sacar la hoja fina
# (mientras, se amplía la que ya hay: el zoom responde al momento).
ESPERA_NITIDA_MS = 90
# Datos de cabecera de una discrepancia: valen igual en todas las líneas de
# la factura y se guardan tal como se leen, así que se pueden copiar a todas.
# El desglose y el suplido van a base_iva (su lectura es un texto o el
# importe del suplido) y la retención vive en una sola línea.
CABECERA_DISCREPANCIA = ("num_factura", "fecha", "total_impreso", "nif")
# Importes que en un abono van en negativo (la lectura los da en positivo).
IMPORTES_DISCREPANCIA = {"total_impreso", "base_iva", "cuota_iva",
                         "cuota_requiv", "cuota_irpf"}
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
        self._png_visor = None
        self._fuente_visor = None
        self._nitida = None
        self._sin_nitida = set()
        self._zoom_visor = 1.0
        self.lbl_origen.setText("Arrastre aquí un PDF o imágenes para comenzar")
        self.lbl_pagina.clear()
        self.lbl_img.clear()
        self.lbl_img.poner_movible(False)
        self.lbl_img.setMinimumSize(250, 180)
        self.lbl_img.setText(
            "Suelte aquí las facturas\no use «Abrir PDF o imágenes»")

    # ---------- la hoja en el visor ----------
    def _escala_hoja_entera(self) -> float:
        """Escala con la que la hoja entera cabe en el visor."""
        pix = self._pixmap_documento
        sitio = self.visor_scroll.maximumViewportSize()
        return min(max(1, sitio.width()) / max(1, pix.width()),
                   max(1, sitio.height()) / max(1, pix.height()))

    def _zoom_ancho(self) -> float:
        """El zoom con el que la hoja ocupa todo el ancho del visor."""
        sitio = self.visor_scroll.maximumViewportSize()
        escala = max(1, sitio.width()) / max(1, self._pixmap_documento.width())
        return max(1.0, escala / self._escala_hoja_entera())

    def _zoom_maximo(self) -> float:
        return min(ZOOM_TOPE, max(ZOOM_MAXIMO, 3 * self._zoom_ancho()))

    def _tamano_hoja(self) -> QSize:
        """Lo que ocupa la hoja en pantalla con el zoom actual."""
        pix = self._pixmap_documento
        escala = self._escala_hoja_entera() * self._zoom_visor
        return QSize(max(1, round(pix.width() * escala)),
                     max(1, round(pix.height() * escala)))

    def _fuente_util(self):
        """(original, página) de la hoja a la vista, si se puede sacar fina."""
        fuente = getattr(self, "_fuente_visor", None)
        if not fuente or fuente in getattr(self, "_sin_nitida", ()):
            return None
        return fuente

    def _hoja_nitida(self, fisico: QSize):
        """La hoja sacada del original al tamaño exacto (o None).

        Devuelve False si el PDF está ocupado (se reintenta enseguida).
        """
        fuente = self._fuente_util()
        if not fuente:
            return None
        clave = (*fuente, fisico.width(), fisico.height())
        guardada = getattr(self, "_nitida", None)
        if guardada and guardada[0] == clave:
            return guardada[1]
        pix = self._pixmap_documento
        try:
            hoja = imagen_visor.hoja(fuente[0], fuente[1], fisico.width(),
                                     fisico.height(), pix.width() / pix.height())
        except imagen_visor.Ocupado:
            return False
        if hoja is None:
            # No está o no es la misma hoja: se queda la imagen de lectura.
            if not hasattr(self, "_sin_nitida"):
                self._sin_nitida = set()
            self._sin_nitida.add(fuente)
            return None
        imagen = QImage(hoja.muestras, hoja.ancho, hoja.alto, hoja.linea,
                        QImage.Format_RGB888).copy()
        nitida = QPixmap.fromImage(imagen)
        if nitida.size() != fisico:
            nitida = nitida.scaled(fisico, Qt.IgnoreAspectRatio,
                                   Qt.SmoothTransformation)
        # Con la escala de la pantalla ya puesta: así no se copia al pintarla.
        nitida.setDevicePixelRatio(self.lbl_img.devicePixelRatioF() or 1.0)
        self._nitida = (clave, nitida)
        return nitida

    @staticmethod
    def _con_escala(pix: QPixmap, escala: float) -> QPixmap:
        """La imagen con la escala de la pantalla (125 %, 150 %…)."""
        if pix.devicePixelRatio() != escala:
            pix = QPixmap(pix)
            pix.setDevicePixelRatio(escala)
        return pix

    def _pintar_pixmap_visor(self, inmediata: bool = False) -> None:
        """Pone la hoja al tamaño del zoom, nítida aunque se acerque mucho.

        Antes se ampliaba la imagen de lectura (150 ppp en JPEG) y al acercar
        se veía borrosa. Ahora se saca la hoja del PDF original al tamaño
        exacto de la pantalla; mientras llega, se amplía la que hay.
        """
        if self._pixmap_documento.isNull():
            return
        tam = self._tamano_hoja()
        escala_pantalla = self.lbl_img.devicePixelRatioF() or 1.0
        fisico = QSize(max(1, round(tam.width() * escala_pantalla)),
                       max(1, round(tam.height() * escala_pantalla)))
        fuente = self._fuente_util()
        guardada = getattr(self, "_nitida", None)
        if not (guardada and fuente and guardada[0][:2] == fuente):
            guardada = None
        pix = None
        if guardada and guardada[0][2:] == (fisico.width(), fisico.height()):
            pix = guardada[1]
        elif inmediata and fuente:
            pix = self._hoja_nitida(fisico) or None
        if pix is None:
            # Al momento: la mejor imagen que ya hay, ampliada o reducida.
            base = guardada[1] if guardada else self._pixmap_documento
            pix = base.scaled(fisico, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            if self._fuente_util():
                self._timer_nitida.start(ESPERA_NITIDA_MS)
        self.lbl_img.setMinimumSize(tam)
        # Se ajusta ya (no al repintar) para poder colocar las barras al
        # momento, con el punto acercado bajo el ratón.
        self.lbl_img.resize(tam.expandedTo(self.visor_scroll.viewport().size()))
        self.lbl_img.setPixmap(self._con_escala(pix, escala_pantalla))
        sitio = self.visor_scroll.maximumViewportSize()
        self.lbl_img.poner_movible(tam.width() > sitio.width()
                                   or tam.height() > sitio.height())

    def _pintar_nitida(self) -> None:
        """Cuando el zoom se para, la hoja fina sustituye a la ampliada."""
        if self._pixmap_documento.isNull() or not self._fuente_util():
            return
        tam = self._tamano_hoja()
        escala_pantalla = self.lbl_img.devicePixelRatioF() or 1.0
        fisico = QSize(max(1, round(tam.width() * escala_pantalla)),
                       max(1, round(tam.height() * escala_pantalla)))
        nitida = self._hoja_nitida(fisico)
        if nitida is False:
            self._timer_nitida.start(250)      # la lectura está usando el PDF
            return
        if nitida is None:
            return
        self.lbl_img.setPixmap(self._con_escala(nitida, escala_pantalla))

    def _zoom_en(self, factor: float, punto: QPointF | None = None,
                 zoom: float | None = None) -> None:
        """Acerca o aleja dejando quieto el punto señalado (o el centro)."""
        if self._pixmap_documento.isNull():
            return
        nuevo = zoom if zoom is not None else self._zoom_visor * factor
        nuevo = min(self._zoom_maximo(), max(1.0, nuevo))
        if abs(nuevo - self._zoom_visor) < 1e-3:
            return
        horizontal = self.visor_scroll.horizontalScrollBar()
        vertical = self.visor_scroll.verticalScrollBar()
        vista = self.visor_scroll.viewport().size()
        if punto is None:
            punto = QPointF(horizontal.value() + vista.width() / 2,
                            vertical.value() + vista.height() / 2)
        antes = self.lbl_img.rect_imagen()
        if antes is None or antes.width() <= 0 or antes.height() <= 0:
            fx = fy = 0.5
        else:
            fx = min(1.0, max(0.0, (punto.x() - antes.x()) / antes.width()))
            fy = min(1.0, max(0.0, (punto.y() - antes.y()) / antes.height()))
        en_vista = QPointF(punto.x() - horizontal.value(),
                           punto.y() - vertical.value())
        self._zoom_visor = nuevo
        self._pintar_pixmap_visor()
        despues = self.lbl_img.rect_imagen()
        if despues is not None:
            horizontal.setValue(round(despues.x() + fx * despues.width() - en_vista.x()))
            vertical.setValue(round(despues.y() + fy * despues.height() - en_vista.y()))

    def eventFilter(self, objeto, evento):
        # El visor cambia de tamaño (divisor, ventana): la hoja se reencaja.
        if (objeto is getattr(self, "visor_scroll", None)
                and evento.type() == QEvent.Resize
                and not self._pixmap_documento.isNull()):
            self._timer_visor.start()
        # La línea de lo leído plegado se recorta al ancho que tenga.
        if (objeto is getattr(self, "lbl_lectura_resumen", None)
                and evento.type() == QEvent.Resize):
            self._pintar_resumen_lectura()
        return super().eventFilter(objeto, evento)

    def _cambiar_zoom_visor(self, incremento: float) -> None:
        """Botones de la lupa: un paso más cerca o más lejos."""
        self._zoom_en(PASO_ZOOM if incremento > 0 else 1 / PASO_ZOOM)

    def _zoom_doble_clic(self, punto: QPointF) -> None:
        """Doble clic: acerca ese punto; si ya está cerca, la hoja entera."""
        if self._zoom_visor > 1.05:
            self._zoom_en(1.0, punto, zoom=1.0)
        else:
            self._zoom_en(1.0, punto, zoom=max(2.5, self._zoom_ancho()))

    def _ver_hoja_entera(self) -> None:
        self._zoom_en(1.0, zoom=1.0)

    def _ajustar_al_ancho(self) -> None:
        self._zoom_en(1.0, zoom=self._zoom_ancho())
        self.visor_scroll.verticalScrollBar().setValue(0)

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
        pagina = factura.pagina_origen or 0
        self.lbl_pagina.setText(f"Pág. {pagina}" if pagina else "")
        fuente = ((factura.origen_imagen, int(pagina))
                  if factura.origen_imagen else None)
        if png is not getattr(self, "_png_visor", None) or self._pixmap_documento.isNull():
            pix = QPixmap()
            pix.loadFromData(png)
            if pix.isNull():
                self._limpiar_visor()
                self.lbl_origen.setText(origen or "Documento cargado")
                self.lbl_img.setText("Vista previa no disponible para esta factura")
                return
            self._pixmap_documento = pix
            self._png_visor = png
            self._fuente_visor = fuente
            self._nitida = None
            self._pintar_pixmap_visor(inmediata=True)
        else:
            # La misma hoja (otra línea de la factura, o la ventana cambió
            # de tamaño): no se vuelve a cargar. El original puede haber
            # cambiado de sitio al archivarse el taco.
            self._fuente_visor = fuente
            self._pintar_pixmap_visor()
        self._pintar_recuadros()

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
        de_linea = {"base_iva", "pct_iva", "cuota_iva", "base_requiv",
                    "pct_requiv", "cuota_requiv"}

        def repartir(mensajes):
            marcas, linea, otros = {}, [], []
            for m in mensajes:
                campos = getattr(m, "campos", None) or ()
                gravedad = getattr(m, "gravedad", REVISAR)
                texto = str(m)
                if texto in (MENSAJE_REVISADA, MENSAJE_CORREGIDA):
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
        # La retención resta; en un abono ya es negativa y entonces suma.
        formula = " + ".join(partes) + (
            "" if not irpf else
            f" − {eur(irpf).replace(' €', '')}" if irpf > 0 else
            f" + {eur(-irpf).replace(' €', '')}")
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
            aplicable = self._destino_discrepancia(d, filas_doc) is not None
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
            "estado": self._estilo_presentacion(registro.presentacion),
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
            # Corregida o revisada: los avisos ya los vio una persona.
            "avisos_vistos": registro.presentacion in (CORREGIDA, REVISADA),
        }

    def _refrescar_ficha(self) -> None:
        if not hasattr(self, "ficha"):
            return
        r = self.tabla.currentRow()
        visible = 0 <= r < len(self.filas) and not self.tabla.isRowHidden(r)
        if hasattr(self, "btn_revisada_factura"):
            # Sin factura a la vista no hay nada que dar por revisado.
            self.btn_revisada_factura.setEnabled(visible)
        if not visible:
            self.ficha.vacio()
            self._poner_resumen_lectura(None)
            return
        datos = self._datos_ficha(r)
        self.ficha.mostrar(datos)
        self._poner_resumen_lectura(datos)

    # ---------- lo leído, plegado a una línea ----------
    def _poner_resumen_lectura(self, d) -> None:
        """La línea que se ve con la lectura plegada: estado y motivo.

        Si hay que elegir entre las dos lecturas, la lectura se despliega
        sola para esa factura (sin cambiar la preferencia guardada): plegada,
        la elección no se vería y se daría por buena la lectura 1.
        """
        if not hasattr(self, "lbl_lectura_resumen"):
            return
        self._lectura_con_decision = bool(d and d["discrepancias"])
        if d is None:
            self._resumen_lectura = ("", None, None, "", "")
        else:
            texto, color, fondo = d["estado"]
            if d["discrepancias"]:
                motivo = (f"{len(d['discrepancias'])} dato(s) no coinciden "
                          "entre las dos lecturas")
            elif d["cuadre"] and not d["cuadre"]["ok"]:
                motivo = "El total no cuadra"
            else:
                motivo = next((m for _g, m in d["otros_motivos"]), "")
            self._resumen_lectura = (texto, color, fondo, d["titulo"], motivo)
        self._pintar_resumen_lectura()
        self._aplicar_plegado(self._plegado_efectivo())

    def _pintar_resumen_lectura(self) -> None:
        """Estado, título y motivo en una línea; el motivo se recorta con
        «…» a lo que quepa y entero sale en el globo."""
        texto, color, fondo, titulo, motivo = getattr(
            self, "_resumen_lectura", ("", None, None, "", ""))
        etiqueta = self.lbl_lectura_resumen
        if not texto:
            etiqueta.setText(
                f"<span style='color:{MUTED}'>Seleccione una factura.</span>")
            etiqueta.setToolTip("Pulse para desplegar lo leído.")
            return
        medida = etiqueta.fontMetrics()
        negrita = QFont(etiqueta.font())
        negrita.setBold(True)
        ocupado = (QFontMetrics(negrita).horizontalAdvance(f" {texto}  {titulo} ")
                   + medida.horizontalAdvance(" · ") + 16)
        visible = medida.elidedText(
            motivo, Qt.ElideRight, max(0, etiqueta.width() - ocupado))
        partes = [
            f"<span style='background:{fondo}; color:{color.name()};"
            f" font-weight:700'>&nbsp;{html.escape(texto)}&nbsp;</span>",
            f"<b>{html.escape(titulo)}</b>"]
        if motivo:
            # Aunque no quepa nada, «…» dice que hay un motivo (en el globo).
            partes.append(f"<span style='color:{MUTED}'>· "
                          f"{html.escape(visible or '…')}</span>")
        etiqueta.setText(" ".join(partes))
        etiqueta.setToolTip(
            (f"{motivo}\n\n" if motivo else "") + "Pulse para desplegar lo leído.")

    def _plegado_efectivo(self) -> bool:
        return (self.btn_plegar_lectura.isChecked()
                and not getattr(self, "_lectura_con_decision", False))

    def _plegar_lectura(self, plegada: bool, guardar: bool = True) -> None:
        """El usuario pliega o despliega lo leído (se recuerda)."""
        if guardar:
            ajustes.guardar("lectura_plegada", bool(plegada))
        self._aplicar_plegado(self._plegado_efectivo())

    def _aplicar_plegado(self, plegada: bool) -> None:
        """Plegada: lo leído se quita de al lado de la hoja y queda una línea
        con el estado y el motivo (el divisor recuerda su ancho)."""
        if not hasattr(self, "panel_lectura"):
            return
        self.panel_lectura.setVisible(not plegada)
        self.lbl_lectura_resumen.setVisible(plegada)
        self.btn_plegar_lectura.setArrowType(
            Qt.LeftArrow if plegada else Qt.RightArrow)

    def _destino_discrepancia(self, d: dict, filas_doc) -> list | None:
        """Las líneas donde se puede poner sin riesgo la otra lectura de `d`.

        None si no se puede hacer solo (se corrige en la tabla): copiar un
        suplido o una retención a todas las líneas de la factura la
        estropearía.
        """
        if d.get("campo_factura") in CABECERA_DISCREPANCIA:
            return list(filas_doc)
        campo = d.get("campo")
        if campo == "lineas_iva":
            l2 = [x for x in (d.get("lineas_2") or []) if isinstance(x, dict)]
            return list(filas_doc) if len(l2) == 1 and len(filas_doc) == 1 \
                else None
        if campo in ("suplidos", "cuota_irpf"):
            suplido = campo == "suplidos"
            lineas = [r for r in filas_doc
                      if bool(self.filas[r].factura.es_suplido) == suplido]
            return lineas if len(lineas) == 1 else None
        return None

    def _con_signo_del_documento(self, campo: str, valor, filas_doc):
        """En un abono los importes van en negativo, como los dejó procesar."""
        if campo in IMPORTES_DISCREPANCIA and isinstance(valor, float) and any(
                (self.filas[r].factura.total_impreso or 0) < 0 for r in filas_doc):
            return -abs(valor)
        return valor

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
        from facturas_excel.extraccion import _num
        if lectura == 1 and d.get("campo_factura") in CABECERA_DISCREPANCIA:
            # La lectura 1 es lo que ya había… salvo que la persona lo haya
            # cambiado a mano después: entonces se vuelve a poner. Solo los
            # datos de cabecera: los importes por línea no se tocan.
            campo = d["campo_factura"]
            valor = d.get("valor_1")
            if campo in CAMPOS_NUMERO:
                valor = _num(valor)
            elif campo == "nif":
                valor = normaliza_nif(valor) or None
            else:
                valor = None if valor in (None, "") else str(valor)
            valor = round(valor, 2) if isinstance(valor, float) else valor
            valor = self._con_signo_del_documento(campo, valor, filas_doc)
            distintas = [r for r in filas_doc
                         if getattr(self.filas[r].factura, campo, None) != valor]
            for r in distintas:
                setattr(self.filas[r].factura, campo, valor)
                self.tabla.pintar(r, self.filas[r], (COLUMNA_DE_CAMPO[campo],))
            if distintas:
                self._invalidar_contraste_registro()
                if campo == "nif":
                    self._nif_escrito_a_mano(fila)
                self._marcar_corregida_documento(fila)
        if lectura == 2:
            destino = self._destino_discrepancia(d, filas_doc)
            if destino is None:
                self._avisar("Este dato no se puede copiar solo: corríjalo "
                             "en la tabla.", AVISO)
                return
            if d.get("campo") == "lineas_iva":
                linea = next(x for x in d.get("lineas_2") or []
                             if isinstance(x, dict))
                cambios = [(destino[0], campo, _num(linea.get(clave)))
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
                cambios = [(r, campo, valor) for r in destino]
            for r, campo, valor in cambios:
                valor = round(valor, 2) if isinstance(valor, float) else valor
                setattr(self.filas[r].factura, campo,
                        self._con_signo_del_documento(campo, valor, filas_doc))
                self.tabla.pintar(r, self.filas[r], (COLUMNA_DE_CAMPO[campo],))
            self._invalidar_contraste_registro()
            if d.get("campo_factura") == "nif":
                self._nif_escrito_a_mano(fila)
            # Elegir el otro valor es corregir a mano: la factura queda
            # «Corregida» (después de propagar, que invalida a las demás).
            self._marcar_corregida_documento(fila)
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
            self._zoom_visor = min(self._zoom_maximo(),
                                   self._zoom_visor * 26 / max(rect.height(), 1))
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
            # Solo lo que aún hay que mirar (no lo revisado ni lo corregido).
            if fila.presentacion not in PENDIENTES:
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

