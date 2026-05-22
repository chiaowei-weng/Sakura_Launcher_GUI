import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List, TypeVar, Callable, Coroutine
from .sakura_ws_client import SakuraWSClient

T = TypeVar('T')  # 定義泛型類型變量

class SakuraShareAPI:
    """
    SakuraShareAPI類用於管理WebSocket連接、健康狀態檢查等功能。
    
    參數:
        port (int): 本地服務運行的埠號。
        worker_url (str): Worker服務的URL地址。
    """

    def __init__(self, port: int, worker_url: str):
        print(f"[API] 初始化API: port={port}, worker_url={worker_url}")
        self.port = port
        self.worker_url = worker_url.rstrip('/')
        self.is_running = False
        self.is_closing = False
        self.ws_client = None
        self._ws_task = None
        self._last_successful_check_mode = None  # 記錄上次成功的檢查模式
        self._health_check_failures = 0  # 記錄連續失敗次數
        self._last_health_check_time = 0  # 記錄上次檢查時間

    async def _retry_request(
        self, 
        request_func: Callable[[], Coroutine[Any, Any, T]], 
        max_retries: int = 3, 
        timeout_seconds: int = 10,
        error_msg: str = "請求失敗",
        success_condition: Callable[[T], bool] = None
    ) -> T:
        """
        通用的重試請求方法
        
        參數:
            request_func: 實際執行請求的異步函數
            max_retries: 最大重試次數
            timeout_seconds: 請求超時時間(秒)
            error_msg: 錯誤信息前綴
            success_condition: 判斷響應是否成功的函數，默認為None表示無需額外判斷
            
        返回:
            T: 請求結果，如果所有嘗試都失敗則返回錯誤信息
        """
        last_error = None
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        
        for attempt in range(max_retries):
            try:
                print(f"[API] {error_msg} (嘗試 {attempt + 1}/{max_retries})")
                result = await request_func()
                
                # 如果提供了成功條件函數，則使用它來判斷是否成功
                if success_condition and not success_condition(result):
                    last_error = f"響應不滿足成功條件: {result}"
                    print(f"[API] {last_error}")
                else:
                    return result
                    
            except asyncio.TimeoutError:
                last_error = "請求超時"
                print(f"[API] {error_msg}超時 (嘗試 {attempt + 1}/{max_retries})")
            except Exception as e:
                last_error = str(e)
                print(f"[API] {error_msg} (嘗試 {attempt + 1}/{max_retries}): {last_error}")
                
            if attempt < max_retries - 1:
                # 根據重試次數動態調整等待時間
                wait_time = min(2 * (attempt + 1), 5)  # 最多等待5秒
                print(f"[API] 等待{wait_time}秒後重試")
                await asyncio.sleep(wait_time)
                
        return {"error": f"{error_msg} - {last_error}"}

    async def check_local_health_status(self) -> bool:
        """
        檢查本地服務的健康狀態
        """
        timeout = aiohttp.ClientTimeout(total=15)  # 增加超時時間到15秒
        max_retries = 3
        
        # 根據之前成功的檢查方式確定優先使用的格式
        check_mode = getattr(self, '_last_successful_check_mode', None)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(max_retries):
                try:
                    # 優先使用上次成功的檢查方式
                    if check_mode == 'llamacpp' or check_mode is None:
                        try:
                            async with session.get(f"http://localhost:{self.port}/health") as response:
                                if response.status == 200:
                                    try:
                                        data = await response.json()
                                        if data.get("status") in ["ok", "no slot available"]:
                                            self._last_successful_check_mode = 'llamacpp'
                                            return True
                                    except:
                                        # 如果解析JSON失敗，可能是SGLang格式
                                        if response.status == 200:
                                            self._last_successful_check_mode = 'sglang'
                                            return True
                        except Exception as e:
                            if check_mode == 'llamacpp':
                                print(f"[API] LlamaCpp健康檢查失敗: {e}")
                    
                    # 如果LlamaCpp格式失敗或者上次是SGLang格式，嘗試SGLang格式
                    if check_mode == 'sglang' or check_mode is None:
                        try:
                            async with session.get(f"http://localhost:{self.port}/health") as response:
                                if response.status == 200:
                                    self._last_successful_check_mode = 'sglang'
                                    return True
                        except Exception as e:
                            if check_mode == 'sglang':
                                print(f"[API] SGLang健康檢查失敗: {e}")
                    
                    # 如果到這裡還沒有返回，說明當前嘗試失敗
                    if attempt < max_retries - 1:
                        # 根據重試次數動態調整等待時間
                        wait_time = min(2 * (attempt + 1), 5)  # 最多等待5秒
                        print(f"[API] 健康檢查失敗，等待{wait_time}秒後重試 ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    
                except asyncio.TimeoutError:
                    print(f"[API] 健康檢查超時 (嘗試 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(min(2 * (attempt + 1), 5))
                except Exception as e:
                    print(f"[API] 健康檢查發生未知錯誤: {e} (嘗試 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(min(2 * (attempt + 1), 5))
        
        print("[API] 健康檢查在最大重試次數後仍然失敗")
        return False

    async def get_slots_status(self) -> str:
        """
        獲取當前在線slot的狀態，包括空閒和處理中數量。
        
        返回:
            str: 描述在線slot數量的字符串。
        """
        async def _request_slots():
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.worker_url}/health") as response:
                    return await response.json()
        
        def _check_success(data):
            return isinstance(data, dict) and data.get("status") == "ok"
        
        result = await self._retry_request(
            request_func=_request_slots,
            max_retries=3,
            timeout_seconds=10,
            error_msg="獲取slot狀態",
            success_condition=_check_success
        )
        
        if isinstance(result, dict) and not result.get("error"):
            if result.get("status") == "ok":
                slots_idle = result.get("slots_idle", "未知")
                slots_processing = result.get("slots_processing", "未知")
                return f"在線slot數量: 空閒 {slots_idle}, 處理中 {slots_processing}"
        
        # 如果請求失敗或結果不符合預期
        error_msg = result.get("error", "未知錯誤") if isinstance(result, dict) else str(result)
        return f"在線slot數量: 獲取失敗 - {error_msg}"

    async def get_ranking(self) -> List[Dict[str, Any]]:
        """
        獲取當前排名信息。
        
        返回:
            List[Dict[str, Any]]: 包含排名信息的列表，如果獲取失敗則返回包含錯誤信息的字典。
            返回格式示例：
            [
                {
                    "name": "用戶名",
                    "token_count": 1000,
                    "online_time": 3600
                }
            ]
        """
        async def _request_ranking():
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.worker_url}/rank") as response:
                    print(f"[API] 排名請求狀態碼: {response.status}")
                    data = await response.json()
                    print(f"[API] 獲取到的排名數據: {data}")
                    return data
        
        def _check_success(data):
            return isinstance(data, list)
        
        result = await self._retry_request(
            request_func=_request_ranking,
            max_retries=3,
            timeout_seconds=10,
            error_msg="獲取排名數據",
            success_condition=_check_success
        )
        
        if isinstance(result, list):
            return result
        
        # 如果請求失敗或結果不符合預期
        error_msg = result.get("error", "未知錯誤") if isinstance(result, dict) else str(result)
        return [{"error": f"獲取失敗 - {error_msg}"}]

    @staticmethod
    def parse_metrics(metrics_text: str) -> Dict[str, float]:
        """
        解析指標文本信息，轉換為字典格式。
        
        參數:
            metrics_text (str): 原始的指標文本。
        
        返回:
            Dict[str, float]: 解析後的指標字典。
        """
        metrics = {}
        is_sglang = False
        model_name = ""
        
        # 檢查是否為SGLang格式
        if "sglang:" in metrics_text:
            is_sglang = True
            logging.debug(f"[DEBUG] 檢測到SGLang格式指標")
            print(f"[DEBUG] 檢測到SGLang格式指標")
            
        for line in metrics_text.split("\n"):
            if line.startswith("#") or not line.strip():
                continue
                
            try:
                if is_sglang:
                    # 解析SGLang格式的指標
                    if "{" in line and "}" in line:
                        # 提取模型名稱
                        if "model_name=" in line:
                            model_parts = line.split("model_name=")[1].split('"')
                            if len(model_parts) > 1:
                                model_name = model_parts[1]
                                logging.debug(f"[DEBUG] 提取到SGLang模型名稱: {model_name}")
                                print(f"[DEBUG] 提取到SGLang模型名稱: {model_name}")
                                
                        # 提取指標名稱和值
                        parts = line.split(" ")
                        if len(parts) >= 2:
                            # 保留完整的鍵名，包括sglang:前綴
                            key = parts[0]
                            if "_bucket" in key:
                                # 跳過bucket指標，太多了
                                continue
                            value = float(parts[-1])
                            metrics[key] = value
                            logging.debug(f"[DEBUG] 解析SGLang指標: {key} = {value}")
                            if "token_usage" in key or "cache_hit_rate" in key or "spec_accept_length" in key:
                                print(f"[DEBUG] 解析關鍵SGLang指標: {key} = {value}")
                else:
                    # 原始LlamaCpp格式
                    key, value = line.split(" ")
                    metrics[key.split(":")[-1]] = float(value)
            except (ValueError, IndexError) as e:
                logging.debug(f"[DEBUG] 解析指標行失敗: {line}, 錯誤: {str(e)}")
                print(f"[DEBUG] 解析指標行失敗: {line}, 錯誤: {str(e)}")
                continue
                
        # 添加指標類型標記和模型名稱
        if is_sglang:
            metrics["_is_sglang"] = 1.0
            metrics["_model_name"] = model_name
            logging.debug(f"[DEBUG] SGLang指標解析完成，共{len(metrics)}個指標")
            logging.debug(f"[DEBUG] SGLang指標鍵值: {list(metrics.keys())}")
            print(f"[DEBUG] SGLang指標解析完成，共{len(metrics)}個指標")
            print(f"[DEBUG] SGLang指標鍵值: {list(metrics.keys())[:10]}...")
        else:
            metrics["_is_sglang"] = 0.0
            
        return metrics

    async def get_metrics(self) -> Dict[str, Any]:
        """
        獲取本地服務的指標信息。
        
        返回:
            Dict[str, Any]: 包含指標信息的字典，如果獲取失敗則返回錯誤信息。
        """
        async def _request_metrics():
            print(f"[DEBUG] 正在獲取指標，埠：{self.port}")
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{self.port}/metrics") as response:
                    if response.status != 200:
                        raise Exception(f"HTTP狀態碼錯誤: {response.status}")
                    metrics_text = await response.text()
                    print(f"[DEBUG] 原始指標數據:\n{metrics_text[:500]}...")  # 只列印前500個字符
                    return metrics_text
        
        result = await self._retry_request(
            request_func=_request_metrics,
            max_retries=3,
            timeout_seconds=10,
            error_msg="獲取指標數據"
        )
        
        if isinstance(result, str):
            return self.parse_metrics(result)
        
        # 如果請求失敗
        error_msg = result.get("error", "未知錯誤") if isinstance(result, dict) else str(result)
        return {"error": error_msg}

    async def start_ws_client(self, token: Optional[str] = None):
        """啟動WebSocket客戶端"""
        print("[API] 開始啟動WebSocket客戶端")
        if self.ws_client:
            print("[API] WebSocket客戶端已存在，跳過啟動")
            return
            
        print(f"[API] 創建新的WebSocket客戶端: port={self.port}, worker_url={self.worker_url}, token={'有token' if token else '無token'}")
        self.ws_client = SakuraWSClient(
            f"http://localhost:{self.port}",
            self.worker_url,
            token
        )
        print("[API] 創建WebSocket客戶端任務")
        self._ws_task = asyncio.create_task(self.ws_client.start())
        self.is_running = True
        print("[API] WebSocket客戶端啟動完成")
        return "ws_connected"

    async def start(self, tg_token: Optional[str] = None) -> bool:
        """
        啟動WebSocket服務。
        
        參數:
            tg_token (Optional[str]): Telegram Token，可選參數。
            
        返回:
            bool: 如果啟動成功則返回True，否則返回False。
        """
        try:
            # 啟動WebSocket客戶端
            await self.start_ws_client(tg_token)
            self.is_running = True
            return True
            
        except Exception as e:
            print(f"[API] 啟動失敗: {str(e)}")
            return False
            
    async def stop(self):
        """停止服務並清理資源"""
        print("[API] 開始停止API服務")
        self.is_running = False
        self.is_closing = True
        
        # 停止WebSocket客戶端
        if self.ws_client:
            print("[API] 停止WebSocket客戶端")
            try:
                await self.ws_client.stop()
                print("[API] WebSocket客戶端已停止")
            except Exception as e:
                print(f"[API] 停止WebSocket客戶端時出錯: {e}")
            self.ws_client = None
        
        print("[API] API服務停止完成")

    async def get_nodes(self, token: Optional[str] = None) -> List[str]:
        """
        獲取節點列表信息。
        
        參數:
            token (Optional[str]): 可選的認證token。
            
        返回:
            List[str]: 包含節點ID的列表，如果獲取失敗則返回包含錯誤信息的字典。
            返回格式示例：["id1", "id2", "id3"]
        """
        async def _request_nodes():
            url = f"{self.worker_url}/nodes"
            if token:
                url += f"?token={token}"
                
            print(f"[API] 請求URL: {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    print(f"[API] 節點列表請求狀態碼: {response.status}")
                    if response.status != 200:
                        raise Exception(f"HTTP狀態碼錯誤: {response.status}")
                    
                    try:
                        data = await response.json()
                        print(f"[API] 獲取到的節點列表數據: {data}")
                        return data
                    except aiohttp.ContentTypeError:
                        # 處理非JSON響應
                        text = await response.text()
                        raise Exception(f"響應不是JSON格式: {text[:200]}")  # 只顯示前200個字符
        
        def _check_success(data):
            return isinstance(data, list)
        
        result = await self._retry_request(
            request_func=_request_nodes,
            max_retries=3,
            timeout_seconds=10,
            error_msg="獲取節點列表",
            success_condition=_check_success
        )
        
        if isinstance(result, list):
            return result
        
        # 如果請求失敗或結果不符合預期
        error_msg = result.get("error", "未知錯誤") if isinstance(result, dict) else str(result)
        return [{"error": f"獲取節點列表失敗 - {error_msg}"}]
