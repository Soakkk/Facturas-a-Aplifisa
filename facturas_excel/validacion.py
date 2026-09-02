"""Controles de calidad de una factura antes de exportar.

Idea central: NO fiarse de lo que "lee" la IA; comprobarlo con las propias
cuentas de la factura. Un digito mal leido casi siempre rompe alguna cuenta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

from .modelo import Factura

# Estados (semaforo)
OK = "ok"            # verde: todo cuadra
REVISAR = "revisar"  # ambar: falta un dato o hay algo dudoso
ERROR = "error"      # rojo: una cuenta no cuadra

TOLERANCIA = 0.02  # euros de margen por redondeos


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
        marcar_revisar(f"No se entiende la fecha «{f.fecha}»: "
                       f"debe ser dd/mm/aaaa")
    if not f.num_factura:
        marcar_error("Falta el nº de factura (obligatorio)")
    if not f.nombre:
        marcar_error("Falta el nombre (obligatorio)")
    if not f.concepto:
        marcar_error("Falta el concepto (obligatorio)")

    # NIF: sin NIF o que no valida -> revisar (puede ser OCR o NIF extranjero),
    # no bloquea, pero avisa para que se compruebe.
    if not f.nif:
        marcar_revisar("Falta el NIF")
    elif not validar_nif(f.nif):
        marcar_revisar(f"NIF/CIF dudoso (no pasa el digito de control): {f.nif}")

    # Aritmetica del IVA: cuota = base * % / 100
    if f.base_iva is not None and f.pct_iva is not None:
        esperada = round(f.base_iva * f.pct_iva / 100.0, 2)
        if f.cuota_iva is None:
            marcar_revisar("Falta la cuota de IVA")
        elif abs(f.cuota_iva - esperada) > TOLERANCIA:
            marcar_error(
                f"Cuota IVA descuadra: {f.cuota_iva} pero base×% = {esperada}"
            )

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
            + (f.cuota_requiv or 0) - (f.cuota_irpf or 0)
        calculado = round(calculado, 2)
        if abs(calculado - f.total_impreso) > TOLERANCIA:
            marcar_revisar(
                f"El total no cuadra: factura pone {f.total_impreso}, "
                f"base+cuota = {calculado} (¿suplidos/retención/financiación?)"
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
