# -*- coding: utf-8 -*-
"""설정 파일 관리 모듈 — config.json에서 API 키 등 설정을 불러오고 저장"""
import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")


def load_config():
    """config.json을 불러옴 (없으면 기본값 생성)"""
    default = {
        "api_keys": {
            "fss_stock": "",
            "fss_product": "",
            "fss_index": "",
            "fss_company": ""
        },
        "theme": "darkly"
    }
    if not os.path.exists(CONFIG_FILE):
        save_config(default)
        return default
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 키 누락 시 기본값 보완
        for k, v in default.items():
            if k not in data:
                data[k] = v
        return data
    except (json.JSONDecodeError, IOError):
        return default


def save_config(data):
    """config.json 저장"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_api_key(key_name):
    """특정 API 키 반환"""
    cfg = load_config()
    return cfg.get("api_keys", {}).get(key_name, "")


def set_api_key(key_name, value):
    """특정 API 키 저장"""
    cfg = load_config()
    if "api_keys" not in cfg:
        cfg["api_keys"] = {}
    cfg["api_keys"][key_name] = value
    save_config(cfg)


def get_all_api_keys():
    """모든 API 키 딕셔너리 반환"""
    cfg = load_config()
    return cfg.get("api_keys", {})


def get_theme():
    """저장된 테마 반환"""
    cfg = load_config()
    return cfg.get("theme", "darkly")


def set_theme(theme_name):
    """테마 저장"""
    cfg = load_config()
    cfg["theme"] = theme_name
    save_config(cfg)
