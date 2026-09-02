# Plan de mejoras — Facturas a Aplifisa (v1.1.0 y siguientes)

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

