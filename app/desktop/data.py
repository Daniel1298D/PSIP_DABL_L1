"""Read the existing H3 results directly from PostGIS, without exporting data."""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING
import json
import os
import socket
from pathlib import Path

from qgis.PyQt.QtCore import QSettings, QVariant
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsDataSourceUri,
    QgsFeatureRequest, QgsField, QgsFillSymbol, QgsProject, QgsVectorLayer, QgsWkbTypes,
)
from python.iop_style import DEFAULT_IOP_COLORS, custom_renderer, renderer

SCENARIO_FIELD = 'iop_scenariusz'


class DataError(RuntimeError):
    """A connection/data error with a message that never contains credentials."""


@dataclass(repr=False)
class DatabaseConfig:
    host: str
    port: str
    database: str
    user: str
    password: str = field(repr=False)

    @classmethod
    def from_environment(cls):
        profile = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / 'QGIS/QGIS3/profiles/default/QGIS/QGIS3.ini'
        settings = QSettings(str(profile), QSettings.IniFormat)
        prefix = 'PostgreSQL/connections/[PSIP] env-test/'
        def value(name, default=''):
            return str(os.environ.get('PSIP_DB_' + name.upper()) or settings.value(prefix + name, default) or default)
        password = os.environ.get('PSIP_DB_PASSWORD') or os.environ.get('PGPASSWORD') or str(settings.value(prefix + 'password', '') or '')
        if not password:
            raise DataError('Brakuje hasła do bazy. Ustaw PSIP_DB_PASSWORD albo zapisz hasło połączenia [PSIP] env-test w QGIS.')
        return cls(value('host', 'localhost'), value('port', '5434'), value('database', 'psip'), value('username', 'psip'), password)

    def uri(self, schema, table, srid):
        uri = QgsDataSourceUri()
        uri.setConnection(self.host, self.port, self.database, self.user, self.password)
        uri.setDataSource(schema, table, 'geom', '', 'id')
        uri.setSrid(str(srid))
        uri.setWkbType(QgsWkbTypes.MultiPolygon)
        return uri.uri(False)


@dataclass
class Grid:
    resolution: int
    layer: QgsVectorLayer
    count: int
    minimum: float
    maximum: float


def _attribute_request(layer, column_names):
    return QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes(column_names, layer.fields())


def _rounded_detail_limit(ranges):
    largest = max(abs(value) for bounds in ranges for value in bounds)
    step = Decimal('0.01')
    return max(step, Decimal(str(largest)).quantize(step, rounding=ROUND_CEILING))


class MapData:
    """Own all layers for this application; never open or modify a QGIS project."""
    def __init__(self):
        self.grids = {}
        self.boundary = None
        self.limit = Decimal('0.07')
        self.crs = QgsCoordinateReferenceSystem('EPSG:3857')
        self.extent = None
        self.weights = {}
        self.labels = {}
        self.overrides = {}
        self.scenario_ranges = {}

    def load(self):
        config = DatabaseConfig.from_environment()
        try:
            with socket.create_connection((config.host, int(config.port)), timeout=3):
                pass
        except (OSError, ValueError):
            raise DataError(f'Baza env-test nie odpowiada na porcie {config.port}. Uruchom Docker Desktop i kontener remote-db-env-test-postgis-1, następnie spróbuj ponownie.') from None
        os.environ.setdefault('PGCONNECT_TIMEOUT', '5')
        grids = {resolution: self._read_grid(config, resolution) for resolution in (7, 8, 9)}
        config_path = Path(__file__).resolve().parents[1] / 'config/iop_weights.json'
        groups = json.loads(config_path.read_text(encoding='utf-8'))['criteria']
        self.labels = {column: group['label'] for group in groups for column in group['columns']}
        for grid in grids.values():
            layer = grid.layer
            weights = self._read_weights(layer)
            if self.weights and weights != self.weights:
                raise DataError('Siatki mają różne zestawy wag. Sprawdź wyniki IOP w bazie.')
            self.weights = weights
            layer.addExpressionField('"iop"', QgsField(SCENARIO_FIELD, QVariant.Double))
        boundary = QgsVectorLayer(config.uri('grid', 'powiat', 2180), 'Granica Warszawy', 'postgres')
        if not boundary.isValid():
            raise DataError('Nie udało się odczytać granicy Warszawy z bazy.')
        limit = _rounded_detail_limit((grid.minimum, grid.maximum) for grid in grids.values())
        self.grids, self.boundary, self.limit = grids, boundary, limit
        self.set_style('detail')
        self.set_boundary_color('#50645a')
        transform = QgsCoordinateTransform(boundary.crs(), self.crs, QgsProject.instance().transformContext())
        self.extent = transform.transformBoundingBox(boundary.extent())
        self.extent.scale(1.12)

    @staticmethod
    def _read_grid(config, resolution):
        layer = QgsVectorLayer(config.uri('viz', f'iop_h3_{resolution}', 3857), f'H3 {resolution} — IOP', 'postgres')
        if not layer.isValid():
            raise DataError(f'Nie udało się odczytać H3 {resolution}. Sprawdź, czy Docker i baza env-test na porcie {config.port} działają.')
        index = layer.fields().indexFromName('iop')
        count = layer.featureCount()
        if index < 0 or count <= 0:
            raise DataError(f'Warstwa H3 {resolution} nie zawiera wyników IOP.')
        if layer.crs().authid() != 'EPSG:3857':
            raise DataError('Nieoczekiwany układ warstwy mapowej.')
        return Grid(resolution, layer, count, float(layer.minimumValue(index)), float(layer.maximumValue(index)))

    @staticmethod
    def _read_weights(layer):
        names = layer.fields().names()
        columns = [name.removesuffix('_norm') for name in names if name.endswith('_norm')]
        weight_fields = [column + '_waga' for column in columns]
        if not columns or any(name not in names for name in weight_fields):
            raise DataError('Warstwa nie zawiera pełnego zestawu wag i normalizacji.')
        example = next(layer.getFeatures(_attribute_request(layer, weight_fields).setLimit(1)), None)
        if example is None:
            raise DataError('Nie można odczytać wag z PostgreSQL.')
        return {column: float(example[field]) for column, field in zip(columns, weight_fields)}

    def style_limits(self, mode, custom=None):
        if mode == 'custom' and custom is not None:
            return custom
        limit = Decimal('1') if mode == 'full' else self.detail_limit()
        return -limit, limit

    def set_style(self, mode, custom=None, *, colors=DEFAULT_IOP_COLORS):
        lower, upper = self.style_limits(mode, custom)
        if mode == 'custom' and custom is not None:
            style = custom_renderer(lower, upper, SCENARIO_FIELD, colors=colors)
        else:
            step = Decimal('0.01') if mode == 'full' else Decimal('0.005')
            classes = int((upper - lower) / step)
            style = renderer(lower, upper, classes, SCENARIO_FIELD, colors=colors)
        for grid in self.grids.values():
            grid.layer.setRenderer(style.clone())
            grid.layer.triggerRepaint()
        return lower, upper

    def detail_limit(self):
        if not self.scenario_ranges:
            return self.limit
        return _rounded_detail_limit(self.scenario_ranges.values())

    def set_weights(self, overrides):
        if any(column not in self.weights or not -1 <= value <= 1 for column, value in overrides.items()):
            raise ValueError('Każda waga musi należeć do przedziału [−1, +1].')
        self.overrides = {column: value for column, value in overrides.items() if value != self.weights[column]}
        terms = [f'"{column}_norm" * ({value:.8f} - "{column}_waga")' for column, value in self.overrides.items()]
        expression = '"iop"'
        if terms:
            expression += f' + ({" + ".join(terms)}) / {len(self.weights)}'
        self.scenario_ranges.clear()
        for resolution, grid in self.grids.items():
            layer = grid.layer
            layer.updateExpressionField(layer.fields().indexFromName(SCENARIO_FIELD), expression)
            if terms:
                request = _attribute_request(layer, [SCENARIO_FIELD])
                values = [float(feature[SCENARIO_FIELD]) for feature in layer.getFeatures(request)]
                self.scenario_ranges[resolution] = min(values), max(values)
            layer.triggerRepaint()

    def set_boundary_color(self, color):
        if self.boundary:
            self.boundary.renderer().setSymbol(QgsFillSymbol.createSimple({
                'style': 'no', 'outline_color': color, 'outline_width': '0.35',
            }))
            self.boundary.triggerRepaint()

    def report(self):
        return {'source': 'PostgreSQL / env-test', 'map_crs': self.crs.authid(),
                'detail_limit': str(self.limit), 'layers': [
                    {'resolution': g.resolution, 'provider': g.layer.providerType(), 'rows': g.count,
                     'minimum': g.minimum, 'maximum': g.maximum, 'fields': len(g.layer.fields())}
                    for g in self.grids.values()]}
