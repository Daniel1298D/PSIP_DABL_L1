"""Show the active map object's attributes and the contents of an H3 cell."""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from qgis.core import QgsVariantUtils

from .data import SCENARIO_FIELD


def value_text(value):
    if QgsVariantUtils.isNull(value):
        return '—'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 0 < abs(value) < .0001:
            formatted = f'{value:.3g}'
        else:
            formatted = f'{value:,}' if isinstance(value, int) else f'{value:,.4f}'.rstrip('0').rstrip('.')
        return formatted.replace(',', ' ').replace('.', ',')
    return str(value)


class ObjectPanel(QWidget):
    zoom_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        self.title = QLabel()
        self.title.setObjectName('MapTitle')
        self.subtitle = QLabel()
        self.subtitle.setObjectName('Muted')
        self.subtitle.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.iop = QLabel()
        self.iop.setObjectName('Value')
        self.note = QLabel()
        self.note.setObjectName('Muted')
        for item in (self.title, self.subtitle, self.iop, self.note):
            item.setWordWrap(True)
            item.setTextFormat(Qt.PlainText)
            layout.addWidget(item)
        self.table = QTableWidget(0, 2)
        self.table.setAccessibleName('Atrybuty wybranego obiektu')
        self.table.setHorizontalHeaderLabels(['Zawartość / atrybut', 'Wartość'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 97)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)
        self.zoom = QPushButton('Przybliż do obiektu')
        self.zoom.clicked.connect(self.zoom_requested.emit)
        layout.addWidget(self.zoom)
        self.clear()

    def clear(self):
        self.title.setText('Zawartość obiektu')
        self.subtitle.setText('Kliknij heksagon lub inny obiekt na mapie.')
        self.iop.hide()
        self.note.clear()
        self.table.setRowCount(0)
        self.zoom.setEnabled(False)

    def show_feature(self, layer, feature, criteria=None):
        self.title.setText(layer.name())
        self.table.setRowCount(0)
        entries = []
        if criteria is not None:
            self.subtitle.setText(f'H3: {feature["h3_index"]}')
            self.iop.setText(f'IOP {float(feature[SCENARIO_FIELD]):+.5f}'.replace('.', ','))
            self.iop.show()
            for column, title in criteria.items():
                value = feature[column]
                if QgsVariantUtils.isNull(value) or value == 0:
                    continue
                unit = {'a': 'm²', 'l': 'm', 'p': 'pkt'}.get(column[-1], '')
                entries.append((f'{title} · {column.upper()}', f'{value_text(value)} {unit}'.strip()))
            self.note.setText(f'Warstwy BDOT10k z wynikiem większym od zera: {len(entries)}')
        else:
            self.subtitle.setText(f'Identyfikator obiektu: {feature.id()}')
            self.iop.hide()
            self.note.clear()
            entries = [(field.name(), value_text(feature[field.name()])) for field in feature.fields()]
        self.table.setRowCount(len(entries))
        for index, (name, value) in enumerate(entries):
            name_item = QTableWidgetItem(name)
            name_item.setToolTip(name)
            self.table.setItem(index, 0, name_item)
            value_item = QTableWidgetItem(value)
            value_item.setToolTip(value)
            self.table.setItem(index, 1, value_item)
        self.table.resizeRowsToContents()
        self.zoom.setEnabled(feature.hasGeometry() and not feature.geometry().isEmpty())
