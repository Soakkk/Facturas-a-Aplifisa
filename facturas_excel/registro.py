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
from dataclasses import dataclass, field
from typing import List, Optional

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
    fecha: str = ""
    concepto: str = ""
    nombre: str = ""
    base: Optional[float] = None
    cuota: Optional[float] = None
    recargo: Optional[float] = None
    irpf: Optional[float] = None
    neto: Optional[float] = None


@dataclass
class Registro:
    apuntes: List[Apunte] = field(default_factory=list)
    total_base: Optional[float] = None
    total_cuota: Optional[float] = None
    total_neto: Optional[float] = None

    @property
    def suma_base(self) -> float:
        return round(sum(a.base or 0 for a in self.apuntes), 2)

    @property
    def suma_cuota(self) -> float:
        return round(sum(a.cuota or 0 for a in self.apuntes), 2)

    @property
    def bien_leido(self) -> bool:
        """El propio listado trae sus totales: si cuadran, se ha leido bien."""
        if self.total_base is None:
            return True          # sin totales que comparar, no se puede decir
        return abs(self.suma_base - self.total_base) <= TOLERANCIA


def leer_registro(ruta_pdf: str) -> Registro:
    """Saca los apuntes del listado de Aplifisa (PDF con texto)."""
    import fitz

    lineas: List[str] = []
    with fitz.open(ruta_pdf) as doc:
        if _es_facturas_recibidas(doc):
            return _leer_facturas_recibidas(doc)
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


# --------------------------------------- listado "IVA - Facturas recibidas" --
# Es el que se saca para un requerimiento: una linea por tipo de IVA, ordenada
# por nº de apunte, y con el Nº fact.rec. que Aplifisa da a cada factura.
# Aqui no vale leer el texto seguido: las columnas se solapan y una linea sin
# IVA (un suplido) trae menos importes que las demas, asi que se lee por la
# POSICION de cada palabra, que es lo unico fiable en este listado.

CABECERAS = {
    "BASEIVA": "base",
    "CUOTAIVA": "cuota",
    "BASER.EQ.": "base_req",
    "CUOTAR.EQ.": "cuota_req",
    "BASE+CUOTA": "total",
}
MARGEN_FILA = 1.5        # puntos: dos palabras de la misma linea
HUECO_COLUMNA = 6        # puntos: separacion entre columnas de la cabecera
NIF_SUELTO = re.compile(r"^[A-Z0-9][0-9]{7}[A-Z0-9]$")


def _es_facturas_recibidas(doc) -> bool:
    """El listado de facturas recibidas trae columnas propias en la cabecera."""
    if not doc.page_count:
        return False
    texto = doc[0].get_text()
    return "fact.rec" in texto and "fra.proveedor" in texto


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


def _columnas(fila) -> Optional[dict]:
    """Saca de la cabecera donde cae cada columna. None si no es la cabecera."""
    texto = " ".join(t for _, _, t in fila)
    if "fact.rec" not in texto or "Orden" not in texto:
        return None

    col = {}
    for x0, _, t in fila:
        if "fact.rec" in t:
            col["x_num"] = x0
        elif "fra.proveedor" in t:
            col["x_proveedor"] = x0
        elif "dentificaci" in t and "x_nombre" not in col:
            col["x_nombre"] = x0

    # Las columnas de importes: se agrupan las palabras de la cabecera y se
    # guarda el centro de cada una, para asignar despues cada numero a la suya.
    grupos: list = []
    for x0, x1, t in fila:
        if grupos and x0 - grupos[-1][-1][1] <= HUECO_COLUMNA:
            grupos[-1].append((x0, x1, t))
        else:
            grupos.append([(x0, x1, t)])
    centros, porcentajes = {}, 0
    for grupo in grupos:
        etiqueta = "".join(t for _, _, t in grupo).upper()
        if etiqueta == "%":
            campo = "pct" if not porcentajes else "pct_req"
            porcentajes += 1
        else:
            campo = CABECERAS.get(etiqueta)
        if campo:
            centros[campo] = (grupo[0][0] + grupo[-1][1]) / 2
    if "base" not in centros or "x_nombre" not in col:
        return None
    col["importes"] = centros
    return col


def _columna_de(x0: float, x1: float, centros: dict) -> str:
    """A que columna de importes pertenece un numero: a la de centro mas cerca."""
    centro = (x0 + x1) / 2
    return min(centros, key=lambda c: abs(centros[c] - centro))


def _apunte_de_fila(fila, col) -> Optional[Apunte]:
    centros = col["importes"]
    tope = max(centros.values()) + 30       # a la derecha van los cobros RECC
    fecha = next((t for x0, _, t in fila
                  if col["x_num"] > x0 and FECHA.match(t)), "")
    if not fecha:
        return None

    numero, nombre = "", []
    valores = {}
    for x0, x1, t in fila:
        if x0 >= tope:
            continue
        if col["x_num"] <= x0 < col["x_proveedor"]:
            numero = t
        elif col["x_nombre"] <= x0 < centros["base"] - 20:
            nombre.append(t)
        elif x0 >= col["x_nombre"]:
            valor = _num(t)
            if valor is not None:
                valores[_columna_de(x0, x1, centros)] = valor
    if "base" not in valores:
        return None
    if nombre and NIF_SUELTO.match(nombre[0].upper()):
        nombre = nombre[1:]                 # el NIF va delante del nombre
    return Apunte(numero=numero, fecha=fecha, nombre=" ".join(nombre),
                  base=valores.get("base"), cuota=valores.get("cuota"),
                  recargo=valores.get("cuota_req"), neto=valores.get("total"))


def _leer_facturas_recibidas(doc) -> Registro:
    registro = Registro()
    for pagina in doc:
        col = None
        filas = _filas(pagina)
        for i, (y, fila) in enumerate(filas):
            cabecera = _columnas(fila)
            if cabecera:
                col = cabecera
                continue
            if col is None:
                continue
            if any("ACUMULADO" in t.upper() for _, _, t in fila):
                # Los importes del acumulado van en su propia linea, justo
                # encima de la etiqueta.
                registro = _totales_recibidas(registro, filas[max(i - 1, 0)][1],
                                              col)
                continue
            apunte = _apunte_de_fila(fila, col)
            if apunte:
                registro.apuntes.append(apunte)
    return registro


def _totales_recibidas(registro: Registro, fila, col) -> Registro:
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
    base_programa: float = 0.0
    base_registro: float = 0.0
    cuota_programa: float = 0.0
    cuota_registro: float = 0.0

    @property
    def todo_cuadra(self) -> bool:
        return not (self.sin_registrar or self.de_mas or self.distintas)

    @property
    def descuadre_base(self) -> float:
        return round(self.base_programa - self.base_registro, 2)


def _clave(fecha, base, cuota) -> tuple:
    return (str(fecha or "").strip(),
            round(float(base or 0), 2), round(float(cuota or 0), 2))


def _describir(fecha, nombre, base, cuota) -> str:
    return (f"{fecha or 'sin fecha'} · {(nombre or '?')[:34]} · "
            f"base {base or 0:.2f} · IVA {cuota or 0:.2f}").replace(".", ",")


def contrastar(facturas, registro: Registro) -> Informe:
    """Empareja las facturas del programa con los apuntes del listado.

    Se empareja por FECHA + BASE + CUOTA, no por numero: Aplifisa renumera las
    facturas recibidas al importarlas, asi que su numero no coincide con el del
    proveedor. Los importes con la fecha son suficientemente unicos, y ademas
    son justo lo que interesa que cuadre.
    """
    informe = Informe()
    pendientes = {}
    for a in registro.apuntes:
        pendientes.setdefault(_clave(a.fecha, a.base, a.cuota), []).append(a)

    for f in facturas:
        informe.base_programa += f.base_iva or 0
        informe.cuota_programa += f.cuota_iva or 0
        clave = _clave(f.fecha, f.base_iva, f.cuota_iva)
        iguales = pendientes.get(clave)
        if iguales:
            iguales.pop()
            informe.emparejadas += 1
            continue
        # Misma fecha e importe pero con la cuota cambiada: se busca aparte
        # para poder decir QUE cambia, en vez de darla por no registrada.
        parecida = next(
            (a for lista in pendientes.values() for a in lista
             if a.fecha == f.fecha
             and abs((a.base or 0) - (f.base_iva or 0)) <= TOLERANCIA), None)
        if parecida:
            pendientes[_clave(parecida.fecha, parecida.base,
                              parecida.cuota)].remove(parecida)
            informe.distintas.append(
                f"{_describir(f.fecha, f.nombre, f.base_iva, f.cuota_iva)}  →  "
                f"en Aplifisa: IVA {parecida.cuota or 0:.2f}".replace(".", ","))
        else:
            informe.sin_registrar.append(
                _describir(f.fecha, f.nombre, f.base_iva, f.cuota_iva))

    for lista in pendientes.values():
        for a in lista:
            informe.de_mas.append(_describir(a.fecha, a.nombre, a.base, a.cuota))

    informe.base_programa = round(informe.base_programa, 2)
    informe.cuota_programa = round(informe.cuota_programa, 2)
    informe.base_registro = registro.suma_base
    informe.cuota_registro = registro.suma_cuota
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
