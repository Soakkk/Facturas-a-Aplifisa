# Cómo se trabaja en este proyecto

En este programa trabajan **dos asistentes de IA a la vez**, cada uno en su
sesión, sobre el **mismo repositorio y la misma rama `master`**. Ya ha pasado
que los dos publicaran versiones con minutos de diferencia (v1.10.1 y v1.10.2 el
2026-09-02). No se perdió nada, pero se pudo perder.

Estas reglas existen para que el trabajo de uno **no pise ni estropee** el del
otro. Son obligatorias antes de tocar código.

## Antes de empezar a trabajar, SIEMPRE

```bash
git fetch
git log --oneline HEAD..origin/master     # ¿hay trabajo nuevo del otro?
git rebase origin/master                  # ponerse encima de lo suyo
```

Si sale trabajo nuevo, **léelo antes de programar** (`git log -p`). Puede que ya
haya arreglado lo que ibas a arreglar, o que haya cambiado la función que ibas a
usar. Trabajar sobre código viejo es la forma más rápida de tirar horas.

## Al publicar

Usa `scripts/publicar.py`, que hace todo esto en orden y se planta si algo falla:

```bash
.venv\Scripts\python scripts\publicar.py "resumen del cambio"
```

Comprueba el trabajo del otro, se pone encima, pasa los tests, **elige el
siguiente número de versión libre** (mirando las etiquetas que ya hay en
GitHub), etiqueta y sube. El CI compila el instalador y publica la release.

Nunca a mano, y **nunca `git push --force`**: aquí solo hay una rama y forzar
borra el trabajo del otro sin avisar.

## Reglas que no se saltan

1. **Nunca `--force`** en push, ni sobre `master` ni sobre etiquetas.
2. **Un número de versión, una release.** Si la que ibas a usar ya existe en
   GitHub, coge la siguiente. `publicar.py` lo hace solo.
3. **Los tests se pasan antes de publicar**, no después:
   `.venv\Scripts\python -m pytest tests\ -q`.
4. **Nada de nombres, NIF ni importes de clientes reales** en el código ni en
   los tests: el repositorio es **público**. Usar NIF de prueba (12345678Z,
   B12345674). Las cachés, PDF y Excel están en `.gitignore`.
5. **Si el otro ya tocó ese fichero hoy, integra en vez de reescribir.** Antes
   de rehacer una función, mira `git log -p -- <fichero>`.

## Cómo está montado

- **Entorno**: `.venv` con Python 3.11 (el `python` del sistema es un 3.7 viejo).
- **Interfaz**: PySide6 (`app.py`), con diálogos aparte (`dialogo_*.py`).
- **Lectura**: Gemini (`extraccion.py`), modelo fijado a `gemini-3.7-flash`.
- **Criterio contable**: `conceptos.py` + `config/conceptos_aplifisa.csv`, que es
  el catálogo REAL de conceptos del Aplifisa del usuario. Las cuentas salen de
  ahí; no se inventan.
- **Escaneo**: `escaner.py`. El alimentador va por **NAPS2** (WIA solo devuelve
  la primera hoja del taco con esta HP); el cristal, por WIA.
- **Datos del usuario**: `%APPDATA%\FacturasAplifisa` (ajustes, clientes,
  proveedores, gasto de Gemini).
- **Canal con el usuario**: `config/pendientes.md` es lo que él ve dentro del
  programa (Ayuda → Diagnóstico y sugerencias). Ahí se le pregunta lo que haga
  falta, y él contesta en
  `%APPDATA%\FacturasAplifisa\notas-para-claude.md`: **leerlo al empezar**.

## Con quién se habla

El usuario es asesor fiscal, **no programador**. Explicarle en su idioma: qué
hace el programa y por qué, no cómo está implementado. Los criterios contables
los pone él y mandan sobre cualquier suposición nuestra (ejemplo: el gasóleo va
a 628 G16, no a G18).
