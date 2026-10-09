"""Dónde está escrito cada dato en la hoja, para señalarlo con un recuadro.

Se le da a Gemini la imagen de la hoja y los valores que ya se han leído
(NIF, número, fecha, bases, cuotas, total… y, si las dos lecturas no
coincidieron, los dos valores en disputa) y devuelve, para cada uno, la caja
donde aparece: [ymin, xmin, ymax, xmax] de 0 a 1000 sobre la imagen. Así, al
revisar, basta mirar el recuadro en vez de buscar el dato por toda la hoja.

Es una consulta aparte y más corta que la lectura (la respuesta es pequeña).
Se pide sola solo para las facturas en ámbar o en rojo; para cualquier otra,
con el botón «¿De dónde sale?». Nunca cambia ningún dato: solo señala.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

# Dato de la Factura -> nombre que se le da a Gemini.
CAMPOS = {
    "nif": "nif", "nombre": "nombre", "num_factura": "num_factura",
    "fecha": "fecha", "base_iva": "base", "cuota_iva": "cuota_iva",
    "pct_iva": "tipo_iva", "cuota_requiv": "cuota_recargo",
    "cuota_irpf": "retencion", "total_impreso": "total",
}
# Y al revés, y los nombres de la doble lectura.
CAMPO_DE_NOMBRE = {v: k for k, v in CAMPOS.items()}
DE_DOBLE_LECTURA = {"emisor_nif": "nif", "receptor_nif": "nif",
                    "num_factura": "num_factura", "fecha": "fecha",
                    "total": "total_impreso", "cuota_irpf": "cuota_irpf"}

_ESQUEMA = {
    "type": "object",
    "properties": {
        "datos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "campo": {"type": "string", "enum": sorted(set(CAMPOS.values()))},
                    "valor": {"type": "string"},
                    "caja": {"type": ["array", "null"],
                             "items": {"type": "integer"}},
                },
                "required": ["campo", "valor", "caja"],
            },
        },
    },
    "required": ["datos"],
}


def clave_imagen(png: bytes) -> str:
    return hashlib.sha1(png or b"").hexdigest()


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return f"{valor:.2f}".replace(".", ",")
    return str(valor).strip()


def _comparable(valor) -> str:
    """Para emparejar un valor con lo que devolvió Gemini (sin puntos ni €)."""
    from .tabla_facturas import parse_numero
    if isinstance(valor, int) and abs(valor) > 10 ** 15:
        return ""      # un entero desbocado: ni float() ni str() (> 4300 cifras)
    numero = parse_numero(valor) if not isinstance(valor, (int, float)) else float(valor)
    if numero is not None and any(c.isdigit() for c in str(valor)) and not any(
            c.isalpha() for c in str(valor)):
        return f"{abs(numero):.2f}"
    return "".join(c for c in str(valor or "") if c.isalnum()).upper()


def peticiones(facturas: Iterable, discrepancias: Iterable = ()) -> List[Tuple[str, str]]:
    """[(nombre del dato, valor)] que hay que buscar en la hoja, sin repetir."""
    salida: Dict[Tuple[str, str], None] = {}
    for f in facturas:
        for campo, nombre in CAMPOS.items():
            texto = _texto(getattr(f, campo, None))
            if texto:
                salida[(nombre, texto)] = None
    for d in discrepancias or ():
        campo = DE_DOBLE_LECTURA.get(d.get("campo"))
        if not campo:
            continue
        for clave in ("valor_1", "valor_2"):
            texto = _texto(d.get(clave))
            if texto:
                salida[(CAMPOS[campo], texto)] = None
    return list(salida)


def _prompt(lista: List[Tuple[str, str]]) -> str:
    lineas = "\n".join(f"- {nombre}: «{valor}»" for nombre, valor in lista)
    return (
        "Esta imagen es una factura. Localiza dónde está escrito cada uno de "
        "estos datos y devuelve su caja [ymin, xmin, ymax, xmax] en una escala "
        "de 0 a 1000 sobre la imagen (0,0 es la esquina de arriba a la "
        "izquierda). La caja debe rodear solo ese valor impreso, no su "
        "etiqueta. Si un valor no aparece tal cual en la hoja, devuelve caja "
        "null: NO lo sitúes en otro número parecido. Devuelve cada dato con el "
        "mismo campo y valor que se piden.\n\n" + lineas)


@dataclass
class Caja:
    campo: str            # dato de la Factura (nif, total_impreso…)
    valor: str
    y0: float             # de 0 a 1 sobre la imagen
    x0: float
    y1: float
    x1: float


def interpretar(datos: dict) -> List[Caja]:
    """Las cajas válidas de la respuesta (se descartan las raras)."""
    cajas = []
    for d in (datos or {}).get("datos") or []:
        if not isinstance(d, dict):
            continue
        campo = CAMPO_DE_NOMBRE.get(d.get("campo"))
        caja = d.get("caja")
        if not campo or not isinstance(caja, list) or len(caja) != 4:
            continue
        try:
            y0, x0, y1, x1 = (min(1000.0, max(0.0, float(v))) / 1000 for v in caja)
        except (TypeError, ValueError):
            continue
        if y1 <= y0 or x1 <= x0:
            continue
        cajas.append(Caja(campo, str(d.get("valor") or ""), y0, x0, y1, x1))
    return cajas


def pedir(api_key: str, modelo: str, img: bytes,
          lista: List[Tuple[str, str]]) -> Tuple[List[Caja], list]:
    """Pregunta a Gemini y devuelve (cajas, consumos)."""
    from google import genai
    from google.genai import types
    from .extraccion import TIEMPO_LIMITE, _consumo, _parse_json_tolerante

    if not lista:
        return [], []
    cliente = genai.Client(api_key=api_key, http_options=types.HttpOptions(
        timeout=TIEMPO_LIMITE * 1000))
    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_json_schema=_ESQUEMA,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW))
    mime = "image/png" if (img or b"").startswith(b"\x89PNG") else "image/jpeg"
    resp = cliente.models.generate_content(
        model=modelo,
        contents=[types.Part.from_bytes(data=img, mime_type=mime), _prompt(lista)],
        config=config)
    real, entrada, salida = _consumo(resp)
    datos = _parse_json_tolerante(resp.text or "")
    return interpretar(datos if isinstance(datos, dict) else {}), [
        (real or modelo, entrada, salida)]


def cajas_de(cajas: Iterable[Caja], campo: str, valor=None) -> List[Caja]:
    """Las cajas de un dato; si se da el valor, las de ese valor primero."""
    del_campo = [c for c in cajas or () if c.campo == campo]
    if valor in (None, ""):
        return del_campo
    buscado = _comparable(valor)
    iguales = [c for c in del_campo if _comparable(c.valor) == buscado]
    return iguales


def a_guardar(cajas: List[Caja]) -> list:
    """Para la sesión guardada (datos simples)."""
    return [[c.campo, c.valor, c.y0, c.x0, c.y1, c.x1] for c in cajas]


def de_guardado(datos) -> List[Caja]:
    salida = []
    for d in datos or []:
        try:
            salida.append(Caja(str(d[0]), str(d[1]), *(float(v) for v in d[2:6])))
        except (TypeError, ValueError, IndexError):
            continue
    return salida


def principal() -> Optional[str]:
    from .extraccion import modelos_configurados
    modelos = modelos_configurados()
    return modelos[0] if modelos else None
