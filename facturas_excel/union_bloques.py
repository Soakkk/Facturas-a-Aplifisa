"""Continuaciones entre partes internas de un mismo PDF.

Solo se reconstruyen los dos documentos de la frontera. Las demás facturas,
correcciones y metadatos del bloque conservan sus objetos originales.
"""

from .procesar import (
    _anadir_aviso, _mismo_origen, consolidar_paginas_factura,
    normaliza_nif, preparar_lote,
)


def _indices_crudos(bloque: dict, pr) -> list[int]:
    ultima = max([pr.pagina] + [f.ultima_pagina_origen or f.pagina_origen
                               for f in pr.facturas])
    return [i for i, (_, origen, pagina, _) in enumerate(bloque.get("crudos", []))
            if _mismo_origen(origen, pr.origen) and pr.pagina <= pagina <= ultima]


def _editada(pr) -> bool:
    return any(getattr(f, "edicion_manual", False) or f.revision_confirmada
               or f.tipo_revision or f.eliminada or f.tratamiento_manual
               for f in pr.facturas)


def unir_ultimo_bloque(bloques: list[dict]) -> bool:
    """Une la última factura anterior con la primera nueva si son continuaciones.

    Devuelve True solo cuando se realiza la unión. Una continuidad con revisión
    humana conserva las dos facturas y añade un aviso para decidir la unión.
    Los crudos consumidos se trasladan al bloque anterior sin alterarlos, para
    poder reconstruirlo y consultar sus páginas físicas más adelante.
    """
    if len(bloques) < 2:
        return False
    nuevo = bloques[-1]
    if not nuevo.get("procesadas"):
        return False
    pr_b = nuevo["procesadas"][0][1]
    posicion = len(bloques) - 2
    ids_saltados = set()
    while posicion >= 0 and not bloques[posicion].get("procesadas"):
        vacio = bloques[posicion]
        consumido = vacio.get("_consumido_por_union")
        if vacio.get("crudos") or not consumido:
            return False
        if (normaliza_nif(vacio.get("nif")) != normaliza_nif(nuevo.get("nif"))
                or normaliza_nif(consumido.get("nif")) != normaliza_nif(nuevo.get("nif"))
                or not _mismo_origen(consumido.get("origen"), pr_b.origen)):
            return False
        if vacio.get("original") and not _mismo_origen(vacio["original"], pr_b.origen):
            return False
        for identidad in (consumido.get("original_id"), vacio.get("original_id")):
            if identidad:
                ids_saltados.add(identidad)
        posicion -= 1
    if posicion < 0:
        return False
    anterior = bloques[posicion]
    nif = normaliza_nif(anterior.get("nif"))
    if not nif or nif != normaliza_nif(nuevo.get("nif")):
        return False
    if not anterior.get("procesadas") or not nuevo.get("procesadas"):
        return False
    pr_a = anterior["procesadas"][-1][1]
    pr_b = nuevo["procesadas"][0][1]
    originales = {getattr(f, "original_id", "")
                  for pr in (pr_a, pr_b) for f in pr.facturas
                  if getattr(f, "original_id", "")}
    originales.update(ids_saltados)
    if len(originales) > 1:
        return False
    original_id = next(iter(originales), "")
    indices_a, indices_b = _indices_crudos(anterior, pr_a), _indices_crudos(nuevo, pr_b)
    if not indices_a or not indices_b:
        return False
    crudos_a = [anterior["crudos"][i] for i in indices_a]
    crudos_b = [nuevo["crudos"][i] for i in indices_b]
    candidatos = crudos_a + crudos_b
    if len(consolidar_paginas_factura(candidatos)) != 1:
        return False
    if _editada(pr_a) or _editada(pr_b):
        aviso = ("Posible continuación entre bloques: hay una factura editada o "
                 "revisada. Comprueba las páginas y decide la unión manual.")
        for pr in (pr_a, pr_b):
            if aviso not in pr.aviso:
                _anadir_aviso(pr, aviso)
        return False
    reconstruidas = preparar_lote(candidatos, anterior.get("cliente", ""), nif)
    if len(reconstruidas) != 1:
        return False
    for f in reconstruidas[0][1].facturas:
        f.original_id = original_id
    anterior["procesadas"][-1] = reconstruidas[0]
    del nuevo["procesadas"][0]
    # Mantener los originales, no la copia consolidada, conserva las imágenes
    # y los datos de cada hoja para una revisión posterior.
    insercion = indices_a[-1] + 1
    anterior["crudos"][insercion:insercion] = crudos_b
    consumidos = set(indices_b)
    nuevo["crudos"] = [r for i, r in enumerate(nuevo["crudos"]) if i not in consumidos]
    if not nuevo["procesadas"] and not nuevo["crudos"]:
        nuevo["_consumido_por_union"] = {
            "nif": nif, "origen": pr_b.origen,
            "original_id": original_id or nuevo.get("original_id", ""),
        }
    return True
