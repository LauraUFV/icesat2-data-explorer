from __future__ import annotations

from types import MethodType

from qgis.PyQt.QtWidgets import QAction


def install_profile_feature(plugin) -> None:
    """
    Add the profile action without importing Matplotlib during plugin startup.

    The profile module is imported only after the user clicks
    "Open ICESat-2 Profile".
    """
    if getattr(plugin, "_profile_feature_installed", False):
        return

    plugin._profile_feature_installed = True
    plugin.profile_dialog = None

    profile_action = QAction(
        "Open ICESat-2 Profile",
        plugin.iface.mainWindow(),
    )

    plugin.profile_action = profile_action

    def open_profile_dialog(self) -> None:
        # Lazy import: Matplotlib and NumPy are loaded only now.
        from .profile_dialog import ICESat2ProfileDialog

        if self.profile_dialog is None:
            self.profile_dialog = ICESat2ProfileDialog(
                iface=self.iface,
                parent=self.iface.mainWindow(),
            )
        else:
            self.profile_dialog.refresh_layers()

        self.profile_dialog.show()
        self.profile_dialog.raise_()
        self.profile_dialog.activateWindow()

    plugin.open_profile_dialog = MethodType(
        open_profile_dialog,
        plugin,
    )

    profile_action.triggered.connect(
        plugin.open_profile_dialog
    )

    plugin.iface.addToolBarIcon(profile_action)

    plugin.iface.addPluginToVectorMenu(
        "ICESat-2 Data Explorer",
        profile_action,
    )

    original_unload = plugin.unload

    def unload_with_profile(self) -> None:
        try:
            if self.profile_dialog is not None:
                self.profile_dialog.close()
                self.profile_dialog = None

            if self.profile_action is not None:
                self.iface.removeToolBarIcon(
                    self.profile_action
                )

                self.iface.removePluginVectorMenu(
                    "ICESat-2 Data Explorer",
                    self.profile_action,
                )

                self.profile_action.deleteLater()
                self.profile_action = None
        finally:
            original_unload()

    plugin.unload = MethodType(
        unload_with_profile,
        plugin,
    )
