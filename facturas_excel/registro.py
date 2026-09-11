"""Lee el LISTADO DE APUNTES que imprime Aplifisa y lo contrasta con el lote.

Es el cuadre a tres bandas que faltaba:

    factura escaneada  ->  Excel generado  ->  lo que de verdad quedo registrado

Los dos primeros pasos ya se comprueban entre si (exportar.verificar_excel).
Este modulo cierra el circulo: se le pasa el PDF del listado de Aplifisa y se
compara apunte a apunte con las facturas del lote. Asi se ven las que no
llegaron a entrar, las que entraron dos veces y las que entraron con otro
importe.

El PDF de Aplifisa lleva capa de texto, asi que se lee tal cual, sin IA y sin
coste. OJO: Aplifisa RENUMERA las facturas recibidas (1, 2, 3...), asi que su
numero no sirve para emparejar; se emparejan por fecha e importes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .validacion import fecha_de

FECHA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
NUMERO = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}-?$|^-?\d+,\d{2}-?$")
TOLERANCIA = 0.02


def _num(texto: str) -> Optional[float]:
    """'1.048,25' -> 1048.25 (y el signo detras, que tambien se usa)."""
    t = str(texto).strip()
    if not NUMERO.match(t):
        return None
    negativo = t.endswith("-")
    t = t.rstrip("-").replace(".", "").replace(",", ".")
    try:
        valor = float(t)
    except ValueError:
        return None
    return -valor if negativo else valor


@dataclass
class Apunte:
    """Una linea del listado de Aplifisa."""
    numero: str = ""          # el numero que le pone Aplifisa, no el del proveedor
    num_factura_proveedor: str = ""
    fecha: str = ""
    concepto: str = ""
    nif: str = ""
    nombre: str = ""
    base: Optional[float] = None
    pct_iva: Optional[float] = None
    cuota: Optional[float] = None
    base_recargo: Optional[float] = None
    pct_recargo: Optional[float] = None
    recargo: Optional[float] = None
    base_irpf: Optional[float] = None
    pct_irpf: Optional[float] = None
    irpf: Optional[float] = None
    neto: Optional[float] = None


@dataclass
class Registro:
    apuntes: List[Apunte] = field(default_factory=list)
    tipo: str = ""
    total_base: Optional[float] = None
    total_cuota: Optional[float] = None
    total_recargo: Optional[float] = None
    total_irpf: Optional[float] = None
    total_neto: Optional[float] = None

    @property
    def suma_base(self) -> float:
        return round(sum(a.base or 0 for a in self.apuntes), 2)

    @property
    def suma_cuota(self) -> float:
        return round(sum(a.cuota or 0 for a in self.apuntes), 2)

    @property
    def suma_recargo(self) -> float:
        return round(sum(a.recargo or 0 for a in self.apuntes), 2)

    @property
    def suma_irpf(self) -> float:
        return round(sum(a.irpf or 0 for a in self.apuntes), 2)

    @property
    def suma_neto(self) -> float:
        return round(sum(
            a.neto if a.neto is not None else
            (a.base or 0) + (a.cuota or 0) + (a.recargo or 0) - (a.irpf or 0)
            for a in self.apuntes), 2)

    @property
    def facturas(self) -> int:
        numeros = {a.numero for a in self.apuntes if a.numero}
        return len(numeros) if numeros else len(self.apuntes)

    @property
    def diferencias_totales(self) -> List[str]:
        comprobaciones = (
            ("base", self.suma_base, self.total_base),
            ("IVA", self.suma_cuota, self.total_cuota),
            ("recargo", self.suma_recargo, self.total_recargo),
            ("IRPF", self.suma_irpf, self.total_irpf),
            ("total", self.suma_neto, self.total_neto),
        )
        return [
            f"{nombre}: las líneas suman {suma:.2f} y el listado imprime {total:.2f}"
            for nombre, suma, total in comprobaciones
            if total is not None and abs(suma - total) > TOLERANCIA
        ]

    @property
    def bien_leido(self) -> bool:
        """El propio listado trae sus totales: si cuadran, se ha leido bien."""
        return not self.diferencias_totales


def leer_registro(ruta_pdf: str) -> Registro:
    """Saca los apuntes del listado de Aplifisa (PDF con texto)."""
    import fitz

    lineas: List[str] = []
    with fitz.open(ruta_pdf) as doc:
        formato = _formato_posicional(doc)
        if formato:
            return _leer_posicional(doc, formato)
        for pagina in doc:
            lineas += [t.strip() for t in pagina.get_text().splitlines()
                       if t.strip()]

    registro = Registro()
    i = 0
    while i < len(lineas):
        if not FECHA.match(lineas[i]):
            # Cada pagina lleva su "TOTAL DE PAGINA / TOTAL ACUMULADO": hay que
            # quedarse con el ACUMULADO DEL FINAL, y seguir leyendo apuntes de
            # las paginas siguientes (antes se paraba en la primera y se dejaba
            # la mitad del listado sin comprobar).
            if lineas[i].startswith("TOTAL ACUMULADO"):
                registro = _leer_totales(registro, lineas[i + 1:i + 9])
            i += 1
            continue
        # El numero de apunte va justo delante de la fecha.
        apunte = Apunte(numero=lineas[i - 1] if i else "", fecha=lineas[i])
        i += 1
        trozos: List[str] = []
        while i < len(lineas) and not FECHA.match(lineas[i]) \
                and not lineas[i].startswith("TOTAL"):
            trozos.append(lineas[i])
            i += 1
        # Lo que sigue: concepto, cuenta, los importes y el nombre entre medias.
        if i < len(lineas) and FECHA.match(lineas[i]) and trozos:
            trozos = trozos[:-1]      # el ultimo es el nº del apunte siguiente
        _rellenar(apunte, trozos)
        if apunte.base is not None:
            registro.apuntes.append(apunte)
    return registro


def _rellenar(apunte: Apunte, trozos: List[str]) -> None:
    numeros = [(_num(t), t) for t in trozos]
    importes = [v for v, _ in numeros if v is not None]
    textos = [t for v, t in numeros if v is None]
    if textos:
        apunte.concepto = textos[0] if textos[0].isdigit() else apunte.concepto
        # El nombre del proveedor es el texto largo, no el codigo de cuenta.
        nombres = [t for t in textos if not t.isdigit()]
        apunte.nombre = max(nombres, key=len) if nombres else ""
    if not importes:
        return
    # El ultimo importe es el neto; los primeros, base y cuota.
    apunte.neto = importes[-1]
    resto = importes[:-1]
    if resto:
        apunte.base = resto[0]
    if len(resto) > 1:
        apunte.cuota = resto[1]
    if len(resto) > 2:
        apunte.recargo = resto[2]
    if len(resto) > 3:
        apunte.irpf = resto[3]


def _leer_totales(registro: Registro, siguientes: List[str]) -> Registro:
    """Tras 'TOTAL ACUMULADO' van, por parejas, el total de pagina y el
    acumulado de cada columna: base, cuota y neto."""
    valores = [v for v in (_num(t) for t in siguientes) if v is not None]
    if len(valores) >= 2:
        registro.total_base = valores[1]
    if len(valores) >= 4:
        registro.total_cuota = valores[3]
    if len(valores) >= 6:
        registro.total_neto = valores[5]
    return registro


# -------------------------------- listados fiscales con columnas de Aplifisa --
# Los listados reales de compras y ventas no se pueden leer concatenando el
# texto: una linea sin IVA trae menos numeros y cada version de Aplifisa cambia
# ligeramente las abreviaturas. Se detectan las columnas por su posicion.

MARGEN_FILA = 1.5
NIF_SUELTO = re.compile(r"^[A-Z0-9][0-9]{7}[A-Z0-9]$")


def _texto_simple(texto: str) -> str:
    texto = "".join(
        c for c in unicodedata.normalize("NFD", str(texto or ""))
        if unicodedata.category(c) != "Mn"
    )
    return texto.upper()


def _formato_posicional(doc) -> str:
    """Devuelve gasto/venta si el PDF trae la tabla fiscal con columnas."""
    if not doc.page_count:
        return ""
    texto = _texto_simple(doc[0].get_text()).lower()
    if ("compras y gastos" in texto or "facturas recibidas" in texto
            or "fra.rec" in texto or "fact.rec" in texto):
        return "gasto"
    if ("ventas e ingresos" in texto or "facturas emitidas" in texto
            or "identificacion del cliente" in texto):
        return "venta"
    return ""


def _filas(pagina) -> list:
    """Las palabras de la pagina agrupadas en lineas, de arriba abajo."""
    palabras = sorted(pagina.get_text("words"), key=lambda p: (p[3], p[0]))
    filas: list = []
    for x0, _, x1, y1, texto, *_ in palabras:
        if filas and abs(filas[-1][0] - y1) <= MARGEN_FILA:
            filas[-1][1].append((x0, x1, texto))
        else:
            filas.append((y1, [(x0, x1, texto)]))
    return filas


def _columnas_posicional(fila, tipo: str) -> Optional[dict]:
    """Posicion de las columnas de una cabecera real de Aplifisa."""
    palabras = sorted(fila, key=lambda p: p[0])
    simples = [_texto_simple(t) for _, _, t in palabras]
    texto = " ".join(simples)
    if "ORDEN" not in texto or "FECHA" not in texto:
        return None

    def x_de(predicado, defecto=None):
        return next((x0 for (x0, _, _), s in zip(palabras, simples)
                     if predicado(s)), defecto)

    col = {
        "tipo": tipo,
        "x_fecha": x_de(lambda s: s == "FECHA"),
        "x_num": x_de(lambda s: "FRA.REC" in s or "FACT.REC" in s
                       or "FACTURA" in s),
        "x_nombre": x_de(lambda s: "DENTIFICACI" in s),
        "x_concepto": x_de(lambda s: s == "CONCEPTO"),
    }
    col["x_proveedor"] = x_de(lambda s: "FRA.PROVEEDOR" in s)
    x_rt = x_de(lambda s: s == "RT")
    if tipo == "gasto" and x_rt is not None:
        col["x_nombre"] = min(col["x_nombre"] or x_rt, x_rt)
    elif col["x_nombre"] is not None:
        col["x_nombre"] -= 6
    if col["x_concepto"] is not None:
        # Los valores aparecen ligeramente a la izquierda del título centrado
        # de la columna (en ventas, por ejemplo, 265 frente a 267).
        col["x_concepto"] -= 6
    if None in (col["x_fecha"], col["x_num"], col["x_nombre"]):
        return None

    bases, cuotas, porcentajes = [], [], []
    total_x = None
    for i, ((x0, _, _), s) in enumerate(zip(palabras, simples)):
        siguiente = simples[i + 1] if i + 1 < len(simples) else ""
        anterior = simples[i - 1] if i else ""
        if s == "BASE":
            if siguiente == "+":
                total_x = x0
            else:
                bases.append(x0)
        elif s == "CUOTA" and anterior != "+":
            cuotas.append(x0)
        elif s == "%":
            porcentajes.append(x0)

    inicios: Dict[str, float] = {}
    if tipo == "gasto":
        for campo, valores, indice in (
            ("base", bases, 0), ("base_recargo", bases, 1),
            ("base_retencion", bases, 2), ("pct_iva", porcentajes, 0),
            ("pct_recargo", porcentajes, 1), ("pct_irpf", porcentajes, 2),
            ("cuota", cuotas, 0), ("recargo", cuotas, 1),
            ("irpf", cuotas, 2),
        ):
            if len(valores) > indice:
                inicios[campo] = valores[indice]
        imputable = x_de(lambda s: s.startswith("IMPUTABLE"))
        if imputable is not None:
            inicios["base_irpf"] = imputable
    else:
        if bases:
            inicios["base"] = bases[0]
        if len(bases) > 1:
            inicios["base_irpf"] = bases[1]
        if cuotas:
            inicios["cuota"] = cuotas[0]
        reten = x_de(lambda s: s.startswith("RETEN"))
        if reten is not None:
            inicios["irpf"] = reten
        suma = x_de(lambda s: s == "SUMA")
        if suma is not None:
            inicios["total"] = suma
    if total_x is not None:
        inicios["total"] = total_x
    if "base" not in inicios:
        return None

    if col["x_concepto"] is None:
        col["x_concepto"] = min(inicios.values()) - 8

    orden = sorted(inicios.items(), key=lambda par: par[1])
    centros = {}
    ultimo_fin = max(x1 for _, x1, _ in palabras)
    for i, (campo, inicio) in enumerate(orden):
        siguiente = orden[i + 1][1] if i + 1 < len(orden) else ultimo_fin
        centros[campo] = (inicio + siguiente) / 2
    col["importes"] = centros
    col["x_importes"] = min(inicios.values()) - 8
    return col


def _columna_de(x0: float, x1: float, centros: dict) -> str:
    centro = (x0 + x1) / 2
    return min(centros, key=lambda c: abs(centros[c] - centro))


def _apunte_de_fila(fila, col) -> Optional[Apunte]:
    centros = col["importes"]
    fecha = next((t for _, _, t in fila if FECHA.match(t)), "")
    if not fecha:
        return None

    orden, numero, numero_proveedor = "", "", ""
    identidad, concepto, valores = [], [], {}
    for x0, x1, t in fila:
        if x0 < col["x_fecha"] and str(t).isdigit():
            orden = t
        elif col["x_num"] <= x0 < (col.get("x_proveedor")
                                     or col["x_nombre"]):
            numero += (" " if numero else "") + t
        elif (col.get("x_proveedor") is not None
              and col["x_proveedor"] <= x0 < col["x_nombre"]):
            numero_proveedor += (" " if numero_proveedor else "") + t
        elif col["x_nombre"] <= x0 < col["x_concepto"]:
            identidad.append(t)
        elif col["x_concepto"] <= x0 < col["x_importes"]:
            concepto.append(t)
        elif x0 >= col["x_importes"]:
            valor = _num(t)
            if valor is not None:
                valores[_columna_de(x0, x1, centros)] = valor
    if "base" not in valores:
        return None
    nif = identidad.pop(0) if identidad and NIF_SUELTO.match(
        _texto_simple(identidad[0])) else ""
    neto = valores.get("total")
    if neto is None:
        neto = round(
            (valores.get("base") or 0) + (valores.get("cuota") or 0)
            + (valores.get("recargo") or 0) - (valores.get("irpf") or 0), 2)
    return Apunte(
        numero=numero.strip() or orden,
        num_factura_proveedor=numero_proveedor.strip(), fecha=fecha,
        concepto=" ".join(concepto), nif=nif, nombre=" ".join(identidad),
        base=valores.get("base"), pct_iva=valores.get("pct_iva"),
        cuota=valores.get("cuota"), base_recargo=valores.get("base_recargo"),
        pct_recargo=valores.get("pct_recargo"), recargo=valores.get("recargo"),
        base_irpf=valores.get("base_irpf") or valores.get("base_retencion"),
        pct_irpf=valores.get("pct_irpf"), irpf=valores.get("irpf"), neto=neto,
    )


def _leer_posicional(doc, tipo: str) -> Registro:
    registro = Registro(tipo=tipo)
    for pagina in doc:
        col = None
        filas = _filas(pagina)
        for i, (_, fila) in enumerate(filas):
            cabecera = _columnas_posicional(fila, tipo)
            if cabecera:
                col = cabecera
                continue
            if col is None:
                continue
            if any("ACUMULADO" in _texto_simple(t) for _, _, t in fila):
                origen = fila if any(_num(t) is not None for _, _, t in fila) \
                    else filas[max(i - 1, 0)][1]
                registro = _totales_posicionales(registro, origen, col)
                continue
            apunte = _apunte_de_fila(fila, col)
            if apunte:
                registro.apuntes.append(apunte)
    if tipo == "venta":
        # En el listado de ventas la columna «Suma» es base + IVA; la
        # retención aparece aparte. Para compararla con el total de la factura
        # hay que obtener el líquido después de IRPF.
        for apunte in registro.apuntes:
            if apunte.neto is not None:
                apunte.neto = round(apunte.neto - (apunte.irpf or 0), 2)
        if registro.total_neto is not None:
            registro.total_neto = round(
                registro.total_neto - (registro.total_irpf or 0), 2)
    return registro


def _totales_posicionales(registro: Registro, fila, col) -> Registro:
    centros = col["importes"]
    for x0, x1, t in fila:
        valor = _num(t)
        if valor is None:
            continue
        campo = _columna_de(x0, x1, centros)
        if campo == "base":
            registro.total_base = valor
        elif campo == "cuota":
            registro.total_cuota = valor
        elif campo == "recargo":
            registro.total_recargo = valor
        elif campo == "irpf":
            registro.total_irpf = valor
        elif campo == "total":
            registro.total_neto = valor
    return registro

# ----------------------------------------------------------------- contraste
@dataclass
class Informe:
    """Que dice el listado de Aplifisa frente a lo que hay en el programa."""
    emparejadas: int = 0
    sin_registrar: List[str] = field(default_factory=list)   # estan aqui, no alli
    de_mas: List[str] = field(default_factory=list)          # estan alli, no aqui
    distintas: List[str] = field(default_factory=list)       # emparejadas pero cambia algo
    dudosas: List[str] = field(default_factory=list)
    apuntes_de_mas: List[Apunte] = field(default_factory=list)
    resultados: Dict[int, str] = field(default_factory=dict)
    detalles: Dict[int, List[str]] = field(default_factory=dict)
    base_programa: float = 0.0
    base_registro: float = 0.0
    cuota_programa: float = 0.0
    cuota_registro: float = 0.0
    recargo_programa: float = 0.0
    recargo_registro: float = 0.0
    irpf_programa: float = 0.0
    irpf_registro: float = 0.0
    total_programa: float = 0.0
    total_registro: float = 0.0
    facturas_programa: int = 0
    facturas_registro: int = 0
    lineas_programa: int = 0
    lineas_registro: int = 0

    @property
    def todo_cuadra(self) -> bool:
        return (
            not (self.sin_registrar or self.de_mas or self.distintas
                 or self.dudosas)
            and all(abs(diferencia) <= TOLERANCIA for diferencia in (
                self.descuadre_base, self.descuadre_cuota,
                self.descuadre_recargo, self.descuadre_irpf,
                self.descuadre_total,
            ))
            and self.facturas_programa == self.facturas_registro
            and self.lineas_programa == self.lineas_registro
        )

    @property
    def descuadre_base(self) -> float:
        return round(self.base_programa - self.base_registro, 2)

    @property
    def descuadre_cuota(self) -> float:
        return round(self.cuota_programa - self.cuota_registro, 2)

    @property
    def descuadre_recargo(self) -> float:
        return round(self.recargo_programa - self.recargo_registro, 2)

    @property
    def descuadre_irpf(self) -> float:
        return round(self.irpf_programa - self.irpf_registro, 2)

    @property
    def descuadre_total(self) -> float:
        return round(self.total_programa - self.total_registro, 2)


def _clave(fecha, base, cuota) -> tuple:
    return (str(fecha or "").strip(),
            round(float(base or 0), 2), round(float(cuota or 0), 2))


def _describir(fecha, nombre, base, cuota) -> str:
    return (f"{fecha or 'sin fecha'} · {(nombre or '?')[:34]} · "
            f"base {base or 0:.2f} · IVA {cuota or 0:.2f}").replace(".", ",")


def _normalizar_id(valor) -> str:
    return "".join(c for c in _texto_simple(valor) if c.isalnum())


def _cerca(a, b) -> bool:
    return abs(float(a or 0) - float(b or 0)) <= TOLERANCIA


def _misma_fecha(a, b) -> bool:
    fecha_a, fecha_b = fecha_de(a), fecha_de(b)
    if fecha_a and fecha_b:
        return fecha_a == fecha_b
    return str(a or "").strip() == str(b or "").strip()


def _total_factura(f) -> float:
    if getattr(f, "es_suplido", False):
        return float(f.base_iva or 0)
    return float(
        (f.base_iva or 0) + (f.cuota_iva or 0) + (f.cuota_requiv or 0)
        + (f.suplidos or 0) - (f.cuota_irpf or 0)
    )


def _puntuacion(f, a: Apunte) -> int:
    """Fuerza de la coincidencia sin exigir que los importes ya cuadren."""
    puntos = 0
    numero_f = _normalizar_id(getattr(f, "num_factura", ""))
    numero_a = _normalizar_id(a.num_factura_proveedor)
    if numero_f and numero_a:
        puntos += 8 if numero_f == numero_a else -4
    nif_f, nif_a = _normalizar_id(getattr(f, "nif", "")), _normalizar_id(a.nif)
    if nif_f and nif_a:
        puntos += 5 if nif_f == nif_a else -5
    if _misma_fecha(getattr(f, "fecha", ""), a.fecha):
        puntos += 4
    else:
        puntos -= 4
    if _cerca(getattr(f, "base_iva", None), a.base):
        puntos += 3
    if _cerca(getattr(f, "cuota_iva", None), a.cuota):
        puntos += 2
    return puntos


def _diferencias(f, a: Apunte) -> List[str]:
    diferencias = []

    def importe(etiqueta, valor_programa, valor_aplifisa):
        if valor_aplifisa is not None and not _cerca(valor_programa, valor_aplifisa):
            diferencias.append(
                f"{etiqueta}: programa {float(valor_programa or 0):.2f}; "
                f"Aplifisa {float(valor_aplifisa):.2f}".replace(".", ","))

    importe("Base", getattr(f, "base_iva", None), a.base)
    importe("IVA", getattr(f, "cuota_iva", None), a.cuota)
    importe("Recargo", getattr(f, "cuota_requiv", None), a.recargo)
    importe("IRPF", getattr(f, "cuota_irpf", None), a.irpf)
    if a.neto is not None and int(getattr(f, "lineas_factura", 1) or 1) <= 1:
        importe("Total", getattr(f, "total_impreso", None) or _total_factura(f),
                a.neto)
    if not _misma_fecha(getattr(f, "fecha", ""), a.fecha):
        diferencias.append(
            f"Fecha: programa {getattr(f, 'fecha', '')}; Aplifisa {a.fecha}")
    numero_f = _normalizar_id(getattr(f, "num_factura", ""))
    numero_a = _normalizar_id(a.num_factura_proveedor)
    if numero_f and numero_a and numero_f != numero_a:
        diferencias.append(
            f"Nº factura: programa {getattr(f, 'num_factura', '')}; "
            f"Aplifisa {a.num_factura_proveedor}")
    nif_f, nif_a = _normalizar_id(getattr(f, "nif", "")), _normalizar_id(a.nif)
    if nif_f and nif_a and nif_f != nif_a:
        diferencias.append(f"NIF: programa {getattr(f, 'nif', '')}; Aplifisa {a.nif}")
    return diferencias


def _facturas_unicas(facturas) -> int:
    claves = set()
    for indice, f in enumerate(facturas):
        documento = str(getattr(f, "documento_id", "") or "")
        if documento:
            clave = ("documento", documento)
        elif int(getattr(f, "lineas_factura", 1) or 1) > 1:
            clave = (
                "compuesta", str(getattr(f, "origen_imagen", "") or ""),
                _normalizar_id(getattr(f, "num_factura", "")),
                _normalizar_id(getattr(f, "nif", "")),
                str(getattr(f, "fecha", "") or ""),
            )
        else:
            clave = ("linea", indice)
        claves.add(clave)
    return len(claves)


def contrastar(facturas, registro: Registro) -> Informe:
    """Empareja las facturas del programa con los apuntes del listado.

    Prioriza el número del proveedor y el NIF cuando están disponibles. Como
    Aplifisa también asigna su propia numeración, fecha e importes permiten
    emparejar los listados que no muestran el número original.
    """
    facturas = list(facturas)
    informe = Informe()
    pendientes = list(enumerate(registro.apuntes))

    for indice, f in enumerate(facturas):
        candidatos = [(pos, original, a, _puntuacion(f, a))
                      for pos, (original, a) in enumerate(pendientes)]
        candidatos = [c for c in candidatos if c[3] >= 7 or (
            _misma_fecha(c[2].fecha, getattr(f, "fecha", ""))
            and _cerca(c[2].base, getattr(f, "base_iva", None)))]
        if not candidatos:
            texto = _describir(f.fecha, f.nombre, f.base_iva, f.cuota_iva)
            informe.sin_registrar.append(texto)
            informe.resultados[indice] = "sin_registrar"
            informe.detalles[indice] = ["No aparece una línea equivalente en Aplifisa."]
            continue
        candidatos.sort(key=lambda c: c[3], reverse=True)
        mejor = candidatos[0]
        empatados = [c for c in candidatos if c[3] == mejor[3]]
        _, _, apunte, _ = mejor
        pendientes.pop(mejor[0])
        diferencias = _diferencias(f, apunte)
        if len(empatados) > 1 and diferencias:
            texto = _describir(f.fecha, f.nombre, f.base_iva, f.cuota_iva)
            informe.dudosas.append(texto)
            informe.resultados[indice] = "dudosa"
            informe.detalles[indice] = [
                "Hay varias líneas posibles en Aplifisa; revise el emparejamiento.",
                *diferencias,
            ]
        elif diferencias:
            texto = (_describir(f.fecha, f.nombre, f.base_iva, f.cuota_iva)
                     + " → " + "; ".join(diferencias))
            informe.distintas.append(texto)
            informe.resultados[indice] = "distinta"
            informe.detalles[indice] = diferencias
        else:
            informe.emparejadas += 1
            informe.resultados[indice] = "cuadra"
            informe.detalles[indice] = ["Coincide con Aplifisa."]

    for _, a in pendientes:
        informe.de_mas.append(_describir(a.fecha, a.nombre, a.base, a.cuota))
        informe.apuntes_de_mas.append(a)

    informe.base_programa = round(sum(f.base_iva or 0 for f in facturas), 2)
    informe.cuota_programa = round(sum(f.cuota_iva or 0 for f in facturas), 2)
    informe.recargo_programa = round(sum(f.cuota_requiv or 0 for f in facturas), 2)
    informe.irpf_programa = round(sum(f.cuota_irpf or 0 for f in facturas), 2)
    informe.total_programa = round(sum(_total_factura(f) for f in facturas), 2)
    informe.base_registro = registro.suma_base
    informe.cuota_registro = registro.suma_cuota
    informe.recargo_registro = registro.suma_recargo
    informe.irpf_registro = registro.suma_irpf
    informe.total_registro = registro.suma_neto
    informe.facturas_programa = _facturas_unicas(facturas)
    informe.facturas_registro = registro.facturas
    informe.lineas_programa = len(facturas)
    informe.lineas_registro = len(registro.apuntes)
    return informe


SEÑALES_LISTADO = ("LISTADO DE APUNTES", "TOTAL ACUMULADO", "FACT.REC",
                   "GESTION FISCAL", "GESTIÓN FISCAL")


def parece_listado(ruta_pdf: str) -> bool:
    """¿Es el listado de Aplifisa y no un taco de facturas?

    Importa: si se cuela como facturas, se manda a Gemini y se paga por leer
    un papel que aqui se lee gratis (y ademas saldria una fila por pagina con
    datos sin sentido).
    """
    try:
        import fitz
        with fitz.open(ruta_pdf) as doc:
            if not doc.page_count:
                return False
            texto = doc[0].get_text().upper()
    except Exception:
        return False
    return any(s in texto for s in SEÑALES_LISTADO)
