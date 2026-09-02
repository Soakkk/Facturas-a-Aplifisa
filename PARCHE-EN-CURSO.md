# Parche en curso — acordado el 2026-09-01

> **Qué es esto:** la lista de cambios pendientes acordados con el usuario, con el
> detalle técnico para poder retomarlos en cualquier sesión.
> **REGLA: cuando los 6 puntos estén al 100% (hechos, con tests y publicados en
> una release), este archivo SE BORRA** (`git rm PARCHE-EN-CURSO.md`). Si queda
> algo a medias, el archivo se queda y se actualiza el estado de cada punto.
>
> Punto de partida: **v1.4.0**, rama `master`, carpeta local al día con GitHub.
> Antes de tocar nada: `git fetch` y mirar `HEAD..origin/master` (Ricardo publica
> desde otro sitio). Tests: `.venv\Scripts\python -m pytest tests\ -q` (86 tests).
>
> **LO QUE FALTA PARA PODER BORRAR ESTE ARCHIVO (2026-09-02):**
> 1. Que el usuario **pruebe el escaneo con papel de verdad** en su HP M148dw.
> 2. Ver **qué modelo de Gemini** sale en pantalla en un lote real y decidir si
>    se fija `MODELOS` a `gemini-2.5-flash` (ver punto 1).
> 3. **Publicar la versión** (subir `__version__` + tag `vX.Y.Z`).

## Estado general

| # | Mejora | Estado |
|---|--------|--------|
| 1 | Modelo, coste y presupuesto de Gemini | ✅ hecho (falta decidir modelo) |
| 2 | El programa escanea (botón + ADF) | ✅ hecho |
| 7 | Cliente automático y gestión de los PDF | ✅ hecho (pedido el 2026-09-02) |
| 8 | Escaneo configurable (color/ppp) y coste por factura | ✅ hecho |
| 9 | Panel de totales ocultable | ✅ hecho |
| 3 | Quitar el banner azul superior | ✅ hecho (menú Configuración incluido) |
| 4 | Resumen de importes por bloque escaneado | ✅ hecho |
| 5 | Quitar el trimestre | ✅ hecho |
| 6 | Trabajar por bloques (varios PDF en un Excel) | ✅ hecho |

Orden recomendado: **5 → 3 → 6 → 4 → 1 → 2**. El 5 y el 3 son limpieza rápida;
el 6 cambia la estructura de datos y el 4 se apoya en él; el 1 y el 2 son
funcionalidad nueva e independiente.

---

## 1. Qué Gemini se usa, cuánto cuesta y cuánto queda — ✅ HECHO (2026-09-02)

`costes.py` con la tabla de tarifas (repasada el 2026-09-02 en la página oficial
de precios), `gasto.json` por meses en `%APPDATA%`, tope configurable (5 €) y
aviso al 80 % y al 100 %. `extraccion._consumo()` saca de cada respuesta el
`model_version` real y los tokens (el "pensamiento" cuenta como salida); el
Worker los suma y la ventana lo enseña abajo a la derecha.

**PENDIENTE DE DECIDIR con datos reales:** `gemini-flash-latest` ya no apunta al
2.5 Flash. Los Gemini 3.6/3.7 Flash cuestan **0,75 $ / 3,75 $** por millón
(lanzamiento; **el 1/1/2027 pasan a 1,50 / 7,50**) frente a **0,30 / 2,50** del
2.5 Flash y **0,10 / 0,40** del 2.5 Flash-Lite. Con 30 facturas: ~0,073 € con
3.7 Flash, ~0,040 € con 2.5 Flash y ~0,009 € con 2.5 Flash-Lite. En cuanto el
usuario pase un lote, mirar qué modelo sale en pantalla y decidir si se fija
`MODELOS` a `gemini-2.5-flash`. **Sigue pendiente el escalado selectivo** (mandar
a un modelo caro solo las facturas ámbar/rojas o de confianza baja).

**Decidido con el usuario:** contador local + tope mensual. *La API de Gemini no
expone el saldo de la cuenta* (eso solo está en la consola de Google Cloud), así
que el gasto se calcula con los tokens reales que devuelve cada respuesta.

Qué hacer:

- `extraccion.py`: al llamar a Gemini, guardar de la respuesta
  `response.model_version` (**el modelo real que ha contestado**, que no siempre
  es el alias pedido: `gemini-flash-latest` apunta a una versión concreta) y
  `response.usage_metadata` (`prompt_token_count`, `candidates_token_count`,
  `total_token_count`). Devolverlos dentro de `ResultadoExtraccion`.
- Módulo nuevo `costes.py`:
  - Tabla de precios por modelo (€/millón de tokens, entrada y salida) en un
    dict fácil de actualizar, con fecha de última revisión y aviso de "precio
    estimado" si el modelo no está en la tabla.
  - `%APPDATA%\FacturasAplifisa\gasto.json`: acumulado **por mes** (`2026-09`)
    con tokens, coste y nº de facturas; y el `tope_mensual` que ponga el usuario
    (por defecto 5 €, que es su límite actual en Google).
  - Funciones: `registrar(modelo, tokens_in, tokens_out)`, `mes_actual()`,
    `restante()`.
- UI: línea de estado o tarjeta pequeña con
  `Modelo: gemini-2.5-flash · Este lote: 0,004 € · Mes: 0,42 € de 5,00 €`.
  Barra de progreso del presupuesto; **aviso ámbar al 80 % y rojo al 100 %**
  (solo avisa, no bloquea). Ajuste del tope en un diálogo (junto al botón
  "Configurar Gemini").
- **Optimización coste/precisión** (lo que pidió: máximo rendimiento al mínimo
  coste). Base medida en su día: una página a 150 ppp ≈ **1.548 tokens** de
  entrada; subir a 200 ppp dobla y a 300 ppp triplica. Propuesta a implementar y
  medir:
  1. Mantener `gemini-flash-latest` como modelo por defecto (relación
     precisión/coste ganadora para facturas).
  2. **Escalado selectivo**: solo las facturas que salgan en ámbar/rojo o con
     `confianza: baja` se reintentan con `gemini-pro-latest` **y 300 ppp**. Así
     el modelo caro toca el 10-15 % del lote, no el 100 %.
  3. Registrar por lote cuántas fueron al modelo caro, para poder decidir con
     números si compensa.
  4. Comprobar antes si `gemini-flash-lite-latest` da igual de bien con las
     facturas grandes y legibles (es ~3× más barato); si sí, usarlo de primera
     pasada y flash de refuerzo.

## 2. El programa ES el escáner (botón Escanear) — ✅ HECHO (2026-09-02)

Hecho con **WIA** (el escaneo de Windows, sin instalar NAPS2 ni nada: se probó
que Windows ve la HP LJ Pro M148/M149 por USB). `escaner.py` (enumerar, ADF,
dúplex, ppp, y armar el PDF con PyMuPDF), `dialogo_escaneo.py` (cliente + tipo),
`ajustes.py` (carpeta, escáner y ppp recordados) y el menú **Configuración**.
El PDF va a `<carpeta>\<CLIENTE>\<CLIENTE>_<gastos|ingresos>_<fecha>.pdf` y
entra solo en el lote como un bloque. Atajos Ctrl+E / Ctrl+O / Ctrl+G. Nueva
dependencia: **pywin32** (en requirements y en el .spec).
**PROBADO CON LA HP DE VERDAD (v1.5.1, 2026-09-02)**: una pasada por el cristal
a 200 ppp tardó 8,8 s y salió un PDF A4 de 33 KB. La v1.5.0 fallaba con
«El parámetro no es correcto» por dos motivos, los dos arreglados y con test:
la HP **solo entrega BMP** (se le pedía JPEG; ahora se pide lo que cada aparato
declare y se convierte a JPEG con PIL), y los márgenes a 300 ppp se salían del
máximo del cristal (1700x3000), así que ahora todo valor se recorta a lo que
admita la propiedad (`_ajustar`). **EL ALIMENTADOR NECESITA NAPS2 (v1.6.0) — LO GORDO.** WIA con esta HP pasa el
taco entero por el alimentador pero **solo devuelve la PRIMERA imagen**: 13
facturas acababan en un PDF de 1 pagina. Probado en el aparato real que no hay
forma por WIA (ni `Pages=1`, ni reconectar, ni re-pedir el item): es limitacion
de la capa de automatizacion (el multipagina de verdad necesita `IWiaTransfer`
con callbacks, que wiaaut no expone). **Solucion: NAPS2** (libre; instalado con
`winget install Cyanfish.NAPS2`; consola en WindowsApps). Probado: 11 hojas en
un PDF de 11 paginas en 52 s. `escaner.escanear_naps2()` lo llama con
`--noprofile --driver wia --source feeder|duplex --dpi --bitdepth --pagesize a4
--deskew --force --verbose -o`. **El cristal sigue con WIA** para no depender de
nada. Si falta NAPS2 y se pide alimentador: `FaltaNAPS2` con el enlace.

**(v1.5.2, ya superado por lo de arriba)**: poner la propiedad de
dispositivo **`Pages` (3096)** hacía que `Transfer` fallase con el mismo
E_INVALIDARG, aunque la HP declare que admite de 0 a 50. Sin tocarla, el ADF
escanea bien (probado: tiró de una hoja, 14,9 MB en BMP). Tampoco se fijan ya
los márgenes en modo alimentador (el tamaño lo manda el ADF). Y si la primera
hoja falla por falta de papel, ahora sale «El alimentador está vacío» en vez
del error crudo del COM. **Falta ver un taco de varias hojas seguidas.**
Queda sin hacer el punto 6 de abajo (carpeta vigilada) y la sinergia con
Escaner-Fotos-Facturas.

**Lo que quiere el usuario (aclarado 2026-09-01):** NO usar la app de HP y que
esta la vigile. Quiere **un botón "Escanear" dentro del programa** que dispare
el escaneo, guarde el PDF en una carpeta con **nombre de cliente y tipo
(gastos/ingresos)** y lo procese solo, sin tocar nada más.

**Equipo: HP LaserJet Pro MFP M148dw** (multifunción con alimentador ADF).

Flujo a construir:

1. Botón **"Escanear"** (junto a "Abrir PDF o imágenes") y `Ctrl+E`.
2. Diálogo corto antes de escanear: **Cliente** (desplegable con los ya
   conocidos de `clientes.json` + escribir uno nuevo) y **Tipo**
   (Gastos / Ingresos), más "una cara / doble cara" recordado.
   *Nota: el tipo aquí es solo para archivar y nombrar; cada factura la sigue
   clasificando el programa por el NIF.*
3. Escaneo real por **NAPS2** (open source, GPL, Windows; habla con la HP por
   WIA y **soporta ADF y dúplex**):
   `NAPS2.Console.exe -d "<escáner>" --source feeder [--dupleix] -o "<destino>"`.
   Módulo nuevo `escaner.py`: localizar `NAPS2.Console.exe` (Program Files o
   ruta guardada en ajustes), listar dispositivos, lanzar el escaneo en un
   `QThread` con progreso, y si NAPS2 no está instalado **ofrecer el enlace de
   descarga** en vez de fallar. Reserva sin instalar nada: WIA por COM
   (`win32com.client`), pero controla peor el ADF.
4. **Nombre y sitio del archivo**, todo automático:
   `<carpeta base>\<CLIENTE>\<CLIENTE>_<gastos|ingresos>_<aaaa-mm-dd>_<n>.pdf`
   (el `<n>` evita pisar nada si se escanea varias veces el mismo día). La
   carpeta base se configura en el menú (por defecto
   `%USERPROFILE%\Documents\Facturas escaneadas`). Nombres saneados (sin
   acentos raros ni caracteres prohibidos de Windows).
5. Al terminar el escaneo, **el PDF entra solo en el lote** como un bloque más
   (punto 6), sin pasar por el diálogo de abrir archivo.
6. Extra opcional, para cuando escanee desde el móvil o le llegue un PDF de
   fuera: casilla **"Procesar automáticamente lo que llegue a esta carpeta"**
   (`QFileSystemWatcher` en `vigilante.py`, esperando a que el archivo deje de
   crecer antes de leerlo). Es barato de hacer y cubre esos dos casos.
- **Atajos de teclado**: `Ctrl+E` escanear, `Ctrl+O` abrir PDF, `Ctrl+G`
  exportar, `F5` reprocesar la fila seleccionada, `Supr` eliminar fila,
  `Ctrl+Z` deshacer eliminación.
- Sinergia con **Escaner-Fotos-Facturas** (ya existe `procesar_rutas` pensada
  para eso): que aquella app pueda mandar el PDF mejorado directamente a esta.

## 7. Cliente automático al escanear y gestión de los PDF — ✅ HECHO (2026-09-02)

Pedido por el usuario después de ver los puntos 1-6.

- **No hace falta decir de quién son las facturas al escanear.** Si se deja el
  cliente vacío, el PDF nace en `<carpeta>\Sin identificar\Escaneo_<tipo>_<fecha>.pdf`
  y, en cuanto el programa detecta al cliente por el NIF, `app._recolocar_escaneo`
  lo **muda solo** a `<CLIENTE>\<CLIENTE>_<gastos|ingresos>_<fecha>.pdf`. El tipo
  se decide por mayoría de lo detectado (si casi todo son ventas, se archiva como
  ingresos). Si no se detecta cliente, se queda donde está y se coloca a mano.
  Mover el archivo nunca puede costar el escaneo: si falla, se sigue con la ruta
  vieja.
- **`archivo.py` + `dialogo_escaneos.py`**: menú **Escaneos** (Ctrl+L) con la
  lista de PDF (cliente, fecha, archivo, tamaño), y botones para volver a
  meterlos en el lote, abrirlos, abrir su carpeta, cambiarlos de cliente o
  quitarlos. **Nada se borra**: lo quitado va a `_Papelera` dentro de la propia
  carpeta de escaneos. La fecha se lee del nombre, no del archivo, para que
  moverlo no la cambie.

## 3. Quitar el banner azul superior — ✅ HECHO (2026-09-01, sin publicar)

Fuera el `QFrame#cabecera` y sus estilos. El menú **Configuración** ya está, con
API key de Gemini, tope de gasto al mes, carpeta de escaneos y calidad (ppp).

- En `app.py._crear_interfaz`: eliminar el `QFrame#cabecera` (68 px, azul marino)
  con el logo, "Facturas a Aplifisa", el subtítulo y la píldora "Gastos e
  ingresos se clasifican automáticamente".
- Lo que no se puede perder se recoloca: **la versión ya está en el título de la
  ventana**; el aviso de clasificación automática ya está bajo "Datos extraídos".
- En `estilo.py` quedan sin uso `QFrame#cabecera`, `QLabel#marca`,
  `#marcaSubtitulo`, `#estadoCabecera`, `#pasoActivo`, `#pasoInactivo`:
  borrarlos también (ojo: `estadoCabecera` lo añadió Ricardo en la v1.4.0,
  comprobar con `grep` que no se usa en ningún otro sitio antes de quitarlo).
- **La barra de menú se queda como está** (azul marino): el usuario la quiere
  igual y además pide **añadir ahí lo útil de configuración**. Menú nuevo
  **Configuración** con: API key de Gemini, tope de gasto mensual (punto 1),
  carpeta de escaneos y escáner (punto 2), y carpeta por defecto de los Excel.

## 4. Resumen de importes por bloque escaneado — ✅ HECHO (2026-09-01, sin publicar)

Las tres etiquetas del resumen son ahora una tabla `Bloque · Tipo · Líneas ·
Base · IVA · Recargo · IRPF · Total factura`, con una línea por bloque y tipo y
la fila **TODOS LOS BLOQUES** en negrita cuando hay más de uno. Botón "Copiar
resumen" (al portapapeles, separado por tabuladores para pegarlo en Excel).
En recargo de equivalencia los gastos salen solo con el total, sin desglose.
`resumen.resumir_por_bloque()` hace la agrupación; `_eur` pasó a ser `eur`.

Mantener el resumen (base, IVA, recargo, IRPF, total) pero **como listado por
bloque**, para cuadrar cada PDF contra lo que suma el papel.

- `resumen.py`: ya tiene `Totales` y `resumir()`; añadir `resumir_por_bloque()`
  que agrupe por bloque (ver punto 6) y devuelva también el total general.
- UI: sustituir las tres etiquetas del resumen por una **tabla pequeña**:
  `Bloque (nombre del PDF) · Nº líneas · Base · IVA · Recargo · IRPF · Total`,
  con **fila de TOTAL GENERAL en negrita** y filas separadas de Gastos e
  Ingresos.
- Que se pueda **copiar al portapapeles** (`Ctrl+C`) para pegarlo donde haga
  falta al comprobar totales.
- El total se sigue calculando (`base + IVA + recargo − IRPF`), que es lo que se
  va a registrar en Aplifisa; el impreso ya lo controla `validacion.py`.
- Ya **no se filtra por trimestre** (punto 5): el resumen suma TODO lo que hay
  en la tabla, y desaparece la línea "⚠ N líneas fuera del trimestre".

## 5. Quitar el trimestre — ✅ HECHO (2026-09-01, sin publicar)

Fuera el selector de trimestre, `_periodo`, `_autoseleccionar_periodo`, el
parámetro `periodo` de `validar` y el aviso "FUERA DEL xT". `periodo_de` se ha
sustituido por `validacion.fecha_de()`, que solo sirve para avisar en ámbar de
una **fecha ilegible** (eso sí es mala lectura). De paso se ha borrado el método
muerto `app._exportar(tipo)` (no lo llamaba nadie y era todo trimestre).
Tests: `tests/test_periodo_resumen.py` → `tests/test_resumen.py`. 57 pasando.

Motivo del usuario: usa el programa para requerimientos y para trimestres
sueltos; marcar en ámbar lo "fuera de trimestre" **confunde más que ayuda**.

Quitar:

- `app.py`: el bloque "TRIMESTRE QUE SE TRABAJA" (`combo_trim`, `spin_anio`),
  `_periodo()`, `_autoseleccionar_periodo()` y las llamadas a ambos.
- `validacion.validar`: quitar el parámetro `periodo` y todo el aviso
  "FUERA DEL xT". **Se mantiene** el aviso ámbar de *fecha que no se entiende*
  (eso sí es un fallo de lectura real) y que la fecha vacía siga siendo error.
- `_exportar_todo`: quitar de la comprobación previa el "N líneas fuera del
  trimestre" (quedan duplicados y errores).
- `_pintar_resumen`: deja de separar dentro/fuera de periodo.
- `detectar_periodo`/`periodo_de`/`fmt_periodo`: `periodo_de` puede quedarse si
  se usa para ordenar por fecha; lo demás fuera.
- Tests: `tests/test_periodo_resumen.py` hay que reescribirlo (comprobará el
  resumen sin periodo). Repasar el resto por si pasan `periodo` a `validar`.

## 6. Trabajar por bloques (varios PDF → un solo Excel) — ✅ HECHO (2026-09-01, sin publicar)

`self._bloques` (lista de dict nombre/procesadas/cliente/nif) sustituye a
`_procesadas`; cada carga se AÑADE. Columna "Bloque" en la tabla, filtro por
bloque, botones "Quitar este bloque" y "Vaciar todo" (ambos preguntan), aviso
si un bloque parece de otro cliente y etiqueta "⚠ VARIOS CLIENTES en el lote".
Los nombres repetidos se numeran ("escaneo", "escaneo (2)"). 9 tests nuevos en
`tests/test_bloques.py`, incluido el duplicado ENTRE bloques (sale en rojo).

Caso real: un requerimiento son muchas facturas y el escáner saca PDF de 25-30
páginas; hacen falta varios PDF en el mismo Excel.

**Decidido:** al abrir un segundo PDF, **se añade al listado** (no sustituye).

- `VentanaPrincipal._procesadas` pasa de lista a lista de **bloques**:
  `[{"nombre": "escaneo1.pdf", "procesadas": [...]}, ...]`. `_rellenar_tabla()`
  recorre todos los bloques; cada fila guarda a qué bloque pertenece
  (`self.filas[r]["bloque"]`) — lo necesita el punto 4.
- Columna nueva **"Bloque"** en la tabla (o el nombre del PDF en la columna de
  origen), y filtro "Mostrar: solo bloque X".
- `procesar_rutas` deja de reiniciar: `_on_terminado` **añade** el bloque.
  Botón **"Vaciar todo"** (con confirmación) para empezar de cero.
- **Duplicados entre bloques**: `encontrar_duplicados` ya trabaja sobre toda la
  tabla, así que funcionará solo — hay que **comprobarlo con un test** de dos
  bloques con la misma factura (es el caso que de verdad protege aquí: al
  escanear en tacos es fácil colar una hoja dos veces).
- **Cliente**: se detecta por bloque. Si el segundo bloque da un NIF distinto al
  del primero, **avisar bien claro** ("estas facturas parecen de otro cliente")
  y dejar decidir; no mezclar clientes en silencio.
- La casilla de **recargo de equivalencia** es del cliente, se aplica a todos
  los bloques.
- Poder **eliminar un bloque entero** (se equivocó de PDF) sin borrar el resto.
- El export sigue siendo uno: `gastos.xlsx` + `ingresos.xlsx` con todo.

---

## Contestado por el usuario (2026-09-01)

- Menús de arriba: **se quedan**, solo fuera el banner azul grande. Y quiere que
  se les añada lo útil de configuración.
- Tope de gasto de Google: **5 €/mes**, confirmado.
- Escáner: el programa **tiene que escanear él**, no vigilar a la app de HP.

## Preguntas abiertas para el usuario

1. Siguen sin contestar las dudas del panel "Para mejorar el programa" (están
   en `config/pendientes.md`): si los pares tipo IVA→recargo son siempre
   21→5,2 / 10→1,4 / 4→0,5, qué hacer con una factura marcada "Copia
   duplicada", cuál es el CIF bueno cuando un proveedor imprime dos en la
   cabecera, y si un proveedor sin recargo va también por el total.

## Recordatorios técnicos

- Entorno: `.venv` con Python 3.11 (el `python` del sistema es un 3.7 viejo).
- **Nada de nombres/NIF de clientes reales en el código** — el repo es público.
- Publicar = subir `__version__` en `facturas_excel/__init__.py` + `git tag -a
  vX.Y.Z` + `git push origin vX.Y.Z`; el CI compila y publica el instalador.
- Al cerrar la sesión, actualizar `config/pendientes.md` con las dudas nuevas
  (es lo que ve el usuario dentro de la app).
