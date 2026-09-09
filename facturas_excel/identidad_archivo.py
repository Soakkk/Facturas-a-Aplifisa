"""Carpetas estables por NIF y reorganización reversible del archivo antiguo."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime
from uuid import uuid4

from . import clientes
from .escaner import sanear

INDICE = ".clientes.json"
HISTORIAL = "_Organizacion"
DUPLICADOS = "_Duplicados"


def leer(base):
    ruta = Path(base) / INDICE
    if not ruta.exists():
        return {}
    # Un índice dañado debe avisarse, nunca sustituirse por otro vacío.
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if (not isinstance(datos, dict) or any(
            not isinstance(nif, str) or not nif or not isinstance(ficha, dict)
            or not isinstance(ficha.get("nombre"), str)
            or not isinstance(ficha.get("carpeta"), str)
            or Path(ficha["carpeta"]).name != ficha["carpeta"]
            for nif, ficha in datos.items())):
        raise ValueError("No se puede leer el índice de clientes del archivo.")
    return datos


def guardar(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ruta.parent,
                                         delete=False) as f:
            temporal = f.name
            json.dump(datos, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, ruta)
    finally:
        if temporal and os.path.exists(temporal):
            os.unlink(temporal)


def dentro(base, relativa):
    base = Path(base).resolve()
    ruta = (base / relativa).resolve()
    if ruta == base or not ruta.is_relative_to(base):
        raise ValueError("La ruta sale de la carpeta de escaneos.")
    return ruta


def carpeta_cliente(base, nombre, nif=""):
    nif = clientes._normaliza(nif)
    if not nif:
        return sanear(nombre)
    indice = leer(base)
    if nif not in indice:
        indice[nif] = {"nombre": nombre.strip(),
                       "carpeta": f"{sanear(nombre)} — {nif}"}
        guardar(Path(base) / INDICE, indice)
    carpeta = indice[nif]["carpeta"]
    dentro(base, carpeta)
    return carpeta


def huella(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def copia_existente(ruta, carpeta):
    """Reutiliza únicamente PDF idénticos dentro del mismo destino documental."""
    candidatos = [p for p in Path(carpeta).glob("*.pdf")
                  if p.is_file() and p.stat().st_size == Path(ruta).stat().st_size]
    if candidatos:
        digest = huella(ruta)
        return next((str(p) for p in candidatos if huella(p) == digest), None)
    return None


def _clave(nombre):
    return tuple(sorted(clientes._clave_nombre(nombre).split()))


def planificar(base):
    """Propone correspondencias únicas; la persona revisa antes de mover nada."""
    base = Path(base).resolve()
    indice = leer(base)
    fichas = clientes._leer_todo()
    for nif, ficha in indice.items():
        fichas.setdefault(nif, ficha)
    nombres = {}
    for nif, ficha in fichas.items():
        if isinstance(ficha, dict) and ficha.get("nombre"):
            nombres.setdefault(_clave(ficha["nombre"]), set()).add(nif)
    movimientos, pendientes, destinos = [], [], {}
    pdfs_destino = {}
    registro = dict(indice)
    for carpeta in sorted(base.iterdir()):
        if (not carpeta.is_dir() or carpeta.name.startswith(("_", "."))
                or carpeta.name == "Sin identificar"):
            continue
        # Las carpetas registradas tienen una identidad explícita.
        nifs = {n for n, f in indice.items() if f["carpeta"] == carpeta.name}
        nifs = nifs or nombres.get(_clave(carpeta.name), set())
        if len(nifs) != 1:
            pendientes.append(carpeta.name)
            continue
        nif = next(iter(nifs))
        ficha = registro.setdefault(nif, {
            "nombre": fichas[nif]["nombre"],
            "carpeta": f"{sanear(fichas[nif]['nombre'])} — {clientes._normaliza(nif)}"})
        destino_carpeta = ficha["carpeta"]
        carpeta_final = dentro(base, destino_carpeta)
        if carpeta_final.is_dir():
            for existente in sorted(carpeta_final.rglob("*.pdf")):
                if existente.is_file():
                    rel = existente.relative_to(base)
                    pdfs_destino.setdefault((os.path.normcase(str(rel.parent)), huella(existente)), str(rel))
        for origen in sorted(carpeta.rglob("*")):
            if not origen.is_file():
                continue
            if origen.resolve() != origen.absolute():
                pendientes.append(str(origen.relative_to(base)))
                continue
            relativa = str(origen.relative_to(base))
            dentro(base, relativa)
            destino = Path(destino_carpeta) / origen.relative_to(carpeta)
            digest = huella(origen)
            clave_pdf = (os.path.normcase(str(destino.parent)), digest)
            previa = pdfs_destino.get(clave_pdf) if origen.suffix.lower() == ".pdf" else None
            if previa and os.path.normcase(previa) != os.path.normcase(relativa):
                destino = Path(DUPLICADOS) / relativa
            elif os.path.normcase(str(destino)) == os.path.normcase(relativa):
                continue
            # No sobrescribir nombres: conservar copias idénticas aparte y
            # numerar archivos distintos que casualmente se llamen igual.
            original_destino = destino
            numero = 2
            while True:
                clave = os.path.normcase(str(destino))
                existente = destinos.get(clave)
                destino_abs = dentro(base, destino)
                if existente is None and destino_abs.exists():
                    existente = huella(destino_abs)
                if existente is None:
                    break
                if existente == digest and destino.parts[0] != DUPLICADOS:
                    destino = Path(DUPLICADOS) / relativa
                    original_destino, numero = destino, 2
                else:
                    destino = original_destino.with_name(
                        f"{original_destino.stem}_{numero}{original_destino.suffix}")
                    numero += 1
            destinos[os.path.normcase(str(destino))] = digest
            if origen.suffix.lower() == ".pdf" and destino.parts[0] != DUPLICADOS:
                pdfs_destino.setdefault(clave_pdf, str(destino))
            movimientos.append({"origen": relativa, "destino": str(destino), "sha256": digest})
    return {"movimientos": movimientos, "pendientes": pendientes,
            "indice_antes": indice, "indice_despues": registro}


def _trasladar(base, origen, destino, digest):
    origen, destino = dentro(base, origen), dentro(base, destino)
    if not origen.is_file() or huella(origen) != digest:
        raise ValueError(f"El archivo ha cambiado: {origen.name}. Vuelva a revisar el plan.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Creación exclusiva: nunca sobreescribir, tampoco ante una carrera.
    creada = False
    try:
        with open(origen, "rb") as entrada, open(destino, "xb") as salida:
            creada = True
            shutil.copyfileobj(entrada, salida)
            salida.flush()
            os.fsync(salida.fileno())
        if huella(destino) != digest or huella(origen) != digest:
            raise OSError(f"No se pudo comprobar la copia de {origen.name}.")
        shutil.copystat(origen, destino)
        origen.unlink()
    except Exception:
        if creada and origen.exists():
            destino.unlink(missing_ok=True)
        raise


def aplicar(base, plan):
    """Guarda el plan antes de mover; cada archivo queda trazado y recuperable."""
    if leer(base) != plan["indice_antes"]:
        raise ValueError("El archivo cambió. Revise una nueva propuesta.")
    registro = {**plan, "completados": [], "estado": "en curso"}
    ruta = Path(base) / HISTORIAL / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{uuid4().hex[:8]}.json"
    guardar(ruta, registro)
    try:
        for movimiento in plan["movimientos"]:
            _trasladar(base, movimiento["origen"], movimiento["destino"], movimiento["sha256"])
            registro["completados"].append(movimiento)
            guardar(ruta, registro)
        guardar(Path(base) / INDICE, plan["indice_despues"])
        registro["estado"] = "completado"
        guardar(ruta, registro)
    except Exception:
        registro["estado"] = "incompleto"
        guardar(ruta, registro)
        raise
    # Solo carpetas vacías, únicamente dentro de la raíz comprobada.
    antiguas = {Path(m["origen"]).parts[0] for m in plan["movimientos"]}
    for nombre in antiguas:
        carpeta = dentro(base, nombre)
        for raiz, _, _ in os.walk(carpeta, topdown=False):
            try:
                dentro(base, Path(raiz).relative_to(Path(base).resolve())).rmdir()
            except OSError:
                pass
    return str(ruta)


def deshacer_ultimo(base):
    registros = sorted((Path(base) / HISTORIAL).glob("*.json"), reverse=True)
    for ruta in registros:
        registro = json.loads(ruta.read_text(encoding="utf-8"))
        if registro["estado"] == "deshecho":
            continue
        for m in reversed(registro["movimientos"]):
            origen, destino = dentro(base, m["origen"]), dentro(base, m["destino"])
            if origen.exists():
                if huella(origen) != m["sha256"]:
                    raise ValueError(f"El original ha cambiado: {origen.name}.")
                continue
            _trasladar(base, m["destino"], m["origen"], m["sha256"])
        # No descartar clientes registrados después de la reorganización.
        indice = leer(base)
        for nif, ficha in registro["indice_despues"].items():
            if indice.get(nif) == ficha and nif not in registro["indice_antes"]:
                carpeta = dentro(base, ficha["carpeta"])
                if not any(p.is_file() for p in carpeta.rglob("*")):
                    indice.pop(nif)
        indice.update(registro["indice_antes"])
        guardar(Path(base) / INDICE, indice)
        registro["estado"] = "deshecho"
        guardar(ruta, registro)
        return True
    return False
