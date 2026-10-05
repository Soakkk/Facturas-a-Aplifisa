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
- **Interfaz**: PySide6. `app.py` monta la ventana; el trabajo está repartido
  en `ventana_lectura.py` (cola y Gemini), `ventana_archivo.py` (escanear,
  recoger, expedientes), `ventana_aplifisa.py` (exportar y cuadrar),
  `ventana_validacion.py` (semáforo, avisos, totales), `ventana_ficha.py`
  (visor, ficha y recuadros), `cinta.py`, `hilos.py`. Diálogos en
  `dialogo_*.py`.
- **Lote**: `lote.py`. Cada línea es una `Fila` con su `Factura`; la tabla
  (`tabla_facturas.py`) solo la enseña. Lo que se escribe en una celda pasa a
  la factura en `_on_celda`; lo que cambia el programa se cambia en la
  factura y se repinta con `tabla.pintar`. No leer datos de las celdas.
- **Datos guardados**: `almacen.py` (SQLite en `%APPDATA%`, colecciones con
  migración única desde los JSON antiguos) y `registro_facturas.py` (una
  ficha por factura con su recorrido, Excel y PDF; `historial.py` es su
  fachada). El directorio de clientes de la suite sigue en JSON, compartido.
- **Lectura**: Gemini (`extraccion.py`), modelos fijos `gemini-3.8-flash`
  (principal) y `gemini-3.7-flash` (respaldo), configurables; doble lectura
  comparada en `doble_lectura.py`. Nunca alias `-latest`.
- **Criterio contable**: `conceptos.py` + `config/conceptos_aplifisa.csv`, que es
  el catálogo REAL de conceptos del Aplifisa del usuario. Las cuentas salen de
  ahí; no se inventan.
- **Escaneo**: `escaner.py`. El alimentador va por **NAPS2** (WIA solo devuelve
  la primera hoja del taco con esta HP); el cristal, por WIA.
- **Datos del usuario**: `%APPDATA%\FacturasAplifisa`, en
  `facturas_aplifisa.db` (ajustes, clientes, proveedores, gasto de Gemini,
  registro de facturas, exámenes) más la sesión, las muestras y las notas.
- **Canal con el usuario**: `config/pendientes.md` es lo que él ve dentro del
  programa (Ayuda → Diagnóstico y sugerencias). Ahí se le pregunta lo que haga
  falta, y él contesta en
  `%APPDATA%\FacturasAplifisa\notas-para-claude.md`: **leerlo al empezar**.

## Criterio fiscal: manda la ley, siempre

Lo pidió el usuario el 2026-10-05 para todo el programa: **el tratamiento
fiscal de cada factura sale de la ley vigente en su fecha** (Ley 37/1992 del
IVA y su Reglamento; Ley 35/2006 del IRPF y su Reglamento), no de lo que traiga
impreso la factura ni de una costumbre o suposición nuestra.

- Si una factura no casa con la ley (un recargo que no toca a su tipo de IVA,
  un recargo cobrado a una sociedad…), **se avisa diciendo por qué**.
- Lo que la ley deja abierto o depende de datos que el programa no tiene (el
  régimen del cliente, a qué actividad va una compra…) **se le pregunta y se
  recuerda**: sus criterios contables mandan dentro de la ley.
- Antes de programar algo fiscal, comprobar qué dice la norma. Si no hay
  certeza, se le pregunta en vez de suponer.
- Ejemplo: cliente en recargo de equivalencia (arts. 148 a 163 LIVA) → no
  presenta 303 ni deduce IVA → **todas** sus compras por el total, traigan o no
  recargo impreso; y una sociedad no puede estar en recargo (art. 148).

## Con quién se habla

El usuario es asesor fiscal, **no programador**. Explicarle en su idioma: qué
hace el programa y por qué, no cómo está implementado. Los criterios contables
los pone él y mandan sobre cualquier suposición nuestra (ejemplo: el gasóleo va
a 628 G16, no a G18).
