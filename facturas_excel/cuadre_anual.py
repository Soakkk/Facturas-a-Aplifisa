"""El cuadre con Aplifisa de lo guardado: el listado de Aplifisa del periodo
que se quiera frente a todo lo que el programa tiene en PDF del cliente.

El programa guarda una ficha de cada factura que sale de él (registro de
facturas) con su PDF en la carpeta del cliente. El listado de Aplifisa del
mismo periodo es la verdad de lo registrado. Cruzándolos sale, factura a
factura:

  - bien:            está en los dos y su PDF está guardado;
  - falta_aplifisa:  el programa la tiene y en Aplifisa no está registrada;
  - falta_programa:  está en Aplifisa y el programa no la tiene guardada
                     (no hay PDF: hay que buscarla y escanearla);
  - sin_pdf:         registrada en los dos, pero su PDF no está en su sitio;
  - distinta:        es la misma factura, pero cambia la fecha, un importe o
                     el nombre;
  - duplicada:       la misma factura dos veces en Aplifisa (mismo número,
                     fecha e importes): sobra una.

Antes que dar por buena una pareja dudosa se dejan las dos a la vista: dos
facturas con distinto número o NIF nunca se emparejan, y lo que no tiene
pareja segura sale como «falta» con una pista de cuál podría ser.

Así se puede comprobar a mitad de año (6 o 9 meses) sin esperar al cierre.
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
from .procesar import nombres_compatibles, normaliza_nif
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
    numero: str = ""               # el que pone Aplifisa al registrar (compras)
    num_proveedor: str = ""
    nombre: str = ""
    nif: str = ""
    base: float = 0.0
    cuota: Optional[float] = None
    neto: float = 0.0
    lineas: int = 0
    orden: int = 0                 # posición en el listado

    @property
    def dia(self) -> Optional[date]:
        return fecha_de(self.fecha)

    @property
    def numero_real(self) -> str:
        """El número de la factura: el del proveedor en compras; en ventas
        es el número que lleva el propio listado."""
        if self.num_proveedor:
            return self.num_proveedor
        return self.numero if self.tipo == "venta" else ""


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
    # {(tipo, año, trimestre): {"programa": [base, cuota, total, n], "aplifisa": [...]}}
    trimestres: Dict[tuple, dict] = field(default_factory=dict)
    fuera_de_periodo: int = 0       # líneas del listado de otras fechas
    fuera_programa: int = 0         # facturas guardadas de otras fechas
    sin_fecha: int = 0              # del programa, sin fecha legible

    def cuenta(self) -> Dict[str, int]:
        salida = {estado: 0 for estado in ORDEN_ESTADO}
        for linea in self.lineas:
            salida[linea.estado] += 1
        return salida

    @property
    def todo_bien(self) -> bool:
        return bool(self.lineas) and all(l.estado == BIEN for l in self.lineas)


# ---------------------------------------------------------------- entradas
def _repetida(lineas, a) -> bool:
    return any(_cerca(x.base, a.base) and _cerca(x.cuota, a.cuota) for x in lineas)


def facturas_aplifisa(registro: Registro, tipo: Optional[str] = None) -> List[FacturaAplifisa]:
    """Las líneas del listado agrupadas por factura.

    Con número, las del mismo número (de Aplifisa y del proveedor), fecha y
    proveedor; sin número, las seguidas del mismo día y proveedor. Una línea
    igual a otra del grupo (misma base e IVA) es otra factura: la misma
    metida dos veces, que así se puede ver.
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
            if grupo is None or _repetida(grupo, a):
                grupo = []
                grupos.append(grupo)
                por_clave[k] = grupo
            grupo.append(a)
        else:
            primera = suelto[0] if suelto else None
            if (suelto is None or primera.fecha != a.fecha
                    or (_normalizar_id(primera.nif) or _normalizar_id(primera.nombre)) != quien
                    or _repetida(suelto, a)):
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
            neto=round(neto, 2), lineas=len(lineas), orden=orden))
    return salida


def facturas_del_registro(cliente_nif: str, cliente_nombre: str,
                          desde: date, hasta: date) -> List[FacturaPrograma]:
    """Todo lo que el programa tiene guardado del cliente en esos años (con
    su NIF y, por si algún lote salió sin él, con su nombre)."""
    salida, vistas = [], set()
    claves = [(cliente_nif, cliente_nombre)]
    if cliente_nif and cliente_nombre:
        claves.append(("", cliente_nombre))
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
    (una línea repetida es una copia, no otra línea de la factura)."""
    por_clave: Dict[str, Tuple[FacturaPrograma, list]] = {}
    sueltas = []
    for f, tipo, fila in filas:
        if getattr(f, "eliminada", False):
            continue
        k = registro_facturas.clave(f, tipo)
        linea = (round(f.base_iva or 0, 2), round(f.cuota_iva or 0, 2))
        if k and k in por_clave:
            p, lineas = por_clave[k]
            if linea in lineas:
                continue
            lineas.append(linea)
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
            por_clave[k] = (p, [linea])
        else:
            sueltas.append(p)
    return [p for p, _ in por_clave.values()] + sueltas


def juntar(registro: List[FacturaPrograma],
           lote: List[FacturaPrograma]) -> List[FacturaPrograma]:
    """Lo guardado y el lote abierto, sin contar dos veces la misma factura.

    Si ya está en el registro vale la ficha (lo que salió hacia Aplifisa) y
    se sabe su fila en el lote. Se reconoce por número y fecha aunque luego
    se haya corregido el NIF en el lote."""
    salida = list(registro)
    for p in lote:
        ya = next((r for r in registro
                   if r.tipo == p.tipo and r.dia and r.dia == p.dia
                   and p.num_factura and _mismo_numero(r.num_factura, p.num_factura)
                   and (normaliza_nif(r.nif) == normaliza_nif(p.nif)
                        or _cerca(r.base, p.base))), None)
        if ya is not None:
            if ya.fila is None:
                ya.fila = p.fila
            continue
        salida.append(p)
    return salida


# ---------------------------------------------------------------- cuadre
def _cerca(a, b) -> bool:
    return abs(float(a or 0) - float(b or 0)) <= TOLERANCIA


def _digitos(numero: str) -> str:
    return re.sub(r"\D", "", numero or "").lstrip("0")


def _mismo_numero(a: str, b: str) -> bool:
    """«F-0012» y «F12»; «2026/0012» y «0012» (series con el año delante)."""
    na, nb = _normalizar_id(a), _normalizar_id(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    corto, largo = sorted((na, nb), key=len)
    if len(corto) >= 4 and largo.endswith(corto):
        return True
    da, db = _digitos(a), _digitos(b)
    return bool(da) and da == db and len(da) >= 3


def _mismos_importes(p: FacturaPrograma, a: FacturaAplifisa) -> bool:
    return _cerca(p.base, a.base) and _cerca(p.cuota, a.cuota)


def _nif_valido(nif) -> str:
    n = normaliza_nif(nif)
    return n if n and validar_nif(n) else ""


def _relacion(p: FacturaPrograma, a: FacturaAplifisa) -> Optional[dict]:
    """Qué une a las dos (o None si no pueden ser la misma factura: dos
    números de factura o dos NIF que no son el mismo)."""
    numero_a = a.numero_real
    if p.num_factura and numero_a and not _mismo_numero(p.num_factura, numero_a):
        return None
    nif_p, nif_a = _nif_valido(p.nif), _nif_valido(a.nif)
    if nif_p and nif_a and nif_p != nif_a:
        return None
    return {
        "numero": bool(p.num_factura and numero_a),
        "nif": bool(nif_p and nif_a),
        "nombre": nombres_compatibles(p.nombre, a.nombre),
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
    if not nombres_compatibles(p.nombre, a.nombre):
        partes.append(f"nombre: programa «{p.nombre}», Aplifisa «{a.nombre}»")
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


# Niveles de emparejamiento, del más seguro al menos. En cada uno, de todas
# las parejas posibles se cogen antes las mejores (no la primera que salga).
def _exacta(p, a, r):
    return r["dias"] == 0 and _mismos_importes(p, a) and (
        r["nombre"] or r["numero"] or r["nif"])


def _exacta_otro_nombre(p, a, r):
    return r["dias"] == 0 and _mismos_importes(p, a)


def _mismo_total(p, a, r):
    return (r["dias"] == 0 and p.total is not None and _cerca(p.total, a.neto)
            and (r["nombre"] or r["numero"] or r["nif"]))


def _misma_factura_otra_fecha(p, a, r):
    return r["numero"] and _mismos_importes(p, a) and r["dias"] <= DIAS_FECHA_DISTINTA


def _misma_factura_otros_importes(p, a, r):
    return r["numero"] and r["dias"] == 0


NIVELES = (_exacta, _exacta_otro_nombre, _mismo_total,
           _misma_factura_otra_fecha, _misma_factura_otros_importes)


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
    for nivel, condicion in enumerate(NIVELES):
        candidatas = []
        for i, p in libres_p.items():
            if nivel == 3:
                cerca = [j for k in (-1, 0, 1)
                         for j in por_base.get((p.tipo, round(p.base) + k), ())]
            else:
                cerca = por_dia.get((p.tipo, p.dia), ())
            for j in cerca:
                if j not in libres_a:
                    continue
                a = libres_a[j]
                r = _relacion(p, a)
                if r is None or not condicion(p, a, r):
                    continue
                puntos = 8 * r["numero"] + 4 * r["nif"] + 2 * r["nombre"]
                candidatas.append((-puntos, r["dias"], i, j))
        for _puntos, _dias, i, j in sorted(candidatas):
            if i in libres_p and j in libres_a:
                parejas.append((libres_p.pop(i), libres_a.pop(j), nivel))
    return parejas, list(libres_p.values()), list(libres_a.values())


def cuadrar(programa: List[FacturaPrograma], aplifisa: List[FacturaAplifisa],
            desde: date, hasta: date, tipos: Iterable[str]) -> Cuadre:
    """Factura a factura, del `desde` al `hasta` y solo de los `tipos` de
    los listados que se han cargado (gastos con compras, ingresos con
    ventas)."""
    tipos = tuple(dict.fromkeys(tipos))
    cuadre = Cuadre(desde=desde, hasta=hasta, tipos=tipos)

    def dentro(x) -> bool:
        return x.dia is not None and desde <= x.dia <= hasta
    del_tipo = [p for p in programa if p.tipo in tipos]
    progs = [p for p in del_tipo if dentro(p)]
    cuadre.sin_fecha = sum(1 for p in del_tipo if p.dia is None)
    cuadre.fuera_programa = len(del_tipo) - len(progs) - cuadre.sin_fecha
    apls = [a for a in aplifisa if a.tipo in tipos and dentro(a)]
    cuadre.fuera_de_periodo = sum(
        1 for a in aplifisa if a.tipo in tipos and not dentro(a))

    # La misma factura dos veces en el programa (leída con otro NIF en otro
    # lote, por ejemplo): mismo número, fecha, importes y proveedor.
    unicas: List[FacturaPrograma] = []
    for p in progs:
        gemela = next((q for q in unicas
                       if q.tipo == p.tipo and p.num_factura and q.dia == p.dia
                       and _mismo_numero(q.num_factura, p.num_factura)
                       and _cerca(q.base, p.base) and _cerca(q.cuota, p.cuota)
                       and (normaliza_nif(q.nif) == normaliza_nif(p.nif)
                            or nombres_compatibles(q.nombre, p.nombre))), None)
        if gemela is not None:
            cuadre.lineas.append(Linea(
                DUPLICADA, programa=p,
                detalle=f"Es la misma factura que otra del programa "
                        f"({gemela.nombre or '?'}, NIF {gemela.nif or '?'}): se "
                        "guardó dos veces."))
            continue
        unicas.append(p)
    progs = unicas

    parejas, solo_programa, solo_aplifisa = _emparejar(progs, apls)
    for p, a, nivel in parejas:
        if nivel == 0 and p.pdf_guardado:
            cuadre.lineas.append(Linea(BIEN, p, a, _detalle_programa(p) + _nota_pdf(p)))
        elif nivel == 0:
            cuadre.lineas.append(Linea(
                SIN_PDF, p, a,
                "Registrada en Aplifisa, pero su PDF no está guardado en la "
                "carpeta del cliente: escanéela o recójala."))
        else:
            cuadre.lineas.append(Linea(
                DISTINTA, p, a, "Cambia " + _diferencias(p, a) + "." + _nota_pdf(p)))

    # Sin pareja segura: se dicen como «falta», con una pista si hay una del
    # otro lado con los mismos importes y otra fecha (puede ser un error al
    # teclear la fecha; mejor que lo mire una persona).
    def pista_programa(p):
        a = next((a for a in solo_aplifisa if a.tipo == p.tipo
                  and _mismos_importes(p, a) and _relacion(p, a) is not None
                  and _relacion(p, a)["dias"] <= DIAS_FECHA_DISTINTA), None)
        return (f" ¿Es la de Aplifisa del {a.fecha} ({a.nombre}) con los mismos "
                "importes? Compruebe la fecha.") if a else ""

    def pista_aplifisa(a):
        p = next((p for p in solo_programa if p.tipo == a.tipo
                  and _mismos_importes(p, a) and _relacion(p, a) is not None
                  and _relacion(p, a)["dias"] <= DIAS_FECHA_DISTINTA), None)
        return (f" ¿Es la del programa del {p.fecha} ({p.nombre}) con los mismos "
                "importes? Compruebe la fecha.") if p else ""

    for p in solo_programa:
        cuadre.lineas.append(Linea(
            FALTA_APLIFISA, programa=p,
            detalle=_detalle_programa(p) + " No está registrada en Aplifisa."
            + _nota_pdf(p) + pista_programa(p)))

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
        cuadre.lineas.append(Linea(
            FALTA_PROGRAMA, aplifisa=a,
            detalle="Registrada en Aplifisa, pero el programa no la tiene "
                    "guardada: búsquela y escanéela." + aviso + pista_aplifisa(a)))

    # Totales por trimestre: programa (sin las repetidas) frente a Aplifisa.
    for p in progs:
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


def periodo_de_listados(registros: Iterable[Registro]) -> Tuple[Optional[date], Optional[date]]:
    """El periodo que se pidió a Aplifisa, por trimestres enteros: del
    primer día del trimestre de su primera factura al último del de la
    última (si falta el último mes, sus facturas salen como «falta»). Solo
    el año del listado: una suelta del año anterior no lo arrastra. La
    ventana deja corregirlo."""
    fechas = [d for r in registros for d in (fecha_de(a.fecha) for a in r.apuntes) if d]
    if not fechas:
        return None, None
    anio = Counter(d.year for d in fechas).most_common(1)[0][0]
    del_anio = [d for d in fechas if d.year == anio]
    primera, ultima = min(del_anio), max(del_anio)
    inicio = date(anio, 3 * (_trimestre(primera) - 1) + 1, 1)
    mes_fin = 3 * _trimestre(ultima)
    return inicio, date(anio, mes_fin, calendar.monthrange(anio, mes_fin)[1])


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
