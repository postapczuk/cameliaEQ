import os
import sys
from dataclasses import dataclass, field

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QGridLayout,
    QFileDialog,
    QSpinBox,
)

from .camilla_dsp import load_camilla_dsp_yaml, save_camilla_dsp_yaml, ensure_devices_section, try_reload_camilla_dsp


def user_config_dir() -> str:
    """Return (and create if needed) the user configuration directory for the app.

    macOS: ~/Library/Application Support/CameliaEQ
    Linux: ~/.config/CameliaEQ
    """
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.path.expanduser("~/.config")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


APP_NAME = "CameliaEQ"
SETTINGS_PATH = os.path.join(user_config_dir(), "settings.yml")


@dataclass
class Settings:
    config_path: str = ""
    port: int = 1234
    playback_device: str = ""
    devices: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                settings = cls(**{k: data.get(k, v) for k, v in {"config_path": "", "port": 1234, "playback_device": "", "devices": {}}.items()})
                print(f"Settings loaded: \n{settings}")
                return settings
        except Exception as e:
            pass
            print("Settings load failure:", e)
        return cls()

    def save(self) -> None:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            settings = {"config_path": self.config_path, "port": self.port, "playback_device": self.playback_device, "devices": self.devices}
            yaml.safe_dump(settings, f, sort_keys=False)
            print(f"Settings saved")


class SettingsWindow(QWidget):
    def __init__(self, settings: Settings, on_save):
        super().__init__()
        self.settings = settings
        # Make settings a tool window and always on top
        self.setWindowFlags(self.windowFlags() | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(f"{APP_NAME} Settings")
        self.on_save = on_save
        layout = QFormLayout()

        self.path_edit = QLineEdit(self.settings.config_path)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self.browse)

        path_row = QWidget()
        path_row_layout = QGridLayout(path_row)
        path_row_layout.setContentsMargins(0, 0, 0, 0)
        path_row_layout.addWidget(self.path_edit, 0, 0)
        path_row_layout.addWidget(self.browse_btn, 0, 1)

        layout.addRow("CamillaDSP config file", path_row)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.settings.port)
        layout.addRow("CamillaDSP port", self.port_spin)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save)
        layout.addRow(self.save_btn)

        self.setLayout(layout)
        self.setFixedSize(self.sizeHint())

    def browse(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select CamillaDSP YAML config", "", "YAML Files (*.yaml *.yml)")
        if file:
            self.path_edit.setText(file)

    def save(self):
        self.settings.config_path = self.path_edit.text()
        self.settings.port = int(self.port_spin.value())
        self.settings.save()
        # If a config file is selected, ensure devices section exists/updated
        if self.settings.config_path:
            cfg = load_camilla_dsp_yaml(self.settings.config_path) or {}
            changed = ensure_devices_section(cfg, self.settings.playback_device)
            if changed:
                save_camilla_dsp_yaml(self.settings.config_path, cfg)
        self.on_save()
        try_reload_camilla_dsp(self.settings.port)
        self.close()
