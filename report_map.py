from __future__ import annotations

import base64
from typing import Iterable

from qgis.PyQt.QtCore import (
    QByteArray,
    QBuffer,
    QIODevice,
    QSize,
)
from qgis.PyQt.QtGui import (
    QColor,
    QFont,
    QPainter,
)
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFillSymbol,
    QgsGeometry,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
)


def _expanded_extent(
    extent: QgsRectangle,
) -> QgsRectangle:
    result = QgsRectangle(
        extent
    )
    width = max(
        result.width(),
        0.0001,
    )
    height = max(
        result.height(),
        0.0001,
    )
    result.grow(
        max(
            width,
            height,
        )
        * 0.30
    )
    return result


def _background_attribution(
    layers: Iterable,
) -> str:
    layer_list = list(
        layers
    )

    if not layer_list:
        return (
            "No visible background layer was available; "
            "the AOI is shown on a neutral background."
        )

    source_text = " ".join(
        (
            str(layer.name())
            + " "
            + str(layer.source())
        ).lower()
        for layer in layer_list
    )

    if (
        "openstreetmap" in source_text
        or "tile.openstreetmap.org" in source_text
        or "osm standard" in source_text
    ):
        return (
            "Background: © OpenStreetMap contributors. "
            "Rendered from the visible QGIS project layers."
        )

    return (
        "Background rendered from the visible QGIS project "
        "layers at report-generation time."
    )


def _draw_attribution(
    image,
    text: str,
) -> None:
    if image.isNull():
        return

    painter = QPainter(
        image
    )

    try:
        painter.setRenderHint(
            QPainter.TextAntialiasing,
            True,
        )
        font = QFont()
        font.setPointSize(
            8
        )
        painter.setFont(
            font
        )
        metrics = painter.fontMetrics()
        margin = 10
        padding = 6
        text_width = min(
            image.width() - 2 * margin,
            max(
                280,
                metrics.horizontalAdvance(
                    text
                )
                + 2 * padding,
            ),
        )
        text_height = (
            metrics.height()
            + 2 * padding
        )
        x_value = (
            image.width()
            - margin
            - text_width
        )
        y_value = (
            image.height()
            - margin
            - text_height
        )
        painter.fillRect(
            x_value,
            y_value,
            text_width,
            text_height,
            QColor(
                255,
                255,
                255,
                220,
            ),
        )
        painter.setPen(
            QColor(
                45,
                61,
                70,
            )
        )
        painter.drawText(
            x_value + padding,
            y_value + padding,
            text_width - 2 * padding,
            metrics.height(),
            0,
            text,
        )
    finally:
        painter.end()


def _image_data_uri(
    image,
) -> str:
    byte_array = QByteArray()
    buffer = QBuffer(
        byte_array
    )
    buffer.open(
        QIODevice.WriteOnly
    )

    try:
        if not image.save(
            buffer,
            "PNG",
        ):
            return ""
    finally:
        buffer.close()

    encoded = base64.b64encode(
        bytes(byte_array)
    ).decode(
        "ascii"
    )
    return (
        "data:image/png;base64,"
        + encoded
    )


def render_aoi_overview(
    iface,
    polygon_wkt: str | None,
    excluded_layer_ids: set[str] | None = None,
) -> dict[str, str | None]:
    """
    Render the AOI over the currently visible QGIS project layers.

    A visible XYZ basemap in QGIS will therefore appear in the report.
    No separate online basemap is forced by the plugin.
    """
    if not polygon_wkt:
        return {
            "data_uri": None,
            "caption": None,
            "warning": (
                "The AOI map could not be generated because "
                "no AOI geometry was available."
            ),
        }

    try:
        geometry = QgsGeometry.fromWkt(
            polygon_wkt
        )

        if (
            geometry.isNull()
            or geometry.isEmpty()
        ):
            raise ValueError(
                "The AOI geometry is empty."
            )

        aoi_layer = QgsVectorLayer(
            "Polygon?crs=EPSG:4326",
            "Report area of interest",
            "memory",
        )

        if not aoi_layer.isValid():
            raise RuntimeError(
                "The temporary AOI layer could not be created."
            )

        feature = QgsFeature()
        feature.setGeometry(
            geometry
        )
        aoi_layer.dataProvider().addFeatures(
            [feature]
        )
        aoi_layer.updateExtents()

        symbol = QgsFillSymbol.createSimple(
            {
                "color": "30,136,168,55",
                "outline_color": "8,83,112,255",
                "outline_width": "1.4",
            }
        )
        aoi_layer.renderer().setSymbol(
            symbol
        )

        canvas = iface.mapCanvas()
        canvas_settings = canvas.mapSettings()
        destination_crs = (
            canvas_settings.destinationCrs()
        )

        if not destination_crs.isValid():
            destination_crs = (
                QgsCoordinateReferenceSystem(
                    "EPSG:4326"
                )
            )

        source_crs = QgsCoordinateReferenceSystem(
            "EPSG:4326"
        )
        extent = geometry.boundingBox()

        if source_crs != destination_crs:
            transform = QgsCoordinateTransform(
                source_crs,
                destination_crs,
                QgsProject.instance(),
            )
            extent = transform.transformBoundingBox(
                extent
            )

        excluded = (
            excluded_layer_ids
            or set()
        )

        background_layers = [
            layer
            for layer in canvas.layers()
            if (
                layer is not None
                and layer.isValid()
                and layer.id() not in excluded
            )
        ]

        attribution = _background_attribution(
            background_layers
        )

        settings = QgsMapSettings()
        settings.setLayers(
            [
                aoi_layer,
                *background_layers,
            ]
        )
        settings.setDestinationCrs(
            destination_crs
        )
        settings.setTransformContext(
            QgsProject.instance()
            .transformContext()
        )
        settings.setBackgroundColor(
            QColor(
                244,
                247,
                248,
            )
        )
        settings.setOutputSize(
            QSize(
                1200,
                620,
            )
        )
        settings.setOutputDpi(
            110
        )
        settings.setExtent(
            _expanded_extent(
                extent
            )
        )

        renderer = QgsMapRendererParallelJob(
            settings
        )
        renderer.start()
        renderer.waitForFinished()
        image = renderer.renderedImage()

        if image.isNull():
            raise RuntimeError(
                "QGIS returned an empty map image."
            )

        _draw_attribution(
            image,
            attribution,
        )
        data_uri = _image_data_uri(
            image
        )

        if not data_uri:
            raise RuntimeError(
                "The rendered map could not be encoded as PNG."
            )

        return {
            "data_uri": data_uri,
            "caption": attribution,
            "warning": None,
        }

    except Exception as error:
        return {
            "data_uri": None,
            "caption": None,
            "warning": (
                "The AOI map could not be rendered: "
                f"{type(error).__name__}: {error}"
            ),
        }
