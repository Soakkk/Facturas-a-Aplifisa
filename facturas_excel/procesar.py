"""Nucleo de procesamiento de un lote de facturas ya extraidas por Gemini.

- Autodetecta el CLIENTE de la asesoria: el NIF que aparece en (casi) todas las
  facturas del lote (como destinatario en los gastos y emisor en las ventas).
- Para cada factura decide GASTO/VENTA, elige la CONTRAPARTE (la otra parte) y
  la CUENTA contable, y construye las Factura (una por linea de IVA).
- Completa los NIF ilegibles copiandolos de otra factura del mismo proveedor
  (ver propagar_nifs).

Reutilizable desde la UI y desde scripts.
"""

from __future__ import annotations

from copy import deepcopy
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from . import clientes, proveedores
from .conceptos import (
    DEFAULT_GASTO, DEFAULT_GASTO_GXX, asignar_concepto_con_origen, es_valido,
    normalizar_concepto, subclave_628, subclaves_de,
)
from .extraccion import _num
from .modelo import Factura
from .sanear_lectura import aviso_saneado
from .validacion import fecha_de, normalizar_fecha, validar_nif
from .texto import limpiar, reparar, tiene_invisibles, visible


def normaliza_nif(nif) -> str:
    if not nif:
        return ""
    # NFKC: las cifras y letras «de ancho completo» (１２３４５６７８Ｚ, de un PDF
    # asiático o una lectura rara) pasan a las normales. Si no, el DNI pasaba
    # el control de la letra y llegaba así al Excel, en verde.
    nif = unicodedata.normalize("NFKC", str(nif))
    return nif.strip().upper().replace(".", "").replace(" ", "").replace("-", "")


def _tokens_nombre(nombre) -> set:
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


@dataclass
class Candidato:
    """Una de las dos partes que salen en las facturas del lote."""
    nif: str
    nombre: str
    veces: int = 0
    como_emisor: int = 0
    como_receptor: int = 0
    cliente_confirmado: bool = False   # una persona dijo que es cliente
    proveedor_conocido: bool = False   # ya se le ha comprado otras veces
    # Todas sus lecturas traían un carácter invisible y no se pudo recuperar
    # la letra: el nombre (limpio) no se guarda ni se comparte con la suite.
    nombre_roto: bool = False

    @property
    def puntos(self) -> int:
        """Lo que dice a favor (o en contra) de que sea EL cliente del lote."""
        return (1000 * self.cliente_confirmado
                - 500 * self.proveedor_conocido
                + self.veces)

    @property
    def papel(self) -> str:
        if self.como_emisor and not self.como_receptor:
            return "siempre emite"
        if self.como_receptor and not self.como_emisor:
            return "siempre recibe"
        return f"emite {self.como_emisor}, recibe {self.como_receptor}"


@dataclass
class Analisis:
    candidatos: List["Candidato"]
    dudoso: bool
    # Por qué: empate entre dos partes, o un homónimo del cliente confirmado
    # con otro NIF válido (1.25).
    homonimo: bool = False
    empate: bool = False

    @property
    def mejor(self) -> "Candidato | None":
        return self.candidatos[0] if self.candidatos else None


def analizar_cliente(lista_datos: List[dict]) -> Analisis:
    """Quien es el cliente de la asesoria en este lote, y con que seguridad.

    El "NIF que mas se repite" NO basta: un taco de facturas de la misma
    gasolinera tiene las dos partes repetidas EXACTAMENTE las mismas veces, y
    entonces se elegia una al azar (y salia el proveedor como cliente, con todo
    lo demas del reves). Por eso se mira ademas:
      - si a alguno ya lo confirmo una persona como cliente (manda),
      - si a alguno se le conoce como proveedor (entonces no es el cliente),
      - y si aun asi hay empate, se marca DUDOSO para preguntarlo.
    """
    cuenta: Dict[str, Candidato] = {}
    nombres: Dict[str, list] = defaultdict(list)
    homonimo = False
    # Los clientes y los proveedores, leídos una vez para todo el lote (no
    # por cada nombre o NIF leído: con 450 hojas era casi un segundo por
    # bloque, y más cuantos más clientes y proveedores hubiera guardados).
    directorio = clientes.Directorio()
    for d in lista_datos:
        # Solo los NIF y nombres que son texto (ver _partes_de).
        d = _partes_de(d)
        for campo_nif, campo_nom, papel in (
                ("emisor_nif", "emisor_nombre", "e"),
                ("receptor_nif", "receptor_nombre", "r")):
            leido = normaliza_nif(d.get(campo_nif))
            nombre_leido, roto = limpiar(d.get(campo_nom))
            nombre_leido = nombre_leido or ""
            # Para elegir el nombre, el roto tal cual: así gana una lectura
            # buena y, si no la hay, se intenta recuperar la letra.
            para_elegir = str(d.get(campo_nom)) if roto else nombre_leido
            conocido = directorio.buscar_por_nombre(nombre_leido)
            if conocido and validar_nif(leido) and leido != conocido[0]:
                # El nombre de un cliente confirmado con OTRO NIF válido: o es
                # su NIF mal leído, o es otra persona que se llama igual (un
                # homónimo). No se decide en silencio: los dos son candidatos
                # y se pregunta (si no, el lote entero se iba a otro cliente).
                homonimo = True
                otro = cuenta.setdefault(leido, Candidato(nif=leido, nombre=""))
                otro.veces += 1
                if papel == "e":
                    otro.como_emisor += 1
                else:
                    otro.como_receptor += 1
                nombres[leido].append(para_elegir)
            nif = conocido[0] if conocido else leido
            if not nif:
                continue
            c = cuenta.setdefault(nif, Candidato(nif=nif, nombre=""))
            c.veces += 1
            if papel == "e":
                c.como_emisor += 1
            else:
                c.como_receptor += 1
            if conocido and conocido[1]:
                nombres[nif].append(conocido[1])
            elif nombre_leido:
                nombres[nif].append(para_elegir)

    nifs_proveedores = _nifs_de_proveedores() if cuenta else set()
    for nif, c in cuenta.items():
        c.nombre, c.nombre_roto = _nombre_leido_de(nif, nombres.get(nif, []))
        c.cliente_confirmado = directorio.es_confirmado(nif)
        # El nombre con el que ya se le conoce (aqui o en la suite) manda
        # sobre las variantes leidas en las facturas.
        confirmado = directorio.nombre_confirmado(nif)
        if confirmado:
            c.nombre, c.nombre_roto = confirmado, False
        c.proveedor_conocido = nif in nifs_proveedores

    # Con empate se propone al que RECIBE las facturas: un taco de facturas
    # iguales suele ser de compras (gasolinera, proveedor de la tienda...). Es
    # solo la propuesta del dialogo; decide la persona, y se recuerda.
    orden = sorted(cuenta.values(),
                   key=lambda c: (-c.puntos, -c.como_receptor, c.nif))
    empate = len(orden) > 1 and orden[0].puntos == orden[1].puntos
    return Analisis(candidatos=orden, dudoso=homonimo or empate,
                    homonimo=homonimo, empate=empate)


def _partes_de(datos) -> dict:
    """Los NIF y nombres de una hoja, solo si son texto: una lista, un número
    o un dict (lectura rara de una sesión vieja) no cuentan para decidir el
    cliente. Una lista rompía después el recuento de nombres y se perdía el
    bloque entero."""
    if not isinstance(datos, dict):
        return {}
    return {campo: datos[campo] for campo in (
        "emisor_nif", "emisor_nombre", "receptor_nif", "receptor_nombre")
        if isinstance(datos.get(campo), str)}


def _nombre_leido_de(nif: str, lista: list) -> tuple:
    """(nombre, roto) de una parte del lote: el más leído de las lecturas
    buenas; si todas traen un carácter invisible, el recuperado con lo que ya
    se conoce de ese NIF o, si no se puede, el limpio marcado como roto."""
    buenos = [n for n in lista if not tiene_invisibles(n)]
    if buenos:
        return Counter(buenos).most_common(1)[0][0], False
    if not lista:
        return "", False
    roto = Counter(lista).most_common(1)[0][0]
    recuperado = reparar(roto, _nombres_conocidos(nif))
    return (recuperado, False) if recuperado else (limpiar(roto)[0], True)


def _nifs_de_proveedores() -> set:
    """Los NIF de todos los proveedores guardados: si ya se le ha comprado
    alguna vez, no es el cliente de la asesoria. (Antes se miraba por cada
    candidato, primero la ficha de su nombre y luego todas, leyendo la base
    dos veces; la de su nombre es una de todas: sale lo mismo.)"""
    return {normaliza_nif(f.get("nif")) for f in proveedores.leer_todo().values()
            if isinstance(f, dict)}


def detectar_cliente(lista_datos: List[dict]) -> Tuple[str, str]:
    """(nombre, nif) del cliente del lote. Compatible con lo de siempre."""
    try:
        mejor = analizar_cliente(lista_datos).mejor
    except Exception:
        # Una hoja rara no tira el bloque (25 hojas ya pagadas): se busca
        # el cliente con las hojas que se pueden analizar, una a una.
        _apuntar_hoja_rara("buscar el cliente del bloque")
        mejor = analizar_cliente(
            [d for d in lista_datos if _se_puede_analizar(d)]).mejor
    return (mejor.nombre, mejor.nif) if mejor else ("", "")


def _se_puede_analizar(datos) -> bool:
    try:
        analizar_cliente([datos])
        return True
    except Exception:
        return False


@dataclass
class FacturaProcesada:
    tipo: str                 # "gasto" / "venta"
    facturas: List[Factura]   # una por linea de IVA
    cuenta: str
    gxx: str | None
    origen: str
    pagina: int
    aviso: str = ""           # rol emisor/destinatario dudoso, etc.
    sustituye_a: str = ""     # nº del documento al que sustituye, si lo dice
    sustituida_por: str = ""  # nº de la factura del lote que la sustituye a ella
    conflicto_nif: dict | None = None  # guardado frente a otra lectura válida


TOLERANCIA_CUADRE = 0.02  # euros de margen por redondeos


def _cuadre_factura(facturas: List[Factura]) -> str:
    """Comprueba el total sumando TODAS las lineas de IVA de la factura.

    Con varios tipos de IVA ninguna fila cuadra ella sola con el total impreso
    (cada una es un trozo), asi que el cuadre hay que hacerlo aqui, una vez.
    """
    if len(facturas) < 2:
        return ""  # una sola linea: ya lo comprueba validacion.validar
    total = facturas[0].total_impreso
    if total is None:
        return ""
    suma = sum((f.base_iva or 0) + (f.cuota_iva or 0) + (f.cuota_requiv or 0)
               for f in facturas)
    suma -= facturas[0].cuota_irpf or 0
    if abs(round(suma, 2) - total) <= TOLERANCIA_CUADRE:
        return ""
    return (f"El total no cuadra: la factura pone {total:.2f} y sus "
            f"{len(facturas)} líneas de IVA suman {suma:.2f}.")


def _redondeo_de_lineas(base, pct, suma) -> float:
    """Lo que `suma` (las cuotas de las líneas juntadas, cada una cuadrando
    sola) se aparta de base×% de la fila, en el sentido de la base."""
    if base is None or pct is None or suma is None:
        return 0.0
    return round((suma - round(base * pct / 100.0, 2))
                 * (-1 if base < 0 else 1), 6)


def apuntar_juntadas(f: Factura, linea: dict) -> None:
    """Lo que validar necesita saber de una línea de IVA que suma varias
    leídas (sanear_lectura.juntar_por_tipo): cuántas son y el redondeo exacto
    de sus cuotas, línea a línea. Con una línea sin juntar, nada (y se olvida
    lo que hubiera: la fila deja de ser una suma)."""
    juntadas = linea.get("_juntadas")
    if not (isinstance(juntadas, int) and not isinstance(juntadas, bool)
            and juntadas > 1):
        f.lineas_juntadas = 1
        f.redondeo_lineas_iva = f.redondeo_lineas_requiv = 0.0
        return
    base = _num(linea.get("base"))
    f.lineas_juntadas = juntadas
    f.redondeo_lineas_iva = _redondeo_de_lineas(
        base, _num(linea.get("tipo_iva")), _num(linea.get("_cuota_lineas")))
    f.redondeo_lineas_requiv = _redondeo_de_lineas(
        base, _num(linea.get("pct_requiv")), _num(linea.get("_requiv_lineas")))


def normalizar_importes_abono(facturas: List[Factura]) -> bool:
    """Pone en negativo todos los importes cuando el total identifica un abono.

    El total impreso es la prueba más inequívoca. Algunos documentos muestran
    el menos solo en el total o Gemini lo pierde en una de las bases/cuotas;
    dejar signos mezclados convertiría parte de la devolución en gasto.
    """
    totales = [f.total_impreso for f in facturas
               if f.total_impreso is not None]
    if not totales or not any(total < 0 for total in totales):
        return False
    campos = (
        "base_iva", "cuota_iva", "base_irpf", "cuota_irpf",
        "base_requiv", "cuota_requiv", "suplidos", "base_sujeta_cero",
        "no_sujeta", "total_impreso",
    )
    for factura in facturas:
        for campo in campos:
            valor = getattr(factura, campo)
            if valor is not None:
                setattr(factura, campo, -abs(valor))
    return True


def concepto_gasto(datos: dict) -> tuple[str, str | None]:
    """Cuenta de gasto propuesta, reutilizable al corregir un abono."""
    cuenta, gxx, _aviso = concepto_propuesto("gasto", datos)
    return cuenta, gxx


def _unica_subclave(cuenta) -> str | None:
    posibles = subclaves_de(cuenta)
    return posibles[0][0] if len(posibles) == 1 else None


def concepto_propuesto(tipo: str, datos: dict) -> tuple[str, str | None, str]:
    """(cuenta, subclave, aviso) de la factura, sin inventar en silencio.

    Manda la cuenta que Gemini ha elegido del catalogo. Si la cuenta es buena
    pero su subclave no existe, se corrige SOLO la subclave cuando la cuenta
    no tiene mas que una (705 -> I01): antes se cambiaba la cuenta entera y
    un servicio (705) acababa como venta de genero (700) sin avisar.
    Cuando Gemini no propone nada valido, las palabras clave o la cuenta de
    descarte dan una propuesta, pero la fila queda en ambar con el motivo.
    """
    lado = "gasto" if tipo == "gasto" else "ingreso"
    campo_cuenta, campo_gxx = (("cuenta_gasto", "subclave_gxx") if lado == "gasto"
                               else ("cuenta_ingreso", "subclave_ingreso"))
    cuenta, gxx = normalizar_concepto(datos.get(campo_cuenta),
                                      datos.get(campo_gxx))
    texto = f"{datos.get('concepto_texto', '')} {datos.get('emisor_nombre', '')}"
    if lado == "ingreso":
        texto = f"{datos.get('concepto_texto', '')}"
    del_catalogo = {c for c, _, _ in catalogo_de(lado)}
    if cuenta and cuenta in del_catalogo:
        if gxx and not es_valido(cuenta, gxx):
            unica = _unica_subclave(cuenta)
            if unica:
                return (cuenta, unica,
                        f"La subclave {gxx} no existe para la {cuenta}: se ha "
                        f"puesto {unica}, la única que admite.")
            if cuenta == "628":
                gxx = subclave_628(texto)
            else:
                gxx = None
        if not gxx:
            gxx = _unica_subclave(cuenta) or (
                subclave_628(texto) if cuenta == "628" else None)
        return cuenta, gxx, ""

    propuesta, origen = asignar_concepto_con_origen(
        "gasto" if lado == "gasto" else "venta", texto)
    gxx = None
    if propuesta == "628":
        gxx = subclave_628(texto)
    if propuesta == DEFAULT_GASTO and lado == "gasto" and origen == "defecto":
        gxx = DEFAULT_GASTO_GXX
    gxx = gxx or _unica_subclave(propuesta)
    leida = f" (Gemini propuso «{cuenta}», que no es de {lado})" if cuenta else ""
    if origen == "palabras":
        aviso = (f"Cuenta {propuesta} propuesta por palabras clave{leida}: "
                 "compruebe el concepto.")
    else:
        aviso = (f"Cuenta {propuesta} puesta por descarte{leida}: no se ha "
                 "podido determinar el concepto. Elija la cuenta correcta.")
    return propuesta, gxx, aviso


def catalogo_de(lado: str):
    from .conceptos import catalogo
    return catalogo(lado)


def _opcion(valor) -> Optional[str]:
    """Una opción cerrada de la lectura, sin las que no dicen nada."""
    texto = str(valor or "").strip().lower()
    return None if texto in ("", "ninguna", "no", "factura", "null") else texto


# Lo justo para identificar la factura (criterio del usuario, 09/10/2026): un
# número o un nombre larguísimo casi siempre es una lectura desbocada, y no
# hace falta entero para el registro. Topes generosos: una factura de verdad
# no llega (Aplifisa ya recorta el nombre a 40 al exportar). El nombre es la
# clave de la memoria de proveedores: a 60 dejaban de encontrarse los nombres
# largos guardados enteros (comunidades de propietarios…).
# El número, hasta 60: lo que admite el SII (NumSerieFacturaEmisor). Con
# menos se recortaba uno de verdad, que ya no casaba con el exportado entero
# por la 1.24.0 (ni «ya exportada» ni el cuadre).
MAX_NUMERO = 60
MAX_NOMBRE_LEIDO = 120
MAX_NIF = 20


def _nombres_conocidos(nif) -> list:
    """Los nombres que ya se conocen de este NIF (memoria y clientes)."""
    nif = normaliza_nif(nif)
    if not nif:
        return []
    nombres = [f.get("nombre") for f in proveedores.leer_todo().values()
               if isinstance(f, dict) and normaliza_nif(f.get("nif")) == nif]
    try:
        nombres.append(clientes.nombre_confirmado(nif))
        nombres.append(clientes.nombre_guardado(nif))
    except Exception:       # el directorio de la suite puede no estar
        pass
    return [n for n in nombres if n]


def _claves_de_la_124() -> dict:
    """{clave de hoy: ficha} de los NIF que la 1.24.0 guardó con una clave
    que hoy ya no sale al leer (nombre roto en la clave, o nombre más largo
    que MAX_NOMBRE_LEIDO). Si dos NIF distintos dan la misma clave, ninguno."""
    salida, dudosas = {}, set()
    for k, ficha in proveedores.leer_todo().items():
        if not ficha.get("nif"):
            continue
        nombre = str(ficha.get("nombre") or "")
        claves = {clave_proveedor(limpiar(k)[0])} if tiene_invisibles(k) else set()
        if clave_proveedor(nombre) == k:
            claves.add(clave_proveedor(acotar_nombre(limpiar(nombre)[0])))
        for otra in claves - {k, ""}:
            previa = salida.setdefault(otra, ficha)
            if normaliza_nif(previa.get("nif")) != normaliza_nif(ficha.get("nif")):
                dudosas.add(otra)
    return {k: v for k, v in salida.items() if k not in dudosas}


def acotar_numero(valor) -> str:
    """El número de factura con lo que la identifica: si es demasiado largo,
    el principio (el nº o la serie) y el final (el contador), con «...» en
    medio. Quedarse solo con el final juntaba facturas distintas («0007/2026
    MANTENIMIENTO…» y «0008/2026 MANTENIMIENTO…») en el mismo nº."""
    texto = " ".join(limpiar(str(valor or ""))[0].split())
    if len(texto) <= MAX_NUMERO:
        return texto
    cabeza = (MAX_NUMERO - 3) // 2
    return (f"{texto[:cabeza].rstrip()}..."
            f"{texto[cabeza + 3 - MAX_NUMERO:].lstrip()}")


def _es_el_cliente(nombre_leido, cliente_nombre) -> bool:
    """Si el nombre leído es el del cliente, aunque traiga una letra rota: el
    del lote ya llega limpio (o reparado) y el leído no."""
    limpio, roto = limpiar(nombre_leido)
    return _mismo_nombre(limpio, cliente_nombre) or bool(
        roto and cliente_nombre and reparar(nombre_leido, [cliente_nombre]))


def acotar_nombre(valor) -> str:
    """El nombre, sin pasar de MAX_NOMBRE_LEIDO; corta por palabra entera si
    apenas se pierde nada."""
    texto = " ".join(str(valor or "").split())
    if len(texto) <= MAX_NOMBRE_LEIDO:
        return texto
    corte = texto[:MAX_NOMBRE_LEIDO]
    hueco = corte.rfind(" ")
    if hueco >= MAX_NOMBRE_LEIDO - 12:
        corte = corte[:hueco]
    return corte.rstrip(" ,.-")


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
        es_emisor = _es_el_cliente(e_nom, cliente_nombre)
        es_receptor = _es_el_cliente(r_nom, cliente_nombre)
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

    # Un nombre coincidente no confirma un NIF explícito de otra persona.
    for rol, nom, leido in (("emisor", e_nom, e_nif),
                            ("destinatario", r_nom, r_nif)):
        if (_es_el_cliente(nom, cliente_nombre) and leido != cliente_nif
                and validar_nif(leido)):
            aviso = f"{aviso} El nombre del cliente coincide con el {rol}, " \
                    f"pero su NIF {leido} es distinto del cliente seleccionado " \
                    f"({cliente_nif}). Confirma cliente y rol antes de importar.".strip()
    aviso = f"{aviso} {aviso_saneado(datos)}".strip()
    if datos.get("_error"):
        aviso = f"{aviso} HOJA NO LEÍDA: {datos['_error']}. Vuelva a pasar " \
                "esta hoja; no se ha rellenado ningún dato.".strip()
    if datos.get("_union_inferida"):
        paginas = ", ".join(str(p) for p in datos.get("_paginas_union_inferida", []))
        aviso = f"{aviso} Unión inferida de páginas {paginas}: " \
                f"{datos.get('_motivo_union_inferida', 'continuidad de hojas')}. " \
                "Comprueba que pertenecen a la misma factura.".strip()

    # Cuenta contable: la del catalogo que elige Gemini. Si no la hay, una
    # propuesta, pero con aviso (nunca una cuenta por descarte en verde).
    cuenta, gxx, aviso_cuenta = concepto_propuesto(tipo, datos)
    if datos.get("es_bien_inversion") and tipo == "gasto" and es_valido("200", "200"):
        # Un inmovilizado va a la 200 (amortización, casillas propias del
        # 303), no a la cuenta de gasto: queda en ámbar para confirmarlo.
        cuenta, gxx, aviso_cuenta = "200", "200", ""
    if aviso_cuenta:
        aviso = f"{aviso} {aviso_cuenta}".strip()

    # Un nombre con un carácter invisible (una tilde mal copiada de un PDF):
    # se recupera con los nombres ya conocidos de ese NIF; si no se puede, se
    # quita el carácter y se avisa para escribirlo bien.
    nombre_limpio, roto = limpiar(nombre)
    sin_letra = False
    if roto:
        recuperado = reparar(nombre, _nombres_conocidos(nif))
        if recuperado:
            nombre_limpio = recuperado
        else:
            sin_letra = True
            aviso = (f"{aviso} El nombre «{visible(nombre)}» traía un carácter "
                     "que no se ve (una letra con tilde mal leída): escríbalo "
                     "bien y se recordará.").strip()
    nombre = nombre_limpio
    num_leido = " ".join(limpiar(str(datos.get("num_factura") or ""))[0].split())
    if len(num_leido) > MAX_NUMERO:
        aviso = (f"{aviso} El nº de factura leído es muy largo («{num_leido[:60]}"
                 f"{'…' if len(num_leido) > 60 else ''}»): se ha acortado. "
                 "Compruébelo.").strip()

    # Construir Factura (una por linea de IVA)
    lineas = datos.get("lineas_iva") or [{}]
    comun = dict(
        documento_id=uuid4().hex,
        num_factura=acotar_numero(datos.get("num_factura")) or None,
        fecha=normalizar_fecha(datos.get("fecha")) or None,
        fecha_operacion=normalizar_fecha(datos.get("fecha_operacion")) or None,
        nombre=acotar_nombre(nombre) or None,
        # El NIF, siempre limpio: el mismo proveedor viene unas veces
        # "A-82018474" y otras "A82018474", y con el guion se contaba como otro
        # distinto (ni se detectaba el duplicado ni valia la memoria de NIF).
        nif=normaliza_nif(nif)[:MAX_NIF] or None,
        concepto=cuenta or None,
        total_impreso=_num(datos.get("total")),
        origen_imagen=origen,
        pagina_origen=pagina,
        ultima_pagina_origen=int(
            datos.get("_ultima_pagina_consolidada", pagina) or pagina),
        confianza_ia=(str(datos.get("confianza") or "").strip().lower()
                      or None),
        tratamiento_manual=("Bien de inversión"
                            if datos.get("es_bien_inversion") else None),
        tipo_documento=_opcion(datos.get("tipo_documento")),
        moneda=(str(datos.get("moneda") or "").strip().upper()[:10] or None),
        mencion_iva=_opcion(datos.get("mencion_iva")),
        posible_no_deducible=_opcion(datos.get("posible_no_deducible")),
        # Un gasto sin el NIF del cliente impreso (un tique): sin él, el IVA
        # no se puede deducir (art. 97 de la Ley del IVA).
        sin_nif_destinatario=(tipo == "gasto" and not r_nif
                              and not datos.get("_error")),
        rectifica_a=acotar_numero(datos.get("sustituye_a")),
        nombre_sin_letra=(acotar_nombre(nombre) if sin_letra else ""),
    )
    facturas = []
    for i, linea in enumerate(lineas):
        f = Factura(**comun)
        f.lineas_factura = len(lineas)
        f.base_iva = _num(linea.get("base"))
        f.pct_iva = _num(linea.get("tipo_iva"))
        f.cuota_iva = _num(linea.get("cuota_iva"))
        apuntar_juntadas(f, linea)
        # CADA tipo de IVA lleva su propio recargo (21->5,2 / 10->1,4 / 4->0,5),
        # y su base es la de esa linea. Los campos sueltos de nivel factura son
        # el respaldo para cuando Gemini los devuelve al viejo estilo.
        f.pct_requiv = _num(linea.get("pct_requiv"))
        f.cuota_requiv = _num(linea.get("cuota_requiv"))
        if f.pct_requiv is None and f.cuota_requiv is None and i == 0:
            f.pct_requiv = _num(datos.get("pct_requiv"))
            f.cuota_requiv = _num(datos.get("cuota_requiv"))
        if f.pct_requiv is not None or f.cuota_requiv is not None:
            f.base_requiv = _num(datos.get("base_requiv")) if len(lineas) == 1 \
                else f.base_iva
            if f.base_requiv is None:
                f.base_requiv = f.base_iva
        if i == 0:
            # La retencion es una sola por factura, no por linea de IVA.
            f.base_irpf = _num(datos.get("base_irpf"))
            f.pct_irpf = _num(datos.get("pct_irpf"))
            f.cuota_irpf = _num(datos.get("cuota_irpf"))
        facturas.append(f)

    # EL SUPLIDO ES OTRA LINEA DEL MISMO APUNTE (criterio del usuario,
    # 2026-09-02, con su pantalla de Aplifisa delante): se registra como una
    # segunda BASE IMPONIBLE sin % ni cuota de IVA, repitiendo fecha, numero,
    # nombre y concepto. No va en la columna Suplidos.
    suplido = _num(datos.get("suplidos"))
    if suplido and facturas:
        for f in facturas:
            f.tratamiento_manual = "Factura con suplido"
        linea = replace(facturas[0])
        linea.base_iva = suplido
        linea.pct_iva = linea.cuota_iva = None
        linea.base_requiv = linea.pct_requiv = linea.cuota_requiv = None
        linea.base_irpf = linea.pct_irpf = linea.cuota_irpf = None
        linea.suplidos = None
        linea.es_suplido = True
        facturas.append(linea)
        for f in facturas:
            f.lineas_factura = len(facturas)

    normalizar_importes_abono(facturas)
    aviso = f"{aviso} {_cuadre_factura(facturas)}".strip()

    # Resultado de la doble lectura, en todas las lineas del documento.
    verificacion = str(datos.get("_verificacion") or "")
    discrepancias = discrepancias_de(datos, tipo)
    paginas_manual = tuple(
        (str(o), int(p)) for o, p in datos.get("_paginas_union_manual") or [])
    for f in facturas:
        f.verificacion = verificacion
        f.discrepancias = discrepancias
        f.paginas_documento = paginas_manual

    # Solo se avisa si lo escrito a mano toca a los IMPORTES. El asesor anota
    # el CIF y numera las facturas para los requerimientos de Hacienda: si se
    # avisara de eso, saldrian todas en ambar y el semaforo no serviria.
    if datos.get("manuscrito_en_importes"):
        aviso = f"{aviso} Hay importes escritos a mano: se han usado los " \
                f"IMPRESOS (lo manuscrito no cuenta). Compruébala.".strip()

    # Si la cuenta solo tiene una subclave posible en Aplifisa, se pone sola:
    # no hay nada que decidir y asi el apunte entra completo.
    if not gxx and cuenta:
        posibles = subclaves_de(cuenta)
        if len(posibles) == 1:
            gxx = posibles[0][0]
    for _f in facturas:
        _f.subclave = gxx
    return FacturaProcesada(tipo=tipo, facturas=facturas, cuenta=cuenta,
                            gxx=gxx, origen=origen, pagina=pagina, aviso=aviso,
                            sustituye_a=acotar_numero(datos.get("sustituye_a")))


# A que dato de la fila afecta cada diferencia de la doble lectura.
_CAMPO_FACTURA = {
    "num_factura": "num_factura", "fecha": "fecha", "total": "total_impreso",
    "cuota_irpf": "cuota_irpf", "lineas_iva": "base_iva", "suplidos": "base_iva",
    # La cuenta llega como «629 (G22)»: cuenta y subclave van juntas.
    "cuenta_gasto": "concepto", "cuenta_ingreso": "concepto",
    "base_irpf": "base_irpf", "pct_irpf": "pct_irpf",
    # «Bien de inversión» no es una columna: se decide con la cuenta (la 200).
    "es_bien_inversion": "",
}
# Lo contable que solo cuenta de un lado: la cuenta de gasto en una venta (o
# la de ingreso en un gasto) no es una discrepancia que importe.
_SOLO_GASTO = {"cuenta_gasto", "subclave_gxx", "es_bien_inversion"}
_SOLO_VENTA = {"cuenta_ingreso"}
_CAMPOS_CUENTA = {"cuenta_gasto", "subclave_gxx", "cuenta_ingreso"}


def discrepancias_de(datos: dict, tipo: str) -> tuple:
    """Las diferencias entre las dos lecturas, listas para la tabla."""
    from .doble_lectura import texto_diferencia
    salida = []
    m1, m2 = datos.get("_modelo_1", ""), datos.get("_modelo_2", "")
    contraparte = "emisor_nif" if tipo == "gasto" else "receptor_nif"
    for d in datos.get("_discrepancias") or []:
        if not isinstance(d, dict):
            continue
        copia = dict(d)
        campo = copia.get("campo")
        if campo in (_SOLO_VENTA if tipo == "gasto" else _SOLO_GASTO):
            continue
        if campo in ("emisor_nif", "receptor_nif"):
            copia["campo_factura"] = "nif" if campo == contraparte else ""
        else:
            copia["campo_factura"] = _CAMPO_FACTURA.get(campo, "")
        copia["modelo_1"], copia["modelo_2"] = m1, m2
        copia["texto"] = texto_diferencia(copia, m1, m2)
        salida.append(copia)
    return tuple(salida)


def _anadir_aviso(pr: FacturaProcesada, texto: str) -> None:
    pr.aviso = f"{pr.aviso} {texto}".strip() if pr.aviso else texto


def _num_doc(valor) -> str:
    """Deja un nº de documento comparable (Gemini lo devuelve con o sin puntos)."""
    return "".join(c for c in str(valor or "") if c.isalnum()).upper()


def marcar_sustituidas(procesadas: List[FacturaProcesada]) -> int:
    """Marca las facturas que otra factura del lote dice sustituir.

    Coca-Cola manda una "POST-FACTURACION" que pone "Sustituye al doc.n: N" y
    rehace un albaran anterior. Si se importan las dos, el gasto se duplica: el
    numero y la base son distintos, asi que la deteccion de duplicados normal no
    las ve. Aqui solo se MARCAN (en rojo): decide la persona.
    """
    por_numero: Dict[str, List[FacturaProcesada]] = defaultdict(list)
    for pr in procesadas:
        num = _num_doc(pr.facturas[0].num_factura if pr.facturas else None)
        if num:
            por_numero[num].append(pr)

    marcadas = 0
    for pr in procesadas:
        objetivo = _num_doc(pr.sustituye_a)
        if not objetivo:
            continue
        if not pr.facturas:
            continue
        nueva = pr.facturas[0]
        nuevo = nueva.num_factura
        candidatas = [vieja for vieja in por_numero.get(objetivo, [])
                      if vieja is not pr and vieja.facturas and vieja.tipo == pr.tipo
                      and normaliza_nif(nueva.nif)
                      and normaliza_nif(vieja.facturas[0].nif) == normaliza_nif(nueva.nif)]
        if len(candidatas) > 1:
            _anadir_aviso(pr, "Sustitución ambigua: hay varias facturas con el "
                              "mismo número y contraparte. Comprueba cuál sustituye.")
            continue
        for vieja in candidatas:
            fecha_vieja, fecha_nueva = fecha_de(vieja.facturas[0].fecha), fecha_de(nueva.fecha)
            if fecha_vieja is None or fecha_nueva is None or fecha_vieja > fecha_nueva:
                _anadir_aviso(pr, "Sustitución pendiente de comprobar: las fechas "
                                  "no permiten confirmar la factura anterior.")
                continue
            _anadir_aviso(vieja, f"SUSTITUIDA por la factura {nuevo} del mismo "
                                 f"lote: NO la importes o duplicarás el gasto.")
            vieja.sustituida_por = nuevo
            for f in vieja.facturas:
                f.tratamiento_manual = f"Sustituida por {nuevo or 'otra factura'}"
            marcadas += 1
    return marcadas


def clave_proveedor(nombre) -> str:
    """Nombre normalizado que identifica a un proveedor en la memoria."""
    return " ".join(sorted(_tokens_nombre(nombre)))


def recordar_nif(nombre, nif, manual: bool = False,
                 guardar_nombre: bool = True) -> bool:
    """Guarda el NIF de un proveedor para los proximos lotes (y otros clientes).
    Solo se recuerdan NIF que pasan el digito de control."""
    nif = normaliza_nif(nif)
    clave = clave_proveedor(nombre)
    if not clave or not validar_nif(nif):
        return False
    return proveedores.guardar(
        clave, nif, str(nombre or "").strip() if guardar_nombre else "", manual)


def nombre_sin_letra(f) -> bool:
    """El nombre de la fila es el que se quedó sin una letra (carácter
    invisible sin recuperar) y nadie lo ha corregido: no se aprende, o se
    impondría a las lecturas buenas de ese NIF."""
    sin_letra = getattr(f, "nombre_sin_letra", "")
    return bool(sin_letra) and f.nombre == sin_letra


def aprender_nifs(procesadas: List[FacturaProcesada]) -> int:
    """Memoriza los NIF que SI se han leido bien en este lote."""
    n = 0
    for pr in procesadas:
        if not pr.facturas:
            continue
        f = pr.facturas[0]
        if recordar_nif(f.nombre, f.nif):
            n += 1
    return n


def aprender_nifs_exportados(facturas) -> int:
    """Memoriza los NIF de las facturas que se acaban de exportar.

    Es el momento seguro: el cliente del lote esta confirmado y cada fila ha
    pasado la revision. Antes se aprendia nada mas leer, y un reparto al reves
    (el cliente tomado por proveedor) quedaba guardado para los proximos lotes.
    """
    n, vistos = 0, set()
    for f in facturas:
        if nombre_sin_letra(f):
            continue    # le falta una letra y nadie lo corrigió: no se aprende
        clave = (clave_proveedor(f.nombre), normaliza_nif(f.nif))
        if clave in vistos:
            continue
        vistos.add(clave)
        if recordar_nif(f.nombre, f.nif):
            n += 1
    return n


# Lo que el OCR confunde en las cifras de un NIF (la O por el 0…).
_PARECIDAS = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1",
                            "S": "5", "B": "8", "G": "6", "Z": "2"})


def _nif_compatible(leido: str, guardado: str) -> bool:
    """Lo leído es el guardado con algún carácter perdido o cambiado (o
    confundido por el OCR: O por 0): el mismo NIF mal impreso o mal leído,
    no el de otra empresa."""
    if not leido or not guardado:
        return False

    def cifras(nif):
        # Solo el centro: la primera y la última pueden ser letras de verdad.
        return nif[:1] + nif[1:-1].translate(_PARECIDAS) + nif[-1:]
    leido, guardado = cifras(leido), cifras(guardado)
    if len(leido) >= 6 and (leido in guardado or guardado in leido):
        return True
    if abs(len(leido) - len(guardado)) > 1:
        return False
    previa = list(range(len(guardado) + 1))
    for i, a in enumerate(leido, 1):
        actual = [i]
        for j, b in enumerate(guardado, 1):
            actual.append(min(previa[j] + 1, actual[j - 1] + 1,
                              previa[j - 1] + (a != b)))
        previa = actual
    return previa[-1] <= 1


def _nifs_del_cliente(cliente_nif: str) -> set:
    """Los NIF de los proveedores que ya le han facturado a este cliente."""
    if not cliente_nif:
        return set()
    try:
        from . import registro_facturas
        return {normaliza_nif(ficha.get("nif"))
                for ficha in registro_facturas.exportadas_de(cliente_nif).values()}
    except Exception:
        return set()


def completar_desde_memoria(procesadas: List[FacturaProcesada],
                            cliente_nif: str = "") -> int:
    """Rellena los NIF que faltan o no valen con los ya sabidos de otras veces.

    Se usa DESPUES de propagar_nifs: dentro del mismo lote la prueba es mejor.
    Un NIF confirmado manualmente sí prevalece incluso si el OCR devuelve otro
    que, por casualidad, pasa el dígito de control. Los aprendidos solo por una
    lectura automática mantienen la cautela anterior.
    """
    completados = 0
    conocidos = None            # los NIF del cliente, solo si hacen falta
    de_antes = None             # las claves de la 1.24.0, solo si hacen falta
    for pr in procesadas:
        if not pr.facturas:
            continue
        f = pr.facturas[0]
        clave = clave_proveedor(f.nombre)
        ficha = proveedores.leer(clave)
        if not ficha and clave:
            if de_antes is None:
                de_antes = _claves_de_la_124()
            ficha = de_antes.get(clave)
        if not ficha:
            continue
        actual = normaliza_nif(f.nif)
        if validar_nif(actual):
            if actual != ficha["nif"]:
                mensaje = (f"OJO: {f.nombre} tiene guardado el NIF "
                           f"{ficha['nif']} y esta factura trae {actual}. "
                           "Comprueba cuál es el bueno.")
                pr.conflicto_nif = {
                    "nombre": f.nombre or "Proveedor",
                    "guardado": ficha["nif"],
                    "leido": actual,
                    "mensaje": mensaje,
                    "consultado": False,
                }
                _anadir_aviso(pr, mensaje)
            continue
        leido = (f.nif or "").strip()   # antes de pisarlo: f ES pr.facturas[0]
        for linea in pr.facturas:
            linea.nif = ficha["nif"]
        motivo = f"aquí se leyó «{leido}», que no es válido" if leido \
            else "aquí no se leyó ninguno"
        # La memoria automática queda en ámbar hasta que alguien la confirme.
        # La confirmada por una persona se pone en silencio solo si no hay
        # duda de que es el mismo proveedor: lo leído es ese NIF mal impreso,
        # o ese proveedor ya le factura a este cliente. Si no, puede ser otra
        # empresa con el mismo nombre (de otro cliente) y el gasto se
        # imputaría a quien no es.
        if conocidos is None and ficha.get("manual"):
            conocidos = _nifs_del_cliente(cliente_nif)
        if not ficha.get("manual") or not (
                _nif_compatible(normaliza_nif(leido), ficha["nif"])
                or ficha["nif"] in conocidos):
            _anadir_aviso(pr, f"NIF puesto de memoria ({ficha['nif']}): es el que "
                              f"consta guardado para {f.nombre} y {motivo}. Compruébalo.")
        completados += 1
    return completados


def a_total_factura(pr: FacturaProcesada) -> FacturaProcesada:
    """Deja un unico apunte por el TOTAL (base + IVA + recargo + suplidos).

    Para clientes en recargo de equivalencia o sin derecho a deducir, y para
    una factura cuyo IVA no se deduce: el gasto es el importe integro y en
    Aplifisa se registra como total factura, sin desglose.

    La retencion (el alquiler del local, un profesional) se CONSERVA tal cual:
    el IVA no deducible va al gasto, pero la retencion se declara aparte
    (modelos 111 y 115) y no se puede perder.
    """
    if pr.tipo != "gasto" or not pr.facturas:
        return pr
    retenida = next((f for f in pr.facturas if f.cuota_irpf), None)

    # La linea del suplido ya entra aqui con su base: es una linea mas.
    total = sum((f.base_iva or 0) + (f.cuota_iva or 0) for f in pr.facturas)
    total += sum(f.cuota_requiv or 0 for f in pr.facturas)
    base = replace(pr.facturas[0])
    base.base_iva = round(total, 2)
    base.pct_iva = None
    base.cuota_iva = None
    base.base_requiv = base.pct_requiv = base.cuota_requiv = None
    base.suplidos = None
    base.es_suplido = False   # el suplido ya esta dentro del total
    base.iva_incluido_en_base = True
    base.lineas_factura = 1
    if retenida is not None:
        base.base_irpf = retenida.base_irpf
        base.pct_irpf = retenida.pct_irpf
        base.cuota_irpf = retenida.cuota_irpf
    return replace(pr, facturas=[base])


def propagar_nifs(procesadas: List[FacturaProcesada]) -> int:
    """Completa el NIF de la contraparte cuando en su factura falta o esta mal
    leido (va en un margen, impreso flojo...), copiandolo de otra factura del
    MISMO proveedor en la que si se leyo bien. Devuelve cuantas ha completado.

    Solo copia cuando no cabe duda de que el NIF es el que toca:
      - El proveedor se identifica por su nombre normalizado EXACTO (mismas
        palabras); un nombre parecido no vale.
      - El NIF de origen tiene que pasar el digito de control (validar_nif):
        un NIF mal leido no puede ser la fuente de nada.
      - Tiene que haber UN UNICO NIF valido para ese nombre en todo el lote. Si
        aparecen dos (dos proveedores homonimos, o uno cambio de CIF), no se
        toca ninguno y se avisa para que se ponga a mano.
      - NUNCA pisa un NIF que ya es valido de por si.
    Toda fila tocada queda marcada con un aviso -> sale en ambar para revisarla.
    """
    grupos: Dict[frozenset, List[FacturaProcesada]] = defaultdict(list)
    for pr in procesadas:
        nombre = pr.facturas[0].nombre if pr.facturas else None
        clave = frozenset(_tokens_nombre(nombre))
        if clave:  # sin nombre no hay forma de saber de quien es la factura
            grupos[clave].append(pr)

    completados = 0
    for grupo in grupos.values():
        validos = {normaliza_nif(pr.facturas[0].nif) for pr in grupo
                   if validar_nif(normaliza_nif(pr.facturas[0].nif))}
        pendientes = [pr for pr in grupo
                      if not validar_nif(normaliza_nif(pr.facturas[0].nif))]
        if not pendientes or not validos:
            continue

        if len(validos) > 1:
            for pr in pendientes:
                _anadir_aviso(pr, "Hay {} NIF distintos para este mismo nombre en "
                                  "el lote ({}): no se copia ninguno, escríbelo a "
                                  "mano.".format(len(validos), ", ".join(sorted(validos))))
            continue

        nif_bueno = next(iter(validos))
        # Citar el nombre tal y como se leyo en la factura de la que sale el NIF.
        nombre_prov = next(pr.facturas[0].nombre for pr in grupo
                           if normaliza_nif(pr.facturas[0].nif) == nif_bueno)
        for pr in pendientes:
            leido = (pr.facturas[0].nif or "").strip()
            for f in pr.facturas:
                f.nif = nif_bueno
            motivo = f"se leyó «{leido}», que no es un NIF válido" if leido \
                else "no se leyó ningún NIF"
            _anadir_aviso(pr, f"NIF copiado de otra factura de {nombre_prov} "
                              f"({nif_bueno}): aquí {motivo}. Compruébalo.")
            completados += 1

    return completados


def _apuntar_hoja_rara(que: str) -> None:
    import traceback
    from . import errores
    errores.apuntar(f"Lectura rara al {que}; las demás hojas siguen:\n"
                    + traceback.format_exc())


def _construir_sin_tumbar(datos, cliente_nif, cliente_nombre, origen, pagina):
    """construir(), pero una hoja rara no se lleva el bloque entero.

    Una lista donde va un nombre o un texto donde van las líneas de IVA (lo
    que trae una lectura sin esquema o desbocada) lanzaba aquí y se perdían
    las 25 hojas del bloque, ya pagadas. Ahora esa hoja queda en rojo con su
    motivo, como una hoja que no se pudo leer, y las demás siguen.
    """
    try:
        return construir(datos, cliente_nif, cliente_nombre, origen, pagina)
    except Exception as error:
        _apuntar_hoja_rara(f"construir la hoja {pagina}")
        motivo = f"lectura que no se pudo interpretar ({type(error).__name__})"
        return construir({"emisor_nombre": None, "lineas_iva": [{}], "_error": motivo},
                         cliente_nif, cliente_nombre, origen, pagina)


def preparar_lote(registros: List[tuple], cliente_nombre: str,
                  cliente_nif: str) -> List[tuple]:
    """De lo leido por Gemini a las facturas listas para la tabla.

    `registros` son (imagen, origen, pagina, datos_crudos). Se guarda tal cual
    en cada bloque: asi, si el cliente estaba mal detectado, se puede rehacer
    todo con el cliente bueno SIN volver a pagar otra lectura a Gemini.
    """
    # Gemini lee cada imagen por separado. En una factura de varias hojas la
    # primera suele traer cabecera/cliente y la ultima el resumen fiscal. Antes
    # ambas acababan como apuntes incompletos distintos. Se juntan primero los
    # fragmentos consecutivos de la misma factura y despues se construye el
    # unico apunte, con todas sus lineas de IVA y recargo.
    try:
        consolidados = consolidar_paginas_factura(registros)
    except Exception:
        # Una lectura que no deja ni comparar las hojas: cada una por su lado.
        _apuntar_hoja_rara("unir las hojas del bloque")
        consolidados = list(registros)
    procesadas = [(img, _construir_sin_tumbar(datos, cliente_nif, cliente_nombre,
                                              origen, pag))
                  for img, origen, pag, datos in consolidados]
    solo = [pr for _, pr in procesadas]
    propagar_nifs(solo)              # 1º la prueba del propio lote
    completar_desde_memoria(solo, cliente_nif)   # 2º lo sabido de otras veces
    # Lo leido NO se memoriza aqui: todavia no se sabe si el cliente esta bien
    # elegido ni si esos NIF son buenos. Se aprende al exportar, con los datos
    # ya revisados (ver aprender_nifs_exportados).
    unificar_nombres(solo)           # 3º el mismo proveedor, escrito igual
    aplicar_recordado(solo, cliente_nif)   # 4º lo que ya corrigio el usuario
    marcar_sustituidas(solo)         # post-facturaciones que rehacen otra
    return procesadas


_CAMPOS_FISCALES = (
    "total", "base_irpf", "pct_irpf", "cuota_irpf", "suplidos",
)
_CAMPOS_BOOLEANOS = (
    "es_bien_inversion", "manuscrito_en_importes",
)


def _tiene_linea_fiscal(linea: dict) -> bool:
    return any(_num(linea.get(campo)) is not None for campo in (
        "base", "tipo_iva", "cuota_iva", "pct_requiv", "cuota_requiv",
    ))


def _tiene_importes(datos: dict) -> bool:
    if any(_tiene_linea_fiscal(linea)
           for linea in (datos.get("lineas_iva") or [])
           if isinstance(linea, dict)):
        return True
    return any(_num(datos.get(campo)) is not None
               for campo in _CAMPOS_FISCALES)


def _tiene_las_dos_partes(datos: dict) -> bool:
    emisor = datos.get("emisor_nif") or datos.get("emisor_nombre")
    receptor = datos.get("receptor_nif") or datos.get("receptor_nombre")
    return bool(emisor and receptor)


def _mismo_origen(a: str, b: str) -> bool:
    import os
    return os.path.normcase(os.path.abspath(a or "")) == \
        os.path.normcase(os.path.abspath(b or ""))


def _estado_pagina(datos: dict) -> str:
    estado = str(datos.get("_estado_ultima_pagina", datos.get("estado_pagina_factura")) or "").strip().lower()
    return estado if estado in {"unica", "inicio", "intermedia", "final"} else ""


def _comparten_una_parte(a: dict, b: dict) -> bool:
    """Prueba conservadora para continuaciones leidas con el prompt antiguo."""
    for prefijo in ("emisor", "receptor"):
        nif_a = normaliza_nif(a.get(f"{prefijo}_nif"))
        nif_b = normaliza_nif(b.get(f"{prefijo}_nif"))
        if nif_a and nif_a == nif_b:
            return True
        nombre_a = a.get(f"{prefijo}_nombre")
        nombre_b = b.get(f"{prefijo}_nombre")
        if nombre_a and nombre_b and _mismo_nombre(nombre_a, nombre_b):
            return True
    return False


def _resumen_fiscal_cuadra(datos: dict) -> bool:
    """La hoja contiene un resumen fiscal completo, no solo un subtotal."""
    total = _num(datos.get("total"))
    lineas = [linea for linea in (datos.get("lineas_iva") or [])
              if isinstance(linea, dict) and _tiene_linea_fiscal(linea)]
    if total is None or not lineas:
        return False
    suma = sum((_num(linea.get("base")) or 0)
               + (_num(linea.get("cuota_iva")) or 0)
               + (_num(linea.get("cuota_requiv")) or 0)
               for linea in lineas)
    suma += _num(datos.get("suplidos")) or 0
    suma -= _num(datos.get("cuota_irpf")) or 0
    return abs(round(suma, 2) - total) <= TOLERANCIA_CUADRE


def _continuacion_sin_numero(anterior: dict, siguiente: dict) -> bool:
    """Une una ultima hoja sin numero solo cuando hay evidencias suficientes."""
    estado_a, estado_b = _estado_pagina(anterior), _estado_pagina(siguiente)
    if estado_a in {"inicio", "intermedia"} and estado_b in {"intermedia", "final"}:
        return True

    # Compatibilidad con lotes ya leidos antes de que existiera el marcador.
    # La hoja siguiente ha de ser parcial en identidad, compartir al menos una
    # parte y traer un resumen fiscal autocuadrado cuyo total englobe el aparente
    # subtotal de la primera. Asi no se absorbe una factura independiente.
    if not _num_doc(anterior.get("num_factura")) or \
            _num_doc(siguiente.get("num_factura")):
        return False
    if not _tiene_las_dos_partes(anterior) or _tiene_las_dos_partes(siguiente):
        return False
    if not _comparten_una_parte(anterior, siguiente) or \
            not _resumen_fiscal_cuadra(siguiente):
        return False
    total_a = _num(anterior.get("total"))
    total_b = _num(siguiente.get("total"))
    return total_a is None or (total_b is not None and abs(total_b) >= abs(total_a))


def _resumen_antes_de_cabecera(a: dict, b: dict) -> bool:
    """Reconoce dos hojas invertidas mediante identidad y datos complementarios."""
    numero = _num_doc(a.get("num_factura"))
    fecha = fecha_de(a.get("fecha"))
    return bool(
        numero and numero == _num_doc(b.get("num_factura"))
        and fecha and fecha == fecha_de(b.get("fecha"))
        and not a.get("_ultima_pagina_consolidada")
        and not _tiene_las_dos_partes(a) and _resumen_fiscal_cuadra(a)
        and _tiene_las_dos_partes(b) and not _tiene_importes(b)
        and _estado_pagina(b) == "inicio"
        and any(normaliza_nif(a.get(f"{p}_nif"))
                and normaliza_nif(a.get(f"{p}_nif")) == normaliza_nif(b.get(f"{p}_nif"))
                for p in ("emisor", "receptor"))
    )


def _son_paginas_de_la_misma_factura(anterior: tuple, siguiente: tuple) -> bool:
    """Reconoce fragmentos consecutivos sin ocultar facturas duplicadas.

    Dos paginas completas con el mismo numero se mantienen separadas para que
    la deteccion de duplicados siga avisando. Solo se unen cuando al menos una
    de las dos es parcial: le falta una de las partes o le faltan los importes.
    """
    _, origen_a, pagina_a, datos_a = anterior
    _, origen_b, pagina_b, datos_b = siguiente
    # Una hoja que no se pudo leer nunca se pega a otra: quedaria escondida.
    if datos_a.get("_error") or datos_b.get("_error"):
        return False
    if not _mismo_origen(origen_a, origen_b):
        return False
    ultima_a = datos_a.get("_ultima_pagina_consolidada", pagina_a)
    try:
        if int(pagina_b) != int(ultima_a) + 1:
            return False
    except (TypeError, ValueError):
        return False
    numero_a = _num_doc(datos_a.get("num_factura"))
    numero_b = _num_doc(datos_b.get("num_factura"))
    if numero_a and numero_b and numero_a != numero_b:
        return False
    for prefijo in ("emisor", "receptor"):
        nif_a = normaliza_nif(datos_a.get(f"{prefijo}_nif"))
        nif_b = normaliza_nif(datos_b.get(f"{prefijo}_nif"))
        if nif_a and nif_b and nif_a != nif_b:
            return False
    if _resumen_antes_de_cabecera(datos_a, datos_b):
        return True
    if _estado_pagina(datos_a) in {"final", "unica"} or _estado_pagina(datos_b) == "unica":
        return False
    completas_a = _tiene_las_dos_partes(datos_a) and _tiene_importes(datos_a)
    completas_b = _tiene_las_dos_partes(datos_b) and _tiene_importes(datos_b)
    if completas_a and completas_b:
        return False
    if not numero_a or numero_a != numero_b:
        if not _continuacion_sin_numero(datos_a, datos_b):
            return False
    # El número impreso y el orden físico mandan sobre una fecha aislada de la
    # continuación. En el pie pequeño, Gemini puede leer 2026 como 2024. La
    # cabecera de la primera hoja se conserva al fusionar, así que una fecha
    # discordante no debe partir una factura cuyo número sí coincide.
    estado_a, estado_b = _estado_pagina(datos_a), _estado_pagina(datos_b)
    if estado_a in {"inicio", "intermedia"} and estado_b in {"intermedia", "final"}:
        return True
    completas_a = _tiene_las_dos_partes(datos_a) and _tiene_importes(datos_a)
    completas_b = _tiene_las_dos_partes(datos_b) and _tiene_importes(datos_b)
    return not (completas_a and completas_b)


def _clave_linea_fiscal(linea: dict) -> tuple:
    return tuple(_num(linea.get(campo)) for campo in (
        "base", "tipo_iva", "cuota_iva", "pct_requiv", "cuota_requiv",
    ))


# Lo que Gemini contesta cuando la hoja no dice nada: al unir hojas, cuenta
# como vacío (la mención «Inversión del sujeto pasivo» suele ir junto a los
# totales, en la última hoja).
_POR_DEFECTO = {"tipo_documento": ("factura",), "moneda": ("EUR",),
                "mencion_iva": ("ninguna",), "posible_no_deducible": ("no",)}


def _fusionar_datos_paginas(primera: dict, siguiente: dict) -> dict:
    fusion = deepcopy(primera)

    # La cabecera buena suele estar en la primera hoja. Completar huecos con
    # las siguientes sin permitir que una lectura parcial la borre.
    for campo, valor in siguiente.items():
        if campo in ("lineas_iva", *_CAMPOS_FISCALES, *_CAMPOS_BOOLEANOS,
                     "confianza"):
            continue
        vacio = (None, "", []) + _POR_DEFECTO.get(campo, ())
        if fusion.get(campo) in vacio and valor not in vacio:
            fusion[campo] = deepcopy(valor)
        elif fusion.get(campo) in (None, "", []):
            fusion[campo] = deepcopy(valor)

    # Si la ultima hoja trae un resumen fiscal que cuadra por si solo, contiene
    # el resumen de TODA la factura: sustituye a cualquier subtotal de articulos
    # que Gemini hubiera confundido con base/total en una hoja anterior.
    fuentes_lineas = (siguiente,) if _resumen_fiscal_cuadra(siguiente) \
        else (primera, siguiente)
    lineas, vistas = [], set()
    for datos in fuentes_lineas:
        for linea in datos.get("lineas_iva") or []:
            if not isinstance(linea, dict) or not _tiene_linea_fiscal(linea):
                continue
            clave = _clave_linea_fiscal(linea)
            if clave not in vistas:
                lineas.append(deepcopy(linea))
                vistas.add(clave)
    fusion["lineas_iva"] = lineas or [{}]

    # El resumen definitivo se imprime normalmente en la ultima pagina.
    for campo in _CAMPOS_FISCALES:
        if siguiente.get(campo) not in (None, ""):
            fusion[campo] = deepcopy(siguiente[campo])
    for campo in _CAMPOS_BOOLEANOS:
        fusion[campo] = bool(primera.get(campo) or siguiente.get(campo))

    # Doble lectura: las diferencias de identidad valen de todas las hojas;
    # las de importes, solo de la hoja de la que salen los importes finales
    # (el subtotal de una hoja inicial se descarta, y su diferencia tambien).
    fiscales = {"total", "lineas_iva", "cuota_irpf", "suplidos"}
    discrepancias = []
    for datos, aporta_importes in ((primera, fuentes_lineas != (siguiente,)),
                                   (siguiente, True)):
        for d in datos.get("_discrepancias") or []:
            if isinstance(d, dict) and (aporta_importes or d.get("campo") not in fiscales):
                if d not in discrepancias:
                    discrepancias.append(d)
    fusion["_discrepancias"] = discrepancias
    verificaciones = {str(d.get("_verificacion") or "") for d in (primera, siguiente)}
    fusion["_verificacion"] = ("simple" if "simple" in verificaciones
                               else "doble" if "doble" in verificaciones else "")
    for clave in ("_modelo_1", "_modelo_2"):
        if not fusion.get(clave) and siguiente.get(clave):
            fusion[clave] = siguiente[clave]

    orden_confianza = {"alta": 0, "media": 1, "baja": 2}
    confianzas = [str(d.get("confianza") or "").strip().lower()
                  for d in (primera, siguiente)]
    confianzas = [c for c in confianzas if c]
    if confianzas:
        fusion["confianza"] = max(
            confianzas, key=lambda c: orden_confianza.get(c, 1))
    return fusion


def consolidar_paginas_factura(registros: List[tuple]) -> List[tuple]:
    """Une paginas consecutivas complementarias de una misma factura.

    Conserva la imagen y el numero de la primera pagina para que la tabla siga
    mostrando la cabecera. Los datos originales no se modifican, de modo que
    cambiar el cliente permite reconstruir el lote otra vez sin llamar a IA.
    """
    salida: List[tuple] = []
    for registro in registros:
        actual = (registro[0], registro[1], registro[2], deepcopy(registro[3]))
        if salida and _son_paginas_de_la_misma_factura(salida[-1], actual):
            img, origen, pagina, datos = salida[-1]
            fusion = _fusionar_datos_paginas(datos, actual[3])
            fusion["_ultima_pagina_consolidada"] = actual[2]
            fusion["_estado_ultima_pagina"] = (
                "final" if _resumen_antes_de_cabecera(datos, actual[3])
                else _estado_pagina(actual[3]))
            sin_numero = not _num_doc(datos.get("num_factura")) or not _num_doc(actual[3].get("num_factura"))
            if sin_numero or datos.get("_union_inferida"):
                fusion["_union_inferida"] = True
                fusion["_motivo_union_inferida"] = "continuidad de hojas sin número repetido"
                fusion["_paginas_union_inferida"] = list(range(int(pagina), int(actual[2]) + 1))
            salida[-1] = (img, origen, pagina, fusion)
        else:
            salida.append(actual)
    return salida


def fusionar_paginas_manual(registros: List[tuple]) -> tuple:
    """Une las hojas elegidas expresamente por una persona.

    La primera aporta cabecera, número y fecha; las siguientes completan los
    huecos y la última que tenga un resumen fiscal autocuadrado aporta los
    importes definitivos. No exige mismo archivo, páginas consecutivas ni que
    Gemini haya repetido bien el número: esa decisión ya la tomó el usuario.
    """
    if len(registros) < 2:
        raise ValueError("Seleccione al menos dos hojas distintas.")
    imagen, origen, pagina, datos = registros[0]
    fusion = deepcopy(datos)
    paginas = [(origen, pagina)]
    for _imagen, origen_sig, pagina_sig, datos_sig in registros[1:]:
        fusion = _fusionar_datos_paginas(fusion, datos_sig)
        paginas.append((origen_sig, pagina_sig))
    fusion["_union_manual"] = True
    fusion["_paginas_union_manual"] = paginas
    fusion["_ultima_pagina_consolidada"] = pagina
    return imagen, origen, pagina, fusion



def nombres_guardados(solo_a_mano: bool = False) -> Dict[str, str]:
    """{NIF: nombre} de los proveedores ya conocidos (el puesto a mano manda).

    `solo_a_mano`: solo los que escribió una persona. Al guardar un NIF se
    guarda también el nombre tal cual se leyó, y ese no debe decidir entre
    dos formas de escribirlo que ya están en el lote.
    """
    por_nif = {}
    for ficha in proveedores.leer_todo().values():
        if not isinstance(ficha, dict):
            continue
        if solo_a_mano and not ficha.get("nombre_manual"):
            continue
        nif = normaliza_nif(ficha.get("nif"))
        if not nif or not ficha.get("nombre") or tiene_invisibles(ficha["nombre"]):
            continue        # un nombre roto guardado no se impone a nadie
        # El corregido a mano manda: se ponga antes o despues en el fichero.
        if ficha.get("nombre_manual") or nif not in por_nif:
            por_nif[nif] = ficha["nombre"]
    return por_nif


def unificar_nombres(procesadas: List[FacturaProcesada]) -> int:
    """El mismo proveedor, escrito siempre igual.

    Una vez llega "TELEFONICA DE ESPAÑA, S.A.U." y otra "Telefónica de España,
    S.A.U.". Es el mismo, pero Aplifisa busca la cuenta por NIF y luego por
    NOMBRE EXACTO, asi que dos formas de escribirlo pueden acabar en dos
    cuentas. Se usa el nombre que ya esta guardado para ese NIF y, si es la
    primera vez que llega, uno solo para todo el lote.
    """
    por_nif = nombres_guardados()
    cambiados = 0
    for pr in procesadas:
        for f in pr.facturas:
            bueno = por_nif.get(normaliza_nif(f.nif))
            if bueno and f.nombre and f.nombre != bueno:
                f.nombre = bueno
                cambiados += 1
    return cambiados + len(unificar_nombres_por_nif(
        [f for pr in procesadas for f in pr.facturas], por_nif))


# Formas jurídicas y palabras que no dicen de quién es la factura.
_FORMAS_JURIDICAS = {
    "SA", "SL", "SLU", "SAU", "SLL", "SLNE", "SC", "CB", "SCOOP", "COOP",
    "SAL", "SOCIEDAD", "LIMITADA", "ANONIMA", "UNIPERSONAL", "COOPERATIVA",
}
_PALABRAS_VACIAS = {"DE", "LA", "EL", "EN", "LO", "AL", "DEL", "LOS", "LAS",
                    "THE", "AND", "CIA"}
# Las comparten empresas que no tienen nada que ver: no bastan para decir
# que dos nombres son la misma.
_PALABRAS_GENERICAS = {
    "SERVICIOS", "SERVICIO", "SERVICE", "SERVICES", "GRUPO", "GROUP",
    "COMERCIAL", "ESPANA", "SPAIN", "IBERICA", "IBERIA", "DISTRIBUCIONES",
    "DISTRIBUCION", "HERMANOS", "HNOS", "EMPRESA", "INDUSTRIAL", "INDUSTRIAS",
    "SOLUCIONES", "SISTEMAS", "GESTION", "TALLER", "TALLERES",
    "CONSTRUCCIONES", "TRANSPORTES", "ASESORES", "ASOCIADOS",
    "INTERNACIONAL", "GLOBAL", "SUMINISTROS", "MANTENIMIENTO",
}


def _palabras_nombre(nombre) -> List[str]:
    """«Orange Espagne, S.A.» -> ['ORANGE', 'ESPAGNE', 'SA'] (sin acentos y
    con las letras sueltas juntas: «S. A.» es «SA»)."""
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", str(nombre or ""))
                if unicodedata.category(c) != "Mn").upper().replace(".", "")
    palabras, sueltas = [], ""
    for p in re.sub(r"[^\w]+", " ", t).split():
        if len(p) == 1:
            sueltas += p
            continue
        if sueltas:
            palabras.append(sueltas)
            sueltas = ""
        palabras.append(p)
    if sueltas:
        palabras.append(sueltas)
    return palabras


def _palabras_que_cuentan(nombre) -> set:
    """Las palabras que dicen quién es (siglas como «HM» o «HP» incluidas);
    las genéricas («SERVICIOS», «GRUPO»…) solo si no hay otras."""
    todas = {p for p in _palabras_nombre(nombre)
             if len(p) >= 2 and p not in _FORMAS_JURIDICAS
             and p not in _PALABRAS_VACIAS}
    return (todas - _PALABRAS_GENERICAS) or todas


def nombres_compatibles(a, b) -> bool:
    """Dos formas de llamar a la misma empresa: comparten alguna palabra que
    no es la forma jurídica ni una genérica («Orange» y «ORANGE ESPAGNE,
    S.A.»). «H&M, S.L.» y «GASOLINERA NORTE, S.L.» con el mismo NIF no lo
    son: uno de los dos está mal leído y lo tiene que ver una persona. Un
    nombre vacío (o que es solo la forma jurídica) toma el de su NIF."""
    pa, pb = _palabras_que_cuentan(a), _palabras_que_cuentan(b)
    return not pa or not pb or bool(pa & pb)


def nombre_preferido(nombres: List[str]) -> str:
    """De las formas de escribir un proveedor, la que va al registro: la que
    lleva la forma jurídica (S.A., S.L.…), después la que más se repite y,
    a igualdad, la más completa."""
    cuenta = Counter(nombres)
    primera = {}
    for i, nombre in enumerate(nombres):
        primera.setdefault(nombre, i)

    def puntos(nombre):
        forma = any(p in _FORMAS_JURIDICAS for p in _palabras_nombre(nombre))
        return (forma, cuenta[nombre], len(_palabras_que_cuentan(nombre)),
                len(nombre), -primera[nombre])
    return max(cuenta, key=puntos)


def unificar_nombres_por_nif(facturas, preferidos: Dict[str, str] | None = None):
    """Un NIF, un nombre: el registro de Aplifisa no admite dos.

    Agrupa las facturas por NIF (solo los válidos: uno ilegible no prueba
    nada) y les pone a todas el mismo nombre: el ya guardado para ese NIF o,
    si no hay, `nombre_preferido` de los del lote. Las que se llaman de otra
    forma que no se parece en nada no se tocan (avisa la validación: o el
    nombre o el NIF está mal leído). Devuelve [(factura, antes, después)].
    """
    preferidos = preferidos or {}
    grupos: Dict[str, list] = defaultdict(list)
    vistas = set()
    for f in facturas:
        if id(f) in vistas:
            continue
        vistas.add(id(f))
        nif = normaliza_nif(f.nif)
        if nif and validar_nif(nif):
            grupos[nif].append(f)
    cambios = []
    for nif, grupo in grupos.items():
        nombres = [str(f.nombre).strip() for f in grupo if str(f.nombre or "").strip()]
        bueno = preferidos.get(nif) or (nombre_preferido(nombres) if nombres else "")
        if not bueno:
            continue
        for f in grupo:
            antes = str(f.nombre or "").strip()
            if antes == bueno or not nombres_compatibles(antes, bueno):
                continue
            cambios.append((f, f.nombre, bueno))
            f.nombre = bueno
    return cambios


def recordar_nombre_proveedor(nif, nombre) -> bool:
    """El nombre con el que el usuario quiere ver a este proveedor.

    Aplifisa busca la cuenta por NIF y luego por nombre EXACTO, asi que como se
    escriba importa. Si lo corrige a mano, se queda corregido para siempre.
    """
    nif, nombre = normaliza_nif(nif), str(nombre or "").strip()
    if not nombre:
        return False
    clave, ficha = proveedores.buscar_clave_por_nif(nif) if nif else (None, None)
    clave = clave or clave_proveedor(nombre)
    guardado = proveedores.guardar_campos(clave, nif=nif or None, nombre=nombre,
                                          nombre_manual=True)
    if nif:
        # Un mismo NIF puede estar guardado con varios nombres (uno por cada
        # forma en que se leyó): el último que pone una persona vale en
        # todas, o uno de antes podría volver a ganar.
        for otra, datos in proveedores.leer_todo().items():
            if (otra != clave and normaliza_nif(datos.get("nif")) == nif
                    and datos.get("nombre_manual")):
                proveedores.guardar_campos(otra, nombre=nombre,
                                           nombre_manual=True)
    return guardado


# La cuenta de antes de la 1.25 (no se sabe de qué cliente era): se conserva
# con esta clave y se sigue poniendo como hasta ahora.
CUENTA_DE_ANTES = "*"
# La que se puso en un lote cuyo cliente no tiene NIF (cuando ya hay cuentas
# por cliente): solo vale para otro lote sin NIF; en los demás, «otro cliente».
CUENTA_SIN_NIF = "~"


def _cuentas_por_cliente(ficha) -> dict:
    """{cliente: [cuenta, gxx]} de una ficha, a prueba de datos raros (una
    lista, un dict, un valor suelto): nunca puede tumbar un lote."""
    valor = (ficha or {}).get("cuentas_cliente") if isinstance(ficha, dict) else None
    if not isinstance(valor, dict):
        return {}
    return {str(k): (list(v) + [None])[:2] for k, v in valor.items()
            if isinstance(v, (list, tuple)) and v}


def recordar_cuenta_proveedor(nif, nombre, cuenta, gxx=None,
                              cliente_nif: str = "",
                              guardar_nombre: bool = True) -> bool:
    """La cuenta contable que el usuario le pone a este proveedor.

    Es lo mismo que hace Aplifisa: la primera vez se dice, y las siguientes
    facturas de ese proveedor entran ya con su concepto. Se recuerda POR
    CLIENTE (1.25): Makro puede ser 600 en un bar y 629 en una oficina.
    """
    cuenta = str(cuenta or "").strip()
    if not cuenta or not es_valido(cuenta, gxx):
        return False
    nif = normaliza_nif(nif)
    clave, ficha = proveedores.buscar_clave_por_nif(nif) if nif else (None, None)
    clave = clave or clave_proveedor(nombre)
    anterior = ficha or proveedores.leer_todo().get(clave) or {}
    por_cliente = _cuentas_por_cliente(anterior)
    cliente = normaliza_nif(cliente_nif)
    if cliente:
        if (not por_cliente and anterior.get("cuenta_manual")
                and anterior.get("cuenta")):
            # La primera por cliente: la de antes no se pierde.
            por_cliente[CUENTA_DE_ANTES] = [anterior.get("cuenta"),
                                            anterior.get("gxx")]
        por_cliente[cliente] = [cuenta, gxx or None]
    elif any(k not in (CUENTA_DE_ANTES, CUENTA_SIN_NIF) for k in por_cliente):
        # Un cliente sin NIF no se puede distinguir, y ya hay cuentas por
        # cliente: la suya vale para los lotes sin NIF; para un cliente con
        # NIF es «de otro cliente» (en ámbar), no la de siempre en verde.
        por_cliente[CUENTA_SIN_NIF] = [cuenta, gxx or None]
    else:
        # Sin cuentas por cliente todavía: lo que pone vale como la cuenta de
        # siempre (si no, la de antes ganaba para siempre).
        por_cliente[CUENTA_DE_ANTES] = [cuenta, gxx or None]
    return proveedores.guardar_campos(clave, nif=nif or None,
                                      nombre=(str(nombre or "").strip() or None)
                                      if guardar_nombre else None,
                                      cuenta=cuenta, gxx=(gxx or None),
                                      cuenta_manual=True,
                                      cuentas_cliente=por_cliente or None)


def ficha_de_cuenta(nif, nombre) -> tuple:
    """(clave, ficha tal cual) del proveedor cuya cuenta se va a recordar,
    para poder dejarla como estaba si se deshace."""
    nif = normaliza_nif(nif)
    clave, ficha = proveedores.buscar_clave_por_nif(nif) if nif else (None, None)
    clave = clave or clave_proveedor(nombre)
    antes = proveedores.leer_todo().get(clave)
    return clave, (dict(antes) if isinstance(antes, dict) else None)


def aplicar_recordado(procesadas: List[FacturaProcesada],
                      cliente_nif: str = "") -> int:
    """Pone en el lote lo que el usuario ya corrigio de esos proveedores.

    La cuenta que puso para ESTE cliente se pone sin más. La que puso en
    otro cliente se propone, pero en ámbar: la cuenta depende de a qué se
    dedica cada uno. (Las guardadas antes de la 1.25 no dicen de qué cliente
    son: se ponen como hasta ahora.)"""
    cliente = normaliza_nif(cliente_nif)
    puestos = 0
    for pr in procesadas:
        if pr.tipo != "gasto" or not pr.facturas:
            continue
        ficha = proveedores.buscar_por_nif(normaliza_nif(pr.facturas[0].nif))
        if not ficha or not ficha.get("cuenta_manual"):
            continue
        if pr.cuenta == "200" or any(
                f.tratamiento_manual == "Bien de inversión"
                or str(f.concepto or "") == "200" for f in pr.facturas):
            # Va a la 200: no la pisa la cuenta de sus gastos (con suplido,
            # el tratamiento pasa a «Factura con suplido», pero sigue en 200).
            continue
        por_cliente = _cuentas_por_cliente(ficha)
        propia = por_cliente.get(cliente) if cliente \
            else por_cliente.get(CUENTA_SIN_NIF)
        de_antes = por_cliente.get(CUENTA_DE_ANTES)
        # De otro cliente: solo si este cliente tiene NIF y no hay ni la suya
        # ni una de antes (que se pone como siempre).
        de_otro = bool(por_cliente) and bool(cliente) and not propia \
            and not de_antes
        cuenta, gxx = propia or de_antes or [ficha.get("cuenta"), ficha.get("gxx")]
        if not es_valido(cuenta, gxx):
            continue
        if de_otro and (cuenta, gxx) == (pr.cuenta, pr.gxx) \
                and not _AVISO_CUENTA.search(pr.aviso or ""):
            continue        # la IA ya propone esa misma: nada que avisar
        pr.cuenta, pr.gxx = cuenta, gxx
        for f in pr.facturas:
            f.concepto, f.subclave = cuenta, gxx
            if not de_otro:
                # La decidió una persona para este cliente: que las dos
                # lecturas de la IA no coincidan en la cuenta ya no importa.
                f.discrepancias = tuple(
                    d for d in (f.discrepancias or ())
                    if d.get("campo") not in _CAMPOS_CUENTA)
        # La cuenta ya la decidio una persona: sobra el aviso de propuesta.
        pr.aviso = quitar_aviso_cuenta(pr.aviso)
        if de_otro:
            nombre = pr.facturas[0].nombre or "este proveedor"
            _anadir_aviso(pr, f"La cuenta {cuenta}{f' ({gxx})' if gxx else ''} "
                              f"es la que usted le puso a {nombre} en otro "
                              "cliente: compruebe que en este también va ahí.")
        puestos += 1
    return puestos


_AVISO_CUENTA = re.compile(
    r"(?:La subclave \S+ no existe para la \S+: se ha puesto \S+, la única "
    r"que admite\.|Cuenta \S+ (?:propuesta por palabras clave|puesta por "
    r"descarte)[^:]*:[^.]*\.(?: Elija la cuenta correcta\.)?"
    r"|La cuenta \S+(?: \(\S+\))? es la que usted le puso a .*? en otro "
    r"cliente: compruebe que en este también va ahí\.)")


def quitar_aviso_cuenta(aviso: str) -> str:
    """Retira el aviso de cuenta propuesta cuando ya la ha fijado alguien."""
    return " ".join(_AVISO_CUENTA.sub("", aviso or "").split())
