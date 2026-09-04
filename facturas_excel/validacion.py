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


@dataclass
class Resultado:
    estado: str
    mensajes: List[str]


def fecha_de(fecha: str) -> Optional[date]:
    """Fecha de la factura. None si no se entiende lo leido.

    El programa NO trabaja por trimestres (se usa igual para un trimestre que
    para un requerimiento de varios años), asi que la fecha solo se comprueba
    para saber si la lectura es buena.
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


def validar_nif(nif: str) -> bool:
    """Valida DNI, NIE y CIF espanoles por su digito/letra de control."""
    if not nif:
        return False
    nif = nif.strip().upper().replace("-", "").replace(" ", "")
    tabla_dni = "TRWAGMYFPDXBNJZSQVHLCKE"

    # NIE: X/Y/Z -> 0/1/2
    if nif and nif[0] in "XYZ":
        nif = str("XYZ".index(nif[0])) + nif[1:]

    # DNI / NIE
    if len(nif) == 9 and nif[:8].isdigit() and nif[8].isalpha():
        return tabla_dni[int(nif[:8]) % 23] == nif[8]

    # CIF: letra inicial + 7 digitos + control
    if len(nif) == 9 and nif[0].isalpha() and nif[0] in "ABCDEFGHJNPQRSUVW":
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
        if c.isdigit():
            return int(c) == control
        return c == "JABCDEFGHI"[control]

    return False


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

    def marcar_revisar(m):
        nonlocal estado
        msgs.append(m)
        if estado == OK:
            estado = REVISAR

    def marcar_error(m):
        nonlocal estado
        msgs.append(m)
        estado = ERROR

    # Campos obligatorios en Aplifisa: Justificante/Fra.Proveedor, Fecha,
    # Concepto y Nombre. Si falta alguno, el registro da error al importar.
    if not f.fecha:
        marcar_error("Falta la fecha (obligatorio)")
    elif fecha_de(f.fecha) is None:
        # Fecha ilegible: Aplifisa la rechazaria y ademas delata una mala
        # lectura de la factura entera.
        marcar_error(f"No se entiende la fecha «{f.fecha}»: "
                     f"debe ser dd/mm/aaaa")
    if not f.num_factura:
        marcar_error("Falta el nº de factura (obligatorio)")
    if not f.nombre:
        marcar_error("Falta el nombre (obligatorio)")
    if not f.concepto:
        marcar_error("Falta el concepto (obligatorio)")
    else:
        marcar_revisar_concepto(f, marcar_revisar)

    # NIF: sin NIF o que no valida -> revisar (puede ser OCR o NIF extranjero),
    # no bloquea, pero avisa para que se compruebe.
    if not f.nif:
        marcar_revisar("Falta el NIF")
    elif not validar_nif(f.nif):
        marcar_revisar(f"NIF/CIF dudoso (no pasa el digito de control): {f.nif}")

    # Verde significa que están presentes todos los importes necesarios para
    # el flujo rutinario. Antes, al faltar todos, no se ejecutaba ninguna
    # comprobación aritmética y la fila podía parecer correcta.
    if f.base_iva is None:
        marcar_error("Falta la base imponible")
    if f.total_impreso is None:
        marcar_error("Falta el total de la factura")
    if not f.es_suplido and not f.iva_incluido_en_base:
        if f.pct_iva is None:
            marcar_error("Falta el tipo de IVA")
        if f.cuota_iva is None:
            marcar_error("Falta la cuota de IVA")

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
            marcar_revisar("Falta la cuota de IVA")
        elif abs(f.cuota_iva - esperada) > TOLERANCIA:
            marcar_error(
                f"Cuota IVA descuadra: {f.cuota_iva} pero base×% = {esperada}"
            )

    # Si aparece parte de un impuesto, tienen que estar sus tres piezas. Un
    # dato parcial no se puede interpretar de forma segura como cero.
    irpf = (f.base_irpf, f.pct_irpf, f.cuota_irpf)
    if any(v is not None for v in irpf) and not all(v is not None for v in irpf):
        marcar_error("IRPF incompleto: faltan base, porcentaje o cuota")
    recargo = (f.base_requiv, f.pct_requiv, f.cuota_requiv)
    if any(v is not None for v in recargo) and not all(v is not None for v in recargo):
        marcar_error("Recargo de equivalencia incompleto")

    # Recargo de equivalencia: su tipo lo fija el del IVA, y la cuota sale de
    # la base. Un recargo mal leido no descuadra siempre el total (son céntimos),
    # asi que hay que comprobarlo aparte.
    if f.pct_requiv is not None and f.pct_iva is not None:
        esperado = RECARGO_DE_IVA.get(round(float(f.pct_iva), 2))
        if esperado is not None and abs(f.pct_requiv - esperado) > 0.01:
            marcar_revisar(
                f"El recargo del {porcentaje(f.pct_iva)}% de IVA es "
                f"{porcentaje(esperado)}%, no {porcentaje(f.pct_requiv)}%")
    if f.base_requiv is not None and f.pct_requiv is not None:
        esperada = round(f.base_requiv * f.pct_requiv / 100.0, 2)
        if f.cuota_requiv is None:
            marcar_revisar("Falta la cuota del recargo de equivalencia")
        elif abs(f.cuota_requiv - esperada) > TOLERANCIA:
            marcar_error(
                f"Cuota del recargo descuadra: {f.cuota_requiv} pero "
                f"base×% = {esperada}")

    # Aritmetica del IRPF
    if f.base_irpf is not None and f.pct_irpf is not None and f.cuota_irpf is not None:
        esperada = round(f.base_irpf * f.pct_irpf / 100.0, 2)
        if abs(f.cuota_irpf - esperada) > TOLERANCIA:
            marcar_error(
                f"Cuota IRPF descuadra: {f.cuota_irpf} pero base×% = {esperada}"
            )

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
                f"importes van en negativo."
            )
        calculado = (f.base_iva or 0) + (f.cuota_iva or 0) \
            + (f.cuota_requiv or 0) + (f.suplidos or 0) \
            - (f.cuota_irpf or 0)
        calculado = round(calculado, 2)
        if abs(calculado - f.total_impreso) > TOLERANCIA:
            marcar_revisar(
                f"El total no cuadra: factura pone {f.total_impreso}, "
                f"base+cuota+suplidos−retención = {calculado} "
                f"(¿falta algún suplido/retención/financiación?)"
            )

    return Resultado(estado=estado, mensajes=msgs)


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


def huecos_de_numeracion(facturas: List[Factura]) -> List[str]:
    """Numeros que faltan en una serie seguida del mismo emisor.

    Devuelve avisos ya escritos. Es un AVISO, no un error: puede que esa
    factura simplemente no la haya traido el cliente.
    """
    series: Dict[tuple, List[tuple]] = {}
    for f in facturas:
        trozos = _trozos(f.num_factura)
        if not trozos:
            continue
        texto, numeros = trozos
        clave = ((f.nif or f.nombre or "").strip().upper(), texto, len(numeros))
        series.setdefault(clave, []).append((numeros, f.nombre or ""))

    avisos = []
    for (_, texto, cuantos), entradas in series.items():
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
