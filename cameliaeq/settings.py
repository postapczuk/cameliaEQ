import json
import os
import sys
from dataclasses import dataclass

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
    QComboBox,
)

from .core import load_yaml, save_yaml, ensure_devices_section, try_reload_camilla
from .commons import APP_NAME, user_config_dir

SETTINGS_PATH = os.path.join(user_config_dir(), "settings.yml")


@dataclass
class Settings:
    config_path: str = ""
    port: int = 1234
    playback_device: str = ""

    @classmethod
    def load(cls) -> "Settings":
        # Prefer YAML settings; migrate from legacy JSON if present
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return cls(**{k: data.get(k, v) for k, v in {"config_path": "", "port": 1234, "playback_device": ""}.items()})
        except Exception:
            pass
        # Legacy migration: config.json
        legacy_json = os.path.join(user_config_dir(), "config.json")
        try:
            if os.path.exists(legacy_json):
                with open(legacy_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                inst = cls(**data)
                # Save immediately to new YAML path
                inst.save()
                return inst
        except Exception:
            pass
        return cls()

    def save(self) -> None:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump({"config_path": self.config_path, "port": self.port, "playback_device": self.playback_device}, f, sort_keys=False)


# System devices helper

def list_system_playback_devices() -> list:
    devices: list[str] = []
    # Try QtMultimedia if available (PySide6 add-on)
    try:
        from PySide6.QtMultimedia import QMediaDevices
        try:
            devs = QMediaDevices.audioOutputs()
            for d in devs:
                name = getattr(d, 'description', None)
                if callable(name):
                    name = d.description()
                if not name:
                    name = getattr(d, 'deviceName', lambda: None)()
                if name and name not in devices:
                    devices.append(str(name))
        except Exception:
            pass
    except Exception:
        pass
    # macOS: try CoreAudio via system command 'SwitchAudioSource' if present
    if sys.platform == 'darwin' and not devices:
        try:
            import subprocess
            out = subprocess.check_output(['SwitchAudioSource', '-a'], text=True, timeout=2)
            for line in out.splitlines():
                line = line.strip()
                if line:
                    # Lines look like: 'Built-in Output (output)'
                    name = line.split(' (')[0].strip()
                    if name and name not in devices:
                        devices.append(name)
        except Exception:
            pass
    # Linux: try aplay -l parsing
    if sys.platform.startswith('linux') and not devices:
        try:
            import subprocess
            out = subprocess.check_output(['aplay', '-l'], text=True, timeout=2, stderr=subprocess.STDOUT)
            for line in out.splitlines():
                line = line.strip()
                if line.startswith('card') and ':' in line:
                    # Example: card 0: PCH [HDA Intel PCH], device 0: ALC... 
                    name_part = line.split(':', 1)[1].strip()
                    name = name_part.split(',', 1)[0].strip()
                    if name and name not in devices:
                        devices.append(name)
        except Exception:
            pass
    # Filter out devices with 'BlackHole' prefix
    devices = [d for d in devices if not str(d).startswith('BlackHole')]
    return devices


class SettingsWindow(QWidget):
    def __init__(self, settings: Settings, on_save):
        super().__init__()
        # Make settings a tool window and always on top
        self.setWindowFlags(self.windowFlags() | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(f"{APP_NAME} Settings")
        self.settings = settings
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

        # Output device selection
        self.device_combo = QComboBox()
        devices = list_system_playback_devices()
        if not devices:
            self.device_combo.addItem("(No devices found)")
            self.device_combo.setEnabled(False)
        else:
            self.device_combo.addItems(devices)
            # Preselect saved setting if present
            if self.settings.playback_device and self.settings.playback_device in devices:
                self.device_combo.setCurrentText(self.settings.playback_device)
        layout.addRow("Output device", self.device_combo)

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
        if hasattr(self, 'device_combo') and self.device_combo.isEnabled():
            self.settings.playback_device = self.device_combo.currentText()
        self.settings.save()
        # If a config file is selected, ensure devices section exists/updated
        if self.settings.config_path:
            cfg = load_yaml(self.settings.config_path) or {}
            changed = ensure_devices_section(cfg, self.settings.playback_device)
            if changed:
                save_yaml(self.settings.config_path, cfg)
        self.on_save(self.settings)
        print("Settings saved")
        try_reload_camilla(self.settings.port)
        self.close()
