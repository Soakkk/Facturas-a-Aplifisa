"""Examen de precisión: cuánto acierta la lectura, medido con sus facturas.

Se cogen facturas que ya revisó una persona y se exportaron (están en el
registro con su PDF), se vuelven a leer con cada modelo configurado y se
compara dato a dato con lo que quedó bueno. Salen dos números que importan:

- el porcentaje de aciertos de cada modelo en cada dato (NIF, número, fecha,
  base, IVA, total);
- las «verificadas con error»: facturas en las que los DOS modelos dijeron lo
  mismo y era mentira. Es el fallo peligroso, porque saldría en verde.

Solo se examinan facturas de una hoja (las de varias hojas se leen por
partes y no se pueden comparar enteras). Nada se envía a ningún sitio salvo
la imagen a Gemini, igual que al leer. Cuesta lo mismo que leerlas: por eso
se pasa solo cuando se pulsa, y antes se dice cuánto costará.

Los resultados se guardan en la base de datos local (colección «examenes»)
para comparar una versión con la anterior.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import almacen, costes, registro_facturas
from .rutas import dir_datos

CAMPOS = (
    ("nif", "NIF de la otra parte"),
    ("num_factura", "Nº de factura"),
    ("fecha", "Fecha"),
    ("base", "Base imponible"),
    ("cuota_iva", "Cuota de IVA"),
    ("total", "Total"),
)
MAXIMO_POR_DEFECTO = 30


@dataclass
class Caso:
    """Una factura revisada: dónde está su hoja y cuáles son sus datos buenos."""
    ruta: str
    pagina: int
    tipo: str
    esperado: Dict[str, object]
    etiqueta: str = ""


@dataclass
class Resultado:
    modelos: List[str]
    casos: int = 0
    # {modelo: {campo: [aciertos, total]}}
    por_campo: Dict[str, Dict[str, List[int]]] = field(default_factory=dict)
    # Facturas en que los dos modelos coincidieron en un dato equivocado.
    verificadas_con_error: List[str] = field(default_factory=list)
    # Casos en que los dos coincidieron en todo (saldrían «Verificada»).
    verificadas: int = 0
    fallos_lectura: int = 0
    coste: float = 0.0
    detalles: List[str] = field(default_factory=list)

    def porcentaje(self, modelo: str, campo: Optional[str] = None) -> Optional[float]:
        cuentas = self.por_campo.get(modelo, {})
        pares = [cuentas[campo]] if campo else list(cuentas.values())
        aciertos = sum(p[0] for p in pares if p)
        total = sum(p[1] for p in pares if p)
        return round(100.0 * aciertos / total, 1) if total else None


# ------------------------------------------------------------------ casos
def _una_hoja(ficha: dict) -> Optional[tuple]:
    """(ruta, página) de la hoja de una factura de una sola hoja, o None."""
    try:
        paginas = json.loads(ficha.get("paginas") or "[]")
    except ValueError:
        paginas = []
    pdf = ficha.get("pdf")
    if len(paginas) > 1:
        return None
    if pdf and os.path.isfile(pdf):
        return pdf, 1
    if len(paginas) == 1:
        origen, pagina = paginas[0]
        if os.path.isfile(origen):
            return origen, int(pagina)
    return None


def casos_disponibles(maximo: int = MAXIMO_POR_DEFECTO) -> List[Caso]:
    """Las facturas revisadas más recientes, variando de proveedor."""
    fichas = [f for f in registro_facturas.consultar(limite=5000)
              if f.get("exportada_en")]
    fichas.sort(key=lambda f: f.get("exportada_en") or "", reverse=True)
    elegidos: List[Caso] = []
    por_proveedor: Dict[str, int] = {}
    # Primero una por proveedor; luego se completa con el resto.
    for ronda in (1, 10 ** 6):
        for f in fichas:
            if len(elegidos) >= maximo:
                return elegidos
            clave = f.get("nif") or f.get("nombre") or ""
            if por_proveedor.get(clave, 0) >= ronda or any(
                    c.etiqueta == f["id"] for c in elegidos):
                continue
            hoja = _una_hoja(f)
            if not hoja:
                continue
            por_proveedor[clave] = por_proveedor.get(clave, 0) + 1
            elegidos.append(Caso(
                ruta=hoja[0], pagina=hoja[1], tipo=f.get("tipo") or "gasto",
                esperado={"nif": f.get("nif"), "num_factura": f.get("num_factura"),
                          "fecha": f.get("fecha"),
                          # Recargo por el total: lo guardado no es el
                          # desglose de la factura, no se puede comparar.
                          "base": None if f.get("por_total") else f.get("base"),
                          "cuota_iva": None if f.get("por_total") else f.get("cuota_iva"),
                          "total": f.get("total")},
                etiqueta=f["id"]))
    return elegidos


def coste_estimado(casos: int, modelos: List[str], ppp: int) -> float:
    return round(sum(costes.coste_por_factura(ppp, m) for m in modelos) * casos, 4)


# ------------------------------------------------------------- comparar
def leido(datos: dict, tipo: str) -> Dict[str, object]:
    """Lo leído por un modelo, con los mismos nombres que lo esperado."""
    from .extraccion import _num
    lineas = [x for x in (datos.get("lineas_iva") or []) if isinstance(x, dict)]
    base = [_num(x.get("base")) for x in lineas]
    cuota = [_num(x.get("cuota_iva")) for x in lineas]
    nif = datos.get("emisor_nif") if tipo != "venta" else datos.get("receptor_nif")
    return {
        "nif": nif, "num_factura": datos.get("num_factura"),
        "fecha": datos.get("fecha"),
        "base": round(sum(b for b in base if b is not None), 2) if any(
            b is not None for b in base) else None,
        "cuota_iva": round(sum(c for c in cuota if c is not None), 2) if any(
            c is not None for c in cuota) else None,
        "total": _num(datos.get("total")),
    }


def igual(campo: str, bueno, leido_) -> bool:
    from .doble_lectura import _iguales
    if campo in ("base", "cuota_iva", "total"):
        # Un importe vacío y un 0,00 son lo mismo.
        return _iguales("total", bueno or 0.0, leido_ or 0.0)
    if campo == "nif":
        return _iguales("emisor_nif", bueno, leido_)
    return _iguales(campo, bueno, leido_)


# ---------------------------------------------------------------- pasar
def pasar(casos: List[Caso], lector: Callable[[str, bytes], tuple],
          modelos: List[str], ppp: int = 150,
          progreso: Optional[Callable[[int, int], None]] = None,
          imagen: Optional[Callable[[Caso], bytes]] = None) -> Resultado:
    """Lee cada caso con cada modelo y lo compara con lo bueno.

    `lector(modelo, imagen)` devuelve (datos, consumos) — así se puede probar
    sin Gemini.
    """
    from .pdf import pagina_a_jpg
    imagen = imagen or (lambda c: pagina_a_jpg(c.ruta, c.pagina, ppp))
    r = Resultado(modelos=list(modelos))
    total_pasos = len(casos) * len(modelos)
    hechos = 0
    for caso in casos:
        try:
            img = imagen(caso)
        except Exception:
            r.fallos_lectura += 1
            hechos += len(modelos)
            continue
        lecturas = {}
        for modelo in modelos:
            try:
                datos, consumos = lector(modelo, img)
                for m, entrada, salida in consumos or ():
                    r.coste += costes.registrar(m, entrada, salida, facturas=0)
                lecturas[modelo] = leido(datos, caso.tipo)
            except Exception as e:  # una hoja que no se lee cuenta como fallo
                r.fallos_lectura += 1
                r.detalles.append(f"{os.path.basename(caso.ruta)}: {modelo} no la leyó ({e})"[:200])
            hechos += 1
            if progreso:
                progreso(hechos, total_pasos)
        if not lecturas:
            continue
        r.casos += 1
        for modelo, valores in lecturas.items():
            cuentas = r.por_campo.setdefault(modelo, {})
            for campo, _ in CAMPOS:
                bueno = caso.esperado.get(campo)
                if bueno in (None, ""):
                    continue
                par = cuentas.setdefault(campo, [0, 0])
                par[1] += 1
                if igual(campo, bueno, valores.get(campo)):
                    par[0] += 1
                else:
                    r.detalles.append(
                        f"{os.path.basename(caso.ruta)} · {modelo} · {campo}: "
                        f"leyó {valores.get(campo)!r}, era {bueno!r}")
        if len(lecturas) >= 2:
            a, b = list(lecturas.values())[:2]
            coinciden = all(igual(c, a.get(c), b.get(c)) or (a.get(c) is None and b.get(c) is None)
                            for c, _ in CAMPOS)
            if coinciden:
                r.verificadas += 1
                malos = [c for c, _ in CAMPOS
                         if caso.esperado.get(c) not in (None, "")
                         and not igual(c, caso.esperado[c], a.get(c))]
                if malos:
                    r.verificadas_con_error.append(
                        f"{os.path.basename(caso.ruta)}: los dos modelos leyeron "
                        f"igual y mal {', '.join(malos)}")
    r.coste = round(r.coste, 6)
    return r


def lector_gemini(api_key: str) -> Callable[[str, bytes], tuple]:
    """Lee una hoja con UN modelo concreto, sin doble lectura ni respaldo."""
    from .extraccion import DOBLE_NO, Extractor

    extractores = {}

    def leer(modelo: str, img: bytes):
        if modelo not in extractores:
            extractores[modelo] = Extractor(api_key, modelos=[modelo], modo_doble=DOBLE_NO)
        datos, _real, consumos = extractores[modelo]._leer_con(modelo, img, 1)
        return datos, consumos
    return leer


# ------------------------------------------------------------- historial
def _col():
    return almacen.Coleccion("examenes", dir_datos())


def guardar(r: Resultado, version: str) -> str:
    momento = almacen.ahora()
    _col().guardar(momento, {
        "version": version, "fecha": momento, "modelos": r.modelos,
        "casos": r.casos, "por_campo": r.por_campo,
        "verificadas": r.verificadas,
        "verificadas_con_error": r.verificadas_con_error,
        "fallos_lectura": r.fallos_lectura, "coste": r.coste,
    })
    return momento


def anteriores() -> List[dict]:
    """Exámenes pasados, del más reciente al más antiguo."""
    return [v for _k, v in sorted(_col().leer_todo().items(), reverse=True)
            if isinstance(v, dict)]


def porcentaje_guardado(examen: dict, modelo: str) -> Optional[float]:
    cuentas = (examen.get("por_campo") or {}).get(modelo, {})
    aciertos = sum(p[0] for p in cuentas.values())
    total = sum(p[1] for p in cuentas.values())
    return round(100.0 * aciertos / total, 1) if total else None
