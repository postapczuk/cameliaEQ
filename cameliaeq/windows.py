import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QGridLayout,
    QLabel,
    QDial,
    QPushButton,
    QApplication,
    QMessageBox,
)

from .core import (
    load_yaml,
    save_yaml,
    ensure_filters_and_pipeline,
    ensure_devices_section,
    ensure_mixers_processors,
    read_gain,
    write_gain,
    DEFAULT_FILTERS,
    try_reload_camilla,
)
from .commons import APP_NAME
from .settings import Settings, SettingsWindow


class TrayWindow(QWidget):
    def __init__(self, settings: Settings):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        # Keep the small window always on top and as a tool window; fix size
        self.setWindowFlags(self.windowFlags() | Qt.Tool | Qt.WindowStaysOnTopHint)

        self.settings = settings
        self.resize(320, 220)

        main_layout = QVBoxLayout()

        # Knobs group
        knobs_group = QGroupBox("Tone Controls (dB)")
        grid = QGridLayout()

        self.knobs = {}
        self.value_labels = {}
        for idx, name in enumerate(["Bass", "Middle", "Treble"]):
            label = QLabel(name)
            dial = QDial()
            dial.setRange(-12, 12)
            dial.setNotchesVisible(True)
            dial.setPageStep(1)
            dial.setWrapping(False)
            dial.setValue(0)
            value_label = QLabel("0 dB")
            value_label.setAlignment(Qt.AlignHCenter)

            def make_on_change(nm=name, d=dial, vl=value_label):
                def _on_change(val):
                    vl.setText(f"{val} dB")
                    self.schedule_apply()
                return _on_change

            dial.valueChanged.connect(make_on_change())

            grid.addWidget(label, 0, idx)
            grid.addWidget(dial, 1, idx)
            grid.addWidget(value_label, 2, idx)
            self.knobs[name] = dial
            self.value_labels[name] = value_label

        knobs_group.setLayout(grid)
        main_layout.addWidget(knobs_group)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        main_layout.addWidget(self.settings_btn)

        self.setLayout(main_layout)
        self.setFixedSize(self.sizeHint())

        # Debounce timer for apply
        self.apply_timer = QTimer(self)
        self.apply_timer.setSingleShot(True)
        self.apply_timer.setInterval(400)  # ms
        self.apply_timer.timeout.connect(self.apply_changes)

        self.load_initial_values()

    def open_settings(self):
        self.settings_win = SettingsWindow(self.settings, self.on_settings_saved)
        # Make settings a tool and always on top too, and center over the tray window
        self.settings_win.setWindowFlags(self.settings_win.windowFlags() | Qt.Tool | Qt.WindowStaysOnTopHint)
        try:
            parent_geom = self.geometry()
            sw = self.settings_win.sizeHint().width()
            sh = self.settings_win.sizeHint().height()
            x = parent_geom.center().x() - sw // 2
            y = parent_geom.center().y() - sh // 2
            screen = QApplication.screenAt(parent_geom.center()) or QApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                x = max(avail.left(), min(x, avail.right() - sw))
                y = max(avail.top(), min(y, avail.bottom() - sh))
            self.settings_win.setGeometry(x, y, sw, sh)
        except Exception:
            pass
        self.settings_win.show()
        self.settings_win.raise_()
        self.settings_win.activateWindow()

    def on_settings_saved(self, settings: Settings):
        self.settings = settings
        self.load_initial_values()

    def schedule_apply(self):
        self.apply_timer.start()

    def load_initial_values(self):
        cfg = load_yaml(self.settings.config_path)
        if not cfg:
            return
        # Ensure required structures; save if changed
        changed = False
        if ensure_filters_and_pipeline(cfg):
            changed = True
        if ensure_devices_section(cfg, self.settings.playback_device):
            changed = True
        if ensure_mixers_processors(cfg):
            changed = True
        if changed and self.settings.config_path:
            save_yaml(self.settings.config_path, cfg)
        for name in ["Bass", "Middle", "Treble"]:
            gain = read_gain(cfg, name)
            if gain is None and name in DEFAULT_FILTERS:
                gain = DEFAULT_FILTERS[name]["parameters"]["gain"]
            if gain is not None and name in self.knobs:
                self.knobs[name].blockSignals(True)
                self.knobs[name].setValue(int(round(gain)))
                self.knobs[name].blockSignals(False)
                if name in self.value_labels:
                    self.value_labels[name].setText(f"{int(round(gain))} dB")

    def apply_changes(self):
        cfg_path = self.settings.config_path
        if not cfg_path or not os.path.exists(cfg_path):
            QMessageBox.warning(self, APP_NAME, "Please set a valid CamillaDSP config file in Settings.")
            return
        cfg = load_yaml(cfg_path)
        if cfg is None:
            QMessageBox.critical(self, APP_NAME, "Failed to load YAML config.")
            return
        changed = False
        if ensure_filters_and_pipeline(cfg):
            changed = True
        if ensure_devices_section(cfg, self.settings.playback_device):
            changed = True
        if ensure_mixers_processors(cfg):
            changed = True
        for name, dial in self.knobs.items():
            val = int(dial.value())
            ok = write_gain(cfg, name, float(val))
            changed = changed or ok
        if changed:
            if not save_yaml(cfg_path, cfg):
                QMessageBox.critical(self, APP_NAME, "Failed to save YAML config.")
                return
        # trigger reload regardless; harmless if unchanged
        port = int(self.settings.port)
        try_reload_camilla(port)
