"""Regression test for coordinates borrowed from the native map click signal."""

from importlib.util import find_spec
import os
import unittest


@unittest.skipUnless(find_spec('qgis'), 'Requires the QGIS desktop Python runtime')
class DesktopMeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], True)
        cls.app.initQgis()

    def test_distinct_canvas_clicks_produce_a_nonzero_distance(self):
        from qgis.PyQt.QtCore import QPoint, Qt
        from qgis.PyQt.QtTest import QTest
        from qgis.core import QgsCoordinateReferenceSystem, QgsPointXY, QgsRectangle
        from qgis.gui import QgsMapCanvas
        from desktop.map_tools import DistanceTool

        canvas = QgsMapCanvas()
        self.addCleanup(canvas.close)
        canvas.resize(900, 550)
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
        canvas.setExtent(QgsRectangle(2310000, 6830000, 2350000, 6880000))
        canvas.show()
        tool = DistanceTool(canvas)
        canvas.setMapTool(tool)
        QTest.qWait(60)

        viewport = canvas.viewport()
        start, end = QPoint(305, 183), QPoint(590, 332)
        QTest.mouseClick(viewport, Qt.LeftButton, pos=start)
        first = QgsPointXY(tool.markers[0].center())
        QTest.mouseClick(viewport, Qt.LeftButton, pos=end)
        second = QgsPointXY(tool.markers[1].center())
        self.assertEqual(tool.points, [first, second])
        self.assertGreater(tool.meters, 1000)
        self.assertAlmostEqual(tool.meters, tool.measure.measureLine(first, second), places=6)
        self.assertEqual(tool.line.asGeometry().asPolyline(), [first, second])
