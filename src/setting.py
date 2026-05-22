import json
import os
import logging
from PySide6.QtCore import QObject, Signal

CONFIG_FILE = "sakura-launcher_config.json"


class Setting(QObject):
    llamacpp_path = ""
    model_search_paths = ""
    model_sort_option = "修改時間"
    remember_window_state = False
    remember_advanced_state = False
    no_gpu_ability_check = False
    window_geometry = None
    advanced_state = False
    worker_url = ""
    presets = []
    no_context_check = False
    token = ""
    port_override = ""
    run_in_background = False
    use_proxy = True
    proxy_port = "8081"

    # 各個屬性的專用信號
    llamacpp_path_changed = Signal(str)
    model_search_paths_changed = Signal(str)
    model_sort_option_changed = Signal(str)
    remember_window_state_changed = Signal(bool)
    remember_advanced_state_changed = Signal(bool)
    no_gpu_ability_check_changed = Signal(bool)
    worker_url_changed = Signal(str)
    presets_changed = Signal(list)
    no_context_check_changed = Signal(bool)
    token_changed = Signal(str)
    port_override_changed = Signal(str)
    run_in_background_changed = Signal(bool)
    use_proxy_changed = Signal(bool)
    proxy_port_changed = Signal(str)

    # 通用的值變化信號
    value_changed = Signal(str, object)  # (key, value)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._load_settings()

        for sig in [
            self.llamacpp_path_changed,
            self.model_search_paths_changed,
            self.model_sort_option_changed,
            self.remember_window_state_changed,
            self.remember_advanced_state_changed,
            self.no_gpu_ability_check_changed,
            self.presets_changed,
            self.worker_url_changed,
            self.no_context_check_changed,
            self.token_changed,
            self.port_override_changed,
            self.run_in_background_changed,
            self.use_proxy_changed,
            self.proxy_port_changed,
        ]:
            sig.connect(lambda: self.save_settings())

    def set_value(self, name: str, value):
        """設定值並發出相應的信號"""
        self.__setattr__(name, value)
        # 發出專用信號
        if hasattr(self, name + "_changed"):
            getattr(self, name + "_changed").emit(value)
        # 發出通用信號
        self.value_changed.emit(name, value)

    def _read_settings(self):
        if not os.path.exists(CONFIG_FILE):
            return {}
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"讀取設定檔案時出錯: {str(e)}")
            return {}

    def _write_settings(self, settings):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"寫入設定檔案時出錯: {str(e)}")

    def save_settings(self):
        settings = {
            "llamacpp_path": self.llamacpp_path,
            "model_search_paths": self.model_search_paths,
            "model_sort_option": self.model_sort_option,
            "remember_window_state": self.remember_window_state,
            "remember_advanced_state": self.remember_advanced_state,
            "no_gpu_ability_check": self.no_gpu_ability_check,
            "window_geometry": self.window_geometry,
            "advanced_state": self.advanced_state,
            "worker_url": self.worker_url,
            "運行": self.presets,
            "no_context_check": self.no_context_check,
            "token": self.token,
            "port_override": self.port_override,
            "run_in_background": self.run_in_background,
            "use_proxy": self.use_proxy,
            "proxy_port": self.proxy_port,
        }
        current_settings = self._read_settings()
        current_settings.update(settings)
        self._write_settings(current_settings)

    def _load_settings(self):
        settings = self._read_settings()
        self.llamacpp_path = settings.get("llamacpp_path", "")
        self.model_search_paths = settings.get("model_search_paths", "")
        self.model_sort_option = settings.get("model_sort_option", "修改時間")
        if self.model_sort_option == "修改时间":
            self.model_sort_option = "修改時間"
            
        self.remember_window_state = settings.get("remember_window_state", False)
        self.remember_advanced_state = settings.get("remember_advanced_state", False)
        self.no_gpu_ability_check = settings.get("no_gpu_ability_check", False)
        self.window_geometry = settings.get("window_geometry", None)
        self.advanced_state = settings.get("advanced_state", False)
        
        # 兼容簡繁體鍵名
        self.presets = settings.get("運行", settings.get("运行", []))
        
        self.worker_url = settings.get("worker_url", "https://sakura-share.one")
        self.no_context_check = settings.get("no_context_check", False)
        self.token = settings.get("token", "")
        self.port_override = settings.get("port_override", "")
        self.run_in_background = settings.get("run_in_background", False)
        self.use_proxy = settings.get("use_proxy", True)
        self.proxy_port = settings.get("proxy_port", "8081")

        # 相容 v1.0.0-beta
        if type(self.model_search_paths) == list:
            self.model_search_paths = "\n".join(self.model_search_paths)


SETTING = Setting()
