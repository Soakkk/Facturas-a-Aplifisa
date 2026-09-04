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
    total_impreso: Optional[float] = None   # total que figura escrito en la factura
    origen_imagen: Optional[str] = None     # ruta del archivo escaneado del que sale
    lineas_factura: int = 1                 # lineas de IVA que tiene la factura entera
    subclave: Optional[str] = None          # GXX del concepto (obligatoria en la 628)
    descripcion_concepto: Optional[str] = None  # como lo llama Aplifisa
    es_suplido: bool = False                # esta linea es el suplido de su factura
    confianza_ia: Optional[str] = None      # alta/media/baja informada por Gemini
    revision_confirmada: bool = False       # una persona comprobo el aviso ambar
    tratamiento_manual: Optional[str] = None  # fuera del flujo rutinario
    iva_incluido_en_base: bool = False       # régimen de recargo: gasto por total
    eliminada: bool = False                  # retirada del lote por el usuario
    tipo_revision: Optional[str] = None      # gasto/venta corregido en la tabla
    # (con varios tipos de IVA, esta fila es solo UNA parte: su base no puede
    #  cuadrar ella sola con el total impreso, que es el de la factura entera)

    def campos_dict(self) -> dict:
        """Devuelve {nombre_campo: valor} solo de los campos exportables."""
        excluidos = {"total_impreso", "origen_imagen", "lineas_factura",
                     "subclave", "descripcion_concepto", "es_suplido",
                     "confianza_ia", "revision_confirmada",
                     "tratamiento_manual", "iva_incluido_en_base", "eliminada",
                     "tipo_revision"}
        return {f.name: getattr(self, f.name) for f in fields(self)
                if f.name not in excluidos}


# Campos que representan importes en euros (formato 2 decimales).
CAMPOS_IMPORTE = {
    "base_iva", "cuota_iva", "base_irpf", "cuota_irpf",
    "base_requiv", "cuota_requiv", "base_sujeta_cero", "suplidos", "no_sujeta",
}
# Campos que representan porcentajes.
CAMPOS_PORCENTAJE = {"pct_iva", "pct_irpf", "pct_requiv"}
