"""Guardado seguro de las API keys (Gemini y Claude) usando el Almacen de
credenciales de Windows (via keyring). Nunca se guardan en texto plano ni en
el repositorio."""

from __future__ import annotations

import os

import keyring

SERVICIO = "FacturasAExcel"
USUARIO = "gemini_api_key"
# La de Claude (Anthropic) va aparte: con «Claude» elegido en los modelos de
# lectura se usan las dos (Claude lee primero y Gemini hace la segunda).
USUARIO_CLAUDE = "claude_api_key"


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


def guardar_api_key_claude(clave: str) -> None:
    keyring.set_password(SERVICIO, USUARIO_CLAUDE, clave.strip())


def leer_api_key_claude() -> str | None:
    # Igual que la de Gemini: la variable de entorno manda (pruebas).
    env = os.environ.get("CLAUDE_API_KEY")
    if env:
        return env
    try:
        return keyring.get_password(SERVICIO, USUARIO_CLAUDE)
    except Exception:    # sin almacen de credenciales: como si no hubiera
        return None


def borrar_api_key_claude() -> None:
    try:
        keyring.delete_password(SERVICIO, USUARIO_CLAUDE)
    except keyring.errors.PasswordDeleteError:
        pass
