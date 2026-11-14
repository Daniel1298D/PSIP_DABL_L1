"""Export a vector PDF from the current QGIS canvas without exporting source data."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis, QgsLayout, QgsLayoutExporter, QgsLayoutItemLabel, QgsLayoutItemMap, QgsLayoutItemPage,
    QgsLayoutPoint, QgsLayoutSize, QgsProject,
)


def export_map_pdf(canvas, destination, *, iop_limits=None):
    destination = Path(destination)
    layers = canvas.layers()
    extent = canvas.extent()
    if not layers or extent.isEmpty():
        raise ValueError('Brak widocznej mapy do wyeksportowania.')

    layout = QgsLayout(QgsProject.instance())
    layout.initializeDefaults()
    page = layout.pageCollection().pages()[0]
    page.setPageSize('A4', QgsLayoutItemPage.Landscape)
    ink = QColor('#17372a')

    def caption(text, x, y, width, height, *, size=9, bold=False, background=None, align=Qt.AlignLeft):
        item = QgsLayoutItemLabel(layout)
        item.setText(text)
        item.setFont(QFont('Segoe UI', size, QFont.Bold if bold else QFont.Normal))
        item.setFontColor(ink)
        item.setHAlign(align)
        item.setVAlign(Qt.AlignVCenter)
        if background is not None:
            item.setBackgroundColor(QColor(background))
            item.setBackgroundEnabled(True)
            item.setFrameStrokeColor(QColor('#8b9e92'))
            item.setFrameEnabled(True)
        layout.addLayoutItem(item)
        item.attemptMove(QgsLayoutPoint(x, y))
        item.attemptResize(QgsLayoutSize(width, height))

    caption('GeoAnaliza | Mapa przejezdności', 10, 6, 215, 11, size=16, bold=True)
    caption(f'{len(layers)} widoczne warstwy · {canvas.mapSettings().destinationCrs().authid()}',
            10, 17, 215, 7)
    map_top = 28
    map_height = 156
    available_width = 277
    ratio = extent.width() / extent.height()
    width = min(available_width, map_height * ratio)
    height = width / ratio

    item = QgsLayoutItemMap(layout)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint((297 - width) / 2, map_top + (map_height - height) / 2))
    item.attemptResize(QgsLayoutSize(width, height))
    item.setCrs(canvas.mapSettings().destinationCrs())
    item.setLayers(layers)
    item.setKeepLayerSet(True)
    item.setBackgroundColor(canvas.mapSettings().backgroundColor())
    item.setBackgroundEnabled(True)
    item.setFrameEnabled(True)
    item.setFrameStrokeColor(QColor('#8b9e92'))
    item.zoomToExtent(extent)

    if iop_limits is not None:
        caption('Skala IOP', 10, 189, 28, 9, bold=True)
        low, high = iop_limits
        for index, (color, value) in enumerate((('#ff0000', low), ('#ffffff', 0), ('#008000', high))):
            x = 40 + index * 42
            caption('', x, 191, 7, 5, background=color)
            caption(f'{value:g}'.replace('.', ','), x + 8, 189, 30, 9)
    scale = f'{round(item.scale()):,}'.replace(',', ' ')
    caption(f'Skala wydruku 1 : {scale}', 195, 189, 92, 9, align=Qt.AlignRight)
    caption('GeoAnaliza · PSIP', 10, 199, 140, 6, size=8)

    settings = QgsLayoutExporter.PdfExportSettings()
    settings.forceVectorOutput = True
    settings.exportMetadata = False
    settings.textRenderFormat = Qgis.TextRenderFormat.AlwaysText
    with TemporaryDirectory(prefix='.geoanaliza-', dir=destination.parent) as folder:
        staged = Path(folder) / 'mapa.pdf'
        exporter = QgsLayoutExporter(layout)
        result = exporter.exportToPdf(str(staged), settings)
        if result != QgsLayoutExporter.Success or not staged.is_file():
            raise OSError('Nie udało się wygenerować pliku PDF.')
        os.replace(staged, destination)
