"""Guardado seguro de la API key de Gemini usando el Almacen de credenciales de
Windows (via keyring). Nunca se guarda en texto plano ni en el repositorio."""

from __future__ import annotations

import os

import keyring

SERVICIO = "FacturasAExcel"
USUARIO = "gemini_api_key"


def guardar_api_key(clave: str) -> None:
    keyring.set_password(SERVICIO, USUARIO, clave.strip())


def leer_api_key() -> str | None:
    # Prioridad: variable de entorno (util en pruebas) -> almacen seguro.
    env = os.environ.get("GEMINI_API_KEY")
    if env:
        return env
    return keyring.get_password(SERVICIO, USUARIO)


def borrar_api_key() -> None:
    try:
        keyring.delete_password(SERVICIO, USUARIO)
    except keyring.errors.PasswordDeleteError:
        pass
