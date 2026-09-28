"""Lo que va y viene de Aplifisa: exportar el Excel y cuadrar con su listado.

Parte de la ventana principal (app.py), separada para que cada tarea
viva en su sitio. Los métodos usan el estado de la ventana (self).
"""

from __future__ import annotations

import os

from collections import Counter
from dataclasses import replace
from datetime import date

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox


from facturas_excel import ajustes, archivo, escaner, historial
from facturas_excel.banda_avisos import AVISO, EXITO, INFO
from facturas_excel.dialogo_orden import (
    PDF as ORDEN_PDF, DialogoOrden,
)
from facturas_excel.dialogo_registro import DialogoRegistro
from facturas_excel.conceptos import texto_para
from facturas_excel.config_columnas import leer_config
from facturas_excel.exportar import (
    exportar_excel, ordenar_para_exportar, totales_del_excel, verificar_excel,
)
from facturas_excel.procesar import aprender_nifs_exportados
from facturas_excel.registro import contrastar, leer_registro
from facturas_excel.resumen import eur
from facturas_excel.rutas import ruta_config
from facturas_excel.tabla_facturas import C_ESTADO
from facturas_excel.validacion import ERROR, REVISAR, fecha_de

from facturas_excel.ventana_comun import ESCRITORIO


class AplifisaMixin:
    def _ofrecer_contraste(self, ruta):
        """Se ha soltado el listado de Aplifisa en vez de facturas."""
        if not self.tabla.rowCount():
            QMessageBox.information(
                self, "Listado de Aplifisa",
                f"«{os.path.basename(ruta)}» es el listado de apuntes de "
                f"Aplifisa, no un taco de facturas.\n\n"
                f"Cargue primero las facturas y luego pulse «Comprobar "
                f"registro» para cuadrarlas con él.")
            return
        if QMessageBox.question(
                self, "Listado de Aplifisa",
                f"«{os.path.basename(ruta)}» parece el listado de apuntes de "
                f"Aplifisa.\n\n¿Lo contrasto con las facturas del lote?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes) == QMessageBox.Yes:
            self._contrastar_registro(ruta)

    def _contrastar_registro(self, ruta=""):
        """El cuadre a tres bandas: factura -> Excel -> lo que quedo en Aplifisa.

        Se le pasa el PDF del "Listado de apuntes" de Aplifisa y se compara
        apunte a apunte con el lote. Es la unica forma de ver si algo se quedo
        sin importar o entro con otro importe.
        """
        if not self.tabla.rowCount():
            QMessageBox.information(
                self, "Contrastar con Aplifisa",
                "Cargue primero el lote de facturas que quiere comprobar.")
            return
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(
                self, "Listado de apuntes de Aplifisa (PDF)", ESCRITORIO,
                "Listado de Aplifisa (*.pdf)")
        if not ruta:
            return
        try:
            registro = leer_registro(ruta)
        except Exception as e:
            QMessageBox.critical(self, "No se pudo leer el listado", str(e))
            return
        if not registro.apuntes:
            QMessageBox.warning(
                self, "Sin apuntes",
                "No se han encontrado apuntes en ese PDF.\n\n"
                "Tiene que ser el listado que imprime Aplifisa. Un PDF de papel "
                "escaneado no sirve: hay que sacarlo del propio programa.")
            return
        facturas = [self._leer_fila(r) for r in range(self.tabla.rowCount())]
        informe = contrastar(facturas, registro)
        self._aplicar_informe_registro(informe)
        dialogo = DialogoRegistro(informe, registro, self, facturas=facturas)
        dialogo.exec()
        fila = dialogo.fila_seleccionada()
        if 0 <= fila < self.tabla.rowCount():
            self._limpiar_filtros()
            self.tabla.selectRow(fila)
            self.tabla.scrollToItem(self.tabla.item(fila, C_ESTADO))
        self.lbl_estado.setText(
            f"Contraste con Aplifisa: {informe.emparejadas} cuadran, "
            f"{len(informe.sin_registrar)} sin registrar, "
            f"{len(informe.de_mas)} de más, {len(informe.distintas)} distintas, "
            f"{len(informe.dudosas)} dudosas.")

    def _aplicar_informe_registro(self, informe) -> None:
        self._informe_registro = informe
        for fila, estado in informe.resultados.items():
            if fila < len(self.filas):
                self.filas[fila]["registro_estado"] = estado
                self.filas[fila]["registro_detalle"] = informe.detalles.get(fila, [])
        cuentas = Counter(informe.resultados.values())
        diferencias = sum(cuentas.get(e, 0)
                          for e in ("sin_registrar", "distinta", "dudosa"))
        opciones = [
            ("Aplifisa: todas", "todas"),
            (f"Aplifisa: solo diferencias ({diferencias})", "diferencias"),
            (f"No registradas ({cuentas.get('sin_registrar', 0)})", "sin_registrar"),
            (f"Importe/dato distinto ({cuentas.get('distinta', 0)})", "distinta"),
            (f"Coincidencia dudosa ({cuentas.get('dudosa', 0)})", "dudosa"),
            (f"Cuadradas ({cuentas.get('cuadra', 0)})", "cuadra"),
        ]
        self.combo_filtro_registro.blockSignals(True)
        self.combo_filtro_registro.clear()
        for texto, dato in opciones:
            self.combo_filtro_registro.addItem(texto, dato)
        self.combo_filtro_registro.setCurrentIndex(1 if diferencias else 0)
        self.combo_filtro_registro.setVisible(True)
        self.combo_filtro_registro.blockSignals(False)
        self._distribuir_herramientas(self.width())
        self._aplicar_filtro()

    def _invalidar_contraste_registro(self) -> None:
        """Una edición hace que el resultado anterior deje de ser fiable."""
        self._informe_registro = None
        for registro in getattr(self, "filas", []):
            registro.pop("registro_estado", None)
            registro.pop("registro_detalle", None)
        if not hasattr(self, "combo_filtro_registro"):
            return
        self.combo_filtro_registro.blockSignals(True)
        self.combo_filtro_registro.clear()
        self.combo_filtro_registro.addItem("Aplifisa: todas", "todas")
        self.combo_filtro_registro.setVisible(False)
        self.combo_filtro_registro.blockSignals(False)

    def _olvidar_exportacion(self) -> None:
        filas = [f for f in self._filas_seleccionadas()
                 if self.filas[f].get("ya_exportada")]
        if not filas:
            self._avisar("Seleccione filas marcadas como «ya exportada».", AVISO)
            return
        por_tipo = {"gasto": [], "venta": []}
        for fila in filas:
            por_tipo[self._tipo_fila(fila)].append(self._leer_fila(fila))
        cliente = getattr(self, "_cliente_nif", "")
        nombre = getattr(self, "_cliente_nombre", "")
        cuantas = historial.olvidar(cliente, por_tipo, nombre)
        self._revalidar_todo()

        def deshacer():
            historial.registrar(cliente, por_tipo, {}, nombre)
            self._revalidar_todo()
        self._avisar(f"{cuantas} factura(s) quitadas del historial de "
                     "exportadas.", INFO, deshacer=deshacer)

    def _para_aplifisa(self, facturas):
        """Traduce el concepto al texto que Aplifisa tiene parametrizado.

        Con el texto, el apunte entra con su cuenta Y su subclave puestas, que
        es lo unico que evita tener que elegir el GXX a mano en cada proveedor
        nuevo. Si no esta configurado, se exporta el codigo de siempre.
        """
        if not ajustes.leer("concepto_texto", False):
            return facturas
        traducidas = []
        for f in facturas:
            texto = texto_para(f.concepto, f.subclave)
            traducidas.append(replace(f, concepto=texto) if texto else f)
        return traducidas

    def _clasificar_exportacion(self):
        """Separa lo exportable, lo manual y lo que todavía bloquea el lote."""
        por_tipo = {"gasto": [], "venta": []}
        excluidas = []
        errores = []
        pendientes_revision = []
        self._ya_exportadas_export = []
        for fila in range(self.tabla.rowCount()):
            f = self._leer_fila(fila)
            registro = self.filas[fila]
            # El aviso de «ya exportada» no cuenta aquí: se decide aparte.
            estado = registro.get("estado_base", registro.get("estado"))
            if getattr(self, "_errores_documento", {}).get(fila) and not f.tratamiento_manual:
                errores.append(fila)
            elif fila in self._duplicados:
                excluidas.append((fila, "duplicada"))
            elif f.tratamiento_manual:
                excluidas.append((fila, f.tratamiento_manual))
            elif estado == ERROR:
                errores.append(fila)
            elif estado == REVISAR and not f.revision_confirmada:
                pendientes_revision.append(fila)
            else:
                if registro.get("ya_exportada"):
                    self._ya_exportadas_export.append((fila, f))
                por_tipo[self._tipo_fila(fila)].append(f)
        return por_tipo, excluidas, errores, pendientes_revision

    def _decidir_ya_exportadas(self, por_tipo) -> bool:
        """Pregunta qué hacer con las facturas que ya salieron en otro lote.

        Devuelve False si se cancela la exportación. Por defecto se QUITAN:
        volver a importarlas las registraría dos veces.
        """
        ya = getattr(self, "_ya_exportadas_export", [])
        if not ya:
            return True
        lineas = "\n".join(
            f"  · Línea {fila + 1}: {f.num_factura or 's/n'} de "
            f"{f.nombre or '?'} — exportada el "
            f"{self.filas[fila]['ya_exportada'].get('exportada', '?')}"
            for fila, f in ya[:8])
        if len(ya) > 8:
            lineas += f"\n  · … y {len(ya) - 8} más"
        caja = QMessageBox(self)
        caja.setIcon(QMessageBox.Warning)
        caja.setWindowTitle("Facturas ya exportadas")
        caja.setText(f"{len(ya)} línea(s) ya salieron hacia Aplifisa en otro "
                     "lote. Si se vuelven a importar, quedarán registradas "
                     "dos veces.")
        caja.setInformativeText(lineas)
        quitar = caja.addButton("Exportar sin ellas", QMessageBox.AcceptRole)
        incluir = caja.addButton("Incluirlas otra vez", QMessageBox.DestructiveRole)
        caja.addButton("Cancelar", QMessageBox.RejectRole)
        caja.setDefaultButton(quitar)
        caja.exec()
        pulsado = caja.clickedButton()
        if pulsado is quitar:
            fuera = {id(f) for _fila, f in ya}
            for tipo in por_tipo:
                por_tipo[tipo] = [f for f in por_tipo[tipo] if id(f) not in fuera]
            return True
        return pulsado is incluir

    def _nombre_cliente_archivo(self) -> str:
        nombre = (getattr(self, "_cliente_nombre", "") or
                  next((b.get("cliente", "") for b in self._bloques
                        if b.get("cliente")), "") or "Cliente")
        return escaner.sanear(nombre)

    @staticmethod
    def _ejercicio_exportacion(facturas) -> int:
        """Ejercicio predominante del lote para ordenar su documentación."""
        ejercicios = []
        for factura in facturas:
            fecha = fecha_de(factura.fecha)
            if fecha:
                ejercicios.append(fecha.year)
        return (Counter(ejercicios).most_common(1)[0][0]
                if ejercicios else date.today().year)

    def _exportar_todo(self):
        """Genera en una sola operación los Excel de gastos e ingresos."""
        self._revalidar_todo()
        self._guardar_muestra_revision()
        clientes = {b.get("nif") or b.get("cliente") for b in self._bloques
                    if b.get("nif") or b.get("cliente")}
        if len(clientes) > 1:
            QMessageBox.critical(
                self, "Hay varios clientes",
                "No se puede crear un Excel con bloques de clientes distintos. "
                "Quite el bloque incorrecto o pulse «Vaciar todo» para empezar "
                "con otro cliente.")
            return
        por_tipo, excluidas, errores, pendientes_revision = \
            self._clasificar_exportacion()

        if errores or pendientes_revision:
            partes = []
            if errores:
                partes.append(f"{len(errores)} línea(s) roja(s) con errores")
            if pendientes_revision:
                partes.append(
                    f"{len(pendientes_revision)} línea(s) ámbar sin confirmar")
            QMessageBox.warning(
                self, "Revisión pendiente",
                "No se ha exportado nada. Corrija los errores y marque como "
                "revisados los avisos comprobados:\n\n  · "
                + "\n  · ".join(partes))
            self._siguiente_incidencia()
            return
        if not self._decidir_ya_exportadas(por_tipo):
            return
        if not any(por_tipo.values()):
            self._avisar(
                "No hay facturas para exportar automáticamente. "
                f"Se han apartado {len(excluidas)} línea(s) para gestión "
                "manual o ya exportadas.", INFO)
            return

        # El orden manda: Aplifisa renumera las facturas recibidas segun entran,
        # asi que este orden es el que tendran en el registro.
        dialogo_orden = DialogoOrden(self)
        if dialogo_orden.exec() != QDialog.Accepted:
            return
        dialogo_orden.recordar()
        orden = dialogo_orden.orden()
        for tipo in por_tipo:
            por_tipo[tipo] = ordenar_para_exportar(por_tipo[tipo], orden)
        problemas_export = []      # lo que no cuadre entre archivo y pantalla
        resumen_archivos = []      # (ruta, lineas, totales) para enseñarlo
        tipos_exportados = []      # los parciales se borran solo tras verificar
        rutas_por_tipo = {}
        cliente_archivo = self._nombre_cliente_archivo()
        for tipo, xml in (
            ("gasto", "gastos.xml"),
            ("venta", "ingresos.xml"),
        ):
            if not por_tipo[tipo]:
                continue
            ejercicio = self._ejercicio_exportacion(por_tipo[tipo])
            ruta = archivo.ruta_excel_consolidado(
                cliente_archivo, ejercicio, tipo)
            nombre = os.path.basename(ruta)
            config = leer_config(ruta_config(xml))
            listas = self._para_aplifisa(por_tipo[tipo])
            exportar_excel(listas, config, ruta)
            # DOBLE CONTRASTE: se vuelve a leer el archivo escrito y se compara
            # con lo que hay en pantalla. Es el ultimo paso antes de que los
            # apuntes entren en la contabilidad, y era el unico sin comprobar.
            fallos = verificar_excel(listas, config, ruta)
            problemas_export.extend(f"{nombre}: {p}" for p in fallos[:5])
            resumen_archivos.append(
                (ruta, len(listas), totales_del_excel(config, ruta)))
            tipos_exportados.append(tipo)
            rutas_por_tipo[tipo] = ruta

        if problemas_export:
            QMessageBox.critical(
                self, "El archivo NO coincide con la pantalla",
                "Al volver a leer lo escrito, esto no cuadra:\n\n  · "
                + "\n  · ".join(problemas_export)
                + "\n\nNO importe estos archivos en Aplifisa sin revisarlos.")
            return

        temporales_eliminados = sum(
            len(archivo.eliminar_excel_temporales(cliente_archivo, tipo))
            for tipo in tipos_exportados
        )
        # Solo con el Excel ya verificado: se recuerda lo exportado (para
        # avisar si vuelve a aparecer) y se aprenden sus NIF, ya revisados.
        exportadas = {t: por_tipo[t] for t in tipos_exportados}
        historial.registrar(getattr(self, "_cliente_nif", ""), exportadas,
                            rutas_por_tipo, getattr(self, "_cliente_nombre", ""))
        # Las apartadas para gestión manual (bien de inversión, suplidos…)
        # no van al Excel, pero son documentación del cliente: también tienen
        # su PDF. Los duplicados y las sustituidas, no.
        apartadas = {"gasto": [], "venta": []}
        for fila, motivo in excluidas:
            if motivo == "duplicada" or str(motivo).startswith("Sustituida"):
                continue
            apartadas[self._tipo_fila(fila)].append(self.filas[fila]["factura"])
        texto_expediente = self._archivar_exportacion(
            exportadas, rutas_por_tipo, apartadas)
        aprender_nifs_exportados(
            [f for t in tipos_exportados for f in por_tipo[t]])
        self._revalidar_todo()
        detalle = "\n".join(
            f"  · {os.path.basename(ruta)}: {lineas} línea(s), "
            f"base {eur(t['base_iva'])}, "
            f"IVA {eur(t['cuota_iva'])}"
            for ruta, lineas, t in resumen_archivos)
        carpetas = "\n".join(
            f"  · {carpeta}" for carpeta in sorted({
                os.path.dirname(ruta) for ruta, _lineas, _totales in resumen_archivos
            }))
        self._avisar(
            f"Exportación terminada y comprobada. Excel consolidados preparados para Aplifisa:\n\n{detalle}\n\n"
            f"Guardados en el Escritorio:\n{carpetas}\n\n"
            + ("En el orden del PDF escaneado.\n" if orden == ORDEN_PDF
               else "Por fecha de factura.\n")
            + (f"Apartadas de la exportación automática: {len(excluidas)} línea(s).\n"
               if excluidas else "")
            + (f"Eliminados {temporales_eliminados} Excel temporales de partes.\n"
               if temporales_eliminados else "")
            + "Comprobado: lo escrito en los archivos coincide con lo que ve "
              "en pantalla, línea por línea. No se han creado Excel parciales."
            + texto_expediente,
            EXITO, segundos=0)
