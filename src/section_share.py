import logging
import asyncio
import os
import aiohttp
from PySide6.QtCore import (
    Qt,
    Signal,
    Slot,
    QThreadPool,
    QRunnable,
    QTimer,
    QObject,
    QMetaObject,
)
from PySide6.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QSpacerItem,
    QSizePolicy,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QStackedWidget,
    QWidget,
)
from qfluentwidgets import (
    PushButton,
    PrimaryPushButton,
    MessageBox,
    SegmentedWidget,
    FluentIcon as FIF,
    TableWidget,
)

from .common import CURRENT_DIR, get_resource_path
from .sakura_share_api import SakuraShareAPI
from .setting import SETTING
from .ui import *
from .section_settings import LogHandler


class ShareState(QObject):
    """狀態管理類"""

    status_changed = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.api = None
        self.is_closing = False

        # 初始化定時器
        self.metrics_timer = QTimer(parent)
        self.metrics_timer.setInterval(60000)  # 1分鐘重新整理一次

    def update_api(self, api):
        """更新API實例"""
        self.api = api

    def cleanup(self):
        """清理狀態"""
        self.is_closing = True
        self.api = None


class AsyncWorker(QRunnable):
    """異步任務處理類"""

    class Signals(QObject):
        finished = Signal(object)
        error = Signal(Exception)

    def __init__(self, coro):
        super().__init__()
        self.coro = coro
        self.signals = self.Signals()

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.coro)
            self.signals.finished.emit(result)  # 直接發送結果，不做類型判斷
        except Exception as e:
            self.signals.error.emit(e)
        finally:
            loop.close()


class CFShareSection(QFrame):
    show_message_signal = Signal(str, str)  # (title, message)
    status_update_signal = Signal(str)  # 添加狀態更新信號
    start_timers_signal = Signal()  # 添加新的信號
    stop_timers_signal = Signal()  # 添加停止定時器信號

    def __init__(self, title, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setObjectName(title.replace(" ", "-"))
        self.title = title

        # 初始化狀態管理
        self.state = ShareState(self)
        self.api = None  # 保持向後兼容
        self.is_closing = False  # 保持向後兼容
        self._should_stop = False  # 添加停止標誌

        # 初始化線程池
        self.thread_pool = QThreadPool()

        # 初始化UI
        self._init_ui()

        # 設定定時器連接
        self.metrics_timer = self.state.metrics_timer  # 保持向後兼容
        self.metrics_timer.timeout.connect(self.refresh_metrics)

        # 連接信號
        self.show_message_signal.connect(self._show_message_box)
        self.status_update_signal.connect(self._update_status_label)  # 連接狀態更新信號
        self.start_timers_signal.connect(self._start_timers)
        self.stop_timers_signal.connect(self._stop_timers)

    @Slot(str, str)
    def _show_message_box(self, title, message):
        """在主線程中顯示消息框的槽函數"""
        MessageBox(title, message, self).exec_()

    @Slot(str)
    def _update_status_label(self, status):
        """更新狀態標籤"""
        self.status_label.setText(f"狀態: {status}")

    def _init_ui(self):
        # 創建標籤頁切換控制項
        pivot = SegmentedWidget()
        stacked_widget = QStackedWidget()

        # 創建不同的頁面
        self.share_page = QWidget()
        self.metrics_page = QWidget()
        self.ranking_page = QWidget()

        self.init_share_page()
        self.init_metrics_page()
        self.init_ranking_page()

        def add_sub_interface(widget: QWidget, object_name, text):
            widget.setObjectName(object_name)
            stacked_widget.addWidget(widget)
            pivot.addItem(
                routeKey=object_name,
                text=text,
                onClick=lambda: stacked_widget.setCurrentWidget(widget),
            )

        add_sub_interface(self.share_page, "share_page", "共享設定")
        add_sub_interface(self.metrics_page, "metrics_page", "本地數據統計")
        add_sub_interface(self.ranking_page, "ranking_page", "線上排名")

        pivot.setCurrentItem(stacked_widget.currentWidget().objectName())

        self.setLayout(
            UiCol(
                pivot,
                stacked_widget,
            )
        )

    def init_share_page(self):
        layout = QVBoxLayout(self.share_page)
        layout.setContentsMargins(0, 0, 0, 0)  # 設定內部邊距

        self.refresh_slots_button = PushButton(FIF.SYNC, "重新整理")
        self.refresh_slots_button.clicked.connect(self.refresh_slots)

        self.stop_button = PushButton(FIF.CLOSE, "下線")
        self.stop_button.clicked.connect(self.stop_cf_share)
        self.stop_button.setEnabled(False)

        self.start_button = PrimaryPushButton(FIF.PLAY, "上線")
        self.start_button.clicked.connect(self.start_cf_share)

        layout.addWidget(
            UiButtonGroup(
                self.refresh_slots_button,
                self.stop_button,
                self.start_button,
            )
        )

        self.worker_url_input = UiLineEdit("輸入WORKER_URL", SETTING.worker_url)
        layout.addLayout(UiOptionRow("連結", self.worker_url_input))
        self.worker_url_input.textChanged.connect(
            lambda text: SETTING.set_value("worker_url", text.strip())
        )

        self.tg_token_input = UiLineEdit("可選，從@sakura_share_one_bot獲取，用於統計貢獻（SGLang 啟動必填）")
        # 從設定中加載儲存的token
        if hasattr(SETTING, "token"):
            self.tg_token_input.setText(SETTING.token)
        layout.addLayout(UiOptionRow("令牌", self.tg_token_input))
        # 添加token自動儲存
        self.tg_token_input.textChanged.connect(
            lambda text: SETTING.set_value("token", text.strip())
        )

        self.port_override_input = UiLineEdit("可選，用於覆蓋運行面板的埠設定，SGLang啟動請填30000")
        # 從設定中加載儲存的埠
        if hasattr(SETTING, "port_override"):
            self.port_override_input.setText(SETTING.port_override)
        layout.addLayout(UiOptionRow("埠", self.port_override_input))
        # 添加埠自動儲存
        self.port_override_input.textChanged.connect(
            lambda text: SETTING.set_value("port_override", text.strip())
        )

        self.status_label = QLabel("狀態: 未運行")
        layout.addWidget(self.status_label)

        self.slots_status_label = QLabel("線上slot數量: 未知")
        layout.addWidget(self.slots_status_label)

        # 添加節點清單顯示
        self.nodes_label = QLabel("節點清單: 未獲取")
        self.nodes_label.setWordWrap(True)
        self.nodes_label.setTextFormat(Qt.RichText)
        self.nodes_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.03);
                border-radius: 5px;
                padding: 8px;
                margin-top: 5px;
                margin-bottom: 5px;
            }
        """)
        layout.addWidget(self.nodes_label)

        # 添加說明文本
        description = QLabel()
        description.setText(
            """
            <html>
            <body>
            <h2>Sakura Share - 模型共享工具</h2>
            
            <p>這是一個讓你快速將本地部署的Sakura模型分享給其他用戶的工具（成為帕魯）。</p>
            
            <h3>支援的模型</h3>
            <ul>
                <li>sakura-14b-qwen2.5-v1.0-iq4xs.gguf</li>
                <li>sakura-14b-qwen2.5-v1.0-q6k.gguf</li>
                <li>SakuraLLM.Sakura-14B-Qwen2.5-v1.0-W8A8-Int8
                    <small>（需要使用SGLang啟動，並需要申請白名單權限）</small>
                </li>
            </ul>
            
            <h3>重要說明</h3>
            <ul>
                <li>建議使用預設連結 - 由共享腳本開發者維護，穩定可靠</li>
                <li>雙向使用 - 你可以選擇成為帕魯分享模型，也可以作為用戶訪問其他帕魯的模型
                    <small>（但不保證服務的可用性與穩定性）</small>
                </li>
                <li><b>匿名分享 - 分享時不填寫「令牌」，就可以匿名分享算力</b></li>
                <li>如果無法正常連結到伺服器，請嘗試將「連結」更改為 <a href='https://cf.sakura-share.one'>https://cf.sakura-share.one</a></li>
            </ul>
            
            <h3>貢獻統計說明</h3>
            <ul>
                <li>參與方式：
                    <ul>
                        <li>通過 <a href='https://t.me/sakura_share_one_bot'>@sakura_share_one_bot</a> 獲取「令牌（Token）」</li>
                        <li>貢獻統計為可選功能（W8A8模型必需）</li>
                        <li>在「線上排名」標籤中可查看貢獻排名（顯示前10名）</li>
                        <li>查看全網算力情況：<a href='https://sakura-share.one/'>算力公示板</a></li>
                    </ul>
                </li>
                <li>詳細文檔請參考：<a href='https://www.youtube.com/watch?v=dQw4w9WgXcQ'>Sakura Share</a></li>
            </ul>
            </body>
            </html>
            """
        )
        description.setTextFormat(Qt.RichText)
        description.setOpenExternalLinks(True)
        description.setWordWrap(True)
        description.setStyleSheet(
            """
            QLabel {
                border-radius: 5px;
                padding: 15px;
            }
        """
        )
        layout.addWidget(description)

        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def init_metrics_page(self):
        """初始化指標統計頁面"""
        layout = QVBoxLayout(self.metrics_page)
        layout.setContentsMargins(0, 0, 0, 0)

        # 創建子頁面切換控制項
        self.metrics_pivot = SegmentedWidget()
        self.metrics_stacked_widget = QStackedWidget()

        # 創建LlamaCpp和SGLang兩個子頁面
        self.llamacpp_page = QWidget()
        self.sglang_page = QWidget()

        # 初始化LlamaCpp頁面
        self.init_llamacpp_page()
        
        # 初始化SGLang頁面
        self.init_sglang_page()

        def add_metrics_sub_interface(widget: QWidget, object_name, text):
            widget.setObjectName(object_name)
            self.metrics_stacked_widget.addWidget(widget)
            self.metrics_pivot.addItem(
                routeKey=object_name,
                text=text,
                onClick=lambda: self.metrics_stacked_widget.setCurrentWidget(widget),
            )

        add_metrics_sub_interface(self.llamacpp_page, "llamacpp_page", "LlamaCpp")
        add_metrics_sub_interface(self.sglang_page, "sglang_page", "SGLang")

        self.metrics_pivot.setCurrentItem(self.metrics_stacked_widget.currentWidget().objectName())

        layout.addWidget(self.metrics_pivot)
        layout.addWidget(self.metrics_stacked_widget)

        # 添加重新整理按鈕
        self.refresh_metrics_button = PushButton(FIF.SYNC, "重新整理數據")
        self.refresh_metrics_button.clicked.connect(self.refresh_metrics)
        layout.addWidget(self.refresh_metrics_button)

    def init_llamacpp_page(self):
        """初始化LlamaCpp指標頁面"""
        layout = QVBoxLayout(self.llamacpp_page)
        layout.setContentsMargins(0, 0, 0, 0)

        # 創建表格
        self.llamacpp_table = TableWidget(self)
        self.llamacpp_table.setColumnCount(2)
        self.llamacpp_table.setHorizontalHeaderLabels(["指標", "值"])
        self.llamacpp_table.verticalHeader().setVisible(False)
        self.llamacpp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # 初始化指標數據
        self._init_llamacpp_metrics_data()

        layout.addWidget(self.llamacpp_table)

    def init_sglang_page(self):
        """初始化SGLang指標頁面"""
        layout = QVBoxLayout(self.sglang_page)
        layout.setContentsMargins(0, 0, 0, 0)

        # 創建表格
        self.sglang_table = TableWidget(self)
        self.sglang_table.setColumnCount(2)
        self.sglang_table.setHorizontalHeaderLabels(["指標", "值"])
        self.sglang_table.verticalHeader().setVisible(False)
        self.sglang_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # 初始化指標數據
        self._init_sglang_metrics_data()

        layout.addWidget(self.sglang_table)
        
        # 添加模型資訊標籤
        self.model_info_label = QLabel("模型: 未知")
        self.model_info_label.setWordWrap(True)
        layout.addWidget(self.model_info_label)

    def _init_llamacpp_metrics_data(self):
        """初始化LlamaCpp指標數據和提示資訊"""
        metrics_data = [
            ("提示詞 tokens 總數", "暫無數據"),
            ("提示詞處理總時間", "暫無數據"),
            ("生成的 tokens 總數", "暫無數據"),
            ("生成處理總時間", "暫無數據"),
            ("llama_decode() 調用總次數", "暫無數據"),
            ("每次 llama_decode() 調用的平均忙碌槽位數", "暫無數據"),
            ("提示詞平均吞吐量", "暫無數據"),
            ("生成平均吞吐量", "暫無數據"),
            ("KV-cache 使用率", "暫無數據"),
            ("KV-cache tokens", "暫無數據"),
            ("正在處理的請求數", "暫無數據"),
            ("延遲的請求數", "暫無數據"),
        ]

        tooltips = {
            "提示詞 tokens 總數": "已處理的提示詞 tokens 總數",
            "提示詞處理總時間": "提示詞處理的總時間",
            "生成的 tokens 總數": "已生成的 tokens 總數",
            "生成處理總時間": "生成處理的總時間",
            "llama_decode() 調用總次數": "llama_decode() 函數的總調用次數",
            "每次 llama_decode() 調用的平均忙碌槽位數": "每次 llama_decode() 調用時的平均忙碌槽位數",
            "提示詞平均吞吐量": "提示詞的平均處理速度",
            "生成平均吞吐量": "生成的平均速度",
            "KV-cache 使用率": "KV-cache 的使用率（1 表示 100% 使用）",
            "KV-cache tokens": "KV-cache 中的 token 數量",
            "正在處理的請求數": "當前正在處理的請求數",
            "延遲的請求數": "被延遲的請求數",
        }

        self.llamacpp_table.setRowCount(len(metrics_data))
        for row, (metric, value) in enumerate(metrics_data):
            self.llamacpp_table.setItem(row, 0, QTableWidgetItem(metric))
            self.llamacpp_table.setItem(row, 1, QTableWidgetItem(value))
            if metric in tooltips:
                self.llamacpp_table.item(row, 0).setToolTip(tooltips[metric])

    def _init_sglang_metrics_data(self):
        """初始化SGLang指標數據和提示資訊"""
        metrics_data = [
            ("Token使用率", "暫無數據"),
            ("緩存命中率", "暫無數據"),
            ("推測解碼接受長度", "暫無數據"),
            ("提示詞tokens總數", "暫無數據"),
            ("生成tokens總數", "暫無數據"),
            ("請求總數", "暫無數據"),
            ("首token平均時間", "暫無數據"),
            ("請求平均延遲", "暫無數據"),
            ("每token平均時間", "暫無數據"),
            ("當前運行請求數", "暫無數據"),
            ("當前使用tokens數", "暫無數據"),
            ("生成吞吐量", "暫無數據"),
            ("隊列中請求數", "暫無數據"),
        ]

        tooltips = {
            "Token使用率": "當前token使用率",
            "緩存命中率": "前綴緩存命中率",
            "推測解碼接受長度": "推測解碼的平均接受長度",
            "提示詞tokens總數": "已處理的提示詞tokens總數",
            "生成tokens總數": "已生成的tokens總數",
            "請求總數": "已處理的請求總數",
            "首token平均時間": "生成第一個token的平均時間",
            "請求平均延遲": "端到端請求的平均延遲",
            "每token平均時間": "每個輸出token的平均時間",
            "當前運行請求數": "當前正在運行的請求數",
            "當前使用tokens數": "當前使用的tokens數量",
            "生成吞吐量": "生成吞吐量(tokens/秒)",
            "隊列中請求數": "等待隊列中的請求數",
        }

        self.sglang_table.setRowCount(len(metrics_data))
        for row, (metric, value) in enumerate(metrics_data):
            self.sglang_table.setItem(row, 0, QTableWidgetItem(metric))
            self.sglang_table.setItem(row, 1, QTableWidgetItem(value))
            if metric in tooltips:
                self.sglang_table.item(row, 0).setToolTip(tooltips[metric])

    def _init_metrics_data(self):
        """初始化指標數據和提示資訊 - 保留向後兼容"""
        self._init_llamacpp_metrics_data()

    def init_ranking_page(self):
        """初始化排名頁面"""
        layout = QVBoxLayout(self.ranking_page)
        layout.setContentsMargins(0, 0, 0, 0)  # 設定內部邊距

        self.ranking_table = TableWidget(self)
        self.ranking_table.setColumnCount(3)
        self.ranking_table.setHorizontalHeaderLabels(["用戶名", "生成Token數", "線上時長(小時)"])
        self.ranking_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.ranking_table)

        self.refresh_ranking_button = PushButton(FIF.SYNC, "重新整理排名", self)
        self.refresh_ranking_button.clicked.connect(self.refresh_ranking)
        layout.addWidget(self.refresh_ranking_button)

    @Slot()
    def refresh_metrics(self):
        """重新整理指標數據"""
        # 添加檢查，如果正在停止過程中，則不繼續重新整理
        if self._should_stop:
            self.refresh_metrics_button.setEnabled(True)
            return
            
        worker_url = self.worker_url_input.text().strip()
        if not worker_url:
            MessageBox("錯誤", "請先設定連結", self).exec_()
            return

        # 優先使用埠設定
        port_override = self.port_override_input.text().strip()
        if port_override:
            try:
                port = int(port_override)
            except ValueError:
                MessageBox("錯誤", "埠設定必須是有效的數字", self).exec_()
                return
        else:
            port = self.main_window.run_server_section.port_input.text().strip()
            if not port:
                MessageBox("錯誤", "請在運行面板中設定埠號或使用埠覆蓋", self).exec_()
                return
            try:
                port = int(port)
            except ValueError:
                MessageBox("錯誤", "埠號必須是有效的數字", self).exec_()
                return

        self.refresh_metrics_button.setEnabled(False)
        
        # 無論是否已啟動API，都創建一個新的臨時API進行重新整理操作
        api = self.api if self.api else SakuraShareAPI(port, worker_url)

        worker = AsyncWorker(api.get_metrics())
        worker.signals.finished.connect(self.on_metrics_refreshed)
        worker.signals.error.connect(self.on_error)
        self.thread_pool.start(worker)

    @Slot(object)
    def on_metrics_refreshed(self, metrics):
        """處理指標重新整理結果"""
        self.refresh_metrics_button.setEnabled(True)
        if "error" in metrics:
            logging.error(f"獲取指標失敗: {metrics['error']}")
            return

        # 儲存當前指標數據，用於鍵值查找
        self.current_metrics = metrics

        # 檢查是否為SGLang指標
        is_sglang = metrics.get("_is_sglang", 0) > 0
        
        # 獲取當前選中的標籤頁
        current_page = self.metrics_stacked_widget.currentWidget().objectName()
        
        # 根據指標類型更新相應的表格
        if is_sglang:
            # 更新SGLang指標
            self._update_sglang_metrics(metrics)
            # 如果當前不是SGLang頁面，提示用戶並詢問是否切換
            if current_page != "sglang_page":
                self._switch_metrics_tab("sglang_page", "檢測到SGLang指標數據")
        else:
            # 更新LlamaCpp指標
            self._update_llamacpp_metrics(metrics)
            # 如果當前不是LlamaCpp頁面，提示用戶並詢問是否切換
            if current_page != "llamacpp_page":
                self._switch_metrics_tab("llamacpp_page", "檢測到LlamaCpp指標數據")

    def _update_llamacpp_metrics(self, metrics):
        """更新LlamaCpp指標表格"""
        for row in range(self.llamacpp_table.rowCount()):
            metric_item = self.llamacpp_table.item(row, 0)
            value_item = self.llamacpp_table.item(row, 1)
            if metric_item and value_item:
                metric_text = metric_item.text()
                key = self.get_llamacpp_metric_key(metric_text)
                if key in metrics:
                    value = metrics[key]
                    self._format_llamacpp_metric_value(value_item, key, value)

    def _update_sglang_metrics(self, metrics):
        """更新SGLang指標表格"""
        # 更新模型資訊
        model_name = metrics.get("_model_name", "未知")
        self.model_info_label.setText(f"模型: {model_name}")
        
        for row in range(self.sglang_table.rowCount()):
            metric_item = self.sglang_table.item(row, 0)
            value_item = self.sglang_table.item(row, 1)
            if metric_item and value_item:
                metric_text = metric_item.text()
                key = self.get_sglang_metric_key(metric_text)
                if key in metrics:
                    value = metrics[key]
                    self._format_sglang_metric_value(value_item, key, value, metrics)
                else:
                    # 嘗試查找匹配的前綴
                    base_key = key.split("{")[0] if "{" in key else key
                    matching_keys = [k for k in metrics.keys() if k.startswith(base_key + "{") or k == base_key]
                    if matching_keys:
                        value = metrics[matching_keys[0]]
                        self._format_sglang_metric_value(value_item, matching_keys[0], value, metrics)

    def _format_llamacpp_metric_value(self, item, key, value):
        """格式化LlamaCpp指標值"""
        try:
            if key in ["prompt_tokens_total", "tokens_predicted_total"]:
                item.setText(f"{float(value):.0f} tokens")
            elif key in ["prompt_seconds_total", "tokens_predicted_seconds_total"]:
                item.setText(f"{float(value):.2f} 秒")
            elif key == "n_decode_total":
                item.setText(f"{float(value):.0f} 次")
            elif key == "n_busy_slots_per_decode":
                item.setText(f"{float(value):.2f}")
            elif key in ["prompt_tokens_seconds", "predicted_tokens_seconds"]:
                item.setText(f"{float(value):.2f} tokens/s")
            elif key == "kv_cache_usage_ratio":
                item.setText(f"{float(value)*100:.2f}%")
            elif key == "kv_cache_tokens":
                item.setText(f"{float(value):.0f} tokens")
            elif key in ["requests_processing", "requests_deferred"]:
                item.setText(f"{float(value):.0f}")
            else:
                item.setText(f"{float(value):.2f}")
        except ValueError:
            item.setText(str(value))

    def _format_sglang_metric_value(self, item, key, value, metrics):
        """格式化SGLang指標值"""
        try:
            # 提取基礎鍵名（不包含模型名稱部分）
            base_key = key.split("{")[0] if "{" in key else key
            
            if base_key == "sglang:token_usage":
                item.setText(f"{float(value)*100:.2f}%")
            elif base_key == "sglang:cache_hit_rate":
                item.setText(f"{float(value)*100:.2f}%")
            elif base_key == "sglang:spec_accept_length":
                item.setText(f"{float(value):.2f}")
            elif base_key in ["sglang:prompt_tokens_total", "sglang:generation_tokens_total"]:
                item.setText(f"{float(value):,.0f} tokens")
            elif base_key == "sglang:num_requests_total":
                item.setText(f"{float(value):,.0f}")
            elif base_key in ["sglang:time_to_first_token_seconds_sum", "sglang:e2e_request_latency_seconds_sum"]:
                # 查找對應的count指標
                count_key = base_key.replace("_sum", "_count")
                # 在所有鍵中查找匹配的count鍵
                count_full_key = None
                for k in metrics.keys():
                    if k.startswith(count_key + "{") or k == count_key:
                        count_full_key = k
                        break
                
                count = metrics.get(count_full_key, 1) if count_full_key else 1
                total = float(value)
                avg = total / count if count > 0 else 0
                item.setText(f"{avg:.2f} 秒")
            elif base_key == "sglang:time_per_output_token_seconds_sum":
                # 查找對應的count指標
                count_key = base_key.replace("_sum", "_count")
                # 在所有鍵中查找匹配的count鍵
                count_full_key = None
                for k in metrics.keys():
                    if k.startswith(count_key + "{") or k == count_key:
                        count_full_key = k
                        break
                    
                count = metrics.get(count_full_key, 1) if count_full_key else 1
                total = float(value)
                avg = total / count if count > 0 else 0
                item.setText(f"{avg*1000:.2f} 毫秒")
            elif base_key in ["sglang:num_running_reqs", "sglang:num_used_tokens", "sglang:num_queue_reqs"]:
                item.setText(f"{float(value):.0f}")
            elif base_key == "sglang:gen_throughput":
                item.setText(f"{float(value):.2f} tokens/s")
            else:
                item.setText(f"{float(value):.2f}")
        except ValueError:
            item.setText(str(value))

    def get_llamacpp_metric_key(self, metric_text):
        """獲取LlamaCpp指標鍵值映射"""
        key_map = {
            "提示詞 tokens 總數": "prompt_tokens_total",
            "提示詞處理總時間": "prompt_seconds_total",
            "生成的 tokens 總數": "tokens_predicted_total",
            "生成處理總時間": "tokens_predicted_seconds_total",
            "llama_decode() 調用總次數": "n_decode_total",
            "每次 llama_decode() 調用的平均忙碌槽位數": "n_busy_slots_per_decode",
            "提示詞平均吞吐量": "prompt_tokens_seconds",
            "生成平均吞吐量": "predicted_tokens_seconds",
            "KV-cache 使用率": "kv_cache_usage_ratio",
            "KV-cache tokens": "kv_cache_tokens",
            "正在處理的請求數": "requests_processing",
            "延遲的請求數": "requests_deferred",
        }
        return key_map.get(metric_text, "")

    def get_sglang_metric_key(self, metric_text):
        """獲取SGLang指標鍵值映射"""
        base_key_map = {
            "Token使用率": "sglang:token_usage",
            "緩存命中率": "sglang:cache_hit_rate",
            "推測解碼接受長度": "sglang:spec_accept_length",
            "提示詞tokens總數": "sglang:prompt_tokens_total",
            "生成tokens總數": "sglang:generation_tokens_total",
            "請求總數": "sglang:num_requests_total",
            "首token平均時間": "sglang:time_to_first_token_seconds_sum",
            "請求平均延遲": "sglang:e2e_request_latency_seconds_sum",
            "每token平均時間": "sglang:time_per_output_token_seconds_sum",
            "當前運行請求數": "sglang:num_running_reqs",
            "當前使用tokens數": "sglang:num_used_tokens",
            "生成吞吐量": "sglang:gen_throughput",
            "隊列中請求數": "sglang:num_queue_reqs",
        }
        
        base_key = base_key_map.get(metric_text, "")
        
        # 如果找不到基礎鍵，直接返回空字符串
        if not base_key:
            return ""
        
        # 在metrics字典中查找匹配的完整鍵（包含模型名稱）
        for full_key in self.current_metrics.keys() if hasattr(self, 'current_metrics') else []:
            if full_key.startswith(base_key + "{"):
                return full_key
        
        # 如果沒有找到匹配的完整鍵，返回基礎鍵
        return base_key

    def get_metric_key(self, metric_text):
        """獲取指標鍵值映射 - 保留向後兼容"""
        return self.get_llamacpp_metric_key(metric_text)

    @Slot()
    def _start_timers(self):
        """在主線程中啟動定時器"""
        self.metrics_timer.start()

    @Slot()
    def _stop_timers(self):
        """在主線程中停止定時器"""
        self.metrics_timer.stop()

    @Slot()
    def start_cf_share(self):
        """啟動共享功能"""
        # 檢查必要參數
        worker_url = self.worker_url_input.text().strip()
        if not worker_url:
            MessageBox("錯誤", "請輸入WORKER_URL", self).exec_()
            return

        # 優先使用埠設定
        port_override = self.port_override_input.text().strip()
        if port_override:
            try:
                port = int(port_override)
            except ValueError:
                MessageBox("錯誤", "埠設定必須是有效的數字", self).exec_()
                return
        else:
            port = self.main_window.run_server_section.port_input.text().strip()
            if not port:
                MessageBox("錯誤", "請在運行面板中設定埠號或使用埠覆蓋", self).exec_()
                return
            try:
                port = int(port)
            except ValueError:
                MessageBox("錯誤", "埠號必須是有效的數字", self).exec_()
                return

        # 儲存參數
        self.port = port
        self.worker_url = worker_url
        self.tg_token = self.tg_token_input.text().strip()

        # 重置停止標誌
        self._should_stop = False
        
        # 創建並啟動worker
        worker = AsyncWorker(self.start_sharing())
        worker.signals.finished.connect(self._handle_connection_status)
        
        # 儲存worker引用
        self._current_worker = worker
        self.thread_pool.start(worker)
        
        # 更新UI狀態
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("狀態: 正在啟動...")

    async def start_sharing(self):
        try:
            # 初始化API
            self.api = SakuraShareAPI(self.port, self.worker_url)
            self.state.update_api(self.api)
            
            # 檢查本地服務狀態
            if not await self.api.check_local_health_status():
                return "錯誤：本地服務未運行"

            # 檢查是否為SGLang服務
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://localhost:{self.port}/get_model_info", timeout=5) as response:
                        if response.status == 200:
                            data = await response.json()
                            if "model_path" in data and "W8A8" in data["model_path"]:
                                if not self.tg_token:
                                    return "錯誤：檢測到SGLang W8A8模型，必須填寫令牌"
            except Exception:
                pass

            # 啟動服務
            if not await self.api.start(self.tg_token):
                return "錯誤：啟動失敗，請檢查配置和網絡連接"

            # 發送初始狀態
            self.status_update_signal.emit("運行中 - WebSocket已連接")
            
            # 使用信號在主線程中啟動定時器
            self.start_timers_signal.emit()
            
            # 保持連接活躍
            while not self._should_stop:
                await asyncio.sleep(60)
                # if not self.api or not self.api.is_running:
                #     return "錯誤：連接已斷開"
                # NOTE: 暫時關閉本地服務檢查，新版Share會大幅增加llamacpp的負載，導致永遠無法通過檢查
                # # 定期檢查連接狀態
                # try:
                #     if not await self.api.check_local_health_status():
                #         return "錯誤：本地服務已斷開"
                # except Exception as e:
                #     return f"錯誤：連接檢查失敗 - {str(e)}"

            return "正常停止"
            
        except Exception as e:
            print(f"[Share] 啟動錯誤: {e}")
            return f"錯誤：{str(e)}"

    def _handle_connection_status(self, status):
        """處理連接狀態更新"""
        if isinstance(status, str):
            if status.startswith("錯誤"):
                self.status_label.setText(f"狀態: {status}")
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                UiInfoBarError(self, status)
            else:
                self.status_label.setText(f"狀態: {status}")
                if status == "正常停止":
                    self.start_button.setEnabled(True)
                    self.stop_button.setEnabled(False)
                    self.metrics_timer.stop()

    @Slot()
    def stop_cf_share(self):
        """停止共享服務"""
        self._should_stop = True
        
        # 立即停止定時器，防止在停止期間繼續觸發重新整理
        self.metrics_timer.stop()
        self.stop_timers_signal.emit()
        
        if self.api:
            async def stop_api():
                api = self.api
                self.api = None  # 立即清除引用
                try:
                    await api.stop()
                    return None
                except Exception as e:
                    print(f"[Share] 停止錯誤: {e}")
                    return str(e)
            
            # 創建新的worker來處理停止操作
            worker = AsyncWorker(stop_api())
            worker.signals.finished.connect(self._handle_stop_finished)
            worker.signals.error.connect(self._handle_stop_error)
            self.thread_pool.start(worker)
        
        # 更新UI狀態
        self.status_label.setText("狀態: 正在停止...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)

    @Slot()
    def _handle_stop_finished(self, error_msg=None):
        """處理停止完成的回調"""
        # 確保定時器已經停止
        self.metrics_timer.stop()
        
        # 重置停止標誌，使重新整理功能恢復可用
        self._should_stop = False
        
        if error_msg:
            self.show_message_signal.emit("錯誤", f"停止時發生錯誤: {error_msg}")
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("狀態: 已停止")

    @Slot(Exception)
    def _handle_stop_error(self, error):
        """處理停止時的錯誤"""
        print(f"[Share] 停止過程中發生錯誤: {error}")
        # 重置停止標誌，即使出錯也能恢復重新整理功能
        self._should_stop = False
        
        # 更新UI狀態
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText(f"狀態: 停止失敗 - {str(error)}")
        self.show_message_signal.emit("錯誤", f"停止過程中發生錯誤: {str(error)}")

    @Slot()
    def refresh_slots(self):
        """重新整理slots狀態"""
        worker_url = self.worker_url_input.text().strip()
        if not worker_url:
            self.slots_status_label.setText("線上slot數量: 未設定連結")
            UiInfoBarWarning(self, "請先設定連結後再重新整理線上數量。")
            return

        self.refresh_slots_button.setEnabled(False)
        api = self.api if self.api else SakuraShareAPI(0, worker_url)

        # 獲取slots狀態
        worker = AsyncWorker(api.get_slots_status())
        worker.signals.finished.connect(self.update_slots_status)
        worker.signals.error.connect(self.on_error_refresh_slots)
        self.thread_pool.start(worker)

        # 同時獲取節點清單
        tg_token = self.tg_token_input.text().strip()
        nodes_worker = AsyncWorker(api.get_nodes(tg_token))
        nodes_worker.signals.finished.connect(self.update_nodes_list)
        nodes_worker.signals.error.connect(self.on_error_refresh_nodes)
        self.thread_pool.start(nodes_worker)

    @Slot(str)
    def update_slots_status(self, status):
        """更新slots狀態顯示"""
        self.slots_status_label.setText(status)
        self.refresh_slots_button.setEnabled(True)

    @Slot(Exception)
    def on_error_refresh_slots(self, error):
        """處理重新整理slots時的錯誤"""
        self.slots_status_label.setText(f"線上slot數量: 獲取失敗 - {str(error)}")
        self.refresh_slots_button.setEnabled(True)

    @Slot(object)
    def update_nodes_list(self, nodes):
        """更新節點清單顯示"""
        if isinstance(nodes, list) and len(nodes) > 0 and not isinstance(nodes[0], dict):
            # 處理正常的節點ID清單
            if len(nodes) == 0:
                self.nodes_label.setText("節點清單: 當前沒有線上節點")
                return
                
            nodes_text = "<b>節點清單 (Metrics IDs):</b><br>"
            for i, node_id in enumerate(nodes):
                nodes_text += f"{i+1}. <b>ID:</b> {node_id}<br>"
                
            self.nodes_label.setText(nodes_text)
            self.nodes_label.setTextFormat(Qt.RichText)
        elif isinstance(nodes, list) and len(nodes) > 0 and "error" in nodes[0]:
            # 處理錯誤情況
            error_msg = nodes[0]["error"]
            self.nodes_label.setText(f"節點清單: 獲取失敗 - {error_msg}")
            self.nodes_label.setTextFormat(Qt.PlainText)
        else:
            # 處理其他未知情況
            self.nodes_label.setText("節點清單: 獲取失敗 - 未知格式")
            self.nodes_label.setTextFormat(Qt.PlainText)

    @Slot(Exception)
    def on_error_refresh_nodes(self, error):
        """處理重新整理節點清單時的錯誤"""
        self.nodes_label.setText(f"節點清單: 獲取失敗 - {str(error)}")

    @Slot()
    def refresh_ranking(self):
        """重新整理排名數據"""
        # 添加檢查，如果正在停止過程中，則不繼續重新整理
        if self._should_stop:
            self.refresh_ranking_button.setEnabled(True)
            return
            
        worker_url = self.worker_url_input.text().strip()
        if not worker_url:
            MessageBox("錯誤", "請先設定連結", self).exec_()
            return

        self.refresh_ranking_button.setEnabled(False)
        api = self.api if self.api else SakuraShareAPI(0, worker_url)

        worker = AsyncWorker(api.get_ranking())
        worker.signals.finished.connect(self.update_ranking)
        worker.signals.error.connect(self.on_error_refresh_ranking)
        self.thread_pool.start(worker)

    @Slot(object)
    def update_ranking(self, ranking_data):
        """更新排名數據"""
        if isinstance(ranking_data, list) and len(ranking_data) > 0 and "error" not in ranking_data[0]:
            self.ranking_table.setRowCount(0)
            for item in ranking_data:
                row = self.ranking_table.rowCount()
                self.ranking_table.insertRow(row)
                self.ranking_table.setItem(row, 0, QTableWidgetItem(item["name"]))
                self.ranking_table.setItem(row, 1, QTableWidgetItem(f"{item['token_count']:,}"))
                # 將線上時間從秒轉換為小時，並保留兩位小數
                online_hours = item["online_time"] / 3600
                self.ranking_table.setItem(row, 2, QTableWidgetItem(f"{online_hours:.2f}"))
        else:
            error_msg = ranking_data[0]["error"] if isinstance(ranking_data, list) else "未知錯誤"
            MessageBox("錯誤", f"獲取排名失敗: {error_msg}", self).exec_()

        self.refresh_ranking_button.setEnabled(True)

    @Slot(Exception)
    def on_error_refresh_ranking(self, error):
        """處理重新整理排名時的錯誤"""
        MessageBox("錯誤", f"獲取排名失敗: {str(error)}", self).exec_()
        self.refresh_ranking_button.setEnabled(True)

    def closeEvent(self, event):
        """處理關閉事件"""
        QTimer.singleShot(0, self.cleanup)
        QTimer.singleShot(100, lambda: super().closeEvent(event))

    def cleanup(self):
        """清理資源"""
        self.is_closing = True
        self.state.is_closing = True

        # 停止定時器
        if hasattr(self, "metrics_timer"):
            self.metrics_timer.stop()
            self.metrics_timer.deleteLater()

        # API清理
        if self.api:
            try:
                def cleanup_api():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.api.stop())
                    except Exception as e:
                        logging.error(f"Error during API cleanup: {str(e)}")
                    finally:
                        self.api = None

                QTimer.singleShot(0, cleanup_api)
            except Exception as e:
                logging.error(f"Error initiating cleanup: {str(e)}")

    @Slot(Exception)
    def on_error(self, error):
        """處理通用錯誤"""
        self.status_label.setText(f"狀態: 錯誤 - {str(error)}")
        # 確保按鈕恢復可用狀態
        self.refresh_metrics_button.setEnabled(True)
        self.refresh_ranking_button.setEnabled(True)
        MessageBox("錯誤", f"操作失敗: {str(error)}", self).exec_()

    def _switch_metrics_tab(self, target_page, reason):
        """智能切換指標標籤頁
        
        Args:
            target_page: 目標頁面的objectName
            reason: 切換原因
        """
        # 直接切換標籤頁，不再彈出提示
        # 設定當前項
        self.metrics_pivot.setCurrentItem(target_page)
        # 同時切換堆疊小部件的當前頁面
        for i in range(self.metrics_stacked_widget.count()):
            if self.metrics_stacked_widget.widget(i).objectName() == target_page:
                self.metrics_stacked_widget.setCurrentIndex(i)
                break
