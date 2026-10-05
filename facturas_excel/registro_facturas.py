"""El registro de facturas: una ficha por factura, con todo su recorrido.

Antes cada factura aparecía en tres sitios que no se conocían: el historial
de exportadas, las carpetas del archivo y los expedientes. Ahora cada factura
que sale del programa tiene UNA ficha en la base de datos local (almacen.py):

    leída → revisada → exportada → archivada

con la fecha de cada paso, el Excel en el que salió y el PDF en el que quedó
guardada. De aquí salen el aviso de «ya exportada», el resumen del expediente
y la consulta «¿qué facturas tengo de este proveedor y dónde está su PDF?».

Una factura se identifica por cliente + lado (gasto/ingreso) + NIF de la otra
parte + número + fecha. Sin NIF, en su lugar va el nombre de la otra parte:
dos tiques sin NIF del mismo número y día de dos tiendas son dos facturas.
Sin número o sin fecha legible no se apunta: dos tickets del mismo día se
confundirían.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from . import almacen
from .rutas import dir_datos

LEIDA, REVISADA, EXPORTADA, ARCHIVADA = "leida", "revisada", "exportada", "archivada"
ORDEN_ESTADO = {LEIDA: 0, REVISADA: 1, EXPORTADA: 2, ARCHIVADA: 3}
TEXTO_ESTADO = {LEIDA: "Leída", REVISADA: "Revisada", EXPORTADA: "Exportada",
                ARCHIVADA: "Archivada"}
_LEGADO = "facturas_exportadas.json"


# ------------------------------------------------------------ identidad
def _nif(valor) -> str:
    return re.sub(r"[\s.\-]+", "", str(valor or "")).upper()


def _numero(valor) -> str:
    return "".join(c for c in str(valor or "") if c.isalnum()).upper()


# Para comparar números de factura desde fuera («F-1/26» = «F126»).
numero_clave = _numero


def lado(tipo: str) -> str:
    return "venta" if tipo in ("venta", "ingreso") else "gasto"


# La clave se guarda: estas listas son las suyas y NO se cambian (si se
# cambiaran, las fichas ya guardadas dejarían de encontrarse). Copia fija de
# las de procesar.py en la 1.22.
_FORMAS_CLAVE = frozenset({
    "SA", "SL", "SLU", "SAU", "SLL", "SLNE", "SC", "CB", "SCOOP", "COOP",
    "SAL", "SOCIEDAD", "LIMITADA", "ANONIMA", "UNIPERSONAL", "COOPERATIVA"})
_VACIAS_CLAVE = frozenset({"DE", "LA", "EL", "EN", "LO", "AL", "DEL", "LOS",
                           "LAS", "THE", "AND", "CIA"})


def _palabras_clave(nombre) -> List[str]:
    """«Bar La Esquina, S.L.» → ['BAR', 'LA', 'ESQUINA', 'SL']: sin acentos y
    con las letras sueltas juntas («S. L.» es «SL»). Fija, como las listas."""
    import unicodedata
    texto = "".join(c for c in unicodedata.normalize("NFD", str(nombre or ""))
                    if unicodedata.category(c) != "Mn").upper().replace(".", "")
    palabras, sueltas = [], ""
    for p in re.sub(r"[^\w]+", " ", texto).split():
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


def _nombre_clave(nombre) -> str:
    """El nombre como identidad: sus palabras sin acentos, forma jurídica ni
    artículos, en orden («Bar La Esquina, S.L.» y «BAR ESQUINA SL» son el
    mismo: BAR-ESQUINA)."""
    return "-".join(sorted(p for p in _palabras_clave(nombre)
                           if p not in _FORMAS_CLAVE and p not in _VACIAS_CLAVE))


def _quien(nif, nombre) -> str:
    """La otra parte: su NIF o, si no lo tiene, su nombre (con «~» delante
    para no confundirlo con un NIF)."""
    n = _nif(nif)
    if n:
        return n
    por_nombre = _nombre_clave(nombre)
    return f"~{por_nombre}" if por_nombre else ""


def clave(f, tipo: str) -> Optional[str]:
    """Identidad de una factura dentro de un cliente, o None si no es segura.
    La fecha va la última (del_ejercicio la lee de ahí)."""
    from .validacion import fecha_de
    numero = _numero(f.num_factura)
    dia = fecha_de(f.fecha) if f.fecha else None
    if not numero or not dia:
        return None
    return f"{lado(tipo)}|{_quien(f.nif, f.nombre)}|{numero}|{dia.isoformat()}"


def cliente_de(cliente_nif: str, cliente_nombre: str = "") -> str:
    return _nif(cliente_nif) or f"NOMBRE:{str(cliente_nombre).strip().upper()}"


def _id(cliente: str, k: str) -> str:
    return f"{cliente}#{k}"


# ------------------------------------------------------------- conexión
def _carpeta() -> str:
    return dir_datos()


def _con():
    carpeta = _carpeta()
    _migrar_historial(carpeta)
    _migrar_claves_sin_nif(carpeta)
    return almacen.conexion(carpeta)


_migrados: set = set()
_claves_migradas: set = set()


def _migrar_claves_sin_nif(carpeta: str) -> None:
    """Una sola vez: las fichas sin NIF de antes de la 1.22 pasan a llevar el
    nombre en su clave (si no, la siguiente exportación de esa factura no la
    encontraría y saldría como nueva)."""
    if carpeta in _claves_migradas:
        return
    with almacen.conexion(carpeta) as con:
        hecho = con.execute("SELECT 1 FROM migraciones WHERE coleccion = ?",
                            ("claves_sin_nif",)).fetchone()
        if not hecho:
            existentes = {f["id"] for f in con.execute("SELECT id FROM facturas")}
            cambiadas = 0
            for fila in con.execute(
                    "SELECT id, nombre FROM facturas WHERE id LIKE '%#%||%'").fetchall():
                cliente, _, k = fila["id"].partition("#")
                partes = k.split("|")
                if len(partes) != 4 or partes[1]:
                    continue
                quien = _quien("", fila["nombre"])
                nuevo = _id(cliente, "|".join([partes[0], quien, partes[2], partes[3]]))
                if not quien or nuevo in existentes:
                    continue
                con.execute("UPDATE facturas SET id = ? WHERE id = ?", (nuevo, fila["id"]))
                existentes.discard(fila["id"])
                existentes.add(nuevo)
                cambiadas += 1
            con.execute("INSERT OR REPLACE INTO migraciones VALUES (?, ?, ?)",
                        ("claves_sin_nif", f"{cambiadas} fichas", almacen.ahora()))
    _claves_migradas.add(carpeta)


def _migrar_historial(carpeta: str) -> None:
    """Copia una sola vez el antiguo facturas_exportadas.json (no lo borra)."""
    if carpeta in _migrados:
        return
    with almacen.conexion(carpeta) as con:
        hecho = con.execute("SELECT 1 FROM migraciones WHERE coleccion = ?",
                            ("facturas_exportadas",)).fetchone()
        if not hecho:
            ruta = os.path.join(carpeta, _LEGADO)
            try:
                with open(ruta, encoding="utf-8") as fh:
                    antiguo = json.load(fh)
            except (OSError, ValueError):
                antiguo = {}
            filas = []
            clientes = antiguo.get("clientes") if isinstance(antiguo, dict) else None
            for cliente, facturas in (clientes if isinstance(clientes, dict) else {}).items():
                if not isinstance(facturas, dict):
                    continue
                for k, info in facturas.items():
                    if isinstance(info, dict):
                        try:
                            filas.append(_fila_desde_historial(str(cliente), str(k), info))
                        except (TypeError, ValueError, AttributeError):
                            continue   # una entrada rota no impide lo demás
            con.executemany(_INSERTAR, filas)
            con.execute("INSERT OR REPLACE INTO migraciones VALUES (?, ?, ?)",
                        ("facturas_exportadas", ruta if filas else None,
                         almacen.ahora()))
    _migrados.add(carpeta)


def _iso_desde_texto(texto: str) -> Optional[str]:
    try:
        return datetime.strptime(texto, "%d/%m/%Y %H:%M").isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


_COLUMNAS = ("id", "cliente", "cliente_nif", "cliente_nombre", "tipo", "nif",
             "nombre", "num_factura", "fecha", "ejercicio", "base", "cuota_iva",
             "cuota_requiv", "cuota_irpf", "total", "estado", "leida_en",
             "revisada_en", "exportada_en", "archivada_en", "excel", "pdf",
             "origen", "paginas", "por_total", "actualizado")
_INSERTAR = (f"INSERT OR REPLACE INTO facturas ({', '.join(_COLUMNAS)}) "
             f"VALUES ({', '.join('?' * len(_COLUMNAS))})")


def _fila_desde_historial(cliente: str, k: str, info: dict) -> tuple:
    partes = k.split("|")
    fecha_iso = partes[3] if len(partes) == 4 else ""
    exportada = _iso_desde_texto(info.get("exportada", "")) or almacen.ahora()
    datos = {
        "id": _id(cliente, k), "cliente": cliente,
        "cliente_nif": "" if cliente.startswith("NOMBRE:") else cliente,
        "cliente_nombre": cliente[7:] if cliente.startswith("NOMBRE:") else "",
        "tipo": info.get("tipo") or (partes[0] if partes else "gasto"),
        "nif": info.get("nif"), "nombre": info.get("nombre"),
        "num_factura": info.get("num_factura"), "fecha": info.get("fecha"),
        "ejercicio": int(fecha_iso[:4]) if fecha_iso[:4].isdigit() else None,
        "base": info.get("base"), "cuota_iva": info.get("cuota_iva"),
        "cuota_requiv": info.get("cuota_requiv"), "cuota_irpf": info.get("cuota_irpf"),
        "total": info.get("total"), "estado": EXPORTADA,
        "revisada_en": exportada, "exportada_en": exportada,
        "excel": info.get("archivo") or None, "actualizado": almacen.ahora(),
    }
    return tuple(datos.get(c) for c in _COLUMNAS)


# ------------------------------------------------------------- agrupar
def _agrupar(facturas_por_tipo: Dict[str, Iterable]) -> Dict[str, dict]:
    """Suma las líneas de IVA de cada factura: {clave: datos de la factura}."""
    from .validacion import fecha_de
    agrupadas: Dict[str, dict] = {}
    for tipo, facturas in facturas_por_tipo.items():
        for f in facturas:
            k = clave(f, tipo)
            if not k:
                continue
            if k not in agrupadas:
                dia = fecha_de(f.fecha)
                paginas = list(getattr(f, "paginas_documento", ()) or ())
                if not paginas and f.origen_imagen:
                    primera = int(f.pagina_origen or 0)
                    ultima = int(f.ultima_pagina_origen or primera)
                    paginas = [(f.origen_imagen, p)
                               for p in range(primera, max(primera, ultima) + 1) if p]
                agrupadas[k] = {
                    "tipo": lado(tipo), "num_factura": f.num_factura,
                    "nombre": f.nombre, "nif": f.nif, "fecha": f.fecha,
                    "ejercicio": dia.year if dia else None,
                    "total": f.total_impreso, "base": 0.0, "cuota_iva": None,
                    "cuota_requiv": 0.0, "cuota_irpf": 0.0,
                    # Cliente en recargo por el total: la «base» es el total
                    # y no hay desglose de IVA que comparar.
                    "por_total": 0,
                    "origen": f.origen_imagen or None,
                    "paginas": json.dumps(paginas, ensure_ascii=False) if paginas else None,
                    "_facturas": [],
                }
            fila = agrupadas[k]
            fila["_facturas"].append(f)
            fila["base"] = round(fila["base"] + (f.base_iva or 0), 2)
            if f.cuota_iva is not None:
                fila["cuota_iva"] = round((fila["cuota_iva"] or 0) + f.cuota_iva, 2)
            if getattr(f, "iva_incluido_en_base", False):
                fila["por_total"] = 1
            fila["cuota_requiv"] = round(fila["cuota_requiv"] + (f.cuota_requiv or 0), 2)
            if f.cuota_irpf:
                fila["cuota_irpf"] = f.cuota_irpf
    return agrupadas


def _existentes(con, ids: List[str]) -> Dict[str, sqlite3.Row]:
    salida = {}
    for i in range(0, len(ids), 500):
        trozo = ids[i:i + 500]
        for fila in con.execute(
                f"SELECT * FROM facturas WHERE id IN ({', '.join('?' * len(trozo))})",
                trozo):
            salida[fila["id"]] = fila
    return salida


def _apuntar(cliente_nif: str, cliente_nombre: str,
             facturas_por_tipo: Dict[str, Iterable], estado: str,
             cambios: dict, leidas_en: Optional[dict] = None) -> Tuple[dict, dict]:
    """Crea o pone al día las fichas. Nunca baja una ficha de estado.

    Devuelve ({clave: ficha anterior o {}}, {clave: datos agrupados}).
    """
    cliente = cliente_de(cliente_nif, cliente_nombre)
    agrupadas = _agrupar(facturas_por_tipo)
    if not agrupadas:
        return {}, {}
    momento = almacen.ahora()
    anteriores = {}
    with _con() as con:
        previas = _existentes(con, [_id(cliente, k) for k in agrupadas])
        filas = []
        for k, datos in agrupadas.items():
            ident = _id(cliente, k)
            previa = dict(previas[ident]) if ident in previas else {}
            anteriores[k] = previa
            ficha = dict(previa)
            ficha.update({c: v for c, v in datos.items() if not c.startswith("_")})
            ficha.update(id=ident, cliente=cliente,
                         cliente_nif=_nif(cliente_nif) or None,
                         cliente_nombre=cliente_nombre or previa.get("cliente_nombre"),
                         actualizado=momento)
            actual = previa.get("estado") or LEIDA
            if ORDEN_ESTADO.get(estado, 0) >= ORDEN_ESTADO.get(actual, 0):
                ficha["estado"] = estado
            else:
                ficha["estado"] = actual
            for campo, valor in cambios.items():
                if callable(valor):
                    valor = valor(k, datos)
                if valor is not None:
                    ficha[campo] = valor
            if not ficha.get("leida_en"):
                lectura = None
                for f in datos["_facturas"]:
                    lectura = (leidas_en or {}).get(id(f)) or lectura
                ficha["leida_en"] = lectura or momento
            filas.append(tuple(ficha.get(c) for c in _COLUMNAS))
        con.executemany(_INSERTAR, filas)
    return anteriores, agrupadas


# ---------------------------------------------------------------- pasos
class NoApuntado(Exception):
    """No se pudo apuntar lo exportado (base bloqueada, disco lleno…)."""


def exportar(cliente_nif: str, facturas_por_tipo: Dict[str, Iterable],
             archivos: Dict[str, str], cliente_nombre: str = "",
             cuando: Optional[datetime] = None,
             leidas_en: Optional[dict] = None) -> int:
    """Las facturas acaban de salir en un Excel verificado.

    Si no se puede apuntar, NO se calla (lanza NoApuntado): sin ese apunte,
    la misma factura se podría exportar otra vez a Aplifisa sin aviso."""
    momento = (cuando or datetime.now()).isoformat(timespec="seconds")
    try:
        anteriores, _ = _apuntar(
            cliente_nif, cliente_nombre, facturas_por_tipo, EXPORTADA,
            {"revisada_en": momento, "exportada_en": momento,
             "excel": lambda k, d: os.path.basename(archivos.get(d["tipo"], "")) or None},
            leidas_en)
    except sqlite3.Error as error:
        from . import errores
        import traceback
        errores.apuntar("Apuntar lo exportado en el registro:\n"
                        + traceback.format_exc())
        raise NoApuntado(str(error) or type(error).__name__) from error
    return sum(1 for previa in anteriores.values() if not previa.get("exportada_en"))


def archivar(cliente_nif: str, cliente_nombre: str,
             pdfs: Iterable[Tuple[str, object, str]]) -> int:
    """Cada factura ya tiene su PDF en el archivo: (tipo, factura, ruta)."""
    por_clave: Dict[str, str] = {}
    por_tipo: Dict[str, list] = {}
    for tipo, f, ruta in pdfs:
        k = clave(f, tipo)
        if k and ruta:
            por_clave[k] = ruta
            por_tipo.setdefault(tipo, []).append(f)
    if not por_clave:
        return 0
    momento = almacen.ahora()
    try:
        _apuntar(cliente_nif, cliente_nombre, por_tipo, ARCHIVADA,
                 {"archivada_en": momento, "pdf": lambda k, d: por_clave.get(k)})
    except sqlite3.Error:
        return 0
    return len(por_clave)


def olvidar(cliente_nif: str, facturas_por_tipo: Dict[str, Iterable],
            cliente_nombre: str = "") -> int:
    """Aplifisa rechazó el Excel: esas facturas dejan de contar como exportadas."""
    cliente = cliente_de(cliente_nif, cliente_nombre)
    ids = [_id(cliente, k) for k in _agrupar(facturas_por_tipo)]
    if not ids:
        return 0
    try:
        with _con() as con:
            quitadas = 0
            for ident, fila in _existentes(con, ids).items():
                if not fila["exportada_en"]:
                    continue
                estado = ARCHIVADA if fila["pdf"] else REVISADA
                con.execute("UPDATE facturas SET estado = ?, exportada_en = NULL, "
                            "excel = NULL, actualizado = ? WHERE id = ?",
                            (estado, almacen.ahora(), ident))
                quitadas += 1
    except sqlite3.Error:
        return 0
    return quitadas


# -------------------------------------------------------------- consultas
def _info(fila) -> dict:
    """La ficha como la usa el resto del programa."""
    info = dict(fila)
    exportada = info.get("exportada_en")
    if exportada:
        try:
            info["exportada"] = datetime.fromisoformat(exportada).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            info["exportada"] = exportada
    info["archivo"] = info.get("excel") or ""
    return info


def buscar(cliente_nif: str, f, tipo: str, cliente_nombre: str = "") -> Optional[dict]:
    """La exportación anterior de esta factura, o None si no se exportó."""
    k = clave(f, tipo)
    if not k:
        return None
    try:
        with _con() as con:
            fila = con.execute(
                "SELECT * FROM facturas WHERE id = ? AND exportada_en IS NOT NULL",
                (_id(cliente_de(cliente_nif, cliente_nombre), k),)).fetchone()
    except sqlite3.Error:
        return None
    return _info(fila) if fila else None


def pdf_de(cliente_nif: str, f, tipo: str, cliente_nombre: str = "") -> str:
    """El PDF propio que tiene apuntado esta factura ("" si ninguno)."""
    k = clave(f, tipo)
    if not k:
        return ""
    try:
        with _con() as con:
            fila = con.execute(
                "SELECT pdf FROM facturas WHERE id = ?",
                (_id(cliente_de(cliente_nif, cliente_nombre), k),)).fetchone()
    except sqlite3.Error:
        return ""
    return (fila["pdf"] if fila else "") or ""


def exportadas_de(cliente_nif: str, cliente_nombre: str = "") -> Dict[str, dict]:
    """{clave: ficha} de todo lo exportado de un cliente (una sola consulta)."""
    cliente = cliente_de(cliente_nif, cliente_nombre)
    try:
        with _con() as con:
            filas = con.execute(
                "SELECT * FROM facturas WHERE cliente = ? AND exportada_en IS NOT NULL",
                (cliente,)).fetchall()
    except sqlite3.Error:
        return {}
    prefijo = f"{cliente}#"
    return {fila["id"][len(prefijo):]: _info(fila) for fila in filas}


def del_ejercicio(cliente_nif: str, ejercicio: int, cliente_nombre: str = "",
                  solo_exportadas: bool = True) -> list:
    """Facturas de ese cliente y año, ordenadas por tipo y fecha."""
    cliente = cliente_de(cliente_nif, cliente_nombre)
    condicion = " AND exportada_en IS NOT NULL" if solo_exportadas else ""
    try:
        with _con() as con:
            filas = con.execute(
                "SELECT * FROM facturas WHERE cliente = ? AND ejercicio = ?"
                + condicion, (cliente, int(ejercicio))).fetchall()
    except sqlite3.Error:
        return []
    salida = []
    for fila in filas:
        info = _info(fila)
        info["_fecha_iso"] = info["id"].rsplit("|", 1)[-1]
        salida.append(info)
    return sorted(salida, key=lambda f: (f.get("tipo", ""), f["_fecha_iso"],
                                         str(f.get("num_factura") or "")))


def consultar(texto: str = "", ejercicio: Optional[int] = None,
              limite: int = 2000) -> List[dict]:
    """Búsqueda libre por proveedor/cliente, NIF, número o importe."""
    condiciones, valores = [], []
    if ejercicio:
        condiciones.append("ejercicio = ?")
        valores.append(int(ejercicio))
    for palabra in str(texto or "").split():
        like = f"%{palabra.upper()}%"
        importe = palabra.replace(".", "").replace(",", ".")
        extra = ""
        try:
            numero = round(float(importe), 2)
            extra = " OR ROUND(total, 2) = ? OR ROUND(base, 2) = ?"
        except ValueError:
            numero = None
        condiciones.append(
            "(UPPER(COALESCE(nombre,'')) LIKE ? OR UPPER(COALESCE(nif,'')) LIKE ? "
            "OR UPPER(COALESCE(num_factura,'')) LIKE ? "
            "OR UPPER(COALESCE(cliente_nombre,'')) LIKE ? OR cliente LIKE ?"
            + extra + ")")
        valores += [like] * 5 + ([numero, numero] if numero is not None else [])
    sql = "SELECT * FROM facturas"
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY ejercicio DESC, cliente, tipo, fecha LIMIT ?"
    valores.append(int(limite))
    try:
        with _con() as con:
            return [_info(f) for f in con.execute(sql, valores).fetchall()]
    except sqlite3.Error:
        return []


def _pares_cliente() -> List[Tuple[str, str]]:
    try:
        with _con() as con:
            filas = con.execute(
                "SELECT cliente_nif, cliente_nombre, MAX(actualizado) FROM facturas "
                "GROUP BY cliente_nif, cliente_nombre "
                "ORDER BY MAX(actualizado), MAX(rowid)").fetchall()
    except sqlite3.Error:
        return []
    return [(_nif(f[0]), (f[1] or "").strip()) for f in filas]


def clientes() -> List[Tuple[str, str]]:
    """(NIF, nombre) de los clientes con alguna factura guardada: uno por
    NIF (con el último nombre usado) y los guardados solo por su nombre,
    salvo si ese nombre es de un único NIF (es el mismo cliente)."""
    pares = _pares_cliente()
    por_nif: Dict[str, str] = {}
    for nif, nombre in pares:                 # del más antiguo al último
        if nif:
            por_nif[nif] = nombre or por_nif.get(nif, "")
    nifs_de_nombre: Dict[str, set] = {}
    for nif, nombre in pares:
        if nif and nombre:
            nifs_de_nombre.setdefault(nombre.upper(), set()).add(nif)
    salida = [(nif, nombre) for nif, nombre in por_nif.items()]
    vistos = set()
    for nif, nombre in pares:
        if nif or not nombre or nombre.upper() in vistos:
            continue
        vistos.add(nombre.upper())
        if len(nifs_de_nombre.get(nombre.upper(), ())) != 1:
            salida.append(("", nombre))
    return sorted(salida, key=lambda c: (c[1].upper(), c[0]))


def claves_cliente(cliente_nif: str, cliente_nombre: str = "") -> List[Tuple[str, str]]:
    """Con qué (NIF, nombre) buscar todo lo guardado de un cliente: su NIF y
    los nombres con los que algún lote salió sin NIF, si esos nombres son
    solo suyos."""
    nif = _nif(cliente_nif)
    if not nif:
        return [("", cliente_nombre)]
    pares = _pares_cliente()
    nombres = {n for f, n in pares if f == nif and n}
    if cliente_nombre:
        nombres.add(cliente_nombre.strip())
    salida = [(nif, cliente_nombre)]
    for nombre in sorted(nombres):
        otros = {f for f, n in pares if f and f != nif and n.upper() == nombre.upper()}
        if not otros:
            salida.append(("", nombre))
    return salida


def ejercicios() -> List[int]:
    try:
        with _con() as con:
            return [f[0] for f in con.execute(
                "SELECT DISTINCT ejercicio FROM facturas WHERE ejercicio IS NOT NULL "
                "ORDER BY ejercicio DESC")]
    except sqlite3.Error:
        return []


def cambiar_ruta(vieja: str, nueva: str) -> None:
    """Un documento se ha movido: que las fichas apunten a su sitio nuevo."""
    def mismo(ruta) -> bool:
        return bool(ruta) and os.path.normcase(os.path.abspath(ruta)) == \
            os.path.normcase(os.path.abspath(vieja))

    try:
        with _con() as con:
            for fila in con.execute("SELECT id, origen, pdf, paginas FROM facturas").fetchall():
                cambios = {}
                if mismo(fila["origen"]):
                    cambios["origen"] = nueva
                if mismo(fila["pdf"]):
                    cambios["pdf"] = nueva
                try:
                    paginas = json.loads(fila["paginas"] or "[]")
                except ValueError:
                    paginas = []
                if any(mismo(o) for o, _p in paginas):
                    cambios["paginas"] = json.dumps(
                        [(nueva if mismo(o) else o, p) for o, p in paginas],
                        ensure_ascii=False)
                if cambios:
                    con.execute(
                        f"UPDATE facturas SET {', '.join(f'{c} = ?' for c in cambios)} "
                        "WHERE id = ?", (*cambios.values(), fila["id"]))
    except sqlite3.Error:
        pass


def usa_retenciones(cliente_nif: str, cliente_nombre: str = "") -> bool:
    """Si alguna factura exportada de este cliente llevaba retención."""
    if not (cliente_nif or cliente_nombre):
        return False
    try:
        with _con() as con:
            return con.execute(
                "SELECT 1 FROM facturas WHERE cliente = ? AND COALESCE(cuota_irpf, 0) != 0 "
                "LIMIT 1", (cliente_de(cliente_nif, cliente_nombre),)).fetchone() is not None
    except sqlite3.Error:
        return False
