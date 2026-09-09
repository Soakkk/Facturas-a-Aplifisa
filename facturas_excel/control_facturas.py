"""Controles del documento completo, independientes de la tabla y del Excel."""
from collections import Counter, defaultdict
import re

from .modelo import Factura
from .validacion import TOLERANCIA, fecha_de


def clave_documento(f: Factura):
    if getattr(f, 'documento_id', ''):
        return ('id', f.documento_id)
    # Compatibilidad con sesiones antiguas. Una fila sin referencia compartida
    # y sin varias líneas declaradas representa un documento independiente.
    if f.lineas_factura > 1:
        return ('anterior', f.origen_imagen, f.pagina_origen,
                f.num_factura, f.fecha, f.nif)
    return ('fila', id(f))


def grupos_documentos(facturas):
    grupos = defaultdict(list)
    for i, f in enumerate(facturas):
        grupos[clave_documento(f)].append(i)
    return list(grupos.values())


def sin_cuadre_antiguo(aviso):
    """Retira solo el mensaje calculado al construir, conservando evidencias."""
    return re.sub(r'El total no cuadra: la factura pone [-\d.]+ y sus '
                  r'\d+ líneas de IVA suman [-\d.]+\.', '', aviso or '').strip()


def controles_documentos(facturas, tipos):
    """Devuelve errores por fila y copias COMPLETAS descartables {fila: original}."""
    errores = defaultdict(list)
    duplicados = {}
    grupos = grupos_documentos(facturas)
    candidatos = defaultdict(list)

    def avisar(filas, texto):
        for i in filas:
            errores[i].append(texto)

    for indices in grupos:
        fs = [facturas[i] for i in indices]
        f = fs[0]
        if len(fs) != f.lineas_factura or any(g.lineas_factura != len(fs) for g in fs):
            avisar(indices, 'Factura incompleta: faltan líneas del documento. '
                   'Restaure las líneas eliminadas o aparte la factura completa.')
        if any((g.num_factura, g.fecha, g.nif, g.nombre) !=
               (f.num_factura, f.fecha, f.nif, f.nombre) for g in fs):
            avisar(indices, 'Las líneas de esta factura no tienen la misma '
                   'identificación (número, fecha, NIF o nombre). Corríjalas juntas.')
        if len({tipos[i] for i in indices}) != 1:
            avisar(indices, 'Una factura no puede tener líneas como gasto y otras '
                   'como ingreso. Compruebe el tipo de todas sus líneas.')
        if any(g.tratamiento_manual for g in fs) and not all(g.tratamiento_manual for g in fs):
            avisar(indices, 'La gestión manual debe aplicarse a la factura completa.')
        totales = {g.total_impreso for g in fs if g.total_impreso is not None}
        if len(totales) > 1:
            avisar(indices, 'Las líneas de la misma factura tienen distintos totales impresos.')
        if len(fs) > 1 and len(totales) == 1 and all(g.base_iva is not None for g in fs):
            total = next(iter(totales))
            suma = round(sum((g.base_iva or 0) + (g.cuota_iva or 0)
                             + (g.cuota_requiv or 0) + (g.suplidos or 0)
                             - (g.cuota_irpf or 0) for g in fs), 2)
            if abs(suma-total) > TOLERANCIA:
                avisar(indices, f'El total no cuadra: impreso {total:.2f} €, '
                       f'calculado {suma:.2f} €, diferencia {suma-total:+.2f} €. '
                       'Compruebe el desglose de la factura completa.')
        numero = (f.num_factura or '').strip().upper()
        nif = re.sub(r'[.\s-]', '', (f.nif or '').upper())
        fecha = fecha_de(f.fecha)
        if numero and nif and fecha:
            candidatos[(numero, nif, fecha.year, tipos[indices[0]])].append(indices)

    # No excluir partes. Una identidad repetida con datos distintos bloquea
    # ambas lecturas, incluso si alguna línea coincide exactamente.
    campos = ('fecha', 'num_factura', 'nif', 'base_iva', 'pct_iva', 'cuota_iva',
              'base_irpf', 'pct_irpf', 'cuota_irpf', 'base_requiv', 'pct_requiv',
              'cuota_requiv', 'total_impreso', 'es_suplido', 'suplidos',
              'concepto', 'subclave', 'tratamiento_manual', 'iva_incluido_en_base')
    def firma(indices):
        return Counter(tuple(getattr(facturas[i], c) for c in campos) for i in indices)
    for versiones in candidatos.values():
        if len(versiones) < 2:
            continue
        original = versiones[0]
        if any(firma(v) != firma(original) for v in versiones[1:]):
            for v in versiones:
                avisar(v, 'Posible duplicado con datos distintos: hay varias '
                       'lecturas de la misma factura. Compare los documentos '
                       'y elimine la copia incorrecta completa.')
        else:
            for copia in versiones[1:]:
                for i in copia:
                    duplicados[i] = original[0]
    return dict(errores), duplicados
