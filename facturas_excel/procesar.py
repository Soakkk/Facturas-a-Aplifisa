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
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Dict, List, Tuple
from uuid import uuid4

from . import clientes, proveedores
from .conceptos import (
    DEFAULT_VENTA, asignar_concepto, es_valido, normalizar_concepto,
    subclave_628, subclaves_de,
)
from .extraccion import _num
from .modelo import Factura
from .validacion import validar_nif, fecha_de


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
    for d in lista_datos:
        for campo_nif, campo_nom, papel in (
                ("emisor_nif", "emisor_nombre", "e"),
                ("receptor_nif", "receptor_nombre", "r")):
            conocido = clientes.buscar_confirmado_por_nombre(d.get(campo_nom, ""))
            nif = conocido[0] if conocido else normaliza_nif(d.get(campo_nif))
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
            elif d.get(campo_nom):
                nombres[nif].append(d[campo_nom])

    for nif, c in cuenta.items():
        lista = nombres.get(nif, [])
        c.nombre = Counter(lista).most_common(1)[0][0] if lista else ""
        c.cliente_confirmado = clientes.es_cliente_confirmado(nif)
        c.proveedor_conocido = _es_proveedor_conocido(nif, c.nombre)

    # Con empate se propone al que RECIBE las facturas: un taco de facturas
    # iguales suele ser de compras (gasolinera, proveedor de la tienda...). Es
    # solo la propuesta del dialogo; decide la persona, y se recuerda.
    orden = sorted(cuenta.values(),
                   key=lambda c: (-c.puntos, -c.como_receptor, c.nif))
    dudoso = len(orden) > 1 and orden[0].puntos == orden[1].puntos
    return Analisis(candidatos=orden, dudoso=dudoso)


def _es_proveedor_conocido(nif: str, nombre: str) -> bool:
    """Si ya se le ha comprado alguna vez, no es el cliente de la asesoria."""
    ficha = proveedores.leer(clave_proveedor(nombre)) if nombre else None
    if ficha and normaliza_nif(ficha.get("nif")) == nif:
        return True
    return any(normaliza_nif(f.get("nif")) == nif
               for f in proveedores.leer_todo().values() if isinstance(f, dict))


def detectar_cliente(lista_datos: List[dict]) -> Tuple[str, str]:
    """(nombre, nif) del cliente del lote. Compatible con lo de siempre."""
    mejor = analizar_cliente(lista_datos).mejor
    return (mejor.nombre, mejor.nif) if mejor else ("", "")


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
    cuenta, gxx = normalizar_concepto(
        datos.get("cuenta_gasto"), datos.get("subclave_gxx"))
    texto = f"{datos.get('concepto_texto', '')} {datos.get('emisor_nombre', '')}"
    if not cuenta:
        cuenta = asignar_concepto("gasto", texto)
    if not gxx and cuenta == "628":
        gxx = subclave_628(texto)
    if not gxx and cuenta:
        posibles = subclaves_de(cuenta)
        if len(posibles) == 1:
            gxx = posibles[0][0]
    return cuenta, gxx


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

    # Un nombre coincidente no confirma un NIF explícito de otra persona.
    for rol, nom, leido in (("emisor", e_nom, e_nif),
                            ("destinatario", r_nom, r_nif)):
        if (_mismo_nombre(nom, cliente_nombre) and leido != cliente_nif
                and validar_nif(leido)):
            aviso = f"{aviso} El nombre del cliente coincide con el {rol}, " \
                    f"pero su NIF {leido} es distinto del cliente seleccionado " \
                    f"({cliente_nif}). Confirma cliente y rol antes de importar.".strip()
    if datos.get("_union_inferida"):
        paginas = ", ".join(str(p) for p in datos.get("_paginas_union_inferida", []))
        aviso = f"{aviso} Unión inferida de páginas {paginas}: " \
                f"{datos.get('_motivo_union_inferida', 'continuidad de hojas')}. " \
                "Comprueba que pertenecen a la misma factura.".strip()

    # Cuenta contable
    if tipo == "venta":
        # Los ingresos tienen su propia lista en Aplifisa (700 ventas, 705
        # servicios, 740/741 subvenciones...). Si Gemini propone una de ellas
        # se respeta; si no, la de siempre.
        cuenta, gxx = normalizar_concepto(
            datos.get("cuenta_ingreso"), datos.get("subclave_ingreso"))
        if not es_valido(cuenta, gxx):
            cuenta, gxx = DEFAULT_VENTA, None
    else:
        cuenta, gxx = concepto_gasto(datos)

    # Construir Factura (una por linea de IVA)
    lineas = datos.get("lineas_iva") or [{}]
    comun = dict(
        documento_id=uuid4().hex,
        num_factura=datos.get("num_factura") or None,
        fecha=datos.get("fecha") or None,
        fecha_operacion=datos.get("fecha_operacion") or None,
        nombre=nombre or None,
        # El NIF, siempre limpio: el mismo proveedor viene unas veces
        # "A-82018474" y otras "A82018474", y con el guion se contaba como otro
        # distinto (ni se detectaba el duplicado ni valia la memoria de NIF).
        nif=normaliza_nif(nif) or None,
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
    )
    facturas = []
    for i, linea in enumerate(lineas):
        f = Factura(**comun)
        f.lineas_factura = len(lineas)
        f.base_iva = _num(linea.get("base"))
        f.pct_iva = _num(linea.get("tipo_iva"))
        f.cuota_iva = _num(linea.get("cuota_iva"))
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
                            sustituye_a=str(datos.get("sustituye_a") or "").strip())


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


def recordar_nif(nombre, nif, manual: bool = False) -> bool:
    """Guarda el NIF de un proveedor para los proximos lotes (y otros clientes).
    Solo se recuerdan NIF que pasan el digito de control."""
    nif = normaliza_nif(nif)
    clave = clave_proveedor(nombre)
    if not clave or not validar_nif(nif):
        return False
    return proveedores.guardar(clave, nif, str(nombre or "").strip(), manual)


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


def completar_desde_memoria(procesadas: List[FacturaProcesada]) -> int:
    """Rellena los NIF que faltan o no valen con los ya sabidos de otras veces.

    Se usa DESPUES de propagar_nifs: dentro del mismo lote la prueba es mejor.
    Un NIF confirmado manualmente sí prevalece incluso si el OCR devuelve otro
    que, por casualidad, pasa el dígito de control. Los aprendidos solo por una
    lectura automática mantienen la cautela anterior.
    """
    completados = 0
    for pr in procesadas:
        if not pr.facturas:
            continue
        f = pr.facturas[0]
        ficha = proveedores.leer(clave_proveedor(f.nombre))
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
        # Lo confirmado por una persona ya está comprobado y no debe obligar a
        # revisar las mismas facturas en cada lote. La memoria automática sí
        # permanece amarilla hasta que alguien la confirme.
        if not ficha.get("manual"):
            _anadir_aviso(pr, f"NIF puesto de memoria ({ficha['nif']}): es el que "
                              f"consta guardado para {f.nombre} y {motivo}. Compruébalo.")
        completados += 1
    return completados


def a_total_factura(pr: FacturaProcesada) -> FacturaProcesada:
    """Deja un unico apunte por el TOTAL (base + IVA + recargo + suplidos).

    Para clientes en recargo de equivalencia: no deducen IVA, asi que el gasto es
    el importe integro y en Aplifisa se registra como total factura, sin desglose.

    Si la factura lleva retencion NO se toca: el IRPF hay que declararlo aparte
    (modelo 111) y colapsarlo lo perderia. Se avisa para hacerla a mano.
    """
    if pr.tipo != "gasto" or not pr.facturas:
        return pr
    if any(f.cuota_irpf for f in pr.facturas):
        copia = replace(pr, facturas=[replace(f) for f in pr.facturas])
        _anadir_aviso(copia, "Lleva retención de IRPF: NO se ha pasado a total "
                             "factura (la retención hay que declararla). Revísala.")
        return copia

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
    consolidados = consolidar_paginas_factura(registros)
    procesadas = [(img, construir(datos, cliente_nif, cliente_nombre, origen, pag))
                  for img, origen, pag, datos in consolidados]
    solo = [pr for _, pr in procesadas]
    propagar_nifs(solo)              # 1º la prueba del propio lote
    completar_desde_memoria(solo)    # 2º lo sabido de otras veces
    aprender_nifs(solo)              # 3º memorizar lo leido bien
    unificar_nombres(solo)           # 4º el mismo proveedor, escrito igual
    aplicar_recordado(solo)          # 5º lo que ya corrigio el usuario a mano
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


def _fusionar_datos_paginas(primera: dict, siguiente: dict) -> dict:
    fusion = deepcopy(primera)

    # La cabecera buena suele estar en la primera hoja. Completar huecos con
    # las siguientes sin permitir que una lectura parcial la borre.
    for campo, valor in siguiente.items():
        if campo in ("lineas_iva", *_CAMPOS_FISCALES, *_CAMPOS_BOOLEANOS,
                     "confianza"):
            continue
        if fusion.get(campo) in (None, "", []):
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



def unificar_nombres(procesadas: List[FacturaProcesada]) -> int:
    """El mismo proveedor, escrito siempre igual.

    Una vez llega "TELEFONICA DE ESPAÑA, S.A.U." y otra "Telefónica de España,
    S.A.U.". Es el mismo, pero Aplifisa busca la cuenta por NIF y luego por
    NOMBRE EXACTO, asi que dos formas de escribirlo pueden acabar en dos
    cuentas. Se usa el nombre que ya esta guardado para ese NIF.
    """
    por_nif = {}
    for ficha in proveedores.leer_todo().values():
        if not isinstance(ficha, dict):
            continue
        nif = normaliza_nif(ficha.get("nif"))
        if not nif or not ficha.get("nombre"):
            continue
        # El corregido a mano manda: se ponga antes o despues en el fichero.
        if ficha.get("nombre_manual") or nif not in por_nif:
            por_nif[nif] = ficha["nombre"]

    cambiados = 0
    for pr in procesadas:
        for f in pr.facturas:
            bueno = por_nif.get(normaliza_nif(f.nif))
            if bueno and f.nombre and f.nombre != bueno:
                f.nombre = bueno
                cambiados += 1
    return cambiados


def recordar_nombre_proveedor(nif, nombre) -> bool:
    """El nombre con el que el usuario quiere ver a este proveedor.

    Aplifisa busca la cuenta por NIF y luego por nombre EXACTO, asi que como se
    escriba importa. Si lo corrige a mano, se queda corregido para siempre.
    """
    nif, nombre = normaliza_nif(nif), str(nombre or "").strip()
    if not nombre:
        return False
    ficha = proveedores.buscar_por_nif(nif) if nif else None
    clave = clave_proveedor(ficha["nombre"]) if ficha and ficha.get("nombre") \
        else clave_proveedor(nombre)
    return proveedores.guardar_campos(clave, nif=nif or None, nombre=nombre,
                                      nombre_manual=True)


def recordar_cuenta_proveedor(nif, nombre, cuenta, gxx=None) -> bool:
    """La cuenta contable que el usuario le pone a este proveedor.

    Es lo mismo que hace Aplifisa: la primera vez se dice, y las siguientes
    facturas de ese proveedor entran ya con su concepto.
    """
    cuenta = str(cuenta or "").strip()
    if not cuenta or not es_valido(cuenta, gxx):
        return False
    nif = normaliza_nif(nif)
    ficha = proveedores.buscar_por_nif(nif) if nif else None
    clave = clave_proveedor(ficha["nombre"]) if ficha and ficha.get("nombre") \
        else clave_proveedor(nombre)
    return proveedores.guardar_campos(clave, nif=nif or None,
                                      nombre=str(nombre or "").strip() or None,
                                      cuenta=cuenta, gxx=(gxx or None),
                                      cuenta_manual=True)


def aplicar_recordado(procesadas: List[FacturaProcesada]) -> int:
    """Pone en el lote lo que el usuario ya corrigio de esos proveedores."""
    puestos = 0
    for pr in procesadas:
        if pr.tipo != "gasto" or not pr.facturas:
            continue
        ficha = proveedores.buscar_por_nif(normaliza_nif(pr.facturas[0].nif))
        if not ficha or not ficha.get("cuenta_manual"):
            continue
        cuenta, gxx = ficha.get("cuenta"), ficha.get("gxx")
        if not es_valido(cuenta, gxx):
            continue
        pr.cuenta, pr.gxx = cuenta, gxx
        for f in pr.facturas:
            f.concepto, f.subclave = cuenta, gxx
        puestos += 1
    return puestos
