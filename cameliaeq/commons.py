import os
import sys

# Common application-wide constants and helpers

APP_NAME = "CameliaEQ"


def user_config_dir() -> str:
    """Return (and create if needed) the user configuration directory for the app.

    macOS: ~/Library/Application Support/CameliaEQ
    Linux:  ~/.config/CameliaEQ
    """
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.path.expanduser("~/.config")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def create_fallback_tray_icon():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor

    icon = QIcon.fromTheme("audio-volume-high")
    if not icon.isNull():
        return icon
    pm = QPixmap(22, 22)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QColor(70, 130, 180))  # steel blue
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, 18, 18)
    p.end()
    return QIcon(pm)
