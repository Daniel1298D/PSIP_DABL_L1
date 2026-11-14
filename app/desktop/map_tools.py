"""Interactive map distance measured on the WGS84 ellipsoid."""

from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication
from qgis.core import QgsDistanceArea, QgsGeometry, QgsPointXY, QgsProject, QgsWkbTypes
from qgis.gui import QgsMapToolEmitPoint, QgsMapToolPan, QgsRubberBand, QgsVertexMarker


class InspectPanTool(QgsMapToolPan):
    clicked = pyqtSignal(int, int)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.start = None

    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start = QPoint(event.pos())
        super().canvasPressEvent(event)

    def canvasReleaseEvent(self, event):
        position = QPoint(event.pos())
        inspect = (event.button() == Qt.LeftButton and self.start is not None
                   and not self.isDragging()
                   and (position - self.start).manhattanLength() < QApplication.startDragDistance())
        if event.button() == Qt.LeftButton:
            self.start = None
        if inspect:
            self.clicked.emit(position.x(), position.y())
        else:
            super().canvasReleaseEvent(event)

    def deactivate(self):
        self.start = None
        super().deactivate()


class DistanceTool(QgsMapToolEmitPoint):
    message = pyqtSignal(str)
    measured = pyqtSignal(float)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.points = []
        self.meters = None
        self.measure = QgsDistanceArea()
        self.measure.setSourceCrs(canvas.mapSettings().destinationCrs(), QgsProject.instance().transformContext())
        self.measure.setEllipsoid('WGS84')
        self.line = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.line.setColor(QColor('#2259c6'))
        self.line.setSecondaryStrokeColor(QColor('#ffffff'))
        self.line.setWidth(3)
        self.markers = []
        for _ in range(2):
            marker = QgsVertexMarker(canvas)
            marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
            marker.setIconSize(10)
            marker.setPenWidth(2)
            marker.setColor(QColor('#2259c6'))
            marker.setFillColor(QColor('#ffffff'))
            self.markers.append(marker)
        self.setCursor(Qt.CrossCursor)
        self.canvasClicked.connect(self.add_point)
        self.clear()

    def activate(self):
        super().activate()
        self.restart()

    def restart(self):
        self.clear()
        self.message.emit('Pomiar · kliknij punkt początkowy')

    def deactivate(self):
        if self.meters is None:
            self.clear()
        super().deactivate()

    def clear(self):
        self.points.clear()
        self.meters = None
        self.line.reset(QgsWkbTypes.LineGeometry)
        for marker in self.markers:
            marker.hide()

    def add_point(self, point, button):
        if button != Qt.LeftButton:
            return
        if len(self.points) == 2:
            self.clear()
        # The native click signal lends its coordinate only until the slot returns.
        point = QgsPointXY(point)
        marker = self.markers[len(self.points)]
        marker.setCenter(point)
        marker.show()
        self.points.append(point)
        if len(self.points) == 1:
            self.message.emit('Pomiar · kliknij punkt końcowy')
            return
        self.line.setToGeometry(QgsGeometry.fromPolylineXY(self.points), None)
        self.line.show()
        self.meters = self.measure.measureLine(*self.points)
        self.measured.emit(self.meters)
