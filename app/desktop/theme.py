"""Complete, centralized light/dark palettes for the application."""
from qgis.PyQt.QtGui import QColor, QPalette


THEMES = {
    'light': dict(bg='#f3f6f4', surface='#ffffff', panel='#f8faf9', text='#17372a',
                  muted='#687b71', border='#dde6e0', accent='#167d53', soft='#e6f4ec',
                  hover='#eef5f0', map='#eaf0eb', line='#50645a', shadow='#d8e5dc'),
    'dark': dict(bg='#0d1716', surface='#14221f', panel='#192b26', text='#e6f0e9',
                 muted='#9db3a7', border='#2b4037', accent='#78d6a5', soft='#244b39',
                 hover='#213b30', map='#0c1918', line='#adc6b6', shadow='#13231d'),
}


def qt_palette(colors):
    palette = QPalette()
    for role, value in {
        QPalette.Window: colors['surface'], QPalette.WindowText: colors['text'],
        QPalette.Base: colors['surface'], QPalette.AlternateBase: colors['panel'],
        QPalette.Text: colors['text'], QPalette.Button: colors['panel'],
        QPalette.ButtonText: colors['text'], QPalette.Highlight: colors['accent'],
        QPalette.HighlightedText: colors['bg'], QPalette.ToolTipBase: colors['surface'],
        QPalette.ToolTipText: colors['text'], QPalette.Link: colors['accent'],
    }.items():
        palette.setColor(role, QColor(value))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors['muted']))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors['muted']))
    return palette


def stylesheet(c):
    return f'''
    QWidget {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 14px; }}
    QMainWindow, #Root, QDialog {{ background: {c['bg']}; }}
    #Header {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
    #Sidebar {{ background: {c['surface']}; border-right: 1px solid {c['border']}; }}
    #MapFrame {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    #MapHeader {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
    #MeasurePanel {{ background: {c['soft']}; border-bottom: 1px solid {c['border']}; }}
    #Footer {{ background: {c['surface']}; border-top: 1px solid {c['border']}; }}
    QLabel {{ background: transparent; border: none; }}
    QLabel#Brand {{ font-size: 21px; font-weight: 700; letter-spacing: -0.4px; }}
    QLabel#Eyebrow {{ font-size: 11px; font-weight: 700; letter-spacing: 1.4px; color: {c['muted']}; }}
    QLabel#Title {{ font-size: 21px; font-weight: 650; }}
    QLabel#MapTitle {{ font-size: 16px; font-weight: 650; }}
    QLabel#Muted, QLabel#Small {{ color: {c['muted']}; }}
    QLabel#Small {{ font-size: 12px; }}
    QLabel#Error {{ color: {('#fda4a4' if c['bg'] == '#0d1716' else '#a52727')}; }}
    QLabel#Value {{ font-size: 19px; font-weight: 650; }}
    QLabel#MeasureValue {{ font-size: 20px; font-weight: 700; color: {c['accent']}; }}
    QLabel#Badge {{ background: {c['soft']}; color: {c['accent']}; border-radius: 14px; padding: 6px 12px; font-size: 12px; font-weight: 600; }}
    QFrame#Summary {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QFrame#Divider {{ background: {c['border']}; border: none; max-height: 1px; }}
    QPushButton, QToolButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 9px 12px; font-weight: 600; }}
    QPushButton:hover, QToolButton:hover {{ background: {c['hover']}; border-color: {c['accent']}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {c['soft']}; }}
    QPushButton:focus, QToolButton:focus, QComboBox:focus {{ border: 2px solid {c['accent']}; }}
    QPushButton#LayerCard {{ text-align: left; padding: 12px 16px; font-size: 14px; font-weight: 500; background: {c['panel']}; }}
    QPushButton#LayerCard:checked {{ background: {c['soft']}; color: {c['accent']}; border: 2px solid {c['accent']}; font-weight: 650; }}
    QPushButton#ThemeButton {{ background: {c['panel']}; min-width: 122px; }}
    QPushButton:checked {{ background: {c['soft']}; color: {c['accent']}; border-color: {c['accent']}; }}
    QTabBar::tab {{ background: {c['surface']}; color: {c['muted']}; padding: 8px 13px; }}
    QTabBar::tab:selected {{ color: {c['accent']}; border-bottom: 2px solid {c['accent']}; }}
    QListWidget, QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; }}
    QListWidget::item, QMenu::item {{ padding: 7px; }}
    QListWidget::item:selected, QMenu::item:selected {{ background: {c['soft']}; color: {c['text']}; }}
    QToolButton {{ padding: 0; min-width: 34px; min-height: 34px; font-size: 20px; }}
    QComboBox {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 7px; padding: 9px 12px; }}
    QComboBox::drop-down {{ border: none; width: 25px; }}
    QComboBox QAbstractItemView {{ background: {c['surface']}; color: {c['text']}; selection-background-color: {c['soft']}; selection-color: {c['text']}; padding: 5px; }}
    QLineEdit, QDoubleSpinBox {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 7px; padding: 7px; }}
    QLineEdit:focus, QDoubleSpinBox:focus {{ border-color: {c['accent']}; }}
    QTableWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; gridline-color: {c['border']}; selection-background-color: {c['soft']}; selection-color: {c['text']}; }}
    QHeaderView::section {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 6px; }}
    QSlider::groove:horizontal {{ height: 6px; border-radius: 3px; background: {c['border']}; }}
    QSlider::handle:horizontal {{ width: 17px; margin: -6px 0; border-radius: 8px; background: {c['accent']}; }}
    QCheckBox {{ spacing: 9px; padding: 5px 0; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {c['muted']}; border-radius: 4px; background: {c['panel']}; }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
    QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 5px; }}
    QScrollBar:vertical {{ background: {c['panel']}; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 25px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    '''
