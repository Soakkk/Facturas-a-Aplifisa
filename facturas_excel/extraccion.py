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
#
# Va FIJADO a gemini-3.7-flash a peticion del usuario (2026-09-02), no al alias
# "gemini-flash-latest": ese alias salta solo al modelo que Google saque, y con
# el saltaria tambien la tarifa y la forma de leer las facturas sin avisar.
# Fijandolo, el dia que cambie algo se ve aqui y se decide.
# Precio (2026-09-02): 0,75 $ / 3,75 $ por millon de tokens; el 1/1/2027 pasa a
# 1,50 / 7,50 -> repasar entonces si compensa frente a gemini-2.5-flash
# (0,30 / 2,50), que tambien leia bien estas facturas.
# Detras van las reservas por si un dia ese modelo se retira o da 503.
MODELOS = ["gemini-3.7-flash", "gemini-flash-latest", "gemini-pro-latest"]


class SinCredito(Exception):
    """La API key no tiene credito / facturacion activa (no reintentar)."""

# Criterio contable que sigue Gemini para proponer el concepto de un GASTO.
# La lista de conceptos NO es libre: es la que ofrece Aplifisa (catalogo en
# config/conceptos_aplifisa.csv). Se le da entera para que elija de ahi y no se
# invente cuentas que luego no existen al importar.
def _lista_conceptos(tipo: str) -> str:
    from .conceptos import catalogo
    return chr(10).join(f"  {c} ({g}) {d}" for c, g, d in catalogo(tipo)
                        if c != "200")


_CRITERIO_CUENTAS = """CONCEPTOS DE GASTO (si la factura es una COMPRA del
cliente). Elige UNO de esta lista EXACTA y devuelve su cuenta y su subclave.
No uses ninguna cuenta que no este aqui:
{conceptos}

CONCEPTOS DE INGRESO (si la factura la EMITE el cliente). Misma norma:
{ingresos}

CRITERIO DE LA ASESORIA (importante):
- COMBUSTIBLE (gasoleo, gasoil, gasolina, diesel, AdBlue) y gasolineras o areas
  de servicio -> 628 (G16) SUMINISTROS GAS. El gasoleo y sus derivados van al
  gas, NO a otros suministros.
- Luz/electricidad -> 628 (G14).  Agua -> 628 (G15).
- Telefono, movil, internet, fibra -> 628 (G17).
- Talleres, reparaciones, recambios, neumaticos -> 622 (G13). Aplica criterio
  real: una "bomba de agua" en una factura de taller es reparacion, no agua.
- Notario, registro, abogado, gestoria, asesoria -> 623 (G19).
- Seguros -> 625 (G20).  Comisiones y gastos de banco -> 626 (G22).
- Alquileres y renting -> 621 (G12).  Publicidad -> 627 (G22).
- Mensajeria y portes -> 624 (G22).  Material de oficina -> 629 (G22).
- Impuestos y tasas municipales (IVTM, basuras) -> 631 (G26).
- Mercaderia para revender -> 600 (G01).
- Si no encaja en ninguno con claridad, usa 629 (G22) OTROS SERVICIOS.
- En los INGRESOS: venta de genero -> 700 (I01); trabajos, obras, reparto,
  alquileres y demas servicios -> 705 (I01); subvenciones -> 740/741/746;
  intereses cobrados -> 760 (I02).""".format(
    conceptos=_lista_conceptos("gasto"), ingresos=_lista_conceptos("ingreso"))

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
  "cuenta_gasto": "cuenta del concepto de GASTO que le corresponderia",
  "subclave_gxx": "la subclave GXX de ESE MISMO concepto (siempre, no solo en la 628)",
  "cuenta_ingreso": "cuenta del concepto de INGRESO que le corresponderia",
  "subclave_ingreso": "la subclave IXX de ese concepto de ingreso",
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

ABONOS Y SIGNO DETRAS DEL NUMERO — CUIDADO, ES FACIL EQUIVOCARSE. Algunos
proveedores (Coca-Cola) imprimen los numeros negativos con el signo menos
DETRAS: "15,51-" significa MENOS 15,51, NO 15,51. Se ve en cantidades ("1,00-"),
importes ("28,20-") y totales ("TOTAL: 15,51- EUROS").
Si la factura es un ABONO / devolucion / rectificativa (sus importes llevan el
menos detras), devuelve TODOS los importes en NEGATIVO con el signo delante:
base, cuota_iva, cuota_requiv y total. NUNCA los pases a positivo: un abono
registrado en positivo cobra al cliente lo que habia que devolverle.

ANOTACIONES A MANO: pon "hay_anotaciones_manuscritas" a true si ves cualquier
cosa escrita a mano sobre la factura (aunque la ignores para los importes), para
que una persona la revise. Las firmas de "RECIBI MERCANCIAS" no cuentan."""


@dataclass
class DatosFactura:
    crudo: dict
    origen: str = ""
    pagina: int = 0
    # Lo que ha costado leer esta factura: el modelo que ha contestado de
    # verdad (el alias 'gemini-flash-latest' cambia solo) y sus tokens.
    modelo: str = ""
    tokens_entrada: int = 0
    tokens_salida: int = 0


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
        modelo, entrada, salida = "", 0, 0
        for _ in range(3):  # Gemini a veces emite JSON invalido; reintentar
            resp = self._generar(img)
            # Los reintentos tambien se pagan: se suman todos.
            m, e, sal = _consumo(resp)
            modelo = m or modelo
            entrada += e
            salida += sal
            ultimo_texto = resp.text or ""
            datos = _parse_json_tolerante(ultimo_texto)
            if datos is not None:
                break
        if datos is None:
            raise ValueError(
                f"No se pudo leer el JSON de Gemini (pag {pagina}): {ultimo_texto[:200]}")
        return DatosFactura(crudo=datos, origen=origen, pagina=pagina,
                            modelo=modelo, tokens_entrada=entrada,
                            tokens_salida=salida)


def _consumo(resp):
    """(modelo real, tokens de entrada, tokens de salida) de una respuesta.

    Se lee con cuidado: si el SDK cambia estos campos, el programa tiene que
    seguir leyendo facturas aunque no pueda contar el gasto.
    """
    modelo = str(getattr(resp, "model_version", "") or "")
    uso = getattr(resp, "usage_metadata", None)

    def _n(nombre):
        try:
            return int(getattr(uso, nombre, 0) or 0)
        except (TypeError, ValueError):
            return 0

    # El "pensamiento" de los modelos nuevos se factura como salida.
    return modelo, _n("prompt_token_count"),         _n("candidates_token_count") + _n("thoughts_token_count")


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
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("€", "").replace(" ", "")
    # Signo DETRAS del numero: Coca-Cola imprime asi los abonos ("15,51-" son
    # MENOS 15,51). Sin esto float() petaba y el importe se perdia entero.
    negativo = t.endswith("-")
    if negativo:
        t = t[:-1]
    if "," in t and "." in t:      # 1.234,56 -> el punto son los miles
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        n = float(t)
    except ValueError:
        return None
    return -n if negativo else n
