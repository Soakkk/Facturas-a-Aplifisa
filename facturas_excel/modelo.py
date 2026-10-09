"""Modelo de una factura: los campos semanticos que luego se vuelcan al Excel
en la columna que indique la configuracion (XML) del gestor fiscal."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional


@dataclass
class Factura:
    # Identificacion
    num_factura: Optional[str] = None      # nº factura proveedor (compras) / justificante (ventas)
    fecha: Optional[str] = None            # fecha factura (dd/mm/aaaa)
    fecha_operacion: Optional[str] = None
    fecha_deduccion: Optional[str] = None
    concepto: Optional[str] = None

    # IVA
    base_iva: Optional[float] = None
    pct_iva: Optional[float] = None
    cuota_iva: Optional[float] = None

    # IRPF (retencion)
    base_irpf: Optional[float] = None
    pct_irpf: Optional[float] = None
    cuota_irpf: Optional[float] = None

    # Recargo de equivalencia
    base_requiv: Optional[float] = None
    pct_requiv: Optional[float] = None
    cuota_requiv: Optional[float] = None

    # Contraparte
    nif: Optional[str] = None
    nombre: Optional[str] = None

    # Campos SII / especiales (normalmente vacios)
    descripcion_sii: Optional[str] = None
    tipo_factura: Optional[str] = None
    clave_reg_esp: Optional[str] = None
    isp: Optional[str] = None
    base_sujeta_cero: Optional[float] = None
    recc: Optional[str] = None
    suplidos: Optional[float] = None
    no_sujeta: Optional[float] = None

    # --- soporte de revision / control de calidad (no se exporta) ---
    original_id: str = ""                  # SHA256 del original capturado para revisión
    edicion_manual: bool = False           # evita reconstrucciones que pisen correcciones
    documento_id: str = ""                 # une las líneas de una lectura concreta
    total_impreso: Optional[float] = None   # total que figura escrito en la factura
    origen_imagen: Optional[str] = None     # ruta del archivo escaneado del que sale
    pagina_origen: int = 0                  # primera página física de esta factura
    ultima_pagina_origen: int = 0           # última página si ocupa varias hojas
    lineas_factura: int = 1                 # lineas de IVA que tiene la factura entera
    subclave: Optional[str] = None          # GXX del concepto (obligatoria en la 628)
    descripcion_concepto: Optional[str] = None  # como lo llama Aplifisa
    es_suplido: bool = False                # esta linea es el suplido de su factura
    confianza_ia: Optional[str] = None      # alta/media/baja informada por Gemini
    revision_confirmada: bool = False       # una persona comprobo el aviso ambar
    # Una persona corrigió a mano un dato de la factura: cuenta como revisada
    # («✎ Corregida»), salvo que tras la corrección el total no cuadre.
    revision_corregida: bool = False
    # Los avisos que tenía la factura cuando la corrigió: solo esos se dan
    # por vistos. Uno NUEVO (un NIF mal tecleado, una fecha fuera del
    # trimestre…) la deja otra vez pendiente.
    avisos_vistos: tuple = ()
    # Motivo por el que conviene mirarla antes de exportar (bien de inversión,
    # suplido, sustituida…). Desde la 1.17.1 NO la aparta: queda en ámbar con
    # ese motivo y, tras «Marcar revisada», se exporta como las demás. El
    # nombre se conserva por las sesiones guardadas.
    tratamiento_manual: Optional[str] = None
    iva_incluido_en_base: bool = False       # régimen de recargo: gasto por total
    eliminada: bool = False                  # retirada del lote por el usuario
    tipo_revision: Optional[str] = None      # gasto/venta corregido en la tabla
    # Doble lectura: "doble" si dos modelos leyeron la hoja, "simple" si solo
    # uno. Las discrepancias son las diferencias sin resolver entre ambos.
    verificacion: str = ""
    discrepancias: tuple = ()
    # Hojas exactas de la factura cuando se unieron a mano (pueden ser de
    # archivos distintos o no seguidas): ((origen, página), ...).
    paginas_documento: tuple = ()
    # Lo que dice el propio documento (1.24): qué es (factura, proforma,
    # albarán…), en qué moneda va y qué mención de IVA trae (inversión del
    # sujeto pasivo, intracomunitaria, exenta…). Para avisar según la ley.
    tipo_documento: Optional[str] = None
    moneda: Optional[str] = None
    mencion_iva: Optional[str] = None
    # Gasto cuyo IVA puede no ser deducible (art. 96 de la Ley del IVA):
    # restauración, regalos, alimentos y tabaco, joyas, espectáculos.
    posible_no_deducible: Optional[str] = None
    # La factura de gasto no trae el NIF del cliente (un tique): sin él no
    # se puede deducir el IVA (art. 97).
    sin_nif_destinatario: bool = False
    # Una persona ha decidido registrarla por el total (IVA no deducible).
    no_deducible: bool = False
    # Nº de la factura que esta rectifica o sustituye, si lo dice.
    rectifica_a: str = ""
    # El nombre llegó con un carácter invisible y no se pudo recuperar la
    # letra: el que quedó sin ella. Si nadie lo corrige, no se aprende.
    nombre_sin_letra: str = ""
    # (con varios tipos de IVA, esta fila es solo UNA parte: su base no puede
    #  cuadrar ella sola con el total impreso, que es el de la factura entera)

    def campos_dict(self) -> dict:
        """Devuelve {nombre_campo: valor} solo de los campos exportables."""
        excluidos = {"original_id", "edicion_manual", "documento_id", "total_impreso", "origen_imagen", "pagina_origen",
                     "ultima_pagina_origen", "lineas_factura",
                     "subclave", "descripcion_concepto", "es_suplido",
                     "confianza_ia", "revision_confirmada", "revision_corregida",
                     "avisos_vistos",
                     "tratamiento_manual", "iva_incluido_en_base", "eliminada",
                     "tipo_revision", "verificacion", "discrepancias",
                     "paginas_documento", "tipo_documento", "moneda",
                     "mencion_iva", "posible_no_deducible",
                     "sin_nif_destinatario", "no_deducible", "rectifica_a",
                     "nombre_sin_letra"}
        return {f.name: getattr(self, f.name) for f in fields(self)
                if f.name not in excluidos}


# Campos que representan importes en euros (formato 2 decimales).
CAMPOS_IMPORTE = {
    "base_iva", "cuota_iva", "base_irpf", "cuota_irpf",
    "base_requiv", "cuota_requiv", "base_sujeta_cero", "suplidos", "no_sujeta",
}
# Campos que representan porcentajes.
CAMPOS_PORCENTAJE = {"pct_iva", "pct_irpf", "pct_requiv"}
