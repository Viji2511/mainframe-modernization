import os
import json
from typing import Dict, Any

_validation_config: Dict[str, Any] = {}

def get_validation_config() -> Dict[str, Any]:
    global _validation_config
    if not _validation_config:
        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "validation_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                _validation_config = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load validation_config.json: {e}")
            _validation_config = {}
    return _validation_config
