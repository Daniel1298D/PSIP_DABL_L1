"""Save an IOP map project in PostgreSQL, with live PostGIS layers only."""
from __future__ import annotations

import argparse
import json
import math
import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlencode

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter, QFont
from qgis.core import (
    QgsApplication, QgsClassificationEqualInterval, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsDataSourceUri, QgsFeatureRequest, QgsFillSymbol,
    QgsGradientColorRamp, QgsGraduatedSymbolRenderer, QgsLayerTreeModel,
    QgsMapRendererParallelJob, QgsMapSettings, QgsMapThemeCollection, QgsProject,
    QgsProviderRegistry, QgsReferencedRectangle, QgsRendererRange, QgsVectorLayer,
    QgsWkbTypes,
)


def renderer(lower: Decimal, upper: Decimal, classes: int):
    """Use equal numeric intervals and equally spaced colors, including red/white."""
    step = (upper - lower) / classes
    ramp = QgsGradientColorRamp(QColor('#ff0000'), QColor('#ffffff'))
    ranges = []
    for i in range(classes):
        start, end = lower + i * step, lower + (i + 1) * step
        color = ramp.color(i / (classes - 1))
        symbol = QgsFillSymbol.createSimple({
            'color': color.name(), 'outline_color': '#a36c6c', 'outline_width': '0.025',
        })
        label = f'{start:+.3f} — {end:+.3f}'.replace('.', ',')
        ranges.append(QgsRendererRange(float(start), float(end), symbol, label))
    result = QgsGraduatedSymbolRenderer('iop', ranges)
    result.setClassificationMethod(QgsClassificationEqualInterval())
    result.updateColorRamp(ramp)
    assert result.ranges()[0].symbol().color().name() == '#ff0000'
    assert result.ranges()[-1].symbol().color().name() == '#ffffff'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', default='5434')
    parser.add_argument('--database', default='psip')
    parser.add_argument('--user', default='psip')
    parser.add_argument('--project-schema', default='qgis')
    parser.add_argument('--project-name', default='IOP_Warszawa_H3_7_8_9')
    parser.add_argument('--preview-dir', type=Path)
    args = parser.parse_args()
    password = os.environ['PGPASSWORD']
    app = QgsApplication([], False)
    app.initQgis()
    project = QgsProject.instance()
    project.setTitle('Warszawa — IOP H3 7, 8, 9 — PostgreSQL')
    crs = QgsCoordinateReferenceSystem('EPSG:3857')
    project.setCrs(crs)
    project.setBackgroundColor(QColor('white'))

    def layer(table, name, schema='viz', srid=3857):
        uri = QgsDataSourceUri()
        uri.setConnection(args.host, args.port, args.database, args.user, password)
        uri.setDataSource(schema, table, 'geom', '', 'id')
        uri.setSrid(str(srid))
        uri.setWkbType(QgsWkbTypes.MultiPolygon)
        result = QgsVectorLayer(uri.uri(False), name, 'postgres')
        if not result.isValid() or result.crs().authid() != f'EPSG:{srid}':
            raise RuntimeError(f'Invalid PostgreSQL layer {schema}.{table}')
        return result

    root = project.layerTreeRoot()
    full = root.addGroup('IOP | skala −1…+1 | równe przedziały co 0,01')
    detail = root.addGroup('IOP | szczegóły | wspólna skala z zakresu danych')
    layers = {'full': {}, 'detail': {}}
    summary = {}
    minimum, maximum = math.inf, -math.inf
    for resolution in (7, 8, 9):
        item = layer(f'iop_h3_{resolution}', f'H3 {resolution} — IOP — PostgreSQL')
        request = QgsFeatureRequest().setSubsetOfAttributes(['iop'], item.fields()).setFlags(QgsFeatureRequest.NoGeometry)
        values = [float(feature['iop']) for feature in item.getFeatures(request)]
        if not values or any(not math.isfinite(v) or not -1 <= v <= 1 for v in values):
            raise RuntimeError(f'Invalid IOP values: H3 {resolution}')
        minimum, maximum = min(minimum, min(values)), max(maximum, max(values))
        summary[resolution] = {'rows': len(values), 'min': min(values), 'max': max(values)}
        item.setRenderer(renderer(Decimal('-1'), Decimal('1'), 200))
        layers['full'][resolution] = item
    detail_lower = Decimal(str(math.floor(minimum * 100) / 100))
    detail_upper = Decimal(str(math.ceil(maximum * 100) / 100))
    if detail_lower == detail_upper:
        detail_upper += Decimal('0.01')
    detail.setName(f'IOP | szczegóły {detail_lower}…{detail_upper} | 20 równych przedziałów')
    for resolution in (7, 8, 9):
        layers['detail'][resolution] = layer(f'iop_h3_{resolution}', f'H3 {resolution} — IOP — PostgreSQL')
        layers['detail'][resolution].setRenderer(renderer(detail_lower, detail_upper, 20))
    for mode, group in [('full', full), ('detail', detail)]:
        for resolution in (7, 8, 9):
            item = layers[mode][resolution]
            # Normalize field captions without changing database column names.
            for field in item.fields():
                name = field.name()
                if name.endswith('_norm'):
                    alias = name[:-5].upper() + ' — normalizacja [0,1]'
                elif name.endswith('_waga'):
                    alias = name[:-5].upper() + ' — waga [−1,1]'
                elif name.endswith(('_a', '_l', '_p')):
                    alias = name.upper() + ' [' + {'a': 'm²', 'l': 'm', 'p': 'liczba'}[name[-1]] + ']'
                elif name == 'iop':
                    alias = 'IOP — współczynnik przejezdności'
                else:
                    continue
                item.setFieldAlias(item.fields().indexFromName(name), alias)
            item.setCustomProperty('iop_display_scale', mode)
            project.addMapLayer(item, False)
            node = group.addLayer(item)
            node.setItemVisibilityChecked(resolution == 8)
            node.setExpanded(False)
        group.setIsMutuallyExclusive(True, 1)

    boundary = layer('powiat', 'Granica Warszawy — PostgreSQL', 'grid', 2180)
    boundary.renderer().setSymbol(QgsFillSymbol.createSimple({
        'style': 'no', 'outline_color': '#4d4d4d', 'outline_width': '0.3',
    }))
    project.addMapLayer(boundary, False)
    root.insertLayer(0, boundary).setExpanded(False)
    extent = QgsCoordinateTransform(boundary.crs(), crs, project.transformContext()).transformBoundingBox(boundary.extent())
    extent.scale(1.08)
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(extent, crs))
    model = QgsLayerTreeModel(root)

    def select(mode, resolution):
        for name, group in [('full', full), ('detail', detail)]:
            for r, item in layers[name].items():
                root.findLayer(item.id()).setItemVisibilityChecked(r == resolution)
            # Checking a child can also check its parent: set group visibility last.
            group.setItemVisibilityChecked(name == mode)

    for mode, scale_name in [('full', 'skala −1…+1'), ('detail', 'szczegóły')]:
        for resolution in (7, 8, 9):
            select(mode, resolution)
            project.mapThemeCollection().insert(f'H3 {resolution} | {scale_name}',
                QgsMapThemeCollection.createThemeFromCurrentState(root, model))
    select('full', 8)
    full.setExpanded(True)
    detail.setExpanded(False)

    # The project itself is stored in PostgreSQL, not just its spatial layers.
    connection_uri = QgsDataSourceUri()
    connection_uri.setConnection(args.host, args.port, args.database, args.user, password)
    connection = QgsProviderRegistry.instance().providerMetadata('postgres').createConnection(connection_uri.uri(False), {})
    schema = '"' + args.project_schema.replace('"', '""') + '"'
    connection.executeSql(f'CREATE SCHEMA IF NOT EXISTS {schema}')
    query = urlencode({'dbname': args.database, 'schema': args.project_schema, 'project': args.project_name})
    storage_uri = f'postgresql://{quote(args.user, safe="")}:{quote(password, safe="")}@{args.host}:{args.port}?{query}'
    if not project.write(storage_uri):
        raise RuntimeError('Cannot save QGIS project in PostgreSQL')

    # Reload the database project and check persisted renderer/source settings.
    project.clear()
    if not project.read(storage_uri):
        raise RuntimeError('Cannot reload QGIS project from PostgreSQL')
    restored = [l for l in project.mapLayers().values() if l.name().startswith('H3 ')]
    if len(restored) != 6:
        raise RuntimeError('Incomplete stored project')
    for item in project.mapLayers().values():
        if not item.isValid() or item.providerType() != 'postgres':
            raise RuntimeError('Project must contain only live PostgreSQL layers')
    for item in restored:
        ranges = item.renderer().ranges()
        mode = item.customProperty('iop_display_scale')
        expected = (-1., 1., 200) if mode == 'full' else (float(detail_lower), float(detail_upper), 20)
        if (ranges[0].lowerValue(), ranges[-1].upperValue(), len(ranges)) != expected:
            raise RuntimeError('Stored classification changed')
        if ranges[0].symbol().color().name() != '#ff0000' or ranges[-1].symbol().color().name() != '#ffffff':
            raise RuntimeError('Stored endpoint colors changed')
        step = (expected[1] - expected[0]) / expected[2]
        if any(abs(r.upperValue() - r.lowerValue() - step) > 1e-12 for r in ranges):
            raise RuntimeError('Intervals are not equal')
    visible_maps = [l for l in restored if project.layerTreeRoot().findLayer(l.id()).isVisible()]
    if len(visible_maps) != 1 or not visible_maps[0].name().startswith('H3 8 ') or visible_maps[0].customProperty('iop_display_scale') != 'full':
        raise RuntimeError('Default view must show H3 8 with the full -1..1 scale')

    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
        # Diagnostic rendering reads the same PostGIS providers; it exports no vector data.
        sheet = QImage(1800, 1240, QImage.Format_ARGB32)
        sheet.fill(QColor('white'))
        images = []
        bound = next(l for l in project.mapLayers().values() if l.name().startswith('Granica'))
        for row, mode in enumerate(('full', 'detail')):
            for col, resolution in enumerate((7, 8, 9)):
                item = next(l for l in restored if l.name().startswith(f'H3 {resolution} ') and l.customProperty('iop_display_scale') == mode)
                settings = QgsMapSettings()
                settings.setLayers([bound, item])
                settings.setDestinationCrs(crs)
                settings.setExtent(extent)
                settings.setOutputSize(QSize(600, 560))
                settings.setBackgroundColor(QColor('white'))
                job = QgsMapRendererParallelJob(settings)
                job.start()
                job.waitForFinished()
                if job.errors():
                    raise RuntimeError(str(job.errors()))
                text = f'H3 {resolution} | ' + ('skala -1 do +1, krok 0,01' if mode == 'full' else f'szczegóły {detail_lower} do {detail_upper}')
                images.append((row, col, job.renderedImage(), text))
        painter = QPainter(sheet)
        font = QFont('Arial')
        font.setPixelSize(18)
        painter.setFont(font)
        painter.setPen(QColor('#222222'))
        for row, col, rendered, label in images:
            painter.drawImage(col * 600, row * 620 + 40, rendered)
            painter.drawText(col * 600 + 20, row * 620 + 28, label)
        painter.end()
        if not sheet.save(str(args.preview_dir / 'IOP_H3_porownanie.png')):
            raise RuntimeError('Cannot save diagnostic rendering')
    print(json.dumps({'project_storage': 'PostgreSQL', 'project_schema': args.project_schema,
        'project_name': args.project_name, 'data_provider': 'postgres', 'host': args.host,
        'port': args.port, 'crs': project.crs().authid(), 'layers': summary,
        'main_scale': {'min': -1, 'max': 1, 'classes': 200, 'interval': .01},
        'optional_detail_scale': {'min': str(detail_lower), 'max': str(detail_upper), 'classes': 20},
        'endpoint_colors': ['#ff0000', '#ffffff'], 'default_view': 'H3 8 | -1..1',
        'round_trip_validation': True}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
