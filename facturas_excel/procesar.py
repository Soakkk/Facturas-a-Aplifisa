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

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .conceptos import DEFAULT_VENTA, asignar_concepto, subclave_628
from .extraccion import _num
from .modelo import Factura
from .validacion import validar_nif


def normaliza_nif(nif) -> str:
    if not nif:
        return ""
    return str(nif).strip().upper().replace(".", "").replace(" ", "").replace("-", "")


def _tokens_nombre(nombre) -> set:
    import unicodedata
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


def detectar_cliente(lista_datos: List[dict]) -> Tuple[str, str]:
    """Devuelve (nombre, nif) del cliente: el NIF mas repetido en el lote."""
    cuenta = Counter()
    nombres: Dict[str, list] = defaultdict(list)
    for d in lista_datos:
        for campo_nif, campo_nom in (("emisor_nif", "emisor_nombre"),
                                     ("receptor_nif", "receptor_nombre")):
            nif = normaliza_nif(d.get(campo_nif))
            if nif:
                cuenta[nif] += 1
                if d.get(campo_nom):
                    nombres[nif].append(d[campo_nom])
    if not cuenta:
        return ("", "")
    nif_cliente, _ = cuenta.most_common(1)[0]
    # nombre mas frecuente (y si empatan, el mas largo/completo)
    lista_nombres = nombres.get(nif_cliente, [])
    if lista_nombres:
        nombre = Counter(lista_nombres).most_common(1)[0][0]
    else:
        nombre = ""
    return (nombre, nif_cliente)


@dataclass
class FacturaProcesada:
    tipo: str                 # "gasto" / "venta"
    facturas: List[Factura]   # una por linea de IVA
    cuenta: str
    gxx: str | None
    origen: str
    pagina: int
    aviso: str = ""           # rol emisor/destinatario dudoso, etc.


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
        es_emisor = _mismo_nombre(e_nom, cliente_nombre)
        es_receptor = _mismo_nombre(r_nom, cliente_nombre)
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

    # Cuenta contable
    if tipo == "venta":
        cuenta = DEFAULT_VENTA
        gxx = None
    else:
        cuenta = str(datos.get("cuenta_gasto") or "").strip()
        texto = f"{datos.get('concepto_texto', '')} {datos.get('emisor_nombre', '')}"
        if not cuenta:  # respaldo por palabras clave si Gemini no dio cuenta
            cuenta = asignar_concepto("gasto", texto)
        gxx = datos.get("subclave_gxx") or (subclave_628(texto) if cuenta == "628" else None)

    # Construir Factura (una por linea de IVA)
    lineas = datos.get("lineas_iva") or [{}]
    comun = dict(
        num_factura=datos.get("num_factura") or None,
        fecha=datos.get("fecha") or None,
        fecha_operacion=datos.get("fecha_operacion") or None,
        nombre=nombre or None,
        nif=nif or None,
        concepto=cuenta or None,
        total_impreso=_num(datos.get("total")),
        origen_imagen=origen,
    )
    facturas = []
    for i, linea in enumerate(lineas):
        f = Factura(**comun)
        f.base_iva = _num(linea.get("base"))
        f.pct_iva = _num(linea.get("tipo_iva"))
        f.cuota_iva = _num(linea.get("cuota_iva"))
        if i == 0:
            f.base_irpf = _num(datos.get("base_irpf"))
            f.pct_irpf = _num(datos.get("pct_irpf"))
            f.cuota_irpf = _num(datos.get("cuota_irpf"))
        facturas.append(f)

    return FacturaProcesada(tipo=tipo, facturas=facturas, cuenta=cuenta,
                            gxx=gxx, origen=origen, pagina=pagina, aviso=aviso)


def _anadir_aviso(pr: FacturaProcesada, texto: str) -> None:
    pr.aviso = f"{pr.aviso} {texto}".strip() if pr.aviso else texto


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
