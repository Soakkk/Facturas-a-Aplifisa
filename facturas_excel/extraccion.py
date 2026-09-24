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
from dataclasses import dataclass, field
from typing import List, Optional

from google import genai
from google.genai import types

# Modelos de lectura (septiembre de 2026).
#
# Se usan modelos FIJOS, nunca los alias "-latest": un alias salta solo al
# modelo que Google saque, y con el saltarian tambien la tarifa y la forma de
# leer las facturas sin avisar. Hasta la 1.13 el respaldo eran precisamente
# esos alias; ahora el respaldo es otro modelo fijo y los dos se pueden
# cambiar en Configuracion -> Modelos de lectura.
#   - gemini-3.8-flash: el mas preciso para leer documentos escaneados.
#   - gemini-3.7-flash: el anterior; hace de respaldo y de segunda lectura.
MODELO_PRINCIPAL = "gemini-3.8-flash"
MODELO_RESPALDO = "gemini-3.7-flash"
MODELOS = [MODELO_PRINCIPAL, MODELO_RESPALDO]
MODELOS_CONOCIDOS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]

# Doble lectura: "siempre" (cada hoja la leen los dos modelos), "dudosas" (la
# segunda solo si la primera no cuadra, trae un NIF invalido o confianza no
# alta) o "no".
DOBLE_SIEMPRE, DOBLE_DUDOSAS, DOBLE_NO = "siempre", "dudosas", "no"
DOBLE_POR_DEFECTO = DOBLE_SIEMPRE


def modelos_configurados() -> List[str]:
    """[principal, respaldo] segun los ajustes, sin repetir."""
    from . import ajustes
    principal = str(ajustes.leer("modelo_principal", MODELO_PRINCIPAL) or "").strip()
    respaldo = str(ajustes.leer("modelo_respaldo", MODELO_RESPALDO) or "").strip()
    salida = []
    for modelo in (principal or MODELO_PRINCIPAL, respaldo):
        if modelo and modelo not in salida and "latest" not in modelo:
            salida.append(modelo)
    return salida or list(MODELOS)


def modo_doble_lectura() -> str:
    from . import ajustes
    modo = str(ajustes.leer("doble_lectura", DOBLE_POR_DEFECTO) or "")
    return modo if modo in (DOBLE_SIEMPRE, DOBLE_DUDOSAS, DOBLE_NO) \
        else DOBLE_POR_DEFECTO


# Tiempo maximo que se espera a Gemini por pagina. Sin esto una peticion que
# se queda colgada bloquea el hilo PARA SIEMPRE: con 70 paginas el lote se
# quedaba en "69/70" y no terminaba nunca (04/09/2026).
TIEMPO_LIMITE = 90       # segundos


class SinCredito(Exception):
    """La API key no tiene credito / facturacion activa (no reintentar)."""


class TiempoAgotado(Exception):
    """Gemini no contesto a tiempo: esa pagina se da por no leida."""


class ModeloNoDisponible(Exception):
    """El modelo pedido no existe o Google lo ha retirado."""


class ErrorLectura(Exception):
    """Una hoja no se pudo leer; lleva lo que ya se habia pagado por ella."""

    def __init__(self, mensaje: str, consumos=None):
        super().__init__(mensaje)
        self.consumos = list(consumos or [])


def _es_modelo_retirado(e: Exception) -> bool:
    texto = str(e).lower()
    return ("404" in texto or "not_found" in texto or "not found" in texto
            or "no longer available" in texto or "deprecated" in texto) \
        and "model" in texto


def _es_error_de_esquema(e: Exception) -> bool:
    texto = str(e).lower()
    return "400" in texto and ("schema" in texto or "thinking" in texto)


def _es_timeout(e: Exception) -> bool:
    texto = (type(e).__name__ + " " + str(e)).lower()
    return "timeout" in texto or "timed out" in texto

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

MUY IMPORTANTE — LOS IMPORTES, SOLO LOS IMPRESOS. Usa siempre los IMPORTES
impresos por el emisor. IGNORA cualquier importe escrito a mano: totales
manuscritos, cifras rodeadas con un circulo, lineas tachadas, "NO" junto a un
articulo o el total impreso tachado con una raya. Aunque el total impreso este
tachado y al lado haya otro a mano, devuelve SIEMPRE el impreso.

FACTURAS DE VARIAS PAGINAS: la imagen puede ser una hoja intermedia o la ultima
hoja de una factura cuya cabecera estaba en la pagina anterior. Lee tambien el
pie de pagina: si alli se repiten el numero de factura y la fecha, devuelvelos
en num_factura y fecha aunque no aparezca otra cabecera. Extrae de esta hoja el
resumen fiscal (bases, IVA, recargo y total) aunque los datos del destinatario
solo estuvieran en la primera. No inventes las partes que no se vean: dejalas a
null. Indica ademas si la hoja es "unica", "inicio", "intermedia" o "final":
- "inicio": tiene cabecera y lineas de articulos, pero no el resumen fiscal final.
- "intermedia": continua lineas de articulos sin cabecera ni resumen final.
- "final": continua una factura anterior y contiene sus ultimos articulos o el
  resumen fiscal definitivo, aunque no repita numero o destinatario.
- "unica": contiene por si sola cabecera y resumen fiscal definitivo.
No confundas un SUBTOTAL DE ARTICULOS al final de una hoja inicial/intermedia
con la base imponible o el total de la factura. En esas hojas deja lineas_iva y
total vacios/null. El resumen fiscal de la hoja final es el que manda.

EN CAMBIO, EL NIF Y EL NUMERO SI PUEDEN VENIR A MANO. El asesor anota a mano el
CIF/NIF cuando el impreso no se lee o es confuso, y numera las facturas para los
requerimientos de Hacienda. Asi que:
- Si el NIF/CIF impreso falta o esta borroso y hay uno escrito a mano
  (normalmente al pie, tipo "CIF: A78923125"), USA EL ESCRITO A MANO.
- Si el numero de factura impreso falta y hay uno a mano, usalo.
- Esas anotaciones NO son un error de la factura: estan puestas a proposito.

Devuelve SOLO un JSON con esta estructura exacta:
{{
  "emisor_nombre": "...", "emisor_nif": "...",
  "receptor_nombre": "...", "receptor_nif": "...",
  "num_factura": "...",
  "fecha": "dd/mm/aaaa",
  "fecha_operacion": "dd/mm/aaaa o null",
  "estado_pagina_factura": "unica/inicio/intermedia/final",
  "lineas_iva": [{{"base": 0.0, "tipo_iva": 0.0, "cuota_iva": 0.0,
                  "pct_requiv": null, "cuota_requiv": null}}],
  "base_irpf": null, "pct_irpf": null, "cuota_irpf": null,
  "suplidos": null,
  "es_bien_inversion": false,
  "total": 0.0,
  "sustituye_a": null,
  "manuscrito_en_importes": false,
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

SUPLIDOS: si la factura identifica expresamente un importe como "suplidos",
"suplido" o cantidad pagada por cuenta del cliente, devuelve ese importe en
"suplidos". Los suplidos NO forman parte de la base imponible ni llevan IVA,
pero se SUMAN al total a pagar. Copia solamente el importe que figure como tal;
no deduzcas un suplido solo porque haya una diferencia en el total. Si no
aparece identificado, deja "suplidos" a null.

BIENES DE INVERSION: pon "es_bien_inversion" a true SOLO cuando la factura
corresponda claramente a la compra de un inmovilizado duradero (maquinaria,
vehiculo, mobiliario, equipo informatico, inmueble, etc.), no a una reparacion,
recambio, consumible o gasto corriente. Estas facturas se revisan manualmente.

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

ANOTACIONES A MANO: pon "manuscrito_en_importes" a true SOLO si lo escrito a
mano toca a los IMPORTES (un total corregido, una cifra tachada, un articulo
marcado con "NO"): eso si hay que revisarlo. Un CIF anotado, una numeracion o
una firma de "RECIBI MERCANCIAS" NO cuentan: son normales y no se avisa de
ellas."""


def _anulable(tipo: str) -> dict:
    return {"type": [tipo, "null"]}


_LINEA = {
    "type": "object",
    "properties": {
        "base": _anulable("number"), "tipo_iva": _anulable("number"),
        "cuota_iva": _anulable("number"), "pct_requiv": _anulable("number"),
        "cuota_requiv": _anulable("number"),
    },
    "required": ["base", "tipo_iva", "cuota_iva", "pct_requiv", "cuota_requiv"],
}

# Formato CERRADO de la respuesta: los importes llegan como numeros (no como
# "1.234" que puede ser mil doscientos o uno coma dos), las opciones cerradas
# solo pueden ser una de las previstas y no falta ninguna clave.
ESQUEMA = {
    "type": "object",
    "properties": {
        "emisor_nombre": _anulable("string"), "emisor_nif": _anulable("string"),
        "receptor_nombre": _anulable("string"),
        "receptor_nif": _anulable("string"),
        "num_factura": _anulable("string"), "fecha": _anulable("string"),
        "fecha_operacion": _anulable("string"),
        "estado_pagina_factura": {
            "type": "string", "enum": ["unica", "inicio", "intermedia", "final"]},
        "lineas_iva": {"type": "array", "items": _LINEA},
        "base_irpf": _anulable("number"), "pct_irpf": _anulable("number"),
        "cuota_irpf": _anulable("number"), "suplidos": _anulable("number"),
        "es_bien_inversion": {"type": "boolean"},
        "total": _anulable("number"),
        "sustituye_a": _anulable("string"),
        "manuscrito_en_importes": {"type": "boolean"},
        "cuenta_gasto": _anulable("string"), "subclave_gxx": _anulable("string"),
        "cuenta_ingreso": _anulable("string"),
        "subclave_ingreso": _anulable("string"),
        "concepto_texto": _anulable("string"),
        "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
    },
}
ESQUEMA["required"] = list(ESQUEMA["properties"])


@dataclass
class DatosFactura:
    crudo: dict
    origen: str = ""
    pagina: int = 0
    # Lo que ha costado leer esta factura: el modelo que ha contestado de
    # verdad y sus tokens (suma de todas las llamadas).
    modelo: str = ""
    tokens_entrada: int = 0
    tokens_salida: int = 0
    # (modelo, tokens de entrada, tokens de salida) de CADA llamada: con la
    # doble lectura hay dos modelos con tarifas distintas.
    consumos: list = field(default_factory=list)


class Extractor:
    def __init__(self, api_key: str, modelos: Optional[List[str]] = None,
                 modo_doble: Optional[str] = None):
        self.client = genai.Client(
            api_key=api_key,
            # El SDK lo quiere en milisegundos.
            http_options=types.HttpOptions(timeout=TIEMPO_LIMITE * 1000))
        self.modelos = list(modelos or modelos_configurados())
        self.modo_doble = modo_doble or modo_doble_lectura()
        self._con_esquema = True
        # Modelos que Google ha dado por retirados: no se vuelven a pedir en
        # las siguientes hojas del mismo bloque.
        self._retirados: set = set()

    # ------------------------------------------------------------ llamadas
    def _config(self):
        if not self._con_esquema:
            return types.GenerateContentConfig(
                response_mime_type="application/json")
        return types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=ESQUEMA,
            # LOW: estos modelos no admiten MINIMAL y la temperatura se
            # ignora. Pensar poco basta para copiar datos y va mas rapido.
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW))

    def _llamar(self, modelo: str, img: bytes):
        """Una respuesta de ese modelo, con reintentos solo ante saturacion."""
        ultimo = None
        for intento in range(3):
            try:
                return self.client.models.generate_content(
                    model=modelo,
                    contents=[types.Part.from_bytes(data=img, mime_type="image/jpeg"),
                              _PROMPT],
                    config=self._config(),
                )
            except Exception as e:  # 503, rate limit, etc.
                ultimo = e
                msg = str(e).lower()
                if any(k in msg for k in ("credit", "billing", "depleted")):
                    raise SinCredito(
                        "Tu API key no tiene crédito/facturación activa. "
                        "Activa la facturación en aistudio.google.com y añade saldo."
                    ) from e
                if _es_modelo_retirado(e):
                    raise ModeloNoDisponible(
                        f"El modelo {modelo} no está disponible: {e}") from e
                if self._con_esquema and _es_error_de_esquema(e):
                    # Un modelo que no admita el formato cerrado sigue
                    # leyendo con el formato libre de siempre.
                    self._con_esquema = False
                    continue
                if _es_timeout(e):
                    # Un tiron de red se reintenta una vez; si vuelve a
                    # colgarse, esta pagina se marca y el lote sigue.
                    if intento == 0:
                        continue
                    raise TiempoAgotado(
                        f"Gemini no contestó en {TIEMPO_LIMITE} segundos "
                        f"(se intentó dos veces).") from e
                if "503" in msg or "unavailable" in msg or "429" in msg:
                    time.sleep(2 * (intento + 1))
                    continue
                raise
        raise ultimo

    def _generar(self, img: bytes):
        """Respuesta del primer modelo que conteste (principal, luego respaldo)."""
        ultimo = None
        for modelo in self._disponibles():
            try:
                return self._llamar(modelo, img)
            except (SinCredito, TiempoAgotado):
                raise
            except ModeloNoDisponible as e:
                self._retirados.add(modelo)
                ultimo = e
            except Exception as e:
                ultimo = e
        raise ultimo

    def _leer_con(self, modelo: str, img: bytes, pagina: int):
        """(datos, modelo real, consumos) de un modelo concreto."""
        consumos = []
        ultimo_texto = ""
        for _ in range(3):  # Gemini a veces emite JSON invalido; reintentar
            try:
                resp = self._llamar(modelo, img)
            except (SinCredito, ModeloNoDisponible):
                raise
            except Exception as e:
                raise ErrorLectura(str(e), consumos) from e
            # Los reintentos tambien se pagan: se suman todos.
            real, entrada, salida = _consumo(resp)
            consumos.append((real or modelo, entrada, salida))
            ultimo_texto = resp.text or ""
            datos = _parse_json_tolerante(ultimo_texto)
            if isinstance(datos, dict):
                return datos, (real or modelo), consumos
        raise ErrorLectura(
            f"No se pudo leer el JSON de Gemini (pag {pagina}): "
            f"{ultimo_texto[:200]}", consumos)

    def _disponibles(self) -> List[str]:
        return [m for m in self.modelos if m not in self._retirados]

    def _leer_uno(self, img: bytes, pagina: int, empezar_por: int = 0):
        """Lee con el primer modelo disponible, saltando los retirados."""
        disponibles = self._disponibles()[empezar_por:]
        ultimo = None
        consumos = []
        for modelo in disponibles:
            try:
                datos, real, gastado = self._leer_con(modelo, img, pagina)
                return datos, real, consumos + gastado
            except ModeloNoDisponible as e:
                self._retirados.add(modelo)
                ultimo = e
            except ErrorLectura as e:
                consumos.extend(e.consumos)
                ultimo = e
        if ultimo is None:
            ultimo = ModeloNoDisponible("No hay ningún modelo de lectura disponible.")
        raise ErrorLectura(str(ultimo), consumos)

    # --------------------------------------------------------------- lectura
    def extraer(self, img: bytes, origen: str = "", pagina: int = 0) -> DatosFactura:
        from .doble_lectura import combinar, es_dudosa

        disponibles = self._disponibles()
        modo = self.modo_doble if len(disponibles) >= 2 else DOBLE_NO
        consumos: list = []

        if modo == DOBLE_SIEMPRE:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as ex:
                futuros = [ex.submit(self._leer_con, m, img, pagina)
                           for m in disponibles[:2]]
                resultados = []
                for modelo, fut in zip(disponibles[:2], futuros):
                    try:
                        datos, real, gastado = fut.result()
                        consumos.extend(gastado)
                        resultados.append((datos, real, ""))
                    except SinCredito:
                        raise
                    except ModeloNoDisponible as e:
                        self._retirados.add(modelo)
                        resultados.append((None, modelo, str(e)))
                    except ErrorLectura as e:
                        consumos.extend(e.consumos)
                        resultados.append((None, modelo, str(e)))
            (d1, m1, e1), (d2, m2, e2) = resultados
            if d1 is None and d2 is None:
                raise ErrorLectura(e1 or e2, consumos)
            if d1 is None:
                crudo = combinar(d2, None, m2, "", error_2=e1)
            elif d2 is None:
                crudo = combinar(d1, None, m1, "", error_2=e2)
            else:
                crudo = combinar(d1, d2, m1, m2)
        else:
            d1, m1, gastado = self._leer_uno(img, pagina)
            consumos.extend(gastado)
            crudo = combinar(d1, None, m1, "")
            if modo == DOBLE_DUDOSAS and es_dudosa(d1):
                otro = next((m for m in self._disponibles() if m != self._base(m1)), None)
                if otro:
                    try:
                        d2, m2, gastado = self._leer_con(otro, img, pagina)
                        consumos.extend(gastado)
                        crudo = combinar(d1, d2, m1, m2)
                    except SinCredito:
                        raise
                    except (ErrorLectura, ModeloNoDisponible) as e:
                        consumos.extend(getattr(e, "consumos", []))
                        crudo = combinar(d1, None, m1, "", error_2=str(e))

        return DatosFactura(
            crudo=crudo, origen=origen, pagina=pagina,
            modelo=crudo.get("_modelo_1", ""),
            tokens_entrada=sum(c[1] for c in consumos),
            tokens_salida=sum(c[2] for c in consumos),
            consumos=consumos)

    def _base(self, modelo_real: str) -> str:
        """El modelo configurado al que corresponde un nombre real con cola."""
        real = str(modelo_real or "").replace("models/", "")
        return next((m for m in self.modelos if real.startswith(m)), real)


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
