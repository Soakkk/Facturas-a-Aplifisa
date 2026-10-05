"""Las comprobaciones de cada línea, el semáforo, los avisos y los totales.

Parte de la ventana principal (app.py), separada para que cada tarea
viva en su sitio. Los métodos usan el estado de la ventana (self).
"""

from __future__ import annotations

import html
import os
import re

from collections import Counter
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPageLayout, QPageSize, QPdfWriter, QTextDocument,
)
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHeaderView, QMenu, QTableWidgetItem,
)

from facturas_excel import ajustes, fiscal, historial, registro_facturas
from facturas_excel.rutas import escritorio
from facturas_excel.banda_avisos import AVISO
from facturas_excel.clientes import DESGLOSE, TOTAL, regimen_recargo
from facturas_excel.conceptos import catalogo
from facturas_excel.control_facturas import controles_documentos, sin_cuadre_antiguo
from facturas_excel.consulta import PeriodoLote, clave_factura, facturas_unicas
from facturas_excel.estilo import ACCENT_FAINT, INK

# Totales: lo que vale cero, en gris claro.
COLOR_CERO = "#9AA9B8"
from facturas_excel.modelo import Factura
from facturas_excel.procesar import normaliza_nif
from facturas_excel.resumen import (
    eur, eur_con_signo, resumir, resumir_por_bloque,
)
from facturas_excel.su_suma import (
    ALTO_FILA_COLUMNA, PRIMERA_COLUMNA_IMPORTE, SOLO_TOTAL, columnas_totales,
)
from facturas_excel.lote import (
    CON_ERROR, ORDEN_PRESENTACION, POR_REVISAR, TEXTO_PRESENTACION, VERIFICADA,
    presentacion,
)

# Mensajes de la casilla de estado cuando una persona ya ha dado el visto
# bueno (la ficha no los enseña como avisos).
MENSAJE_REVISADA = "Revisada y confirmada manualmente"
MENSAJE_CORREGIDA = "Corregida a mano: cuenta como revisada"
MENSAJE_CORREGIDA_DESCUADRA = (
    "Corregida a mano, pero el total no cuadra: compruébelo y, si está bien "
    "así, pulse «Marcar revisada».")
MENSAJE_CORREGIDA_NUEVOS = (
    "Corregida a mano, pero la corrección ha traído un aviso nuevo: "
    "compruébelo y, si está bien así, pulse «Marcar revisada».")
# Los que añade el propio programa al dar o negar el visto bueno: no son
# avisos de la factura.
MENSAJES_DE_ESTADO = (MENSAJE_REVISADA, MENSAJE_CORREGIDA,
                      MENSAJE_CORREGIDA_DESCUADRA, MENSAJE_CORREGIDA_NUEVOS)
from facturas_excel.tabla_facturas import (
    C_BASE, C_BASE_IRPF, C_BASE_RE, C_CUENTA, C_CUOTA, C_CUOTA_IRPF, C_CUOTA_RE,
    C_BLOQUE, C_FECHA, C_GXX, C_NIF, C_NOMBRE, C_NUM, C_PCT, C_PCT_IRPF, C_PCT_RE,
    C_TIPO, C_TOTAL, COLUMNAS_COMPACTAS, columnas_visibles,
)
from facturas_excel.validacion import (
    ERROR, OK, REVISAR, Incidencia, huecos_de_numeracion, fecha_de, validar,
    validar_nif,
)

from facturas_excel.ventana_comun import (
    ESTILO_PRESENTACION, COLOR_CONTADOR, TODOS_LOS_BLOQUES,
    _sin_aviso_ejercicios_antiguo, _ayuda_estado, _cabeceras_resumen,
)


def _otro_nombre_del_mismo_nif(facturas) -> dict:
    """{fila: [otros nombres, en orden]} de las que comparten NIF con otra
    que se llama distinto (lo que se parece ya lo unifica la lectura). Sin
    números de línea: el aviso tiene que decir lo mismo aunque se ordene la
    tabla, o una factura ya revisada volvería a pendiente."""
    por_nif = {}
    for f in facturas:
        nif, nombre = normaliza_nif(f.nif), str(f.nombre or "").strip()
        if nombre and validar_nif(nif):
            por_nif.setdefault(nif, set()).add(nombre)
    otro = {}
    for r, f in enumerate(facturas):
        nombres = por_nif.get(normaliza_nif(f.nif)) or set()
        if len(nombres) > 1:
            otro[r] = sorted(nombres - {str(f.nombre or "").strip()})
    return otro


class ValidacionMixin:
    def _revalidar_fila(self, r):
        if r < 0 or r >= len(self.filas):
            return
        pasada = getattr(self, "_pasada", None) or self._preparar_pasada()
        f = pasada["facturas"][r]
        registro = self.filas[r]
        res = validar(f)
        estado = res.estado
        msgs = list(res.mensajes)

        def anadir(texto, *campos, gravedad=REVISAR):
            nonlocal estado
            msgs.append(Incidencia(texto, campos, gravedad))
            if gravedad == ERROR:
                estado = ERROR
            elif estado == OK:
                estado = REVISAR

        # Las sesiones de versiones anteriores guardaron un aviso de ejercicio
        # en TODAS las filas. Se limpia al abrirlas; ahora se señala únicamente
        # la factura cuya fecha no pertenece al ejercicio predominante.
        aviso_guardado = sin_cuadre_antiguo(_sin_aviso_ejercicios_antiguo(
            registro["aviso"]))
        registro["aviso"] = aviso_guardado
        if aviso_guardado:
            msgs.append(aviso_guardado)
            if estado == OK:
                estado = REVISAR
        aviso_tipo = self._aviso_tipo(r)
        if aviso_tipo:
            anadir(aviso_tipo)
        aviso_irpf = self._aviso_irpf_transportista(r, f)
        if aviso_irpf:
            anadir(aviso_irpf, "base_irpf", "pct_irpf", "cuota_irpf")
        # Lo que dice la ley según sea gasto o venta (fiscal.py).
        for texto, campos, gravedad in fiscal.avisos(f, pasada["tipos"][r]):
            anadir(texto, *campos, gravedad=gravedad)
        rectificada = self._rectificada_fuera_del_lote(f, pasada["tipos"][r],
                                                       pasada["facturas"])
        if rectificada:
            anadir(rectificada, "num_factura")
        for texto in pasada["errores_documento"].get(r, []):
            anadir(texto, gravedad=ERROR)
        otros = pasada.get("otro_nombre", {}).get(r)
        if otros:
            anadir("Este NIF también está a nombre de "
                   + ", ".join(f"«{n}»" for n in otros)
                   + ". En Aplifisa un NIF es un solo proveedor: escriba aquí "
                   "el nombre bueno (se pone en todas las de ese NIF) o "
                   "corrija el NIF si está mal leído.", "nombre", "nif")
        lado = "gasto" if pasada["tipos"][r] == "gasto" else "ingreso"
        if f.concepto and not any(
                c == str(f.concepto).strip() and (not f.subclave or g == f.subclave)
                for c, g in pasada["catalogo"][lado]):
            anadir(f"La cuenta {f.concepto} ({f.subclave or 'sin subclave'}) "
                   f"no corresponde a {lado}. Compruebe cuenta y contraparte.",
                   "concepto", "subclave", gravedad=ERROR)
        if r in self._duplicados:
            # Rojo, no ambar: importar dos veces la misma factura la paga dos
            # veces. Que obligue a decidir, no que se quede en "ya lo miraré".
            anadir(f"FACTURA DUPLICADA: es la misma que la línea "
                   f"{self._duplicados[r] + 1} del lote (mismo nº, NIF, "
                   f"base y tipo de IVA). Bórrala o quedará registrada dos veces.",
                   "num_factura", gravedad=ERROR)
        aviso_periodo = self._aviso_periodo(f)
        if aviso_periodo:
            anadir(aviso_periodo, "fecha")
        aviso_ejercicio = self._aviso_ejercicio(f)
        if aviso_ejercicio:
            # Igual que un duplicado: no se puede confirmar para ocultarlo,
            # porque exportarlo llevaría el apunte al ejercicio equivocado.
            anadir(aviso_ejercicio, "fecha", gravedad=ERROR)
        # Se guarda el estado SIN el aviso de «ya exportada»: la exportación
        # trata esas filas aparte y pregunta qué hacer con ellas.
        registro["estado_base"] = estado
        # Corregida a mano: vale como revisada para los avisos que ya tenía
        # cuando la corrigió. Un aviso nuevo (un NIF o una fecha mal
        # tecleados) o un total que no cuadra la dejan pendiente.
        vistos = set(getattr(f, "avisos_vistos", ()) or ())
        nuevos = [m for m in msgs if str(m) not in vistos]
        descuadra = any(str(m).startswith("El total no cuadra") for m in msgs)
        corregida = (getattr(f, "revision_corregida", False)
                     and estado in (OK, REVISAR) and not nuevos and not descuadra)
        registro.aceptada = estado == REVISAR and (
            f.revision_confirmada or corregida)
        ya = pasada["exportadas"].get(r)
        registro["ya_exportada"] = ya
        if ya:
            anadir(historial.texto_aviso(ya), "num_factura")
        confirmada = estado == REVISAR and f.revision_confirmada
        if confirmada:
            msgs.append(MENSAJE_REVISADA)
        elif corregida:
            msgs.append(MENSAJE_CORREGIDA)
        elif getattr(f, "revision_corregida", False) and estado == REVISAR:
            if descuadra:
                msgs.append(Incidencia(
                    MENSAJE_CORREGIDA_DESCUADRA, ("total_impreso",)))
            else:
                msgs.append(MENSAJE_CORREGIDA_NUEVOS)
        registro["estado"] = estado
        registro["mensajes"] = msgs
        registro.presentacion = presentacion(estado, f, confirmada, corregida)
        texto, color, fondo = self._presentacion_estado(
            estado, f, confirmada, corregida)
        self.tabla.pintar_estado(
            r, texto, color, fondo,
            _ayuda_estado(estado, msgs) if msgs else
            ("Verificada: las dos lecturas coinciden y todo cuadra"
             if registro.presentacion == VERIFICADA else
             "Todo cuadra, pero solo la ha leído un modelo"))
        self.tabla.resaltar(r, registro, estado, msgs)
        if not getattr(self, "_pasada", None):
            self._resumen()

    @staticmethod
    def _estilo_presentacion(codigo: str):
        """(texto, color, fondo) de un código de presentación."""
        color, fondo = ESTILO_PRESENTACION[codigo]
        return TEXTO_PRESENTACION[codigo], color, fondo

    @staticmethod
    def _presentacion_estado(estado, f: Factura, confirmada: bool,
                             corregida: bool = False):
        """(texto, color, fondo) de la casilla de estado."""
        codigo = presentacion(estado, f, confirmada, corregida)
        color, fondo = ESTILO_PRESENTACION[codigo]
        return TEXTO_PRESENTACION[codigo], color, fondo

    def _preparar_pasada(self) -> dict:
        """Lo que comparten todas las filas en una revalidación.

        Antes cada fila volvía a recorrer el lote entero (su bloque, los
        datos leídos, el catálogo) y rehacía el resumen: con 300 líneas cada
        corrección tardaba 6 segundos. Ahora se calcula una sola vez.
        """
        n = self.tabla.rowCount()
        facturas = [self._leer_fila(r) for r in range(n)]
        tipos = [self._tipo_fila(r) for r in range(n)]
        por_bloque = {}
        for r in range(n):
            bloque = self.filas[r]["bloque"]
            por_bloque.setdefault(bloque, Counter())[tipos[r]] += 1
        cliente_nif = getattr(self, "_cliente_nif", "")
        cliente_nombre = getattr(self, "_cliente_nombre", "")
        # Todo lo exportado del cliente en una sola consulta al registro.
        ya = historial.exportadas_de(cliente_nif, cliente_nombre) if n else {}
        # Para los huecos de numeración y las rectificativas: lo exportado
        # antes del cliente también cuenta.
        self._exportadas_cliente = ya
        exportadas = {}
        for r in range(n):
            k = historial.clave(facturas[r], tipos[r])
            if k and k in ya:
                exportadas[r] = ya[k]
        return {
            "facturas": facturas, "tipos": tipos, "por_bloque": por_bloque,
            "otro_nombre": _otro_nombre_del_mismo_nif(facturas),
            "transportista": self._cliente_es_transportista(),
            "catalogo": {lado: {(c, g) for c, g, _ in catalogo(lado)}
                         for lado in ("gasto", "ingreso")},
            "errores_documento": getattr(self, "_errores_documento", {}),
            "exportadas": exportadas,
        }

    @staticmethod
    def _clave_factura_para_ejercicio(f: Factura, fila: int) -> tuple:
        """Una factura con varias líneas de IVA cuenta una sola vez."""
        numero = re.sub(r"\s+", "", str(f.num_factura or "")).upper()
        nif = normaliza_nif(f.nif)
        fecha = fecha_de(f.fecha)
        if numero:
            return (str(f.origen_imagen or ""), numero, nif,
                    fecha.isoformat() if fecha else str(f.fecha or ""))
        # Sin número no es seguro unir dos documentos distintos.
        return ("fila", fila)

    def _calcular_ejercicio_lote(self):
        """Ejercicio de trabajo: el más frecuente, contando facturas únicas."""
        ejercicios = []
        vistas = set()
        for r in range(self.tabla.rowCount()):
            f = self._leer_fila(r)
            clave = self._clave_factura_para_ejercicio(f, r)
            if clave in vistas:
                continue
            vistas.add(clave)
            fecha = fecha_de(f.fecha)
            if fecha:
                ejercicios.append(fecha.year)
        return (Counter(ejercicios).most_common(1)[0][0]
                if ejercicios else None)

    def _rectificada_fuera_del_lote(self, f: Factura, tipo: str,
                                    facturas) -> str:
        """Una rectificativa cuya factura original no está en este lote: hay
        que comprobar que la original está registrada (se busca en el
        registro) y el signo (un abono en positivo suma en vez de restar)."""
        original = registro_facturas.numero_clave(getattr(f, "rectifica_a", ""))
        if not original:
            return ""
        nif = normaliza_nif(f.nif)
        if any(registro_facturas.numero_clave(otra.num_factura) == original
               and normaliza_nif(otra.nif) == nif for otra in facturas):
            return ""          # está en el lote: ya lo trata «SUSTITUIDA»
        lado = registro_facturas.lado(tipo)
        previa = next((ficha for ficha in getattr(
            self, "_exportadas_cliente", {}).values()
            if ficha.get("tipo") == lado
            and registro_facturas.numero_clave(ficha.get("num_factura")) == original
            and normaliza_nif(ficha.get("nif")) == nif), None)
        donde = (f"la original consta como exportada el {previa['exportada']}"
                 if previa and previa.get("exportada") else
                 "la original no consta en el registro: compruebe que está "
                 "registrada")
        signo = (" Si es un abono, los importes van en negativo."
                 if (f.base_iva or 0) > 0 else "")
        return (f"Rectifica a la factura {f.rectifica_a}, que no está en este "
                f"lote: {donde}.{signo}")

    def _aviso_ejercicio(self, f: Factura) -> str:
        fecha = fecha_de(f.fecha)
        ejercicio = getattr(self, "_ejercicio_lote", None)
        if not fecha or not ejercicio or fecha.year == ejercicio:
            return ""
        return (f"AÑO DISTINTO: la fecha leída es {f.fecha} (año {fecha.year}), "
                f"pero el ejercicio del lote es {ejercicio}. Corrija la fecha "
                "o compruebe si esta factura pertenece al lote.")

    def _aviso_periodo(self, f: Factura) -> str:
        periodo = getattr(self, "_periodo_lote", PeriodoLote())
        fecha = fecha_de(f.fecha)
        if not fecha or not periodo.es_trimestre \
                or fecha.year != periodo.ejercicio or periodo.contiene(f):
            return ""
        return (
            f"FUERA DEL TRIMESTRE: la fecha {f.fecha} no pertenece a "
            f"{periodo.etiqueta}. Se puede registrar después de comprobarla, "
            "pero queda fuera del total de ese periodo."
        )

    def _aviso_tipo(self, r) -> str:
        """Comprueba por dos vias que la fila esta bien clasificada.

        Gasto o ingreso se decide por el NIF del cliente, que es lo fiable,
        pero si el NIF viene mal leido la factura se va al lado contrario sin
        que nadie se entere. Se contrasta con lo que dijo el usuario al
        escanear el taco y con lo que hace el resto de su bloque.
        """
        if r >= len(self.filas):
            return ""
        tipo = self._tipo_fila(r)
        bloque = self.filas[r]["bloque"]
        declarado = next((b.get("tipo_declarado", "") for b in self._bloques
                          if b["nombre"] == bloque), "")
        esperado = {"gastos": "gasto", "ingresos": "venta"}.get(declarado)
        if esperado and tipo != esperado:
            return (f"Dijo que este taco era de "
                    f"{'GASTOS' if esperado == 'gasto' else 'INGRESOS'} y esta "
                    f"factura sale como {'gasto' if tipo == 'gasto' else 'ingreso'}: "
                    f"compruebe si está bien")
        # Sin taco declarado: la que se sale de lo que hace todo su bloque.
        pasada = getattr(self, "_pasada", None)
        if pasada:
            cuenta = pasada["por_bloque"].get(bloque, Counter())
        else:
            cuenta = Counter(self._tipo_fila(i) for i in range(len(self.filas))
                             if self.filas[i]["bloque"] == bloque)
        if sum(cuenta.values()) >= 5 and cuenta[tipo] == 1:
            return ("Es la única factura de su bloque que sale como "
                    f"{'gasto' if tipo == 'gasto' else 'ingreso'}: compruébela")
        return ""

    def _cliente_es_transportista(self) -> bool:
        """Detecta la actividad en el nombre fiscal o comercial del emisor."""
        nombres = [getattr(self, "_cliente_nombre", "")]
        cliente_nif = normaliza_nif(getattr(self, "_cliente_nif", ""))
        for bloque in self._bloques:
            for registro in bloque.get("crudos", []):
                if not registro or not isinstance(registro[-1], dict):
                    continue
                datos = registro[-1]
                if normaliza_nif(datos.get("emisor_nif")) == cliente_nif:
                    nombres.append(datos.get("emisor_nombre") or "")
        return any("TRANSPORT" in str(nombre).upper() for nombre in nombres)

    def _aviso_irpf_transportista(self, r: int, f: Factura) -> str:
        """Control visible del 1% en los ingresos de transportistas."""
        pasada = getattr(self, "_pasada", None)
        transportista = (pasada["transportista"] if pasada
                         else self._cliente_es_transportista())
        if self._tipo_fila(r) != "venta" or not transportista:
            return ""
        if f.base_irpf is None and f.pct_irpf is None and f.cuota_irpf is None:
            return ("INGRESO DE TRANSPORTISTA SIN IRPF: compruebe si esta "
                    "factura debe llevar la retención del 1%.")
        if f.pct_irpf is not None and abs(f.pct_irpf - 1.0) > 0.01:
            return (f"IRPF DE TRANSPORTISTA: figura un {f.pct_irpf:g}% en vez "
                    "del 1%; compruébelo.")
        return ""

    def _actualizar_columnas(self) -> None:
        """Recargo y retenciones, solo cuando tocan a este cliente o lote."""
        if not hasattr(self, "accion_todas_columnas"):
            return
        nif = getattr(self, "_cliente_nif", "")
        nombre = getattr(self, "_cliente_nombre", "")
        # Lo que se sabe del cliente: su régimen de recargo y si sus facturas
        # suelen llevar retención (transportista, o ya las tuvo antes).
        clave = (nif, nombre)
        if getattr(self, "_perfil_columnas", (None,))[0] != clave:
            self._perfil_columnas = (clave, bool(nif) and regimen_recargo(nif)
                                     in (TOTAL, DESGLOSE),
                                     registro_facturas.usa_retenciones(nif, nombre))
        _, recargo_cliente, retenciones_cliente = self._perfil_columnas
        visibles = columnas_visibles(
            self.filas,
            recargo_cliente=recargo_cliente,
            irpf_cliente=retenciones_cliente or (
                self._cliente_es_transportista() if self._bloques else False),
            ver_todas=self.accion_todas_columnas.isChecked())
        # La distribución «una a una» deja la tabla con lo justo.
        compacta = getattr(getattr(self, "_distribucion", None), "tabla_compacta", False)
        for columna in range(self.tabla.columnCount()):
            if columna == C_BLOQUE:
                oculta = True                    # ya está en el filtro
            elif compacta:
                oculta = columna not in COLUMNAS_COMPACTAS
            else:
                oculta = not visibles.get(columna, True)
            if self.tabla.isColumnHidden(columna) != oculta:
                self.tabla.setColumnHidden(columna, oculta)

    def _con_columnas_de_recargo(self) -> bool:
        """Si el lote lleva columnas de recargo (por el cliente o por sus
        facturas), lo vea o no la tabla («una a una» enseña lo justo)."""
        if not hasattr(self, "accion_todas_columnas"):
            return not self.tabla.isColumnHidden(C_BASE_RE)
        self._actualizar_columnas()
        _clave, recargo_cliente, retenciones_cliente = self._perfil_columnas
        visibles = columnas_visibles(
            self.filas, recargo_cliente=recargo_cliente,
            irpf_cliente=retenciones_cliente,
            ver_todas=self.accion_todas_columnas.isChecked())
        return bool(visibles.get(C_BASE_RE))

    def _ver_todas_columnas(self, todas: bool) -> None:
        ajustes.guardar("ver_todas_columnas", bool(todas))
        self._actualizar_columnas()

    def _menu_columnas(self, posicion) -> None:
        menu = QMenu(self)
        menu.addAction(self.accion_todas_columnas)
        menu.addAction(self.accion_ajustar_columnas)
        menu.exec(self.tabla.horizontalHeader().mapToGlobal(posicion))

    def _revalidar_todo(self):
        self._ejercicio_lote = self._calcular_ejercicio_lote()
        self._actualizar_selector_periodo()
        self._pasada = None
        pasada = self._preparar_pasada()
        self._errores_documento, self._duplicados = controles_documentos(
            pasada["facturas"], pasada["tipos"])
        pasada["errores_documento"] = self._errores_documento
        self._pasada = pasada
        try:
            for r in range(self.tabla.rowCount()):
                self._revalidar_fila(r)
        finally:
            self._pasada = None
        self._actualizar_columnas()
        # El resumen se rehace SIEMPRE, tambien con la tabla vacia: si no, al
        # vaciar el lote se quedaban abajo los totales del lote anterior y
        # parecia que no se habia borrado nada.
        self._resumen()
        self._pintar_alerta()
        if hasattr(self, "combo_filtro_estado"):
            self._aplicar_filtro()
        self._refrescar_ficha()
        self._timer_muestras.start()
        if hasattr(self, "_timer_sesion"):
            self._timer_sesion.start()

    def _pintar_alerta(self):
        """Banner rojo arriba con las duplicadas y las sustituidas: las dos
        acaban registrando dos veces el mismo gasto si se cuelan."""
        avisos = []
        for r, original in sorted(self._duplicados.items()):
            f = self.filas[r]["factura"]
            avisos.append(f"Línea {r + 1}: factura {f.num_factura or '?'} de "
                          f"{f.nombre or '?'} — repetida de la línea {original + 1}.")
        ejercicios_vistos = set()
        for r in range(len(self.filas)):
            f = self.filas[r]["factura"]
            aviso = self._aviso_ejercicio(f)
            if not aviso:
                continue
            clave = self._clave_factura_para_ejercicio(f, r)
            if clave in ejercicios_vistos:
                continue
            ejercicios_vistos.add(clave)
            fecha = fecha_de(f.fecha)
            avisos.append(
                f"Línea {r + 1}: factura {f.num_factura or '?'} de "
                f"{f.nombre or '?'} — fecha {f.fecha} (año {fecha.year}); "
                f"el lote es de {self._ejercicio_lote}.")
        periodos_vistos = set()
        for r in range(len(self.filas)):
            f = self.filas[r]["factura"]
            if not self._aviso_periodo(f):
                continue
            clave = self._clave_factura_para_ejercicio(f, r)
            if clave in periodos_vistos:
                continue
            periodos_vistos.add(clave)
            avisos.append(
                f"Línea {r + 1}: factura {f.num_factura or '?'} de "
                f"{f.nombre or '?'} — {f.fecha}, fuera de "
                f"{self._periodo_lote.etiqueta}.")
        # Una hoja que se quedo pegada en el alimentador no da ningun error:
        # simplemente esa factura no esta. El salto de numeracion la delata.
        ejercicio = getattr(self, "_ejercicio_lote", None)
        anteriores = [ficha.get("num_factura") for ficha in getattr(
            self, "_exportadas_cliente", {}).values()
            if ficha.get("tipo") == "venta"
            and (not ejercicio or ficha.get("ejercicio") == ejercicio)]
        avisos += huecos_de_numeracion(
            [d["factura"] for d in self.filas],
            [self._tipo_fila(r) for r in range(len(self.filas))],
            getattr(self, "_cliente_nombre", ""), anteriores)
        sustituidas = [r for r in range(len(self.filas))
                       if "SUSTITUIDA" in (self.filas[r]["aviso"] or "")]
        for r in sustituidas:
            f = self.filas[r]["factura"]
            avisos.append(f"Línea {r + 1}: factura {f.num_factura or '?'} de "
                          f"{f.nombre or '?'} — sustituida por otra del lote.")
        if not avisos:
            self.alerta.setVisible(False)
            return
        n = len(avisos)
        self.lbl_alerta_titulo.setText(
            f"Atención: {n} aviso{'s' if n > 1 else ''} que revisar "
            f"antes de exportar")
        self.lbl_alerta_texto.setText(
            "\n".join(avisos[:2])
            + (f"\n… y {n - 2} avisos más. Use «Ver incidencias»." if n > 2 else ""))
        self.lbl_alerta_texto.setToolTip("\n".join(avisos))
        self.alerta.setVisible(True)

    def _resumen(self):
        facturas = [fila["factura"] for fila in self.filas]
        self.lbl_lote.setText(
            f"Lote completo · {facturas_unicas(facturas)} facturas · "
            f"{len(facturas)} líneas fiscales")
        # Por cómo se ve cada línea: una revisada o corregida ya no cuenta
        # como «por revisar».
        vistas = [self.filas[r].presentacion
                  for r in range(self.tabla.rowCount())]
        n_g = sum(1 for r in range(self.tabla.rowCount()) if self._tipo_fila(r) == "gasto")
        self._pintar_contadores()
        revisar, errores = vistas.count(POR_REVISAR), vistas.count(CON_ERROR)
        self.lbl_estado.setText(
            "Lote vacío. Cargue o escanee facturas para empezar." if not vistas else
            f"{len(vistas)} líneas  ·  Gastos: {n_g}  ·  Ventas: {len(vistas) - n_g}  ·  "
            f"Correctas: {len(vistas) - revisar - errores} · Revisar: {revisar} · "
            f"Errores: {errores}")
        self._pintar_resumen()

    def _pintar_contadores(self) -> None:
        """Recuento de estados en la barra inferior, con los colores de la tabla."""
        if not hasattr(self, "lbl_contadores"):
            return
        c = Counter(registro.presentacion for registro in self.filas)
        partes = [f"<span style='color:{COLOR_CONTADOR[codigo]}; font-weight:600'>"
                  f"{html.escape(TEXTO_PRESENTACION[codigo])}: {c[codigo]}</span>"
                  for codigo in ORDEN_PRESENTACION if c[codigo]]
        self.lbl_contadores.setText(" &nbsp;·&nbsp; ".join(partes))
        self._pintar_progreso(partes)

    def _pintar_progreso(self, partes) -> None:
        """«N de M listas»: por factura (una con varias líneas cuenta una
        vez y está lista solo si lo están todas sus líneas)."""
        if not hasattr(self, "panel_progreso"):
            return
        pendientes = {}
        for i, registro in enumerate(self.filas):
            clave = clave_factura(registro.factura, i)
            pendientes[clave] = pendientes.get(clave, False) or (
                registro.presentacion in (POR_REVISAR, CON_ERROR))
        total = len(pendientes)
        faltan = sum(pendientes.values())
        if not total:
            self.lbl_progreso.setText("Sin facturas")
        else:
            self.lbl_progreso.setText(f"{total - faltan} de {total} listas")
        self.lbl_faltan.setText(f"Faltan {faltan}" if faltan else
                                ("✓ Todas listas" if total else ""))
        self.lbl_faltan.setProperty("todas", not faltan)
        self.lbl_faltan.style().unpolish(self.lbl_faltan)
        self.lbl_faltan.style().polish(self.lbl_faltan)
        self.barra_progreso.setRange(0, max(total, 1))
        self.barra_progreso.setValue(total - faltan)
        self.lbl_progreso_detalle.setText(" &nbsp;·&nbsp; ".join(partes))

    def _pintar_resumen(self):
        """Totales del taco, del periodo y de la búsqueda actualmente visible."""
        filas_por_tipo = {"gasto": [], "venta": []}
        for r in range(self.tabla.rowCount()):
            filas_por_tipo[self._tipo_fila(r)].append(
                (self.filas[r]["bloque"] or "—", self.filas[r]["factura"]))
        # En recargo el gasto no tiene desglose de IVA: solo el total factura.
        recargo = self._por_el_total()
        periodo = getattr(self, "_periodo_lote", PeriodoLote())
        filtro_activo = self._hay_filtro_activo()
        # «3T 2026» no se parte en dos líneas en la columna estrecha.
        periodo_txt = periodo.etiqueta.replace(" ", "\u00a0")
        self.lbl_resumen_titulo.setText(
            "Comprobación de totales"
            + (f"  ·  {periodo_txt}" if periodo.ejercicio else "")
            + (f"  ·  {self._texto_filtro()}" if filtro_activo else "")
            + (f"  ·  {self._motivo_por_el_total()}" if recargo else ""))

        lineas = []   # (bloque, tipo, Totales, es_total)
        for tipo, etiqueta in (("gasto", "Gastos"), ("venta", "Ingresos")):
            pares = filas_por_tipo[tipo]
            if not pares:
                continue
            por_bloque = resumir_por_bloque(pares)
            if self.accion_detalle_bloques.isChecked():
                for nombre, t in por_bloque.items():
                    lineas.append((nombre, etiqueta, t, False))
            fuera_periodo = ([f for _, f in pares if not periodo.contiene(f)]
                             if periodo.es_trimestre else [])
            lineas.append(("TOTAL LOTE", etiqueta,
                           resumir([f for _, f in pares]), True))
            if fuera_periodo:
                dentro = [f for _, f in pares if periodo.contiene(f)]
                lineas.append((f"DENTRO {periodo.etiqueta}", etiqueta,
                               resumir(dentro), True))
                lineas.append((f"FUERA {periodo.etiqueta}", etiqueta,
                               resumir(fuera_periodo), True))
            if filtro_activo:
                visibles = [self.filas[r]["factura"]
                            for r in range(self.tabla.rowCount())
                            if not self.tabla.isRowHidden(r)
                            and self._tipo_fila(r) == tipo]
                lineas.append(("FILTRO ACTUAL", etiqueta,
                               resumir(visibles), True))
        self._volcar_resumen(lineas, recargo)

    def _volcar_resumen(self, lineas, recargo):
        # Un IVA por columna, con su porcentaje en la cabecera: asi se leen los
        # totales de cada tipo de un vistazo, en vez de todos en una celda.
        tipos_iva = sorted({tipo for _, _, t, _ in lineas
                            for tipo in t.iva_por_tipo})
        self._tipos_iva_resumen = tipos_iva
        cabeceras = _cabeceras_resumen(tipos_iva)
        self.tabla_resumen.setColumnCount(len(cabeceras))
        self.tabla_resumen.setHorizontalHeaderLabels(cabeceras)
        self.tabla_resumen.setRowCount(len(lineas))
        for r, (bloque, tipo, t, es_total) in enumerate(lineas):
            # En recargo el gasto va por el total factura: el desglose de IVA
            # no existe y ponerlo a 0,00 despistaria. Salvo si hay facturas
            # con retención, que no se resumen y van con su desglose.
            solo_total = recargo and tipo == "Gastos" and not t.iva_por_tipo
            cuotas = ["" if solo_total or p not in t.iva_por_tipo
                      else eur(t.iva_por_tipo[p]) for p in tipos_iva]
            if not tipos_iva:
                cuotas = ["" if solo_total else eur(t.iva)]
            valores = [
                bloque, tipo, str(t.facturas), str(t.lineas),
                "" if solo_total else eur(t.base),
                *cuotas,
                eur(t.requiv) if t.tiene_requiv and not solo_total else "",
                eur_con_signo(-t.irpf) if t.tiene_irpf else "",
                eur(t.suplidos) if t.tiene_suplidos and not solo_total else "",
                eur(t.total),
            ]
            for c, texto in enumerate(valores):
                item = QTableWidgetItem(texto)
                if c >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if es_total:
                    fuente = item.font()
                    fuente.setBold(True)
                    item.setFont(fuente)
                if bloque == "FILTRO ACTUAL":
                    item.setBackground(QColor(ACCENT_FAINT))
                    item.setForeground(QColor(INK))
                self.tabla_resumen.setItem(r, c, item)
        # Con un lote vacío no se reserva una gran tabla en blanco.
        self._ajustar_altura_resumen()
        # En pantalla, con un filtro, lo que se ve va primero (es lo que se
        # está cuadrando); Copiar y el listado PDF siguen el orden de siempre.
        # (Si el filtro no deja nada de ese tipo, su fila a cero va con las
        # demás, no delante.)
        en_pantalla = sorted(lineas, key=lambda linea: not (
            linea[0] == "FILTRO ACTUAL" and linea[2].lineas))
        self._pintar_tabla_totales(en_pantalla, recargo, tipos_iva)
        self._actualizar_su_suma(en_pantalla, recargo)

    def _actualizar_su_suma(self, lineas, recargo=False) -> None:
        """«Su suma a mano» compara con lo que se ve: con un filtro (un mes,
        un proveedor…), lo filtrado; si no, todo el lote. Con el cliente en
        recargo «por el total», los gastos solo tienen total (y retención)."""
        if not hasattr(self, "tabla_su_suma"):
            return
        if not self.filas and not getattr(self, "_bloques", None):
            # Lote vacío: lo tecleado era para el lote anterior.
            self.tabla_su_suma.limpiar()
        elegidos = {}
        self._fila_comparada = {}
        for r, (ambito, tipo, t, _es_total) in enumerate(lineas):
            clave = "gasto" if tipo == "Gastos" else "venta"
            if ambito == "FILTRO ACTUAL" or (
                    ambito == "TOTAL LOTE" and clave not in elegidos):
                solo_total = recargo and tipo == "Gastos" and not t.iva_por_tipo
                elegidos[clave] = (t, f"{tipo} · {self._nombre_ambito(ambito)}",
                                   solo_total)
                self._fila_comparada[clave] = r
        self.tabla_su_suma.actualizar(elegidos)
        self._resaltar_fila_comparada()

    def _resaltar_fila_comparada(self) -> None:
        """El ámbito de los totales con el que se compara «Su suma», en
        negrita (su fila, o su columna con los totales en columna): así se
        sabe de dónde sale la cifra del programa. El total, siempre."""
        if not hasattr(self, "tabla_totales"):
            return
        comparada = getattr(self, "_fila_comparada", {}).get(self.tabla_su_suma.tipo)
        en_columna = self.tabla_su_suma.vertical
        for r in range(self.tabla_totales.rowCount()):
            for c in range(self.tabla_totales.columnCount()):
                item = self.tabla_totales.item(r, c)
                if item is None:
                    continue
                ambito = c - 1 if en_columna else r
                fuente = item.font()
                fuente.setBold(ambito == comparada or item.data(Qt.UserRole) == "total")
                item.setFont(fuente)

    def _texto_filtro(self) -> str:
        """Cómo se nombra el filtro en el título: el mes si es solo eso."""
        mes = (self.combo_filtro_mes.currentData()
               if hasattr(self, "combo_filtro_mes") else None)
        if mes is None:
            return "filtro activo"
        otros = (self.combo_filtro_estado.currentIndex()
                 or not self.botones_tipo["todos"].isChecked()
                 or self.combo_filtro_bloque.currentText() != TODOS_LOS_BLOQUES
                 or self.txt_buscar.text().strip()
                 or (self.combo_filtro_registro.isVisible()
                     and self.combo_filtro_registro.currentData() != "todas"))
        nombre = self.combo_filtro_mes.currentText().lower().replace(" ", "\u00a0")
        return f"{nombre} y otros filtros" if otros else nombre

    # Cómo se llama cada fila en la tarjeta de la derecha (más claro que en
    # la tabla, que se conserva tal cual para Copiar y el listado PDF).
    @staticmethod
    def _nombre_ambito(ambito: str) -> str:
        if ambito == "TOTAL LOTE":
            return "Todo el lote"
        if ambito == "FILTRO ACTUAL":
            return "Lo que se ve (filtro)"
        if ambito.startswith("DENTRO "):
            return "Dentro del " + ambito[len("DENTRO "):].replace(" ", "\u00a0")
        if ambito.startswith("FUERA "):
            return "Fuera del " + ambito[len("FUERA "):].replace(" ", "\u00a0")
        return ambito

    def _pintar_tabla_totales(self, lineas, recargo, tipos_iva) -> None:
        """Los totales con el desglose completo, como el listado de Aplifisa.

        Para cada ámbito (todo el lote, dentro y fuera del trimestre, lo que
        se ve con un filtro): nº de facturas, base, cada IVA, total IVA,
        recargo, retención, suplidos y total. Lo que vale cero también se ve
        (en gris): así se sabe que el programa lo ha mirado.

        Abajo y a lo ancho, una fila por ámbito y una columna por importe,
        con «Su suma» debajo. En columna (o en una caja), un importe por
        fila y una columna por ámbito, con «Su suma» al lado.
        """
        if not hasattr(self, "tabla_totales"):
            return
        tabla = self.tabla_totales
        sin_tipo = any(abs(t.iva_sin_tipo) >= 0.005 for _a, _t, t, _e in lineas)
        columnas = columnas_totales(tipos_iva, sin_tipo)
        # Por ámbito: (nombre, globo, fondo, [(texto, color, globo)] del nº
        # de facturas y de cada importe).
        ambitos = []
        motivo = (self._motivo_por_el_total()[:1].upper()
                  + self._motivo_por_el_total()[1:]) if recargo else ""
        for ambito, tipo, t, _es_total in lineas:
            solo_total = recargo and tipo == "Gastos" and not t.iva_por_tipo
            fondo = QColor(ACCENT_FAINT) if ambito == "FILTRO ACTUAL" else None
            nota = None
            if recargo and tipo == "Gastos" and not solo_total:
                nota = (f"{motivo}: los gastos van por el total factura "
                        "(dentro de la base). Alguno lleva todavía desglose "
                        "de IVA: compruébelo.")
            cifras = [(str(t.facturas), INK,
                       f"{t.facturas} factura(s) · {t.lineas} línea(s)")]
            for clave, _cabecera, importe in columnas:
                if solo_total and clave not in SOLO_TOTAL:
                    cifras.append(("—", COLOR_CERO,
                                   f"{motivo}: los gastos van a Aplifisa por "
                                   "el total factura."))
                    continue
                valor = importe(t)
                cero = abs(valor) < 0.005
                cifras.append((eur(0.0) if cero else eur_con_signo(valor),
                               COLOR_CERO if cero else INK, None))
            ambitos.append((tipo, self._nombre_ambito(ambito), nota, fondo, cifras))
        ayuda_total = ("Total = base + IVA + recargo + suplidos − retención: lo "
                       "que se registra en Aplifisa. La factura cuyo total "
                       "impreso no coincide sale marcada en la tabla.")

        def celda(texto, color, ayuda, fondo, derecha, total=False):
            item = QTableWidgetItem(texto)
            item.setForeground(QColor(color))
            if derecha:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if total:
                item.setData(Qt.UserRole, "total")
            if ayuda:
                item.setToolTip(ayuda)
            if fondo is not None:
                item.setBackground(fondo)
            return item

        conceptos = ["Nº facturas", *(c[1] for c in columnas)]
        ultimo = len(conceptos) - 1
        if self.tabla_su_suma.vertical:
            # Un importe por fila; una columna por ámbito.
            tabla.setRowCount(len(conceptos))
            tabla.setColumnCount(1 + len(ambitos))
            tabla.setHorizontalHeaderLabels(
                ["", *(f"{tipo}\n{nombre}" for tipo, nombre, *_ in ambitos)])
            tabla.horizontalHeaderItem(0).setToolTip("")
            for c, (tipo, nombre, nota, _f, _x) in enumerate(ambitos, start=1):
                tabla.horizontalHeaderItem(c).setToolTip(
                    f"{tipo} · {nombre}" + (f"\n{nota}" if nota else ""))
            for r, concepto in enumerate(conceptos):
                tabla.setItem(r, 0, celda(concepto, INK,
                                          ayuda_total if r == ultimo else None,
                                          None, False, total=r == ultimo))
            for c, (_tipo, _nombre, _nota, fondo, cifras) in enumerate(ambitos, start=1):
                for r, (texto, color, ayuda) in enumerate(cifras):
                    tabla.setItem(r, c, celda(texto, color, ayuda, fondo, True,
                                              total=r == ultimo))
        else:
            # Una fila por ámbito; una columna por importe.
            cabeceras = ["", "Nº", *(c[1] for c in columnas)]
            tabla.setColumnCount(len(cabeceras))
            tabla.setHorizontalHeaderLabels(cabeceras)
            # Qt reutiliza los títulos: sin los globos de la forma en columna.
            for c in range(len(cabeceras)):
                tabla.horizontalHeaderItem(c).setToolTip("")
            tabla.horizontalHeaderItem(len(cabeceras) - 1).setToolTip(ayuda_total)
            tabla.setRowCount(len(ambitos))
            for r, (tipo, nombre, nota, fondo, cifras) in enumerate(ambitos):
                tabla.setItem(r, 0, celda(f"{tipo} · {nombre}", INK, nota, fondo, False))
                for i, (texto, color, ayuda) in enumerate(cifras):
                    tabla.setItem(r, 1 + i, celda(texto, color, ayuda, fondo, True,
                                                  total=i == ultimo))
        alto_fila = ALTO_FILA_COLUMNA if self.tabla_su_suma.vertical else 24
        for r in range(tabla.rowCount()):
            if tabla.rowHeight(r) != alto_fila:
                tabla.setRowHeight(r, alto_fila)
        self.tabla_su_suma.configurar(columnas)
        self._anchos_totales(columnas)
        self._ajustar_alto_totales()

    def _ajustar_alto_totales(self) -> None:
        """Como mucho lo que ocupan todas las filas (no crece en blanco); si
        el divisor la deja más baja, se desplaza. Se repite al verse la
        ventana: hasta entonces no se sabe el alto real de la cabecera.
        En columna, «Su suma» mide lo mismo que los totales (al lado)."""
        tabla = self.tabla_totales
        # En columna la cabecera tiene alto fijo (el de las dos tablas).
        cabecera = max(tabla.horizontalHeader().sizeHint().height(),
                       tabla.horizontalHeader().minimumHeight())
        if tabla.horizontalHeader().isVisible():
            cabecera = max(cabecera, tabla.horizontalHeader().height())
        marco = 2 * tabla.frameWidth()
        alto = cabecera + sum(tabla.rowHeight(r) for r in range(tabla.rowCount())) + marco
        # La barra horizontal de los totales (sin «Su suma», o en columna)
        # va debajo de las filas, sin taparlas.
        barra = tabla.horizontalScrollBar()
        if (tabla.horizontalScrollBarPolicy() != Qt.ScrollBarAlwaysOff
                and barra.maximum() > 0):
            alto += barra.sizeHint().height()
        maximo = max(alto, cabecera + marco + 4)
        filas_minimas = 4 if self.tabla_su_suma.vertical else 2
        minimo = min(alto, cabecera + filas_minimas
                     * tabla.verticalHeader().defaultSectionSize() + marco)
        for widget in ((tabla, self.tabla_su_suma) if self.tabla_su_suma.vertical
                       else (tabla,)):
            if widget.maximumHeight() != maximo:
                widget.setMaximumHeight(maximo)
            if widget.minimumHeight() != minimo:
                widget.setMinimumHeight(minimo)
            widget.updateGeometry()
        if hasattr(self, "_encajar_totales"):
            self._encajar_totales()

    def _anchos_totales(self, columnas) -> None:
        """Abajo y a lo ancho: mismos anchos en los totales y en «Su suma»
        (cada casilla bajo su columna). En columna: misma cabecera y mismo
        alto de fila en las dos (cada casilla a la altura de su importe).
        Cada importe, lo que ocupe su cifra más larga (o su título), y nunca
        menos que una cifra de cinco dígitos."""
        self._columnas_totales = list(columnas)
        tabla = self.tabla_totales
        medida = tabla.fontMetrics()
        negrita = QFont(tabla.font())
        negrita.setBold(True)
        medida_negrita = QFontMetrics(negrita)
        cabecera = QFontMetrics(tabla.horizontalHeader().font())
        minimo = medida.horizontalAdvance("−99.999,99 €") + 20
        if self.tabla_su_suma.vertical:
            self._anchos_totales_en_columna(medida_negrita, cabecera, minimo)
            return
        anchos_importe = []
        for i, (_clave, titulo, _importe) in enumerate(columnas):
            c = PRIMERA_COLUMNA_IMPORTE + i
            cifras = [medida_negrita.horizontalAdvance(tabla.item(r, c).text())
                      for r in range(tabla.rowCount()) if tabla.item(r, c)]
            anchos_importe.append(max(
                minimo, cabecera.horizontalAdvance(titulo) + 24,
                max(cifras, default=0) + 20))
        ambitos = [medida_negrita.horizontalAdvance(tabla.item(r, 0).text())
                   for r in range(tabla.rowCount()) if tabla.item(r, 0)]
        anchos = [max(150, max(ambitos, default=0) + 16),
                  max(40, cabecera.horizontalAdvance("Nº") + 20)] + anchos_importe
        # El ámbito se queda lo que sobre, pero nunca menos que su texto: si
        # no cabe todo, se desplaza a lo ancho (la barra la lleva «Su suma»).
        anchos[0] = max(anchos[0], tabla.viewport().width() - sum(anchos[1:]))
        for tabla in (self.tabla_totales, self.tabla_su_suma):
            if tabla.columnCount() < len(anchos):
                continue
            cabecera = tabla.horizontalHeader()
            # Los anchos van calculados (el Nº, 40 como poco); la columna de
            # relleno de «Su suma» mide lo que la barra, menos de 40.
            cabecera.setMinimumSectionSize(1)
            for c, ancho in enumerate(anchos):
                cabecera.setSectionResizeMode(c, QHeaderView.Fixed)
                if tabla.columnWidth(c) != ancho:
                    tabla.setColumnWidth(c, ancho)
        # La barra vertical de los totales les quita ancho de vista: «Su
        # suma» lleva al final una columna vacía de ese ancho para que las
        # dos se desplacen igual.
        totales = self.tabla_totales
        barra = totales.width() - totales.viewport().width() - 2 * totales.frameWidth()
        self.tabla_su_suma.dejar_hueco(barra if totales.verticalScrollBar().maximum() > 0
                                       else 0)

    def _anchos_totales_en_columna(self, medida_negrita, cabecera, minimo) -> None:
        tabla, suma = self.tabla_totales, self.tabla_su_suma
        cabecera_tabla = tabla.horizontalHeader()
        cabecera_tabla.setMinimumSectionSize(1)
        conceptos = [medida_negrita.horizontalAdvance(tabla.item(r, 0).text())
                     for r in range(tabla.rowCount()) if tabla.item(r, 0)]
        anchos = [max(100, max(conceptos, default=0) + 12)]
        for c in range(1, tabla.columnCount()):
            titulo = tabla.horizontalHeaderItem(c).text() if tabla.horizontalHeaderItem(c) else ""
            lineas = [cabecera.horizontalAdvance(x) for x in titulo.split("\n")]
            cifras = [medida_negrita.horizontalAdvance(tabla.item(r, c).text())
                      for r in range(tabla.rowCount()) if tabla.item(r, c)]
            anchos.append(max(minimo - 16, max(lineas, default=0) + 16,
                              max(cifras, default=0) + 14))
        # El concepto se queda lo que sobre, pero nunca menos que su texto.
        anchos[0] = max(anchos[0], tabla.viewport().width() - sum(anchos[1:]))
        for c, ancho in enumerate(anchos):
            cabecera_tabla.setSectionResizeMode(c, QHeaderView.Fixed)
            if tabla.columnWidth(c) != ancho:
                tabla.setColumnWidth(c, ancho)
        # Misma cabecera y mismo alto de fila en las dos tablas.
        alto = max(cabecera_tabla.sizeHint().height(),
                   suma.horizontalHeader().sizeHint().height())
        cambia = False
        for widget in (cabecera_tabla, suma.horizontalHeader()):
            if widget.minimumHeight() != alto or widget.maximumHeight() != alto:
                widget.setFixedHeight(alto)
                cambia = True
        # La barra horizontal de los totales les quita alto de vista: «Su
        # suma» lleva al final una fila vacía de ese alto para que las dos
        # se desplacen igual.
        barra = tabla.horizontalScrollBar()
        suma.dejar_hueco(barra.height() if barra.isVisible() else 0)
        if cambia:
            # Con la letra ya puesta la cabecera puede medir otra cosa.
            self._ajustar_alto_totales()

    def _copiar_resumen(self):
        """El resumen al portapapeles, para pegarlo al comprobar los totales."""
        filas = ["\t".join(
            _cabeceras_resumen(getattr(self, "_tipos_iva_resumen", [])))]
        for r in range(self.tabla_resumen.rowCount()):
            filas.append("\t".join(
                (self.tabla_resumen.item(r, c).text() if self.tabla_resumen.item(r, c)
                 else "")
                for c in range(self.tabla_resumen.columnCount())))
        QApplication.clipboard().setText("\n".join(filas))
        self.lbl_estado.setText("Resumen copiado al portapapeles.")

    def _html_listado_totales(self) -> str:
        """Listado fiscal legible e imprimible del lote y del filtro actual."""
        escapar = lambda valor: html.escape(str(valor or ""))
        cabeceras_resumen = _cabeceras_resumen(
            getattr(self, "_tipos_iva_resumen", []))
        filas_resumen = []
        for r in range(self.tabla_resumen.rowCount()):
            celdas = [
                self.tabla_resumen.item(r, c).text()
                if self.tabla_resumen.item(r, c) else ""
                for c in range(self.tabla_resumen.columnCount())
            ]
            filas_resumen.append("<tr>" + "".join(
                f"<td>{escapar(valor)}</td>" for valor in celdas) + "</tr>")

        columnas_detalle = [
            ("Factura", C_NUM), ("Fecha", C_FECHA), ("Nombre", C_NOMBRE),
            ("NIF", C_NIF), ("Tipo", C_TIPO), ("Cuenta", C_CUENTA),
            ("GXX", C_GXX), ("Base", C_BASE), ("% IVA", C_PCT),
            ("Cuota", C_CUOTA),
        ]
        if self._con_columnas_de_recargo():
            columnas_detalle.extend([
                ("Base RE", C_BASE_RE), ("% RE", C_PCT_RE),
                ("Cuota RE", C_CUOTA_RE),
            ])
        columnas_detalle.extend([
            ("Base IRPF", C_BASE_IRPF), ("% IRPF", C_PCT_IRPF),
            ("Retención", C_CUOTA_IRPF), ("Total", C_TOTAL),
        ])
        filas_visibles = [r for r in range(self.tabla.rowCount())
                          if not self.tabla.isRowHidden(r)]
        detalle = []
        for r in filas_visibles:
            valores = []
            for _titulo, columna in columnas_detalle:
                if columna == C_TIPO:
                    valor = "Ingreso" if self._tipo_fila(r) == "venta" else "Gasto"
                else:
                    item = self.tabla.item(r, columna)
                    valor = item.text() if item else ""
                valores.append(valor)
            detalle.append("<tr>" + "".join(
                f"<td>{escapar(valor)}</td>" for valor in valores) + "</tr>")

        cliente = escapar(getattr(self, "_cliente_nombre", "") or
                           self.lbl_cliente.text())
        nif = escapar(getattr(self, "_cliente_nif", ""))
        periodo = escapar(getattr(self, "_periodo_lote", PeriodoLote()).etiqueta)
        estilo = """
        <style>
          body { font-family: 'Segoe UI', Arial, sans-serif; color: #24384D; }
          h1 { color: #326FA6; font-size: 18pt; margin-bottom: 4px; }
          h2 { font-size: 11pt; margin: 16px 0 6px; }
          p.meta { color: #5D7084; margin: 2px 0; }
          table { border-collapse: collapse; width: 100%; font-size: 7.5pt; }
          th { background: #EAF3FC; color: #24384D; font-weight: 600; }
          th, td { border: 1px solid #DCE5F0; padding: 4px; }
          td:not(:nth-child(1)):not(:nth-child(2)):not(:nth-child(3)) {
            text-align: right;
          }
        </style>
        """
        return f"""<!doctype html><html><head>{estilo}</head><body>
        <h1>Comprobación de totales</h1>
        <p class="meta"><b>Cliente:</b> {cliente} {(' · ' + nif) if nif else ''}</p>
        <p class="meta"><b>Periodo:</b> {periodo or 'Sin periodo detectado'} ·
        <b>Fecha:</b> {date.today().strftime('%d/%m/%Y')}</p>
        <h2>Resumen del lote y del filtro</h2>
        <table><thead><tr>{''.join(f'<th>{escapar(c)}</th>' for c in cabeceras_resumen)}</tr></thead>
        <tbody>{''.join(filas_resumen)}</tbody></table>
        <h2>Facturas mostradas ({len(filas_visibles)})</h2>
        <table><thead><tr>{''.join(f'<th>{escapar(t)}</th>' for t, _ in columnas_detalle)}</tr></thead>
        <tbody>{''.join(detalle)}</tbody></table>
        </body></html>"""

    def _guardar_listado_totales(self) -> None:
        if not self.tabla.rowCount():
            self._avisar("No hay facturas para incluir en el listado.", AVISO)
            return
        cliente = re.sub(r"[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ -]+", "", (
            getattr(self, "_cliente_nombre", "") or "CLIENTE")).strip()
        sugerido = os.path.join(
            escritorio(), f"COMPROBACION TOTALES {cliente or 'CLIENTE'}.pdf")
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar listado de comprobación", sugerido,
            "Documento PDF (*.pdf)")
        if not ruta:
            return
        if not ruta.lower().endswith(".pdf"):
            ruta += ".pdf"
        documento = QTextDocument(self)
        documento.setHtml(self._html_listado_totales())
        escritor = QPdfWriter(ruta)
        escritor.setResolution(150)
        escritor.setPageSize(QPageSize(QPageSize.A4))
        escritor.setPageOrientation(QPageLayout.Landscape)
        documento.print_(escritor)
        self.lbl_estado.setText(f"Listado de comprobación guardado: {ruta}")

    # ---------- miniatura ----------
