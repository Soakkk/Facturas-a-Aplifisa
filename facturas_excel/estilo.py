"""Sistema visual compartido con el Generador de avisos fiscales.

La interfaz usa superficies claras, azul marino para la navegación y las
acciones principales, y estados semánticos discretos para la revisión.
"""

from PySide6.QtGui import QColor, QPalette

NAVY = "#0B3159"
NAVY_HOVER = "#082745"
INK = "#1E293B"
MUTED = "#64748B"
PAGE = "#F7F6F3"
CARD = "#FFFFFF"
SOFT = "#F8FAFC"
BORDER = "#DCE2E8"
SUCCESS = "#2E6B43"
WARNING = "#A16207"
DANGER = "#B42318"

QSS = f"""
QWidget {{
    color: {INK};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog, QMessageBox, QFileDialog {{ background: {PAGE}; }}
QMenuBar {{
    background: {NAVY}; color: white; border: none; padding: 2px 10px;
}}
QMenuBar::item {{ padding: 7px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: rgba(255,255,255,0.14); }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; padding: 5px; }}
QMenu::item {{ padding: 7px 24px 7px 10px; border-radius: 4px; }}
QMenu::item:selected {{ background: #EDF4FA; color: {NAVY}; }}

QFrame#tarjeta {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px;
}}
QLabel#tituloSeccion {{ color: #102A4C; font-size: 17px; font-weight: 700; }}
QFrame#alerta {{
    background: #FEF3F2; border: 1px solid {DANGER};
    border-left: 5px solid {DANGER}; border-radius: 6px;
}}
QLabel#alertaTitulo {{ color: {DANGER}; font-size: 14px; font-weight: 700; }}
QLabel#alertaTexto {{ color: #7A271A; font-size: 12px; }}
QLabel#textoSuave {{ color: {MUTED}; font-size: 11px; }}
QLabel#cliente {{ color: {NAVY}; font-size: 14px; font-weight: 700; }}
QLabel#visor {{
    background: #F1F4F7; color: {MUTED};
    border: 1px dashed #BCC8D4; border-radius: 8px;
}}

QPushButton {{
    background: {CARD}; color: {INK}; border: 1px solid #C9D2DC;
    border-radius: 7px; padding: 8px 13px; font-weight: 600;
}}
QPushButton:hover {{ background: #F4F8FB; border-color: #9DB3CF; color: {NAVY}; }}
QPushButton:pressed {{ background: #E8EFF6; }}
QPushButton:focus {{ border-color: {NAVY}; }}
QPushButton:disabled {{ background: #F3F4F6; color: #A3AAB3; border-color: #E0E3E7; }}
QPushButton#primario {{ background: {NAVY}; color: white; border-color: {NAVY}; }}
QPushButton#primario:hover {{ background: {NAVY_HOVER}; }}
QPushButton#exito {{ background: {SUCCESS}; color: white; border-color: {SUCCESS}; }}
QPushButton#peligro {{ color: {DANGER}; }}

QLineEdit, QComboBox {{
    background: {CARD}; border: 1px solid #C9D2DC; border-radius: 6px;
    padding: 6px 8px; selection-background-color: {NAVY};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {NAVY}; }}
QComboBox QAbstractItemView {{
    background: {CARD}; border: 1px solid {BORDER};
    selection-background-color: #E8F0F8; selection-color: {NAVY};
}}

QTableWidget {{
    background: {CARD}; alternate-background-color: #FAFCFE;
    border: 1px solid {BORDER}; border-radius: 7px; gridline-color: #E8EDF2;
    selection-background-color: #E6EFF8; selection-color: {INK};
}}
QHeaderView::section {{
    background: #EEF3F7; color: #405469; border: none;
    border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER};
    padding: 8px 6px; font-weight: 700;
}}
QProgressBar {{
    background: #E6EBF0; border: none; border-radius: 5px;
    min-height: 9px; max-height: 9px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {NAVY}; border-radius: 5px; }}
QStatusBar {{ background: {CARD}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QToolTip {{
    background: {CARD}; color: {INK};
    border: 1px solid #C4CFDB; border-left: 4px solid {NAVY};
    padding: 8px 10px;
}}

/* Barras de desplazamiento: finas, redondeadas y sin los botones de flecha,
   que en una tabla larga solo estorban. */
QScrollBar:vertical {{
    background: transparent; width: 12px; margin: 2px 2px 2px 0;
}}
QScrollBar::handle:vertical {{
    background: #C3CEDA; border-radius: 5px; min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{ background: #9DB0C6; }}
QScrollBar::handle:vertical:pressed {{ background: {NAVY}; }}
QScrollBar:horizontal {{
    background: transparent; height: 12px; margin: 0 2px 2px 2px;
}}
QScrollBar::handle:horizontal {{
    background: #C3CEDA; border-radius: 5px; min-width: 36px;
}}
QScrollBar::handle:horizontal:hover {{ background: #9DB0C6; }}
QScrollBar::handle:horizontal:pressed {{ background: {NAVY}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Ficha de incidencias de una fila (se abre al pulsar el semaforo). */
QFrame#ficha {{
    background: {CARD}; border: 1px solid #C4CFDB; border-radius: 8px;
}}
QLabel#fichaTitulo {{ font-size: 14px; font-weight: 700; }}
QLabel#fichaLinea {{ color: {INK}; font-size: 12px; }}
QLabel#fichaPie {{ color: {MUTED}; font-size: 11px; }}
"""


def aplicar_tema(app):
    app.setStyle("Fusion")
    paleta = app.palette()
    rol = QPalette.ColorRole
    paleta.setColor(rol.Window, QColor(PAGE))
    paleta.setColor(rol.WindowText, QColor(INK))
    paleta.setColor(rol.Base, QColor(CARD))
    paleta.setColor(rol.AlternateBase, QColor(SOFT))
    paleta.setColor(rol.Text, QColor(INK))
    paleta.setColor(rol.Button, QColor(CARD))
    paleta.setColor(rol.ButtonText, QColor(INK))
    paleta.setColor(rol.Highlight, QColor(NAVY))
    paleta.setColor(rol.HighlightedText, QColor("#FFFFFF"))
    paleta.setColor(rol.PlaceholderText, QColor(MUTED))
    app.setPalette(paleta)
    app.setStyleSheet(QSS)
