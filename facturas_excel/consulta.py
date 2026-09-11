"""Búsqueda y periodo de trabajo del lote actualmente cargado."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional

from .modelo import Factura
from .validacion import fecha_de


FORMAS_JURIDICAS = {
    "s", "l", "a", "u", "p", "sl", "sa", "slu", "slp",
    "sociedad", "limitada", "anonima", "unipersonal", "profesional",
}


def normalizar_texto(valor) -> str:
    texto = "".join(
        c for c in unicodedata.normalize("NFD", str(valor or ""))
        if unicodedata.category(c) != "Mn"
    ).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", texto))


def _importe_buscado(texto: str) -> Optional[float]:
    limpio = str(texto or "").strip().replace("€", "").replace(" ", "")
    if not re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}", limpio):
        return None
    try:
        return float(limpio.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def coincide_busqueda(factura: Factura, texto: str) -> bool:
    """Busca por contraparte, NIF, número o un importe español exacto."""
    if not str(texto or "").strip():
        return True
    importe = _importe_buscado(texto)
    if importe is not None:
        valores = (
            factura.base_iva, factura.cuota_iva, factura.base_irpf,
            factura.cuota_irpf, factura.cuota_requiv, factura.total_impreso,
        )
        return any(v is not None and abs(float(v) - importe) <= 0.005
                   for v in valores)
    consulta_original = normalizar_texto(texto).split()
    consulta = [token for token in consulta_original
                if token not in FORMAS_JURIDICAS] or consulta_original
    destino = normalizar_texto(
        " ".join(str(v or "") for v in (
            factura.nombre, factura.nif, factura.num_factura,
        )))
    return all(token in destino for token in consulta)


def clave_factura(factura: Factura, indice: int) -> tuple:
    """Una factura con varias líneas de IVA cuenta una sola vez."""
    if factura.documento_id:
        return ("documento", factura.documento_id)
    if int(factura.lineas_factura or 1) > 1:
        return (
            "compuesta", factura.origen_imagen or "",
            normalizar_texto(factura.num_factura).replace(" ", ""),
            normalizar_texto(factura.nif).replace(" ", ""),
            factura.fecha or "",
        )
    return ("linea", indice)


def facturas_unicas(facturas: Iterable[Factura]) -> int:
    return len({clave_factura(f, i) for i, f in enumerate(facturas)})


@dataclass(frozen=True)
class PeriodoLote:
    ejercicio: Optional[int] = None
    trimestre: Optional[int] = None
    automatico: bool = True

    @property
    def es_trimestre(self) -> bool:
        return self.ejercicio is not None and self.trimestre in (1, 2, 3, 4)

    @property
    def etiqueta(self) -> str:
        if self.ejercicio is None:
            return "Sin periodo"
        if self.es_trimestre:
            return f"{self.trimestre}T {self.ejercicio}"
        return f"Anual {self.ejercicio}"

    def contiene(self, factura: Factura) -> bool:
        fecha = fecha_de(factura.fecha)
        if not fecha or self.ejercicio is None:
            return True
        if fecha.year != self.ejercicio:
            return False
        if not self.es_trimestre:
            return True
        return ((fecha.month - 1) // 3 + 1) == self.trimestre


def detectar_periodo(facturas: Iterable[Factura]) -> PeriodoLote:
    """Detecta trimestre dominante; si el lote está repartido, es anual."""
    fechas = []
    vistas = set()
    for indice, factura in enumerate(facturas):
        clave = clave_factura(factura, indice)
        if clave in vistas:
            continue
        vistas.add(clave)
        fecha = fecha_de(factura.fecha)
        if fecha:
            fechas.append(fecha)
    if not fechas:
        return PeriodoLote()
    ejercicio = Counter(f.year for f in fechas).most_common(1)[0][0]
    del_ejercicio = [f for f in fechas if f.year == ejercicio]
    trimestres = Counter((f.month - 1) // 3 + 1 for f in del_ejercicio)
    if len(trimestres) == 1:
        return PeriodoLote(ejercicio, next(iter(trimestres)))
    dominante, cantidad = trimestres.most_common(1)[0]
    # Un único despiste fuera de un taco trimestral no debe convertirlo en
    # anual. Con actividad repartida de verdad se considera el ejercicio entero.
    if len(del_ejercicio) >= 4 and cantidad / len(del_ejercicio) >= 0.75:
        return PeriodoLote(ejercicio, dominante)
    return PeriodoLote(ejercicio)


def periodo_manual(ejercicio: int, valor: str) -> PeriodoLote:
    if valor in {"1", "2", "3", "4"}:
        return PeriodoLote(ejercicio, int(valor), automatico=False)
    return PeriodoLote(ejercicio, automatico=False)
