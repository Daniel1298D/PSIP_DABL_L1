"""Controls for signing in, changing the map style, and searching a grid."""

from decimal import Decimal
from functools import partial
from itertools import islice
import sqlite3

from qgis.PyQt.QtCore import QAbstractTableModel, QModelIndex, QSignalBlocker, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QSizePolicy, QSlider, QTableView,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qgis.core import QgsFeatureRequest, QgsVariantUtils
from python.iop_style import DEFAULT_IOP_COLORS

from . import APP_NAME
from .data import SCENARIO_FIELD


def add_button(layout, text, on_click):
    button = QPushButton(text)
    button.clicked.connect(on_click)
    layout.addWidget(button)
    return button


class LoginPanel(QWidget):
    signed_in = pyqtSignal(str)

    def __init__(self, accounts):
        super().__init__()
        self.accounts = accounts
        layout = QVBoxLayout(self)
        card = QFrame()
        card.setObjectName('Summary')
        card.setFixedWidth(408)
        form = QVBoxLayout(card)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)
        self.title = QLabel()
        self.title.setObjectName('Title')
        self.instructions = QLabel()
        self.instructions.setWordWrap(True)
        self.instructions.setObjectName('Muted')
        form.addWidget(self.title)
        form.addWidget(self.instructions)
        fields = QFormLayout()
        self.username = QLineEdit()
        self.username.setMaxLength(64)
        self.password = QLineEdit()
        self.confirmation = QLineEdit()
        for entry in (self.password, self.confirmation):
            entry.setMaxLength(256)
            entry.setEchoMode(QLineEdit.Password)
            entry.returnPressed.connect(self.login)
        fields.addRow('Użytkownik', self.username)
        fields.addRow('Hasło', self.password)
        self.confirmation_label = QLabel('Powtórz hasło')
        fields.addRow(self.confirmation_label, self.confirmation)
        form.addLayout(fields)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setObjectName('Error')
        form.addWidget(self.error)
        self.submit = add_button(form, '', self.login)
        layout.addStretch()
        layout.addWidget(card, 0, Qt.AlignCenter)
        layout.addStretch()

    def reset(self):
        self.creating = self.accounts.record() is None
        self.title.setText(f'Utwórz konto w {APP_NAME}' if self.creating else f'Zaloguj się do {APP_NAME}')
        self.instructions.setText('Pierwsze uruchomienie. Wybierz nazwę użytkownika i hasło (co najmniej 8 znaków).'
                                  if self.creating else 'Wpisz dane swojego lokalnego konta.')
        self.confirmation.setVisible(self.creating)
        self.confirmation_label.setVisible(self.creating)
        self.submit.setText('Utwórz konto i wejdź' if self.creating else 'Zaloguj się')
        self.password.clear()
        self.confirmation.clear()
        self.error.clear()
        self.username.setFocus()

    def login(self):
        username = self.username.text().strip()
        password = self.password.text()
        try:
            if self.creating:
                if password != self.confirmation.text():
                    raise ValueError('Hasła muszą być identyczne.')
                self.accounts.create(username, password)
            elif not self.accounts.verify(username, password):
                raise ValueError('Nieprawidłowy użytkownik lub hasło.')
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        except sqlite3.Error:
            self.error.setText('Nie udało się odczytać lub zapisać lokalnego konta.')
            return
        self.password.clear()
        self.confirmation.clear()
        self.signed_in.emit(username)


class WeightsDialog(QDialog):
    weights_changed = pyqtSignal(dict)
    EXAMPLE_VALUES = (0.0, 0.5, 1.0)

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Wagi kryteriów IOP')
        self.setMinimumWidth(515)
        self.data = data
        self.values = dict(data.overrides)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Wybierz kryterium i ustaw wagę od −1 do +1. Mapa reaguje podczas zmiany.'))
        self.criterion = QComboBox()
        for column in sorted(data.weights):
            name = data.labels.get(column, column.upper())
            self.criterion.addItem(f'{name} · {column.upper()}', column)
        layout.addWidget(self.criterion)
        row = QHBoxLayout()
        row.addWidget(QLabel('−1'))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setAccessibleName('Waga wybranego kryterium')
        self.slider.setRange(-100, 100)
        self.slider.setPageStep(10)
        row.addWidget(self.slider, 1)
        row.addWidget(QLabel('+1'))
        self.weight_display = QLabel()
        self.weight_display.setFixedWidth(55)
        row.addWidget(self.weight_display)
        layout.addLayout(row)
        self.baseline = QLabel()
        self.baseline.setObjectName('Muted')
        layout.addWidget(self.baseline)

        formula = QLabel('Zmiana IOP = wartość po normalizacji × (nowa waga − waga z bazy) ÷ liczba kryteriów')
        formula.setWordWrap(True)
        layout.addWidget(formula)
        hint = QLabel('Poniższe przykłady pokazują zmianę względem IOP z bazy. Znak „+” oznacza wzrost wyniku, a „−” spadek.')
        hint.setObjectName('Muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.impact_table = QTableWidget(len(self.EXAMPLE_VALUES), 3)
        self.impact_table.setAccessibleName('Przykładowa zmiana IOP po zmianie wagi')
        self.impact_table.setHorizontalHeaderLabels(['Wartość po normalizacji', 'Obliczenie', 'Zmiana IOP'])
        header = self.impact_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.impact_table.verticalHeader().hide()
        self.impact_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.impact_table.setSelectionMode(QTableWidget.NoSelection)
        self.impact_table.setSizeAdjustPolicy(QTableWidget.AdjustToContents)
        self.impact_table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        layout.addWidget(self.impact_table)

        row = QHBoxLayout()
        add_button(row, 'Przywróć tę wagę', self.reset_one)
        add_button(row, 'Przywróć wszystkie', self.reset_all)
        row.addStretch()
        add_button(row, 'Zamknij', self.accept)
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.publish)
        self.finished.connect(self.flush)
        self.criterion.currentIndexChanged.connect(self.show_weight)
        self.slider.valueChanged.connect(self.move_weight)
        self.show_weight()

    def show_weight(self):
        column = self.criterion.currentData()
        baseline = self.data.weights[column]
        value = self.values.get(column, baseline)
        with QSignalBlocker(self.slider):
            self.slider.setValue(round(value * 100))
        self.weight_display.setText(f'{value:+.2f}'.replace('.', ','))
        self.baseline.setText(f'Waga z bazy: {baseline:+.2f}  ·  Zmienione kryteria: {len(self.values)}'.replace('.', ','))
        self.show_weight_impact(value - baseline)

    def show_weight_impact(self, weight_change):
        count = len(self.data.weights)
        for row, normalized in enumerate(self.EXAMPLE_VALUES):
            change = normalized * weight_change / count
            cells = (
                f'{normalized:.2f}',
                f'{normalized:.2f} × ({weight_change:+.2f}) ÷ {count}',
                f'{change:+.4f}' if change else '0,0000',
            )
            for column_index, cell in enumerate(cells):
                item = QTableWidgetItem(cell.replace('.', ',').replace('-', '−'))
                item.setTextAlignment(Qt.AlignCenter)
                self.impact_table.setItem(row, column_index, item)

    def move_weight(self, slider_position):
        column = self.criterion.currentData()
        weight = slider_position / 100
        if weight == self.data.weights[column]:
            self.values.pop(column, None)
        else:
            self.values[column] = weight
        self.show_weight()
        self.timer.start()

    def reset_one(self):
        self.values.pop(self.criterion.currentData(), None)
        self.show_weight()
        self.publish()

    def reset_all(self):
        self.values.clear()
        self.show_weight()
        self.publish()

    def publish(self):
        self.timer.stop()
        self.weights_changed.emit(dict(self.values))

    def flush(self):
        if self.timer.isActive():
            self.publish()


class StyleDialog(QDialog):
    PRESET_COLORS = (
        ('Czerwony', DEFAULT_IOP_COLORS[0]), ('Pomarańczowy', '#f97316'), ('Żółty', '#facc15'),
        ('Zielony', DEFAULT_IOP_COLORS[2]), ('Niebieski', '#2563eb'), ('Fioletowy', '#9333ea'),
        ('Biały', DEFAULT_IOP_COLORS[1]), ('Szary', '#808080'), ('Czarny', '#000000'),
    )

    def __init__(self, limits, colors, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edytuj styl IOP')
        self.setMinimumWidth(430)
        form = QFormLayout(self)
        hint = QLabel('Kliknij próbkę, aby wybrać kolor. Wartości poza zakresem przyjmują kolor najbliższego końca skali.')
        hint.setWordWrap(True)
        form.addRow(hint)
        self.lower, self.upper = QDoubleSpinBox(), QDoubleSpinBox()
        for spin, minimum, maximum, value in ((self.lower, -1, -.0001, limits[0]), (self.upper, .0001, 1, limits[1])):
            spin.setDecimals(4)
            spin.setRange(minimum, maximum)
            spin.setSingleStep(.005)
            spin.setValue(float(value))
        self.color_buttons = []
        self.palette_colors = list(colors)
        for index, (caption, value) in enumerate((('Minimum', self.lower), ('Zero', QLabel('0')), ('Maksimum', self.upper))):
            row = QHBoxLayout()
            row.addWidget(value, 1)
            button = QPushButton()
            button.setMinimumWidth(130)
            button.setToolTip(f'Wybierz kolor dla wartości: {caption.lower()}')
            button.setAccessibleName(f'Wybierz kolor — {caption}')
            button.setAutoDefault(False)
            menu = QMenu(button)
            for color_name, color in self.PRESET_COLORS:
                menu.addAction(self.swatch_icon(color), color_name,
                               partial(self.set_color, index, color))
            menu.addSeparator()
            menu.addAction('Wpisz kod HEX…', partial(self.choose_hex, index, caption))
            button.setMenu(menu)
            row.addWidget(button)
            self.color_buttons.append(button)
            self.update_swatch(index)
            form.addRow(caption, row)
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Apply).setText('Zastosuj')
        buttons.button(QDialogButtonBox.Cancel).setText('Anuluj')
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def limits(self):
        return Decimal(str(self.lower.value())), Decimal(str(self.upper.value()))

    def colors(self):
        return tuple(self.palette_colors)

    def choose_hex(self, index, name):
        text, accepted = QInputDialog.getText(
            self, f'Kolor — {name}', 'Kod HEX (#RRGGBB)', text=self.palette_colors[index],
        )
        if not accepted:
            return
        code = '#' + text.strip().lstrip('#')
        color = QColor(code)
        if len(code) == 7 and color.isValid():
            self.set_color(index, color.name())
        else:
            QMessageBox.warning(self, 'Nieprawidłowy kolor', 'Wpisz sześć cyfr lub liter od A do F, np. #2563EB.')

    def set_color(self, index, color):
        self.palette_colors[index] = color
        self.update_swatch(index)

    def update_swatch(self, index):
        color = self.palette_colors[index]
        button = self.color_buttons[index]
        button.setIcon(self.swatch_icon(color))
        button.setText(color.upper())

    @staticmethod
    def swatch_icon(color):
        swatch = QPixmap(16, 16)
        swatch.fill(QColor(color))
        return QIcon(swatch)


class AttributeTableModel(QAbstractTableModel):
    BATCH_SIZE = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers = []
        self.descriptions = []
        self.features = []
        self.iterator = None

    def set_layer(self, layer, labels):
        self.close_iterator()
        self.beginResetModel()
        self.features.clear()
        self.headers = []
        self.descriptions = []
        for index, field in enumerate(layer.fields()):
            name = field.name()
            header = layer.attributeDisplayName(index)
            base = name.removesuffix('_norm').removesuffix('_waga')
            detail = labels.get(base)
            if name == SCENARIO_FIELD:
                detail = 'IOP z aktualnymi wagami'
            parts = [part for part in (header, name, detail) if part]
            self.headers.append(header)
            self.descriptions.append(' · '.join(dict.fromkeys(parts)))
        self.iterator = layer.getFeatures(QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry))
        self.endResetModel()
        self.fetchMore()

    def close_iterator(self):
        if self.iterator is not None:
            self.iterator.close()
            self.iterator = None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.features)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def canFetchMore(self, parent=QModelIndex()):
        return not parent.isValid() and self.iterator is not None

    def fetchMore(self, parent=QModelIndex()):
        if not self.canFetchMore(parent):
            return
        batch = list(islice(self.iterator, self.BATCH_SIZE))
        if len(batch) < self.BATCH_SIZE:
            self.close_iterator()
        if batch:
            start = len(self.features)
            self.beginInsertRows(QModelIndex(), start, start + len(batch) - 1)
            self.features.extend(batch)
            self.endInsertRows()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.headers[section]
            if role == Qt.ToolTipRole:
                return self.descriptions[section]
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role in (Qt.DisplayRole, Qt.ToolTipRole):
            value = self.features[index.row()][index.column()]
            if QgsVariantUtils.isNull(value):
                return '—'
            return f'{value:.12g}' if isinstance(value, float) else str(value)
        return None


class SearchDialog(QDialog):
    feature_chosen = pyqtSignal(object, object)
    selection_cleared = pyqtSignal()

    def __init__(self, layers, selected_key, labels, parent=None):
        super().__init__(parent)
        self.layers = layers
        self.labels = labels
        self.setWindowTitle('Tabela atrybutów')
        self.resize(850, 550)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.layer_choice = QComboBox()
        for key, layer in layers.items():
            self.layer_choice.addItem(layer.name(), key)
        self.layer_choice.setCurrentIndex(max(0, self.layer_choice.findData(selected_key)))
        form.addRow('Warstwa', self.layer_choice)
        self.query = QLineEdit()
        self.query.setClearButtonEnabled(True)
        self.query.setPlaceholderText('Wpisz pełną nazwę atrybutu lub jej fragment, np. iop')
        form.addRow('Nazwa atrybutu', self.query)
        layout.addLayout(form)
        self.status = QLabel()
        self.status.setObjectName('Muted')
        layout.addWidget(self.status)
        self.model = AttributeTableModel(self)
        self.table = QTableView()
        self.table.setAccessibleName('Atrybuty i wartości dla wybranej warstwy')
        self.table.setModel(self.model)
        self.table.horizontalHeader().setDefaultSectionSize(145)
        self.table.setHorizontalScrollMode(QTableView.ScrollPerPixel)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.selectionModel().selectionChanged.connect(self.sync_buttons)
        self.table.doubleClicked.connect(self.choose)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        clear = add_button(row, 'Usuń zaznaczenie', self.table.clearSelection)
        clear.clicked.connect(self.selection_cleared.emit)
        row.addStretch()
        self.show_feature = add_button(row, 'Pokaż na mapie', self.choose)
        close = add_button(row, 'Zamknij', self.reject)
        layout.addLayout(row)
        for button in (clear, self.show_feature, close):
            button.setAutoDefault(False)
        self.layer_choice.currentIndexChanged.connect(self.change_layer)
        self.query.textChanged.connect(self.filter_fields)
        self.finished.connect(self.model.close_iterator)
        self.change_layer()
        self.query.setFocus()

    def change_layer(self):
        key = self.layer_choice.currentData()
        self.model.set_layer(self.layers[key], self.labels if isinstance(key, int) else {})
        self.filter_fields()
        self.table.scrollToTop()

    def filter_fields(self):
        query = self.query.text().strip().casefold()
        visible = 0
        for column, name in enumerate(self.model.descriptions):
            matches = query in name.casefold()
            self.table.setColumnHidden(column, not matches)
            visible += matches
        self.table.horizontalScrollBar().setValue(0)
        if not visible:
            self.status.setText('Brak atrybutów pasujących do wpisanej nazwy.' if query else 'Warstwa nie ma atrybutów.')
        elif not self.model.rowCount():
            self.status.setText('Warstwa nie zawiera obiektów. W tabeli widać nazwy atrybutów.')
        else:
            self.status.setText(f'Widoczne atrybuty: {visible} z {self.model.columnCount()}')
        self.sync_buttons()

    def sync_buttons(self):
        self.show_feature.setEnabled(bool(self.table.selectionModel().selectedRows()) and
                                     self.table.horizontalHeader().hiddenSectionCount() < self.model.columnCount())

    def choose(self):
        rows = self.table.selectionModel().selectedRows()
        if rows and self.show_feature.isEnabled():
            feature = self.model.features[rows[0].row()]
            self.feature_chosen.emit(self.layer_choice.currentData(), feature.id())
            self.accept()
