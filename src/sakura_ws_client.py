import asyncio
import aiohttp
import yarl
import os
import json
from typing import Optional, Set, Dict, Any

class SakuraWSClient:
    def __init__(self, local_url: str, worker_url: str, token: Optional[str] = None):
        print(f"[WS] 初始化WebSocket客戶端: local_url={local_url}, worker_url={worker_url}, token={'有token' if token else '無token'}")
        self.local_url = local_url
        self.worker_url = worker_url
        self.token = token
        self.is_closing = False
        self.tasks = set()
        self._ws = None
        self._current_loop = None

    async def _do_request(self, req: Dict[str, Any], session: aiohttp.ClientSession) -> tuple[bytes, int]:
        """處理HTTP請求"""
        try:
            if req.get("type") == "GET":
                async with session.get(self.local_url + req["path"]) as response:
                    return await response.read(), response.status
            elif req.get("type") == "POST":
                async with session.post(self.local_url + req["path"], data=req["data"], headers={"Content-Type": "application/json"}) as response:
                    return await response.read(), response.status
        except aiohttp.ClientError as e:
            print(f"HTTP Client Error: {e}")
            return b'', 503
        except Exception as e:
            print(f"Unexpected Error: {e}")
            return b'', 500

    async def _handle_request(self, ws: aiohttp.ClientWebSocketResponse, req: Dict[str, Any], session: aiohttp.ClientSession):
        """處理WebSocket請求"""
        if self.is_closing:
            return
            
        data = b''
        status = 500

        try:
            data, status = await self._do_request(req, session)
        except Exception as e:
            print(f"Request failed: {e}")

        await ws.send_json({
            "id": req["id"],
            "status": status,
            "data": data.decode('utf-8', errors='replace') if data else ""
        })

    async def stop(self):
        """停止WebSocket客戶端"""
        print("[WS] 開始停止WebSocket客戶端")
        self.is_closing = True
        
        # 取消所有待處理任務
        if hasattr(self, 'tasks'):
            for task in self.tasks:
                task.cancel()
        
        if self._ws and not self._ws.closed:
            await self._ws.close()
        
        print("[WS] WebSocket客戶端停止完成")

    async def start(self):
        """啟動WebSocket客戶端"""
        self._current_loop = asyncio.get_running_loop()
        
        while not self.is_closing:
            try:
                # 構建WebSocket URL
                ws_url = self.worker_url.replace('http://', 'ws://').replace('https://', 'wss://')
                uri = yarl.URL(f"{ws_url}/ws")
                uri_with_token_removed = str(uri)
                if self.token:
                    uri = uri.with_query({"token": self.token})
                    uri_with_token_removed = str(uri).replace(self.token[4:], "****")
                
                print(f"[WS] 嘗試連接到WebSocket伺服器: {uri_with_token_removed}")
                
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(uri, heartbeat=5.0, timeout=15.0) as ws:
                        self._ws = ws
                        print("[WS] 已成功連接到伺服器")
                        try:
                            async for msg in ws:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    if not self.is_closing:
                                        req = json.loads(msg.data)
                                        task = asyncio.create_task(
                                            self._handle_request(ws, req, session)
                                        )
                                        self.tasks.add(task)
                                        task.add_done_callback(self.tasks.discard)
                        except asyncio.CancelledError:
                            print("[WS] 連接被主動取消")
                            break
                        
            except asyncio.CancelledError:
                print("[WS] 連接任務被取消")
                break
            except Exception as e:
                if not self.is_closing:
                    print(f"[WS] 連接錯誤: {e}, 5秒後重試...")
                    await asyncio.sleep(5)
                else:
                    break
                
