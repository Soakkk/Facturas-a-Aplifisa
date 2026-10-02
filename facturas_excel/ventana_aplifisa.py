"""Lo que va y viene de Aplifisa: exportar el Excel y cuadrar con su listado.

Parte de la ventana principal (app.py), separada para que cada tarea
viva en su sitio. Los métodos usan el estado de la ventana (self).
"""

from __future__ import annotations

import os
import traceback

from collections import Counter
from dataclasses import replace
from datetime import date

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from facturas_excel import ajustes, archivo, escaner, historial
from facturas_excel import errores as registro_errores
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
from facturas_excel.registro import contrastar_listado, leer_registro
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
        filas = range(self.tabla.rowCount())
        facturas = [self._leer_fila(r) for r in filas]
        # Gastos con un listado de compras e ingresos con uno de ventas, y
        # solo las fechas que cubre el listado.
        informe = contrastar_listado(
            facturas, [self._tipo_fila(r) for r in filas], registro)
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
            f"{len(informe.dudosas)} dudosas."
            + (f" {len(informe.no_comprobadas)} sin comprobar (otro tipo u "
               "otras fechas)." if informe.no_comprobadas else ""))

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

    def _momentos_de_lectura(self) -> dict:
        """{id(factura): cuándo se leyó su bloque}, para el registro."""
        cuando = {b.get("nombre"): b.get("leido_en") for b in self._bloques}
        salida = {}
        for registro in self.filas:
            momento = cuando.get(registro.bloque)
            if momento:
                for f in (registro.factura, *registro.fuentes):
                    salida[id(f)] = momento
        return salida

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
        """Separa lo exportable, los duplicados y lo que todavía bloquea.

        Ya no se aparta nada «para gestión manual»: esas facturas no llegaban
        a Aplifisa y descuadraban el registro. Ahora son avisos ámbar y salen
        en el Excel en cuanto se marcan revisadas.
        """
        por_tipo = {"gasto": [], "venta": []}
        excluidas = []
        errores = []
        pendientes_revision = []
        self._ya_exportadas_export = []
        self._filas_export = []        # (fila, factura) de lo exportable
        for fila in range(self.tabla.rowCount()):
            f = self._leer_fila(fila)
            registro = self.filas[fila]
            # El aviso de «ya exportada» no cuenta aquí: se decide aparte.
            estado = registro.get("estado_base", registro.get("estado"))
            if getattr(self, "_errores_documento", {}).get(fila):
                errores.append(fila)
            elif fila in self._duplicados:
                excluidas.append((fila, "duplicada"))
            elif estado == ERROR:
                errores.append(fila)
            elif estado == REVISAR and not registro.get("aceptada"):
                # Ni revisada con el botón ni corregida a mano.
                pendientes_revision.append(fila)
            else:
                if registro.get("ya_exportada"):
                    self._ya_exportadas_export.append((fila, f))
                self._filas_export.append((fila, f))
                por_tipo[self._tipo_fila(fila)].append(f)
        return por_tipo, excluidas, errores, pendientes_revision

    def _lineas_texto(self, pares, detalle=None) -> str:
        """«· Línea 3: F-12 de PROVEEDOR» de las primeras ocho."""
        lineas = "\n".join(
            f"  · Línea {fila + 1}: {f.num_factura or 's/n'} de {f.nombre or '?'}"
            + (detalle(fila) if detalle else "")
            for fila, f in pares[:8])
        if len(pares) > 8:
            lineas += f"\n  · … y {len(pares) - 8} más"
        return lineas

    @staticmethod
    def _quedarse_con(por_tipo, pares) -> None:
        dentro = {id(f) for _fila, f in pares}
        for tipo in por_tipo:
            por_tipo[tipo] = [f for f in por_tipo[tipo] if id(f) in dentro]

    def _decidir_ya_exportadas(self, por_tipo) -> bool:
        """Qué hacer con lo que ya salió hacia Aplifisa. False: se cancela.

        Una factura cuenta como exportada en cuanto se crea su Excel, aunque
        luego la importación en Aplifisa se cancele o se quede a medias. Por
        eso nunca se deja un callejón sin salida: si todo el lote ya salió,
        no se ofrece «solo las nuevas» (no quedaría nada que exportar) sino
        comprobar con el listado de Aplifisa cuáles faltan y exportar esas.
        """
        if getattr(self, "_informe_registro", None) is not None:
            return self._decidir_con_listado(por_tipo)
        ya = getattr(self, "_ya_exportadas_export", [])
        if not ya:
            return True
        fuera = {id(f) for _fila, f in ya}
        nuevas = [(fila, f) for fila, f in getattr(self, "_filas_export", [])
                  if id(f) not in fuera]
        caja = QMessageBox(self)
        caja.setIcon(QMessageBox.Warning)
        caja.setWindowTitle("Facturas ya exportadas")
        caja.setText(
            (f"{len(ya)} línea(s) ya salieron hacia Aplifisa en otro lote."
             if nuevas else
             f"Todas las líneas del lote ({len(ya)}) ya salieron hacia "
             "Aplifisa.")
            + " Si se vuelven a importar, quedarán registradas dos veces.")
        caja.setInformativeText(
            self._lineas_texto(ya, lambda fila: " — exportada el "
                               f"{self.filas[fila]['ya_exportada'].get('exportada', '?')}")
            + "\n\n¿Alguna no llegó a entrar en Aplifisa (se canceló la "
            "importación o la rechazó)? «Comprobar con el listado de "
            "Aplifisa…» mira cuáles faltan y exporta solo esas.")
        solo_nuevas = (caja.addButton(f"Exportar solo las nuevas ({len(nuevas)})",
                                      QMessageBox.AcceptRole) if nuevas else None)
        comprobar = caja.addButton("Comprobar con el listado de Aplifisa…",
                                   QMessageBox.ActionRole)
        incluir = caja.addButton("Incluirlas todas otra vez",
                                 QMessageBox.DestructiveRole)
        caja.addButton("Cancelar", QMessageBox.RejectRole)
        caja.setDefaultButton(solo_nuevas or comprobar)
        caja.exec()
        pulsado = caja.clickedButton()
        if pulsado is not None and pulsado is solo_nuevas:
            self._quedarse_con(por_tipo, nuevas)
            return True
        if pulsado is comprobar:
            self._contrastar_registro()
            if getattr(self, "_informe_registro", None) is None:
                return False           # no se eligió el listado
            return self._decidir_con_listado(por_tipo)
        return pulsado is incluir

    def _decidir_con_listado(self, por_tipo) -> bool:
        """Con el listado de Aplifisa ya comprobado se sabe lo que falta:
        se exporta eso (lo nuevo y lo que salió pero no llegó a entrar)."""
        exportables = getattr(self, "_filas_export", [])
        ya = {id(f) for _fila, f in getattr(self, "_ya_exportadas_export", [])}

        def estado(fila):
            return self.filas[fila].get("registro_estado")
        # Lo que el listado no cubre (otro tipo, otras fechas, cargado
        # después): falta si no salió; si ya salió, se queda fuera.
        faltan = [(fila, f) for fila, f in exportables
                  if estado(fila) == "sin_registrar"
                  or (estado(fila) is None and id(f) not in ya)]
        sin_comprobar = sum(1 for fila, f in exportables
                            if estado(fila) is None and id(f) in ya)
        estan = len(exportables) - len(faltan) - sin_comprobar
        if not estan and not sin_comprobar:
            return True
        raras = sum(1 for fila, _f in exportables
                    if estado(fila) in ("distinta", "dudosa"))
        caja = QMessageBox(self)
        caja.setIcon(QMessageBox.Question if faltan else QMessageBox.Warning)
        caja.setWindowTitle("Lo que ya está en Aplifisa")
        if faltan:
            caja.setText(f"Según el listado de Aplifisa, {estan} línea(s) del "
                         f"lote ya están registradas y faltan {len(faltan)}.")
            texto = "Se exportarán solo las que faltan:\n" + self._lineas_texto(faltan)
        else:
            caja.setText("Según el listado de Aplifisa no falta ninguna: "
                         f"{estan} línea(s) del lote ya están registradas.")
            texto = "Si se vuelven a importar, quedarán registradas dos veces."
        if sin_comprobar:
            texto += (f"\n\n{sin_comprobar} ya exportada(s) no entran en el "
                      "listado (son del otro tipo o de otras fechas): no se "
                      "exportan otra vez.")
        if raras:
            texto += (f"\n\n{raras} están en Aplifisa con otro importe o con "
                      "una coincidencia dudosa: no se exportan otra vez. "
                      "Revíselas con el filtro «Aplifisa: solo diferencias».")
        caja.setInformativeText(texto)
        boton_faltan = (caja.addButton(f"Exportar las que faltan ({len(faltan)})",
                                       QMessageBox.AcceptRole) if faltan else None)
        todas = caja.addButton("Exportarlas todas otra vez",
                               QMessageBox.DestructiveRole)
        cancelar = caja.addButton("Cancelar", QMessageBox.RejectRole)
        caja.setDefaultButton(boton_faltan or cancelar)
        caja.exec()
        pulsado = caja.clickedButton()
        if pulsado is not None and pulsado is boton_faltan:
            self._quedarse_con(por_tipo, faltan)
            return True
        return pulsado is todas

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
            # Con una ventana, no en la banda: si no, parece que «Exportar»
            # no hace nada.
            QMessageBox.information(
                self, "Nada que exportar",
                "No queda ninguna factura para el Excel: las "
                f"{len(excluidas) + len(self._ya_exportadas_export)} línea(s) "
                "del lote están duplicadas o ya se exportaron.")
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
        numerados = []             # ya había otro con ese nombre: va con _2…
        nuevos = []                # lo creado en esta exportación
        cliente_archivo = self._nombre_cliente_archivo()
        nombre = ""
        try:
            for tipo, xml in (
                ("gasto", "gastos.xml"),
                ("venta", "ingresos.xml"),
            ):
                if not por_tipo[tipo]:
                    continue
                nombre = "el Excel de " + ("gastos" if tipo == "gasto" else "ingresos")
                ejercicio = self._ejercicio_exportacion(por_tipo[tipo])
                propia = archivo.ruta_excel_consolidado(
                    cliente_archivo, ejercicio, tipo)
                # Nunca se pisa el Excel de una exportación anterior (puede
                # estar abierto o sin importar): el nuevo lleva «_2», «_3»…
                ruta = archivo.excel_sin_pisar(propia)
                nombre = os.path.basename(ruta)
                config = leer_config(ruta_config(xml))
                listas = self._para_aplifisa(por_tipo[tipo])
                try:
                    exportar_excel(listas, config, ruta, solo_nuevo=True)
                except FileExistsError:
                    raise              # no es nuestro: no se toca
                except Exception:
                    nuevos.append(ruta)    # puede haber quedado a medias
                    raise
                nuevos.append(ruta)
                if ruta != propia:
                    numerados.append((propia, ruta))
                # DOBLE CONTRASTE: se vuelve a leer el archivo escrito y se
                # compara con lo que hay en pantalla. Es el ultimo paso antes
                # de que los apuntes entren en la contabilidad.
                fallos = verificar_excel(listas, config, ruta)
                problemas_export.extend(f"{nombre}: {p}" for p in fallos[:5])
                resumen_archivos.append(
                    (ruta, len(listas), totales_del_excel(config, ruta)))
                tipos_exportados.append(tipo)
                rutas_por_tipo[tipo] = ruta
        except Exception as error:
            # Antes un fallo aquí no avisaba de nada: «no genera el Excel».
            registro_errores.apuntar(traceback.format_exc())
            sobrantes = self._retirar_excel_fallidos(nuevos, borrar=True)
            if isinstance(error, OSError):
                causa = (f"No se pudo guardar «{nombre}» en el Escritorio:\n"
                         f"{error}\n\nCompruebe que el Escritorio existe y se "
                         "puede escribir en él, y vuelva a pulsar Exportar.")
            else:
                causa = (f"Falló al preparar «{nombre}»: {error}\n\nEl detalle "
                         f"queda apuntado en {registro_errores.FICHERO}, en la carpeta de "
                         "datos del programa.")
            QMessageBox.critical(
                self, "No se ha podido crear el Excel",
                "No se ha exportado nada.\n\n" + causa + sobrantes)
            return

        if problemas_export:
            # Que no parezca un Excel exportado: ni se importa por error, ni
            # el siguiente sale como «_2» dejando este con el nombre bueno,
            # ni «Recoger sueltos» lo archiva como si lo fuera.
            apartados = self._retirar_excel_fallidos(nuevos, borrar=False)
            QMessageBox.critical(
                self, "El archivo NO coincide con la pantalla",
                "Al volver a leer lo escrito, esto no cuadra:\n\n  · "
                + "\n  · ".join(problemas_export)
                + "\n\nNo se ha exportado nada." + apartados)
            return

        temporales_eliminados = sum(
            len(archivo.eliminar_excel_temporales(cliente_archivo, tipo))
            for tipo in tipos_exportados
        )
        # Solo con el Excel ya verificado: se recuerda lo exportado (para
        # avisar si vuelve a aparecer) y se aprenden sus NIF, ya revisados.
        exportadas = {t: por_tipo[t] for t in tipos_exportados}
        historial.registrar(getattr(self, "_cliente_nif", ""), exportadas,
                            rutas_por_tipo, getattr(self, "_cliente_nombre", ""),
                            leidas_en=self._momentos_de_lectura())
        # A partir de aquí el Excel ya es bueno y está apuntado: un fallo al
        # archivar no puede esconder el aviso final con su nombre (si no,
        # parece que no se exportó y se exporta otra vez).
        try:
            # Los duplicados no van al Excel ni tienen PDF propio: su original sí.
            texto_expediente = self._archivar_exportacion(
                exportadas, rutas_por_tipo)
            aprender_nifs_exportados(
                [f for t in tipos_exportados for f in por_tipo[t]])
        except Exception as error:
            registro_errores.apuntar(traceback.format_exc())
            texto_expediente = (
                f"\nOJO: el Excel está bien, pero no se pudo poner al día el "
                f"archivo del cliente ({error}). El detalle queda en "
                f"{registro_errores.FICHERO}.")
        self._perfil_columnas = (None,)      # el registro ha cambiado
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
            + "".join(
                f"Ya había un «{os.path.basename(propia)}» en el Escritorio y "
                f"no se ha tocado: el nuevo es «{os.path.basename(ruta)}».\n"
                for propia, ruta in numerados)
            + (f"Duplicadas, no exportadas: {len(excluidas)} línea(s).\n"
               if excluidas else "")
            + (f"Eliminados {temporales_eliminados} Excel temporales de partes.\n"
               if temporales_eliminados else "")
            + "Comprobado: lo escrito en los archivos coincide con lo que ve "
              "en pantalla, línea por línea. No se han creado Excel parciales."
            + texto_expediente,
            EXITO, segundos=0)

    @staticmethod
    def _retirar_excel_fallidos(rutas, borrar: bool) -> str:
        """Quita de en medio los Excel de una exportación fallida.

        Se borran, o se renombran a «NO IMPORTAR - …» si hay que poder
        mirarlos. Si no se puede ninguna de las dos cosas, se dice cuáles
        quedan para que no se importen. Devuelve el texto para el aviso.
        """
        avisos = []
        for ruta in rutas:
            if not os.path.exists(ruta):
                continue
            nombre = os.path.basename(ruta)
            if borrar:
                try:
                    os.remove(ruta)
                    continue
                except OSError:
                    pass
            destino = archivo.excel_sin_pisar(os.path.join(
                os.path.dirname(ruta), f"NO IMPORTAR - {nombre}"))
            try:
                os.replace(ruta, destino)
                if not borrar:
                    avisos.append(f"Se ha guardado como «{os.path.basename(destino)}» "
                                  "para que lo pueda mirar: no lo importe.")
                    continue
            except OSError:
                pass
            if os.path.exists(ruta):
                avisos.append(f"No se ha podido quitar «{nombre}» del "
                              "Escritorio: bórrelo a mano y NO lo importe.")
        return "".join(f"\n\n{a}" for a in avisos)
