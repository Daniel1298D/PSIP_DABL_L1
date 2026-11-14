"""Launch GeoAnaliza as its own desktop application, without opening QGIS."""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate', action='store_true', help='Check live map data and theme palettes without opening a window')
    args = parser.parse_args()
    if args.validate:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from qgis.core import QgsApplication
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QFont
    QgsApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QgsApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QgsApplication([], True)
    app.setOrganizationName('PSIP')
    app.setApplicationName('GeoAnaliza')
    app.setStyle('Fusion')
    app.setFont(QFont('Segoe UI', 10))
    app.initQgis()
    if args.validate:
        from desktop.data import MapData
        from desktop.theme import THEMES, qt_palette
        data = MapData()
        data.load()
        for mode in ('full', 'detail'):
            data.set_style(mode)
            for grid in data.grids.values():
                style = grid.layer.renderer()
                assert style.ranges()[0].symbol().color().name() == '#ff0000'
                assert style.sourceColorRamp().color(.5).name() == '#ffffff'
                assert style.ranges()[-1].symbol().color().name() == '#008000'
        for colors in THEMES.values():
            assert qt_palette(colors).color(qt_palette(colors).Window).name() == colors['surface']
        print(json.dumps(dict(data.report(), themes=list(THEMES), validation='passed'), indent=2))
        del data
        app.exitQgis()
        return 0
    from desktop.window import MainWindow
    window = MainWindow()
    window.showMaximized()
    result = app.exec()
    window.close()
    del window
    app.exitQgis()
    return result


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        # pythonw has no console: keep startup failures inspectable on this PC.
        import logging
        folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'GeoAnaliza'
        folder.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=folder / 'startup.log', level=logging.ERROR, encoding='utf-8')
        logging.exception('GeoAnaliza startup failed')
        raise
