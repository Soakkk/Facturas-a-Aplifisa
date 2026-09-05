"""Sistema visual «gris técnico» para Facturas a Aplifisa.

Sustituye a facturas_excel/estilo.py conservando los mismos nombres de objeto
(tarjeta, tituloSeccion, alerta, primario, exito, peligro, textoSuave,
cliente, visor, ficha), asi que no hay que tocar app.py ni los dialogos.

Claves del estilo: fondo gris claro, tarjetas blancas con borde marcado de
1.5 px, esquinas de 4 px, sin sombras, cabecera azul oscuro y cifras
monoespaciadas para que los importes queden alineados en columna.
"""

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

PAGE = "#EDEFF2"      # fondo de ventana
CARD = "#FFFFFF"      # tarjetas y tablas
SOFT = "#F4F6F8"      # filas alternas
HEAD = "#E4E8ED"      # cabecera de tabla
BAR = "#0F172A"       # barra de menu / cabecera
INK = "#0F172A"
MUTED = "#6A7484"
DIM = "#3F4A5C"
BORDER = "#B9C0CA"
ACCENT = "#0F4C81"        # azul del programa: botones y foco
ACCENT_HOVER = "#0C3D68"
ACCENT_FAINT = "#E7EEF5"
SUCCESS = "#1F6F43"
WARNING = "#8A5A00"
DANGER = "#A61B1B"

# Interfaz en Inter/Segoe; cifras y tablas en monoespaciada.
FUENTE_UI = '"Inter", "Segoe UI", sans-serif'
FUENTE_MONO = '"JetBrains Mono", "Cascadia Mono", "Consolas", monospace'

QSS = f"""
QWidget {{
    color: {INK};
    font-family: {FUENTE_UI};
    font-size: 13px;
}}
QMainWindow, QDialog, QMessageBox, QFileDialog {{ background: {PAGE}; }}

QMenuBar {{ background: {BAR}; color: #E6EAF0; border: none; padding: 2px 10px; }}
QMenuBar::item {{ padding: 7px 10px; border-radius: 3px; }}
QMenuBar::item:selected {{ background: rgba(255,255,255,0.14); }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 7px 24px 7px 10px; border-radius: 3px; }}
QMenu::item:selected {{ background: {ACCENT_FAINT}; color: {ACCENT}; }}

QFrame#tarjeta {{
    background: {CARD}; border: 1.5px solid {BORDER}; border-radius: 4px;
}}
QLabel#tituloSeccion {{
    color: {MUTED}; font-size: 11px; font-weight: 700;
    letter-spacing: 1.4px; text-transform: uppercase;
}}
QLabel#textoSuave {{ color: {MUTED}; font-size: 11px; }}
QLabel#cliente {{ color: {INK}; font-size: 15px; font-weight: 600; }}
QLabel#visor {{
    background: {SOFT}; color: {MUTED};
    border: 1px dashed {BORDER}; border-radius: 3px;
}}

QFrame#alerta {{
    background: #FBF3E2; border: 1px solid {WARNING}; border-radius: 3px;
}}
QLabel#alertaTitulo {{
    color: {WARNING}; font-size: 11px; font-weight: 700; letter-spacing: 1.4px;
}}
QLabel#alertaTexto {{ color: {INK}; font-size: 12px; }}

QPushButton {{
    background: {CARD}; color: {INK}; border: 1px solid {BORDER};
    border-radius: 3px; padding: 8px 13px; font-weight: 600;
    font-family: {FUENTE_MONO};
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_FAINT}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ background: {SOFT}; color: #A3AAB3; border-color: #D8DDE3; }}
QPushButton#primario {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QPushButton#primario:hover {{ background: {ACCENT_HOVER}; color: white; }}
QPushButton#exito {{ background: {SUCCESS}; color: white; border-color: {SUCCESS}; }}
QPushButton#exito:hover {{ background: #185634; color: white; }}
QPushButton#peligro {{ color: {DANGER}; }}
QPushButton#peligro:hover {{ border-color: {DANGER}; color: {DANGER}; }}

QLineEdit, QComboBox {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 3px;
    padding: 6px 8px; font-family: {FUENTE_MONO};
    selection-background-color: {ACCENT}; selection-color: white;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{
    background: {CARD}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_FAINT}; selection-color: {ACCENT};
}}

QTableWidget {{
    background: {CARD}; alternate-background-color: {SOFT};
    border: 1px solid {BORDER}; border-radius: 3px; gridline-color: #DDE2E7;
    selection-background-color: {ACCENT_FAINT}; selection-color: {INK};
    font-family: {FUENTE_MONO}; font-size: 12px;
}}
QHeaderView::section {{
    background: {HEAD}; color: {DIM}; border: none;
    border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER};
    padding: 8px 6px; font-weight: 700; font-size: 11px;
    letter-spacing: 0.8px; text-transform: uppercase;
}}
QProgressBar {{
    background: {HEAD}; border: none; border-radius: 2px;
    min-height: 8px; max-height: 8px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}
QStatusBar {{ background: {CARD}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QToolTip {{
    background: {CARD}; color: {INK};
    border: 1px solid {BORDER}; border-left: 3px solid {ACCENT};
    padding: 8px 10px;
}}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px 2px 2px 0; }}
QScrollBar::handle:vertical {{ background: #C3CAD2; border-radius: 2px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: #A6AFBA; }}
QScrollBar::handle:vertical:pressed {{ background: {ACCENT}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0 2px 2px 2px; }}
QScrollBar::handle:horizontal {{ background: #C3CAD2; border-radius: 2px; min-width: 36px; }}
QScrollBar::handle:horizontal:hover {{ background: #A6AFBA; }}
QScrollBar::handle:horizontal:pressed {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QFrame#ficha {{
    background: {CARD}; border: 1.5px solid {BORDER}; border-radius: 4px;
}}
QLabel#fichaTitulo {{
    font-size: 11px; font-weight: 700; letter-spacing: 1.4px;
    text-transform: uppercase; color: {DANGER};
}}
QLabel#fichaLinea {{ color: {INK}; font-size: 12px; }}
QLabel#fichaPie {{ color: {MUTED}; font-size: 11px; }}
"""

# Colores del semaforo, para COLOR_ESTADO en app.py
ESTADO_OK = SUCCESS
ESTADO_REVISAR = WARNING
ESTADO_ERROR = DANGER
ESTADO_REVISADO = ACCENT
ESTADO_MANUAL = MUTED

# Compatibilidad con el estilo anterior (app.py importa estos nombres).
NAVY = ACCENT
NAVY_HOVER = ACCENT_HOVER
WARNING_ = WARNING


def aplicar_tema(app):
    app.setStyle("Fusion")
    familias = set(QFontDatabase.families())
    familia = "JetBrains Mono" if "JetBrains Mono" in familias else (
        "Inter" if "Inter" in familias else "Segoe UI")
    app.setFont(QFont(familia, 9))
    paleta = app.palette()
    rol = QPalette.ColorRole
    paleta.setColor(rol.Window, QColor(PAGE))
    paleta.setColor(rol.WindowText, QColor(INK))
    paleta.setColor(rol.Base, QColor(CARD))
    paleta.setColor(rol.AlternateBase, QColor(SOFT))
    paleta.setColor(rol.Text, QColor(INK))
    paleta.setColor(rol.Button, QColor(CARD))
    paleta.setColor(rol.ButtonText, QColor(INK))
    paleta.setColor(rol.Highlight, QColor(ACCENT))
    paleta.setColor(rol.HighlightedText, QColor("#FFFFFF"))
    paleta.setColor(rol.PlaceholderText, QColor(MUTED))
    app.setPalette(paleta)
    app.setStyleSheet(QSS)
