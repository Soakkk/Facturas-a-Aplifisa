"""Suma de un grupo de facturas, para cuadrar el lote antes de exportarlo.

El total se CALCULA (base + IVA + recargo + suplidos - retencion) en vez de
sumar el total
impreso: es lo que se va a registrar en Aplifisa, que es lo que interesa cuadrar.
Si el impreso no coincide, validacion ya lo marca factura a factura.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

from .modelo import Factura


@dataclass
class Totales:
    lineas: int = 0
    base: float = 0.0
    iva: float = 0.0
    irpf: float = 0.0
    requiv: float = 0.0
    suplidos: float = 0.0
    iva_por_tipo: Dict[float, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        """Total: base + IVA + recargo + suplidos - retencion."""
        return round(
            self.base + self.iva + self.requiv + self.suplidos - self.irpf, 2)

    @property
    def tiene_irpf(self) -> bool:
        return abs(self.irpf) > 0.005

    @property
    def tiene_requiv(self) -> bool:
        return abs(self.requiv) > 0.005

    @property
    def tiene_suplidos(self) -> bool:
        return abs(self.suplidos) > 0.005


def _acumular(t: Totales, f: Factura) -> None:
    t.lineas += 1
    t.base += f.base_iva or 0.0
    t.iva += f.cuota_iva or 0.0
    if f.pct_iva is not None and f.cuota_iva is not None:
        tipo = round(float(f.pct_iva), 4)
        t.iva_por_tipo[tipo] = t.iva_por_tipo.get(tipo, 0.0) + f.cuota_iva
    t.irpf += f.cuota_irpf or 0.0
    t.requiv += f.cuota_requiv or 0.0
    t.suplidos += f.suplidos or 0.0


def _redondear(t: Totales) -> Totales:
    for campo in ("base", "iva", "irpf", "requiv", "suplidos"):
        setattr(t, campo, round(getattr(t, campo), 2))
    t.iva_por_tipo = {tipo: round(cuota, 2)
                      for tipo, cuota in t.iva_por_tipo.items()}
    return t


def resumir(facturas: Iterable[Factura]) -> Totales:
    t = Totales()
    for f in facturas:
        _acumular(t, f)
    return _redondear(t)


def resumir_por_bloque(filas: Iterable[Tuple[str, Factura]]) -> Dict[str, Totales]:
    """Suma cada bloque escaneado por separado, en el orden en que se cargaron.

    Es lo que hace falta para cuadrar: cada PDF del escaner se comprueba contra
    el taco de papel que se metio en el alimentador, no contra el lote entero.
    """
    grupos: Dict[str, Totales] = {}
    for bloque, f in filas:
        _acumular(grupos.setdefault(bloque, Totales()), f)
    return {nombre: _redondear(t) for nombre, t in grupos.items()}


def eur(v: float) -> str:
    entero, dec = f"{abs(v):.2f}".split(".")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    signo = "-" if v < 0 else ""
    return f"{signo}{'.'.join(grupos)},{dec} €"


def iva_desglosado(t: Totales) -> str:
    """IVA compacto: muestra siempre porcentaje y cuota cuando se conoce."""
    if not t.iva_por_tipo:
        return eur(t.iva)

    def porcentaje(tipo: float) -> str:
        if tipo.is_integer():
            return str(int(tipo))
        return f"{tipo:g}".replace(".", ",")

    return " · ".join(
        f"{porcentaje(tipo)}%: {eur(cuota)}"
        for tipo, cuota in sorted(t.iva_por_tipo.items()))


def describir(t: Totales, solo_total: bool = False) -> str:
    """Texto del resumen. solo_total=True para los clientes que registran por
    el total de la factura (recargo de equivalencia): ahi el desglose sobra."""
    if not t.lineas:
        return "—"
    if solo_total:
        return f"total factura {eur(t.total)}"
    partes: List[str] = [f"base {eur(t.base)}", f"IVA {eur(t.iva)}"]
    if t.tiene_requiv:
        partes.append(f"recargo {eur(t.requiv)}")
    if t.tiene_irpf:  # solo si la factura lleva retencion
        partes.append(f"IRPF −{eur(t.irpf)}")
    if t.tiene_suplidos:
        partes.append(f"suplidos {eur(t.suplidos)}")
    partes.append(f"total factura {eur(t.total)}")
    return "  ·  ".join(partes)

