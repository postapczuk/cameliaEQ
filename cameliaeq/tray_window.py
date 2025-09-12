import os

from PySide6 import QtCore
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
    QComboBox,
)

from .camilla_dsp import (
    load_camilla_dsp_yaml,
    save_camilla_dsp_yaml,
    ensure_filters_and_pipelines,
    ensure_devices_section,
    ensure_mixers_and_processors,
    read_gain,
    write_gain,
    DEFAULT_FILTERS,
    try_reload_camilla_dsp,
)
from .devices import list_system_playback_devices
from .settings import Settings, SettingsWindow, APP_NAME


class TrayWindow(QWidget):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

        self.setWindowTitle(APP_NAME)
        # Keep the small window always on top and as a tool window; fix size
        self.setWindowFlags(self.windowFlags() | Qt.Tool | Qt.WindowStaysOnTopHint)

        self.resize(320, 220)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.prepare_knobs_group())
        main_layout.addWidget(self.prepare_settings_group())

        self.setLayout(main_layout)
        self.setFixedSize(self.sizeHint())

        # Debounce timer for apply
        self.apply_timer = QTimer(self)
        self.apply_timer.setSingleShot(True)
        self.apply_timer.setInterval(400)  # ms
        self.apply_timer.timeout.connect(self.apply_knobs_to_camilla_dsp)

        print("Initial values loaded from camilla dsp config yaml")

    def prepare_knobs_group(self):
        # Knobs group
        knobs_group = QGroupBox()
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
                    print(f"Knob {name} changed value to {val}")
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
        return knobs_group

    def prepare_settings_group(self):
        settings_grid = QGridLayout()
        settings_group = QGroupBox()
        settings_group.setLayout(settings_grid)
        # Output device selection
        self.device_combo = QComboBox()
        self.fill_in_devices_into_combobox()

        settings_grid.addWidget(self.device_combo, 0, 0)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings)
        settings_grid.addWidget(settings_btn, 0, 1)
        self.load_initial_values_from_camilla_dsp_yaml()
        return settings_group

    def fill_in_devices_into_combobox(self):
        self.device_combo.currentTextChanged.disconnect(self.select_device)
        devices = list_system_playback_devices()
        self.device_combo.clear()
        if not devices:
            self.device_combo.addItem("(No devices found)")
            self.device_combo.setEnabled(False)
        else:
            print(f"Selected device: {self.settings.playback_device}")
            self.device_combo.addItems(devices)
            # Preselect saved setting if present
            selected_device = self.settings.playback_device
            if selected_device in devices:
                self.settings.playback_device = selected_device
                self.device_combo.setCurrentText(selected_device)
            else:
                self.device_combo.addItem(selected_device)
                self.device_combo.setCurrentText(selected_device)
                self.device_combo.setItemData(len(devices), 0, QtCore.Qt.ItemDataRole.UserRole - 1)
            self.device_combo.currentTextChanged.connect(self.select_device)

    def select_device(self):
        selected_device = self.device_combo.currentText()
        if selected_device in self.settings.devices:
            save_camilla_dsp_yaml(self.settings.config_path, self.settings.devices[selected_device])
        self.apply_changes_to_camilla_dsp()
        self.settings.playback_device = selected_device
        self.settings.save()
        self.load_initial_values_from_camilla_dsp_yaml()
        port = int(self.settings.port)
        try_reload_camilla_dsp(port)
        print(f"Device changed to {selected_device}")

    def open_settings(self):
        self.settings_win = SettingsWindow(self.settings, self.load_initial_values_from_camilla_dsp_yaml)
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

    def schedule_apply(self):
        self.apply_timer.start()

    def load_initial_values_from_camilla_dsp_yaml(self):
        camilla_dsp_cfg = load_camilla_dsp_yaml(self.settings.config_path)
        selected_device = self.settings.playback_device
        all_saved_devices = self.settings.devices

        if not camilla_dsp_cfg:
            return
        # Ensure required structures; save if changed
        changed = False
        if ensure_devices_section(camilla_dsp_cfg, selected_device):
            changed = True
            if selected_device in all_saved_devices:
                camilla_dsp_cfg = all_saved_devices[selected_device]
        if ensure_filters_and_pipelines(camilla_dsp_cfg):
            changed = True
        if ensure_mixers_and_processors(camilla_dsp_cfg):
            changed = True
        if changed and self.settings.config_path:
            save_camilla_dsp_yaml(self.settings.config_path, camilla_dsp_cfg)
        for name in ["Bass", "Middle", "Treble"]:
            gain = read_gain(camilla_dsp_cfg, name)
            if gain is None and name in DEFAULT_FILTERS:
                gain = DEFAULT_FILTERS[name]["parameters"]["gain"]
            if gain is not None and name in self.knobs:
                self.knobs[name].blockSignals(True)
                self.knobs[name].setValue(int(round(gain)))
                self.knobs[name].blockSignals(False)
                if name in self.value_labels:
                    self.value_labels[name].setText(f"{int(round(gain))} dB")

    def apply_knobs_to_camilla_dsp(self):
        cfg_path = self.settings.config_path

        if not cfg_path or not os.path.exists(cfg_path):
            QMessageBox.warning(self, APP_NAME, "Please set a valid CamillaDSP config file in Settings.")
            return
        camilla_dsp_cfg = load_camilla_dsp_yaml(cfg_path)
        if camilla_dsp_cfg is None:
            QMessageBox.critical(self, APP_NAME, "Failed to load YAML config.")
            return

        changed = False
        if ensure_filters_and_pipelines(camilla_dsp_cfg):
            changed = True
        if ensure_mixers_and_processors(camilla_dsp_cfg):
            changed = True
        for name, dial in self.knobs.items():
            val = int(dial.value())
            ok = write_gain(camilla_dsp_cfg, name, float(val))
            changed = changed or ok
        if changed:
            if not save_camilla_dsp_yaml(cfg_path, camilla_dsp_cfg):
                QMessageBox.critical(self, APP_NAME, "Failed to save YAML config.")
                return
            else:
                self.settings.devices[self.settings.playback_device] = camilla_dsp_cfg
                self.settings.save()
        port = int(self.settings.port)
        try_reload_camilla_dsp(port)


    def apply_changes_to_camilla_dsp(self):
        cfg_path = self.settings.config_path
        selected_device = self.settings.playback_device
        all_devices = self.settings.devices

        if not cfg_path or not os.path.exists(cfg_path):
            QMessageBox.warning(self, APP_NAME, "Please set a valid CamillaDSP config file in Settings.")
            return
        camilla_dsp_cfg = load_camilla_dsp_yaml(cfg_path)
        if camilla_dsp_cfg is None:
            QMessageBox.critical(self, APP_NAME, "Failed to load YAML config.")
            return

        changed = False
        if ensure_devices_section(camilla_dsp_cfg, selected_device):
            if selected_device in all_devices:
                camilla_dsp_cfg = all_devices[selected_device]
            changed = True
        for name, dial in self.knobs.items():
            val = int(dial.value())
            ok = write_gain(camilla_dsp_cfg, name, float(val))
            changed = changed or ok
        if changed:
            if not save_camilla_dsp_yaml(cfg_path, camilla_dsp_cfg):
                QMessageBox.critical(self, APP_NAME, "Failed to save YAML config.")
                return
            else:
                all_devices[selected_device] = camilla_dsp_cfg
                self.settings.save()
        # trigger reload regardless; harmless if unchanged
        port = int(self.settings.port)
        try_reload_camilla_dsp(port)
