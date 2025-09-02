import sys

from PySide6.QtMultimedia import QMediaDevices

# System devices helper
def list_system_playback_devices() -> list:
    devices: list[str] = []
    try:
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
