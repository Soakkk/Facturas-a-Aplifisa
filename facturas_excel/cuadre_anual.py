"""El cuadre del año de un cliente: lo que tiene guardado el programa frente a
lo que hay registrado en Aplifisa, del 1 de enero a la fecha que se elija.

El programa guarda una ficha de cada factura que sale de él (registro de
facturas) con su PDF en la carpeta del cliente. El listado de Aplifisa del
mismo periodo es la verdad de lo registrado. Cruzándolos sale, factura a
factura:

  - bien:            está en los dos y su PDF está guardado;
  - falta_aplifisa:  el programa la tiene y en Aplifisa no está registrada;
  - falta_programa:  está en Aplifisa y el programa no la tiene guardada
                     (no hay PDF: hay que buscarla y escanearla);
  - sin_pdf:         registrada en los dos, pero su PDF no está en su sitio;
  - distinta:        es la misma factura, pero cambia la fecha o un importe;
  - duplicada:       la misma factura dos veces (mismo proveedor, número,
                     fecha e importes): en Aplifisa sobra una.

Así se puede comprobar a mitad de año (6 o 9 meses) sin esperar al cierre.
Sin IA ni coste: todo sale de lo ya leído y del texto del listado.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from . import registro_facturas
from .procesar import nombres_compatibles, normaliza_nif
from .registro import Apunte, Registro, _normalizar_id
from .validacion import fecha_de

TOLERANCIA = 0.02
DIAS_FECHA_DISTINTA = 62

BIEN, FALTA_APLIFISA, FALTA_PROGRAMA = "bien", "falta_aplifisa", "falta_programa"
SIN_PDF, DISTINTA, DUPLICADA = "sin_pdf", "distinta", "duplicada"
TEXTO_ESTADO = {
    BIEN: "Todo bien",
    FALTA_APLIFISA: "Falta en Aplifisa",
    FALTA_PROGRAMA: "Falta en el programa",
    SIN_PDF: "Falta el PDF",
    DISTINTA: "Dato distinto",
    DUPLICADA: "Duplicada",
}
ORDEN_ESTADO = (FALTA_PROGRAMA, FALTA_APLIFISA, SIN_PDF, DUPLICADA, DISTINTA, BIEN)


@dataclass
class FacturaPrograma:
    """Una factura que tiene el programa (registro o lote abierto)."""
    tipo: str                      # gasto / venta
    fecha: str
    num_factura: str = ""
    nombre: str = ""
    nif: str = ""
    base: float = 0.0
    cuota: Optional[float] = None
    total: Optional[float] = None
    pdf: str = ""                  # su PDF en el archivo (o el del escaneo)
    origen: str = "registro"       # registro / lote
    excel: str = ""
    exportada: str = ""
    fila: Optional[int] = None     # en el lote abierto, si está

    @property
    def dia(self) -> Optional[date]:
        return fecha_de(self.fecha)

    @property
    def pdf_guardado(self) -> bool:
        return bool(self.pdf) and os.path.isfile(self.pdf)


@dataclass
class FacturaAplifisa:
    """Una factura del listado: sus líneas (una por tipo de IVA) juntas."""
    tipo: str
    fecha: str
    numero: str = ""
    num_proveedor: str = ""
    nombre: str = ""
    nif: str = ""
    base: float = 0.0
    cuota: Optional[float] = None
    neto: float = 0.0
    lineas: int = 0

    @property
    def dia(self) -> Optional[date]:
        return fecha_de(self.fecha)


@dataclass
class Linea:
    estado: str
    programa: Optional[FacturaPrograma] = None
    aplifisa: Optional[FacturaAplifisa] = None
    detalle: str = ""

    @property
    def fecha(self) -> str:
        return (self.programa or self.aplifisa).fecha

    @property
    def tipo(self) -> str:
        return (self.programa or self.aplifisa).tipo


@dataclass
class Cuadre:
    desde: date
    hasta: date
    tipos: Tuple[str, ...]
    lineas: List[Linea] = field(default_factory=list)
    # {(tipo, trimestre): {"programa": [base, cuota, total], "aplifisa": [...]}}
    trimestres: Dict[tuple, dict] = field(default_factory=dict)
    fuera_de_periodo: int = 0       # líneas del listado de otras fechas

    def cuenta(self) -> Dict[str, int]:
        salida = {estado: 0 for estado in ORDEN_ESTADO}
        for linea in self.lineas:
            salida[linea.estado] += 1
        return salida

    @property
    def todo_bien(self) -> bool:
        return all(l.estado == BIEN for l in self.lineas)


# ---------------------------------------------------------------- entradas
def facturas_aplifisa(registro: Registro, tipo: Optional[str] = None) -> List[FacturaAplifisa]:
    """Las líneas del listado agrupadas por factura (mismo número de
    Aplifisa, fecha y proveedor); una línea sin número es una factura."""
    tipo = tipo or registro.tipo or "gasto"
    grupos: Dict[tuple, List[Apunte]] = {}
    for i, a in enumerate(registro.apuntes):
        numero = a.num_factura_proveedor or a.numero
        quien = _normalizar_id(a.nif) or _normalizar_id(a.nombre)
        k = (a.fecha, quien, numero) if numero else ("suelta", i)
        grupos.setdefault(k, []).append(a)
    salida = []
    for lineas in grupos.values():
        a = lineas[0]
        cuotas = [x.cuota for x in lineas if x.cuota is not None]
        neto = sum(x.neto if x.neto is not None else
                   (x.base or 0) + (x.cuota or 0) + (x.recargo or 0) - (x.irpf or 0)
                   for x in lineas)
        salida.append(FacturaAplifisa(
            tipo=tipo, fecha=a.fecha, numero=a.numero,
            num_proveedor=a.num_factura_proveedor, nombre=a.nombre, nif=a.nif,
            base=round(sum(x.base or 0 for x in lineas), 2),
            cuota=round(sum(cuotas), 2) if cuotas else None,
            neto=round(neto, 2), lineas=len(lineas)))
    return salida


def facturas_del_registro(cliente_nif: str, cliente_nombre: str,
                          desde: date, hasta: date) -> List[FacturaPrograma]:
    """Todo lo que el programa tiene guardado del cliente en esos años."""
    salida = []
    for anio in range(desde.year, hasta.year + 1):
        for f in registro_facturas.del_ejercicio(
                cliente_nif, anio, cliente_nombre, solo_exportadas=False):
            pdf = f.get("pdf") or ""
            if not (pdf and os.path.isfile(pdf)) and f.get("origen") \
                    and os.path.isfile(f["origen"]):
                pdf = f["origen"]          # sigue dentro del taco escaneado
            salida.append(FacturaPrograma(
                tipo=registro_facturas.lado(f.get("tipo") or "gasto"),
                fecha=f.get("fecha") or "", num_factura=f.get("num_factura") or "",
                nombre=f.get("nombre") or "", nif=f.get("nif") or "",
                base=float(f.get("base") or 0), cuota=f.get("cuota_iva"),
                total=f.get("total"), pdf=pdf, origen="registro",
                excel=f.get("excel") or "", exportada=f.get("exportada") or ""))
    return salida


def facturas_del_lote(filas: Iterable[Tuple[object, str, int]]) -> List[FacturaPrograma]:
    """El lote abierto: (factura, tipo, fila). Sus líneas de IVA, juntas."""
    por_clave: Dict[str, FacturaPrograma] = {}
    sueltas = []
    for f, tipo, fila in filas:
        if getattr(f, "eliminada", False):
            continue
        k = registro_facturas.clave(f, tipo)
        if k and k in por_clave:
            p = por_clave[k]
            p.base = round(p.base + (f.base_iva or 0), 2)
            if f.cuota_iva is not None:
                p.cuota = round((p.cuota or 0) + f.cuota_iva, 2)
            continue
        p = FacturaPrograma(
            tipo=registro_facturas.lado(tipo), fecha=f.fecha or "",
            num_factura=f.num_factura or "", nombre=f.nombre or "",
            nif=f.nif or "", base=round(f.base_iva or 0, 2), cuota=f.cuota_iva,
            total=f.total_impreso, pdf=f.origen_imagen or "", origen="lote",
            fila=fila)
        if k:
            por_clave[k] = p
        else:
            sueltas.append(p)
    return list(por_clave.values()) + sueltas


def juntar(registro: List[FacturaPrograma],
           lote: List[FacturaPrograma]) -> List[FacturaPrograma]:
    """Lo guardado y el lote abierto, sin contar dos veces la misma factura:
    si ya está en el registro, vale la ficha (y se sabe su fila en el lote)."""
    def k(p):
        return (p.tipo, normaliza_nif(p.nif), _normalizar_id(p.num_factura), p.dia)
    salida = list(registro)
    vistas = {k(p): p for p in registro if p.num_factura and p.dia}
    for p in lote:
        ya = vistas.get(k(p)) if p.num_factura and p.dia else None
        if ya is not None:
            ya.fila = p.fila
            continue
        salida.append(p)
    return salida


# ---------------------------------------------------------------- cuadre
def _cerca(a, b) -> bool:
    return abs(float(a or 0) - float(b or 0)) <= TOLERANCIA


def _mismos_importes(p: FacturaPrograma, a: FacturaAplifisa) -> bool:
    return _cerca(p.base, a.base) and _cerca(p.cuota, a.cuota)


def _parecido(p: FacturaPrograma, a: FacturaAplifisa) -> int:
    """Para elegir entre varias del mismo día e importe."""
    puntos = 0
    if p.nif and a.nif and normaliza_nif(p.nif) == normaliza_nif(a.nif):
        puntos += 4
    if p.num_factura and a.num_proveedor and \
            _normalizar_id(p.num_factura) == _normalizar_id(a.num_proveedor):
        puntos += 4
    if nombres_compatibles(p.nombre, a.nombre):
        puntos += 2
    return puntos


def _mismo_proveedor(p: FacturaPrograma, a: FacturaAplifisa) -> bool:
    if p.nif and a.nif:
        return normaliza_nif(p.nif) == normaliza_nif(a.nif)
    return bool(p.nombre and a.nombre) and nombres_compatibles(p.nombre, a.nombre)


def _euros(valor) -> str:
    texto = f"{float(valor or 0):,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _diferencias(p: FacturaPrograma, a: FacturaAplifisa) -> str:
    partes = []
    if p.dia != a.dia:
        partes.append(f"fecha: programa {p.fecha}, Aplifisa {a.fecha}")
    if not _cerca(p.base, a.base):
        partes.append(f"base: programa {_euros(p.base)}, Aplifisa {_euros(a.base)}")
    if not _cerca(p.cuota, a.cuota):
        partes.append(f"IVA: programa {_euros(p.cuota)}, Aplifisa {_euros(a.cuota)}")
    if p.total is not None and not _cerca(p.total, a.neto):
        partes.append(f"total: programa {_euros(p.total)}, Aplifisa {_euros(a.neto)}")
    return "; ".join(partes)


def _detalle_programa(p: FacturaPrograma) -> str:
    if p.origen == "lote":
        return "En el lote abierto, sin exportar todavía."
    if p.exportada:
        return f"Exportada el {p.exportada}" + (f" en {p.excel}" if p.excel else "") + "."
    return "Guardada en el programa."


def _trimestre(dia: date) -> int:
    return (dia.month - 1) // 3 + 1


def cuadrar(programa: List[FacturaPrograma], aplifisa: List[FacturaAplifisa],
            desde: date, hasta: date, tipos: Iterable[str]) -> Cuadre:
    """Factura a factura, del `desde` al `hasta` y solo de los `tipos` de
    los listados que se han cargado (gastos con compras, ingresos con
    ventas)."""
    tipos = tuple(dict.fromkeys(tipos))
    cuadre = Cuadre(desde=desde, hasta=hasta, tipos=tipos)

    def dentro(x) -> bool:
        return x.tipo in tipos and x.dia is not None and desde <= x.dia <= hasta
    progs = [p for p in programa if dentro(p)]
    apls = [a for a in aplifisa if dentro(a)]
    cuadre.fuera_de_periodo = sum(
        1 for a in aplifisa if a.tipo in tipos and not dentro(a))

    # La misma factura dos veces en el programa (leída con otro NIF, por
    # ejemplo): mismo número, fecha e importes. Cuenta una.
    unicas, vistas = [], {}
    for p in progs:
        k = (p.tipo, _normalizar_id(p.num_factura), p.dia, round(p.base, 2))
        if p.num_factura and k in vistas:
            cuadre.lineas.append(Linea(
                DUPLICADA, programa=p,
                detalle=f"Es la misma factura que otra del programa "
                        f"({vistas[k].nombre or '?'}): se ha escaneado dos veces."))
            continue
        vistas[k] = p
        unicas.append(p)
    progs = unicas

    pendientes = list(apls)
    emparejadas: List[Tuple[FacturaPrograma, FacturaAplifisa]] = []
    sueltas = []

    def elegir(p, condicion):
        candidatos = [a for a in pendientes if a.tipo == p.tipo and condicion(p, a)]
        if not candidatos:
            return None
        mejor = max(candidatos, key=lambda a: _parecido(p, a))
        pendientes.remove(mejor)
        return mejor

    # 1º mismo día e importes; 2º mismo día y total (otro desglose);
    # 3º mismo proveedor e importes con otra fecha; 4º mismo proveedor y
    # día con otros importes.
    pasos = (
        lambda p, a: p.dia == a.dia and _mismos_importes(p, a),
        lambda p, a: p.dia == a.dia and p.total is not None and _cerca(p.total, a.neto),
        lambda p, a: (_mismos_importes(p, a) and _mismo_proveedor(p, a)
                      and abs((p.dia - a.dia).days) <= DIAS_FECHA_DISTINTA),
        lambda p, a: p.dia == a.dia and _mismo_proveedor(p, a),
    )
    restantes = list(progs)
    for paso in pasos:
        quedan = []
        for p in restantes:
            a = elegir(p, paso)
            if a is None:
                quedan.append(p)
            else:
                emparejadas.append((p, a))
        restantes = quedan
    sueltas = restantes

    for p, a in emparejadas:
        diferencias = _diferencias(p, a)
        if diferencias and not (p.dia == a.dia and _mismos_importes(p, a)):
            cuadre.lineas.append(Linea(DISTINTA, p, a, "Cambia " + diferencias + "."))
        elif not p.pdf_guardado:
            cuadre.lineas.append(Linea(
                SIN_PDF, p, a,
                "Registrada en Aplifisa, pero su PDF no está guardado en la "
                "carpeta del cliente: escanéela o recójala."))
        else:
            cuadre.lineas.append(Linea(BIEN, p, a, _detalle_programa(p)))
    for p in sueltas:
        sin_pdf = "" if p.pdf_guardado else " Y su PDF no está guardado."
        cuadre.lineas.append(Linea(
            FALTA_APLIFISA, programa=p,
            detalle=_detalle_programa(p) + " No está registrada en Aplifisa." + sin_pdf))

    # Lo que queda en Aplifisa: o sobra (repetida) o el programa no la tiene.
    registradas = [a for _p, a in emparejadas]
    for a in pendientes:
        gemela = next((b for b in registradas + [x for x in pendientes if x is not a]
                       if b.tipo == a.tipo and b.dia == a.dia
                       and _cerca(b.base, a.base) and _cerca(b.cuota, a.cuota)
                       and (not (a.num_proveedor and b.num_proveedor)
                            or _normalizar_id(a.num_proveedor)
                            == _normalizar_id(b.num_proveedor))
                       and (normaliza_nif(a.nif) == normaliza_nif(b.nif)
                            if a.nif and b.nif else
                            _normalizar_id(a.nombre) == _normalizar_id(b.nombre))),
                      None)
        if gemela is not None and (gemela in registradas or id(gemela) < id(a)):
            cuadre.lineas.append(Linea(
                DUPLICADA, aplifisa=a,
                detalle="En Aplifisa está dos veces (mismo proveedor, fecha e "
                        "importes): sobra una."))
        else:
            cuadre.lineas.append(Linea(
                FALTA_PROGRAMA, aplifisa=a,
                detalle="Registrada en Aplifisa, pero el programa no la tiene "
                        "guardada: búsquela y escanéela."))

    # Totales por trimestre: programa (sin las duplicadas) frente a Aplifisa.
    for p in progs:
        _sumar(cuadre.trimestres, p.tipo, _trimestre(p.dia), "programa",
               p.base, p.cuota, p.total if p.total is not None else p.base + (p.cuota or 0))
    for a in apls:
        _sumar(cuadre.trimestres, a.tipo, _trimestre(a.dia), "aplifisa",
               a.base, a.cuota, a.neto)
    cuadre.lineas.sort(key=lambda l: (ORDEN_ESTADO.index(l.estado), l.tipo,
                                      fecha_de(l.fecha) or date.min))
    return cuadre


def _sumar(tabla, tipo, trimestre, lado, base, cuota, total) -> None:
    celda = tabla.setdefault((tipo, trimestre), {
        "programa": [0.0, 0.0, 0.0, 0], "aplifisa": [0.0, 0.0, 0.0, 0]})[lado]
    celda[0] = round(celda[0] + float(base or 0), 2)
    celda[1] = round(celda[1] + float(cuota or 0), 2)
    celda[2] = round(celda[2] + float(total or 0), 2)
    celda[3] += 1


def periodo_de_listados(registros: Iterable[Registro]) -> Tuple[Optional[date], Optional[date]]:
    """El periodo de los listados: del primer día del mes de su primera
    factura al último del mes de la última (el listado es lo que se quiere
    comprobar; la ventana deja corregirlo)."""
    periodos = [r.periodo for r in registros if r.periodo[0]]
    if not periodos:
        return None, None
    return (min(ini for ini, _fin in periodos), max(fin for _ini, fin in periodos))


def clientes_guardados() -> List[Tuple[str, str]]:
    """(NIF, nombre) de los clientes con facturas en el registro."""
    return registro_facturas.clientes()
