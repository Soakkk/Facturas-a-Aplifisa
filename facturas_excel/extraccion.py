"""Extraccion de datos de facturas con Gemini (Google).

Gemini devuelve EMISOR y DESTINATARIO por separado (para autodetectar quien es
el cliente de la asesoria: el NIF que se repite en todo el lote), los importes,
y una propuesta de CUENTA contable (plan PGC PYMES) segun el criterio de la
asesoria. La decision gasto/venta y la contraparte se calculan despues, en
procesar.py, una vez detectado el cliente.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import List, Optional

from google import genai
from google.genai import types

# Modelos por orden de preferencia (con reserva ante 503/alta demanda).
# flash-latest = ultimo Flash estable: la mejor relacion precision/coste/velocidad
# para extraer campos de facturas. pro-latest de refuerzo (mas potente, mas caro).
MODELOS = ["gemini-flash-latest", "gemini-pro-latest", "gemini-3.1-flash-lite"]


class SinCredito(Exception):
    """La API key no tiene credito / facturacion activa (no reintentar)."""

# Criterio contable que sigue Gemini para proponer la cuenta de un GASTO.
_CRITERIO_CUENTAS = """CUENTAS DE GASTO (PGC PYMES) - elige el codigo que mejor encaje:
- 628 Suministros: luz, agua, gas, telefono/internet, y COMBUSTIBLE/carburante
  (gasoleo, diesel, gasolina). Si es 628, indica subclave_gxx:
  G14 luz/electricidad, G15 agua, G16 gas, G17 telefono/internet, G18 combustible.
- 622 Reparacion y conservacion: talleres, reparacion de vehiculo/maquinaria,
  repuestos, recambios, neumaticos, kit distribucion.
- 631 Tributos: impuestos, tasas (IVTM/impuesto de vehiculos, AEAT, ayuntamiento).
- 623 Servicios profesionales: notario, registro de la propiedad, abogado,
  procurador, gestoria, asesoria, auditor.
- 625 Primas de seguros.  626 Servicios bancarios.  627 Publicidad.
- 621 Arrendamientos y canones (alquiler, renting).
- 624 Transportes y mensajeria.  629 Otros servicios (material de oficina).
- 600 Compras (solo si es mercaderia para revender).
Aplica criterio contable real: p.ej. "bomba de agua" en una factura de taller es
REPARACION (622), no suministro de agua (628)."""

_PROMPT = f"""Eres un experto en contabilidad espanola. Analiza esta factura escaneada.

Identifica las DOS partes de la factura, cada una con su nombre y NIF/CIF:
- EMISOR: quien emite/cobra la factura.
- DESTINATARIO: el cliente que recibe/paga la factura.

{_CRITERIO_CUENTAS}

MUY IMPORTANTE — SOLO LO IMPRESO. Usa siempre los importes IMPRESOS por el
emisor. IGNORA por completo cualquier anotacion manuscrita: totales escritos a
mano, cifras rodeadas con un circulo, lineas tachadas, "NO" junto a un articulo
o el total impreso tachado con una raya. Aunque el total impreso este tachado y
al lado haya otro escrito a mano, devuelve SIEMPRE el impreso.

Devuelve SOLO un JSON con esta estructura exacta:
{{
  "emisor_nombre": "...", "emisor_nif": "...",
  "receptor_nombre": "...", "receptor_nif": "...",
  "num_factura": "...",
  "fecha": "dd/mm/aaaa",
  "fecha_operacion": "dd/mm/aaaa o null",
  "lineas_iva": [{{"base": 0.0, "tipo_iva": 0.0, "cuota_iva": 0.0,
                  "pct_requiv": null, "cuota_requiv": null}}],
  "base_irpf": null, "pct_irpf": null, "cuota_irpf": null,
  "total": 0.0,
  "sustituye_a": null,
  "hay_anotaciones_manuscritas": false,
  "cuenta_gasto": "codigo PGC segun el criterio de arriba (si fuese un gasto)",
  "subclave_gxx": "G14/G15/G16/G17/G18 si cuenta_gasto es 628, si no null",
  "concepto_texto": "descripcion breve del gasto/venta",
  "confianza": "alta/media/baja segun lo legible que este la factura"
}}
Numeros con punto decimal. Si la factura tiene varios tipos de IVA, pon una
entrada por cada tipo en lineas_iva. Si un dato no aparece, usa null.

RECARGO DE EQUIVALENCIA: si la factura desglosa un "Recargo Equivalencia",
"Recargo Equivalent" o "REC.EQUIV", va DENTRO de su linea de lineas_iva
(pct_requiv y cuota_requiv), porque CADA TIPO DE IVA LLEVA SU PROPIO RECARGO:
IVA 21% -> 5,2% ; IVA 10% -> 1,4% ; IVA 4% -> 0,5%. Su base es la misma que la
base de esa linea. Es un impuesto MAS que se suma al total, no un descuento.
Si esa linea no lleva recargo, deja los dos a null.

FACTURA QUE SUSTITUYE A OTRA: si el documento dice que sustituye/anula/rectifica
a otro (p.ej. "Sustituye al doc.n: 4532023141", "POST-FACTURACION", factura
rectificativa), pon en "sustituye_a" el numero del documento al que sustituye.
Si no lo dice, null.

ANOTACIONES A MANO: pon "hay_anotaciones_manuscritas" a true si ves cualquier
cosa escrita a mano sobre la factura (aunque la ignores para los importes), para
que una persona la revise. Las firmas de "RECIBI MERCANCIAS" no cuentan."""


@dataclass
class DatosFactura:
    crudo: dict
    origen: str = ""
    pagina: int = 0


class Extractor:
    def __init__(self, api_key: str, modelos: Optional[List[str]] = None):
        self.client = genai.Client(api_key=api_key)
        self.modelos = modelos or MODELOS

    def _generar(self, img: bytes):
        ultimo = None
        for modelo in self.modelos:
            for intento in range(3):
                try:
                    return self.client.models.generate_content(
                        model=modelo,
                        contents=[types.Part.from_bytes(data=img, mime_type="image/jpeg"),
                                  _PROMPT],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"),
                    )
                except Exception as e:  # 503, rate limit, etc.
                    ultimo = e
                    msg = str(e).lower()
                    if any(k in msg for k in ("credit", "billing", "depleted")):
                        raise SinCredito(
                            "Tu API key no tiene crédito/facturación activa. "
                            "Activa la facturación en aistudio.google.com y añade saldo."
                        ) from e
                    if "503" in msg or "unavailable" in msg or "429" in msg:
                        time.sleep(2 * (intento + 1))
                        continue
                    break
        raise ultimo

    def extraer(self, img: bytes, origen: str = "", pagina: int = 0) -> DatosFactura:
        datos = None
        ultimo_texto = ""
        for _ in range(3):  # Gemini a veces emite JSON invalido; reintentar
            resp = self._generar(img)
            ultimo_texto = resp.text or ""
            datos = _parse_json_tolerante(ultimo_texto)
            if datos is not None:
                break
        if datos is None:
            raise ValueError(
                f"No se pudo leer el JSON de Gemini (pag {pagina}): {ultimo_texto[:200]}")
        return DatosFactura(crudo=datos, origen=origen, pagina=pagina)


def _parse_json_tolerante(texto: str):
    """Intenta parsear el JSON de Gemini, tolerando fallos habituales."""
    if not texto:
        return None
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    t = texto.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    ini, fin = t.find("{"), t.rfind("}")
    if ini != -1 and fin != -1:
        t = t[ini:fin + 1]
    t = re.sub(r",\s*([}\]])", r"\1", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return None


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None
