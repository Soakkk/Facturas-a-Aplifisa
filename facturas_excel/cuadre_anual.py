"""El cuadre con Aplifisa de lo guardado: el listado de Aplifisa del periodo
que se quiera frente a todo lo que el programa tiene en PDF del cliente.

El programa guarda una ficha de cada factura que sale de él (registro de
facturas) con su PDF en la carpeta del cliente. El listado de Aplifisa es la
verdad de lo registrado. Cruzándolos sale, factura a factura:

  - bien:            está en los dos y su PDF está guardado;
  - falta_aplifisa:  el programa la tiene (de ese periodo) y en Aplifisa no
                     está registrada;
  - falta_programa:  está en Aplifisa y el programa no la tiene guardada
                     (no hay PDF: hay que buscarla y escanearla);
  - sin_pdf:         registrada en los dos, pero su PDF no está en su sitio;
  - distinta:        es la misma factura (mismo número), pero cambia la
                     fecha o un importe;
  - duplicada:       la misma factura dos veces en Aplifisa (mismo número,
                     fecha e importes): sobra una.

Reglas para no engañar nunca con un «todo bien»:
  - todas las líneas del listado se comprueban, sean de la fecha que sean;
    el periodo solo dice qué facturas guardadas se reclaman como «falta en
    Aplifisa»;
  - dos facturas con distinto número o NIF no se emparejan, y dos que no se
    parecen en nada tampoco: salen las dos como «falta», con una pista de
    cuál podría ser la otra;
  - si el listado no se ha leído entero, o falta algo por comprobar, no se
    dice «todo bien».

Sin IA ni coste: todo sale de lo ya leído y del texto del listado.
"""

from __future__ import annotations

import calendar
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from . import registro_facturas
from .procesar import _palabras_que_cuentan, nombres_compatibles, normaliza_nif
from .registro import Registro, _normalizar_id
from .validacion import fecha_de, validar_nif

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
    pdf: str = ""                  # su PDF en el archivo (o el taco escaneado)
    en_taco: bool = False          # sin PDF propio: sigue dentro del taco
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
    numero: str = ""               # el de la columna del listado
    num_proveedor: str = ""        # el de la factura (listado con columnas)
    nombre: str = ""
    nif: str = ""
    base: float = 0.0
    cuota: Optional[float] = None
    neto: float = 0.0
    lineas: int = 0
    orden: int = 0                 # posición en el listado
    formato: str = ""

    @property
    def dia(self) -> Optional[date]:
        return fecha_de(self.fecha)

    @property
    def numero_real(self) -> str:
        """El número de la factura cuando se sabe seguro: el del proveedor
        (listado de facturas recibidas) o el de las facturas emitidas."""
        if self.num_proveedor:
            return self.num_proveedor
        return self.numero if self.tipo == "venta" and self.formato == "columnas" else ""

    @property
    def numero_posible(self) -> str:
        """En el listado desglosado de ventas el número puede ser el de la
        factura o uno de Aplifisa: suma si coincide, no veta si no."""
        return self.numero if self.tipo == "venta" and not self.numero_real else ""


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
    periodos: Dict[str, Tuple[date, date]]
    lineas: List[Linea] = field(default_factory=list)
    # {(tipo, año, trimestre): {"programa": [base, cuota, total, n], "aplifisa": [...]}}
    trimestres: Dict[tuple, dict] = field(default_factory=dict)
    fuera_de_periodo: int = 0       # líneas del listado de otras fechas (comprobadas)
    fuera_programa: int = 0         # facturas guardadas de otras fechas
    sin_fecha: int = 0              # del programa, sin fecha legible
    avisos: List[str] = field(default_factory=list)   # lo que impide el «todo bien»
    notas: List[str] = field(default_factory=list)    # para saber, sin impedirlo

    @property
    def tipos(self) -> Tuple[str, ...]:
        return tuple(self.periodos)

    def cuenta(self) -> Dict[str, int]:
        salida = {estado: 0 for estado in ORDEN_ESTADO}
        for linea in self.lineas:
            salida[linea.estado] += 1
        return salida

    @property
    def todo_bien(self) -> bool:
        return (bool(self.lineas) and not self.avisos and not self.sin_fecha
                and all(l.estado == BIEN for l in self.lineas))


# ---------------------------------------------------------------- nombres
def _palabras(nombre) -> set:
    return _palabras_que_cuentan(nombre)


def nombres_parecidos(a, b) -> bool:
    """Comparten una palabra que dice quién es, o una va dentro de otra
    («AQUASERVICE» y «VIVA AQUA SERVICE»)."""
    if nombres_compatibles(a, b):
        return True
    pa, pb = _palabras(a), _palabras(b)
    return any(len(x) >= 4 and len(y) >= 4 and (x in y or y in x)
               for x in pa for y in pb)


def _similitud(a, b) -> float:
    """De 0 a 1: cuánto se parecen dos nombres (para desempatar)."""
    pa, pb = _palabras(a), _palabras(b)
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


# ---------------------------------------------------------------- entradas
def _cerca(a, b) -> bool:
    return abs(float(a or 0) - float(b or 0)) <= TOLERANCIA


def _tipo_iva(base, cuota) -> Optional[float]:
    if not base:
        return None
    return round(float(cuota or 0) / float(base), 3)


def facturas_aplifisa(registro: Registro, tipo: Optional[str] = None) -> List[FacturaAplifisa]:
    """Las líneas del listado agrupadas por factura.

    Con número, las del mismo número (de Aplifisa y del proveedor), fecha y
    proveedor; una línea igual a otra del grupo (misma base e IVA) es otra
    factura: la misma metida dos veces, que así se puede ver. Sin número,
    solo se juntan las seguidas del mismo día y proveedor con distinto tipo
    de IVA (una factura de varios tipos); dos tiques iguales son dos.
    """
    tipo = tipo or registro.tipo or "gasto"
    grupos: List[list] = []
    por_clave: Dict[tuple, list] = {}
    suelto: Optional[list] = None
    for a in registro.apuntes:
        quien = _normalizar_id(a.nif) or _normalizar_id(a.nombre)
        if a.numero or a.num_factura_proveedor:
            suelto = None
            k = (a.fecha, quien, a.numero, a.num_factura_proveedor)
            grupo = por_clave.get(k)
            if grupo is None or any(_cerca(x.base, a.base) and _cerca(x.cuota, a.cuota)
                                    for x in grupo):
                grupo = []
                grupos.append(grupo)
                por_clave[k] = grupo
            grupo.append(a)
        else:
            primera = suelto[0] if suelto else None
            if (suelto is None or primera.fecha != a.fecha
                    or (_normalizar_id(primera.nif) or _normalizar_id(primera.nombre)) != quien
                    or _tipo_iva(a.base, a.cuota) in
                    {_tipo_iva(x.base, x.cuota) for x in suelto}):
                suelto = []
                grupos.append(suelto)
            suelto.append(a)
    salida = []
    for orden, lineas in enumerate(grupos):
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
            neto=round(neto, 2), lineas=len(lineas), orden=orden,
            formato=registro.formato))
    return salida


def facturas_del_registro(cliente_nif: str, cliente_nombre: str,
                          desde: date, hasta: date) -> List[FacturaPrograma]:
    """Todo lo que el programa tiene guardado del cliente en esos años (por
    su NIF y por los nombres con los que algún lote salió sin él)."""
    salida, vistas = [], set()
    claves = registro_facturas.claves_cliente(cliente_nif, cliente_nombre)
    for anio in range(desde.year, hasta.year + 1):
        for nif, nombre in claves:
            for f in registro_facturas.del_ejercicio(
                    nif, anio, nombre, solo_exportadas=False):
                if f["id"] in vistas:
                    continue
                vistas.add(f["id"])
                pdf, en_taco = f.get("pdf") or "", False
                if not pdf and f.get("origen"):
                    # Nunca tuvo PDF propio: sigue dentro del taco escaneado.
                    pdf, en_taco = f["origen"], True
                salida.append(FacturaPrograma(
                    tipo=registro_facturas.lado(f.get("tipo") or "gasto"),
                    fecha=f.get("fecha") or "", num_factura=f.get("num_factura") or "",
                    nombre=f.get("nombre") or "", nif=f.get("nif") or "",
                    base=float(f.get("base") or 0), cuota=f.get("cuota_iva"),
                    total=f.get("total"), pdf=pdf, en_taco=en_taco,
                    origen="registro", excel=f.get("excel") or "",
                    exportada=f.get("exportada") or ""))
    return salida


def facturas_del_lote(filas: Iterable[Tuple[object, str, int]]) -> List[FacturaPrograma]:
    """El lote abierto: (factura, tipo, fila). Sus líneas de IVA, juntas
    (como en el registro). Las copias repetidas las quita quien llama."""
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
            total=f.total_impreso, pdf=f.origen_imagen or "", en_taco=True,
            origen="lote", fila=fila)
        if k:
            por_clave[k] = p
        else:
            sueltas.append(p)
    return list(por_clave.values()) + sueltas


def _nif_valido(nif) -> str:
    n = normaliza_nif(nif)
    return n if n and validar_nif(n) else ""


def _nifs_distintos(a, b) -> bool:
    na, nb = _nif_valido(a), _nif_valido(b)
    return bool(na and nb and na != nb)


def juntar(registro: List[FacturaPrograma],
           lote: List[FacturaPrograma]) -> List[FacturaPrograma]:
    """Lo guardado y el lote abierto, sin contar dos veces la misma factura.

    Si ya está en el registro vale la ficha (lo que salió hacia Aplifisa) y
    se sabe su fila en el lote. Dos NIF válidos distintos son dos facturas
    (dos proveedores con el mismo número, o un NIF corregido después: eso
    se avisa en el cuadre)."""
    salida = list(registro)
    for p in lote:
        ya = next((r for r in registro
                   if r.tipo == p.tipo and r.dia and r.dia == p.dia
                   and p.num_factura and _mismo_numero(r.num_factura, p.num_factura)
                   and not _nifs_distintos(r.nif, p.nif)
                   and (normaliza_nif(r.nif) == normaliza_nif(p.nif)
                        or _cerca(r.base, p.base))), None)
        if ya is not None:
            if ya.fila is None:
                ya.fila = p.fila
            continue
        salida.append(p)
    return salida


# ---------------------------------------------------------------- números
def _partes_numero(numero: str) -> Tuple[str, List[str]]:
    """(letras del principio, grupos de cifras sin ceros delante):
    «F-0012» → ("F", ["12"]); «2026/0012» → ("", ["2026", "12"])."""
    letras = re.match(r"[A-Z]*", _normalizar_id(numero)).group(0)
    grupos = [(g.lstrip("0") or "0") for g in re.findall(r"\d+", str(numero or ""))]
    return letras, grupos


def _mismo_numero(a: str, b: str) -> bool:
    """La misma factura escrita de dos formas: «F-0012», «F12», «12»,
    «2026/0012». «A-0123» y «B-0123», o «1234» y «11234», no."""
    na, nb = _normalizar_id(a), _normalizar_id(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    letras_a, grupos_a = _partes_numero(a)
    letras_b, grupos_b = _partes_numero(b)
    if not grupos_a or not grupos_b or grupos_a[-1] != grupos_b[-1]:
        return False
    # «F-2026-0001» y «F-2025-0001» son dos: con serie en los dos, la misma.
    if len(grupos_a) > 1 and len(grupos_b) > 1 and grupos_a != grupos_b:
        return False
    return not (letras_a and letras_b and letras_a != letras_b)


def _numeros_distintos(a: str, b: str) -> bool:
    """Dos números que seguro son de facturas distintas (no solo escritos
    de otra forma)."""
    if not _normalizar_id(a) or not _normalizar_id(b):
        return False
    return not _mismo_numero(a, b)


# ---------------------------------------------------------------- cuadre
def _mismos_importes(p: FacturaPrograma, a: FacturaAplifisa) -> bool:
    return _cerca(p.base, a.base) and _cerca(p.cuota, a.cuota)


def _relacion(p: FacturaPrograma, a: FacturaAplifisa) -> Optional[dict]:
    """Qué une a las dos (o None si no pueden ser la misma factura: dos
    números de factura o dos NIF que no son el mismo)."""
    if p.num_factura and a.numero_real and _numeros_distintos(p.num_factura, a.numero_real):
        return None
    if _nifs_distintos(p.nif, a.nif):
        return None
    numero = bool(p.num_factura and (
        (a.numero_real and _mismo_numero(p.num_factura, a.numero_real))
        or (a.numero_posible and _mismo_numero(p.num_factura, a.numero_posible))))
    return {
        "numero": numero,
        "nif": bool(_nif_valido(p.nif) and _nif_valido(a.nif)),
        "nombre": nombres_parecidos(p.nombre, a.nombre),
        "similitud": _similitud(p.nombre, a.nombre),
        "dias": abs((p.dia - a.dia).days),
    }


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


def _nota_pdf(p: FacturaPrograma) -> str:
    if not p.pdf_guardado:
        return " Y su PDF no está guardado."
    if p.en_taco and p.origen == "registro":
        return " Su PDF está dentro del taco escaneado (sin separar)."
    return ""


def _trimestre(dia: date) -> int:
    return (dia.month - 1) // 3 + 1


# Niveles de emparejamiento, del más seguro al menos: (condición, misma
# fecha). En cada uno, de todas las parejas posibles se cogen antes las
# mejores (número, NIF, nombre más parecido, menos días), no la primera.
def _exacta(p, a, r):
    return r["dias"] == 0 and _mismos_importes(p, a) and (
        r["nombre"] or r["numero"] or r["nif"])


def _mismo_total(p, a, r):
    return (r["dias"] == 0 and p.total is not None and _cerca(p.total, a.neto)
            and (r["nombre"] or r["numero"] or r["nif"]))


def _misma_factura_otra_fecha(p, a, r):
    return r["numero"] and _mismos_importes(p, a) and r["dias"] <= DIAS_FECHA_DISTINTA


def _misma_factura_otros_importes(p, a, r):
    return r["numero"] and r["dias"] == 0


NIVELES = ((_exacta, True), (_mismo_total, True),
           (_misma_factura_otra_fecha, False), (_misma_factura_otros_importes, True))


def _emparejar(progs: List[FacturaPrograma], apls: List[FacturaAplifisa]):
    """[(p, a, nivel)] y lo que queda sin pareja de cada lado."""
    libres_p = {i: p for i, p in enumerate(progs)}
    libres_a = {j: a for j, a in enumerate(apls)}
    # Para no comparar todas con todas: por día y por base (en euros).
    por_dia, por_base = defaultdict(list), defaultdict(list)
    for j, a in enumerate(apls):
        por_dia[(a.tipo, a.dia)].append(j)
        por_base[(a.tipo, round(a.base))].append(j)
    parejas = []
    for nivel, (condicion, misma_fecha) in enumerate(NIVELES):
        candidatas = []
        for i, p in libres_p.items():
            if misma_fecha:
                cerca = por_dia.get((p.tipo, p.dia), ())
            else:
                cerca = [j for k in (-1, 0, 1)
                         for j in por_base.get((p.tipo, round(p.base) + k), ())]
            for j in cerca:
                if j not in libres_a:
                    continue
                a = libres_a[j]
                r = _relacion(p, a)
                if r is None or not condicion(p, a, r):
                    continue
                puntos = (8 * r["numero"] + 4 * r["nif"] + 2 * r["nombre"]
                          + r["similitud"])
                candidatas.append((-puntos, r["dias"], i, j))
        for _puntos, _dias, i, j in sorted(candidatas):
            if i in libres_p and j in libres_a:
                parejas.append((libres_p.pop(i), libres_a.pop(j), nivel))
    return parejas, list(libres_p.values()), list(libres_a.values())


def _que_cambia(p: FacturaPrograma, a: FacturaAplifisa) -> str:
    cambios = []
    if p.dia != a.dia:
        cambios.append("la fecha")
    if p.num_factura and a.numero_real and _numeros_distintos(p.num_factura, a.numero_real):
        cambios.append(f"el nº de factura ({a.numero_real})")
    if _nifs_distintos(p.nif, a.nif):
        cambios.append(f"el NIF ({a.nif})")
    if not nombres_parecidos(p.nombre, a.nombre):
        cambios.append(f"el nombre («{a.nombre}»)")
    return ", ".join(cambios) or "algún dato"


def _pista(p: FacturaPrograma, a: FacturaAplifisa) -> bool:
    """Mismos importes en una fecha cercana: puede ser la misma con un dato
    cambiado. Solo para avisar, nunca para darla por buena."""
    return (p.tipo == a.tipo and _mismos_importes(p, a) and p.dia and a.dia
            and abs((p.dia - a.dia).days) <= DIAS_FECHA_DISTINTA)


def cuadrar(programa: List[FacturaPrograma], aplifisa: List[FacturaAplifisa],
            periodos: Dict[str, Tuple[date, date]]) -> Cuadre:
    """Factura a factura. `periodos`: {tipo: (desde, hasta)} de cada listado
    cargado (gastos con compras, ingresos con ventas). Todas las líneas del
    listado se comprueban; el periodo dice qué guardadas se reclaman."""
    cuadre = Cuadre(periodos=dict(periodos))
    tipos = tuple(periodos)

    def en_periodo(x) -> bool:
        desde, hasta = periodos[x.tipo]
        return desde <= x.dia <= hasta
    del_tipo = [p for p in programa if p.tipo in tipos]
    cuadre.sin_fecha = sum(1 for p in del_tipo if p.dia is None)
    progs = [p for p in del_tipo if p.dia is not None]
    apls = [a for a in aplifisa if a.tipo in tipos and a.dia is not None]
    cuadre.fuera_de_periodo = sum(1 for a in apls if not en_periodo(a))

    # La misma factura dos veces en el programa (leída en dos lotes): mismo
    # número, fecha, importes y proveedor. Con dos NIF válidos distintos son
    # dos facturas (dos proveedores con el mismo número): se cuadran las dos.
    unicas: List[FacturaPrograma] = []
    for p in progs:
        gemela = next((q for q in unicas
                       if q.tipo == p.tipo and p.num_factura and q.dia == p.dia
                       and _mismo_numero(q.num_factura, p.num_factura)
                       and _cerca(q.base, p.base) and _cerca(q.cuota, p.cuota)
                       and not _nifs_distintos(q.nif, p.nif)
                       and (normaliza_nif(q.nif) == normaliza_nif(p.nif)
                            or nombres_parecidos(q.nombre, p.nombre))), None)
        if gemela is not None:
            if en_periodo(p):
                cuadre.lineas.append(Linea(
                    DUPLICADA, programa=p,
                    detalle=f"Es la misma factura que otra del programa "
                            f"({gemela.nombre or '?'}): se guardó dos veces."))
            continue
        unicas.append(p)
    progs = unicas

    parejas, solo_programa, solo_aplifisa = _emparejar(progs, apls)
    emparejadas = []
    for p, a, nivel in parejas:
        emparejadas.append(p)
        if nivel == 0 and p.pdf_guardado:
            cuadre.lineas.append(Linea(BIEN, p, a, _detalle_programa(p) + _nota_pdf(p)))
        elif nivel == 0:
            cuadre.lineas.append(Linea(
                SIN_PDF, p, a,
                "Registrada en Aplifisa, pero su PDF no está guardado en la "
                "carpeta del cliente: escanéela o recójala."))
        else:
            cuadre.lineas.append(Linea(
                DISTINTA, p, a, "Es la misma factura, pero cambia "
                + _diferencias(p, a) + "." + _nota_pdf(p)))

    # Sin pareja segura: se dicen como «falta», con una pista si hay una del
    # otro lado con los mismos importes (puede ser la misma con la fecha, el
    # número, el NIF o el nombre cambiados: que lo mire una persona).
    for p in solo_programa:
        if not en_periodo(p):
            cuadre.fuera_programa += 1
            continue
        pista = ""
        a = min((a for a in solo_aplifisa if _pista(p, a)),
                key=lambda a: (abs((p.dia - a.dia).days), -_similitud(p.nombre, a.nombre)),
                default=None)
        if a is not None:
            pista = (f" ¿Es la de Aplifisa del {a.fecha} ({a.nombre}) con los "
                     f"mismos importes? Cambia {_que_cambia(p, a)}.")
        gemela = next((q for q in emparejadas if q.tipo == p.tipo and q.dia == p.dia
                       and p.num_factura and _mismo_numero(q.num_factura, p.num_factura)
                       and _cerca(q.base, p.base) and _nifs_distintos(q.nif, p.nif)), None)
        if gemela is not None:
            pista += (f" Es igual que la de {gemela.nombre} (NIF {gemela.nif}) salvo "
                      "el NIF: si es la misma, se guardó dos veces con otro NIF.")
        cuadre.lineas.append(Linea(
            FALTA_APLIFISA, programa=p,
            detalle=_detalle_programa(p) + " No está registrada en Aplifisa."
            + _nota_pdf(p) + pista))

    # Lo que queda en Aplifisa: repetida de verdad (mismo número de factura,
    # fecha e importes que otra del listado) o el programa no la tiene.
    for a in sorted(solo_aplifisa, key=lambda x: x.orden):
        iguales = [b for b in apls if b is not a and b.tipo == a.tipo
                   and b.dia == a.dia and _cerca(b.base, a.base)
                   and _cerca(b.cuota, a.cuota)
                   and _normalizar_id(b.nif or b.nombre) == _normalizar_id(a.nif or a.nombre)]
        if a.numero_real and any(
                b.orden < a.orden and _mismo_numero(b.numero_real, a.numero_real)
                for b in iguales):
            cuadre.lineas.append(Linea(
                DUPLICADA, aplifisa=a,
                detalle=f"En Aplifisa está dos veces la factura {a.numero_real} "
                        "(mismo número, fecha e importes): sobra una."))
            continue
        aviso = ""
        if any(b.orden < a.orden and not (a.numero_real and b.numero_real)
               for b in iguales):
            aviso = (" Hay otra igual en el listado el mismo día: si es la misma "
                     "metida dos veces, sobra una.")
        p = min((p for p in solo_programa if _pista(p, a)),
                key=lambda p: (abs((p.dia - a.dia).days), -_similitud(p.nombre, a.nombre)),
                default=None)
        if p is not None:
            aviso += (f" ¿Es la del programa del {p.fecha} ({p.nombre}) con los "
                      f"mismos importes? Cambia {_que_cambia(p, a)}.")
        fuera = "" if en_periodo(a) else " (Es de fuera del periodo que ha puesto.)"
        cuadre.lineas.append(Linea(
            FALTA_PROGRAMA, aplifisa=a,
            detalle="Registrada en Aplifisa, pero el programa no la tiene "
                    "guardada: búsquela y escanéela." + aviso + fuera))

    # Totales por trimestre: lo guardado del periodo (y lo emparejado)
    # frente a todo el listado.
    contadas = [p for p in progs if en_periodo(p) or p in emparejadas]
    for p in contadas:
        _sumar(cuadre.trimestres, (p.tipo, p.dia.year, _trimestre(p.dia)), "programa",
               p.base, p.cuota, p.total if p.total is not None else p.base + (p.cuota or 0))
    for a in apls:
        _sumar(cuadre.trimestres, (a.tipo, a.dia.year, _trimestre(a.dia)), "aplifisa",
               a.base, a.cuota, a.neto)
    cuadre.lineas.sort(key=lambda l: (ORDEN_ESTADO.index(l.estado), l.tipo,
                                      fecha_de(l.fecha) or date.min))
    return cuadre


def _sumar(tabla, clave, lado, base, cuota, total) -> None:
    celda = tabla.setdefault(clave, {
        "programa": [0.0, 0.0, 0.0, 0], "aplifisa": [0.0, 0.0, 0.0, 0]})[lado]
    celda[0] = round(celda[0] + float(base or 0), 2)
    celda[1] = round(celda[1] + float(cuota or 0), 2)
    celda[2] = round(celda[2] + float(total or 0), 2)
    celda[3] += 1


def avisos_de_listado(registro: Registro) -> List[str]:
    """Lo que hace que un listado no sirva para decir «todo bien»."""
    clase = "compras" if registro.tipo != "venta" else "ventas"
    avisos = []
    if not registro.bien_leido:
        avisos.append(f"El listado de {clase} no se ha leído entero (sus "
                      "totales no cuadran: " + "; ".join(registro.diferencias_totales)
                      + "). Puede faltar alguna línea por comprobar.")
    return avisos


def notas_de_listado(registro: Registro) -> List[str]:
    if registro.tipo != "venta" and registro.apuntes and not any(
            a.num_factura_proveedor for a in registro.apuntes):
        return ["El listado de compras no trae el número de factura del "
                "proveedor: dos facturas del mismo día, proveedor e importe no se "
                "pueden distinguir. Para un cuadre seguro, saque de Aplifisa el "
                "listado de facturas recibidas (con su número)."]
    return []


def periodo_de_listado(registro: Registro) -> Tuple[Optional[date], Optional[date]]:
    """El periodo que se pidió a Aplifisa, por trimestres enteros: del
    primer día del trimestre de su primera factura al último del de la
    última (si falta el último mes, lo guardado de ese mes sale como
    «falta»). Una o dos sueltas de otro año (menos del 10 %) no lo
    arrastran. La ventana deja corregirlo."""
    fechas = sorted(d for d in (fecha_de(a.fecha) for a in registro.apuntes) if d)
    if not fechas:
        return None, None
    por_anio = Counter(d.year for d in fechas)
    raros = {anio for anio, n in por_anio.items()
             if n <= 2 and n < 0.1 * len(fechas) and len(por_anio) > 1}
    fechas = [d for d in fechas if d.year not in raros] or fechas
    primera, ultima = fechas[0], fechas[-1]
    inicio = date(primera.year, 3 * (_trimestre(primera) - 1) + 1, 1)
    mes_fin = 3 * _trimestre(ultima)
    return inicio, date(ultima.year, mes_fin, calendar.monthrange(ultima.year, mes_fin)[1])


def periodo_de_listados(registros: Iterable[Registro]) -> Tuple[Optional[date], Optional[date]]:
    """El de varios listados juntos (del primero al último)."""
    periodos = [p for p in (periodo_de_listado(r) for r in registros) if p[0]]
    if not periodos:
        return None, None
    return min(p[0] for p in periodos), max(p[1] for p in periodos)


def anios_a_cargar(periodos: Dict[str, Tuple[date, date]],
                   aplifisa: List[FacturaAplifisa]) -> Tuple[date, date]:
    """Los años del registro que hay que leer: los del periodo y los de
    todas las líneas del listado (todas se comprueban)."""
    dias = [d for desde, hasta in periodos.values() for d in (desde, hasta)]
    dias += [a.dia for a in aplifisa if a.dia]
    return min(dias), max(dias)


def clientes_guardados() -> List[Tuple[str, str]]:
    """(NIF, nombre) de los clientes con facturas en el registro."""
    return registro_facturas.clientes()


def mismo_cliente(a: Tuple[str, str], b: Tuple[str, str]) -> bool:
    nif_a, nombre_a = a
    nif_b, nombre_b = b
    if normaliza_nif(nif_a) and normaliza_nif(nif_b):
        return normaliza_nif(nif_a) == normaliza_nif(nif_b)
    return bool(nombre_a and nombre_b) and \
        str(nombre_a).strip().upper() == str(nombre_b).strip().upper()
