from __future__ import annotations

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
)
from qgis.gui import (
    QgsMapTool,
    QgsRubberBand,
)


class PolygonMapTool(QgsMapTool):
    """
    Map tool used to draw a polygonal area of interest.

    Controls
    --------
    Left click:
        Add a polygon vertex.

    Right click:
        Finish the polygon.

    Escape:
        Cancel polygon drawing.
    """

    polygon_created = pyqtSignal(object)
    drawing_cancelled = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)

        self.canvas = canvas

        self.vertices: list[QgsPointXY] = []
        self.preview_point: QgsPointXY | None = None

        self.rubber_band = QgsRubberBand(
            self.canvas,
            QgsWkbTypes.PolygonGeometry,
        )

        self.rubber_band.setFillColor(
            QColor(0, 120, 215, 70)
        )

        self.rubber_band.setStrokeColor(
            QColor(0, 90, 180, 255)
        )

        self.rubber_band.setWidth(3)

    def canvasPressEvent(self, event) -> None:
        """
        Add a vertex with the left mouse button or finish with the right one.
        """
        if event.button() == Qt.LeftButton:
            map_point = self.toMapCoordinates(
                event.pos()
            )

            self.vertices.append(
                QgsPointXY(map_point)
            )

            self.preview_point = None

            self._refresh_rubber_band()

        elif event.button() == Qt.RightButton:
            self.finish_polygon()

    def canvasMoveEvent(self, event) -> None:
        """
        Update the temporary vertex while the mouse moves.
        """
        if not self.vertices:
            return

        map_point = self.toMapCoordinates(
            event.pos()
        )

        self.preview_point = QgsPointXY(
            map_point
        )

        self._refresh_rubber_band()

    def keyPressEvent(self, event) -> None:
        """
        Cancel polygon drawing when Escape is pressed.
        """
        if event.key() == Qt.Key_Escape:
            self.cancel_drawing()
            return

        super().keyPressEvent(event)

    def finish_polygon(self) -> None:
        """
        Finish and emit the polygon geometry.
        """
        if len(self.vertices) < 3:
            return

        polygon_geometry = self._create_polygon_geometry(
            include_preview=False
        )

        if polygon_geometry is None:
            return

        if (
            polygon_geometry.isNull()
            or polygon_geometry.isEmpty()
        ):
            return

        if not polygon_geometry.isGeosValid():
            return

        emitted_geometry = QgsGeometry(
            polygon_geometry
        )

        self.clear()

        self.polygon_created.emit(
            emitted_geometry
        )

    def _create_polygon_geometry(
        self,
        include_preview: bool,
    ) -> QgsGeometry | None:
        """
        Build a polygon geometry from the current vertices.
        """
        points = [
            QgsPointXY(point)
            for point in self.vertices
        ]

        if (
            include_preview
            and self.preview_point is not None
        ):
            points.append(
                QgsPointXY(self.preview_point)
            )

        if len(points) < 2:
            return None

        # A polygon requires at least three different vertices.
        # During the preview, duplicate the last point temporarily
        # until three vertices are available.
        if len(points) == 2:
            points.append(
                QgsPointXY(points[-1])
            )

        if points[0] != points[-1]:
            points.append(
                QgsPointXY(points[0])
            )

        return QgsGeometry.fromPolygonXY(
            [points]
        )

    def _refresh_rubber_band(self) -> None:
        """
        Update the polygon preview shown on the QGIS canvas.
        """
        self.rubber_band.reset(
            QgsWkbTypes.PolygonGeometry
        )

        if not self.vertices:
            self.canvas.refresh()
            return

        geometry = self._create_polygon_geometry(
            include_preview=True
        )

        if geometry is None:
            self.canvas.refresh()
            return

        self.rubber_band.setToGeometry(
            geometry,
            None,
        )

        self.rubber_band.show()
        self.rubber_band.updatePosition()
        self.canvas.refresh()

    def cancel_drawing(self) -> None:
        """
        Clear the temporary polygon and emit a cancellation signal.
        """
        self.clear()

        self.drawing_cancelled.emit()

    def clear(self) -> None:
        """
        Remove the temporary polygon.
        """
        self.vertices.clear()
        self.preview_point = None

        self.rubber_band.reset(
            QgsWkbTypes.PolygonGeometry
        )

        self.canvas.refresh()

    def deactivate(self) -> None:
        """
        Called when another QGIS map tool becomes active.
        """
        super().deactivate()