import json
from typing import Optional

import yaml
from websocket import create_connection


def load_camilla_dsp_yaml(path: str) -> Optional[dict]:
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def save_camilla_dsp_yaml(path: str, data: dict) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)
        return True
    except Exception:
        return False


# Default filters and pipeline templates
DEFAULT_FILTERS = {
    "Bass": {
        "description": None,
        "parameters": {"freq": 95, "gain": 3, "q": 1, "type": "Lowshelf"},
        "type": "Biquad",
    },
    "Middle": {
        "description": None,
        "parameters": {"freq": 750, "gain": 0, "q": 1, "type": "Peaking"},
        "type": "Biquad",
    },
    "Treble": {
        "description": None,
        "parameters": {"freq": 7500, "gain": 2, "q": 1, "type": "Highshelf"},
        "type": "Biquad",
    },
}


def make_pipeline_entry(name: str) -> dict:
    return {
        "bypassed": None,
        "channels": [0, 1],
        "description": None,
        "names": [name],
        "type": "Filter",
    }


def ensure_filters_and_pipelines(cfg: dict) -> bool:
    changed = False
    # Ensure filters exist
    if "filters" not in cfg or cfg["filters"] is None:
        cfg["filters"] = {}
        changed = True
    for name, defn in DEFAULT_FILTERS.items():
        if name not in cfg["filters"]:
            # Deep copy to avoid accidental mutation
            cfg["filters"][name] = yaml.safe_load(yaml.safe_dump(defn))
            changed = True
        else:
            # Ensure key structure exists; do not overwrite existing params
            f = cfg["filters"][name]
            if not isinstance(f, dict):
                cfg["filters"][name] = yaml.safe_load(yaml.safe_dump(defn))
                changed = True
            else:
                if "type" not in f:
                    f["type"] = "Biquad";
                    changed = True
                if "description" not in f:
                    f["description"] = None;
                    changed = True
                params = f.setdefault("parameters", {})
                # Ensure required parameter keys exist; keep existing gain
                for k, v in DEFAULT_FILTERS[name]["parameters"].items():
                    if k not in params:
                        params[k] = v;
                        changed = True
    # Ensure pipeline contains entries for each filter name (anywhere in list)
    pipeline = cfg.get("pipeline")
    if not isinstance(pipeline, list):
        cfg["pipeline"] = []
        pipeline = cfg["pipeline"]
        changed = True
    # Collect existing names referenced
    existing_names = set()
    for step in pipeline:
        try:
            if isinstance(step, dict) and step.get("type") == "Filter":
                names = step.get("names")
                if isinstance(names, list):
                    for n in names:
                        existing_names.add(n)
        except Exception:
            continue
    for name in ["Bass", "Middle", "Treble"]:
        if name not in existing_names:
            pipeline.append(make_pipeline_entry(name))
            changed = True
    return changed


def ensure_devices_section(cfg: dict, selected_device: str) -> bool:
    changed = False
    created_devices = False
    # Ensure devices dict exists
    dev = cfg.get('devices')
    if not isinstance(dev, dict):
        dev = {}
        cfg['devices'] = dev
        changed = True
        created_devices = True
    # Ensure chunksize
    if dev.get('chunksize') != 256:
        dev['chunksize'] = 256
        changed = True
    # Ensure target_level
    if dev.get('target_level') != 256:
        dev['target_level'] = 256
        changed = True
    # Ensure samplerate
    if dev.get('samplerate') != 44100:
        dev['samplerate'] = 44100
        changed = True
    # Ensure capture
    cap = dev.get('capture')
    if not isinstance(cap, dict):
        cap = {}
        dev['capture'] = cap
        changed = True
    if cap.get('channels') != 2:
        cap['channels'] = 2
        changed = True
    if cap.get('device') != 'BlackHole 2ch':
        cap['device'] = 'BlackHole 2ch'
        changed = True
    if cap.get('type') != 'CoreAudio':
        cap['type'] = 'CoreAudio'
        changed = True
    # Ensure playback
    pb = dev.get('playback')
    if not isinstance(pb, dict):
        pb = {}
        dev['playback'] = pb
        changed = True
    if pb.get('channels') != 2:
        pb['channels'] = 2
        changed = True
    # Set selected device if provided
    if selected_device and pb.get('device') != selected_device:
        pb['device'] = selected_device
        changed = True
    if pb.get('type') != 'CoreAudio':
        pb['type'] = 'CoreAudio'
        changed = True
    # If we created a new devices section, move it to be first key
    if created_devices:
        try:
            # Rebuild cfg with 'devices' first while preserving other keys order
            new_cfg = {'devices': dev}
            for k, v in list(cfg.items()):
                if k == 'devices':
                    continue
                new_cfg[k] = v
            cfg.clear()
            cfg.update(new_cfg)
        except Exception:
            pass
    return changed


def ensure_mixers_and_processors(cfg: dict) -> bool:
    """Ensure top-level mixers: {} and processors: {} exist and are placed at the end.

    Returns True if any changes were made (added/normalized/reordered).
    """
    changed = False
    if not isinstance(cfg, dict):
        return False
    # Normalize values
    mixers = cfg.get("mixers")
    if not isinstance(mixers, dict):
        cfg["mixers"] = {}
        changed = True
    processors = cfg.get("processors")
    if not isinstance(processors, dict):
        cfg["processors"] = {}
        changed = True
    # Reorder to ensure mixers and processors are the last keys
    try:
        items = list(cfg.items())
        items = [(k, v) for k, v in items if k not in ("mixers", "processors")]
        items.append(("mixers", cfg["mixers"]))
        items.append(("processors", cfg["processors"]))
        if list(cfg.items()) != items:
            cfg.clear()
            cfg.update(items)
            changed = True
    except Exception:
        pass
    return changed


def read_gain(cfg: dict, filter_name: str) -> Optional[float]:
    try:
        return cfg["filters"][filter_name]["parameters"]["gain"]
    except Exception as e:
        print(e)
        return None


def write_gain(cfg: dict, filter_name: str, gain: float) -> bool:
    try:
        if "filters" not in cfg or cfg["filters"] is None:
            cfg["filters"] = {}
        if filter_name not in cfg["filters"]:
            # Create full default if we have one; fallback to minimal structure
            if filter_name in DEFAULT_FILTERS:
                cfg["filters"][filter_name] = yaml.safe_load(yaml.safe_dump(DEFAULT_FILTERS[filter_name]))
            else:
                cfg["filters"][filter_name] = {
                    "type": "Biquad",
                    "description": None,
                    "parameters": {
                        # Provide safe starting values
                        "freq": 1000,
                        "q": 0.5,
                        "type": "Peaking",
                        "gain": 0,
                    },
                }
        params = cfg["filters"][filter_name].setdefault("parameters", {})
        if filter_name in DEFAULT_FILTERS:
            for k, v in DEFAULT_FILTERS[filter_name]["parameters"].items():
                params.setdefault(k, v)
        params["gain"] = gain
        return True
    except Exception:
        return False


# CamillaDSP reload
def try_reload_camilla_dsp(port: int):
    print("Reload camilla dsp...")
    if port <= 0 or port > 65535:
        print("Failed")
        return
    try:
        ws = create_connection(f"ws://localhost:{port}", timeout=1.5)
        try:
            ws.send(json.dumps("Reload"))
            try:
                resp = ws.recv()
                print("CamillaDSP configuration: " + resp)
                print("Succeeded")
            except Exception as e:
                print("Failed")
                print(e)
                pass
        finally:
            try:
                ws.close()
            except Exception as e:
                print("Websocket not closed!")
                print(e)
                pass
        return
    except Exception as ex:
        print("Failed")
        print(ex)
        return
