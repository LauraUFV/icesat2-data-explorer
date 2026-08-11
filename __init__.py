def classFactory(iface):
    """QGIS plugin entry point."""
    from .sliderule_support import ensure_support_path

    ensure_support_path()

    from .icesat2_plugin import ICESat2DataExplorerPlugin

    return ICESat2DataExplorerPlugin(iface)
