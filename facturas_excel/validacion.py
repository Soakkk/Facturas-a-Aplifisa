"""Controles de calidad de una factura antes de exportar.

Idea central: NO fiarse de lo que "lee" la IA; comprobarlo con las propias
cuentas de la factura. Un digito mal leido casi siempre rompe alguna cuenta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

from .modelo import Factura

# Estados (semaforo)
OK = "ok"            # verde: todo cuadra
REVISAR = "revisar"  # ambar: falta un dato o hay algo dudoso
ERROR = "error"      # rojo: una cuenta no cuadra

TOLERANCIA = 0.02  # euros de margen por redondeos

# El recargo de equivalencia va SIEMPRE emparejado con su tipo de IVA: es el
# regimen quien lo fija, no el proveedor (confirmado por el usuario 2026-09-02).
RECARGO_DE_IVA = {21.0: 5.2, 10.0: 1.4, 4.0: 0.5}


# Tipos de IVA que existen o han existido recientemente en España: los
# generales (21, 10, 4), los temporales de 2021-2024 (0, 5, 2 y 7,5 en luz,
# gas y alimentos) y la exención (0). Un 22 % o un 12 % solo sale de una mala
# lectura, aunque la cuota cuadre con él.
TIPOS_IVA_VALIDOS = {0.0, 2.0, 4.0, 5.0, 7.5, 10.0, 21.0}


class Incidencia(str):
    """Un aviso de la validación con el dato al que se refiere.

    Sigue siendo un texto (todo lo que ya trabaja con mensajes funciona igual),
    pero lleva además los campos afectados y su gravedad. Así la pantalla
    colorea la celda culpable sin tener que adivinarlo leyendo la frase.
    """

    def __new__(cls, texto: str, campos=(), gravedad: str = "revisar"):
        obj = super().__new__(cls, texto)
        obj.campos = tuple(campos)
        obj.gravedad = gravedad
        return obj

    def __reduce__(self):
        return (Incidencia, (str(self), self.campos, self.gravedad))


@dataclass
class Resultado:
    estado: str
    mensajes: List[str]


def _hoy() -> date:
    return date.today()


def fecha_de(fecha: str) -> Optional[date]:
    """Fecha de la factura. None si no se entiende lo leido.

    La validación básica solo comprueba que la fecha exista. El periodo fiscal
    esperado del lote se controla aparte en la interfaz.
    """
    if not fecha:
        return None
    texto = str(fecha).strip()
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


_TABLA_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
# Prefijos de NIF-IVA de la Unión Europea (el de Grecia es EL).
PREFIJOS_UE = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "FI", "FR",
    "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT",
    "RO", "SE", "SI", "SK", "XI",
}


def _limpiar_nif(nif) -> str:
    return str(nif or "").strip().upper().replace("-", "").replace(" ", "") \
        .replace(".", "")


def validar_nif(nif: str) -> bool:
    """Valida DNI, NIE, NIF K/L/M y CIF españoles por su dígito de control.

    En los CIF el tipo de entidad decide si el control es letra o número: una
    S.L. (B) o una S.A. (A) terminan SIEMPRE en número, y un organismo público
    (P, Q, S) o una entidad extranjera (N, W) SIEMPRE en letra. Admitir
    cualquiera de las dos formas daba por buenos CIF mal leídos.
    """
    nif = _limpiar_nif(nif)
    if len(nif) != 9:
        return False

    # NIE: X/Y/Z -> 0/1/2
    if nif[0] in "XYZ":
        nif = str("XYZ".index(nif[0])) + nif[1:]

    # DNI / NIE
    if nif[:8].isdigit() and nif[8].isalpha():
        return _TABLA_DNI[int(nif[:8]) % 23] == nif[8]

    # NIF de personas físicas sin DNI: K (menores), L (no residentes), M
    # (extranjeros sin NIE). La letra se calcula con los 7 dígitos.
    if nif[0] in "KLM" and nif[1:8].isdigit() and nif[8].isalpha():
        return _TABLA_DNI[int(nif[1:8]) % 23] == nif[8]

    # CIF: letra inicial + 7 digitos + control
    if nif[0] in "ABCDEFGHJNPQRSUVW":
        digitos = nif[1:8]
        if not digitos.isdigit():
            return False
        suma_par = sum(int(digitos[i]) for i in (1, 3, 5))
        suma_impar = 0
        for i in (0, 2, 4, 6):
            d = int(digitos[i]) * 2
            suma_impar += d if d < 10 else d - 9
        control = (10 - (suma_par + suma_impar) % 10) % 10
        c = nif[8]
        letra = "JABCDEFGHI"[control]
        if nif[0] in "NPQRSW":
            return c == letra
        if nif[0] in "ABEH":
            return c == str(control)
        return c == str(control) or c == letra

    return False


def clasificar_nif(nif) -> str:
    """Qué clase de identificador es, para avisar con el motivo exacto.

    - "valido": NIF español correcto.
    - "es_prefijo": NIF español correcto con el prefijo ES del NIF-IVA.
    - "ue": NIF-IVA de otro país de la UE (no se puede comprobar su control).
    - "invalido": ni una cosa ni otra (casi siempre, un dígito mal leído).
    """
    limpio = _limpiar_nif(nif)
    if validar_nif(limpio):
        return "valido"
    if limpio.startswith("ES") and validar_nif(limpio[2:]):
        return "es_prefijo"
    if len(limpio) >= 6 and limpio[:2] in PREFIJOS_UE \
            and limpio[2:].isalnum() and any(c.isdigit() for c in limpio[2:]):
        return "ue"
    return "invalido"


def marcar_revisar_concepto(f: Factura, marcar_revisar) -> None:
    """Comprueba el concepto contra el catalogo REAL de Aplifisa.

    El registro tiene que quedar con la cuenta que toca: si la cuenta no existe
    alli, o la pareja cuenta+subclave no es una de las suyas, al importar se
    queda a revisar (o entra en un concepto que no es).
    """
    from .conceptos import descripcion_de, es_valido, subclaves_de

    cuenta = str(f.concepto or "").strip()
    gxx = (f.subclave or "").strip().upper()
    if not es_valido(cuenta):
        marcar_revisar(f"La cuenta {cuenta} no está en la lista de conceptos "
                       f"de Aplifisa: compruébela")
        return
    posibles = subclaves_de(cuenta)
    if not gxx:
        if len(posibles) == 1:
            return          # solo hay una: la pone Aplifisa sola
        opciones = ", ".join(f"{g} {d.lower()}" for g, d in posibles)
        marcar_revisar(f"La cuenta {cuenta} necesita subclave. Opciones: "
                       f"{opciones}")
    elif not es_valido(cuenta, gxx):
        opciones = ", ".join(g for g, _ in posibles)
        marcar_revisar(f"{cuenta} ({gxx}) no existe en Aplifisa. "
                       f"Subclaves de la {cuenta}: {opciones}")
    else:
        # Todo correcto: se deja el nombre del concepto a la vista.
        f.descripcion_concepto = descripcion_de(cuenta, gxx)


def porcentaje(v) -> str:
    """21, 10, 5,2... como se escribe, sin ceros de sobra."""
    v = float(v)
    return str(int(v)) if v.is_integer() else f"{v:g}".replace(".", ",")


def validar(f: Factura) -> Resultado:
    msgs: List[str] = []
    estado = OK

    def marcar_revisar(m, *campos):
        nonlocal estado
        msgs.append(Incidencia(m, campos, REVISAR))
        if estado == OK:
            estado = REVISAR

    def marcar_error(m, *campos):
        nonlocal estado
        msgs.append(Incidencia(m, campos, ERROR))
        estado = ERROR

    # Campos obligatorios en Aplifisa: Justificante/Fra.Proveedor, Fecha,
    # Concepto y Nombre. Si falta alguno, el registro da error al importar.
    dia = fecha_de(f.fecha) if f.fecha else None
    if not f.fecha:
        marcar_error("Falta la fecha (obligatorio)", "fecha")
    elif dia is None:
        # Fecha ilegible: Aplifisa la rechazaria y ademas delata una mala
        # lectura de la factura entera.
        marcar_error(f"No se entiende la fecha «{f.fecha}»: "
                     f"debe ser dd/mm/aaaa", "fecha")
    else:
        hoy = _hoy()
        if dia > hoy:
            # Una factura no puede estar fechada en el futuro: es un año o un
            # mes mal leido (2026 -> 2028, 03 -> 08).
            marcar_error(f"Fecha futura: {f.fecha} es posterior a hoy. "
                         "Casi seguro que el año o el mes están mal leídos",
                         "fecha")
        # Una fecha antigua NO se marca: en un requerimiento las facturas
        # son de cualquier año y todas valen (criterio del usuario).
        operacion = fecha_de(f.fecha_operacion) if f.fecha_operacion else None
        if operacion and operacion > dia and (operacion - dia).days > 31:
            marcar_revisar(f"La fecha de operación ({f.fecha_operacion}) es "
                           f"posterior a la de la factura ({f.fecha}): "
                           "compruebe las dos", "fecha")
    if not f.num_factura:
        marcar_error("Falta el nº de factura (obligatorio)", "num_factura")
    if not f.nombre:
        marcar_error("Falta el nombre (obligatorio)", "nombre")
    if not f.concepto:
        marcar_error("Falta el concepto (obligatorio)", "concepto")
    else:
        marcar_revisar_concepto(
            f, lambda m: marcar_revisar(m, "concepto", "subclave"))

    # NIF: sin NIF o que no valida -> revisar (puede ser OCR o NIF extranjero),
    # no bloquea, pero avisa para que se compruebe con el motivo exacto.
    if not f.nif:
        marcar_revisar("Falta el NIF", "nif")
    else:
        clase = clasificar_nif(f.nif)
        if clase == "es_prefijo":
            marcar_revisar(f"NIF con prefijo ES de operador intracomunitario "
                           f"({f.nif}): en Aplifisa se registra sin «ES»",
                           "nif")
        elif clase == "ue":
            marcar_revisar(f"NIF extranjero de la UE ({f.nif}): su dígito de "
                           "control no se puede comprobar. Revise la factura "
                           "(posible operación intracomunitaria)", "nif")
        elif clase == "invalido":
            marcar_revisar(f"NIF/CIF dudoso (no pasa el digito de control): "
                           f"{f.nif}", "nif")

    # Verde significa que están presentes todos los importes necesarios para
    # el flujo rutinario. Antes, al faltar todos, no se ejecutaba ninguna
    # comprobación aritmética y la fila podía parecer correcta.
    if f.base_iva is None:
        marcar_error("Falta la base imponible", "base_iva")
    if f.total_impreso is None:
        marcar_error("Falta el total de la factura", "total_impreso")
    if not f.es_suplido and not f.iva_incluido_en_base:
        if f.pct_iva is None:
            marcar_error("Falta el tipo de IVA", "pct_iva")
        if f.cuota_iva is None:
            marcar_error("Falta la cuota de IVA", "cuota_iva")

    # Un tipo que no existe en España delata una mala lectura aunque la cuota
    # cuadre con él (la IA puede leer mal el tipo Y calcular la cuota).
    if f.pct_iva is not None and round(abs(float(f.pct_iva)), 2) \
            not in TIPOS_IVA_VALIDOS:
        marcar_error(f"Tipo de IVA {porcentaje(abs(f.pct_iva))}% no existe en "
                     "España (21, 10, 5, 4, 2 o 0): revise el tipo leído",
                     "pct_iva")

    confianza = str(f.confianza_ia or "").strip().lower()
    if confianza in {"media", "baja"}:
        marcar_revisar(
            f"Confianza de lectura {confianza}: compare los datos con el PDF")
    if f.tratamiento_manual:
        marcar_revisar(
            f"Gestión manual: {f.tratamiento_manual}. No se incluirá en la "
            "exportación automática")

    # Aritmetica del IVA: cuota = base * % / 100
    if f.base_iva is not None and f.pct_iva is not None:
        esperada = round(f.base_iva * f.pct_iva / 100.0, 2)
        if f.cuota_iva is None:
            marcar_revisar("Falta la cuota de IVA", "cuota_iva")
        elif abs(f.cuota_iva - esperada) > TOLERANCIA:
            marcar_error(
                f"Cuota IVA descuadra: {f.cuota_iva} pero base×% = {esperada}",
                "cuota_iva", "base_iva", "pct_iva")

    # Si aparece parte de un impuesto, tienen que estar sus tres piezas. Un
    # dato parcial no se puede interpretar de forma segura como cero.
    irpf = (f.base_irpf, f.pct_irpf, f.cuota_irpf)
    if any(v is not None for v in irpf) and not all(v is not None for v in irpf):
        marcar_error("IRPF incompleto: faltan base, porcentaje o cuota",
                     "base_irpf", "pct_irpf", "cuota_irpf")
    recargo = (f.base_requiv, f.pct_requiv, f.cuota_requiv)
    if any(v is not None for v in recargo) and not all(v is not None for v in recargo):
        marcar_error("Recargo de equivalencia incompleto",
                     "base_requiv", "pct_requiv", "cuota_requiv")

    # Recargo de equivalencia: su tipo lo fija el del IVA, y la cuota sale de
    # la base. Un recargo mal leido no descuadra siempre el total (son céntimos),
    # asi que hay que comprobarlo aparte.
    if f.pct_requiv is not None and f.pct_iva is not None:
        esperado = RECARGO_DE_IVA.get(round(float(f.pct_iva), 2))
        if esperado is not None and abs(f.pct_requiv - esperado) > 0.01:
            marcar_revisar(
                f"El recargo del {porcentaje(f.pct_iva)}% de IVA es "
                f"{porcentaje(esperado)}%, no {porcentaje(f.pct_requiv)}%",
                "pct_requiv")
    if f.base_requiv is not None and f.pct_requiv is not None:
        esperada = round(f.base_requiv * f.pct_requiv / 100.0, 2)
        if f.cuota_requiv is None:
            marcar_revisar("Falta la cuota del recargo de equivalencia",
                           "cuota_requiv")
        elif abs(f.cuota_requiv - esperada) > TOLERANCIA:
            marcar_error(
                f"Cuota del recargo descuadra: {f.cuota_requiv} pero "
                f"base×% = {esperada}", "cuota_requiv")

    # Aritmetica del IRPF
    if f.base_irpf is not None and f.pct_irpf is not None and f.cuota_irpf is not None:
        esperada = round(f.base_irpf * f.pct_irpf / 100.0, 2)
        if abs(f.cuota_irpf - esperada) > TOLERANCIA:
            marcar_error(
                f"Cuota IRPF descuadra: {f.cuota_irpf} pero base×% = {esperada}",
                "cuota_irpf")

    # Cuadre con el total impreso: si no cuadra puede haber suplidos, retencion
    # o financiacion (ej. moviles a plazos) que no son base imponible -> revisar,
    # no bloquea (la base y la cuota pueden ser correctas para el impuesto).
    # Solo tiene sentido si la fila ES la factura entera: con varios tipos de IVA
    # cada fila es un trozo y nunca cuadraria sola (el cuadre lo hace construir).
    if f.total_impreso is not None and f.base_iva is not None and f.lineas_factura == 1:
        # Abono leido a medias: los proveedores que ponen el signo detras
        # ("15,51-" = -15,51) despistan y se pierde el menos por el camino.
        # Registrar un abono en positivo COBRA lo que habia que devolver.
        if (f.total_impreso < 0) != (f.base_iva < 0):
            marcar_error(
                f"El signo no cuadra: el total es {f.total_impreso} y la base "
                f"{f.base_iva}. ¿Es un abono/devolución? En un abono TODOS los "
                f"importes van en negativo.", "total_impreso", "base_iva"
            )
        calculado = cuadre_de(f)
        if abs(calculado - f.total_impreso) > TOLERANCIA:
            marcar_revisar(
                f"El total no cuadra: factura pone {f.total_impreso}, "
                f"base+cuota+suplidos−retención = {calculado} "
                f"(¿falta algún suplido/retención/financiación?)",
                "total_impreso"
            )

    return Resultado(estado=estado, mensajes=msgs)


def cuadre_de(f: Factura) -> float:
    """Base + IVA + recargo + suplidos − retención de una fila."""
    return round((f.base_iva or 0) + (f.cuota_iva or 0)
                 + (f.cuota_requiv or 0) + (f.suplidos or 0)
                 - (f.cuota_irpf or 0), 2)


def encontrar_duplicados(facturas: List[Factura]) -> Dict[int, int]:
    """Facturas repetidas dentro del lote: {fila duplicada: fila original}.

    Misma factura = mismo nº + NIF + base + tipo de IVA. El tipo entra en la
    clave porque una factura con varios tipos de IVA son VARIAS filas con el
    mismo nº y NIF, y si dos de sus lineas tuvieran la misma base se marcarian
    como duplicadas sin serlo.
    """
    vistos: Dict[tuple, int] = {}
    dups: Dict[int, int] = {}
    for i, f in enumerate(facturas):
        clave = (
            (f.num_factura or "").strip().upper(),
            (f.nif or "").strip().upper(),
            round(f.base_iva or 0, 2),
            round(f.pct_iva or 0, 2),
        )
        if not any(clave):
            continue          # fila vacia: no se compara
        if clave in vistos:
            dups[i] = vistos[clave]
        else:
            vistos[clave] = i
    return dups


# --------------------------------------------------- huecos en la numeracion
# El alimentador arrastra a veces dos hojas pegadas y de esa factura NO se
# entera nadie: no da error, simplemente no esta. Si un mismo emisor lleva una
# serie seguida, un salto en la numeracion delata la hoja que falta.
#
# El numero de serie puede ir en cualquier sitio ("01/25", "F-2025-014",
# "A25/7"), asi que la factura se parte en trozos de texto y numeros, se
# agrupan las que comparten la misma forma, y se mira el unico numero que
# cambia entre ellas: ese es el contador.
MINIMO_SERIE = 3        # con menos de 3 no hay serie que valga
MAXIMO_HUECO = 12       # un salto enorme suele ser otra serie, no una perdida


def _trozos(num_factura: str):
    """'01/25' -> (('', '/', ''), ('01', '25')): la forma y los numeros."""
    partes = re.split(r"(\d+)", str(num_factura or "").strip().upper())
    if len(partes) < 3:            # sin ningun numero: no hay serie posible
        return None
    texto = tuple(partes[0::2])
    numeros = tuple(partes[1::2])
    return texto, numeros


def huecos_de_numeracion(facturas: List[Factura], tipos: List[str] | None = None,
                         cliente_nombre: str = "") -> List[str]:
    """Numeros que faltan en una serie seguida del mismo emisor.

    Devuelve avisos ya escritos. Es un AVISO, no un error: puede que esa
    factura simplemente no la haya traido el cliente.

    En los gastos, el emisor es la contraparte guardada en ``Factura`` y cada
    proveedor lleva su serie. En los ingresos ocurre al reves: el emisor es el
    cliente de la asesoria, mientras ``Factura.nombre`` es cada comprador. Por
    eso todas las ventas del lote se comprueban juntas, no comprador a
    comprador. Las varias lineas de IVA de un mismo apunte cuentan una vez.
    """
    series: Dict[tuple, Dict[str, tuple]] = {}
    for indice, f in enumerate(facturas):
        trozos = _trozos(f.num_factura)
        if not trozos:
            continue
        texto, numeros = trozos
        tipo = tipos[indice] if tipos and indice < len(tipos) else ""
        es_venta = tipo in ("venta", "ingreso")
        if es_venta:
            identidad = "__SERIE_INGRESOS__"
            quien = cliente_nombre or "la serie de ingresos del cliente"
        else:
            identidad = (f.nif or f.nombre or "").strip().upper()
            quien = f.nombre or ""
        clave = (identidad, texto, len(numeros))
        numero_completo = str(f.num_factura or "").strip().upper()
        series.setdefault(clave, {}).setdefault(
            numero_completo, (numeros, quien))

    avisos = []
    for (_, texto, cuantos), por_numero in series.items():
        entradas = list(por_numero.values())
        if len(entradas) < MINIMO_SERIE:
            continue
        # El contador es el unico hueco numerico que cambia (el resto suele ser
        # el año o el codigo de serie, y tiene que quedarse igual).
        cambian = [i for i in range(cuantos)
                   if len({numeros[i] for numeros, _ in entradas}) > 1]
        if len(cambian) != 1:
            continue
        col = cambian[0]
        vistos = {int(numeros[col]) for numeros, _ in entradas}
        faltan = [n for n in range(min(vistos), max(vistos)) if n not in vistos]
        if not faltan or len(faltan) > MAXIMO_HUECO:
            continue
        modelo, quien = entradas[0]
        ancho = len(modelo[col])

        def escribir(n):
            partes = list(modelo)
            partes[col] = f"{n:0{ancho}d}"
            return "".join(t + p for t, p in zip(texto, partes)) + texto[-1]

        cuales = ", ".join(escribir(n) for n in faltan[:8])
        avisos.append(
            f"FALTA la factura {cuales} de {quien or 'este emisor'}: la "
            f"numeración salta. ¿Se han quedado hojas pegadas en el "
            f"alimentador o sin traer?")
    return avisos
