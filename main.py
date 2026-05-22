import logging
import sys
import os
import subprocess
import shutil
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QAbstractScrollArea
from PySide6.QtGui import QIcon, QColor, QFont
from qfluentwidgets import (
    MessageBox,
    setTheme,
    Theme,
    MSFluentWindow,
    FluentIcon as FIF,
    setThemeColor,
    NavigationItemPosition,
)

from src.common import *
from src.llamacpp import get_llamacpp_version
from src.gpu import GPUManager
from src.section_run_server import RunServerSection
from src.section_download import DownloadSection
from src.section_share import CFShareSection
from src.section_about import AboutSection
from src.section_settings import SettingsSection
from src.setting import *
from src.ui import *
from src.utils.launcher import build_llamacpp_command

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())

# 设置CUDA设备顺序，保证nvidia-smi的输出顺序和llama.cpp的输出顺序一致
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"


class MainWindow(MSFluentWindow):
    def __init__(self):
        super().__init__()
        self.gpu_manager = GPUManager()
        self.init_navigation()
        self.init_window()
        self.setMinimumSize(600, 700)
        self.load_window_state()

        # 黑魔法，强行覆盖函数以关闭标签页切换动画
        def setCurrentWidget(widget, _=True):
            if isinstance(widget, QAbstractScrollArea):
                widget.verticalScrollBar().setValue(0)
            self.stackedWidget.view.setCurrentWidget(widget, duration=0)

        self.stackedWidget.setCurrentWidget = (
            lambda widget, popOut=True: setCurrentWidget(widget, popOut)
        )

    def init_navigation(self):
        self.run_server_section = RunServerSection("啟動", self)
        self.dowload_section = DownloadSection("下載")
        self.cf_share_section = CFShareSection("共享", self)
        self.settings_section = SettingsSection("設定")
        self.about_section = AboutSection("關於")

        self.addSubInterface(self.run_server_section, FIF.COMMAND_PROMPT, "啟動")
        self.addSubInterface(self.dowload_section, FIF.DOWNLOAD, "下載")
        self.addSubInterface(self.cf_share_section, FIF.IOT, "共享")
        self.addSubInterface(self.settings_section, FIF.SETTING, "設定")
        self.addSubInterface(
            self.about_section,
            FIF.INFO,
            "關於",
            position=NavigationItemPosition.BOTTOM,
        )

        self.navigationInterface.setCurrentItem("啟動")

    def init_window(self):
        self.run_server_section.run_button.clicked.connect(self.run_llamacpp_server)
        self.run_server_section.run_and_share_button.clicked.connect(
            self.run_llamacpp_server_and_share
        )
        self.run_server_section.benchmark_button.clicked.connect(
            self.run_llamacpp_batch_bench
        )

        self.settings_section.sig_need_update.connect(
            self.dowload_section.start_download_launcher
        )

        self.setStyleSheet(
            """
            QLabel {
                color: #dadada;
            }

            CheckBox {
                color: #dadada;
            }

            AcrylicWindow{
                background-color: #272727;
            }
        """
        )

        icon = get_resource_path(ICON_FILE)
        self.setWindowIcon(QIcon(icon))
        self.setWindowTitle(f"Sakura 啟動器 {SAKURA_LAUNCHER_GUI_VERSION}")

        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

    def get_llamacpp_path(self):
        path = SETTING.llamacpp_path
        if not path:
            return os.path.join(CURRENT_DIR, "llama")
        return os.path.abspath(path)

    def run_llamacpp_server(self):
        self.refresh_gpus()
        self.start_proxy()
        self._run_llamacpp("llama-server")

    def run_llamacpp_server_and_share(self):
        self.start_proxy()
        self._run_llamacpp("llama-server")
        cf_share_url = self.cf_share_section.worker_url_input.text()
        if not cf_share_url:
            MessageBox("錯誤", "分享連結不能為空", self).exec()
            return
        QTimer.singleShot(18000, self.cf_share_section.start_cf_share)

    def run_llamacpp_batch_bench(self):
        self._run_llamacpp("llama-batched-bench")

    def check_gpu_ability(self, selected_gpu_display, model_name, context_length, n_parallel):
        """檢查GPU能力"""
        try:
            check_result = self.gpu_manager.check_gpu_ability(
                selected_gpu_display,
                model_name,
                context_length,
                n_parallel,
            )
            if not check_result.is_capable and not SETTING.no_gpu_ability_check:
                if check_result.is_fatal:
                    MessageBox(
                        "致命錯誤：GPU 不滿足強制需求",
                        f"顯示卡 {selected_gpu_display} 無法執行 {model_name}。\n\n"
                        f"原因：{check_result.reason}\n\n"
                        f"註：GPU能力檢測對話框可以在設定中關閉",
                        self,
                    ).exec()
                    return False
                else:
                    box = MessageBox(
                        "警告：GPU 不滿足執行最低需求",
                        f"顯示卡 {selected_gpu_display} 無法執行 {model_name}。\n\n"
                        f"原因：{check_result.reason}\n\n"
                        f"你可以繼續使用，但是執行可能發生異常\n\n"
                        f"註：GPU能力檢測對話框可以在設定中關閉",
                        self,
                    )
                    is_quit = False

                    def on_yes():
                        nonlocal is_quit
                        is_quit = False

                    def on_cancel():
                        nonlocal is_quit
                        is_quit = True

                    box.yesSignal.connect(on_yes)
                    box.cancelSignal.connect(on_cancel)
                    box.yesButton.setText("無視風險繼續！")
                    box.cancelButton.setText("停止")
                    box.exec()
                    return not is_quit
        except Exception as e:
            logging.info(f"檢查GPU能力時出錯: {str(e)}")
            MessageBox("錯誤", f"檢查GPU能力時出錯: {str(e)}", self).exec()
            return False
        return True

    def check_context_per_thread(self, context_length, n_parallel):
        """檢查每執行緒上下文長度"""
        context_per_thread = context_length // n_parallel
        if context_per_thread < 1024 and not SETTING.no_context_check:
            box = MessageBox(
                "警告：每執行緒上下文長度過小",
                f"當前每個執行緒的上下文長度為 {context_per_thread}，\n"
                f"小於推薦的最小值 1024。\n\n"
                f"這可能會導致模型無法正常使用。建議：\n"
                f"1. 增加總上下文長度\n"
                f"2. 減少並發數量\n"
                f"3. 點擊「自動配置」按鈕進行自動優化，然後繼續\n（僅支援「下載」頁面中的模型）\n\n"
                f"註：此警告可以在設定中關閉",
                self,
            )
            is_quit = False

            def on_yes():
                nonlocal is_quit
                is_quit = False

            def on_cancel():
                nonlocal is_quit
                is_quit = True

            def on_auto_config():
                nonlocal is_quit
                is_quit = True
                # 調用 RunServerSection 的自動配置功能
                self.run_server_section.auto_configure()

            box.yesSignal.connect(on_yes)
            box.cancelSignal.connect(on_cancel)

            # 建立自動配置按鈕並添加到buttonGroup
            from qfluentwidgets import PushButton

            auto_config_button = PushButton("自動配置", box)
            auto_config_button.clicked.connect(on_auto_config)
            box.buttonGroup.layout().insertWidget(
                1, auto_config_button
            )  # 插入到yes和cancel按鈕之間

            box.yesButton.setText("繼續")
            box.cancelButton.setText("停止")
            box.exec()
            return not is_quit
        return True

    def check_launch_requirements(
        self, selected_gpu_display, model_name, context_length, n_parallel
    ):
        """檢查啟動要求"""
        # 檢查GPU能力
        if not self.check_gpu_ability(
            selected_gpu_display,
            model_name,
            context_length,
            n_parallel
        ):
            return False

        # 檢查每執行緒上下文長度
        if not self.check_context_per_thread(context_length, n_parallel):
            return False

        return True

    def _run_llamacpp(self, executable):
        section = self.run_server_section

        llamacpp_override = section.llamacpp_override.text().strip()
        llamacpp_path = (
            llamacpp_override if llamacpp_override else self.get_llamacpp_path()
        )
        exe_extension = ".exe" if sys.platform == "win32" else ""

        if not os.path.exists(llamacpp_path):
            MessageBox("錯誤", f"llamacpp路徑不存在: {llamacpp_path}", self).exec()
            return

        model_name = section.model_path.currentText().split(os.sep)[-1]
        model_path = section.model_path.currentText()
        logging.info(f"模型路徑: {model_path}")
        logging.info(f"模型名稱: {model_name}")

        # 將GPU檢查提前到這裡
        if section.gpu_combo.currentText() != "自動":
            selected_gpu_display = section.gpu_combo.currentText()
            selected_index = section.gpu_combo.currentIndex()

            # 檢查啟動要求
            if not self.check_launch_requirements(
                selected_gpu_display,
                model_name,
                section.context_length_input.value(),
                section.n_parallel_spinbox.value(),
            ):
                return

        # 判斷使用哪個執行檔
        executable_path = os.path.join(llamacpp_path, f"{executable}{exe_extension}")
        if not os.path.exists(executable_path):
            MessageBox("錯誤", f"執行檔不存在: {executable_path}", self).exec()
            return

        # 獲取llama.cpp版本
        version = get_llamacpp_version(llamacpp_path)
        logging.info(f"llama.cpp版本: {version}")

        # 構建配置字典
        config = {
            "model_path": model_path,
            "context_length": section.context_length_input.value(),
            "gpu_layers": section.gpu_layers_spinbox.value(),
            "host": section.host_input.text(),
            "port": section.port_input.text(),
            "n_parallel": section.n_parallel_spinbox.value(),
            "npp": section.npp_input.text(),
            "ntg": section.ntg_input.text(),
            "npl": section.npl_input.text(),
            "flash_attention": section.flash_attention_check.isChecked(),
            "no_mmap": section.no_mmap_check.isChecked(),
            "command_template": section.command_template.toPlainText().strip(),
        }

        command = build_llamacpp_command(config, executable_path, version)

        env = os.environ.copy()
        try:
            if section.gpu_combo.currentText() != "自動":
                self.gpu_manager.set_gpu_env(
                    env,
                    section.gpu_combo.currentText(),
                    section.gpu_combo.currentIndex(),
                )
        except Exception as e:
            logging.info(f"設置GPU環境變數時出錯: {str(e)}")
            MessageBox("錯誤", f"設置GPU環境變數時出錯: {str(e)}", self).exec()
            return

        command_plain = " ".join(command)
        logging.info(f"執行命令: {command_plain}")

        # 在執行命令的部分
        if sys.platform == "win32":
            if section.background_check.isChecked():
                # 後台執行，不顯示視窗，並加入 processes 列表以便退出時關閉
                proc = subprocess.Popen(command, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
                processes.append(proc)
                logging.info("命令已在後台啟動。")
            else:
                command_prefix = ["start", "cmd", "/K"]
                subprocess.Popen(command_prefix + command, env=env, shell=True)
                logging.info("命令已在新的終端機視窗中啟動。")
        elif sys.platform == "darwin":
            if section.background_check.isChecked():
                proc = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processes.append(proc)
                logging.info("命令已在後台啟動。")
            else:
                cmd_str = " ".join(command)
                # 使用 osascript 執行命令，要先進入正確目錄
                apple_script = [
                    'osascript',
                    '-e',
                    f'''tell application "Terminal"
                        do script "cd {CURRENT_DIR} && {cmd_str}"
                    end tell'''
                ]
                subprocess.Popen(apple_script, env=env)
                logging.info("命令已在新的終端機視窗中啟動。")
        else:
            if section.background_check.isChecked():
                proc = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processes.append(proc)
                logging.info("命令已在後台啟動。")
            else:
                terminal = self.find_terminal()
                if not terminal:
                    MessageBox("錯誤", "無法找到合適的終端機，請手動執行命令。", self).exec()
                    logging.info(f"請手動執行以下命令：\n{command_plain}")
                    return
                if terminal == "gnome-terminal":
                    command_prefix = [terminal, "--", "bash", "-c"]
                else:
                    command_prefix = [terminal, "-e"]
                subprocess.Popen(command_prefix + command, env=env)
                logging.info("命令已在新的終端機視窗中啟動。")

    def find_terminal(self):
        terminals = [
            "x-terminal-emulator",
            "gnome-terminal",
            "konsole",
            "xfce4-terminal",
            "xterm",
        ]
        for term in terminals:
            if shutil.which(term):
                return term
        return None

    def closeEvent(self, event):
        self.save_window_state()
        self.terminate_all_processes()
        event.accept()

    def terminate_all_processes(self):
        print("Terminating all processes...")
        try:
            self.cf_share_section.stop_cf_share()
        except AttributeError:
            print("Warning: CFShareSection not properly initialized")
        for proc in processes:
            proc.terminate()
            try:
                proc.wait(timeout=0.1)  # 等待最多0.1秒
            except subprocess.TimeoutExpired:
                proc.kill()
        processes.clear()

    def start_proxy(self):
        section = self.run_server_section
        if not section.proxy_check.isChecked():
            return

        target_port = section.port_input.text()
        proxy_port = section.proxy_port_input.text()
        
        proxy_script = os.path.join(CURRENT_DIR, "src", "utils", "proxy.py")
        
        # 使用 venv 的 python 執行
        venv_python = os.path.join(CURRENT_DIR, "venv", "Scripts", "python.exe")
        if not os.path.exists(venv_python):
            venv_python = "python"
            
        command = [venv_python, proxy_script, "--target-port", target_port, "--proxy-port", proxy_port]
        
        logging.info(f"啟動繁體轉換代理: {proxy_port} -> {target_port}")
        
        # 始終在背景啟動代理
        if sys.platform == "win32":
            proc = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        processes.append(proc)

    def refresh_gpus(self):
        self.gpu_manager.detect_gpus()
        self.run_server_section.refresh_gpus(keep_selected=True)

        if not self.gpu_manager.nvidia_gpus and not self.gpu_manager.amd_gpus:
            logging.info("未檢測到NVIDIA或AMD GPU")

    def save_window_state(self):
        if SETTING.remember_window_state:
            SETTING.window_geometry = {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height(),
            }
            SETTING.save_settings()

    def load_window_state(self):
        if SETTING.remember_window_state:
            geometry = SETTING.window_geometry
            if geometry:
                self.setGeometry(
                    geometry.get("x", self.x()),
                    geometry.get("y", self.y()),
                    geometry.get("width", self.width()),
                    geometry.get("height", self.height()),
                )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sakura Launcher GUI")
    parser.add_argument(
        "--run-preset", type=str, help="Run a specific preset in background and exit"
    )
    parser.add_argument(
        "--list-presets", action="store_true", help="List all available presets"
    )
    args, unknown = parser.parse_known_args()

    if args.list_presets:
        if not SETTING.presets:
            print("No presets found.")
        else:
            print("Available presets:")
            for p in SETTING.presets:
                print(f"  - {p['name']}")
        sys.exit(0)

    if args.run_preset:
        preset = next((p for p in SETTING.presets if p["name"] == args.run_preset), None)
        if not preset:
            print(f"Error: Preset '{args.run_preset}' not found.")
            sys.exit(1)

        config = preset["config"]
        llamacpp_path = (
            config.get("llamacpp_override")
            or SETTING.llamacpp_path
            or os.path.join(CURRENT_DIR, "llama")
        )
        if not os.path.exists(llamacpp_path):
            print(f"Error: llamacpp path not found: {llamacpp_path}")
            sys.exit(1)

        version = get_llamacpp_version(llamacpp_path)
        exe_ext = ".exe" if sys.platform == "win32" else ""
        executable_path = os.path.join(llamacpp_path, f"llama-server{exe_ext}")

        if not os.path.exists(executable_path):
            print(f"Error: Executable not found: {executable_path}")
            sys.exit(1)

        command = build_llamacpp_command(config, executable_path, version)

        env = os.environ.copy()
        gpu_name = config.get("gpu", "")
        if gpu_name and gpu_name != "自動":
            try:
                from src.gpu import GPUManager, GPUDisplayHelper

                gm = GPUManager()
                # 嘗試根據名稱匹配 GPU 並設置環境變數
                # 這裡簡單處理：如果名稱中包含索引，則提取索引
                _, gpu_index = GPUDisplayHelper.parse_display_name(gpu_name)
                if gpu_index is not None:
                    gm.set_gpu_env(env, gpu_name, gpu_index)
                else:
                    # 如果沒有索引，嘗試查找
                    gpu_key = GPUDisplayHelper.find_gpu_key(gpu_name, gm.gpu_info_map)
                    if gpu_key:
                        # 查找該 key 在列表中的大致索引（這部分邏輯在 GUI 中比較複雜，CLI 盡力而為）
                        pass
            except Exception as e:
                print(f"Warning: Failed to set GPU environment: {e}")

        print(f"Executing: {' '.join(command)}")

        # 啟動代理伺服器 (如果啟用)
        if config.get("use_proxy", False):
            target_port = config.get("port", "8080")
            proxy_port = config.get("proxy_port", "8081")
            proxy_script = os.path.join(CURRENT_DIR, "src", "utils", "proxy.py")
            
            print(f"Starting Traditional Chinese Proxy: {proxy_port} -> {target_port}")
            proxy_cmd = [sys.executable, proxy_script, "--target-port", str(target_port), "--proxy-port", str(proxy_port)]
            
            if sys.platform == "win32":
                subprocess.Popen(proxy_cmd, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen(proxy_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if sys.platform == "win32":
            subprocess.Popen(
                command, env=env, creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            subprocess.Popen(
                command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        print("Success: Server started in background.")
        sys.exit(0)

    setTheme(Theme.DARK)
    setThemeColor(QColor(222, 142, 204))
    app = QApplication(sys.argv)
    better_font = QFont()

    # 獲取主螢幕的縮放比例和原始解析度
    screen = app.primaryScreen()
    screen_geometry = screen.geometry()
    device_pixel_ratio = screen.devicePixelRatio()
    print(f"設備像素比: {device_pixel_ratio}")

    # 計算原始解析度
    original_width = screen_geometry.width() * device_pixel_ratio
    original_height = screen_geometry.height() * device_pixel_ratio
    print(f"原始螢幕解析度: {original_width}x{original_height}")

    # 如果原始解析度大於1920x1080，關閉hinting
    if original_width > 1920 and original_height > 1080:
        print("原始螢幕解析度大於1920x1080，關閉hinting")
        better_font.setHintingPreference(QFont.PreferNoHinting)

    app.setFont(better_font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
