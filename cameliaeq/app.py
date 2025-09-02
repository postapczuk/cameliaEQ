import sys

from PySide6 import QtGui
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

from .settings import Settings, APP_NAME
from .tray_window import TrayWindow


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # Make this host window a tool (though we don't show it)
        self.settings = Settings.load()
        self.setWindowFlags(self.windowFlags() | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowIcon(QtGui.QIcon("../icon.icns"))

        # Tray icon
        self.tray = QSystemTrayIcon(self)
        # Try theme icon first; fallback to a simple drawn pixmap to ensure the tray is visible
        icon = QIcon.fromTheme("audio-volume-high")
        if icon.isNull():
            icon = self.create_fallback_tray_icon()
        self.tray.setIcon(icon)
        self.tray.setToolTip(APP_NAME)
        print("Tray icon created")

        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()
        print("Context menu created")

        # Main small window
        self.window = TrayWindow(self.settings)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_window()

    def _anchor_point(self):
        # Try to get tray icon geometry; fallback to the cursor position
        rect = self.tray.geometry()
        if rect and rect.width() > 0 and rect.height() > 0:
            return rect.center(), rect
        # Fallback: current cursor position
        from PySide6.QtGui import QCursor
        pos = QCursor.pos()
        return pos, None

    def position_window_under_tray(self):
        anchor, rect = self._anchor_point()
        # Determine target screen
        screen = QApplication.screenAt(anchor)
        if screen is None:
            screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        margin = 6
        w = self.window.width()
        h = self.window.height()
        if rect and rect.height() > 0:
            x = rect.center().x() - w // 2
            y = rect.bottom() + margin
            # If bottom overflows screen, place above the icon
            if avail and y + h > avail.bottom():
                y = rect.top() - h - margin
        else:
            # Anchor by cursor; place below
            x = anchor.x() - w // 2
            y = anchor.y() + margin
            if avail and y + h > avail.bottom():
                y = anchor.y() - h - margin
        # Clamp within available geometry
        if avail:
            x = max(avail.left(), min(x, avail.right() - w))
            y = max(avail.top(), min(y, avail.bottom() - h))
        self.window.move(x, y)

    def toggle_window(self):
        if self.window.isVisible():
            self.window.hide()
        else:
            self.position_window_under_tray()
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()

    def open_settings_window(self):
        self.window.open_settings()


    def create_fallback_tray_icon(self):
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


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    win = MainApp()
    # Keep the tray running; no main window
    sys.exit(app.exec())
