<!-- Revisión del 04-05/10/2026, copiada del scratchpad de la sesión (las rutas /tmp/... ya no existen). Estado de cada punto: ver PLAN-MEJORAS.md, «Para seguir». -->

## Revisión de la APLICACIÓN (estabilidad, errores, actualizaciones, diagnóstico)

No he tocado el repo. Las líneas citadas son de HEAD 55f12d5. Otra sesión está cambiando ahora mismo la copia de trabajo, sin commit, en build.yml, conftest.py, app.py, su_suma.py y ventana_validacion.py: está metiendo un «FrenoDeAjustes». Por eso comprobé lo importante sobre una copia sacada con `git archive HEAD`. Los scripts de prueba están en `/tmp/claude-0/-home-user-Notas-Asesoria-app/80eee95a-129e-573c-8981-869185147349/scratchpad/revision/aplicacion/`.

**1. Guardar la sesión sola [VERIFICADO]**
- **Hoy:** `_guardar_sesion` solo se llama al cerrar (app.py:1809) y al unir hojas (ventana_lectura.py:588), no al acabar cada bloque. Además:
  - Las correcciones y la cola pendiente (`_cola` no se guarda) se pierden si el programa se cuelga o se va la luz.
  - Si la sesión no se puede cargar (pickle de otra versión), al cerrar se ejecuta `sesion.borrar()` (app.py:1665).
- **Propuesta:**
  - Guardar al terminar cada bloque y unos segundos después de cada cambio.
  - Guardar las imágenes aparte por su hash: ya existen en muestras_revision/imagenes.
  - Apartar la sesión ilegible como `.danada` en vez de borrarla.
- **Por qué:** cada lectura perdida se vuelve a pagar. Con 400 hojas, guardar tarda 2,06 s y ocupa 80 MB porque se comprimen JPEG ya comprimidos.
- **Esfuerzo:** medio.

**2. La cola vuelve a entrar mientras hay un aviso abierto [VERIFICADO]**
- **Hoy:** `_on_terminado` abre ventanas modales a mitad del proceso (ventana_lectura.py:257, 266-267, 280). Si mientras tanto termina un escaneo, `procesar_rutas` arranca otra lectura, y al cerrar el aviso se arranca una más.
- Lo reproduje con un Worker simulado: dos lecturas a la vez, y el bloque «taco_b» quedó guardado como «escaneo_nuevo». Sus filas apuntan al PDF equivocado, y el PDF se parte al exportar.
- **Propuesta:**
  - Que cada Worker lleve su propio elemento (no `self._elemento_cola_actual`).
  - Una marca de «procesando resultado» que impida entrar dos veces.
  - Cambiar esos avisos por la banda no modal (`_avisar`).
- **Esfuerzo:** medio.

**3. Cerrar con una lectura en marcha: ventana congelada y cierre forzoso [VERIFICADO]**
- **Hoy:** `esperar_hilos` espera 5 s y se llama dos veces (app.py:1370 y aboutToQuit). Medido: 10 s congelada y luego «QThread: Destroyed while thread is still running», salida 134 (en Windows, «dejó de funcionar»).
- Ni Worker ni HiloEscaneo se pueden cancelar.
- **Propuesta:** botón «Detener lectura» con cancelación cooperativa (comprobar entre hojas y usar `cancel_futures`), y al cerrar preguntar o desconectar los hilos.
- **Esfuerzo:** medio.

**4. Un 429 por «cuota por minuto» se toma como «sin crédito» y se tira lo leído [VERIFICADO]**
- **Hoy:** extraccion.py:345 busca «billing» antes de mirar si es un 429. El mensaje habitual de Google para ese 429 dice «check your plan and billing details», así que se trata como `SinCredito`.
- Medido: 19 hojas leídas y pagadas, y el bloque entero se descarta (hilos.py:62-64 y 94).
- Las hojas leídas a la vez son 10 y con doble lectura se piden dos modelos, así que van ~20 peticiones simultáneas.
- **Propuesta:**
  - Clasificar por código: 429 frente a «prepayment/depleted».
  - Reintentar con espera creciente y bajar los hilos sobre la marcha.
  - Ante un error de crédito, entregar lo ya leído.
- **Esfuerzo:** pequeño.

**5. Sin red, API key mala o sin crédito: pausar en vez de llenar el lote de rojos [VERIFICADO]**
- **Hoy:**
  - Con una key no válida (400), bloqueada (403) o sin red, cada hoja falla por su cuenta (2 llamadas por hoja). El bloque entra entero en rojo y el PDF se archiva igual.
  - `_on_fallo` (ventana_lectura.py:165) no dice qué PDF falló.
  - No hay «volver a leer las hojas en rojo», aunque el aviso lo sugiere.
- **Propuesta:** un error de conexión o de cuenta pone la cola en pausa conservando el PDF, con un botón «Reintentar». Y una acción para releer solo las hojas rojas a partir de `crudos`, que ya tiene las imágenes.
- **Esfuerzo:** medio.

**6. El cuelgue del CI no lo causan los ajustes de tamaño [VERIFICADO]**
- **Causa real:** con faulthandler pillé el cuelgue (1 de cada ~5 ejecuciones). Está en app.py:1521, `DialogoNotasVersion(...).exec()`, abierto por el temporizador de 500 ms (app.py:158). El fixture `guardado` (test_distribuciones.py:32) sustituye `ajustes.leer`, así que no ve `notas_version_vistas`.
- **Los ajustes de tamaño no hacen bucle:** probé 5 distribuciones × 72 tamaños; nunca pasan de 60 llamadas seguidas y siempre se paran. El «freno» que está metiendo la otra sesión no arregla este cuelgue.
- **Propuesta:**
  - Poner esa clave en el fixture.
  - `VentanaPrincipal(dialogos_al_arrancar=False)` para las pruebas.
  - En conftest, que cualquier `exec()` de un diálogo falle al momento.
- **Esfuerzo:** pequeño.

**7. Fallos sin avisar después de exportar [VERIFICADO]**
- **Hoy:**
  - `registro_facturas.exportar` traga `sqlite3.Error` (registro_facturas.py:265), y ventana_aplifisa.py:519 no mira lo que devuelve. Con la base bloqueada o el disco lleno, no queda apuntada como «ya exportada».
  - `_actualizar_expedientes` hace `pass` ante errores de escritura, por ejemplo si un PDF está abierto (ventana_archivo.py:133).
- **Propuesta:** avisar en rojo y reintentar, y dejarlo en el registro de errores.
- **Por qué:** sin ese apunte, la misma factura puede exportarse dos veces a Aplifisa sin aviso.
- **Esfuerzo:** pequeño.

**8. Que solo se pueda abrir el programa una vez [VERIFICADO]**
- **Hoy:** no hay QLockFile ni QLocalServer, y el instalador no tiene AppMutex. Un doble clic o un `--import` de Escáner Fotos abre otra copia que recupera la misma sesión y la misma base SQLite (espera de bloqueo de 15 s). La última en cerrarse pisa a la otra.
- **Propuesta:** bloqueo de instancia, y pasar el `--import` a la copia que ya está abierta.
- **Esfuerzo:** pequeño-medio.

**9. Publicar versiones de forma reproducible y con vuelta atrás**
- **Hoy:**
  - requirements.txt no fija versiones (`PySide6>=6.6`, `google-genai>=1.0`). Las pruebas y la compilación instalan cada una por su lado (build.yml:32 y 53).
  - El .exe compilado no se arranca nunca antes de publicar.
  - El instalador no tiene `[InstallDelete]` para limpiar `_internal` de la versión anterior.
  - El programa se actualiza solo desde `releases/latest` y no hay forma de volver atrás.
- **Propuesta:**
  - Fichero de versiones fijas con hashes, usado en los dos pasos del CI.
  - Prueba de humo `FacturasAplifisa.exe --autocomprobacion` en el CI.
  - Guardar el instalador anterior y ofrecer «Volver a la versión anterior» (Inno Setup permite instalar una versión más vieja).
- **Esfuerzo:** medio.

**10. La actualización interrumpe el trabajo**
- **Hoy:** a los 1,5 s de arrancar sale una pregunta modal (app.py:1557). Si se acepta, se instala y se cierra (app.py:1584) aunque haya una lectura en marcha (caso del punto 3). No enseña `act.notas` ni deja «más tarde» u «omitir esta versión».
- **Propuesta:** bajar en segundo plano, instalar al cerrar, no hacerlo durante una lectura o un escaneo, y enseñar las novedades.
- **Esfuerzo:** pequeño-medio.

**11. Registro de actividad e «Informe para soporte»**
- **Hoy:** solo se apuntan las excepciones no tratadas en errores.log (que crece sin límite). No queda nada de los fallos de cada hoja, de los errores de Gemini, de la salida de NAPS2, de las actualizaciones ni de los guardados de sesión. Ayuda → Diagnóstico enseña solo pendientes.md.
- **Propuesta:**
  - `actividad.log` rotativo: versión, versiones de Qt y genai, pantalla y escala, cada bloque (hojas, tiempo, coste, modelo), errores clasificados, sin la key.
  - Un ZIP de diagnóstico con un solo clic.
- **Por qué:** sin esto, diagnosticar a distancia depende de que el asesor copie a mano las ventanas de error.
- **Esfuerzo:** medio.

**12. Las caídas graves no dejan rastro [VERIFICADO]**
- **Hoy:** no hay faulthandler, ni `threading.excepthook` (HiloLocalizar va en un hilo de Python), ni manejador de mensajes de Qt. En el .exe no hay consola, así que el aborto del punto 3 no deja nada.
- **Propuesta:** `faulthandler.enable(file=…)` en `main`, más esos dos ganchos escribiendo al registro.
- **Esfuerzo:** pequeño.

**13. El tope de tiempo de NAPS2 no sirve [VERIFICADO]**
- **Hoy:** el bucle `for linea in proceso.stdout` (escaner.py:430) bloquea antes de llegar a `wait(timeout)` (escaner.py:435), y si salta el tiempo no se mata el proceso. Con un NAPS2 falso colgado y el tope a 2 s, el hilo seguía vivo a los 12 s.
- **Propuesta:** leer la salida en otro hilo, poner un tiempo máximo sin hojas nuevas, `kill()` al pasarse, y botón «Cancelar escaneo».
- **Esfuerzo:** pequeño.

**14. muestras_revision crece sin límite y frena la ventana [VERIFICADO]**
- **Hoy:**
  - Cada PDF cargado se copia entero en AppData; uno de 276 MB tardó 2,8 s en la ventana.
  - Partir el PDF (`dividir_pdf`) también va en la ventana: 1,6 s.
  - Cada corrección guarda una foto completa del lote: 1,3 MB por edición con 400 líneas (ventana_validacion.py:437, muestras_revision.py:153).
  - El ZIP de ejemplos lleva todos los clientes.
- **Propuesta:** límite de días o de tamaño con limpieza, guardar en segundo plano, una foto por sesión en vez de por tecla, y elegir el periodo del ZIP.
- **Esfuerzo:** medio.

**15. Las actualizaciones no van firmadas**
- **Hoy:** el SHA-256 viene de la misma release que el instalador. Si falta el `.sha256`, no se comprueba nada (updater.py:85 y 104). Se instala en silencio.
- **Propuesta:** firma Ed25519 con la clave pública dentro del programa (o Authenticode), y negarse a instalar sin firma.
- **Por qué:** una cuenta de GitHub comprometida llegaría directa al ordenador con datos de clientes.
- **Esfuerzo:** medio.

**16. Páginas de PDF enormes [VERIFICADO]**
- **Hoy:** el límite `MAX_LADO` solo se aplica a imágenes sueltas (pdf.py:35), no a las páginas de PDF (pdf.py:51). Una foto de móvil metida en una página de 3000×4000 pt sale a 6250×8334 px: 1,2 MB por hoja frente a 67 KB, 12 veces más lenta, y con el propio cálculo de costes.py 25.542 tokens frente a 1.548.
- **Propuesta:** elegir la escala para no pasar de 2000 px.
- **Esfuerzo:** pequeño.

**17. Certificados: Gemini no usa el almacén de Windows**
- **Hoy:** google-genai crea la conexión segura solo con `certifi.where()` (_api_client.py), mientras urllib (las actualizaciones) usa el almacén de Windows. Con un antivirus que inspecciona HTTPS (ESET, Kaspersky), las actualizaciones irían y la lectura daría CERTIFICATE_VERIFY_FAILED.
- **Propuesta:** pasar un contexto de `truststore` con `HttpOptions(client_args={"verify": ctx})` y explicar ese error en español.
- **Esfuerzo:** pequeño.

**18. La API key no se comprueba**
- **Hoy:** se guarda sin probarla y se escribe a la vista (app.py:1830-1834). `GEMINI_API_KEY` del entorno manda sobre la guardada sin decirlo (claves.py:20); Gemini CLI usa esa misma variable.
- **Propuesta:** comprobarla con una llamada gratuita (`models.get`), ocultar lo escrito, avisar si viene del entorno, y un botón «Comprobar conexión».
- **Esfuerzo:** pequeño.

**19. El tope de gasto solo avisa a toro pasado**
- **Hoy:** `aviso_tope` solo se mira después de un lote y una vez por sesión (ventana_lectura.py:490). `procesar_rutas` no estima nada antes de empezar.
- **Propuesta:** «Esto costará ~X € (doble lectura)» antes de colas grandes, y un tope duro opcional que pause la cola.
- **Esfuerzo:** pequeño.

**20. El escaneo y la cola comparten datos de la ventana**
- **Hoy:** `_escanear` cambia `_tipo_escaneo` y `_escaneo_reciente` (ventana_archivo.py:48-49) mientras se lee otro bloque. Ese bloque se apunta como del tipo del escaneo (ventana_lectura.py:252), y sus líneas salen en ámbar con avisos falsos de «Dijo que este taco era de…».
- **Propuesta:** guardar ese estado por cada elemento de la cola.
- **Esfuerzo:** pequeño.

**21. Pantallas pequeñas y escalado**
- **Hoy:**
  - La ventana abre siempre a 1420×820 (app.py:112) y no recuerda posición ni si estaba maximizada.
  - El Cuadre (1180×760) y el Examen (880×780) se salen en un portátil 1080p al 150 %, que da 1280×720.
- **Propuesta:** guardar y restaurar la geometría, y una función que ajuste cada diálogo a `availableGeometry`.
- **Esfuerzo:** pequeño.

**22. Rendimiento con lotes grandes y al arrancar**
- **Hoy:**
  - Al acabar cada bloque se rehace la tabla entera: con 800 líneas, 1,4 s de rellenar más 0,5 s de revalidar.
  - Cada fila lleva un QComboBox propio (tabla_facturas.py:380).
  - Cada corrección revalida todo: 0,38 s con 400 líneas.
  - Al arrancar, importar `google.genai` cuesta 0,53 s de 1,0 s (medido en Linux).
- **Propuesta:** añadir solo el bloque nuevo, usar un delegado en vez del QComboBox, revalidar solo el documento tocado, importar genai solo cuando haga falta, y pantalla de arranque.
- **Esfuerzo:** medio.