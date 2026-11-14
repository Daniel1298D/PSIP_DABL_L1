"""Controls for signing in, changing the map style, and searching a grid."""

from decimal import Decimal
import sqlite3

from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSlider, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from qgis.core import QgsFeatureRequest

from .data import SCENARIO_FIELD


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
        fields.addRow('Użytkownik', self.username)
        fields.addRow('Hasło', self.password)
        self.confirmation_label = QLabel('Powtórz hasło')
        fields.addRow(self.confirmation_label, self.confirmation)
        form.addLayout(fields)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setObjectName('Error')
        form.addWidget(self.error)
        self.submit = QPushButton()
        self.submit.clicked.connect(self.login)
        self.password.returnPressed.connect(self.login)
        self.confirmation.returnPressed.connect(self.login)
        form.addWidget(self.submit)
        layout.addStretch()
        layout.addWidget(card, 0, Qt.AlignCenter)
        layout.addStretch()

    def reset(self):
        self.creating = self.accounts.record() is None
        self.title.setText('Utwórz konto GeoAnaliza' if self.creating else 'Zaloguj się do GeoAnalizy')
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
        row = QHBoxLayout()
        reset_one = QPushButton('Przywróć tę wagę')
        reset_one.clicked.connect(self.reset_one)
        row.addWidget(reset_one)
        reset_all = QPushButton('Przywróć wszystkie')
        reset_all.clicked.connect(self.reset_all)
        row.addWidget(reset_all)
        row.addStretch()
        close = QPushButton('Zamknij')
        close.clicked.connect(self.accept)
        row.addWidget(close)
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
        previous = self.slider.blockSignals(True)
        self.slider.setValue(round(value * 100))
        self.slider.blockSignals(previous)
        self.weight_display.setText(f'{value:+.2f}'.replace('.', ','))
        self.baseline.setText(f'Waga z bazy: {baseline:+.2f}  ·  Zmienione kryteria: {len(self.values)}'.replace('.', ','))

    def move_weight(self, value):
        column = self.criterion.currentData()
        if value / 100 == self.data.weights[column]:
            self.values.pop(column, None)
        else:
            self.values[column] = value / 100
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
    def __init__(self, limits, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edytuj zakres kolorów IOP')
        self.setMinimumWidth(395)
        form = QFormLayout(self)
        hint = QLabel('Minimum jest czerwone, zero białe, maksimum zielone. Wartości poza zakresem zachowują kolor skrajny.')
        hint.setWordWrap(True)
        form.addRow(hint)
        self.lower, self.upper = QDoubleSpinBox(), QDoubleSpinBox()
        for spin, minimum, maximum, value in ((self.lower, -1, -.0001, limits[0]), (self.upper, .0001, 1, limits[1])):
            spin.setDecimals(4)
            spin.setRange(minimum, maximum)
            spin.setSingleStep(.005)
            spin.setValue(float(value))
        form.addRow('Minimum (czerwony)', self.lower)
        form.addRow('Maksimum (zielony)', self.upper)
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Apply).setText('Zastosuj')
        buttons.button(QDialogButtonBox.Cancel).setText('Anuluj')
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def limits(self):
        return Decimal(str(self.lower.value())), Decimal(str(self.upper.value()))


def attribute_text(value):
    return f'{value:.12g}' if isinstance(value, float) else str(value)


class SearchDialog(QDialog):
    feature_chosen = pyqtSignal(object)
    selection_cleared = pyqtSignal()
    ROW_LIMIT = 200

    def __init__(self, layer, labels, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.fields = layer.fields()
        self.identity = [column for column in ('id', 'h3_index') if column in self.fields.names()]
        self.setWindowTitle(f'Szukaj atrybutów · {layer.name()}')
        self.resize(680, 490)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.field = QComboBox()
        self.field.setMinimumContentsLength(26)
        priority = {'h3_index': 'Identyfikator H3', 'id': 'Identyfikator', 'iop': 'IOP z bazy',
                    SCENARIO_FIELD: 'IOP z aktualnymi wagami'}
        fields = self.fields.names()
        for column in dict.fromkeys([name for name in priority if name in fields] + fields):
            base = column.removesuffix('_norm').removesuffix('_waga')
            caption = f'{column} · {labels[base]}' if base in labels else column
            self.field.addItem(priority.get(column, caption), column)
        self.query = QLineEdit()
        self.query.setPlaceholderText('Wpisz całość lub fragment wartości')
        form.addRow('Atrybut', self.field)
        form.addRow('Szukana wartość', self.query)
        layout.addLayout(form)
        search = QPushButton('Szukaj')
        search.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        self.field.currentIndexChanged.connect(self.clear_results)
        layout.addWidget(search, 0, Qt.AlignRight)
        self.status = QLabel()
        self.status.setObjectName('Muted')
        layout.addWidget(self.status)
        headers = ['Identyfikator obiektu']
        if 'h3_index' in self.identity:
            headers.append('Identyfikator H3')
        headers.append('Wartość')
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.sync_buttons)
        self.table.itemDoubleClicked.connect(self.choose)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        clear = QPushButton('Usuń zaznaczenie')
        clear.clicked.connect(self.selection_cleared.emit)
        row.addWidget(clear)
        row.addStretch()
        self.show_feature = QPushButton('Pokaż na mapie')
        self.show_feature.clicked.connect(self.choose)
        row.addWidget(self.show_feature)
        close = QPushButton('Zamknij')
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)
        self.clear_results()

    def clear_results(self):
        self.table.setRowCount(0)
        self.status.setText('Wybierz atrybut i wpisz wartość.')
        self.sync_buttons()

    def sync_buttons(self):
        self.show_feature.setEnabled(bool(self.table.selectedItems()))

    def search(self):
        self.table.setRowCount(0)
        column = self.field.currentData()
        query = self.query.text().strip().casefold()
        if not query or column is None:
            self.clear_results()
            return
        field = self.fields.field(column)
        if field.isNumeric():
            query = query.replace(',', '.')
        request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry)
        request.setSubsetOfAttributes(list(dict.fromkeys(self.identity + [column])), self.fields)
        matches = 0
        for feature in self.layer.getFeatures(request):
            value = attribute_text(feature[column])
            if query not in value.casefold():
                continue
            matches += 1
            if matches > self.ROW_LIMIT:
                continue
            index = self.table.rowCount()
            self.table.insertRow(index)
            cells = [str(feature['id'] if 'id' in self.identity else feature.id())]
            if 'h3_index' in self.identity:
                cells.append(str(feature['h3_index']))
            cells.append(value)
            for col, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setData(Qt.UserRole, feature.id())
                self.table.setItem(index, col, item)
        suffix = f' · pokazano {self.ROW_LIMIT}, zawęź wyszukiwanie' if matches > self.ROW_LIMIT else ''
        self.status.setText(f'Wyniki: {matches}{suffix}' if matches else 'Brak pasujących obiektów.')
        self.sync_buttons()

    def choose(self):
        items = self.table.selectedItems()
        if items:
            self.feature_chosen.emit(items[0].data(Qt.UserRole))
            self.accept()
