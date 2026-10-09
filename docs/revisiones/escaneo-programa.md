<!-- Investigación del 09/10/2026 (consulta del usuario: el escáner es el cuello de botella). Copiada de la sesión; cada informe va seguido de su verificación adversarial, que corrige al informe donde discrepan. -->

# Cómo escanea hoy el programa y qué se puede cambiar

# Escaneo en «Facturas a Aplifisa»: cómo funciona hoy y qué se puede cambiar en el programa

Leí el código y no he modificado el repositorio. Los datos del código llevan fichero:línea y los externos llevan URL. La web de NAPS2 (naps2.com) y las de HP y Coolblue no se pueden abrir desde aquí porque el proxy las bloquea. Por eso los argumentos de NAPS2 los comprobé en su código fuente en GitHub (rama master; no sé qué versión hay instalada en el equipo). Los datos de la HP vienen solo de resultados de búsqueda y van marcados como no confirmados.

## 1. Modelo de escáner y cómo se escanea

**Modelo que asume el código:** una HP LaserJet Pro M148. Lo dicen los comentarios en escaner.py:49, escaner.py:198 y escaner.py:262, y también CLAUDE.md:74-75. El código no dice qué variante es (M148dw o M148fdw).
- Datos externos, sin confirmar: la M148fdw tendría un alimentador de 35 hojas y escanearía a unas 15 páginas por minuto ([coolblue.be](https://www.coolblue.be/en/product/824505/hp-laserjet-pro-mfp-m148fdw.html)).
- Su hermana, la M149fdw, figura con «Duplex ADF scanning: No» ([hp.com M149fdw](https://hp.com/bd-en/products/printers/product-details/product-specifications/22954498)). Es probable que la M148 tampoco escanee a dos caras por el alimentador, pero no está confirmado.

**Por el alimentador se usa NAPS2.** El escaneo de Windows (WIA) con esta HP solo entrega la primera hoja del taco (escaner.py:71-75 y escaner.py:465-467). Los argumentos exactos (escaner.py:422-428) son:

`NAPS2.Console.exe --noprofile --driver wia --source feeder|duplex --dpi <N> --bitdepth color|gray|bw --pagesize a4 --deskew --force --verbose -o <destino.pdf> [--device <nombre WIA>]`

- NAPS2 entrega el PDF ya hecho y el programa lo comprueba con `verificar_pdf` (escaner.py:449).
- Las hojas escaneadas se cuentan leyendo la salida de NAPS2 (escaner.py:437-441).
- Hay un tope de 45 minutos (escaner.py:79 y escaner.py:442), pero no funciona: el bucle de lectura bloquea antes de llegar a la espera y nunca se mata el proceso. Ya está verificado en docs/revisiones/aplicacion.md:103-106.
- Dónde busca NAPS2: la clave `naps2_exe` de ajustes, el PATH, WindowsApps y Program Files (escaner.py:383-397). No vi ninguna pantalla para indicar esa ruta.
- En el código de NAPS2, el PDF se escribe solo cuando ha terminado todo el escaneo. Si el controlador da un error a mitad (un atasco), no se exporta nada ([AutomatedScanning.cs](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Automation/AutomatedScanning.cs), método Execute).

**Por el cristal se usa WIA:**
- Fija el modo cristal, el tipo de color y los ppp, y pide un área de A4 (escaner.py:258-281).
- Pide JPEG, BMP o PNG según lo que sepa dar el aparato (escaner.py:228-237) y lo convierte a JPEG de calidad 80 (escaner.py:240-255).
- Arma el PDF con PyMuPDF (escaner.py:348-362).
- **Una hoja por cada vez que se pulsa Escanear** (escaner.py:341-342).

**Valores por defecto y si se pueden cambiar:**

| Ajuste | Valor por defecto | Dónde | ¿Se puede cambiar? |
|---|---|---|---|
| Resolución | 200 ppp (`DPI_POR_DEFECTO`) | escaner.py:62 | Sí, en el diálogo: 75, 150, 200 o 300 (dialogo_escaneo.py:35-40) |
| Color en el diálogo | grises | dialogo_escaneo.py:80 | Sí: blanco y negro, grises o color (dialogo_escaneo.py:30-34) |
| Color en las funciones si falta el dato | color | escaner.py:307, 411 y 455; hilos.py:144 | — |
| Alimentador | activado | dialogo_escaneo.py:107 | Sí |
| Dos caras | desactivado | dialogo_escaneo.py:110 | Sí |

- Escáner, color, ppp, alimentador y dos caras se recuerdan para el siguiente escaneo (dialogo_escaneo.py:151-159).
- El tipo, el cliente y las hojas no se recuerdan.
- La carpeta de escaneos se puede cambiar (app.py:2101-2105).
- Gemini nunca ve los ppp del escaneo: cada página se vuelve a convertir a imagen a `lectura_ppp`, que por defecto es 150 (hilos.py:46-47; dialogo_calidad.py:20 y 49). **Escanear a 200 ppp no le da a Gemini ni un punto más que escanear a 150.** Esos 200 ppp solo sirven para el archivo y el visor.

## 2. Cuántos pasos hacen falta por cada taco

1. Pulsar Escanear o Ctrl+E (app.py:1403; cinta.py:101-103). Antes de abrir el diálogo, el programa pregunta cada vez a Windows qué escáneres hay (ventana_archivo.py:31).
2. Diálogo «Escanear facturas» (dialogo_escaneo.py:43-130), con ocho controles: escáner, cliente, tipo, color, calidad, hojas que pone, alimentador y dos caras.
   - **Tipo**: vuelve a «Gastos» cada vez (dialogo_escaneo.py:72-75). Un taco de ingresos cuesta uno o dos clics más.
   - **Cliente**: lo que se escriba no sirve para nada.
     - El PDF siempre se guarda en «Sin identificar» (ventana_archivo.py:47; archivo.py:35-41).
     - El campo solo cambia un indicador (ventana_archivo.py:51), y la cola lo vuelve a calcular a partir de la ruta (ventana_lectura.py:49 y 143).
     - El texto del diálogo promete «<CLIENTE>…» (dialogo_escaneo.py:115-120), lo cual confunde.
   - **Hojas que pone**: vuelve a 0 («no las he contado») cada vez (dialogo_escaneo.py:96-104).
3. Pulsar «Escanear».

Lo mínimo es **dos acciones** (Ctrl+E y Escanear) para un taco de gastos con los ajustes recordados. Un taco de ingresos son tres o cuatro. Si se quiere el control de hojas pegadas, además hay que teclear el número de hojas.

**Ventanas que pueden saltar después:**
- «Faltan hojas» (ventana_archivo.py:177-196). Sale **antes** de mandar el taco a la cola (ventana_archivo.py:173-175), así que la lectura no empieza hasta cerrarla.
- Al acabar cada bloque:
  - elegir cliente si hay empate o un nombre igual con otro NIF (ventana_lectura.py:269-271);
  - confirmar el NIF de un proveedor cuando tres o más facturas lo contradicen (ventana_lectura.py:342-353);
  - «¿Facturas de otro cliente?» (ventana_lectura.py:486-499);
  - «Páginas sin leer» (ventana_lectura.py:374-396);
  - el aviso de gasto de Gemini, una vez por sesión (ventana_lectura.py:501-507).

**Encadenar tacos:** no hay «escanear otro igual» ni modo continuo. El diálogo se cierra al aceptar y hay que volver a abrirlo; solo se reactiva el botón Escanear (ventana_archivo.py:171). Por el cristal, cada hoja suelta pide el diálogo completo y produce su propio PDF y bloque.

## 3. ¿Se solapan escaneo y lectura?

**Sí, el taco 2 se puede escanear mientras Gemini lee el taco 1.**
- `_escanear` solo se niega si hay otro escaneo en marcha (ventana_archivo.py:28-30).
- Al terminar, el taco va a la cola (ventana_lectura.py:104-118).
- Mientras hay lectura, el botón Abrir sigue desactivado hasta que la cola termina (ventana_archivo.py:53; ventana_lectura.py:125), pero Ctrl+O y arrastrar siguen funcionando (app.py:1404 y 1951-1955).

**La cola:**
- Va bloque a bloque, con un solo lector a la vez (ventana_lectura.py:121-153).
- Dentro de cada bloque se leen 10 hojas a la vez (`HILOS`, ajustable de 1 a 20 con `hilos_lectura`; hilos.py:13-21 y 92-99).
- Los PDF de más de 25 páginas se parten en trozos de 25 (pdf.py:23 y 88-125).
- Todas las páginas se convierten a imagen antes de la primera llamada a Gemini (hilos.py:46-47).

**Lo que frena:**
1. Solo puede haber un escaneo a la vez (ventana_archivo.py:28-30).
2. NAPS2 solo entrega el PDF al final, así que el taco no se empieza a leer hasta que ha pasado entero.
3. Si NAPS2 se cuelga, el tope de tiempo no actúa y no hay botón de cancelar. No se puede volver a escanear hasta reiniciar el programa.
4. Las ventanas que saltan al acabar cada bloque paran la cola hasta que alguien las contesta: la cola solo sigue en ventana_lectura.py:288, después de todas ellas.
5. Al meter un taco en la cola se copia el PDF entero y se parte dentro del hilo de la ventana (ventana_lectura.py:59 y 69). Ya está medido: 2,8 s y 1,6 s con un PDF de 276 MB (docs/revisiones/aplicacion.md:110-111).

**Fallos cuando se solapan.** Los deduzco leyendo el código; no los he reproducido. El tipo y los indicadores del escaneo se guardan en variables compartidas de la ventana (ventana_archivo.py:48-51; ventana_lectura.py:141-143 y 253-257):
- **Tipo equivocado en el taco que se está leyendo.** Si el taco 1 (gastos) se está leyendo y se escanea el taco 2 como ingresos, el bloque 1 se guarda con el tipo «ingresos» (ventana_lectura.py:253). Entonces todas sus facturas de gasto salen en ámbar con «Dijo que este taco era de INGRESOS…» (ventana_validacion.py:402-409 y 125-127).
- **Tipo equivocado en el taco nuevo.** Si en la cola hay una segunda parte del taco 1, al empezar a leerla se pone otra vez «gastos» en la variable (ventana_lectura.py:141). El taco 2 se mete en la cola con ese tipo equivocado (ventana_lectura.py:85 y 96).
- **PDF que se queda sin archivar.** Si el escaneo 2 falla, se ponen a falso los indicadores (ventana_archivo.py:203-204). Con eso, el PDF del taco 1 ya no se mueve a la carpeta del cliente: se queda en «Sin identificar» (ventana_archivo.py:218-220).

## 4. ¿Hace falta un taco por cliente?

**En la práctica sí: un lote es un solo cliente.**
- Cada bloque elige un cliente (hilos.py:110-111) y se analiza el lote entero (ventana_lectura.py:416-419).
- «Cambiar cliente» rehace todos los bloques con el mismo cliente (ventana_lectura.py:454-467).
- Exportar y archivar usan un único cliente (ventana_archivo.py:267-270).
- Un bloque de otro cliente solo da el aviso de la sección 2 (ventana_lectura.py:486-499).
- «Vaciar todo» también borra la cola (app.py:2232).
- Así que el escáner espera mientras se revisa y se exporta un cliente antes de pasar al siguiente.

**Si un taco va mezclado:**
- Gana la parte que más se repite (procesar.py:102-165).
- Las hojas del otro cliente no coinciden en NIF. Se comparan por nombre y acaban como «Rol emisor/destinatario dudoso» y gasto por defecto (procesar.py:344-347).
- La segunda y siguientes partes de un PDF largo **heredan el cliente de la primera** (ventana_lectura.py:174-181).

**¿Podría el programa separarlo solo?** Los datos ya existen:
- Gemini lee el NIF del emisor y del receptor de cada hoja.
- Hay una lista de clientes conocidos (recoger.py:70-85).
- Ya existe una función que asigna un documento a un cliente (`identificar_por_datos`, recoger.py:141-173).
- Rehacer la clasificación no vuelve a pagar a Gemini (ventana_lectura.py:454-467).

**Lo que lo impide hoy:**
1. El modelo de un lote por cliente, en la interfaz, la sesión, la exportación y el archivo (ventana_archivo.py:210-256).
2. Los tiques sin NIF del cliente, que se marcan en procesar.py:402-405, no se pueden asignar a nadie.
3. Facturas entre dos clientes de la asesoría (recoger.py:155-160).
4. Clientes nuevos que todavía no están en la lista.
5. Unir hojas consecutivas de una misma factura (procesar.py:1084-1109) en la frontera entre dos clientes.
6. El PDF del taco se archiva entero para un solo cliente.

## 5. Dos caras, hojas en blanco, hojas pegadas, atascos y tope de páginas

- **Dos caras:** la casilla manda `--source duplex` a NAPS2 (escaner.py:423). Por WIA está el indicador `DUPLEX` (escaner.py:268), pero en la práctica el alimentador siempre va por NAPS2. Que la M148 escanee a dos caras por el alimentador no está confirmado (ver sección 1).
- **Hojas en blanco:** ni el programa ni NAPS2 las quitan.
  - En el código no hay ningún filtro.
  - Con `--noprofile` se usa un perfil nuevo y la opción `ExcludeBlankPages` queda desactivada. No existe un argumento para activarla; solo se puede con un perfil guardado y `--profile` ([AutomatedScanningOptions.cs](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Automation/AutomatedScanningOptions.cs), [ScanProfile.cs](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Scan/ScanProfile.cs), [ScanOptions.cs](https://github.com/cyanfish/naps2/blob/master/NAPS2.Sdk/Scan/ScanOptions.cs)).
  - Cada dorso en blanco se manda a Gemini y se paga (hilos.py:65-99).
  - No sé qué devuelve Gemini con una hoja en blanco. Las reglas para unir hojas no lo impiden (procesar.py:952-982), así que podría pegarse a la factura anterior, pero no está confirmado.
- **Hojas pegadas (dos hojas arrastradas a la vez):** el programa no tiene forma de detectarlo. Solo hay dos avisos:
  - comparar las páginas con «Hojas que pone», que por defecto está a 0 y entonces no compara (ventana_archivo.py:177-196);
  - los saltos en la numeración de las facturas (validacion.py:505-545).
- **Atascos:**
  - Por NAPS2, un error a mitad hace que no se guarde nada. El programa avisa con las últimas 400 letras de la salida de NAPS2 (escaner.py:444-448) y no mete nada en la cola (ventana_archivo.py:198-206). Hay que repetir el taco entero.
  - Por WIA, se pierden las hojas ya escaneadas porque se borra la carpeta temporal (escaner.py:326-329 y 475-478).
- **Tope de páginas:**
  - `MAX_PAGINAS = 200` solo actúa en el bucle de WIA, y por el cristal ya se corta en la primera hoja (escaner.py:64, 319 y 341-342). Para NAPS2 no hay tope.
  - El campo «Hojas que pone» admite de 0 a 500 (dialogo_escaneo.py:97).
  - Para leer, los PDF se parten en trozos de 25 páginas (pdf.py:23).
  - El tope físico serían las 35 hojas del alimentador (no confirmado).

## 6. Vías de entrada sin escáner

- **Abrir (Ctrl+O):** pdf, png, jpg, jpeg, tif, tiff y bmp (ventana_lectura.py:34-39).
- **Arrastrar sobre la ventana:** las mismas extensiones (ventana_comun.py:61 y 173-184; app.py:1945-1955).
- **HEIC: no se acepta.** No está en esas listas (ventana_comun.py:61; pdf.py:19) ni en requirements.txt. Pillow necesita el complemento pillow-heif para abrirlo ([pypi pillow-heif](https://pypi.org/project/pillow-heif/)). HEIF es el formato por defecto de las fotos de iPhone y iPad ([Apple](https://support.apple.com/116944)).
- **TIFF de varias páginas: solo se lee la primera.** Lo he comprobado: con un TIFF de 3 páginas, `cargar_imagenes` devuelve 1 (pdf.py:136-138).
- **`--import`:** `FacturasAplifisa.exe --import ruta…` (app.py:3096-3100) llama a `procesar_rutas` a los 200 ms de arrancar (app.py:3145-3146). Está documentado para «Escáner Fotos» (README.md:16-17). No hay control de una sola copia del programa: cada `--import` abre otra copia, que comparte sesión y base de datos (docs/revisiones/aplicacion.md:68-71).
- **Recoger sueltos:**
  - Se lanza a mano desde el menú (app.py:1420-1421).
  - Busca solo PDF y Excel en el Escritorio y Descargas, también los de OneDrive, hasta dos niveles de subcarpetas (recoger.py:41, 52-67 y 238-260).
  - Solo **archiva** en la carpeta del cliente: no mete nada en el lote (ventana_archivo.py:75-111). Las imágenes las ignora.
- **«Escaneos guardados» (Ctrl+L):** permite volver a meter en el lote a mano un PDF que ya está en el archivo (ventana_archivo.py:162-167).
- **Carpeta vigilada: no existe.** No hay QFileSystemWatcher ni nada que revise una carpeta periódicamente. Figura como «pendiente de valorar» en config/pendientes.md:441-443.
- No sé si la M148 puede escanear directamente a una carpeta de red desde su panel; la búsqueda no lo confirmó para este modelo.

## 7. Cambios en el programa que reducirían el cuello de botella

Ninguna cifra de ahorro está medida: el programa no apunta cuánto tarda cada taco. Por eso el primer cambio de la lista es medir.

| # | Qué cambiar | Ficheros | Beneficio | Esfuerzo | Riesgo |
|---|---|---|---|---|---|
| 0 | Apuntar los tiempos de cada taco: inicio y fin del escaneo, páginas, salida de NAPS2 y segundos de lectura por bloque | escaner.py:410-450, hilos.py:43-114, errores.py | Saber con datos si el escáner es de verdad el cuello de botella y comprobar el efecto de cada cambio | Pequeño | Nulo |
| 1 | «Otro taco igual»: tras cada escaneo, un aviso sin ventana con «Escanear otro (Intro)» con los mismos ajustes. Recordar el tipo. Quitar el campo Cliente, o usarlo como cliente confirmado | ventana_archivo.py:27-62 y 169-175; dialogo_escaneo.py:60-75 y 151-159; cinta.py:101-103 | Una pulsación por taco en vez de dos a cuatro más el diálogo; el escáner espera menos | Pequeño | Bajo: un tipo equivocado solo genera avisos |
| 1b | Opcional: arrancar solo cuando se cargan hojas en el alimentador (ya existe la comprobación de papel listo) | escaner.py:29 y 284-292 | Se reduce a poner el papel | Medio | No confirmado que la M148 avise de que hay papel; riesgo de escaneos sin querer |
| 2 | Llevar el tipo y los indicadores de cada escaneo dentro de sus opciones, no en variables de la ventana | ventana_archivo.py:48-51 y 169-206; ventana_lectura.py:85, 96, 141-143 y 253-257 | Arregla los tres fallos de la sección 3; hace falta para escanear con tranquilidad mientras se lee | Pequeño | Bajo |
| 3 | Cambiar las ventanas de fin de bloque y la de «Faltan hojas» por avisos en la banda, y meter el taco en la cola primero | ventana_archivo.py:173-196; ventana_lectura.py:258-288, 374-396 y 486-507 | La cola no se para esperando un clic | Medio | Medio: decisiones aplazadas; se mitiga porque rehacer no vuelve a pagar a Gemini |
| 4 | NAPS2 a prueba de cuelgues: leer su salida en otro hilo, tiempo máximo sin hojas nuevas, matar el proceso y botón «Cancelar escaneo». Decir claro que tras un atasco hay que repetir el taco entero | escaner.py:410-450, hilos.py:126-149, ventana_archivo.py | Un cuelgue no deja el escáner bloqueado hasta reiniciar | Pequeño | Bajo |
| 5 | Resolución por defecto igual a `lectura_ppp` (150) y que vaya ligada a ella | escaner.py:62; dialogo_escaneo.py:35-40 y 89-90 | Menos datos y PDF más ligero sin perder nada para Gemini. No está confirmado que la HP escanee más rápido a 150 que a 200: medirlo con el cambio 0 | Pequeño | Bajo: el archivo queda algo menos nítido |
| 6 | Hojas en blanco: medir la tinta de cada página antes de mandarla a Gemini, o usar un perfil de NAPS2 con `ExcludeBlankPages` en vez de `--noprofile` | pdf.py:128-139, hilos.py:46-99, escaner.py:422 | No se pagan dorsos en blanco ni salen filas en ámbar; permitiría escanear siempre a dos caras si la máquina puede (no confirmado) | Pequeño-medio | Medio: descartar una hoja casi vacía con contenido. Dejarla en el PDF y saltarse solo la lectura |
| 7 | Cristal con varias hojas por PDF: «Añadir otra hoja / Terminar» | escaner.py:305-345 y 453-478; ventana_archivo.py | Los tiques que no entran por el alimentador ya no piden el diálogo hoja a hoja | Pequeño-medio | Bajo |
| 8 | Carpeta vigilada: comprobar que el archivo ha terminado de escribirse (tamaño estable), no repetir copias ya archivadas (comparando su huella, `identidad_archivo.huella`) y apartar lo ya procesado | Módulo nuevo; app.py (arranque); ventana_lectura.py:41-119 | Entrada sin intervención para el escaneo a carpeta de la impresora (no confirmado en la M148), el móvil o Escáner Fotos. Permite otro aparato en paralelo | Medio | Medio: gasto de Gemini sin que nadie lo vea (pedir confirmación o poner un tope diario) y archivos a medio escribir |
| 9 | Una sola copia del programa, y que `--import` se pase a la copia ya abierta | app.py:3096-3147 | Escáner Fotos no abre otra copia que pisa la sesión | Pequeño-medio | Bajo |
| 10 | Aceptar HEIC/HEIF con pillow-heif y leer todas las páginas de un TIFF | pdf.py:19 y 128-139; ventana_comun.py:61; ventana_lectura.py:37; requirements.txt | Fotos de iPhone sin convertir y TIFF completos | Pequeño | Bajo |
| 11 | Copiar el original y partir el PDF fuera del hilo de la ventana | ventana_lectura.py:59-69; app.py:1679-1684 | La ventana no se congela al meter tacos grandes | Pequeño-medio | Bajo |
| 12 | Bandeja por cliente: leer en segundo plano los tacos de otros clientes y guardar cada uno en su propia sesión, sin mezclarlos con el lote abierto | ventana_lectura.py (cola y `_on_terminado`), app.py:2217-2250, sesion.py, ventana_archivo.py:210-256 | El mayor: el escáner pasa todos los clientes seguidos y la revisión se hace después | Grande | Medio-alto: sesión, archivo y exportación están pensados para un solo cliente |
| 13 | Hojas separadoras entre clientes: `--splitpatcht` de NAPS2, o una hoja impresa con el NIF que lea Gemini o un código QR | escaner.py:422-428 más lo del cambio 12 | Varios clientes en una sola pasada por el alimentador | Medio, sobre el 12 | Medio: no confirmado que la HP con WIA detecte Patch-T; si no se ve un separador, se mezclan clientes |
| 14 | Separar automáticamente por NIF un taco mezclado, reutilizando `identificar_por_datos` | procesar.py:102-165, recoger.py:70-173, ventana_lectura.py:174-181 | Ya no habría que ordenar los tacos por cliente | Grande | Alto: tiques sin NIF y facturas entre dos clientes. Mejor solo como propuesta o junto con los separadores |

**Orden recomendado:** 0, 2, 1, 4 y 3, que son baratos y quitan la espera entre tacos. Después 5, 6 y 10. Luego 8 y 9. Y finalmente 12 con 13 si se quiere escanear todo sin parar a revisar.

## Verificación

# Verificación del informe «Escaneo en Facturas a Aplifisa»

He leído el repositorio sin modificarlo; `git status` sigue limpio. Hice dos pruebas, las dos en el scratchpad y usando el `.venv` del repo.

**Límites de lo que pude comprobar:**
- WebFetch y curl no llegan a hp.com, support.hp.com, coolblue, icecat ni bhphotovideo (fallan DNS y proxy). Los datos de HP vienen de los extractos de WebSearch y los marco como «según el extracto del buscador».
- NAPS2 lo leí en su código fuente: rama master (commit 9314194, del 3-10-2026) y la última versión publicada, v8.4.1.
- El informe no contiene fechas legales, así que no había nada que verificar en ese apartado.

## A. Datos externos

| Afirmación | Veredicto | Dato y fuente |
|---|---|---|
| La M148fdw tiene alimentador de 35 hojas y escanea a unas 15 ppm | **Confirmada** (extracto, página no abierta) | Ficha de HP: «up to 15 ppm», alimentador de 35 hojas. [support.hp.com c06165580](https://support.hp.com/ro-en/document/c06165580), [hoja de datos HP c07874033](https://www8.hp.com/h20195/V2/GetPDF.aspx/c07874033) |
| «Probable que la M148 no escanee a dos caras por el alimentador, no confirmado» | **Corregida: confirmado que no** (extracto) | HP pone «Duplex ADF scanning: No» en la M148fdw ([c06165580](https://support.hp.com/ro-en/document/c06165580)) y en la M148dw ([hoja de datos de la serie M148](https://cc.cnetcontent.com/vcs/hp/inline-content/2Q/F/8/5/7/3/F857370BD9579E1CA66D2726203B64E849B72ECA_source.PDF)) |
| «El tope físico serían las 35 hojas (no confirmado)» | **Confirmada** (extracto) | Las mismas fuentes. La M148dw también tiene alimentador de 35 hojas ([printerland M148dw](https://www.printerland.co.uk/product/hp-laserjet-pro-mfp-m148dw/144354)), así que tener alimentador no indica cuál de las dos es |
| «No sé si la M148 puede escanear a una carpeta de red» | **Corregida en parte** (extracto, no confirmado del todo) | La guía M148-M149 dice «Scan to a network folder (touchscreen models only)». Eso apunta a que sí en la M148fdw (pantalla táctil) y no en la M148dw (pantalla de iconos). [Guía M148-M149](https://www.bhphotovideo.com/lit_files/608228.pdf), [manua.ls](https://www.manua.ls/hp/laserjet-pro-mfp-m148fdw/manual?p=102) |
| Si el modelo existe o está descatalogado (el informe no lo dice) | **Dato a añadir** (extracto) | La tienda de HP en EE. UU. marca la M148fdw como «Discontinued» ([hp.com](https://www.hp.com/us-en/shop/pdp/hp-laserjet-pro-mfp-m148fdw)) |
| Argumentos de NAPS2 (`--noprofile`, `--driver`, `--source`, `--dpi`, `--bitdepth`, `--pagesize`, `--deskew`, `--force`, `--verbose`, `-o`, `--device`) | **Confirmada** | [AutomatedScanningOptions.cs](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Automation/AutomatedScanningOptions.cs) |
| El PDF se escribe solo cuando ha terminado todo el escaneo | **Confirmada** | Primero escanea y después exporta: [AutomatedScanning.cs:142 y 151](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Automation/AutomatedScanning.cs#L142) |
| **«Si hay un error a mitad (atasco), no se exporta nada»** | **Corregida (refutada)** | Ver el detalle debajo de esta tabla |
| `ExcludeBlankPages` está desactivado con `--noprofile` y no hay argumento para activarlo | **Confirmada** | Vale para master y para v8.4.1. [ScanProfile.cs:112](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Scan/ScanProfile.cs#L112), [ScanOptions.cs:106](https://github.com/cyanfish/naps2/blob/master/NAPS2.Sdk/Scan/ScanOptions.cs#L106) |
| `--splitpatcht` existe | **Confirmada** | [AutomatedScanningOptions.cs:134](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Automation/AutomatedScanningOptions.cs#L134) |
| Riesgo «no confirmado que la HP con WIA detecte Patch-T» | **Corregida** | La HP no tiene que detectar nada. NAPS2 busca el código de barras en la imagen ya escaneada, por software (ZXing, formato Code 39): [BarcodeDetector.cs:13-33](https://github.com/cyanfish/naps2/blob/master/NAPS2.Sdk/Scan/BarcodeDetector.cs#L13). El problema real es otro: al partir, NAPS2 numera los ficheros (X1.pdf, X2.pdf…; [AutomatedScanning.cs:700](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Automation/AutomatedScanning.cs#L700), [Placeholders.cs:133](https://github.com/cyanfish/naps2/blob/master/NAPS2.Sdk/ImportExport/Placeholders.cs#L133)), así que el fichero `destino` no existe y escaner.py:444 lo daría por fallido |
| Pillow necesita pillow-heif para abrir HEIC | **Confirmada** | Pillow 12.3.0 es la última en PyPI y en el venv no tiene ninguna extensión «hei» registrada (lo probé). pillow-heif 1.8.0 está en [PyPI](https://pypi.org/project/pillow-heif/) |
| HEIF es el formato por defecto del iPhone | **Confirmada en lo esencial; lo de «por defecto» no está literal** | El extracto de [Apple 116944](https://support.apple.com/116944) explica «High Efficiency» frente a «Most Compatible» (JPEG), pero no dice «default» con esas palabras |

**Detalle del atasco a mitad (la refutación de la tabla):**
1. `ScanPerformer` pone `controller.PropagateErrors = false` ([ScanPerformer.cs:128](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Scan/ScanPerformer.cs#L128); igual en v8.4.1).
2. Con eso, las hojas ya escaneadas se entregan y el error solo se muestra en pantalla ([ScanController.cs:138-141 y 230-236](https://github.com/cyanfish/naps2/blob/master/NAPS2.Sdk/Scan/ScanController.cs#L138)).
3. Después se exporta el PDF parcial con esas hojas, y NAPS2 sale con código 1 ([ConsoleEntryPoint.cs:59](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/EntryPoints/ConsoleEntryPoint.cs#L59)).
4. Resultado en el programa: escaner.py:444 lo trata como fallo, ventana_archivo.py:198-206 no lo mete en la cola, y el PDF parcial se queda en «Sin identificar». No hay que repetir el taco entero.

**Consecuencia nueva para la casilla «Dos caras»:** manda `--source duplex`. Si el controlador WIA de la HP dice que no admite dúplex, NAPS2 lanza `NoDuplexSupportException` y aborta sin ninguna hoja ([WiaScanDriver.cs:257-259](https://github.com/cyanfish/naps2/blob/master/NAPS2.Sdk/Scan/Internal/Wia/WiaScanDriver.cs#L257)). No lo he reproducido con la HP.

## B. Código (fichero:línea)

**Confirmadas: la línea citada dice lo que afirma el informe.**
- **escaner.py:** 62, 64, 71-75, 79, 198 (con el matiz de la lista de abajo), 228-237, 240-255, 258-281, 284-292, 307, 319, 341-342, 348-362, 383-397, 411, 422-428, 437-441, 442, 444-448, 449, 455, 465-467.
- **dialogo_escaneo.py:** 30-40, 43-130 (ocho controles), 72-75, 80, 96-104, 107, 110, 115-120, 151-159.
- **ventana_archivo.py:** 28-31, 47-51, 162-167, 171, 173-196, 198-206, 210-256, 267-270.
- **archivo.py:** 35-41.
- **ventana_lectura.py:** 34-39, 49, 59, 69, 85, 96, 104-153, 174-181, 253-257, 269-271, 288, 342-353, 374-396, 416-419, 454-467, 486-507.
- **hilos.py:** 13-21, 46-47, 65-99, 92-99, 110-111, 144.
- **pdf.py:** 19, 23, 88-125, 136-138.
- **dialogo_calidad.py:** 20 y 49.
- **app.py:** 1403-1406, 1420-1421, 1945-1955, 2101-2105, 2232, 3096-3100, 3145-3146.
- **ventana_comun.py:** 61 y 173-184.
- **recoger.py:** 41, 70-85, 141-173, 155-160.
- **procesar.py:** 344-347, 402-405, 1084-1109.
- **validacion.py:** 505-545.
- **ventana_validacion.py:** 125-127 y 402-409.
- **Documentos:** README.md:16-17, CLAUDE.md:74-75, docs/revisiones/aplicacion.md:68-71, 103-106 y 110-111, config/pendientes.md:441-443.
- **TIFF de 3 páginas:** lo reproduje y `cargar_imagenes` devuelve 1.
- **Los tres fallos al solapar** (tipo en el bloque que se lee, tipo en el taco nuevo y PDF sin archivar): la cadena de llamadas se confirma leyendo el código. No los he reproducido.

**Corregidas o con matiz:**
1. **Comentarios sobre el modelo.** El comentario que nombra la M148 está en escaner.py:48, no en la 49. escaner.py:198 y CLAUDE.md:74-75 dicen «la HP» / «esta HP», sin modelo. Donde sí aparece M148 es en escaner.py:48 y 262 y en tests/test_escaner.py:193 y 228.
2. **«WIA con esta HP solo entrega la primera hoja».** Lo que falla es el bucle propio del programa con la librería de automatización de WIA (`item.Transfer`, escaner.py:319-342). NAPS2 también usa WIA (`--driver wia`) y sí saca el taco entero.
3. **«Gana la parte que más se repite» (procesar.py:102-165).** Gana la que tiene más puntos: +1000 si es cliente confirmado, −500 si es proveedor conocido, más el número de apariciones (procesar.py:72-77 y 161-165). Si hay empate, se pregunta.
4. **«Mientras hay lectura, el botón Abrir sigue desactivado».** Solo se desactiva al empezar un escaneo (ventana_archivo.py:53). Vuelve al acabar la cola (ventana_lectura.py:125) o si el escaneo falla (ventana_archivo.py:202). Una lectura lanzada con Abrir o arrastrando no lo desactiva: procesar_rutas no lo toca (ventana_lectura.py:41-119).
5. **«Las ventanas de fin de bloque paran la cola».** Es cierto para las que salen dentro de `_on_terminado`. **No es cierto para el aviso de gasto de Gemini.** Esa señal se emite antes que `terminado` (hilos.py:104→123, antes de la 112). Mientras el aviso está abierto, Qt sigue atendiendo señales y ejecuta `_on_terminado` hasta la línea 288. Lo comprobé con PySide6 del venv: «terminado» se ejecuta antes de cerrar el aviso.
6. **Reentrada, un fallo nuevo** (deducido del código; el comportamiento de Qt sí está comprobado):
   - Mientras está abierta una ventana de `_on_terminado` (ventana_lectura.py:258-285), puede acabar un escaneo.
   - Entonces `_on_escaneo_hecho` → `procesar_rutas` ve que el lector ya terminó y arranca otro (ventana_lectura.py:104-119).
   - Al cerrar la ventana, la línea 288 vuelve a llamar a `_iniciar_siguiente_cola`. Si la cola está vacía, pone `_elemento_cola_actual=None` y «Cola terminada» con un lector todavía en marcha. Si el taco nuevo tenía dos partes, quedan dos lectores a la vez.
   - Además, ventana_lectura.py:285 enseña los fallos del lector nuevo, no los del que terminó.
7. **Efectos que añadir a los fallos al solapar:**
   - Al fallo 1: también le pasa a un bloque que se abrió (no escaneado), porque ventana_archivo.py:49 pone `_escaneo_reciente=True`.
   - Al fallo 3: el bloque 1 pierde además su `tipo_declarado` (ventana_lectura.py:253-254).
8. **Hojas en blanco: «Las reglas para unir hojas no lo impiden (procesar.py:952-982)».** En la mayoría de los casos sí lo impiden. Si la hoja anterior es «unica» o «final», no se une (procesar.py:983-984). Si no, hace falta `_continuacion_sin_numero` (989-991 y 912-932). Una hoja en blanco solo se uniría si Gemini la marca «intermedia» o «final» y la anterior era «inicio» o «intermedia». El esquema obliga a elegir uno de los cuatro estados (extraccion.py:354-355 y 374).
9. **«Por WIA se pierden las hojas ya escaneadas».** En la práctica no aplica. WIA solo se usa para el cristal (escaner.py:465-467) y por el cristal se para en la primera hoja (341-342). Lo más que se pierde es esa hoja.
10. **Recoger sueltos.** De OneDrive solo mira el Escritorio, no Descargas (recoger.py:56-59). De Excel solo coge los que se llaman `GASTOS_…xlsx` o `INGRESOS_…xlsx` (recoger.py:48 y 258).
11. **«Gemini no gana nada escaneando a 200».** Es verdad si `lectura_ppp` está en 150, que es el valor por defecto. Pero se puede subir a 200 o 300 (dialogo_calidad.py:23-32), y entonces los ppp del escaneo sí cuentan.
12. **«Faltan hojas» (ventana_archivo.py:177-196).** Si las dos caras funcionaran, las páginas serían el doble que las hojas. La comparación `leidas >= puestas` taparía entonces una hoja que falta.
13. **Cambio 1b:** `_hay_papel` solo se usa en el camino de WIA (escaner.py:313). Con NAPS2 nadie mira si hay papel.
14. **Fuera del informe:** el aviso de alimentador vacío nunca sale con NAPS2. La expresión de escaner.py:445 no coincide con sus mensajes, ni con «No pages are in the feeder.» ni con «Sin hojas en el alimentador.» ([SdkResources.resx:150-151](https://github.com/cyanfish/naps2/blob/master/NAPS2.Sdk/Lang/Resources/SdkResources.resx), [SdkResources.es.resx:45-46](https://github.com/cyanfish/naps2/blob/master/NAPS2.Sdk/Lang/Resources/SdkResources.es.resx)). El usuario ve el error genérico.
15. **Sin medir:** cada taco abre un NAPS2 nuevo, que vuelve a buscar el aparato por nombre ([AutomatedScanning.cs:842](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Automation/AutomatedScanning.cs#L842)), además de la búsqueda de ventana_archivo.py:31. Conviene incluirlo en el cambio 0.

## C. Correcciones que hay que aplicar al informe

1. **Sección 1:** citar escaner.py:48 (no 49). Decir que escaner.py:198 y CLAUDE.md:74-75 no nombran el modelo.
2. **Sección 1, datos de la HP:** el alimentador de 35 hojas, las 15 ppm y el «no escanea a dos caras» pasan de «no confirmado» a confirmados según la ficha de HP (extracto, página no abierta). Añadir que la M148dw también tiene alimentador de 35 hojas y que HP EE. UU. marca la M148fdw como descatalogada.
3. **Sección 1, NAPS2:** sustituir «si el controlador da un error a mitad, no se exporta nada». En master y en v8.4.1, NAPS2 guarda las hojas anteriores al atasco y sale con código 1. El programa lo trata como fallo, no lo mete en la cola y deja el PDF parcial en «Sin identificar».
4. **Sección 1, WIA:** precisar que lo que pierde hojas es el bucle propio del programa con `item.Transfer` (escaner.py:319-342). NAPS2 también usa WIA y saca el taco entero.
5. **Sección 2, ventanas:** el aviso de gasto de Gemini no para la cola. Añadir el fallo de reentrada (punto B6).
6. **Sección 3:** precisar cuándo se desactiva el botón Abrir (ventana_archivo.py:53, ventana_archivo.py:202 y ventana_lectura.py:125). En «Fallos cuando se solapan», añadir la reentrada y los dos efectos extra del punto B7.
7. **Sección 4:** cambiar «gana la parte que más se repite» por la regla de puntos (procesar.py:72-77 y 161-165).
8. **Sección 5, dos caras:** la M148 no escanea a dos caras por el alimentador (HP). La casilla probablemente hace fallar el escaneo con `NoDuplexSupportException` (WiaScanDriver.cs:257-259; no reproducido).
9. **Sección 5, hojas en blanco:** las reglas de unión sí lo impiden salvo que Gemini marque la hoja en blanco como «intermedia» o «final» (procesar.py:983-991 y 912-932; extraccion.py:354-355 y 374).
10. **Sección 5, atascos:** por NAPS2 no se pierde todo; corregir según el punto 3. Por WIA, la pérdida de hojas no aplica en la práctica (solo el cristal, una hoja).
11. **Sección 5:** la capacidad física de 35 hojas pasa a confirmada (extracto).
12. **Sección 6, Recoger:** de OneDrive solo el Escritorio; de Excel solo `GASTOS_` / `INGRESOS_`.
13. **Sección 6, escanear a carpeta:** probable en la M148fdw (pantalla táctil) y no en la M148dw, según la guía M148-M149 (extracto, no confirmado del todo).
14. **Sección 1, frase de los 200 ppp:** añadir «con `lectura_ppp` a 150».
15. **Cambio 1b:** `_hay_papel` hoy solo se usa con WIA (escaner.py:313).
16. **Cambio 4:**
    - Quitar «tras un atasco hay que repetir el taco entero».
    - Proponer que si el código es 1 y el PDF existe, se trate como parcial: avisar, meterlo en la cola y escanear solo las hojas que faltan.
    - Arreglar también la detección de alimentador vacío (escaner.py:445).
17. **Cambio 6:** quitar «permitiría escanear siempre a dos caras». Proponer ocultar la casilla «Dos caras» o sustituirla por dos pasadas a mano (`-n 2 --waitscan --altinterleave` de NAPS2, [AutomatedScanningOptions.cs:39, 45 y 112](https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Automation/AutomatedScanningOptions.cs#L39); no probado).
18. **Cambio 13:**
    - El riesgo no es que la HP detecte Patch-T: lo detecta NAPS2 por software (BarcodeDetector.cs).
    - Añadir que NAPS2 numera los ficheros de salida, así que hay que cambiar escaner.py:444-449 para recoger varios PDF. Sube el esfuerzo.
19. **Cambio 3:** añadir que no se empiece a leer otro taco mientras hay una ventana abierta al acabar un bloque, para evitar la reentrada.
20. **Cambio 0:** medir también cuánto tarda NAPS2 en arrancar y encontrar el aparato en cada taco.

Las pruebas y el código de NAPS2 están en `/tmp/claude-0/-home-user-Notas-Asesoria-app/80eee95a-129e-573c-8981-869185147349/scratchpad/` (`tiff/`, `nested.py`, `naps2/`, `naps2git/`).

# Nitidez, fiabilidad e integración de un escáner nuevo

**Conclusión: la falta de nitidez viene sobre todo de cómo el programa usa la HP, no de la máquina.** La HP M148 puede escanear a 300 ppp ópticos por el alimentador, pero el programa escanea a 200 ppp, guarda en JPEG de calidad 75 y luego baja la imagen a 150 ppp y la vuelve a comprimir antes de mandarla a Gemini. Eso se arregla sin comprar nada. Donde la máquina sí se queda corta es en **tiques, doble cara y hojas arrastradas de dos en dos**, y eso es lo que justificaría un escáner de documentos.

**Limitación de las fuentes:** WebFetch no resolvía hp.com, ai.google.dev ni las webs de los fabricantes. Los datos de HP, Google y escáneres salen de los extractos del buscador sobre esas URL, no de abrir la página. El código fuente de NAPS2 sí lo leí directamente en GitHub. Las cifras que no pude confirmar van marcadas como «sin confirmar».

## 1. Qué hace el programa con la imagen

**Ajustes de escaneo**
- **Resolución por defecto:** `DPI_POR_DEFECTO = 200` (`facturas_excel/escaner.py:62`). Se puede elegir 75/150/200/300; la etiqueta de 200 dice «recomendado» y la de 300 «lento» (`facturas_excel/dialogo_escaneo.py:35-40`).
- **Lo elegido se guarda:** el valor queda en el ajuste `escaneo_dpi` (`dialogo_escaneo.py:89-90, 158`). Cambiar solo la constante no afecta a quien ya tiene guardado 200.
- **Color:** por defecto «grises» (`dialogo_escaneo.py:80`). El modo B/N se ofrece como «lo más rápido» (`dialogo_escaneo.py:31`). En NAPS2 eso es 1 bit (`escaner.py:78`), lo peor para tiques térmicos desvaídos.

**Línea exacta que se manda a NAPS2** (`escaner.py:422-428`):
```
NAPS2.Console.exe --noprofile --driver wia --source feeder|duplex --dpi N --bitdepth gray|color|bw --pagesize a4 --deskew --force --verbose -o destino [--device <nombre WIA>]
```
- **No se pasa `--jpegquality`, y aunque se pasara no serviría:** en NAPS2 solo afecta al exportar imágenes, no al PDF (`DoExportToImageFiles`).
- **Con `--noprofile` se usa el perfil por defecto:** `Quality = 75` y `MaxQuality = false`. Las páginas se guardan como **JPEG de calidad 75**, sin opción de línea de comandos para subirla. Tampoco hay opción para quitar hojas en blanco ni para brillo o contraste. Fuentes: AutomatedScanningOptions.cs, AutomatedScanning.cs, ScanProfile.cs y ScanOptions.cs (`/NAPS2.Lib/Automation/`, `/NAPS2.Lib/Scan/`, `/NAPS2.Sdk/Scan/` en https://raw.githubusercontent.com/cyanfish/naps2/master/).
- **Enderezado:** `--deskew` gira la imagen con remuestreo, lo que la suaviza un poco. Efecto pequeño; no lo he medido.
- **Tamaño forzado:** `--pagesize a4` mete cada tique en una hoja A4 con mucho blanco alrededor.
- **Cristal (WIA):** recibe BMP y lo pasa a JPEG con `quality=80` (`escaner.py:240-251`).

**Lo que se hace antes de mandar a Gemini**
- **Se vuelve a rasterizar a 150 ppp:** cada página del PDF se dibuja con `get_pixmap(dpi=lectura_ppp)`; por defecto 150 (`facturas_excel/hilos.py:46-47`, `facturas_excel/dialogo_calidad.py:20`, `facturas_excel/pdf.py:43-52`).
- **Se recomprime en JPEG 80** (`pdf.py:21, 52`).
- **Resultado:** escaneo a 200 → JPEG 75 → bajada a 150 (factor 0,75, que interpola) → JPEG 80. Son **dos compresiones con pérdida y una reducción**.
- **Otros sitios con 150 fijo:** `facturas_excel/recoger.py:300`, `facturas_excel/dialogo_examen.py:39` y `facturas_excel/examen.py:161,170`.
- **`MAX_LADO = 2000`** (`pdf.py:22, 35-37`) solo afecta a imágenes sueltas (`pdf.py:63, 138`), no a las páginas de PDF.
- **Partir el taco no recomprime:** `separar.py:166` copia la página tal cual.

**El visor**
- Saca la hoja del PDF original al tamaño de la pantalla (`facturas_excel/imagen_visor.py:1-9, 97-98`). Lo que se ve borroso en el visor es, por tanto, el propio PDF: 200 ppp en JPEG 75.

**Coste en Gemini**
- **La estimación del programa sigue la regla de Gemini 2.x:** cuadros de 768 px a 258 tokens cada uno (`facturas_excel/costes.py:192-215`). Con su fórmula salen 1.548 tokens a 150 ppp, 3.096 a 200 y 5.160 a 300. De ahí los textos «cuesta el doble» y «más del triple» (`dialogo_calidad.py:24-31`).
- **Pero los modelos que usa son gemini-3.8-flash y gemini-3.7-flash** (`facturas_excel/extraccion.py:32-33`), y no fija `media_resolution` (`extraccion.py:441, 458-468`).
- **En Gemini 3 los tokens de una imagen tienen un tope fijo:** por defecto unos 1.120 (alto), 280 en bajo, 560 en medio y 2.240 en ultra alto (https://ai.google.dev/gemini-api/docs/media-resolution).
- **Consecuencia probable:** subir `lectura_ppp` no multiplicaría el coste en Gemini 3. Hay que confirmarlo con los tokens reales que ya registra `costes.registrar`.
- **El SDK instalado ya permite fijar `media_resolution` por imagen** (`.venv/.../google/genai/types.py:2492-2508`).
- **Doble lectura activada por defecto** (`extraccion.py:41`): cada hoja se paga dos veces.

## 2. Resolución real del alimentador de la HP M148

- **Resolución óptica:** hasta 300×300 ppp en el alimentador (color y mono). En el cristal, hasta 600 ppp en color y 1200 en mono.
- **Sensor:** CIS (sensor de contacto).
- **Doble cara:** el alimentador no hace doble cara.
- **Capacidad y velocidad:** 35 hojas, 15–16 ppm (las fuentes no coinciden).
- **Tamaño mínimo por el alimentador: 148,5×210 mm** (de anchura, la de un A5; de altura, la de un A4). **Los tiques están por debajo del mínimo** del alimentador.
- **Detección de doble alimentación:** las especificaciones no la mencionan. El programa lo suple pidiendo el número de hojas (`dialogo_escaneo.py:96-104`, `facturas_excel/ventana_archivo.py:177-196`).
- **Fuentes:** https://cc.cnetcontent.com/vcs/hp/inline-content/2Q/F/8/5/7/3/F857370BD9579E1CA66D2726203B64E849B72ECA_source.PDF, https://support.hp.com/us-en/product/hp-laserjet-pro-mfp-m148-m149-series/21996897/document/c06165580, https://www8.hp.com/h20195/V2/GetPDF.aspx/c07874033 y https://hp.com/bd-en/products/printers/product-details/product-specifications/22954498 (página del M149fdw, modelo hermano). El mínimo de 148,5×210 mm lo dan listados de distribuidores y la página de HP del M149fdw, no una página de HP del M148.
- **Extensiones de imagen sin verificar:** `escaner.py:198` dice que la HP «no pasa de 1700x3000 puntos». A 300 ppp un A4 son 2481×3507 px, así que hay que comprobar que a 300 ppp no corta la hoja.

## 3. Ajustes para más nitidez con la HP actual

1. **Escanear a 300 ppp en grises por defecto**, y no usar nunca B/N con tiques. Es el máximo óptico del alimentador y la base habitual para OCR (https://github.com/tesseract-ocr/tesseract/wiki/ImproveQuality/5bc360ad90a69dd2c924066e7a50388b785f29b7).
   - Estimación con una minúscula de unos 1,5 mm (no medida): ocupa unos 9 px a 150 ppp y unos 18 px a 300.
   - Coste: el escaneo va más lento; no encontré cifras de HP por resolución, hay que cronometrarlo.
2. **Subir la calidad de las imágenes dentro del PDF.**
   - Crear en NAPS2 un perfil, por ejemplo «Facturas», con calidad JPEG 90–95 o «Máxima calidad».
   - Cambiar `--noprofile` por `--profile "Facturas"` en `escaner.py:422`. NAPS2 sigue aplicando `--dpi`, `--source`, `--bitdepth`, `--pagesize` y `--deskew` encima del perfil.
   - Coste: PDF más pesado (no cuantificado).
3. **Mandar a Gemini sin degradar la imagen.**
   - Sacar la imagen incrustada de cada página y enviarla tal cual, o al menos rasterizar a 300 ppp con JPEG 90 (`pdf.py:21, 43-66`; `lectura_ppp` en `dialogo_calidad.py:20` y `hilos.py:47`).
   - Coste en tokens: según la documentación de Gemini 3 seguiría topado en unos 1.120 por imagen. Confirmarlo con el registro de costes.
   - Opción para los casos difíciles: `media_resolution=ULTRA_HIGH` solo en tiques o lecturas dudosas (unos 2.240 tokens).
4. **Tiques, por el cristal**, varios a la vez, a 300 ppp en grises. Están por debajo del mínimo del alimentador. Escanear el papel térmico cuanto antes, porque se degrada (https://download4.epson.biz/sec_pubs/ds-1730/useg/en/GUID-8E846775-F590-4E58-958D-A3E3703FD481.htm).
5. **Desactivar «Escanear las dos caras» con esta HP** (`dialogo_escaneo.py:109-111`, `escaner.py:423`): su alimentador no hace doble cara.
6. **Corregir textos que confunden**: «300 lento» y los avisos de coste de `dialogo_calidad.py:24-31`, más el modelo de tokens de `costes.py:192-215`.

## 4. Qué aporta un escáner de documentos a la nitidez

- **Resolución óptica de 600 ppp** y doble sensor CIS: una sola pasada para las dos caras.
  - ScanSnap iX2500: https://www.ricoh-americalatina.com/en/products/pd/equipment/scanners/scansnap-ix2500
  - Brother ADS-4300N: https://www.brother.com.ph/en/scanners/all-scanners/ads-4300n
  - Canon DR-C230: https://www.canon-europe.com/business/products/scanners/document-scanners/imageformula-dr-c230/specifications/
  - Epson ES-580W: 600 ppp según la mayoría de tiendas.
- **Mejora de texto para letra desvaída:**
  - Epson Scan 2 tiene «Text Enhancement» con un modo para resaltar letras claras.
  - Canon tiene «Advanced Text Enhancement I/II»; no hay datos de cómo va con tiques térmicos.
- **Documentos pequeños:** desde 2×2 pulgadas en el iX2500 y el DS-C490.
- **Accesorios para tiques:** el iX2500 tiene guía de recibos (edición «Receipt») y los Brother usan hoja portadora (CS-A3301).
- **Otras funciones:** papel largo, enderezado y borrado de páginas en blanco (DS-C490, según tiendas).
- **Límite:** un tique muy borrado no lo recupera ningún escáner.

## 5. Fiabilidad («menos fallos»)

**Detección ultrasónica de doble alimentación**
- Sí: iX2500 e iX1600 (PFU), ADS-4300N (Brother), DR-C230 (folleto de Canon) y ES-580W (Micro Center).
- No: ADS-1800W (B&H indica «Multi-Feed Detection: No»).
- Sin confirmar: DS-C490.

**Rodillos (separación/freno) y repuesto**
- iX2500: juego PA03860-0001, cambio cada 200.000 hojas o un año, 58 $ en la tienda de Ricoh EE. UU. (https://store.pfu-us.ricoh.com/pa03860-0001/).
- iX1600: juego PA03656-0001, mismo ciclo. El iX1600 ya está descatalogado; lo sustituye el iX2500.
- ADS-4300N: kit PRK-A3001, cada 100.000 hojas. Precio sin confirmar.
- DR-C230: kit de rodillo de alimentación y de retardo; número de pieza y duración sin confirmar.
- ES-580W: duración sin confirmar.

**Ciclo de trabajo diario**

| Modelo | Uso diario | Velocidad | Bandeja |
|---|---|---|---|
| ADS-4300N | hasta 6.000 | — | 80 hojas |
| ES-580W | 4.000 | — | — |
| DR-C230 | 2.000–4.500 según la web de Canon (3.500 en otras) | 30 ppm | 60 hojas |
| DS-C490 | 4.500–6.500 (fuentes no coinciden) | 40 ppm | 20 hojas |
| iX2500 | no publicado (un distribuidor dice 7.000) | 45 ppm | 100 hojas |
| ADS-1800W | 1.000 | — | 20 hojas |

**Grapas, arrugas y tiques**
- Grapas: hay que quitarlas siempre. El DS-C490 anuncia protección contra grapas, según tiendas.
- Arrugadas: hoja portadora o cristal.
- Mezcla de tamaños: los tiques entran por el alimentador en los dedicados (mínimo 2×2 pulgadas), no en la HP.

## 6. Integración con el programa

**NAPS2 admite los controladores wia, twain, escl, sane y apple.**
- Brother ADS-4300N: TWAIN, WIA, ISIS y SANE.
- Epson ES-580W y DS-C490: TWAIN; WIA según tiendas.
- Canon DR-C230: TWAIN e ISIS; WIA sin confirmar.
- ScanSnap iX1600 e iX2500: **ni TWAIN ni ISIS**, solo ScanSnap Home (https://scansnap-faq.pfu.ricoh.com/hc/en-us/articles/27610858674713-Does-the-ScanSnap-Series-support-TWAIN-or-ISIS).
  - Opción 1: que ScanSnap Home guarde en una carpeta y el programa la vigile (https://www.pfu.ricoh.com/imaging/downloads/manual/ss_webhelp/en/help/webhelp/topic/ope_screen_scantofolder.html).
  - Opción 2: SnapTwain, un puente TWAIN comercial de terceros (https://snaptwain.com/). No he comprobado que funcione con NAPS2.

**Cambios en el código si se compra uno**

| Cambio | Dónde | Esfuerzo |
|---|---|---|
| a) Elegir el controlador: hoy `--driver wia` está fijo; pasarlo a un ajuste twain/wia/escl | `escaner.py:422` | ~1 h |
| b) Listar escáneres con `NAPS2.Console --listdevices --driver twain` (ver nota 1) | `escaner.py:158-177`, `ventana_archivo.py:31-38, 44`, `escaner.py:427-428` | 3–5 h |
| c) Sin cristal: ocultar «Usar el alimentador» y el camino WIA | `dialogo_escaneo.py:106-108`, `escaner.py:469-478` | 30 min |
| d) Doble cara por defecto y quitar hojas en blanco (ver nota 2) | `dialogo_escaneo.py:109-111`, `ventana_archivo.py:177-196` | 1–3 h |
| e) Probar sin `--pagesize a4` para que el controlador recorte cada tique (no he confirmado que NAPS2 tenga «auto») | `escaner.py:425` | ~1 h más pruebas |
| f) Solo ScanSnap: vigilar una carpeta, esperar a que el archivo esté completo y llamar a `procesar_rutas` | nuevo módulo | ~1 día con pruebas |

Notas:
1. Hoy solo se listan escáneres WIA, así que un escáner solo TWAIN haría que el programa diga «Windows no ve ningún escáner». Además, a `--device` se le pasa el nombre WIA.
2. Para quitar hojas en blanco no hay opción de línea de comandos en NAPS2: o perfil de NAPS2 con «ExcludeBlankPages», o filtro en Python. El aviso de hojas perdidas compara páginas con hojas, y con doble cara deja de funcionar.

El coste en Gemini por página no cambia con el escáner. Quitar los reversos en blanco ahorra llamadas, que con la doble lectura van por partida doble.

## Recomendación

1. **Primero, cambios gratis (un día de trabajo):** 300 ppp en grises, perfil de NAPS2 con calidad alta, enviar a Gemini la imagen original y tiques por el cristal. Después, escanear el mismo taco antes y después y comparar.
2. **Si siguen los tiques mal leídos y las hojas dobles**, comprar un escáner con TWAIN o WIA y detección ultrasónica: Brother ADS-4300N, Epson ES-580W o Canon DR-C230. Se integran con NAPS2 con los cambios a–e.
3. **Evitar un ScanSnap y el ADS-1800W.** El ScanSnap no tiene TWAIN y obliga a la carpeta vigilada. El ADS-1800W no detecta la doble alimentación y solo admite 1.000 hojas al día.

## Verificación

**Verificación adversarial del informe**

Método: leí el código de `/home/user/facturas-a-aplifisa` sin modificar nada (`git status` sigue limpio). El código de NAPS2 lo descargué de raw.githubusercontent.com, rama master. WebFetch y curl no llegan a ai.google.dev, hp.com ni scansnap-faq (fallo de DNS o 403 del proxy), así que los datos externos salen de extractos de WebSearch. No abrí uploads ni ninguna carpeta «listado».

## 1. Código

**Confirmadas (file:line exactos):**
- `escaner.py:62` → `DPI_POR_DEFECTO = 200`.
- `dialogo_escaneo.py:35-40` → etiquetas de las resoluciones; «300 lento» está en la línea 39.
- `dialogo_escaneo.py:89-90, 158` → el valor se guarda en `escaneo_dpi`. `recordar()` lo guarda en cada escaneo, así que cambiar la constante no afecta a quien ya escaneó.
- `dialogo_escaneo.py:80` → grises por defecto. `dialogo_escaneo.py:31` → B/N «lo más rápido».
- `escaner.py:78` → B/N se pasa a NAPS2 como `bw`.
- `escaner.py:422-428` → la orden exacta que se manda a NAPS2.
- `escaner.py:240-251` → el cristal pasa a JPEG con `quality=80`.
- `escaner.py:198` → el comentario de «1700x3000».
- `hilos.py:46-47`, `dialogo_calidad.py:20`, `pdf.py:43-52` → rasterizado a 150 ppp. `pdf.py:21, 52` → JPEG 80.
- `pdf.py:22, 35-37, 63, 138` → `MAX_LADO` solo afecta a imágenes sueltas.
- `separar.py:166` → `insert_pdf`, sin recomprimir.
- `imagen_visor.py:1-9, 97-98` → el visor saca la hoja del PDF original.
- `costes.py:192-215` → regla de cuadros de 768 px a 258 tokens. Recalculado: 1.548, 3.096 y 5.160 tokens.
- `dialogo_calidad.py:24-31` → «el doble» y «más del triple».
- `extraccion.py:32-33` → gemini-3.8-flash y gemini-3.7-flash. `extraccion.py:441, 458-468` → no se fija `media_resolution`. `extraccion.py:41` → `DOBLE_POR_DEFECTO = DOBLE_SIEMPRE`.
- `.venv/lib/python3.11/site-packages/google/genai/types.py:2492-2508` → `Part.from_bytes(..., media_resolution=...)` existe en google-genai 2.26.0. `types.py:1040-1052` incluye `MEDIA_RESOLUTION_ULTRA_HIGH`.
- `costes.py:112` → `registrar` existe.
- `dialogo_escaneo.py:96-111`, `ventana_archivo.py:31-38, 44, 175, 177-196`, `escaner.py:158-177, 423, 425, 469-478` → todo correcto.

**Corregidas:**
- **«Otros sitios con 150 fijo».** Solo `recoger.py:300` está fijo a 150; su estimación de coste en `recoger.py:333` también usa 150. En cambio, `dialogo_examen.py:39` lee `lectura_ppp` (150 es solo el valor de reserva) y se lo pasa a `examen.pasar` (`dialogo_examen.py:140-141`). `examen.py:161` es un parámetro por defecto y `examen.py:170` usa ese `ppp`. El examen ya sigue el ajuste.
- **Recomendación 4, «tiques por el cristal, varios a la vez»: choca con el programa.**
  - El esquema de Gemini es un único objeto factura por imagen (`extraccion.py:346-374`), y no hay código que separe varios documentos en una hoja.
  - Además, el cristal hace una sola hoja por escaneo (`escaner.py:341-342`).
  - Varios tiques en una misma pasada saldrían como una sola factura y los demás se perderían. Por el cristal habría que poner un tique por escaneo, lo que es lento y refuerza el argumento de comprar un escáner.
- **«En el visor se ve el PDF a 200 ppp en JPEG 75».** Solo es así para lo que entra por el alimentador. Lo escaneado por el cristal es JPEG 80 (`escaner.py:251`).

**Precisión que falta:**
- `_ajustar` (`escaner.py:195-212`) solo se usa en el camino WIA del cristal. El alimentador va por NAPS2, que no pasa por ese recorte.
- 1700 px = 8,5 pulgadas × 200 ppp. Eso sugiere que el límite se midió a 200 ppp y depende de la resolución. Es una deducción mía, no lo he comprobado.

## 2. NAPS2 (código fuente, rama master)

**Confirmadas:**
- `--jpegquality` (por defecto 75) solo se aplica en `DoExportToImageFiles` (AutomatedScanning.cs:592-600), no al PDF.
- `--noprofile` crea `new ScanProfile` (AutomatedScanning.cs:768-770). Sus valores por defecto son `Quality = 75` (ScanProfile.cs:25) y `MaxQuality` en falso.
- ScanOptions.cs:113-121: si no se marca la calidad máxima, las imágenes se guardan en general como JPEG.
- La línea de comandos no tiene opciones de hojas en blanco, brillo ni contraste (AutomatedScanningOptions.cs). `ExcludeBlankPages` existe solo en el perfil (ScanProfile.cs:112).
- `SetProfileOverrides` (AutomatedScanning.cs:800-834) aplica driver, source, pagesize, dpi, bitdepth y deskew encima del perfil.
- Los controladores son `wia/twain/escl/sane/apple` (AutomatedScanningOptions.cs:69; Driver.cs). `--listdevices` existe (línea 75).

**Corregida (cambio e):**
- Quitar `--pagesize a4` no da un tamaño automático. Con `--noprofile`, el perfil por defecto es **Letter** (ScanProfile.cs:22).
- `PageSize.Parse` solo admite letter, legal, a5, a4, a3, b5, b4 o medidas (NAPS2.Sdk/Images/PageSize.cs:24-43), y `ScanPageSize` no tiene «Auto».
- El recorte por tique tendría que venir de un perfil de interfaz o del propio controlador. Sin confirmar.

**Aviso:** todo esto es la rama master. La versión de NAPS2 instalada en el PC no se conoce.

## 3. HP M148

**Confirmadas** (ficha técnica HP M148dw/fdw; https://www8.hp.com/h20195/V2/GetPDF.aspx/c07874033 y https://cc.cnetcontent.com/vcs/hp/inline-content/2Q/F/8/5/7/3/F857370BD9579E1CA66D2726203B64E849B72ECA_source.PDF):
- Alimentador: 300×300 ppp en color y mono, óptico hasta 300.
- Cristal: 600 en color y 1200 en mono.
- Alimentador de 35 hojas.
- Sin doble cara en el alimentador («Duplex ADF scanning: No»).
- **15 ppm.** No encontré ninguna fuente que dé 16.

**Corregida (fuente):** el mínimo de 148,5×210 mm sí aparece en la propia ficha de HP del M148fdw (https://support.hp.com/us-en/product/hp-laserjet-pro-mfp-m148-m149-series/21996897/document/c06165580, según el extracto del buscador). No hace falta apoyarse solo en el M149 ni en distribuidores.

**Sensor CIS:** solo lo dice una tienda (https://www.paklap.pk/hp-laserjet-pro-m148fdw-printer-pakistan.html). En HP no lo he confirmado.

## 4. Gemini 3

**Confirmadas** (https://ai.google.dev/gemini-api/docs/media-resolution, por extracto):
- Imagen: 1.120 tokens por defecto y en alto, 280 en bajo, 560 en medio y 2.240 en ultra alto.
- Ultra alto solo se puede fijar por parte, no para toda la petición.

**Matices que faltan:**
- **Más ppp puede no mejorar la lectura.** Si el tope de tokens es fijo, Gemini probablemente reduce la imagen por dentro, así que subir `lectura_ppp` puede no notarse: es una deducción mía, y la documentación no dice cuántos píxeles usa en cada nivel. La recomendación 3 hay que medirla, no darla por hecha.
- **PDF frente a imagen.** Para PDF, Google recomienda el nivel medio (560) y dice que el alto rara vez mejora el OCR de documentos normales. El programa manda JPEG, así que se aplica la regla de imagen.
- **Versión de la API.** La guía de Gemini 3 (https://ai.google.dev/gemini-api/docs/gemini-3) tenía una nota de que `media_resolution` solo estaba en la API v1alpha. El programa usa la versión por defecto (`extraccion.py:395-398`), así que hay que probarlo.
- **Tesseract y los 300 ppp.** La regla es real (https://github.com/tesseract-ocr/tesseract/wiki/ImproveQuality/5bc360ad90a69dd2c924066e7a50388b785f29b7), pero es para Tesseract, no para Gemini.

## 5. ScanSnap y TWAIN

**Confirmada:** no tienen TWAIN ni ISIS; ScanSnap Home es el único controlador.
- FAQ de PFU: https://scansnap-faq.pfu.ricoh.com/hc/en-us/articles/27610858674713-Does-the-ScanSnap-Series-support-TWAIN-or-ISIS
- Página del iX2500: https://www.pfu-us.ricoh.com/scanners/scansnap/ix2500

**SnapTwain:** confirmado que es un controlador comercial de JSE (https://www.jse.de/scansnap-twain-driver.html, https://snaptwain.com/). Su lista incluye el iX1600 y el iX2500. Que funcione con NAPS2 sigue sin comprobar. WIA o eSCL para ScanSnap: sin confirmar.

**Confirmado:** el iX1600 lo sustituye el iX2500 (https://www.pfu-us.ricoh.com/scanners/scansnap/ix1600).

## 6. Escáneres

**iX2500**
- **Confirmadas:**
  - 600 ppp, 45 ppm y 100 hojas (https://www.ricoh-americalatina.com/en/products/pd/equipment/scanners/scansnap-ix2500). Los 45 ppm valen hasta 300 ppp en color; a 600 ppp en color baja a 13 hojas/min, según la tabla comparativa de PFU: https://scansnap-faq.pfu.ricoh.com/hc/en-us/articles/21619450199321
  - Detección ultrasónica (folleto: https://www.pfu-apac.ricoh.com/au/scanners/downloads/datasheet/AU_ScanSnap_iX2500_Brochure_202603_EN.pdf).
  - Mínimo de 2×2 pulgadas (B&H).
- **Corregida:** la guía de tiques viene también con el iX2500 normal (https://gigazine.net/news/20250624-scansnap-ix2500/). La «Receipt Edition» existe (enero de 2026) y lo que añade es QuickBooks y lectura de datos de factura (https://www.pfu-us.ricoh.com/about-us/press-releases/2026/01/pfu-america-introduces-scansnap-ix2500-receipt-edition). Con la guía puesta, el alimentador admite 50 hojas, no 100.
- **Rodillos:** PA03860-0001 a 58 $ confirmado en B&H, SHI y LTT (https://www.shidirect.com/product/50346325/Ricoh-ScanAid-Scanner-roller-kit). La tienda de Ricoh no la pude abrir. El ciclo de 200.000 hojas o un año es la guía general de ScanSnap (https://www.pfu.ricoh.com/imaging/downloads/manual/ss_webhelp/en/help/webhelp/topic/ma_consumable_rollerset_500.html). No encontré una página propia del iX2500.

**iX1600:** juego de rodillos PA03656-0001, cada 200.000 hojas o un año (https://www.pfu.ricoh.com/imaging/downloads/manual/ss_webhelp/en/help/webhelp/topic/ma_consumable_rollerset.html). Detección ultrasónica confirmada (https://www.pfu.ricoh.com/global/scanners/scansnap/ix1600/).

**Brother ADS-4300N**
- **Confirmadas:**
  - Detección ultrasónica (https://support.brother.com/g/s/id/htmldoc/ads/cv_ads4300n/use/html/GUID-A0F85D51-7108-4D34-89C9-98C8AFBE4B37_23.html).
  - Controladores TWAIN, WIA, ISIS y SANE (folleto: https://brother-usa.com/-/media/brother/product-catalog-media/documents/ads-4300n-2-page-brochure.pdf).
  - 80 hojas, 6.000 al día (tiendas), 600 ppp.
  - Hoja portadora CS-A3301 compatible (https://brother-usa.com/products/csa3301), 500 usos y 24,99 $.
  - Kit de rodillos PRK-A3001 cada unas 100.000 hojas (https://www.brother-usa.com/p/scanner-supplies/PRKA3001).
- **Corregida:** el precio del PRK-A3001, que el informe da como «sin confirmar», es de 37,79 $ en Brother EE. UU.

**Canon DR-C230**
- **Confirmadas:**
  - Ultrasónico y por longitud (https://www.canon-europe.com/business/products/scanners/document-scanners/imageformula-dr-c230/specifications/).
  - 30 ppm y 60 hojas.
  - 2.000–4.500 al día según Canon Europa; 3.500 según Canon EE. UU. y Asia.
- **Corregida (WIA):** el paquete oficial de controladores se llama «ISIS / TWAIN / WIA Driver» (https://hk.canon/en/support/0100979818). Así que sí tiene WIA.
- **Corregida (rodillos):** el kit de cambio es para 200.000 hojas o 12 meses, pero las tiendas dan números de pieza distintos: 0697C003 (https://www.precisionroller.com/exchange-roller-kits-for-canon-dr-c230-imageformula-scanner/products.html) y 5595C001 (https://scannerone.com/product/canon-c230-roller-kit/). Hay que confirmarlo con Canon.

**Epson ES-580W**
- **Confirmadas:** detección ultrasónica y por longitud, más una función de protección del papel que detecta grapas (https://www.epson.com.sg/p/B11B258502). 4.000 al día, 600 ppp, 35 ppm y 100 hojas (tiendas).
- **Corregida (controladores):** el folleto de Epson da TWAIN, WIA, ISIS, SANE e ICA, así que WIA no es solo «según tiendas» (https://download.epson.com.sg/product_brochures/scanner/ESD/20045%20EPSON%20A4%20Biz%20Scanner%20Product%20Launch%20(ES-580W)_FOR%20WEB.pdf).
- **Confirmada:** «Text Enhancement» de Epson Scan 2 con la opción para resaltar letras claras (https://download4.epson.biz/sec_pubs/ds-c490/useg/en/GUID-E2AC0D1A-F96C-446A-8B07-7B545540574C.htm).

**Epson DS-C490**
- **Confirmadas:** 4.500 al día según tiendas y 6.500 de pico según Epson EE. UU. (https://epson.com/p/B11B271201). 20 hojas, 40 ppm, mínimo de 2×2 pulgadas, TWAIN e ISIS.
- **Detección ultrasónica:** solo la mencionan tiendas, así que sigue «probable, sin confirmar».
- **Sin confirmar:** WIA y la protección contra grapas.

**Brother ADS-1800W**
- **Confirmadas:** «Multi-Feed Detection: No» y 1.000 hojas al día (https://www.bhphotovideo.com/c/product/1837721-REG/brother_compact_desktop_scanner_with.html). Brother da también 1.000 al día. No encontré ninguna fuente de Brother sobre la detección de doble alimentación.

## 7. Precios

El informe no da el precio de ningún escáner. Precios orientativos, sin fecha ni IVA confirmados:

| Modelo | Precio | Fuente |
|---|---|---|
| ADS-4300N | 329–380 € | LDLC, PcComponentes, Galaxus |
| ES-580W | 396–435 € | Galaxus |
| DR-C230 | unos 500 € | LDLC |
| iX2500 | unos 424–454 € | Klarna ES (https://www.klarna.com/es/shopping/pl/cl50/3527348270/Escaneres/ScanSnap-IX2500-Dual-CIS-WiFi-USB-Scanner/), Alternate.fr |
| iX2500 Receipt Edition | 439,99–449,99 $ | tienda de PFU EE. UU. |

## Lista de correcciones

1. **Tiques por el cristal:** no ponerlos «varios a la vez». El programa lee una factura por imagen (`extraccion.py:346-374`) y el cristal hace una hoja por escaneo (`escaner.py:341-342`).
2. **Cambio e:** quitar `--pagesize a4` con `--noprofile` escanea en Letter (ScanProfile.cs:22). NAPS2 no tiene tamaño «auto» (PageSize.cs:24-43).
3. **«150 fijo»:** solo lo está `recoger.py:300` (y la estimación de `recoger.py:333`). `dialogo_examen.py:39` y `examen.py:161, 170` siguen `lectura_ppp`.
4. **Canon DR-C230:** sí tiene WIA (paquete oficial «ISIS / TWAIN / WIA»).
5. **Epson ES-580W:** WIA, TWAIN e ISIS confirmados en el folleto de Epson, no solo en tiendas.
6. **HP M148:** el mínimo de 148,5×210 mm aparece en la ficha de HP del M148fdw (c06165580). La velocidad es 15 ppm; los 16 no tienen fuente.
7. **iX2500:** la guía de tiques viene también en el modelo normal. La Receipt Edition (enero de 2026) añade QuickBooks. Con la guía puesta, el alimentador admite 50 hojas.
8. **Precio del PRK-A3001:** 37,79 $ (Brother EE. UU.). El DR-C230 tiene kit de rodillos de 200.000 hojas o 12 meses, con números de pieza distintos según la tienda (0697C003 / 5595C001).
9. **Gemini 3:** con el tope de 1.120 tokens, subir `lectura_ppp` quizá no mejore la lectura. Hay que medirlo antes de darlo por ganado. Además, `media_resolution` pudo estar limitado a v1alpha y el programa usa la versión por defecto, así que hay que probarlo.
10. **Visor:** lo escaneado por el cristal está en JPEG 80, no en 75.
11. **Falta el precio de los escáneres:** unos 330–500 € (tabla de la sección 7).
12. **La conclusión principal es plausible pero no está medida.** Que la falta de nitidez venga sobre todo del programa no se ha comparado con escaneos reales.

**Sin poder verificar:**
- Que el iX2500 admita 7.000 hojas al día.
- La duración de los rodillos del ES-580W.
- El sensor CIS de la HP en una fuente de HP.
- La detección ultrasónica, WIA y la protección contra grapas del DS-C490.
- Que SnapTwain funcione con NAPS2.
- Cuántos píxeles usa Gemini 3 en cada nivel.
- Las horas de trabajo estimadas para cada cambio.

