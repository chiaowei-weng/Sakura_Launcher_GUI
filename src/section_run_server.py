import logging
import os
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import (
    ComboBox,
    PushButton,
    SpinBox,
    PrimaryPushButton,
    TextEdit,
    EditableComboBox,
    MessageBox,
    FluentIcon as FIF,
    Slider,
)

from .common import CURRENT_DIR
from .gpu import GPUManager, GPUDisplayHelper
from .sakura import SAKURA_LIST, SakuraCalculator
from .setting import SETTING
from .ui import *


class RunServerSection(QFrame):
    def __init__(self, title, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setObjectName(title)

        self._init_ui()
        self.refresh_models()
        self.refresh_gpus()
        self.load_presets(SETTING.presets)

        SETTING.model_sort_option_changed.connect(self.refresh_models)

    def _init_ui(self):
        menu_base = self._create_menu_base()
        menu_advance = self._create_advance_menu()

        layout = QVBoxLayout()
        layout.addLayout(menu_base)
        layout.addWidget(menu_advance)
        layout.insertStretch(-1)
        self.setLayout(layout)

        self.context_length_input.valueChanged.connect(self.update_slider_from_input)
        self.context_length.valueChanged.connect(self.update_context_per_thread)
        self.n_parallel_spinbox.valueChanged.connect(self.update_context_per_thread)
        self.update_context_per_thread()

    def _create_menu_base(self):
        self.benchmark_button = PushButton(FIF.UNIT, "效能測試")
        self.run_and_share_button = PushButton(FIF.IOT, "啟動/共享")
        self.run_button = PrimaryPushButton(FIF.PLAY, "啟動")

        buttons_group = UiButtonGroup(
            UiButton("進階設定", FIF.MORE, self.toggle_advanced_settings),
            self.benchmark_button,
            self.run_and_share_button,
            self.run_button,
        )

        self.context_per_thread_label = QLabel()

        return UiCol(
            buttons_group,
            UiOptionRow("模型", self._create_model_selection_layout()),
            UiOptionRow("顯示卡", self._create_gpu_selection_layout()),
            UiOptionRow(
                "上下文長度 -c",
                self._create_context_length_layout(),
                label_width=74,
            ),
            UiOptionRow(
                "並發數量 -np",
                UiSlider(self, "n_parallel", 1, 1, 32, 1, spinbox_fixed_width=140),
                label_width=74,
            ),
            self.context_per_thread_label,
        )

    def _create_preset_options(self):
        self.config_preset_combo = EditableComboBox()
        self.config_preset_combo.currentIndexChanged.connect(self.load_selected_preset)
        SETTING.presets_changed.connect(self.load_presets)

        return UiRow(
            (self.config_preset_combo, 1),
            (UiButton("儲存", FIF.SAVE, self.save_preset), 0),
        )

    def _create_ip_port_log_option(self):
        self.host_input = UiLineEdit("", "127.0.0.1")
        self.port_input = UiLineEdit("", "8080")
        self.gpu_layers_spinbox = SpinBox()
        self.gpu_layers_spinbox.setRange(0, 200)
        self.gpu_layers_spinbox.setValue(200)
        return UiRow(
            UiOptionCol("主機地址 --host", self.host_input),
            UiOptionCol("埠口 --port", self.port_input),
            UiOptionCol("GPU層數 -ngl", self.gpu_layers_spinbox),
        )

    def _create_benchmark_layout(self):
        self.npp_input = UiLineEdit("Prompt數量", "768")
        self.ntg_input = UiLineEdit("生成文本數量", "384")
        self.npl_input = UiLineEdit("並行Prompt數量", "1,2,4,8,16")
        return UiRow(
            UiOptionCol("Prompt數量 -npp", self.npp_input),
            UiOptionCol("生成文本數量 -ntg", self.ntg_input),
            UiOptionCol("並行Prompt數量 -npl", self.npl_input),
        )

    def _create_advance_menu(self):
        self.flash_attention_check = UiCheckBox("啟用 Flash Attention -fa", True)
        self.no_mmap_check = UiCheckBox("啟用 --no-mmap", True)
        self.background_check = UiCheckBox("背景執行", SETTING.run_in_background)
        self.background_check.stateChanged.connect(
            lambda: SETTING.set_value("run_in_background", self.background_check.isChecked())
        )

        layout_extra_options = UiRow(
            self.flash_attention_check,
            self.no_mmap_check,
            self.background_check,
            None,
        )
        layout_extra_options.setContentsMargins(0, 0, 0, 0)  # 設定內部邊距

        self.llamacpp_override = UiLineEdit("覆蓋預設 llamacpp 路徑（可選）", "")

        self.proxy_port_input = UiLineEdit("繁體代理埠口 (預設 8081)", SETTING.proxy_port)
        self.proxy_port_input.textChanged.connect(
            lambda text: SETTING.set_value("proxy_port", text.strip())
        )

        self.command_template = TextEdit()
        self.command_template.setAcceptRichText(False)
        self.command_template.setPlaceholderText(
            "\n".join(
                [
                    "自定義命令模板，其中",
                    "- %cmd%會替換成 UI 生成的完整命令",
                    "- %cmd_raw%會被替換成 UI 生成的命令和模型選項，但不包括其他選項",
                ]
            )
        )

        layout = UiCol(
            UiHLine(),
            layout_extra_options,
            UiOptionRow("配置預設選擇", self._create_preset_options()),
            self._create_ip_port_log_option(),
            self._create_benchmark_layout(),
            self.llamacpp_override,
            self.command_template,
        )
        layout.setContentsMargins(0, 0, 0, 0)  # 確保布局的邊距也被移除
        self.menu_advance = QFrame(self)
        self.menu_advance.setLayout(layout)
        if SETTING.remember_advanced_state:
            self.menu_advance.setVisible(SETTING.advanced_state)
        else:
            self.menu_advance.setVisible(False)
        return self.menu_advance

    def _create_context_length_layout(self):
        layout = QHBoxLayout()
        self.context_length = Slider(Qt.Horizontal, self)
        self.context_length.setRange(0, 10000)
        self.context_length.setPageStep(5)
        self.context_length.setValue(5000)

        self.context_length_input = SpinBox(self)
        self.context_length_input.setRange(256, 131072)
        self.context_length_input.setSingleStep(256)
        self.context_length_input.setValue(2048)
        self.context_length_input.setFixedWidth(140)

        layout.addWidget(self.context_length)
        layout.addWidget(self.context_length_input)

        self.context_length.valueChanged.connect(self.update_context_from_slider)
        self.context_length_input.valueChanged.connect(self.update_slider_from_input)

        return layout

    def _create_model_selection_layout(self):
        layout = QHBoxLayout()
        self.model_path = EditableComboBox(self)
        self.model_path.setPlaceholderText("請選擇模型路徑")
        self.refresh_model_button = PushButton(FIF.SYNC, "重新整理")
        self.refresh_model_button.clicked.connect(self.refresh_models)
        self.refresh_model_button.setFixedWidth(140)
        layout.addWidget(self.model_path)
        layout.addWidget(self.refresh_model_button)
        return layout

    def refresh_models(self):
        self.model_path.clear()
        models = []
        paths = SETTING.model_search_paths.split("\n")
        search_paths = [CURRENT_DIR] + [path.strip() for path in paths if path.strip()]
        logging.debug(f"搜尋路徑: {search_paths}")
        for path in search_paths:
            logging.debug(f"正在搜尋路徑: {path}")
            if os.path.exists(path):
                logging.debug(f"路徑存在: {path}")
                if os.path.isdir(path):
                    logging.debug(f"路徑為目錄: {path}")
                    for root, dirs, files in os.walk(path):
                        logging.debug(f"正在搜尋子目錄: {root}")
                        logging.debug(f"檔案清單: {files}")
                        for f in files:
                            if f.endswith(".gguf"):
                                full_path = os.path.join(root, f)
                                logging.debug(f"找到模型檔案: {full_path}")
                                models.append(full_path)
                else:
                    logging.debug(f"路徑不是目錄: {path}")
            else:
                logging.debug(f"路徑不存在: {path}")

        logging.debug(f"找到的模型檔案: {models}")

        # 從設定中獲取排序選項
        sort_option = SETTING.model_sort_option

        # 根據選擇的排序方式對模型清單進行排序
        if sort_option == "修改時間":
            models.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        elif sort_option == "檔案名稱":
            models.sort(key=lambda x: os.path.basename(x).lower())
        elif sort_option == "檔案大小":
            models.sort(key=lambda x: os.path.getsize(x), reverse=True)

        models_shortest = []
        for abspath in models:
            # 檢查文件是否在當前目錄下（不在子目錄中）
            if os.path.dirname(abspath) == CURRENT_DIR:
                # 如果在當前目錄，使用文件名作為相對路徑
                models_shortest.append(os.path.basename(abspath))
            else:
                # 計算相對路徑和絕對路徑
                abs_path = os.path.abspath(abspath)
                # 只有在同一個盤符時才計算相對路徑
                if os.path.splitdrive(abspath)[0] == os.path.splitdrive(CURRENT_DIR)[0]:
                    rel_path = os.path.relpath(abspath, CURRENT_DIR)
                    # 選擇更短的路徑
                    models_shortest.append(
                        rel_path if len(rel_path) < len(abs_path) else abs_path
                    )
                else:
                    # 不同盤符時使用絕對路徑
                    models_shortest.append(abs_path)

        self.model_path.addItems(models_shortest)

    def _create_gpu_selection_layout(self):
        self.gpu_combo = ComboBox(self)
        button = UiButton("自動配置", FIF.SETTING, self.auto_configure)
        button.setFixedWidth(140)
        return UiRow(self.gpu_combo, button)

    def refresh_gpus(self, keep_selected=False):
        # 儲存當前選擇的GPU
        current_gpu = self.gpu_combo.currentText() if keep_selected else None

        self.gpu_combo.clear()
        self.nvidia_gpus = self.main_window.gpu_manager.nvidia_gpus
        self.amd_gpus = self.main_window.gpu_manager.amd_gpus

        # 優先添加NVIDIA GPU
        if self.nvidia_gpus:
            self.gpu_combo.addItems(self.nvidia_gpus)

        # 如果有AMD GPU，添加到清單末尾
        if self.amd_gpus:
            self.gpu_combo.addItems(self.amd_gpus)

        if not self.nvidia_gpus and not self.amd_gpus:
            logging.warning("未檢測到NVIDIA或AMD GPU")

        self.gpu_combo.addItems(["自動"])

        # 如果需要保持選擇，嘗試恢復之前的選擇
        if keep_selected and current_gpu:
            index = self.gpu_combo.findText(current_gpu)
            if index >= 0:
                self.gpu_combo.setCurrentIndex(index)
            else:
                self.gpu_combo.setCurrentText("自動")

    def context_to_slider(self, context):
        min_value = math.log(256)
        max_value = math.log(131072)
        return int(10000 * (math.log(context) - min_value) / (max_value - min_value))

    def slider_to_context(self, value):
        min_value = math.log(256)
        max_value = math.log(131072)
        return int(math.exp(min_value + (value / 10000) * (max_value - min_value)))

    def update_context_from_slider(self, value):
        context_length = self.slider_to_context(value)
        context_length = max(256, min(131072, context_length))
        context_length = round(context_length / 256) * 256
        self.context_length_input.blockSignals(True)
        self.context_length_input.setValue(context_length)
        self.context_length_input.blockSignals(False)
        self.update_context_per_thread()

    def update_slider_from_input(self, value):

        value = round(value / 256) * 256
        slider_value = self.context_to_slider(value)
        slider_value = max(0, min(10000, slider_value))
        self.context_length.setValue(slider_value)
        self.context_length.update()
        self.update_context_per_thread()

    def update_context_per_thread(self):
        total_context = self.context_length_input.value()
        n_parallel = self.n_parallel_spinbox.value()
        context_per_thread = total_context // n_parallel
        self.context_per_thread_label.setText(
            f"每個工作線程的上下文大小: {context_per_thread}"
        )

    def auto_configure(self):
        current_model = self.model_path.currentText()
        if not current_model:
            UiInfoBarWarning(self, "請先選擇一個模型")
            return

        model_name = current_model.split(os.sep)[-1]
        sakura_model = SAKURA_LIST[model_name]
        if not sakura_model:
            UiInfoBarWarning(self, "無法找到選中模型的配置資訊")
            return

        # 重新整理並獲取GPU資訊
        gpu_manager: GPUManager = self.main_window.gpu_manager
        gpu_manager.detect_gpus()
        selected_gpu_display = self.gpu_combo.currentText()

        # 從顯示名稱中找到對應的GPU key
        gpu_key = GPUDisplayHelper.find_gpu_key(selected_gpu_display, gpu_manager.gpu_info_map)
        if not gpu_key:
            UiInfoBarWarning(self, "請先選擇一個GPU")
            return

        # 檢查GPU能力
        gpu_info = gpu_manager.gpu_info_map[gpu_key]
        ability = gpu_manager.check_gpu_ability(selected_gpu_display, model_name)
        if not ability.is_capable:
            UiInfoBarWarning(self, ability.reason)
            return

        available_memory_gib = gpu_info.avail_dedicated_gpu_memory / (2**30)
        total_memory_gib = gpu_info.dedicated_gpu_memory / (2**30)

        try:
            # 創建計算器實例
            calculator = SakuraCalculator(sakura_model)

            # 如果不能獲取顯存佔用，則使用最大顯存-2GiB
            if available_memory_gib is None:
                available_memory_gib = total_memory_gib - 2

            # 獲取推薦配置
            config = calculator.recommend_config(available_memory_gib)

            # 應用配置
            self.n_parallel_spinbox.setValue(config["n_parallel"])
            self.context_length_input.setValue(config["context_length"])

            # 計算實際顯存使用
            memory_usage = calculator.calculate_memory_requirements(
                config["context_length"]
            )

            UiInfoBarSuccess(
                self,
                f"已自動配置: context={config['context_length']}, "
                f"np={config['n_parallel']}, \n"
                f"當前顯存佔用: {total_memory_gib - available_memory_gib:.2f} GiB, \n"
                f"預計模型顯存佔用: {memory_usage['total_size_gib']:.2f} GiB（可能偏大）。 ",
            )

        except ValueError as e:
            UiInfoBarWarning(self, str(e))

    def save_preset(self):
        preset_name = self.config_preset_combo.currentText()
        if not preset_name:
            MessageBox("錯誤", "預設名稱不能為空", self).exec()
            return

        selected_gpu = self.gpu_combo.currentText()
        # 如果是帶有PCI ID的顯示名稱，儲存完整的顯示名稱
        SETTING.set_preset(
            preset_name,
            {
                "custom_command": self.command_template.toPlainText(),
                "gpu_layers": self.gpu_layers_spinbox.value(),
                "flash_attention": self.flash_attention_check.isChecked(),
                "no_mmap": self.no_mmap_check.isChecked(),
                "run_in_background": self.background_check.isChecked(),
                "use_proxy": True,
                "proxy_port": self.proxy_port_input.text(),
                "gpu": selected_gpu,  # 儲存完整的GPU顯示名稱
                "model_path": self.model_path.currentText(),
                "context_length": self.context_length_input.value(),
                "n_parallel": self.n_parallel_spinbox.value(),
                "host": self.host_input.text(),
                "port": self.port_input.text(),
                "npp": self.npp_input.text(),
                "ntg": self.ntg_input.text(),
                "npl": self.npl_input.text(),
                "llamacpp_override": self.llamacpp_override.text(),
            },
        )
        UiInfoBarSuccess(self, "預設已儲存")

    def load_presets(self, presets):
        current_preset_name = self.config_preset_combo.currentText()

        self.config_preset_combo.clear()
        preset_names = [preset["name"] for preset in presets]
        self.config_preset_combo.addItems(preset_names)

        if current_preset_name not in preset_names:
            self.config_preset_combo.setCurrentText("")
        else:
            self.config_preset_combo.setCurrentText(current_preset_name)

    def load_selected_preset(self):
        preset_name = self.config_preset_combo.currentText()
        for preset in SETTING.presets:
            if preset["name"] == preset_name:
                config = preset["config"]

                self.command_template.setPlainText(config.get("command_template", ""))
                if self.command_template == "":
                    cmd1 = config.get("custom_command", "")
                    cmd2 = config.get("custom_command_append", "")
                    if cmd1 != "":
                        self.command_template = "%cmd_raw% " + cmd1
                    elif cmd2 != "":
                        self.command_template = "%cmd% " + cmd2

                self.gpu_layers_spinbox.setValue(config.get("gpu_layers", 200))
                self.model_path.setCurrentText(config.get("model_path", ""))
                self.context_length_input.setValue(config.get("context_length", 2048))
                self.n_parallel_spinbox.setValue(config.get("n_parallel", 1))
                self.host_input.setText(config.get("host", "127.0.0.1"))
                self.port_input.setText(config.get("port", "8080"))
                self.flash_attention_check.setChecked(
                    config.get("flash_attention", True)
                )
                self.npp_input.setText(config.get("npp", "768"))
                self.ntg_input.setText(config.get("ntg", "384"))
                self.npl_input.setText(config.get("npl", "1,2,4,8,16"))
                self.no_mmap_check.setChecked(config.get("no_mmap", True))
                self.proxy_port_input.setText(config.get("proxy_port", SETTING.proxy_port))

                # 加載GPU選擇，支援新舊格式
                gpu_setting = config.get("gpu", "")
                if gpu_setting:
                    index = self.gpu_combo.findText(gpu_setting)
                    if index >= 0:
                        self.gpu_combo.setCurrentIndex(index)
                    else:
                        # 如果找不到完整的顯示名稱，嘗試在當前GPU清單中查找匹配的名稱部分
                        from src.gpu import GPUDisplayHelper
                        for i in range(self.gpu_combo.count()):
                            current_text = self.gpu_combo.itemText(i)
                            if GPUDisplayHelper.match_gpu_name(current_text, gpu_setting):
                                self.gpu_combo.setCurrentIndex(i)
                                break

                self.llamacpp_override.setText(config.get("llamacpp_override", ""))
                self.update_context_per_thread()
                break

    def toggle_advanced_settings(self):
        new_state = not self.menu_advance.isVisible()
        self.menu_advance.setVisible(new_state)
        if SETTING.remember_advanced_state:
            SETTING.advanced_state = new_state
            SETTING.save_settings()
