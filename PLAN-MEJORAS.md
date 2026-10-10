# Plan de mejoras — Facturas a Aplifisa (v1.1.0 y siguientes)

## Para seguir (nota del 10/10/2026)

**Estado.** Publicada la **1.26.0 «PDF pesados sin miedo»** (10/10/2026).
El usuario pidió: «el objetivo es que el programa pueda trabajar con PDF de
alto peso de 100-200 MB para ir sobrados» y «cuando termines sube todo como
update».

### Qué se hizo en la 1.26

- **Pruebas de estrés** en 4 frentes (volumen y mañana, tablas grandes,
  lecturas absurdas de la IA, registro y concurrencia), con 37 puntos
  priorizados. Quedaron hechos los n.º 1–18, 20 (1), 21–26, 28–35.
- **Memoria:** imagen de cada hoja en disco con su asa (`imagen_hoja.py`),
  caché de MuPDF vaciada, original guardado a trozos en un hilo, sesión
  pequeña y con un solo guardado pendiente.
- **Tabla incremental**, exportación con el archivo del cliente en un hilo,
  expediente por tandas.
- **Nitidez:** la foto del escaneo se reduce con PIL sin que MuPDF la dibuje
  (también HP Scan, «1 g»), JPEG 90, cada hoja se dibuja justo antes de
  leerla (`pdf.Hojas`), tope de 9 Mpx.
- **Lecturas absurdas:** `sanear_lectura.py`, importes imposibles en rojo,
  JSON seguro, líneas juntadas por tipo (con margen de redondeo), tope de
  tokens con reintento ampliado si Gemini corta.
- **Cola y cierres:** una lectura a la vez, cerrar/actualizar/vaciar a mitad
  sin perder nada, cola guardada en la sesión con «Seguir leyendo», bloques
  fallidos que se pueden volver a leer, salir con `os._exit(0)` tras guardar
  si la lectura no acaba.
- **Registro:** al archivar se guardan todas las líneas de IVA (antes solo la
  primera; venía de antes de la 1.25).
- Revisiones adversariales: por rama, una final por 5 frentes y tres rondas
  más sobre sus arreglos. La última fue diferencial: 12.000 facturas
  inventadas de 13 a 300 líneas por el camino de la 1.25 y el de la 1.26, sin
  ninguna diferencia de gravedad en IVA, recargo ni base.

**Medida final** (banco con IA falsa, `scratchpad/sintesis/res/final.md`):

| Caso | Pico 1.25 → 1.26 | Parón máx. | Cierre | Sesión |
|---|---|---|---|---|
| 450 hojas | 1063 → 398 MB | 17,9 → 0,9 s | 4,5 → 0,17 s | 75 → 0,1 MB |
| 200 hojas a 300 ppp | 1106 → 442 MB | 7,8 → 0,5 s | 6,5 → 0,18 s | 120 → 0,05 MB |
| Dos PDF (650 hojas) | 1257 → 431 MB | 10,2 → 1,5 s | 5,2 → 0,33 s | 104 → 0,15 MB |

### Pendiente para la 1.27

1. **Bloque cortado al cerrar:** se vuelve a leer (y pagar) entero, hasta
   24 hojas. Que `Worker.run` guarde con la cola las hojas ya leídas y no
   las vuelva a pedir.
2. **Registro con facturas de varios tipos archivadas antes de la 1.26:**
   tienen solo la primera línea. Repararlas leyendo la copia del Excel que
   se guarda en el expediente (no volver a exportar).
3. **n.º 19 (a) y hallazgo d2o:** lo tecleado en una fila se pierde si llega
   un bloque con el editor abierto. Delegado para el desplegable o pasar a
   `QTableView` con modelo.
4. **Cerrar mientras se dibuja** tarda hasta 5 s: mirar la cancelación dentro
   de `pdf.hoja_a_jpg`, ya con el cerrojo.
5. **n.º 27 purga de disco** (partes de una cola guardada que se queda días,
   muestras viejas) y **n.º 36** (el cuadre crece con el cuadrado con muchos
   importes iguales).
6. **n.º 20 (2):** productor/consumidor (dibujar y leer en paralelo con la IA).
7. **Volver a la 1.25 tras instalar la 1.26** aparta la sesión (el pickle
   lleva `imagen_hoja.ImagenHoja`) y la 1.26 no la recupera después. Riesgo
   bajo.
8. **Banco reducido en `tools/`** para correrlo antes de cada versión (punto
   de la síntesis), con los umbrales: pico < 600 MB, parones < 1 s, cierre
   < 0,5 s, sesión < 1 MB.
9. **Escáner nuevo** (cuando lo compre): elegir controlador TWAIN/WIA/eSCL,
   dos caras, quitar hojas en blanco. **UBL** (RD 238/2026).
10. Lo que quede de `docs/revisiones/` (aplicación, organización, diseño).

### Después: «El resto dale con todo»

Fuera de todo esto queda lo de **tamaño de pantalla** (modo portátil,
anchos, letra, tamaño de ventana): el usuario tiene una pantalla 2K y dijo
«no hace falta ajustar nada más». Las revisiones completas están en
`docs/revisiones/`. Antes de cada PR se hace una revisión adversarial con
un subagente.

- **1.26 aplicación** (`aplicacion.md`):
  - **Pendientes:** puntos 2, 3, 5, 8, 9, 10, 11, 12, 13, 14, 15 (exigir el
    `.sha256`), 16, 18, 20 y 22.
  - **Si cabe:** 17 (truststore) y 19 (estimar el coste antes de leer).
  - **Ya hechos:** 1, 4, 6 y 7.
  - **Fuera:** 21 (pantalla).
- **1.27 organización** (`organizacion.md`):
  - **Pendientes:** puntos 3 (clave de las facturas sin número), 4, 6, 7,
    10, 11, 12, 14, 15, 16, 17, 18, 19 y 20.
  - **Ya hechos:** 1, 2, 5 y 8.
  - **A medias:** el 9 (falta el historial de movimientos).
  - **En la 1.26:** el 13 y el 21.
- **1.28 diseño funcional** (`diseno.md`, sin lo de tamaño):
  - repaso del teclado;
  - «Exportar» que diga «Faltan N»;
  - que el Cuadre año no se cierre con «Ver en el lote»;
  - un solo cuadre;
  - botones repetidos y menús;
  - una guía cuando la pantalla está vacía;
  - los textos que confunden;
  - «Escanear otro igual».
- **1.29 estructura** (`estructura.md`).
- **Funcionamiento** (`funcionamiento.md`): casi todo hecho en la 1.24 y la
  1.25; repasar lo que quede.

### Escáner: cuello de botella y nitidez (consulta del 09/10/2026)

Informes verificados en `docs/revisiones/`: `escaneo-programa.md`,
`escaner-compra.md` y `factura-electronica.md`.

**Qué pasa hoy.** Cada hoja pierde calidad tres veces:
1. se escanea a 200 ppp;
2. NAPS2 la guarda en JPEG de calidad 75 (con `--noprofile`);
3. antes de mandarla a Gemini se vuelve a pasar a imagen a 150 ppp, en JPEG
   de calidad 80.

Además, la HP M148:
- no hace las dos caras por el alimentador;
- no detecta dos hojas pegadas;
- no admite tiques por el alimentador (el mínimo es 148×210 mm).

**El usuario piensa comprar un escáner de documentos** (unos 200 €, en
Amazon). Le recomendé el Canon DR-C230 (unos 300 €) o el Ricoh SP-1120N
(235–255 €). Hay que preguntarle cuál compra.

**Para la 1.26.** Medir antes de cambiar.
1. **Apuntar tiempos.** Por taco: escaneo, páginas y lectura.
2. **Nitidez:**
   - escanear a 300 ppp en grises;
   - subir la calidad del JPEG con un perfil de NAPS2 en vez de
     `--noprofile`;
   - no reducir la imagen antes de mandarla a Gemini.

   Con Gemini 3 los tokens de una imagen tienen un tope fijo: medir el coste
   y la lectura con el registro de costes.
3. **Escáner nuevo:**
   - elegir controlador TWAIN/WIA/eSCL (hoy `--driver wia` está fijo y los
     escáneres solo se listan por WIA);
   - dos caras y quitar las hojas en blanco;
   - sin cristal.
4. **Entre tacos:**
   - «Escanear otro igual», recordar el tipo y quitar el campo Cliente, que
     no sirve;
   - que el tipo vaya con cada escaneo (punto 20 de `aplicacion.md`);
   - avisos sin ventana al acabar cada bloque.
5. **NAPS2:** que un cuelgue no bloquee (tiempo máximo, matar el proceso) y
   un botón «Cancelar escaneo».
6. **Más adelante:**
   - carpeta vigilada;
   - aceptar fotos HEIC y TIFF de varias páginas;
   - bandeja por cliente y hojas separadoras;
   - importar facturas electrónicas en UBL. El RD 238/2026 y la Orden
     HAC/1028/2026 ya están publicados; calendario aún sin confirmar:
     octubre de 2027 para más de 8 M€ y octubre de 2028 para el resto.

### El equipo del usuario (09/10/2026)

PC nuevo:
- 16 GB de RAM;
- SSD de 1 TB, con ~85 % libre;
- pantalla 2K.

Con la 1.25, un PDF de 200 MB sube el programa a ~1 GB: le sobra. La 1.26
apunta a menos de 500 MB. La limpieza de copias en disco no corre prisa,
pero sigue en el plan.

### Preguntas al usuario sin contestar (`config/pendientes.md`, 4–7)

- Formato de Aplifisa para la ISP, el tipo de factura y la clave de régimen.
- La fecha de deducción de las facturas del año anterior: hoy salen en rojo.
- Sectores diferenciados en el recargo de equivalencia.
- Las ventas de un cliente en recargo.

## v1.16.0 — una factura, un PDF (24/09/2026)

Estado: **implementado**. El usuario pidió guardar por proveedor/cliente y
eligió: todo junto con el nombre del proveedor (sin subcarpetas), conservar
el taco en «Tacos escaneados» y aplicarlo solo a lo nuevo. `separar.py` parte
al exportar (datos ya revisados), cada factura a su ejercicio y tipo; las
uniones a mano guardan sus hojas en `Factura.paginas_documento`.

## v1.15.0 — archivo unificado (24/09/2026)

Estado: **implementado**. Petición del usuario: que las carpetas se creen,
se recojan los archivos que ya hay y se cree algo unificado; eligió
«expediente completo», origen Escritorio y Descargas, identificación por
texto (Gemini solo en escaneados, con coste a la vista). El diseño lo dejó
a criterio nuestro «ideal para lo que hay y para el futuro»:

- `recoger.py` + `dialogo_recogida.py`: búsqueda, identificación por NIF de
  clientes conocidos (archivo, confirmados y suite), propuesta revisable,
  movimiento con comprobación de huella, `_Duplicados`, deshacer.
- `expediente.py` + `dialogo_expedientes.py`: PDF unificados con índice y
  marcadores, Excel, `Resumen AAAA.pdf` desde el historial de exportadas
  (ahora guarda base/IVA/recargo/retención por factura) y ZIP.
- Al exportar: copia fechada del Excel en `Excel Aplifisa` y expediente
  actualizado.

## v1.14.0 — revisión de fiabilidad del 24/09/2026

Estado: **implementado**. Análisis de 16 puntos aceptado por el usuario
(«dale con todo»):

1. Cuentas sin inventar: 629 (G22) por descarte y en ámbar; 705 con subclave
   mala corrige la subclave, no la cuenta (`procesar.concepto_propuesto`).
2. Tipos de IVA existentes, fecha futura en rojo, NIF por tipo de entidad,
   K/L/M e intracomunitarios (`validacion.py`). Las fechas antiguas NO se
   marcan (criterio del usuario para requerimientos).
3. Doble lectura 3.8-flash + 3.7-flash comparada campo a campo
   (`doble_lectura.py`), resoluble desde la ficha.
4. `response_json_schema`, `thinking_level LOW`, modelos fijos configurables
   y sin alias; tarifas editables (la de 3.8-flash la debe dar el usuario).
5. Historial de facturas exportadas por cliente (`historial.py`).
6. Los NIF se aprenden al exportar, no al leer.
7. Sin crédito se cancela el lote; se cuenta lo pagado por hojas fallidas.
8. Revalidación en una pasada (300 líneas: 5,9 s → 0,18 s).
9. 10 hojas en paralelo (`hilos_lectura` en ajustes.json).
10. Directorio común de clientes de la suite (`suite.py`).
11. Avisos dentro de la ventana con Deshacer (`banda_avisos.py`).
12. Ficha de la factura junto al documento (`panel_ficha.py`).
13. Estados Verificada / Sin verificar / Revisar / Error.
14. Estética de la suite: cinta por grupos, lista de bloques, barra de estado,
    barra de título #1F3550. Se mantiene el orden de columnas de la 1.13.23.
15. Incidencias con su campo y gravedad (`validacion.Incidencia`).
16. Publicación manual desde Actions con la casilla «publicar»; corregida la
    suma del Excel en modo numérico.

## Próxima actualización después de v1.13.21 — petición del 11/09/2026

Estado: **implementado**. El rediseño de la tabla, la visibilidad de campos y
el orden contable se incorporaron en v1.13.23. El listado PDF imprimible de
comprobación de totales se incorporó en v1.13.24.

### Campos siempre visibles y orden estable

Implementado en v1.13.23.

- El usuario no quiere tener que abrir «Mostrar todos los campos contables».
  La vista habitual debe mostrar directamente todos los campos de su captura.
- Orden de izquierda a derecha indicado por esa captura:
  **Estado → Nombre → Nº Factura → Fecha → Base → Cuota → Retención → Total →
  Tipo → NIF → % IVA → Cuenta → GXX → Base IRPF → % IRPF**.
- Mantener ese orden y esa visibilidad al arrancar, restaurar una sesión,
  cargar nuevos lotes, filtrar y cambiar el tamaño de la ventana. No aplicar
  una vista simplificada que vuelva a ocultarlos ni otra reordenación estética.
- Los campos adicionales de recargo de equivalencia y otros conceptos
  especiales deben aparecer automáticamente cuando haya datos aplicables en
  el lote, y no ocupar espacio cuando no los haya. Los campos habituales
  anteriores, incluido IRPF, permanecen visibles.
- Conservar el acabado claro Azul asesoría y todos los controles de revisión.

### Listado de comprobación de totales

Implementado en v1.13.24.

- Añadir una salida en forma de listado imprimible de la comprobación de
  totales, para poder puntearlo y contrastarlo con el registro de Aplifisa.
  Actualmente «Copiar resumen» no cubre por sí solo esta petición.
- Respetar el alcance acordado: todo el lote cargado y, si se está filtrando,
  su resultado identificado por separado, sin confundir las dos sumas.
- Reflejar el periodo y la separación dentro/fuera de trimestre cuando
  proceda; incluir los importes y recuentos que se muestran en el resumen.
- Propuesta técnica a concretar al implementar: vista previa e impresión con
  opción de guardar en PDF. No se ha solicitado una exportación Excel adicional.

Referencia: captura aportada por el usuario en esta conversación. Se conserva
solo la especificación de las columnas; no incorporar la captura ni sus datos
fiscales al repositorio público.

---

> Documento de trabajo para la próxima sesión. Objetivo: implementar las mejoras
> acordadas para maximizar la precisión ("que ningún error pase sin ser
> detectado") y dejar preparados los extras.
>
> Estado al escribir esto: **v1.0.1 publicada** (2026-07-13). Código en
> `Soakkk/Facturas-a-Aplifisa`, instaladores en `Soakkk/Facturas-a-Aplifisa-releases`.
> La app funciona end-to-end: PDF/imágenes → Gemini (paralelo x6, JPEG) →
> autodetección de cliente por NIF → tabla de revisión con semáforo y miniatura →
> gastos.xlsx / ventas.xlsx para Aplifisa.

## Filosofía

El 100% absoluto no existe con papel escaneado. La meta es doble:
1. Maximizar aciertos automáticos (verde).
2. Que TODO lo dudoso acabe en ámbar con el motivo señalado. Nada silencioso.

---

## Fase 1 — v1.1.0 (prioridad, en este orden)

### 1. Memoria de contrapartes (la de mayor impacto)
Base de datos local de proveedores/clientes ya confirmados por el usuario.

- **Dónde:** nuevo `facturas_excel/contrapartes.py` + SQLite en
  `%APPDATA%\FacturasAplifisa\contrapartes.db` (usar `dir_datos()` de `rutas.py`).
- **Esquema:** `nif (PK), nombre_bueno, cuenta_habitual, gxx_habitual,
  veces_visto, ultima_vez`.
- **Al exportar** (momento de confirmación humana): guardar/actualizar cada
  contraparte de las filas exportadas.
- **Al procesar un lote nuevo:**
  - NIF conocido → usar `nombre_bueno` y `cuenta_habitual` (pisando la
    propuesta de Gemini) y marcar la fila como "conocido" (tooltip).
  - Nombre ~igual (usar `_mismo_nombre` de `procesar.py`) pero **NIF distinto**
    → ámbar: "NIF no coincide con el histórico de este proveedor (¿OCR?)".
- **UI:** diálogo simple "Contrapartes" (gestión: ver/editar/borrar), estilo
  del catálogo de clientes de otros proyectos del usuario.

### 2. Doble lectura con consenso
Cada factura se lee 2 veces y se comparan campo a campo.

- **Dónde:** `extraccion.py` — método `extraer_consenso(img, ...)`:
  1ª pasada `gemini-flash-latest`, 2ª pasada `gemini-pro-latest`
  (modelos distintos = errores no correlacionados).
- **Comparar:** num_factura, fecha, NIFs, bases/cuotas/tipos, total.
  - Todo igual (tolerancia 0,01 en importes) → confianza real alta.
  - Discrepancia → ámbar con detalle: "Las dos lecturas no coinciden en X:
    lectura A / lectura B" y dejar en la celda el valor de la pasada Pro.
- **Coste:** ~2x por factura (sigue siendo céntimos). Hacerlo **opcional**
  (checkbox "Verificación doble" en la barra, activado por defecto).
- **Cuidado:** el paralelismo ya existe (HILOS=6); con doble pasada limitar a
  posibles rate limits del nivel 1 (reintentos ya implementados).

### 3. Historial anti-duplicados entre sesiones
- **Dónde:** misma SQLite; tabla `procesadas (hash_imagen, nif, num_factura,
  fecha, base, fecha_proceso)`. Hash = sha256 del JPEG.
- **Al cargar un lote:** si (nif+num_factura+base) o el hash ya existen →
  ámbar "Ya procesada el DD/MM/AAAA".
- No bloquear (puede ser legítimo reprocesar), solo avisar.

### 4. Escalado automático de dudosos
- Si tras la extracción una fila queda en ámbar/rojo por descuadre aritmético
  o `confianza: baja` → reintento automático con `gemini-pro-latest` y la
  página renderizada a **300 dpi** (en `pdf.py`, parámetro dpi por llamada).
- Si el reintento arregla el descuadre → verde con nota "verificada con Pro".
  Si no → se queda como estaba. Máximo 1 escalado por factura.

## Fase 2 — v1.2.x

### 5. Facturas multipágina
- Preguntar en el prompt: `"es_continuacion": true/false` (si la página no
  tiene cabecera de factura propia y parece continuar la anterior).
- En `procesar.py`, fusionar continuaciones con la página anterior (sumar
  líneas de IVA si procede, conservar el total de la última página).
- Probar con facturas reales de telefonía/eléctricas (suelen ser 2-3 páginas).

### 6. Lector de QR Verifactu / TicketBAI
- Librería: `zxing-cpp` (pip) o `pyzbar`. Leer QR de cada imagen ANTES de
  llamar a Gemini.
- Si hay QR AEAT (Verifactu): contiene NIF emisor, número, fecha y total
  exactos → usarlos como **verdad absoluta** y cruzar contra lo extraído
  (discrepancia → corregir con el QR y anotar). Campos que el QR no trae
  (bases/cuotas desglosadas, contraparte) siguen viniendo de Gemini.
- Cada vez más facturas lo llevarán (obligación Verifactu 2026+).

### 7. Sinergia con EscanerFotos
- Botón/flujo en EscanerFotos: "Enviar a Facturas a Aplifisa" (las imágenes ya
  mejoradas leen mejor que fotos crudas).
- Mínimo viable: que Facturas a Aplifisa acepte arrastrar y soltar (drag&drop)
  archivos a la ventana, y EscanerFotos solo tenga que abrir la app.

## Mejoras menores de UI (cuando toque)
- Icono propio de la app (.ico) para exe + instalador.
- Botón "Cargar carpeta completa" y recordar la última carpeta usada.
- Subir HILOS si el nivel de la API lo permite.
- Resumen previo a exportar (nº facturas, suma de bases/cuotas) para cuadrar
  contra lo esperado del trimestre.

## Archivo digital limpio por cliente (fase posterior)

Objetivo: conservar los PDF que respaldan exactamente lo registrado, sin
mezclar escaneos incompletos ni bloques que todavía tengan incidencias.

- Estructura propuesta:
  `<archivo digital>/<Gastos|Ingresos>/<CLIENTE> <EJERCICIO>/<1T|2T|3T|4T|ANUAL>/`.
- El periodo se deduce de las fechas del bloque: un solo trimestre usa `1T` a
  `4T`; si abarca varios trimestres del mismo ejercicio, usa `ANUAL`.
- Si un PDF mezcla ejercicios, no se archiva automáticamente: antes habrá que
  dividirlo o confirmar expresamente dónde debe quedar.
- Un bloque solo puede archivarse después de exportar si **todas** sus filas
  están verdes, el PDF original existe y el usuario lo confirma como revisado.
- Se copia el original (no se mueve) y se calcula SHA-256 para no duplicarlo.
- Guardar junto al PDF un índice que relacione archivo, facturas exportadas,
  cliente, ejercicio, periodo y hash. Así se puede demostrar qué documento
  respalda cada registro.
- Si faltan páginas, hay filas ámbar/rojas, varios clientes o el Excel no se
  generó correctamente, el bloque queda fuera del archivo definitivo.

## Extras open source (independientes, recomendar/instalar si el usuario quiere)
- **Paperless-ngx** — archivo documental con OCR y búsqueda (por cliente/año).
- **NAPS2** — escaneo por lotes en Windows directo a PDF.
- **Stirling-PDF** — trocear/unir/rotar PDFs autoalojado.
- **ocrmypdf** — capa de texto buscable en PDFs escaneados.
- **Tesseract/PaddleOCR** — segunda opinión OCR local (alternativa barata al
  consenso con dos modelos; valorar tras medir la fase 1).
- **invoice2data** — plantillas regex para proveedores muy repetitivos.

## Flecos pendientes del usuario
- [ ] Confirmar la subclave **GXX del combustible** en su Aplifisa (ahora G18
      provisional en `conceptos.py` / prompt de `extraccion.py`).
- [ ] Probar la velocidad real del lote con la key de pago (paralelo x6).
- [ ] Decidir si activar "Verificación doble" por defecto tras ver el coste real.

## Recordatorios técnicos para la sesión
- Venv del proyecto: `.venv` (Python 3.11). El `python` global es 3.7, no usar.
- La API key se lee con `claves.leer_api_key()` (keyring; el usuario la guardó
  desde la app). No pedirla ni pegarla en el chat.
- Release: subir versión en `facturas_excel/__init__.py` y ejecutar
  `python scripts/release.py` (lint → PyInstaller → Inno Setup → GitHub release).
  Preguntar al usuario antes de publicar.
- **Nunca** nombres/NIFs de clientes reales en código, docs o commits: el repo
  es público. Cachés, PDFs y xlsx están en `.gitignore`.
- Probar la UI en headless con `QT_QPA_PLATFORM=offscreen` y
  `VentanaPrincipal(comprobar_updates=False)` (evita el exit 9 por QThread vivo).

