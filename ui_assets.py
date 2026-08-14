from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

PLUGIN_ROOT = Path(__file__).resolve().parent
ICONS_ROOT = PLUGIN_ROOT / "icons"


def icon_path(name: str) -> str:
    return str(ICONS_ROOT / name)


def icon(name: str) -> QIcon:
    return QIcon(icon_path(name))


def set_button_icon(button, name: str, size: int = 18) -> None:
    button.setIcon(icon(name))
    button.setIconSize(QSize(size, size))


def apply_dialog_theme(widget) -> None:
    widget.setStyleSheet(
        """
        QDialog {
            background: #f4f7f9;
            color: #263642;
        }
        QFrame#ICESat2Header {
            background: #ffffff;
            border: 1px solid #dce5ea;
            border-radius: 10px;
        }
        QLabel#ICESat2HeaderTitle {
            color: #123f55;
            font-size: 19px;
            font-weight: 700;
        }
        QLabel#ICESat2HeaderSubtitle,
        QLabel[muted="true"] {
            color: #61717c;
        }
        QLabel#ICESat2ProductBadge {
            color: white;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 9px;
        }
        QGroupBox {
            background: #ffffff;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            margin-top: 11px;
            padding: 12px 10px 10px 10px;
            font-weight: 650;
            color: #244a5b;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 5px;
        }
        QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox {
            min-height: 27px;
            padding: 2px 6px;
            background: #ffffff;
            border: 1px solid #c9d5dc;
            border-radius: 5px;
        }
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
        QDoubleSpinBox:focus, QSpinBox:focus {
            border: 1px solid #1684a5;
        }
        QComboBox QAbstractItemView {
            background: #ffffff;
            color: #263642;
            border: 1px solid #c9d5dc;
            outline: 0;
            selection-background-color: rgba(22, 132, 165, 38);
            selection-color: #123f55;
        }
        QComboBox QAbstractItemView::item {
            min-height: 26px;
            padding: 3px 7px;
            background: transparent;
            color: #263642;
        }
        QComboBox QAbstractItemView::item:selected {
            background: rgba(22, 132, 165, 38);
            color: #123f55;
        }
        QPushButton {
            min-height: 28px;
            padding: 4px 11px;
            background: #ffffff;
            border: 1px solid #bdcbd3;
            border-radius: 6px;
        }
        QPushButton:hover {
            background: #edf6f8;
            border-color: #6fa5b5;
        }
        QPushButton[primary="true"] {
            color: white;
            background: #146b8b;
            border-color: #146b8b;
            font-weight: 650;
        }
        QPushButton[primary="true"]:hover {
            background: #0f5873;
        }
        QPushButton:disabled {
            color: #8e9aa1;
            background: #eef1f3;
        }
        QProgressBar {
            min-height: 15px;
            border: 1px solid #cbd6dc;
            border-radius: 6px;
            text-align: center;
            background: #edf1f3;
        }
        QProgressBar::chunk {
            border-radius: 5px;
            background: #58a52e;
        }
        QFrame#ICESat2StatusPanel {
            background: #eef7fa;
            border: 1px solid #cde2e9;
            border-radius: 7px;
        }
        """
    )


def create_dialog_header(
    title: str,
    subtitle: str,
    icon_name: str = "plugin.svg",
    version: str | None = None,
) -> QWidget:
    frame = QFrame()
    frame.setObjectName("ICESat2Header")

    layout = QHBoxLayout(frame)
    layout.setContentsMargins(14, 11, 14, 11)
    layout.setSpacing(12)

    image = QLabel()
    image.setPixmap(icon(icon_name).pixmap(QSize(46, 46)))
    image.setFixedSize(48, 48)
    image.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(image)

    text_layout = QVBoxLayout()
    text_layout.setSpacing(2)

    title_label = QLabel(title)
    title_label.setObjectName("ICESat2HeaderTitle")
    text_layout.addWidget(title_label)

    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("ICESat2HeaderSubtitle")
    subtitle_label.setWordWrap(True)
    text_layout.addWidget(subtitle_label)

    layout.addLayout(text_layout, 1)

    if version:
        version_label = QLabel(version)
        version_label.setProperty("muted", True)
        version_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(version_label)

    return frame
