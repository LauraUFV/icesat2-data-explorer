from __future__ import annotations

from types import MethodType

from qgis.PyQt.QtWidgets import QAction


def install_model_tide_feature(plugin) -> None:
    """
    Add the model-based tide action without importing pyTMD in QGIS.
    """
    if getattr(
        plugin,
        "_model_tide_feature_installed",
        False,
    ):
        return

    plugin._model_tide_feature_installed = True
    plugin.model_tide_dialog = None

    action = QAction(
        "Add Model Tide Values",
        plugin.iface.mainWindow(),
    )

    plugin.model_tide_action = action

    def open_model_tide_dialog(self) -> None:
        from .model_tide_dialog import ModelTideDialog

        if self.model_tide_dialog is None:
            self.model_tide_dialog = ModelTideDialog(
                iface=self.iface,
                parent=self.iface.mainWindow(),
            )
        else:
            self.model_tide_dialog.refresh_layers()
            self.model_tide_dialog.refresh_support_status()

        self.model_tide_dialog.show()
        self.model_tide_dialog.raise_()
        self.model_tide_dialog.activateWindow()

    plugin.open_model_tide_dialog = MethodType(
        open_model_tide_dialog,
        plugin,
    )

    action.triggered.connect(
        plugin.open_model_tide_dialog
    )

    plugin.iface.addToolBarIcon(action)

    plugin.iface.addPluginToVectorMenu(
        "ICESat-2 Data Explorer",
        action,
    )

    original_unload = plugin.unload

    def unload_with_model_tide(self) -> None:
        try:
            if self.model_tide_dialog is not None:
                self.model_tide_dialog.close()
                self.model_tide_dialog = None

            if self.model_tide_action is not None:
                self.iface.removeToolBarIcon(
                    self.model_tide_action
                )
                self.iface.removePluginVectorMenu(
                    "ICESat-2 Data Explorer",
                    self.model_tide_action,
                )
                self.model_tide_action.deleteLater()
                self.model_tide_action = None
        finally:
            original_unload()

    plugin.unload = MethodType(
        unload_with_model_tide,
        plugin,
    )
