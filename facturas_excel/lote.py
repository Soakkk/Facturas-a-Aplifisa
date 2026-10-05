"""Las facturas del lote, sin nada de pantalla.

Antes lo que valía era lo escrito en cada celda de la tabla: cada comprobación
volvía a leer las celdas, y ordenar borraba y rehacía la tabla entera. Ahora
cada línea de la tabla es una `Fila` con su `Factura`, y la tabla solo la
enseña. Una corrección en una celda se apunta al momento en la factura; al
revés, todo lo que cambia el programa se cambia en la factura y se repinta.

Aquí no se importa Qt: se puede probar y reutilizar sin abrir ventanas.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any, List, Optional

from .modelo import Factura
from .validacion import ERROR, OK, REVISAR, fecha_de

# Campos de la factura que se ven y se corrigen en la tabla.
CAMPOS_TEXTO = ("concepto", "subclave", "fecha", "num_factura", "nombre", "nif")
CAMPOS_NUMERO = ("base_iva", "pct_iva", "cuota_iva", "base_requiv",
                 "pct_requiv", "cuota_requiv", "base_irpf", "pct_irpf",
                 "cuota_irpf", "total_impreso")
CAMPOS_RECARGO = ("base_requiv", "pct_requiv", "cuota_requiv")
CAMPOS_IRPF = ("base_irpf", "pct_irpf", "cuota_irpf")

# Cómo se presenta el estado de una línea. El programa decide por el CÓDIGO;
# el texto es solo lo que se ve (antes se comparaba el texto de la celda).
# Ya no hay estado «Manual»: lo que antes se apartaba (bien de inversión,
# suplido, sustituida) queda en «Revisar» con su motivo y se exporta después
# de «Marcar revisada», como cualquier otro aviso ámbar.
VERIFICADA, SIN_VERIFICAR, POR_REVISAR, CON_ERROR, REVISADA, CORREGIDA = (
    "verificada", "sin_verificar", "revisar", "error", "revisada", "corregida")
TEXTO_PRESENTACION = {
    VERIFICADA: "✓ Verificada", SIN_VERIFICAR: "○ Sin verificar",
    POR_REVISAR: "! Revisar", CON_ERROR: "✕ Error",
    REVISADA: "✓ Revisada", CORREGIDA: "✎ Corregida",
}
ORDEN_PRESENTACION = (VERIFICADA, SIN_VERIFICAR, REVISADA, CORREGIDA,
                      POR_REVISAR, CON_ERROR)
# Lo que todavía impide exportar (o hay que mirar).
PENDIENTES = (POR_REVISAR, CON_ERROR)


def normalizar(f: Factura) -> Factura:
    """Deja los datos como los enseña la tabla (y como se exportan).

    Importes a dos decimales, textos sin blancos sobrantes y la subclave en
    mayúsculas. Es lo mismo que pasaba antes al releer cada celda, así que
    ninguna comprobación cambia de resultado.
    """
    for campo in CAMPOS_NUMERO:
        valor = getattr(f, campo)
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            setattr(f, campo, round(float(valor), 2))
    for campo in CAMPOS_TEXTO:
        valor = getattr(f, campo)
        if valor is None:
            continue
        texto = str(valor)
        if campo == "subclave":
            texto = texto.strip().upper()
        setattr(f, campo, texto or None)
    return f


def presentacion(estado: str, f: Factura, confirmada: bool,
                 corregida: bool = False) -> str:
    """El código con el que se enseña una línea.

    Un error manda siempre. Después, lo que confirmó una persona: «Revisada»
    con el botón, «Corregida» si cambió algún dato a mano.
    """
    if estado == ERROR:
        return CON_ERROR
    if confirmada:
        return REVISADA
    if corregida:
        return CORREGIDA
    if estado == OK:
        return VERIFICADA if getattr(f, "verificacion", "") == "doble" else SIN_VERIFICAR
    return CON_ERROR if estado == ERROR else POR_REVISAR


@dataclass
class Fila:
    """Una línea de la tabla: la factura y lo que el programa sabe de ella."""

    png: Any
    factura: Factura
    tipo: str = "gasto"            # "gasto" o "venta"
    aviso: str = ""
    bloque: str = ""
    fuentes: list = field(default_factory=list)
    # Lo que calcula cada revalidación.
    estado: Optional[str] = None
    estado_base: Optional[str] = None
    mensajes: list = field(default_factory=list)
    presentacion: str = ""
    ya_exportada: Optional[dict] = None
    # Resultado del último contraste con el listado de Aplifisa.
    registro_estado: Optional[str] = None
    registro_detalle: Optional[list] = None
    # Dónde está cada dato en la hoja (recuadros del visor).
    localizacion: Optional[dict] = None
    # Ámbar ya aceptado por una persona (revisada o corregida), sin contar
    # el aviso de «ya exportada», que la exportación trata aparte.
    aceptada: bool = False

    def __post_init__(self):
        if not self.fuentes:
            self.fuentes = [self.factura]
        normalizar(self.factura)

    # Acceso como diccionario: las sesiones guardadas, las muestras y las
    # pruebas antiguas tratan cada fila como un dict.
    def __getitem__(self, clave):
        try:
            return getattr(self, clave)
        except AttributeError:
            raise KeyError(clave) from None

    def __setitem__(self, clave, valor):
        setattr(self, clave, valor)

    def get(self, clave, por_defecto=None):
        valor = getattr(self, clave, None)
        return por_defecto if valor is None else valor

    def pop(self, clave, por_defecto=None):
        valor = self.get(clave, por_defecto)
        if hasattr(self, clave):
            setattr(self, clave, None)
        return valor

    def keys(self):
        return [f.name for f in fields(self)]

    @property
    def confirmada(self) -> bool:
        f = self.factura
        return self.estado == REVISAR and f.revision_confirmada

    @property
    def pendiente(self) -> bool:
        """Lo que impide exportar: un error o un ámbar sin confirmar."""
        f = self.factura
        return (self.estado == ERROR or
                (self.estado == REVISAR and not f.revision_confirmada))


def filas_de_bloques(bloques, por_el_total: bool, a_total_factura) -> List[Fila]:
    """Las líneas que enseña la tabla a partir de lo leído en cada bloque.

    Con el cliente en recargo por el total, cada factura se enseña como UNA
    línea por el total; sus líneas originales quedan en `fuentes`.
    """
    filas: List[Fila] = []
    for bloque in bloques:
        for png, pr in bloque["procesadas"]:
            fuentes = [f for f in pr.facturas if not f.eliminada]
            if not fuentes:
                continue
            # Manda el tipo que ha puesto la persona (gasto/venta), si lo hay:
            # solo los gastos se resumen por el total.
            tipo = next((f.tipo_revision for f in fuentes if f.tipo_revision),
                        None) or pr.tipo
            # Por el total: todo el lote (cliente en recargo o sin derecho a
            # deducir) o esta factura, si una persona dijo que su IVA no se
            # deduce («Por el total»).
            resumir = por_el_total or any(
                getattr(f, "no_deducible", False) for f in fuentes)
            vista = (a_total_factura(replace(pr, facturas=fuentes, tipo=tipo))
                     if resumir else pr)
            visibles = vista.facturas if resumir else fuentes
            for f in visibles:
                filas.append(Fila(
                    png, f, f.tipo_revision or vista.tipo, vista.aviso,
                    bloque["nombre"], list(fuentes if resumir else [f])))
    return filas


def valor_orden(fila: Fila, campo: str):
    """Con qué se ordena una fila por esa columna (None: al final)."""
    f = fila.factura
    if campo == "estado":
        return {ERROR: 0, REVISAR: 1, OK: 2}.get(fila.estado, 3)
    if campo == "tipo":
        return fila.tipo
    if campo == "fecha":
        dia = fecha_de(f.fecha)
        return dia.toordinal() if dia else None
    dato = getattr(f, campo, None)
    return dato.casefold() if isinstance(dato, str) else dato


def ordenar(filas: List[Fila], campo: str, ascendente: bool) -> List[Fila]:
    """Ordena sin perder nada: las que no tienen ese dato van al final."""
    con = [x for x in filas if valor_orden(x, campo) not in (None, "")]
    sin = [x for x in filas if valor_orden(x, campo) in (None, "")]
    con.sort(key=lambda x: valor_orden(x, campo), reverse=not ascendente)
    return con + sin


def hay_datos(filas: List[Fila], campos) -> bool:
    return any(getattr(x.factura, c, None) is not None
               for x in filas for c in campos)
