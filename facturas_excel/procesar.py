"""Nucleo de procesamiento de un lote de facturas ya extraidas por Gemini.

- Autodetecta el CLIENTE de la asesoria: el NIF que aparece en (casi) todas las
  facturas del lote (como destinatario en los gastos y emisor en las ventas).
- Para cada factura decide GASTO/VENTA, elige la CONTRAPARTE (la otra parte) y
  la CUENTA contable, y construye las Factura (una por linea de IVA).

Reutilizable desde la UI y desde scripts.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .conceptos import DEFAULT_VENTA, asignar_concepto, subclave_628
from .extraccion import _num
from .modelo import Factura


def normaliza_nif(nif) -> str:
    if not nif:
        return ""
    return str(nif).strip().upper().replace(".", "").replace(" ", "").replace("-", "")


def _tokens_nombre(nombre) -> set:
    import unicodedata
    if not nombre:
        return set()
    t = "".join(c for c in unicodedata.normalize("NFD", str(nombre))
                if unicodedata.category(c) != "Mn").upper()
    # quitar formas societarias y puntuacion
    for r in [",", ".", "(", ")", " SL", " S L", " SLU", " SA", " SAU", " CB"]:
        t = t.replace(r, " ")
    return {p for p in t.split() if len(p) >= 3}


def _mismo_nombre(a, b) -> bool:
    """Mismo nombre si comparten >=2 palabras Y la mayoria de las del mas corto.
    Evita confundir 'JOSE ANTONIO MARIN PRIETO' con 'JOSE ANTONIO MAYOR MARCO'
    (solo comparten el nombre de pila compuesto)."""
    ta, tb = _tokens_nombre(a), _tokens_nombre(b)
    if not ta or not tb:
        return False
    comunes = len(ta & tb)
    return comunes >= 2 and comunes / min(len(ta), len(tb)) >= 0.6


def detectar_cliente(lista_datos: List[dict]) -> Tuple[str, str]:
    """Devuelve (nombre, nif) del cliente: el NIF mas repetido en el lote."""
    cuenta = Counter()
    nombres: Dict[str, list] = defaultdict(list)
    for d in lista_datos:
        for campo_nif, campo_nom in (("emisor_nif", "emisor_nombre"),
                                     ("receptor_nif", "receptor_nombre")):
            nif = normaliza_nif(d.get(campo_nif))
            if nif:
                cuenta[nif] += 1
                if d.get(campo_nom):
                    nombres[nif].append(d[campo_nom])
    if not cuenta:
        return ("", "")
    nif_cliente, _ = cuenta.most_common(1)[0]
    # nombre mas frecuente (y si empatan, el mas largo/completo)
    lista_nombres = nombres.get(nif_cliente, [])
    if lista_nombres:
        nombre = Counter(lista_nombres).most_common(1)[0][0]
    else:
        nombre = ""
    return (nombre, nif_cliente)


@dataclass
class FacturaProcesada:
    tipo: str                 # "gasto" / "venta"
    facturas: List[Factura]   # una por linea de IVA
    cuenta: str
    gxx: str | None
    origen: str
    pagina: int
    aviso: str = ""           # rol emisor/destinatario dudoso, etc.


def construir(datos: dict, cliente_nif: str, cliente_nombre: str = "",
              origen: str = "", pagina: int = 0) -> FacturaProcesada:
    cliente_nif = normaliza_nif(cliente_nif)
    e_nif = normaliza_nif(datos.get("emisor_nif"))
    r_nif = normaliza_nif(datos.get("receptor_nif"))
    e_nom, r_nom = datos.get("emisor_nombre"), datos.get("receptor_nombre")

    # Identificar al cliente. EL NIF MANDA (no engaña); el nombre solo se usa
    # cuando falta el NIF. La contraparte es SIEMPRE la parte que no es el cliente.
    aviso = ""
    if e_nif == cliente_nif and r_nif != cliente_nif:
        # NIF del emisor = cliente -> venta (aunque el receptor se llame parecido)
        tipo, nombre, nif = "venta", r_nom, datos.get("receptor_nif")
    elif r_nif == cliente_nif and e_nif != cliente_nif:
        tipo, nombre, nif = "gasto", e_nom, datos.get("emisor_nif")
    else:
        # Sin NIF decisivo -> comparar nombres
        es_emisor = _mismo_nombre(e_nom, cliente_nombre)
        es_receptor = _mismo_nombre(r_nom, cliente_nombre)
        if es_emisor and not es_receptor:
            tipo, nombre, nif = "venta", r_nom, datos.get("receptor_nif")
            if not e_nif:
                aviso = "El cliente figura como emisor sin NIF: confirma si es venta o gasto."
        elif es_receptor and not es_emisor:
            tipo, nombre, nif = "gasto", e_nom, datos.get("emisor_nif")
        else:
            # No se identifica con claridad -> asumir gasto y avisar.
            tipo, nombre, nif = "gasto", e_nom, datos.get("emisor_nif")
            aviso = "Rol emisor/destinatario dudoso: revisa si es gasto o venta."

    # Cuenta contable
    if tipo == "venta":
        cuenta = DEFAULT_VENTA
        gxx = None
    else:
        cuenta = str(datos.get("cuenta_gasto") or "").strip()
        texto = f"{datos.get('concepto_texto', '')} {datos.get('emisor_nombre', '')}"
        if not cuenta:  # respaldo por palabras clave si Gemini no dio cuenta
            cuenta = asignar_concepto("gasto", texto)
        gxx = datos.get("subclave_gxx") or (subclave_628(texto) if cuenta == "628" else None)

    # Construir Factura (una por linea de IVA)
    lineas = datos.get("lineas_iva") or [{}]
    comun = dict(
        num_factura=datos.get("num_factura") or None,
        fecha=datos.get("fecha") or None,
        fecha_operacion=datos.get("fecha_operacion") or None,
        nombre=nombre or None,
        nif=nif or None,
        concepto=cuenta or None,
        total_impreso=_num(datos.get("total")),
        origen_imagen=origen,
    )
    facturas = []
    for i, linea in enumerate(lineas):
        f = Factura(**comun)
        f.base_iva = _num(linea.get("base"))
        f.pct_iva = _num(linea.get("tipo_iva"))
        f.cuota_iva = _num(linea.get("cuota_iva"))
        if i == 0:
            f.base_irpf = _num(datos.get("base_irpf"))
            f.pct_irpf = _num(datos.get("pct_irpf"))
            f.cuota_irpf = _num(datos.get("cuota_irpf"))
        facturas.append(f)

    return FacturaProcesada(tipo=tipo, facturas=facturas, cuenta=cuenta,
                            gxx=gxx, origen=origen, pagina=pagina, aviso=aviso)
