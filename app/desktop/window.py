"""Desktop window, session, map and analytical tools."""
import os
from pathlib import Path
import sys

from qgis.PyQt.QtCore import QByteArray, Qt, QSettings, QTimer, QSize, QDateTime, QSignalBlocker
from qgis.PyQt.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap, QKeySequence
from qgis.PyQt.QtSvg import QSvgRenderer
from qgis.PyQt.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QMainWindow, QMessageBox, QPushButton, QShortcut, QStackedWidget, QTabWidget, QToolBar, QToolButton,
    QVBoxLayout, QWidget,
)
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsProject, QgsRectangle
from qgis.gui import QgsMapCanvas, QgsMapToolEmitPoint, QgsMapToolIdentify
from python.iop_style import DEFAULT_IOP_COLORS

from . import APP_ICON, APP_NAME
from .accounts import Accounts
from .data import DataError, MapData
from .dialogs import LoginPanel, SearchDialog, StyleDialog, WeightsDialog
from .layers import LayerPanel, load_shape, make_point_layer
from .map_tools import DistanceTool, InspectPanTool
from .object_panel import ObjectPanel
from .pdf_export import export_map_pdf
from .theme import THEMES, qt_palette, stylesheet

PAN_HINT = 'Kliknij obiekt, aby zobaczyć atrybuty · przeciągnij mapę, aby ją przesunąć'
MEASURE_LABEL = 'Zmierz odległość'


def integer(value):
    return f'{value:,}'.replace(',', ' ')


def number(value):
    return f'{value:+.4f}'.replace('.', ',')


def label(text='', name=None):
    item = QLabel(text)
    if name:
        item.setObjectName(name)
    return item


def icon(name, color, size=20):
    shapes = {
        'moon': '<path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/>',
        'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
        'weights': '<path d="M3 6h8m4 0h6M3 12h3m4 0h11M3 18h11m4 0h3"/><circle cx="13" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="18" r="2"/>',
        'style': '<path d="M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-3.7 1.5 1.5 0 0 1 1-2.7h2a4 4 0 0 0 4-4C21 6.4 17 3 12 3Z"/><path d="M7 11h.01M10 7h.01M15 7h.01M18 10h.01" stroke-width="2.7"/>',
        'search': '<path d="M12 20H3V4h16v6M3 9h12M3 14h6M8 9v11"/><circle cx="16" cy="16" r="4"/><path d="m19 19 3 3"/>',
        'measure': '<path d="m3 16 13-13 5 5L8 21Z M12 7l2 2m-5 1 2 2m-5 1 2 2"/>',
        'pdf': '<path d="M5 21V3h10l4 4v14ZM14 3v5h5M8 16h8m-8-4h8"/>',
        'plus': '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5M7 10h6m-3-3v6"/>',
        'minus': '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5M7 10h6"/>',
        'extent': '<path d="M9 3H3v6m12-6h6v6M3 15v6h6m6 0h6v-6"/><circle cx="12" cy="12" r="3"/>',
        'refresh': '<path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 2M5 16a8 8 0 0 0 13 2"/>',
    }
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{shapes[name]}</svg>'
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def set_tool_label(button, caption):
    button.setText(caption)
    button.setToolTip(caption)
    button.setAccessibleName(caption)


def tabbed_sidebar(name):
    sidebar = QFrame()
    sidebar.setObjectName(name)
    sidebar.setFixedWidth(298)
    layout = QVBoxLayout(sidebar)
    layout.setContentsMargins(0, 10, 0, 0)
    tabs = QTabWidget()
    tabs.setDocumentMode(True)
    layout.addWidget(tabs)
    return sidebar, tabs


class Legend(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(13)
        self.border = '#dde6e0'
        self.zero = .5
        self.colors = DEFAULT_IOP_COLORS
        self.setAccessibleName('Skala IOP od minimum przez zero do maksimum')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        for position, color in zip((0, self.zero, 1), self.colors):
            gradient.setColorAt(position, QColor(color))
        painter.setBrush(gradient)
        painter.setPen(QColor(self.border))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 5, 5)


class MainWindow(QMainWindow):
    def __init__(self, accounts=None, settings=None):
        super().__init__()
        self.setWindowTitle(f'{APP_NAME} — Warszawa | Przejezdność terenu')
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1440, 900)
        self.setMinimumSize(1080, 720)
        self.settings = settings if settings is not None else QSettings('PSIP', 'GeoAnaliza')
        profile = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'GeoAnaliza'
        self.accounts = accounts if accounts is not None else Accounts(profile / 'account.sqlite3')
        self.theme = str(self.settings.value('theme', 'light'))
        if self.theme not in THEMES:
            self.theme = 'light'
        try:
            self.resolution = int(self.settings.value('resolution', 8))
        except (TypeError, ValueError):
            self.resolution = 8
        if self.resolution not in (7, 8, 9):
            self.resolution = 8
        self.data = None
        self.session_user = None
        self.custom_limits = None
        self.iop_colors = DEFAULT_IOP_COLORS
        self.weights_dialog = None
        self.point_target = None
        self.inspected = None
        self.loading = False
        self.build_ui()
        self.apply_theme(self.theme, persist=False)
        QShortcut(QKeySequence('Ctrl+Shift+L'), self, activated=self.toggle_theme)
        QShortcut(QKeySequence('Escape'), self, activated=self.use_pan)
        self.sign_out()

    def build_ui(self):
        root = QWidget()
        root.setObjectName('Root')
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName('Header')
        header.setFixedHeight(78)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 12, 26, 12)
        brand_icon = label()
        brand_icon.setPixmap(self.windowIcon().pixmap(44, 44))
        header_layout.addWidget(brand_icon)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        brand.addWidget(label(APP_NAME, 'Brand'))
        brand.addWidget(label('PRACOWNIA PRZESTRZENNA', 'Eyebrow'))
        header_layout.addLayout(brand)
        header_layout.addStretch()
        self.connection_badge = label('Zaloguj się', 'Badge')
        header_layout.addWidget(self.connection_badge)
        self.user_label = label('', 'Muted')
        header_layout.addWidget(self.user_label)
        self.logout_button = QPushButton('Wyloguj się')
        self.logout_button.clicked.connect(self.sign_out)
        header_layout.addWidget(self.logout_button)
        outer.addWidget(header)
        outer.addWidget(self.build_toolbar())

        content = QHBoxLayout()
        content.setSpacing(0)
        self.sidebar, self.side_tabs = tabbed_sidebar('Sidebar')
        analysis_panel = QWidget()
        self.side_tabs.addTab(analysis_panel, 'Analiza IOP')
        self.layer_panel = LayerPanel()
        self.object_panel = ObjectPanel()
        self.side_tabs.addTab(self.object_panel, 'Obiekt')
        self.object_panel.zoom_requested.connect(self.zoom_to_object)
        self.layer_panel.changed.connect(self.update_map_layers)
        self.layer_panel.import_files.connect(self.pick_shape_files)
        self.layer_panel.import_folder.connect(self.pick_shape_folder)
        self.layer_panel.create_points.connect(self.prompt_point_layer)
        self.layer_panel.digitize.connect(self.toggle_digitize)
        self.layer_panel.list.currentRowChanged.connect(self.point_selection_changed)
        side = QVBoxLayout(analysis_panel)
        side.setContentsMargins(22, 22, 22, 18)
        side.setSpacing(11)
        side.addWidget(label('Warszawa', 'Title'))
        subtitle = label('Analiza przejezdności terenu', 'Muted')
        subtitle.setWordWrap(True)
        side.addWidget(subtitle)
        side.addSpacing(12)
        side.addWidget(label('ROZDZIELCZOŚĆ SIATKI', 'Eyebrow'))
        self.layer_buttons = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for resolution in (7, 8, 9):
            button = QPushButton(f'H3 {resolution}')
            button.setObjectName('LayerCard')
            button.setAccessibleName(f'Wybierz heksagony H3 {resolution}')
            button.setMinimumHeight(61)
            button.setCheckable(True)
            button.setChecked(resolution == self.resolution)
            button.clicked.connect(lambda checked, r=resolution: self.select_grid(r))
            group.addButton(button)
            self.layer_buttons[resolution] = button
            side.addWidget(button)
        side.addSpacing(7)
        side.addWidget(label('WIDOK WSKAŹNIKA', 'Eyebrow'))
        self.style_combo = QComboBox()
        self.style_combo.setAccessibleName('Zakres prezentacji IOP')
        self.style_combo.addItem('Szczegółowy · −0,07 … +0,07', 'detail')
        self.style_combo.addItem('Pełny · −1 … +1', 'full')
        self.style_combo.currentIndexChanged.connect(self.change_style)
        side.addWidget(self.style_combo)
        self.boundary_check = QCheckBox('Granica Warszawy')
        self.boundary_check.setChecked(True)
        self.boundary_check.toggled.connect(lambda shown: self.layer_panel.set_visible('boundary', shown))
        side.addWidget(self.boundary_check)
        divider = QFrame()
        divider.setObjectName('Divider')
        divider.setFixedHeight(1)
        side.addWidget(divider)
        side.addSpacing(3)
        side.addWidget(label('WSPÓŁCZYNNIK IOP', 'Eyebrow'))
        self.legend = Legend()
        side.addWidget(self.legend)
        ticks = QHBoxLayout()
        self.legend_ticks = ticks
        self.legend_low = label('−0,07', 'Small')
        self.legend_high = label('+0,07', 'Small')
        ticks.addWidget(self.legend_low)
        ticks.addStretch(50)
        ticks.addWidget(label('0', 'Small'))
        ticks.addStretch(50)
        ticks.addWidget(self.legend_high)
        side.addLayout(ticks)
        explanation = label('Ujemne wartości: utrudnienie\nDodatnie wartości: ułatwienie', 'Muted')
        side.addWidget(explanation)
        side.addSpacing(6)
        summary = QFrame()
        summary.setObjectName('Summary')
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(13, 12, 13, 12)
        summary_layout.setSpacing(5)
        summary_layout.addWidget(label('Zakres IOP w tej siatce', 'Small'))
        self.range_value = label('—', 'Value')
        self.range_value.setStyleSheet('font-size: 16px;')
        summary_layout.addWidget(self.range_value)
        self.summary_caption = label('Dane z 73 kryteriów BDOT10k', 'Small')
        summary_layout.addWidget(self.summary_caption)
        side.addWidget(summary)
        side.addStretch()
        side.addWidget(label('ŹRÓDŁO DANYCH', 'Eyebrow'))
        side.addWidget(label('PostGIS · env-test', 'MapTitle'))
        self.read_time = label('Oczekiwanie na odczyt', 'Small')
        side.addWidget(self.read_time)
        content.addWidget(self.sidebar)

        map_area = QVBoxLayout()
        map_area.setContentsMargins(20, 20, 20, 20)
        frame = QFrame()
        frame.setObjectName('MapFrame')
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(1, 1, 1, 1)
        frame_layout.setSpacing(0)
        map_header = QFrame()
        map_header.setObjectName('MapHeader')
        map_header.setFixedHeight(54)
        titles = QVBoxLayout(map_header)
        titles.setContentsMargins(18, 6, 14, 6)
        titles.setSpacing(1)
        titles.addWidget(label('Mapa przejezdności', 'MapTitle'))
        self.map_subtitle = label('Łączenie z danymi przestrzennymi…', 'Small')
        titles.addWidget(self.map_subtitle)
        frame_layout.addWidget(map_header)
        self.measure_panel = QFrame()
        self.measure_panel.setObjectName('MeasurePanel')
        measure_layout = QHBoxLayout(self.measure_panel)
        measure_layout.setContentsMargins(18, 10, 14, 10)
        measure_layout.setSpacing(14)
        measure_layout.addWidget(label('Odległość', 'MapTitle'))
        self.measure_value = label('—', 'MeasureValue')
        self.measure_value.setAccessibleName('Zmierzona odległość w metrach')
        self.measure_value.setMinimumWidth(104)
        measure_layout.addWidget(self.measure_value)
        self.measure_hint = label('', 'Muted')
        self.measure_hint.setWordWrap(True)
        measure_layout.addWidget(self.measure_hint, 1)
        clear_measure = QPushButton('Wyczyść pomiar')
        clear_measure.clicked.connect(self.clear_measurement)
        measure_layout.addWidget(clear_measure)
        frame_layout.addWidget(self.measure_panel)
        self.measure_panel.hide()
        self.pages = QStackedWidget()
        self.login_panel = LoginPanel(self.accounts)
        self.login_panel.signed_in.connect(self.sign_in)
        self.pages.addWidget(self.login_panel)
        self.loading_page = QWidget()
        loading_layout = QVBoxLayout(self.loading_page)
        loading_layout.setContentsMargins(50, 30, 50, 30)
        loading_layout.addStretch()
        self.load_title = label('Wczytywanie heksagonów…', 'Title')
        self.load_title.setAlignment(Qt.AlignCenter)
        self.load_title.setWordWrap(True)
        loading_layout.addWidget(self.load_title)
        self.load_message = label('Odczyt danych bezpośrednio z PostgreSQL.', 'Muted')
        self.load_message.setWordWrap(True)
        self.load_message.setAlignment(Qt.AlignCenter)
        loading_layout.addWidget(self.load_message)
        self.retry_button = QPushButton('Spróbuj ponownie')
        self.retry_button.clicked.connect(self.load_data)
        self.retry_button.hide()
        loading_layout.addWidget(self.retry_button, 0, Qt.AlignCenter)
        loading_layout.addStretch()
        self.pages.addWidget(self.loading_page)
        self.canvas = QgsMapCanvas()
        self.canvas.setAccessibleName('Interaktywna mapa heksagonów Warszawy')
        self.canvas.enableAntiAliasing(True)
        self.canvas.setCachingEnabled(True)
        self.canvas.setParallelRenderingEnabled(True)
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
        self.canvas.setWheelFactor(1.7)
        self.pan_tool = InspectPanTool(self.canvas)
        self.pan_tool.clicked.connect(self.inspect_at)
        self.identify_tool = QgsMapToolIdentify(self.canvas)
        self.pan_tool.setCursor(Qt.OpenHandCursor)
        self.canvas.setMapTool(self.pan_tool)
        self.distance_tool = DistanceTool(self.canvas)
        self.point_tool = QgsMapToolEmitPoint(self.canvas)
        self.point_tool.setCursor(Qt.CrossCursor)
        self.point_tool.canvasClicked.connect(self.add_map_point)
        self.to_wgs84 = QgsCoordinateTransform(self.canvas.mapSettings().destinationCrs(),
            QgsCoordinateReferenceSystem('EPSG:4326'), QgsProject.instance().transformContext())
        self.pages.addWidget(self.canvas)
        frame_layout.addWidget(self.pages)
        map_area.addWidget(frame)
        content.addLayout(map_area, 1)

        self.layers_sidebar, layers_tabs = tabbed_sidebar('LayersSidebar')
        layers_tabs.addTab(self.layer_panel, 'Warstwy')
        content.addWidget(self.layers_sidebar)
        outer.addLayout(content, 1)

        footer = QFrame()
        footer.setObjectName('Footer')
        footer.setFixedHeight(34)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(22, 0, 24, 0)
        self.coordinates = label('Najedź na mapę · EPSG:4326', 'Small')
        footer_layout.addWidget(self.coordinates)
        footer_layout.addStretch()
        self.tool_hint = label(PAN_HINT, 'Small')
        self.distance_tool.message.connect(self.show_measure_instruction)
        self.distance_tool.measured.connect(self.show_measurement)
        footer_layout.addWidget(self.tool_hint)
        footer_layout.addSpacing(24)
        self.scale_label = label('Skala —', 'Small')
        footer_layout.addWidget(self.scale_label)
        outer.addWidget(footer)
        self.canvas.xyCoordinates.connect(self.show_coordinates)
        self.canvas.scaleChanged.connect(lambda scale: self.scale_label.setText(f'Skala 1 : {integer(round(scale))}'))

    def build_toolbar(self):
        toolbar = QToolBar('Narzędzia mapy', self)
        toolbar.setObjectName('MapTools')
        toolbar.setAccessibleName('Narzędzia mapy')
        toolbar.setMovable(False)
        toolbar.setFloatable(False)

        def add_tool(caption, action=None):
            button = QToolButton()
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setFixedSize(34, 34)
            button.setIconSize(QSize(20, 20))
            button.setFocusPolicy(Qt.StrongFocus)
            set_tool_label(button, caption)
            if action is not None:
                button.clicked.connect(action)
            toolbar.addWidget(button)
            return button

        self.analysis_buttons = {
            'weights': add_tool('Wagi IOP', self.edit_weights),
            'style': add_tool('Edytuj styl', self.edit_style),
            'search': add_tool('Wyszukaj', self.search_attributes),
            'measure': add_tool(MEASURE_LABEL),
        }
        self.measure_button = self.analysis_buttons['measure']
        self.measure_button.setCheckable(True)
        self.measure_button.toggled.connect(self.toggle_measure)
        toolbar.addSeparator()
        self.tools = {
            'refresh': add_tool('Odśwież dane z bazy', self.load_data),
            'extent': add_tool('Pokaż całą Warszawę', self.full_extent),
            'minus': add_tool('Oddal mapę', lambda: self.canvas.zoomOut()),
            'plus': add_tool('Przybliż mapę', lambda: self.canvas.zoomIn()),
        }
        toolbar.addSeparator()
        self.pdf_button = add_tool('Eksport PDF', self.save_pdf)
        self.theme_button = add_tool('Zmień motyw', self.toggle_theme)
        return toolbar

    def apply_theme(self, name, persist=True):
        self.theme = name
        colors = THEMES[name]
        app = QApplication.instance()
        app.setPalette(qt_palette(colors))
        app.setStyleSheet(stylesheet(colors))
        self.canvas.setCanvasColor(QColor(colors['map']))
        theme_label = 'Tryb jasny' if name == 'dark' else 'Tryb ciemny'
        set_tool_label(self.theme_button, theme_label)
        self.theme_button.setToolTip(f'{theme_label} · Ctrl+Shift+L')
        self.theme_button.setIcon(icon('sun' if name == 'dark' else 'moon', colors['text']))
        self.pdf_button.setIcon(icon('pdf', colors['text']))
        for key, button in self.analysis_buttons.items():
            button.setIcon(icon(key, colors['accent']))
        for key, button in self.tools.items():
            button.setIcon(icon(key, colors['text']))
        self.legend.border = colors['border']
        self.legend.update()
        self.fit_measure_value()
        if self.data:
            self.data.set_boundary_color(colors['line'])
        self.canvas.refresh()
        if persist:
            self.settings.setValue('theme', name)
            self.settings.sync()
        # Apply the same theme to this application's own native Windows title bar.
        if sys.platform == 'win32':
            try:
                import ctypes
                dark = ctypes.c_int(name == 'dark')
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(int(self.winId())), 20, ctypes.byref(dark), ctypes.sizeof(dark))
                for attribute, value in ((34, colors['border']), (35, colors['surface']), (36, colors['text'])):
                    color = QColor(value)
                    colorref = ctypes.c_uint(color.red() | (color.green() << 8) | (color.blue() << 16))
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        ctypes.c_void_p(int(self.winId())), attribute, ctypes.byref(colorref), ctypes.sizeof(colorref))
            except (AttributeError, OSError):
                pass

    def toggle_theme(self):
        self.apply_theme('light' if self.theme == 'dark' else 'dark')

    def sync_actions(self):
        signed_in = self.session_user is not None
        ready = signed_in and self.data is not None and not self.loading
        self.logout_button.setVisible(signed_in)
        self.logout_button.setEnabled(not self.loading)
        self.user_label.setVisible(signed_in)
        for sidebar in (self.sidebar, self.layers_sidebar):
            sidebar.setVisible(signed_in)
            sidebar.setEnabled(ready)
        for button in self.analysis_buttons.values():
            button.setEnabled(ready)
        self.pdf_button.setEnabled(ready and bool(self.canvas.layers()))
        for name, button in self.tools.items():
            button.setEnabled(ready or (name == 'refresh' and signed_in and not self.loading))

    def sign_in(self, username):
        self.session_user = username
        self.user_label.setText(username)
        self.user_label.setTextFormat(Qt.PlainText)
        self.pages.setCurrentWidget(self.loading_page)
        self.sync_actions()
        QTimer.singleShot(0, self.load_data)

    def sign_out(self):
        self.session_user = None
        if self.weights_dialog is not None:
            self.weights_dialog.close()
        self.canvas.stopRendering()
        self.canvas.setLayers([])
        self.use_pan()
        self.clear_measurement()
        self.clear_inspection()
        self.layer_panel.clear()
        self.data = None
        self.custom_limits = None
        self.iop_colors = DEFAULT_IOP_COLORS
        self.style_combo.setCurrentIndex(0)
        custom_index = self.style_combo.findData('custom')
        if custom_index >= 0:
            self.style_combo.removeItem(custom_index)
        self.range_value.setText('—')
        self.summary_caption.setText('Dane z 73 kryteriów BDOT10k')
        self.coordinates.setText('Najedź na mapę · EPSG:4326')
        self.scale_label.setText('Skala —')
        self.map_subtitle.setText('Zaloguj się, aby wczytać mapę')
        self.connection_badge.setText('Niezalogowano')
        self.pages.setCurrentWidget(self.login_panel)
        self.login_panel.reset()
        self.sync_actions()

    def load_data(self):
        if self.session_user is None or self.loading:
            return
        if self.weights_dialog is not None:
            self.weights_dialog.close()
        self.loading = True
        self.use_pan()
        self.clear_measurement()
        self.clear_inspection()
        self.sync_actions()
        self.connection_badge.setText('Łączenie z bazą…')
        self.load_title.setText('Wczytywanie heksagonów…')
        self.load_message.setText('Odczyt danych bezpośrednio z PostgreSQL.')
        self.retry_button.hide()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            staged = MapData()
            staged.load()
            if self.data and self.data.overrides:
                staged.set_weights({key: value for key, value in self.data.overrides.items() if key in staged.weights})
            self.canvas.stopRendering()
            self.canvas.freeze(True)
            self.canvas.setLayers([])
            self.data = staged
            self.data.set_boundary_color(THEMES[self.theme]['line'])
            self.data.set_style(self.style_combo.currentData(), self.custom_limits, colors=self.iop_colors)
            for resolution, grid in self.data.grids.items():
                self.layer_buttons[resolution].setText(f'H3 {resolution}\n{integer(grid.count)} heksagonów')
            self.layer_panel.upsert('boundary', self.data.boundary)
            self.layer_panel.upsert('grid', self.data.grids[self.resolution].layer)
            if self.layer_panel.selected_key() is None:
                self.layer_panel.select('grid')
            self.pages.setCurrentWidget(self.canvas)
            self.connection_badge.setText('●  Połączono · env-test')
            self.read_time.setText('Odczyt: ' + QDateTime.currentDateTime().toString('HH:mm:ss'))
            self.update_map_layers()
            self.update_values()
            QTimer.singleShot(0, self.full_extent)
        except DataError as exc:
            self.canvas.stopRendering()
            self.canvas.setLayers([])
            self.data = None
            self.load_title.setText('Nie można wczytać danych')
            self.load_message.setText(str(exc))
            self.retry_button.show()
            self.pages.setCurrentWidget(self.loading_page)
            self.connection_badge.setText('Brak połączenia')
        finally:
            self.loading = False
            self.sync_actions()
            self.canvas.freeze(False)
            QApplication.restoreOverrideCursor()

    def select_grid(self, resolution):
        if self.data:
            self.data.grids[self.resolution].layer.removeSelection()
            if self.inspected is not None and self.inspected[0] is self.data.grids[self.resolution].layer:
                self.clear_inspection()
        self.resolution = resolution
        self.settings.setValue('resolution', resolution)
        if self.data:
            self.layer_panel.upsert('grid', self.data.grids[resolution].layer)
        self.update_map_layers()
        self.update_values()

    def update_map_layers(self):
        if not self.data:
            return
        with QSignalBlocker(self.boundary_check):
            self.boundary_check.setChecked(self.layer_panel.visible('boundary'))
        layers = self.layer_panel.visible_layers()
        if self.inspected is not None and self.inspected[0] not in layers:
            self.clear_inspection()
        self.canvas.setLayers(layers)
        self.canvas.refresh()
        self.pdf_button.setEnabled(bool(layers) and not self.loading)

    def pick_shape_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Wybierz warstwy SHP', str(Path.home()), 'Shapefile (*.shp)')
        self.import_shapes(paths)

    def pick_shape_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Wybierz folder z warstwami SHP', str(Path.home()))
        if not folder:
            return
        try:
            paths = sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() == '.shp')
        except OSError:
            QMessageBox.warning(self, 'Wczytywanie SHP', 'Nie udało się odczytać wybranego folderu.')
            return
        if not paths:
            QMessageBox.information(self, 'Wczytywanie SHP', 'W tym folderze nie ma plików .shp.')
            return
        self.import_shapes(paths)

    def import_shapes(self, paths):
        errors = []
        added = 0
        for path in paths:
            try:
                key = 'shp:' + os.path.normcase(str(Path(path).resolve()))
                if key not in self.layer_panel.layers:
                    self.layer_panel.upsert(key, load_shape(path), at_top=True)
                    added += 1
                self.layer_panel.set_visible(key, True)
                self.layer_panel.select(key)
            except (DataError, OSError) as exc:
                errors.append(str(exc))
        if added:
            self.update_map_layers()
            self.tool_hint.setText(f'Wczytane warstwy SHP: {added}')
        if errors:
            QMessageBox.warning(self, 'Nie udało się wczytać części plików SHP', '\n'.join(errors))

    def prompt_point_layer(self):
        name, accepted = QInputDialog.getText(self, 'Nowa warstwa punktowa', 'Nazwa warstwy', text='Punkty')
        if accepted and name.strip():
            self.add_point_layer(name.strip())

    def add_point_layer(self, name):
        layer = make_point_layer(name)
        self.layer_panel.upsert(layer.id(), layer, at_top=True, editable=True)
        self.layer_panel.select(layer.id())
        self.update_map_layers()
        self.layer_panel.digitize_button.setChecked(True)
        return layer

    def point_selection_changed(self):
        if self.point_target is not None and self.layer_panel.selected_key() != self.point_target:
            self.use_pan()

    def use_pan(self):
        self.point_target = None
        with QSignalBlocker(self.measure_button), QSignalBlocker(self.layer_panel.digitize_button):
            self.measure_button.setChecked(False)
            self.layer_panel.digitize_button.setChecked(False)
        self.canvas.setMapTool(self.pan_tool)
        self.tool_hint.setText(PAN_HINT)
        set_tool_label(self.measure_button, MEASURE_LABEL)
        if self.distance_tool.meters is None:
            self.measure_panel.hide()
        else:
            self.measure_hint.setText('Ostatni pomiar')

    def toggle_measure(self, active):
        if not active:
            self.use_pan()
            return
        self.point_target = None
        with QSignalBlocker(self.layer_panel.digitize_button):
            self.layer_panel.digitize_button.setChecked(False)
        self.canvas.setMapTool(self.distance_tool)
        self.canvas.setFocus()
        set_tool_label(self.measure_button, 'Zakończ pomiar')

    def show_measure_instruction(self, message, value='—'):
        self.measure_value.setText(value)
        self.fit_measure_value()
        self.measure_hint.setText(message)
        self.measure_panel.show()

    def show_measurement(self, meters):
        distance = f'{meters:,.2f}'.replace(',', ' ').replace('.', ',')
        self.show_measure_instruction('Kliknij mapę, aby rozpocząć nowy pomiar. Esc wraca do przesuwania.',
                                      f'{distance} m')

    def fit_measure_value(self):
        width = self.measure_value.fontMetrics().horizontalAdvance(self.measure_value.text())
        self.measure_value.setMinimumWidth(max(104, width + 4))

    def clear_measurement(self):
        if self.canvas.mapTool() is self.distance_tool:
            self.distance_tool.restart()
        else:
            self.distance_tool.clear()
            self.measure_value.setText('—')
            self.measure_panel.hide()

    def toggle_digitize(self, active):
        key = self.layer_panel.selected_key()
        if not active or key not in self.layer_panel.point_layers:
            self.use_pan()
            return
        self.point_target = key
        self.layer_panel.set_visible(key, True)
        with QSignalBlocker(self.measure_button):
            self.measure_button.setChecked(False)
        self.canvas.setMapTool(self.point_tool)
        set_tool_label(self.measure_button, MEASURE_LABEL)
        self.clear_measurement()
        self.canvas.setFocus()
        self.tool_hint.setText('Kliknij na mapie, aby dodać punkt · Esc kończy dodawanie')

    def add_map_point(self, point, button):
        if button != Qt.LeftButton or self.point_target is None:
            return
        layer = self.layer_panel.layers[self.point_target]
        next_number = layer.featureCount() + 1
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(self.to_wgs84.transform(point)))
        feature.setAttributes([next_number, f'Punkt {next_number}'])
        ok, _ = layer.dataProvider().addFeatures([feature])
        if not ok:
            self.tool_hint.setText('Nie udało się dodać punktu.')
            return
        layer.updateExtents()
        layer.triggerRepaint()
        self.canvas.refresh()
        self.tool_hint.setText(f'Dodano punkt {next_number} · kliknij ponownie lub naciśnij Esc')

    def update_values(self):
        if not self.data:
            return
        grid = self.data.grids[self.resolution]
        self.map_subtitle.setText(f'H3 {grid.resolution} · {integer(grid.count)} heksagonów · Warszawa')
        low, high = self.data.scenario_ranges.get(self.resolution, (grid.minimum, grid.maximum))
        self.range_value.setText(f'{number(low)} … {number(high)}')
        self.summary_caption.setText(f'Zmienione wagi: {len(self.data.overrides)}' if self.data.overrides
                                     else f'Dane z {len(self.data.weights)} kryteriów BDOT10k')
        detail = self.data.detail_limit()
        caption = str(detail).replace('.', ',')
        self.style_combo.setItemText(0, f'Szczegółowy · −{caption} … +{caption}')
        low, high = self.current_limits()
        self.legend_low.setText(number(low).rstrip('0').rstrip(','))
        self.legend_high.setText(number(high).rstrip('0').rstrip(','))
        self.legend.zero = float(-low / (high - low))
        self.legend.colors = self.iop_colors
        self.legend_ticks.setStretch(1, round(self.legend.zero * 1000))
        self.legend_ticks.setStretch(3, round((1 - self.legend.zero) * 1000))
        self.legend.update()

    def change_style(self):
        if self.data:
            self.canvas.stopRendering()
            self.data.set_style(self.style_combo.currentData(), self.custom_limits, colors=self.iop_colors)
            self.update_map_layers()
            self.update_values()

    def current_limits(self):
        return self.data.style_limits(self.style_combo.currentData(), self.custom_limits)

    def edit_weights(self):
        if not self.data:
            return
        if self.weights_dialog is None:
            self.weights_dialog = WeightsDialog(self.data, self)
            self.weights_dialog.setAttribute(Qt.WA_DeleteOnClose)
            self.weights_dialog.weights_changed.connect(self.apply_weights)
            self.weights_dialog.finished.connect(self.release_weights_dialog)
        self.weights_dialog.show()
        self.weights_dialog.raise_()
        self.weights_dialog.activateWindow()

    def release_weights_dialog(self):
        self.weights_dialog = None

    def apply_weights(self, weights):
        if self.session_user is None or not self.data or weights == self.data.overrides:
            return
        self.canvas.stopRendering()
        self.data.set_weights(weights)
        self.change_style()
        if self.inspected is not None:
            layer, feature_id = self.inspected
            self.object_panel.show_feature(layer, layer.getFeature(feature_id), self.criteria_for(layer))

    def edit_style(self):
        if not self.data:
            return
        limits = self.current_limits()
        dialog = StyleDialog(limits, self.iop_colors, self)
        if dialog.exec() == StyleDialog.Accepted:
            self.iop_colors = dialog.colors()
            chosen_limits = dialog.limits()
            if chosen_limits != limits:
                self.custom_limits = chosen_limits
                index = self.style_combo.findData('custom')
                if index < 0:
                    self.style_combo.addItem('Własny zakres', 'custom')
                    index = self.style_combo.findData('custom')
                with QSignalBlocker(self.style_combo):
                    self.style_combo.setCurrentIndex(index)
            self.change_style()
        dialog.deleteLater()

    def search_attributes(self):
        if not self.data:
            return
        layers = {resolution: grid.layer for resolution, grid in self.data.grids.items()}
        layers.update((key, layer) for key, layer in self.layer_panel.layers.items() if key != 'grid')
        selected = self.layer_panel.selected_key()
        dialog = SearchDialog(layers, selected if selected in layers else self.resolution, self.data.labels, self)
        dialog.feature_chosen.connect(self.select_feature)
        dialog.selection_cleared.connect(self.clear_inspection)
        dialog.exec()
        dialog.deleteLater()

    def select_feature(self, key, feature_id):
        if isinstance(key, int):
            self.select_grid(key)
            key = 'grid'
        layer = self.layer_panel.layers[key]
        self.layer_panel.set_visible(key, True)
        self.show_inspected(layer, layer.getFeature(feature_id))
        self.zoom_to_object()

    def criteria_for(self, layer):
        if self.data and layer is self.data.grids[self.resolution].layer:
            return {key: self.data.labels.get(key, key) for key in self.data.weights}
        return None

    def inspect_at(self, x, y):
        if not self.data:
            return
        layers = [layer for layer in self.canvas.layers() if layer is not self.data.boundary]
        results = self.identify_tool.identify(x, y, layers, QgsMapToolIdentify.TopDownStopAtFirst) if layers else []
        if results:
            layer = results[0].mLayer
            transform = QgsCoordinateTransform(self.canvas.mapSettings().destinationCrs(), layer.crs(),
                                               QgsProject.instance().transformContext())
            point = transform.transform(self.canvas.getCoordinateTransform().toMapCoordinates(x, y))
            target = QgsGeometry.fromPointXY(point)
            result = min(results, key=lambda entry: entry.mFeature.geometry().distance(target))
            self.show_inspected(layer, result.mFeature)
        else:
            self.clear_inspection()

    def show_inspected(self, layer, feature):
        if not feature.isValid():
            self.clear_inspection()
            return
        self.clear_inspection()
        self.inspected = layer, feature.id()
        layer.selectByIds([feature.id()])
        # Re-read the feature so virtual attributes use the current scenario.
        self.object_panel.show_feature(layer, layer.getFeature(feature.id()), self.criteria_for(layer))
        self.side_tabs.setCurrentWidget(self.object_panel)
        self.canvas.refresh()

    def clear_inspection(self):
        if self.inspected is not None:
            layer, _ = self.inspected
            layer.removeSelection()
        self.inspected = None
        self.object_panel.clear()

    def zoom_to_object(self):
        if self.inspected is None:
            return
        layer, feature_id = self.inspected
        geometry = layer.getFeature(feature_id).geometry()
        if geometry.isEmpty():
            self.clear_inspection()
            return
        transform = QgsCoordinateTransform(layer.crs(), self.canvas.mapSettings().destinationCrs(),
                                           QgsProject.instance().transformContext())
        geometry.transform(transform)
        bounds = geometry.boundingBox()
        center = bounds.center()
        half_width = max(bounds.width() * .7, 90)
        half_height = max(bounds.height() * .7, 90)
        self.canvas.setExtent(QgsRectangle(center.x() - half_width, center.y() - half_height,
                                           center.x() + half_width, center.y() + half_height))
        self.canvas.refresh()

    def save_pdf(self):
        if not self.data or not self.canvas.layers():
            return
        filename, _ = QFileDialog.getSaveFileName(self, 'Eksportuj widok mapy',
            str(Path.home() / 'Documents' / f'Mapa {APP_NAME}.pdf'), 'Plik PDF (*.pdf)')
        if not filename:
            return
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'
        limits = self.current_limits() if self.layer_panel.visible('grid') else None
        try:
            export_map_pdf(self.canvas, filename, iop_limits=limits, iop_colors=self.iop_colors)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Eksport PDF', f'Nie udało się zapisać mapy.\n{exc}')
            return
        self.tool_hint.setText(f'Zapisano PDF: {Path(filename).name}')

    def full_extent(self):
        if self.data:
            self.canvas.setExtent(self.data.extent)
            self.canvas.refresh()

    def show_coordinates(self, point):
        try:
            position = self.to_wgs84.transform(point)
            self.coordinates.setText(f'Szer. {position.y():.5f}° · Dł. {position.x():.5f}° · EPSG:4326')
        except Exception:
            self.coordinates.setText('Współrzędne niedostępne')

    def closeEvent(self, event):
        self.settings.setValue('theme', self.theme)
        self.settings.setValue('resolution', self.resolution)
        self.settings.sync()
        self.session_user = None
        if self.weights_dialog is not None:
            self.weights_dialog.close()
        self.canvas.stopRendering()
        self.canvas.setLayers([])
        self.data = None
        super().closeEvent(event)
