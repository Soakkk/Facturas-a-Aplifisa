"""Suma de un grupo de facturas, para cuadrar el lote antes de exportarlo.

El total se CALCULA (base + IVA + recargo - retencion) en vez de sumar el total
impreso: es lo que se va a registrar en Aplifisa, que es lo que interesa cuadrar.
Si el impreso no coincide, validacion ya lo marca factura a factura.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from .modelo import Factura


@dataclass
class Totales:
    lineas: int = 0
    base: float = 0.0
    iva: float = 0.0
    irpf: float = 0.0
    requiv: float = 0.0

    @property
    def total(self) -> float:
        """Total factura: lo que se paga = base + IVA + recargo - retencion."""
        return round(self.base + self.iva + self.requiv - self.irpf, 2)

    @property
    def tiene_irpf(self) -> bool:
        return abs(self.irpf) > 0.005

    @property
    def tiene_requiv(self) -> bool:
        return abs(self.requiv) > 0.005


def resumir(facturas: Iterable[Factura]) -> Totales:
    t = Totales()
    for f in facturas:
        t.lineas += 1
        t.base += f.base_iva or 0.0
        t.iva += f.cuota_iva or 0.0
        t.irpf += f.cuota_irpf or 0.0
        t.requiv += f.cuota_requiv or 0.0
    for campo in ("base", "iva", "irpf", "requiv"):
        setattr(t, campo, round(getattr(t, campo), 2))
    return t


def _eur(v: float) -> str:
    entero, dec = f"{abs(v):.2f}".split(".")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    signo = "-" if v < 0 else ""
    return f"{signo}{'.'.join(grupos)},{dec} €"


def describir(t: Totales, solo_total: bool = False) -> str:
    """Texto del resumen. solo_total=True para los clientes que registran por
    el total de la factura (recargo de equivalencia): ahi el desglose sobra."""
    if not t.lineas:
        return "—"
    if solo_total:
        return f"total factura {_eur(t.total)}"
    partes: List[str] = [f"base {_eur(t.base)}", f"IVA {_eur(t.iva)}"]
    if t.tiene_requiv:
        partes.append(f"recargo {_eur(t.requiv)}")
    if t.tiene_irpf:  # solo si la factura lleva retencion
        partes.append(f"IRPF −{_eur(t.irpf)}")
    partes.append(f"total factura {_eur(t.total)}")
    return "  ·  ".join(partes)
