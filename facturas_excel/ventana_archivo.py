"""El archivo documental: escanear, recoger sueltos, expedientes y un PDF por factura.

Parte de la ventana principal (app.py), separada para que cada tarea
viva en su sitio. Los métodos usan el estado de la ventana (self).
"""

from __future__ import annotations

import os

from collections import Counter

from PySide6.QtWidgets import QDialog, QMessageBox

from facturas_excel import archivo, escaner, registro_facturas
from facturas_excel.banda_avisos import AVISO, EXITO, INFO
from facturas_excel.claves import leer_api_key
from facturas_excel.dialogo_escaneo import DialogoEscaneo
from facturas_excel.dialogo_escaneos import DialogoEscaneos
from facturas_excel.clientes import nombres_conocidos
from facturas_excel.validacion import fecha_de

from facturas_excel.hilos import HiloEscaneo


class ArchivoMixin:
    def _escanear(self):
        if getattr(self, "_hilo_escaneo", None) and self._hilo_escaneo.isRunning():
            self._avisar("Espere a que termine el escaneo en curso.", AVISO)
            return
        disponibles = escaner.escaneres()
        if not disponibles:
            QMessageBox.warning(
                self, "Sin escáner",
                "Windows no ve ningún escáner.\n\nCompruebe que la impresora "
                "está encendida y conectada, y vuelva a intentarlo.\n\n"
                "Mientras tanto puede usar «Abrir PDF o imágenes».")
            return
        dialogo = DialogoEscaneo(disponibles, nombres_conocidos(), self)
        if dialogo.exec() != QDialog.Accepted:
            return
        dialogo.recordar()
        opciones = dialogo.valores()
        opciones["nombre_dispositivo"] = dialogo.combo_escaner.currentText()
        # Sin cliente no se para: el PDF nace en "Sin identificar" y se muda
        # solo a su carpeta cuando el programa averigua de quién es por el NIF.
        destino = archivo.ruta_provisional(opciones["carpeta"], opciones["tipo"])
        self._tipo_escaneo = opciones["tipo"]
        self._escaneo_reciente = True
        self._hojas_puestas = opciones.get("hojas", 0)
        self._escaneo_sin_identificar = not opciones["cliente"]
        self.btn_escanear.setEnabled(False)
        self.btn_cargar.setEnabled(False)
        self.progreso.setVisible(True)
        self.progreso.setRange(0, 0)          # no se sabe cuántas hojas hay
        self.lbl_estado.setText("Escaneando… no retire las hojas del alimentador.")
        self._hilo_escaneo = HiloEscaneo(destino, opciones)
        self._hilo_escaneo.progreso.connect(
            lambda n: self.lbl_estado.setText(f"Escaneando… {n} hoja(s)."))
        self._hilo_escaneo.terminado.connect(self._on_escaneo_hecho)
        self._hilo_escaneo.fallo.connect(self._on_escaneo_fallo)
        self._hilo_escaneo.start()

    # ---------- archivo: recoger sueltos y expedientes ----------

    def _rutas_del_lote(self) -> list:
        """Archivos que usa el lote abierto: no se mueven al recoger."""
        rutas = []
        for bloque in self._bloques:
            if bloque.get("original"):
                rutas.append(bloque["original"])
            rutas.extend(origen for _img, origen, _p, _d in bloque.get("crudos", []))
        return [r for r in rutas if r]

    def _recoger_sueltos(self) -> None:
        from facturas_excel import recoger
        from facturas_excel.dialogo_recogida import (
            DialogoRecogida, ejecutar_con_progreso)
        base = archivo.carpeta_escaneos()
        origenes = recoger.carpetas_origen()
        if not origenes:
            self._avisar("No se encuentran las carpetas Escritorio ni Descargas.", AVISO)
            return
        try:
            candidatos = ejecutar_con_progreso(
                self, "Buscando facturas en el Escritorio y Descargas…",
                lambda progreso: recoger.buscar(
                    origenes, base, self._rutas_del_lote(), progreso))
        except RuntimeError as error:
            QMessageBox.warning(self, "Recoger facturas", str(error))
            return
        if not candidatos:
            self._avisar("No hay facturas sueltas en el Escritorio ni en "
                         "Descargas: todo está en su sitio.", EXITO)
            return
        dialogo = DialogoRecogida(candidatos, base, leer_api_key() or "", self)
        if dialogo.exec() != QDialog.Accepted or not dialogo.resultado:
            return
        r = dialogo.resultado
        actualizados = self._actualizar_expedientes(r.get("afectados", []))
        texto = (f"Recogidos {r['movidos']} archivo(s)"
                 + (f" y {r['duplicados']} copia(s) repetidas apartadas en "
                    "_Duplicados" if r["duplicados"] else "")
                 + (f". Expedientes actualizados: {actualizados}" if actualizados else "")
                 + ".")
        if r["errores"]:
            texto += f" No se pudieron mover {len(r['errores'])}: " + "; ".join(r["errores"][:3])
        sin_expediente = self._texto_expedientes_sin_actualizar()
        texto += sin_expediente
        self._avisar(texto, AVISO if r["errores"] or sin_expediente else EXITO,
                     deshacer=self._deshacer_recogida, segundos=0)

    def _deshacer_recogida(self) -> None:
        from facturas_excel import recoger
        try:
            vueltos = recoger.deshacer_ultima(archivo.carpeta_escaneos())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Deshacer recogida", str(error))
            return
        self._avisar(f"{vueltos} archivo(s) devueltos a su sitio." if vueltos
                     else "No hay ninguna recogida que deshacer.", INFO)

    def _actualizar_expedientes(self, afectados) -> int:
        """Rehace los expedientes de esos (nombre, nif, ejercicio).

        Los que no se pueden (un PDF abierto en otro programa…) quedan en
        `_expedientes_sin_actualizar`, para decirlo: ver
        `_texto_expedientes_sin_actualizar`."""
        from facturas_excel import errores, expediente
        base = archivo.carpeta_escaneos()
        hechos = 0
        self._expedientes_sin_actualizar = []
        for nombre, nif, ejercicio in afectados:
            e = expediente.buscar(base, nif, nombre, ejercicio)
            if not e:
                continue
            try:
                expediente.crear(base, e)
                hechos += 1
            except (OSError, ValueError, RuntimeError) as error:
                errores.apuntar(f"Expediente {nombre or nif} {ejercicio}: {error}")
                self._expedientes_sin_actualizar.append(
                    f"{nombre or nif} {ejercicio} ({error})")
        return hechos

    def _texto_expedientes_sin_actualizar(self) -> str:
        fallidos = getattr(self, "_expedientes_sin_actualizar", [])
        if not fallidos:
            return ""
        return (f" No se pudo poner al día el expediente de "
                f"{'; '.join(fallidos[:3])}: ¿tiene abierto su PDF? Ciérrelo y "
                "vuelva a abrir Expedientes.")

    def _ver_registro_facturas(self) -> None:
        from facturas_excel.dialogo_registro_facturas import DialogoRegistroFacturas
        DialogoRegistroFacturas(self).exec()

    def _ver_expedientes(self) -> None:
        from facturas_excel.dialogo_expedientes import DialogoExpedientes
        DialogoExpedientes(archivo.carpeta_escaneos(), self).exec()

    def _ver_escaneos(self):
        """Los PDF que va generando el escaneo: abrirlos, recolocarlos o
        volver a pasarlos por el programa."""
        dialogo = DialogoEscaneos(self)
        if dialogo.exec() == QDialog.Accepted and dialogo.rutas_elegidas:
            self.procesar_rutas(dialogo.rutas_elegidas)

    def _on_escaneo_hecho(self, ruta):
        self.progreso.setRange(0, 100)
        self.btn_escanear.setEnabled(True)
        self.lbl_estado.setText(f"Escaneado y guardado en {ruta}")
        self._avisar_hojas_perdidas(ruta)
        # Directo al lote: es el flujo que se pidio, sin pasar por abrir archivo.
        self.procesar_rutas([ruta], desde_escaner=True)

    def _avisar_hojas_perdidas(self, ruta):
        """El alimentador arrastra a veces dos hojas pegadas: salen menos
        páginas de las que se pusieron y esa factura no se registra."""
        puestas = getattr(self, "_hojas_puestas", 0)
        if not puestas:
            return
        try:
            import fitz
            with fitz.open(ruta) as doc:
                leidas = doc.page_count
        except Exception:
            return
        if leidas >= puestas:
            return
        QMessageBox.warning(
            self, "Faltan hojas",
            f"Puso {puestas} hojas y solo se han escaneado {leidas}.\n\n"
            f"El alimentador suele arrastrar dos hojas pegadas. Compruebe qué "
            f"factura falta (el programa avisa también si ve un salto en la "
            f"numeración) y escanee esas hojas aparte: se añadirán al lote.")

    def _on_escaneo_fallo(self, mensaje):
        self.progreso.setRange(0, 100)
        self.progreso.setVisible(False)
        self.btn_escanear.setEnabled(True)
        self.btn_cargar.setEnabled(True)
        self._escaneo_reciente = False
        self._escaneo_sin_identificar = False
        self.lbl_estado.setText("No se pudo escanear.")
        QMessageBox.critical(self, "Error al escanear", mensaje)

    # ---------- carga ----------

    def _recolocar_escaneo(self, cliente, procesadas, copiar: bool = False, nif=""):
        """Archiva el PDF original por cliente, ejercicio y tipo.

        Al escanear no hace falta decir de quién son las facturas: el programa
        lo averigua por el NIF que se repite y coloca el archivo despues. Si no
        lo averigua, el PDF se queda en «Sin identificar» y se puede colocar a
        mano desde «Escaneos guardados».
        """
        if (not copiar and not self._escaneo_reciente
                and not self._escaneo_sin_identificar) \
                or len(self._rutas_actuales) != 1:
            return
        ruta = self._rutas_actuales[0]
        if not cliente:
            return
        ventas = sum(1 for _, pr in procesadas if pr.tipo == "venta")
        tipo = "ingresos" if ventas > len(procesadas) / 2 else "gastos"
        ejercicios = []
        for _, pr in procesadas:
            if not pr.facturas:
                continue
            fecha = fecha_de(pr.facturas[0].fecha)
            if fecha:
                ejercicios.append(fecha.year)
        ejercicio = Counter(ejercicios).most_common(1)[0][0] if ejercicios else None
        try:
            if copiar:
                nueva = archivo.copiar_a_cliente(
                    ruta, cliente, tipo, ejercicio=ejercicio, nif=nif)
            else:
                nueva = archivo.mover_a_cliente(
                    ruta, cliente, tipo, ejercicio=ejercicio, nif=nif)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Archivo documental",
                f"No se pudo archivar el PDF: {e}\nEl original sigue en {ruta}.")
            return
        if nueva == ruta:
            return
        self._escaneo_sin_identificar = False
        self._rutas_actuales = [nueva]
        for _, pr in procesadas:     # que la miniatura siga apuntando al PDF
            pr.origen = nueva
            for f in pr.facturas:
                f.origen_imagen = nueva
        self.lbl_estado.setText(
            f"Documento archivado en {cliente} / {ejercicio or 'ejercicio actual'} / "
            f"{'Ingresos' if tipo == 'ingresos' else 'Gastos'}")

    def _archivar_exportacion(self, exportadas, rutas_por_tipo,
                              apartadas=None) -> str:
        """Copia el Excel al archivo del cliente y pone al día su expediente.

        Así el expediente de cada cliente y ejercicio se mantiene solo, sin
        tener que acordarse. Si algo falla, la exportación sigue siendo buena:
        solo se avisa.
        """
        from facturas_excel import expediente
        nif = getattr(self, "_cliente_nif", "")
        nombre = getattr(self, "_cliente_nombre", "")
        if not nombre:
            return ""
        from facturas_excel import separar
        base = archivo.carpeta_escaneos()
        afectados = set()
        avisos = []
        # Una factura, un PDF: el taco escaneado se parte ahora que cada
        # factura está revisada, y el original se aparta intacto.
        try:
            documentos = {t: list(exportadas.get(t, [])) + list((apartadas or {}).get(t, []))
                          for t in set(exportadas) | set(apartadas or {})}
            partido = separar.separar(
                documentos, base, nombre, nif,
                pdf_previo=lambda tipo, f: registro_facturas.pdf_de(
                    nif, f, tipo, nombre))
        except Exception as error:  # nunca debe estropear la exportación
            partido = None
            avisos.append(f"No se pudieron separar las facturas en PDF: {error}")
        if partido:
            for viejo, nuevo in partido["tacos"].items():
                self._cambiar_origen(viejo, nuevo)
            afectados.update((nombre, nif, e) for e in partido["afectados"])
            # Cada factura queda en el registro con su PDF.
            registro_facturas.archivar(nif, nombre, partido["pdfs"])
            if partido["creados"]:
                avisos.append(f"{len(partido['creados'])} factura(s) guardadas "
                              "en su propio PDF en el archivo del cliente.")
            if partido["sin_paginas"]:
                avisos.append(
                    f"{len(partido['sin_paginas'])} factura(s) sin PDF propio "
                    "(no se encontró su documento original): siguen dentro "
                    "del taco.")
        try:
            for tipo, facturas in exportadas.items():
                ejercicio = self._ejercicio_exportacion(facturas)
                expediente.guardar_excel_exportado(
                    base, rutas_por_tipo[tipo], nombre, nif, ejercicio, tipo)
                afectados.add((nombre, nif, ejercicio))
        except (OSError, ValueError) as error:
            avisos.append(f"No se pudo guardar la copia del Excel en el archivo: {error}")
        hechos = self._actualizar_expedientes(sorted(afectados))
        if hechos:
            avisos.append(f"Expediente del cliente actualizado ({hechos}).")
        if self._texto_expedientes_sin_actualizar():
            avisos.append(self._texto_expedientes_sin_actualizar().strip())
        return "".join(f"\n{a}" for a in avisos)

    def _cambiar_origen(self, viejo: str, nuevo: str) -> None:
        """El taco se ha apartado en «Tacos escaneados»: que todo lo sepa."""
        def mismo(ruta):
            return ruta and os.path.normcase(os.path.abspath(ruta)) == \
                os.path.normcase(os.path.abspath(viejo))

        def cambiar(f):
            if mismo(f.origen_imagen):
                f.origen_imagen = nuevo
            if getattr(f, "paginas_documento", ()):
                f.paginas_documento = tuple(
                    (nuevo if mismo(o) else o, p) for o, p in f.paginas_documento)

        for bloque in self._bloques:
            if mismo(bloque.get("original")):
                bloque["original"] = nuevo
            bloque["crudos"] = [(img, nuevo if mismo(o) else o, p, d)
                                for img, o, p, d in bloque.get("crudos", [])]
            for _img, pr in bloque.get("procesadas", []):
                if mismo(pr.origen):
                    pr.origen = nuevo
                for f in pr.facturas:
                    cambiar(f)
        for registro in self.filas:
            cambiar(registro["factura"])
            for f in registro.get("fuentes", []):
                cambiar(f)
        registro_facturas.cambiar_ruta(viejo, nuevo)
