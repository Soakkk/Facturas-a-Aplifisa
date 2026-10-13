"""Genera el archivo .xlsx en la maqueta exacta que espera el gestor fiscal,
colocando cada campo en la columna que indica la configuracion (ConfigColumnas).
"""

from __future__ import annotations

import io
import math
from datetime import date
from typing import List

from openpyxl import Workbook
from openpyxl.utils import column_index_from_string

from .config_columnas import ConfigColumnas, ETIQUETA_CABECERA
from .modelo import CAMPOS_IMPORTE, CAMPOS_PORCENTAJE, Factura
from .texto import sin_invisibles

# Modo en que se escriben los numeros en las celdas:
#   "texto"  -> "1234,56" como texto (separador decimal coma)
#   "numero" -> 1234.56 como numero real de Excel
MODO_TEXTO = "texto"
MODO_NUMERO = "numero"

# Aplifisa rechaza el apunte si el nombre de la cuenta pasa de 40 caracteres
# ("El tamano del nombre excede el maximo").
MAX_NOMBRE = 40


# Palabras que no deben quedar al final de un nombre recortado.
_CONECTORES = {"DE", "DEL", "LA", "EL", "LOS", "LAS", "Y", "E"}


def _recortar_nombre(nombre: str) -> str:
    """Recorta a MAX_NOMBRE sin dejar restos feos: corta por palabra entera si
    apenas cuesta caracteres ('... IBERIA, S' -> '... IBERIA') y si no corta en
    seco, que conserva mas informacion para identificar la cuenta."""
    nombre = " ".join(str(nombre).split())
    if len(nombre) <= MAX_NOMBRE:
        return nombre
    corte = nombre[:MAX_NOMBRE]
    if not nombre[MAX_NOMBRE].isspace():
        hueco = corte.rfind(" ")
        # Retroceder solo si se pierden pocas letras; si no, corte seco.
        if hueco >= MAX_NOMBRE - 6:
            corte = corte[:hueco]
    corte = corte.rstrip(" ,.-")
    palabras = corte.split(" ")
    if len(palabras) > 1 and palabras[-1].upper() in _CONECTORES:
        corte = " ".join(palabras[:-1])
    return corte.rstrip(" ,.-")


def _fmt_importe_texto(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def _fmt_porcentaje_texto(valor: float) -> str:
    # 21.0 -> "21" ; 21.5 -> "21,5"
    if float(valor).is_integer():
        return str(int(valor))
    return f"{valor:g}".replace(".", ",")


def _valor_celda(campo: str, valor, modo: str):
    """Devuelve el valor listo para escribir en la celda segun el tipo de campo."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, str):
        # Un carácter de control en un nombre tumbaba la exportación entera
        # (openpyxl no lo admite). La validación ya lo ha señalado en ámbar.
        valor = sin_invisibles(valor)
        if not valor:
            return None

    # Aplifisa: el NIF de la cuenta no puede llevar puntos, espacios ni guiones.
    if campo == "nif":
        return str(valor).strip().upper().replace(".", "").replace(" ", "").replace("-", "")

    if campo == "nombre":
        return _recortar_nombre(valor)

    if campo in ("fecha", "fecha_operacion", "fecha_deduccion"):
        # Siempre dd/mm/aaaa: «2026-03-05» o «05/03/26» podían llegar tal cual.
        from .validacion import normalizar_fecha
        return normalizar_fecha(str(valor).strip())

    es_numerico = campo in CAMPOS_IMPORTE or campo in CAMPOS_PORCENTAJE
    if not es_numerico:
        return str(valor)

    try:
        valor = float(valor)
    except OverflowError:           # un entero de cientos de cifras
        return None
    if not math.isfinite(valor):
        # Ni «nan» ni «inf» en el Excel de Aplifisa: la celda queda vacía (la
        # fila ya sale en rojo, «Importe imposible»).
        return None
    if modo == MODO_NUMERO:
        return round(valor, 2)

    # modo texto
    if campo in CAMPOS_PORCENTAJE:
        return _fmt_porcentaje_texto(valor)
    return _fmt_importe_texto(valor)


# ------------------------------------------- tipo de operación: IRPF/IVA
# Un cliente en ESTIMACIÓN DIRECTA tiene que llevar sus ingresos y gastos en
# Aplifisa como «IRPF/IVA» para que cuenten en su IRPF; importados salían
# todos «Sólo IVA» y había que cambiarlos a mano uno a uno.
#
# La pantalla de importación de Aplifisa («Desde fichero Excel») no tiene
# ningún ajuste ni columna para el tipo de operación (el desplegable de al
# lado de COMPRAS/GASTOS es IVA/IGIC): lo decide SOLO la Base IRPF. Lo
# comprobó el usuario en octubre de 2026 importando filas de prueba:
#   - Base IRPF vacía (como siempre)                      -> «Sólo IVA»;
#   - solo % IRPF = 0, o solo cuota IRPF = 0 (sin base)    -> «Sólo IVA»;
#   - Base IRPF = la base imponible, con % y cuota a 0     -> «IRPF/IVA»;
#   - Base IRPF = la base imponible, sin % ni cuota        -> «IRPF/IVA», y el
#     bloque I.R.P.F. del apunte queda con la base, sin tipo ni cuota.
# Así que, para esos clientes, cada línea lleva en Base IRPF la base que va
# en el Excel, y el % y la cuota se quedan como estén (vacíos). Las
# facturas con retención ya traen su base, % y cuota: no se tocan.

def _hay(valor) -> bool:
    if valor is None or valor == "":
        return False
    try:
        return abs(float(valor)) >= 0.005
    except (TypeError, ValueError, OverflowError):
        return True         # algo raro: esa factura, mejor no tocarla


def _con_retencion(factura: Factura) -> bool:
    """La línea trae algo de IRPF (una retención, o al menos su base)."""
    return any(_hay(getattr(factura, campo)) for campo in
               ("base_irpf", "pct_irpf", "cuota_irpf"))


# Las bases que pueden ir en el Excel: la imponible (también la de una línea
# exenta al 0 %, y la de una «por el total», que ya es el total), y la sujeta
# al 0 % y la no sujeta si la configuración les da columna.
_BASES = ("base_iva", "base_sujeta_cero", "no_sujeta")


def base_irpf_directa(factura: Factura,
                      config: ConfigColumnas | None = None,
                      suplido: bool = False) -> float | None:
    """La Base IRPF que lleva en el Excel una línea de un cliente en
    estimación directa que no trae retención: la base con la que va al Excel.

    Nada (None) para la línea de un suplido (sumas pagadas en nombre y por
    cuenta del cliente, art. 78.Tres.3.º de la Ley del IVA: no son la
    operación facturada) ni para una línea de importe 0, que no tiene nada
    que imputar. Con ``suplido``, también la del suplido: es la de una
    factura que no trae otra cosa (ver datos_para_aplifisa)."""
    if getattr(factura, "es_suplido", False) and not suplido:
        return None
    columnas = config.columnas if config is not None else None
    base = 0.0
    for campo in _BASES:
        valor = getattr(factura, campo, None)
        if (columnas is None or campo in columnas) and valor is not None:
            try:
                valor = float(valor)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(valor):
                base += valor
    base = round(base, 2)
    return base if abs(base) >= 0.005 else None


def datos_para_aplifisa(
    facturas: List[Factura],
    config: ConfigColumnas | None = None,
    estimacion_directa: bool = False,
) -> List[dict]:
    """Lo que va en cada fila del Excel: {campo: valor}, una por línea.

    Lo usan tanto la escritura como la comprobación (verificar_excel), para
    que las dos digan lo mismo. Sin estimación directa son los datos de la
    línea tal cual. En directa, cada línea sin Base IRPF lleva la suya (ver
    arriba), salvo las de una factura con retención: esa ya trae su base, %
    y cuota (en su primera línea, la de toda la factura) y no se toca
    ninguna de sus líneas; poner aparte la base de las demás contaría dos
    veces esa parte en el IRPF."""
    filas = [factura.campos_dict() for factura in facturas]
    if not estimacion_directa:
        return filas
    from .control_facturas import clave_documento
    retenidas = {clave_documento(f) for f in facturas if _con_retencion(f)}
    con_base = set()
    for factura, datos in zip(facturas, filas):
        if clave_documento(factura) in retenidas:
            continue
        base = base_irpf_directa(factura, config)
        if base is not None:
            datos["base_irpf"] = base
            con_base.add(clave_documento(factura))
    # Una factura que solo trae suplidos (la de una gestoría con las tasas
    # que pagó por el cliente) se quedaba sin ninguna Base IRPF: el apunte
    # entraba «Sólo IVA», como con las columnas de IRPF vacías. Esa, con la
    # base del suplido, que es su gasto.
    for factura, datos in zip(facturas, filas):
        clave = clave_documento(factura)
        if clave in retenidas or clave in con_base:
            continue
        base = base_irpf_directa(factura, config, suplido=True)
        if base is not None:
            datos["base_irpf"] = base
    return filas


def exportar_excel(
    facturas: List[Factura],
    config: ConfigColumnas,
    ruta_salida: str,
    modo_numeros: str = MODO_TEXTO,
    solo_nuevo: bool = False,
    estimacion_directa: bool = False,
) -> str:
    """Escribe el .xlsx y devuelve la ruta.

    - Fila 1: cabecera (si config.incluye_cabecera).
    - Datos desde config.primera_fila.
    - Cada campo va a la columna (letra) que diga config.columnas.
    - Con ``solo_nuevo`` nunca pisa un archivo que ya exista (lanza
      FileExistsError): la exportación elige antes un nombre libre.
    - Con ``estimacion_directa`` (cliente en directa) cada línea lleva su
      Base IRPF, para que entre en Aplifisa como «IRPF/IVA» (ver
      datos_para_aplifisa).
    """
    wb = Workbook()
    # Aplifisa interpreta la mera presencia de <workbookProtection /> como si
    # el libro estuviera protegido, aunque openpyxl lo escriba vacio y Excel
    # no muestre ninguna contraseña. No serializar esa etiqueta en absoluto.
    wb.security = None
    ws = wb.active
    ws.title = "Facturas"

    # Cabecera
    if config.incluye_cabecera:
        for campo, letra in config.columnas.items():
            col = column_index_from_string(letra)
            ws.cell(row=1, column=col, value=ETIQUETA_CABECERA.get(campo, campo))

    # Datos
    fila = config.primera_fila
    for datos in datos_para_aplifisa(facturas, config, estimacion_directa):
        for campo, letra in config.columnas.items():
            valor = _valor_celda(campo, datos.get(campo), modo_numeros)
            if valor is not None:
                col = column_index_from_string(letra)
                celda = ws.cell(row=fila, column=col, value=valor)
                # Forzar texto cuando toca, para que Excel no reinterprete la coma
                if modo_numeros == MODO_TEXTO and (
                    campo in CAMPOS_IMPORTE or campo in CAMPOS_PORCENTAJE
                ):
                    celda.number_format = "@"
        fila += 1

    # El libro se prepara en memoria y se escribe de una vez: si la escritura
    # falla, el archivo queda cerrado y se puede borrar (en Windows un archivo
    # abierto no se deja borrar). Así tampoco queda ningún descriptor abierto:
    # Aplifisa necesita acceso exclusivo para importarlo.
    contenido = io.BytesIO()
    try:
        wb.save(contenido)
    finally:
        wb.close()
    with open(ruta_salida, "xb" if solo_nuevo else "wb") as fh:
        fh.write(contenido.getvalue())
    return ruta_salida


def verificar_excel(
    facturas: List[Factura],
    config: ConfigColumnas,
    ruta: str,
    modo_numeros: str = MODO_TEXTO,
    estimacion_directa: bool = False,
) -> List[str]:
    """Vuelve a LEER el Excel escrito y lo compara con lo que hay en pantalla.

    Es el ultimo paso antes de que los apuntes entren en Aplifisa, y hasta
    ahora era el unico que nadie comprobaba: si una columna se escribiera
    corrida, un importe se perdiera o faltara una linea, no se enteraba nadie
    hasta tener el problema dentro de la contabilidad.

    Devuelve la lista de diferencias (vacia = el archivo dice exactamente lo
    mismo que la tabla). Se le dice lo mismo que a exportar_excel
    (``estimacion_directa``): la Base IRPF de cada línea se compara con la
    que le toca.
    """
    from openpyxl import load_workbook

    problemas: List[str] = []
    libro = None
    try:
        libro = load_workbook(ruta, data_only=True)
        hoja = libro.active
    except Exception as e:  # archivo abierto en Excel, disco lleno...
        return [f"No se pudo volver a abrir el archivo para comprobarlo: {e}"]

    try:
        escritas = hoja.max_row - config.primera_fila + 1
        if escritas != len(facturas):
            problemas.append(
                f"El archivo tiene {max(escritas, 0)} línea(s) y deberían ser "
                f"{len(facturas)}.")

        filas = datos_para_aplifisa(facturas, config, estimacion_directa)
        for i, (factura, datos) in enumerate(zip(facturas, filas)):
            fila = config.primera_fila + i
            for campo, letra in config.columnas.items():
                esperado = _valor_celda(campo, datos.get(campo), modo_numeros)
                escrito = hoja[f"{letra}{fila}"].value
                if esperado is None and (escrito is None or escrito == ""):
                    continue
                if str(escrito) != str(esperado):
                    problemas.append(
                        f"Línea {i + 1} ({factura.num_factura or 'sin nº'}), "
                        f"{ETIQUETA_CABECERA.get(campo, campo)}: el archivo pone "
                        f"«{escrito}» y debería poner «{esperado}».")
    finally:
        libro.close()
    return problemas


def totales_del_excel(config: ConfigColumnas, ruta: str) -> dict:
    """Suma los importes TAL COMO HAN QUEDADO en el archivo.

    Sirve para el contraste final: estos totales tienen que ser los mismos que
    los del resumen en pantalla.
    """
    from openpyxl import load_workbook

    suma = {"lineas": 0, "base_iva": 0.0, "cuota_iva": 0.0,
            "cuota_requiv": 0.0, "cuota_irpf": 0.0}
    libro = None
    try:
        libro = load_workbook(ruta, data_only=True)
        hoja = libro.active
    except Exception:
        return suma
    try:
        fila = config.primera_fila
        while fila <= hoja.max_row:
            vacia = True
            for campo in list(suma)[1:]:
                letra = config.columnas.get(campo)
                if not letra:
                    continue
                valor = hoja[f"{letra}{fila}"].value
                if valor in (None, ""):
                    continue
                vacia = False
                try:
                    if isinstance(valor, (int, float)):
                        # Modo numero: ya es un numero de Excel. Antes se le
                        # quitaba el punto decimal y 123.45 sumaba 12345.
                        suma[campo] += float(valor)
                    else:
                        suma[campo] += float(
                            str(valor).replace(".", "").replace(",", "."))
                except ValueError:
                    pass
            if (not vacia
                    or hoja[f"{config.columnas.get('fecha', 'B')}{fila}"].value):
                suma["lineas"] += 1
            fila += 1
    finally:
        libro.close()
    for campo in list(suma)[1:]:
        suma[campo] = round(suma[campo], 2)
    return suma


def ordenar_para_exportar(facturas: List[Factura], orden: str) -> List[Factura]:
    """Ordena los apuntes para el Excel.

    Aplifisa numera las facturas recibidas SEGUN ENTRAN, asi que el orden del
    archivo decide con que numero queda registrada cada factura:

    - "pdf": tal como estan (el orden del escaneo). El apunte nº 3 es la hoja 3.
      Es lo que hace falta en un requerimiento.
    - "fecha": de la mas antigua a la mas reciente, para el registro trimestral.

    Las lineas de una misma factura (varios tipos de IVA, o el suplido) NO se
    separan nunca: se ordenan juntas, por la primera.
    """
    if orden != "fecha":
        return list(facturas)

    from .validacion import fecha_de

    grupos: List[List[Factura]] = []
    indice = {}
    for f in facturas:
        clave = ((f.num_factura or "").strip().upper(), (f.nif or "").strip().upper())
        if clave in indice and grupos[indice[clave]]:
            grupos[indice[clave]].append(f)
        else:
            indice[clave] = len(grupos)
            grupos.append([f])

    def orden_grupo(par):
        i, grupo = par
        dia = fecha_de(grupo[0].fecha)
        # Sin fecha entendible: al final, sin cambiar su orden entre ellas.
        return (dia is None, dia or date.max, i)

    ordenados = sorted(enumerate(grupos), key=orden_grupo)
    return [f for _, grupo in ordenados for f in grupo]
