"""Map layer order, visibility and local vector sources."""

from pathlib import Path

from qgis.PyQt.QtCore import QSignalBlocker, Qt, QVariant, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QVBoxLayout, QWidget,
)
from qgis.core import QgsField, QgsMarkerSymbol, QgsVectorLayer

from .data import DataError


def load_shape(path):
    path = Path(path)
    layer = QgsVectorLayer(str(path), path.stem, 'ogr')
    if not layer.isValid() or not layer.isSpatial():
        raise DataError(f'{path.name} — nie można odczytać geometrii lub plików składowych SHP.')
    if not layer.crs().isValid():
        raise DataError(f'{path.name} — brak poprawnego układu współrzędnych. Sprawdź plik .prj.')
    return layer


def make_point_layer(name):
    layer = QgsVectorLayer('Point?crs=EPSG:4326', name, 'memory')
    layer.dataProvider().addAttributes([QgsField('numer', QVariant.Int), QgsField('nazwa', QVariant.String)])
    layer.updateFields()
    layer.renderer().setSymbol(QgsMarkerSymbol.createSimple({
        'name': 'circle', 'color': '#2259c6', 'outline_color': '#ffffff', 'outline_width': '0.5', 'size': '3.6',
    }))
    return layer


class LayerPanel(QWidget):
    changed = pyqtSignal()
    import_files = pyqtSignal()
    import_folder = pyqtSignal()
    create_points = pyqtSignal()
    digitize = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.layers = {}
        self.point_layers = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.addWidget(QLabel('Kolejność warstw'))
        hint = QLabel('Warstwy wyżej na liście są rysowane na wierzchu.')
        hint.setObjectName('Muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.list = QListWidget()
        self.list.setAccessibleName('Kolejność i widoczność warstw mapy')
        self.list.itemChanged.connect(self.changed.emit)
        self.list.currentRowChanged.connect(self.sync_buttons)
        layout.addWidget(self.list, 1)
        order = QHBoxLayout()
        self.up = QPushButton('↑ Wyżej')
        self.down = QPushButton('↓ Niżej')
        self.up.clicked.connect(lambda: self.move(-1))
        self.down.clicked.connect(lambda: self.move(1))
        order.addWidget(self.up)
        order.addWidget(self.down)
        layout.addLayout(order)
        self.import_button = QPushButton('Wczytaj SHP')
        menu = QMenu(self.import_button)
        menu.addAction('Wybierz pliki .shp…', self.import_files.emit)
        menu.addAction('Wczytaj pliki .shp z folderu…', self.import_folder.emit)
        self.import_button.setMenu(menu)
        layout.addWidget(self.import_button)
        create = QPushButton('Nowa warstwa punktowa')
        create.clicked.connect(self.create_points.emit)
        layout.addWidget(create)
        self.digitize_button = QPushButton('Dodawaj punkty na mapie')
        self.digitize_button.setCheckable(True)
        self.digitize_button.toggled.connect(self.digitize.emit)
        layout.addWidget(self.digitize_button)
        self.sync_buttons()

    def upsert(self, key, layer, *, at_top=False, editable=False):
        self.layers[key] = layer
        if editable:
            self.point_layers.add(key)
        with QSignalBlocker(self.list):
            item = self.find(key)
            if item is None:
                item = QListWidgetItem()
                item.setData(Qt.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                self.list.insertItem(0 if at_top else self.list.count(), item)
            item.setText(layer.name())
            item.setToolTip(layer.name())
        self.sync_buttons()

    def find(self, key):
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.UserRole) == key:
                return item
        return None

    def set_visible(self, key, visible):
        item = self.find(key)
        if item is not None:
            item.setCheckState(Qt.Checked if visible else Qt.Unchecked)

    def visible(self, key):
        item = self.find(key)
        return item is not None and item.checkState() == Qt.Checked

    def selected_key(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def select(self, key):
        self.list.setCurrentItem(self.find(key))

    def visible_layers(self):
        return [self.layers[self.list.item(row).data(Qt.UserRole)] for row in range(self.list.count())
                if self.list.item(row).checkState() == Qt.Checked]

    def move(self, delta):
        row = self.list.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self.list.count():
            return
        with QSignalBlocker(self.list):
            item = self.list.takeItem(row)
            self.list.insertItem(target, item)
            self.list.setCurrentRow(target)
        self.sync_buttons()
        self.changed.emit()

    def sync_buttons(self):
        row = self.list.currentRow()
        self.up.setEnabled(row > 0)
        self.down.setEnabled(0 <= row < self.list.count() - 1)
        self.digitize_button.setEnabled(self.selected_key() in self.point_layers)

    def clear(self):
        self.list.clear()
        self.layers.clear()
        self.point_layers.clear()
        self.sync_buttons()
