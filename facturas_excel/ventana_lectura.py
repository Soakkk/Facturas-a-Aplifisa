"""Leer facturas: la cola de PDF, Gemini, el cliente del lote y unir hojas.

Parte de la ventana principal (app.py), separada para que cada tarea
viva en su sitio. Los métodos usan el estado de la ventana (self).
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from facturas_excel import almacen, archivo, costes, muestras_revision
from facturas_excel.banda_avisos import AVISO, INFO
from facturas_excel.claves import leer_api_key
from facturas_excel.dialogo_cliente import DialogoCliente
from facturas_excel.clientes import marcar_cliente, mismo_nombre, recordar_nombre
from facturas_excel.control_facturas import clave_documento
from facturas_excel.pdf import PAGINAS_POR_BLOQUE, dividir_pdf
from facturas_excel.procesar import (
    analizar_cliente, clave_proveedor, fusionar_paginas_manual, preparar_lote,
    recordar_nif,
)
from facturas_excel.registro import parece_listado
from facturas_excel.rutas import dir_datos
from facturas_excel.union_bloques import unir_ultimo_bloque

from facturas_excel.rutas import escritorio
from facturas_excel.ventana_comun import EXT_FACTURA
from facturas_excel.hilos import Worker


class LecturaMixin:
    def _cargar(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Elige facturas (PDF o imágenes)", escritorio(),
            "Facturas (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if rutas:
            self.procesar_rutas(rutas)

    def procesar_rutas(self, rutas, desde_escaner: bool = False):
        """Añade documentos a la cola, dividiendo los PDF largos en bloques."""
        self._esperar_archivo()      # antes, lo que se esté archivando
        rutas = [os.path.abspath(r) for r in rutas
                 if os.path.isfile(r) and os.path.splitext(r)[1].lower() in EXT_FACTURA]
        if not rutas:
            QMessageBox.warning(self, "Archivos no compatibles",
                                "No se encontraron PDFs o imágenes válidas.")
            return
        sin_identificar = (len(rutas) == 1 and archivo.sin_identificar(rutas[0]))
        # Si lo que se ha soltado es el listado de Aplifisa, NO se manda a
        # Gemini: aqui se lee gratis y lo que se quiere es contrastarlo.
        listados = [r for r in rutas if r.lower().endswith(".pdf")
                    and parece_listado(r)]
        if listados:
            self._ofrecer_contraste(listados[0])
            rutas = [r for r in rutas if r not in listados]
            if not rutas:
                return
        muestras = {ruta: self._capturar_original(ruta) for ruta in rutas}
        api_key = leer_api_key()
        if not api_key:
            QMessageBox.warning(self, "Falta la API key",
                                "Configura primero tu API key de Gemini.")
            return
        elementos = []
        try:
            for ruta in rutas:
                if ruta.lower().endswith(".pdf"):
                    partes = dividir_pdf(ruta, PAGINAS_POR_BLOQUE)
                    for numero, parte in enumerate(partes, 1):
                        mover_original = bool(desde_escaner or sin_identificar)
                        elementos.append({
                            "rutas": [parte],
                            "original": ruta, "muestra_id": muestras.get(ruta),
                            "etiqueta": os.path.splitext(os.path.basename(parte))[0],
                            "parte": numero,
                            "partes": len(partes),
                            # Todo PDF termina en el archivo documental. Los
                            # externos se COPIAN; solo se mueve el provisional
                            # creado por el escáner de la propia aplicación.
                            "archivar": True,
                            "mover_original": mover_original,
                            "desde_escaner": bool(desde_escaner),
                            "sin_identificar": bool(sin_identificar),
                            "tipo_escaneo": self._tipo_escaneo,
                        })
                else:
                    elementos.append({
                        "rutas": [ruta], "original": ruta, "muestra_id": muestras.get(ruta),
                        "etiqueta": os.path.splitext(os.path.basename(ruta))[0],
                        "parte": 1, "partes": 1,
                        "archivar": False,
                        "mover_original": False,
                        "desde_escaner": bool(desde_escaner),
                        "sin_identificar": bool(sin_identificar),
                        "tipo_escaneo": self._tipo_escaneo,
                    })
        except Exception as e:
            QMessageBox.critical(
                self, "No se pudo preparar el PDF",
                f"No se ha añadido a la cola:\n\n{e}")
            return

        en_curso = bool(getattr(self, "worker", None) and self.worker.isRunning())
        if not en_curso and not self._cola:
            self._cola_total = 0
            self._cola_completados = 0
        self._cola.extend(elementos)
        self._cola_total += len(elementos)
        self.btn_gastos.setEnabled(False)
        self.btn_ventas.setEnabled(False)
        self.progreso.setVisible(True)
        self.progreso.setValue(0)
        if en_curso:
            self.lbl_estado.setText(
                f"Añadidos {len(elementos)} bloque(s). Cola total: "
                f"{self._cola_completados + 1}/{self._cola_total} en curso.")
            return
        self._iniciar_siguiente_cola(api_key)

    def _iniciar_siguiente_cola(self, api_key=None):
        if not self._cola:
            self._elemento_cola_actual = None
            self.progreso.setVisible(False)
            self.btn_cargar.setEnabled(True)
            hay_datos = self.tabla.rowCount() > 0
            self.btn_gastos.setEnabled(hay_datos)
            self.btn_registro.setEnabled(hay_datos)
            self.lbl_estado.setText(
                f"Cola terminada: {self._cola_completados} bloque(s) procesado(s).")
            # Lo dudoso se señala en el documento mientras se revisa lo demás.
            self._localizar_dudosas()
            return
        api_key = api_key or leer_api_key()
        if not api_key:
            self.lbl_estado.setText("Cola pendiente: falta la API key de Gemini.")
            return
        elemento = self._cola.pop(0)
        self._elemento_cola_actual = elemento
        self._rutas_actuales = list(elemento["rutas"])
        self._tipo_escaneo = elemento["tipo_escaneo"]
        self._escaneo_reciente = elemento["desde_escaner"]
        self._escaneo_sin_identificar = elemento["sin_identificar"]
        self.lbl_origen.setText(elemento["etiqueta"])
        actual = self._cola_completados + 1
        self.lbl_estado.setText(
            f"Cola {actual}/{self._cola_total}: leyendo {elemento['etiqueta']}…")
        self.worker = Worker(self._rutas_actuales, api_key)
        self.worker.progreso.connect(self._on_progreso)
        self.worker.gasto.connect(self._on_gasto)
        self.worker.terminado.connect(self._on_terminado)
        self.worker.fallo.connect(self._on_fallo)
        self.worker.start()

    def _on_progreso(self, actual, total):
        self.progreso.setMaximum(total)
        self.progreso.setValue(actual)
        bloque = self._cola_completados + 1
        self.lbl_estado.setText(
            f"Cola {bloque}/{self._cola_total} · páginas {actual}/{total}")

    def _on_fallo(self, msg):
        self._limpiar_parte_interna(self._elemento_cola_actual or {})
        self._cola_completados += 1
        self._escaneo_reciente = False
        QMessageBox.critical(
            self, "Error en un bloque",
            f"Este bloque no se pudo procesar, pero la cola continuará:\n\n{msg}")
        self._iniciar_siguiente_cola()

    def _on_terminado(self, procesadas, nombre, nif, crudos=None):
        elemento = self._elemento_cola_actual or {}
        rutas_parte = list(self._rutas_actuales)
        if (elemento.get("parte", 1) > 1 and self._bloques
                and self._bloques[-1].get("original") == elemento.get("original")
                and self._bloques[-1].get("nif")):
            # La segunda parte puede empezar solo con importes y no aportar
            # candidato a cliente. Mantener el cliente del mismo PDF completo.
            anterior = self._bloques[-1]
            nombre, nif = anterior["cliente"], anterior["nif"]
            procesadas = preparar_lote(crudos or [], nombre, nif)
        # Si el escaneo salió sin saber de quién era, ahora ya se sabe: el PDF
        # se muda solo a la carpeta del cliente antes de nombrar el bloque.
        if elemento.get("archivar"):
            original_anterior = elemento.get("original", "")
            self._rutas_actuales = [original_anterior]
            self._recolocar_escaneo(
                nombre, procesadas,
                copiar=not elemento.get("mover_original", False), nif=nif)
            original_nuevo = self._rutas_actuales[0]
            elemento["original"] = original_nuevo
            for pendiente in self._cola:
                if pendiente.get("original") == original_anterior:
                    pendiente["original"] = original_nuevo
                    pendiente["archivar"] = False
                    pendiente["mover_original"] = False
                    pendiente["desde_escaner"] = False
                    pendiente["sin_identificar"] = False
        elif not elemento:
            # También conserva el contrato de llamadas directas (pruebas y
            # pequeñas integraciones que entregan un bloque ya procesado).
            self._recolocar_escaneo(nombre, procesadas, nif=nif)
        if elemento:
            self._rutas_actuales = rutas_parte
            # Una parte interna no es documentación. Las filas y los datos
            # crudos deben apuntar siempre al PDF completo archivado y conservar
            # el número de página global para poder borrar la parte temporal.
            origen_documento = elemento.get("original", "")
            desplazamiento = ((elemento.get("parte", 1) - 1)
                              * PAGINAS_POR_BLOQUE)
            if origen_documento:
                for _, pr in procesadas:
                    pr.origen = origen_documento
                    pr.pagina += desplazamiento
                    for factura in pr.facturas:
                        factura.origen_imagen = origen_documento
                        factura.pagina_origen += desplazamiento
                        factura.ultima_pagina_origen += desplazamiento
                crudos = [
                    (imagen, origen_documento, pagina + desplazamiento, datos)
                    for imagen, _origen, pagina, datos in (crudos or [])
                ]
        referencias = {}
        for _, origen, _, _ in (crudos or []):
            if origen not in referencias:
                identificador = elemento.get("muestra_id")
                if not identificador and os.path.isfile(origen):
                    identificador = self._capturar_original(origen)
                if identificador:
                    referencias[origen] = identificador
        for _, pr in procesadas:
            for f in pr.facturas:
                f.original_id = referencias.get(f.origen_imagen, "")
        try:
            muestras_revision.guardar_lecturas(crudos or [], referencias)
        except (OSError, ValueError) as error:
            self._avisar_error_muestras(error)
        # Cada carga entra como un BLOQUE mas: asi se pueden juntar varios PDF
        # de escaner (25-30 hojas cada uno) en un unico Excel para Aplifisa.
        self._bloques.append({
            "nombre": self._nombre_bloque(elemento.get("etiqueta")),
            # Cuándo se leyó: pasa al registro de facturas al exportar.
            "leido_en": almacen.ahora(),
            "original": elemento.get("original", ""),
            "procesadas": procesadas,
            # Lo leido por Gemini, tal cual: permite rehacer el lote con otro
            # cliente sin gastar otra lectura.
            "crudos": list(crudos or []),
            "cliente": nombre,
            "nif": nif,
            # Lo que dijo el usuario al escanear ("gastos" o "ingresos"): sirve
            # para cazar una factura que sale del reves.
            "tipo_declarado": (self._tipo_escaneo
                               if self._escaneo_reciente else ""),
        })
        unir_ultimo_bloque(self._bloques)
        self._escaneo_reciente = False
        self._avisar_si_otro_cliente(nombre, nif)
        analisis = self._analisis_del_lote()
        # El nombre del cliente se guarda para proponerlo al escanear el
        # proximo taco suyo, sin tener que escribirlo otra vez (no si le falta
        # una letra: se quedaría así).
        if not any(c.nif == nif and c.nombre_roto for c in analisis.candidatos):
            recordar_nombre(nif, nombre)
        self._cliente_nif, self._cliente_nombre = nif, nombre
        self._pintar_cliente()
        # Primero se confirma quién es el cliente; solo después tiene sentido
        # decidir si la otra parte contradice un NIF guardado de proveedor.
        # Un homónimo del cliente se pregunta una vez por lote: si ya se eligió
        # este cliente, no se repregunta después de cada bloque de la cola.
        ya_elegido = getattr(self, "_cliente_elegido_lote", "") == nif
        if analisis.empate or (analisis.homonimo and not ya_elegido):
            self._cambiar_cliente(automatico=True)
        self._resolver_conflictos_nif()
        self._preparar_recargo()
        self._actualizar_combo_bloques()
        self._rellenar_tabla()
        self._revalidar_todo()
        hay_datos = self.tabla.rowCount() > 0
        self.btn_gastos.setEnabled(hay_datos)
        self.btn_ventas.setEnabled(hay_datos)
        self.btn_registro.setEnabled(hay_datos)
        self.btn_cliente.setEnabled(bool(self._bloques))
        if hay_datos and len(self._bloques) == 1:
            self.tabla.selectRow(0)
        self._guardar_muestra_revision()
        self._avisar_paginas_no_leidas()
        self._limpiar_parte_interna(elemento)
        self._cola_completados += 1
        self._iniciar_siguiente_cola()

    @staticmethod
    def _quitar_aviso_conflicto(pr, mensaje: str) -> None:
        """Retira únicamente el aviso que acaba de quedar resuelto."""
        if pr.aviso == mensaje:
            pr.aviso = ""
        else:
            pr.aviso = " ".join(pr.aviso.replace(mensaje, "").split())

    def _decidir_conflicto_nif(self, nombre: str, guardado: str,
                               leido: str, cantidad: int) -> str:
        """Pregunta una vez cuando varias facturas contradicen la memoria."""
        cuadro = QMessageBox(self)
        cuadro.setWindowTitle("Confirmar CIF/NIF del proveedor")
        cuadro.setIcon(QMessageBox.Warning)
        cuadro.setText(
            f"Para {nombre} está guardado <b>{guardado}</b>, pero "
            f"{cantidad} facturas de este lote muestran <b>{leido}</b>.")
        cuadro.setInformativeText(
            "El programa no cambiará lo aprendido sin que usted lo confirme.")
        mantener = cuadro.addButton("Mantener el guardado", QMessageBox.AcceptRole)
        sustituir = cuadro.addButton("Usar el nuevo y recordarlo", QMessageBox.ActionRole)
        revisar = cuadro.addButton("Dejar pendiente", QMessageBox.RejectRole)
        cuadro.setDefaultButton(revisar)
        cuadro.exec()
        pulsado = cuadro.clickedButton()
        if pulsado is mantener:
            return "guardado"
        if pulsado is sustituir:
            return "nuevo"
        return "revisar"

    def _resolver_conflictos_nif(self) -> None:
        """Contrasta la memoria con la evidencia acumulada de todo el lote."""
        grupos = {}
        for bloque in self._bloques:
            for _imagen, pr in bloque.get("procesadas", []):
                conflicto = getattr(pr, "conflicto_nif", None)
                if not conflicto:
                    continue
                clave = (clave_proveedor(conflicto["nombre"]),
                         conflicto["guardado"], conflicto["leido"])
                grupos.setdefault(clave, []).append(pr)

        for clave_grupo, procesadas in grupos.items():
            _clave, guardado, leido = clave_grupo
            decision = self._decisiones_conflicto_nif.get(clave_grupo)
            if decision:
                self._aplicar_decision_conflicto_nif(
                    procesadas, decision, guardado, leido)
                continue
            # Una discrepancia aislada se ve en amarillo. Con evidencia
            # repetida se pregunta una sola vez por todo el grupo.
            if len(procesadas) < 3:
                continue
            if any(pr.conflicto_nif.get("consultado") for pr in procesadas):
                for pr in procesadas:
                    pr.conflicto_nif["consultado"] = True
                continue
            nombre = procesadas[0].conflicto_nif["nombre"]
            decision = self._decidir_conflicto_nif(
                nombre, guardado, leido, len(procesadas))
            self._decisiones_conflicto_nif[clave_grupo] = decision
            self._aplicar_decision_conflicto_nif(
                procesadas, decision, guardado, leido)

    def _aplicar_decision_conflicto_nif(self, procesadas, decision: str,
                                        guardado: str, leido: str) -> None:
        """Aplica la decisión a este grupo y a sus partes posteriores."""
        nombre = procesadas[0].conflicto_nif["nombre"]
        if decision == "guardado":
            recordar_nif(nombre, guardado, manual=True)
            for pr in procesadas:
                for factura in pr.facturas:
                    factura.nif = guardado
        elif decision == "nuevo":
            recordar_nif(nombre, leido, manual=True)
        for pr in procesadas:
            conflicto = pr.conflicto_nif
            if decision != "revisar":
                self._quitar_aviso_conflicto(pr, conflicto["mensaje"])
                pr.conflicto_nif = None
            else:
                conflicto["consultado"] = True

    def _avisar_paginas_no_leidas(self):
        """Detalla las páginas agotadas o ilegibles sin detener la cola."""
        worker = getattr(self, "worker", None)
        fallos = getattr(worker, "fallos", None)
        if not fallos:
            return
        salto = chr(10)
        credito = getattr(worker, "sin_credito", "")
        cabecera = (
            f"Gemini se quedó sin crédito a mitad del bloque. Lo ya leído se ha "
            f"conservado; lo que falta está en rojo para leerlo cuando haya "
            f"saldo.{salto}{credito}{salto}{salto}" if credito else "")
        detalle = salto.join(
            f"· {os.path.basename(ruta) or 'documento'}, página {pagina}: {motivo}"
            for ruta, pagina, motivo in fallos[:10])
        if len(fallos) > 10:
            detalle += f"{salto}· … y {len(fallos) - 10} más"
        QMessageBox.warning(
            self, "Páginas sin leer",
            f"{cabecera}"
            f"{len(fallos)} página(s) no se han podido leer y están en rojo "
            f"en la tabla:{salto}{salto}{detalle}{salto}{salto}"
            "La cola continúa. Puede volver a cargar solo esas páginas.")

    def _limpiar_parte_interna(self, elemento: dict) -> None:
        """Borra una parte ya procesada, nunca el PDF original del usuario."""
        if int(elemento.get("partes", 1) or 1) <= 1:
            return
        raiz = os.path.abspath(os.path.join(dir_datos(), "cola_pdf"))
        for ruta in elemento.get("rutas", []):
            ruta_abs = os.path.abspath(ruta)
            if not os.path.normcase(ruta_abs).startswith(
                    os.path.normcase(raiz) + os.sep):
                continue
            try:
                os.remove(ruta_abs)
                carpeta = os.path.dirname(ruta_abs)
                if os.path.isdir(carpeta) and not os.listdir(carpeta):
                    os.rmdir(carpeta)
            except OSError:
                pass

    def _analisis_del_lote(self):
        """Las partes que salen en TODO el lote (todos los bloques)."""
        datos = [d for bloque in self._bloques for *_, d in bloque.get("crudos", [])]
        return analizar_cliente(datos)

    def _cambiar_cliente(self, automatico: bool = False):
        """Quien es el cliente de la asesoria en este lote.

        Al cambiarlo se rehace todo desde lo que ya leyo Gemini: no se vuelve a
        pagar ninguna lectura.
        """
        analisis = self._analisis_del_lote()
        if len(analisis.candidatos) < 2:
            if not automatico:
                self._avisar(
                    "En estas facturas solo se ha identificado una parte con "
                    "NIF, así que no hay entre quién elegir.", INFO)
            return
        dialogo = DialogoCliente(analisis.candidatos, self,
                                 elegido=getattr(self, "_cliente_nif", ""))
        if dialogo.exec() != QDialog.Accepted:
            return
        elegido = dialogo.elegido()
        if not elegido or not elegido.nif:
            return
        # Lo que dice una persona manda y se recuerda; y a los demas del lote
        # se les apunta como proveedores, que es lo que son.
        # Un nombre al que le falta una letra no se confirma ni se lleva a
        # la suite: se queda la confirmación del NIF.
        marcar_cliente(elegido.nif,
                       "" if elegido.nombre_roto else elegido.nombre)
        self._cliente_elegido_lote = elegido.nif
        for otro in analisis.candidatos:
            # Un homónimo del cliente (su nombre con otro NIF) no se apunta
            # como proveedor: estropearía la memoria de quien sí le compra.
            if (otro.nif != elegido.nif and otro.nombre and otro.nif
                    and not otro.nombre_roto
                    and not mismo_nombre(otro.nombre, elegido.nombre)
                    and clave_proveedor(otro.nombre)
                    != clave_proveedor(elegido.nombre)):
                recordar_nif(otro.nombre, otro.nif, manual=True)
        self._rehacer_con_cliente(elegido.nombre, elegido.nif)

    def _rehacer_con_cliente(self, nombre, nif):
        """Vuelve a montar todos los bloques con otro cliente, sin Gemini."""
        for bloque in self._bloques:
            if bloque.get("crudos"):
                bloque["procesadas"] = preparar_lote(bloque["crudos"], nombre, nif)
                bloque["cliente"], bloque["nif"] = nombre, nif
        self._cliente_nif, self._cliente_nombre = nif, nombre
        self._pintar_cliente()
        self._preparar_recargo()
        self._rellenar_tabla()
        self._revalidar_todo()
        self.lbl_estado.setText(f"Lote rehecho con {nombre or nif} como cliente.")
        self._avisar(f"Lote rehecho con {nombre or nif} como cliente, sin "
                     "volver a pagar la lectura.", INFO)

    def _nombre_bloque(self, base_preferido: str = "") -> str:
        """Nombre corto del bloque: el del PDF cargado, sin repetirse."""
        rutas = self._rutas_actuales
        if base_preferido:
            base = base_preferido
        elif not rutas:
            base = f"Bloque {len(self._bloques) + 1}"
        elif len(rutas) == 1:
            base = os.path.splitext(os.path.basename(rutas[0]))[0]
        else:
            base = f"{os.path.splitext(os.path.basename(rutas[0]))[0]} +{len(rutas) - 1}"
        usados = {b["nombre"] for b in self._bloques}   # aun no se ha añadido
        nombre, n = base, 2
        while nombre in usados:
            nombre, n = f"{base} ({n})", n + 1
        return nombre

    def _avisar_si_otro_cliente(self, nombre, nif):
        """Mezclar clientes en un mismo Excel es un lio gordo: hay que verlo."""
        anteriores = {b["nif"] for b in self._bloques[:-1] if b["nif"]}
        if not anteriores or not nif or nif in anteriores:
            return
        previo = next(b for b in self._bloques[:-1] if b["nif"])
        QMessageBox.warning(
            self, "¿Facturas de otro cliente?",
            f"Este bloque parece de OTRO cliente:\n\n"
            f"  · Bloques anteriores: {previo['cliente'] or '?'} "
            f"({previo['nif']})\n"
            f"  · Bloque nuevo: {nombre or '?'} ({nif})\n\n"
            "Se ha añadido igualmente, pero el Excel saldría con facturas de "
            "los dos. Si es un error, use «Quitar este bloque».")

    def _on_gasto(self, modelo, coste_lote):
        self._pintar_gasto(modelo, coste_lote)
        aviso = costes.aviso_tope()
        if aviso and not getattr(self, "_aviso_tope_dado", False):
            # Una vez por sesion: recordarlo en cada lote seria un incordio.
            self._aviso_tope_dado = True
            QMessageBox.warning(self, "Gasto de Gemini", aviso)

    @staticmethod
    def _mismo_archivo(a: str, b: str) -> bool:
        return os.path.normcase(os.path.abspath(a or "")) == \
            os.path.normcase(os.path.abspath(b or ""))

    def _crudos_de_filas(self, filas: list[int]) -> list[tuple]:
        """Localiza las páginas originales de las filas, también en sesiones viejas."""
        encontrados = []
        usados = set()
        for fila in filas:
            registro_tabla = self.filas[fila]
            f = self._leer_fila(fila)
            pagina = int(getattr(f, "pagina_origen", 0) or 0)
            for ib, bloque in enumerate(self._bloques):
                for ir, crudo in enumerate(bloque.get("crudos", [])):
                    clave = (ib, ir)
                    if clave in usados:
                        continue
                    imagen, origen, pag, _datos = crudo
                    ultima = max(pagina, int(f.ultima_pagina_origen or pagina))
                    coincide_pagina = (pagina and pagina <= int(pag) <= ultima and
                                       self._mismo_archivo(origen, f.origen_imagen))
                    # Las sesiones creadas antes de guardar pagina_origen aún
                    # pueden localizarse por la miniatura y el archivo.
                    coincide_imagen = (not pagina and imagen == registro_tabla["png"] and
                                       self._mismo_archivo(origen, f.origen_imagen))
                    if coincide_pagina or coincide_imagen:
                        encontrados.append((ib, ir, crudo))
                        usados.add(clave)
        return sorted(encontrados, key=lambda r: (r[0], r[1]))

    def _unir_hojas_seleccionadas(self) -> None:
        filas = self._filas_seleccionadas()
        crudos = self._crudos_de_filas(filas)
        if len(crudos) < 2:
            self._avisar(
                "Para unir hojas, seleccione filas de al menos dos hojas "
                "distintas. Si una factura tiene varias líneas de IVA en la "
                "misma hoja, cuentan como una sola hoja.", AVISO)
            return
        referencias = []
        for _ib, _ir, (_img, _origen, pagina, datos) in crudos:
            referencias.append(
                f"página {pagina}: {datos.get('num_factura') or 'sin nº'}")
        pregunta = (
            "Se unirán estas hojas como UNA sola factura:\n\n· "
            + "\n· ".join(referencias)
            + "\n\nLa primera aporta número, fecha y cliente; el resumen fiscal "
              "completo de la última sustituye los subtotales intermedios."
        )
        if QMessageBox.question(
                self, "Confirmar unión de hojas", pregunta,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return

        self._guardar_muestra_revision()
        fuentes = [fuente for fila in filas
                   for fuente in self.filas[fila].get("fuentes", [self.filas[fila]["factura"]])]
        documentos = {clave_documento(f) for f in fuentes}
        primero_bloque, primero_indice, _ = crudos[0]
        destino = self._bloques[primero_bloque]
        seleccion = {(ib, ir) for ib, ir, _ in crudos}
        posicion = sum(1 for ir in range(primero_indice)
                       if (primero_bloque, ir) not in seleccion)
        fusionado = fusionar_paginas_manual([crudo for _, _, crudo in crudos])
        nueva = preparar_lote([fusionado], destino.get("cliente", ""), destino.get("nif", ""))[0]
        original_id = next((f.original_id for f in fuentes if f.original_id), "")
        for f in nueva[1].facturas:
            f.original_id = original_id
            f.edicion_manual = True
        insertada = False
        for ib, bloque in enumerate(self._bloques):
            restantes = []
            for imagen, pr in bloque["procesadas"]:
                if any(clave_documento(f) in documentos for f in pr.facturas):
                    if bloque is destino and not insertada:
                        restantes.append(nueva)
                        insertada = True
                else:
                    restantes.append((imagen, pr))
            bloque["procesadas"] = restantes
            bloque["crudos"] = [crudo for ir, crudo in enumerate(bloque.get("crudos", []))
                                if (ib, ir) not in seleccion]
        if not insertada:
            destino["procesadas"].append(nueva)
        destino["crudos"].insert(posicion, fusionado)
        self._bloques = [bloque for bloque in self._bloques
                         if bloque.get("procesadas") or bloque is destino]
        try:
            muestras_revision.guardar_lecturas(
                [fusionado], {fusionado[1]: original_id} if original_id else {})
        except (OSError, ValueError) as error:
            self._avisar_error_muestras(error)
        self._actualizar_combo_bloques()
        self._rellenar_tabla()
        self._revalidar_todo()
        self._guardar_sesion()
        numero = fusionado[3].get("num_factura") or "sin nº"
        self.lbl_estado.setText(
            f"{len(crudos)} hojas unidas como una sola factura ({numero}).")
