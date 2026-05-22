import asyncio
import json
import logging
import argparse
import sys
import os
from aiohttp import web, ClientSession, ClientTimeout

# 處理導入路徑，確保作為獨立腳本執行時能找到模組
try:
    from .converter import BaseConverter, ZhConvConverter
    from .doc_manager import DocManager
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from converter import BaseConverter, ZhConvConverter
    from doc_manager import DocManager

class TranslationProxy:
    def __init__(self, target_port: int, proxy_port: int, converter: BaseConverter, doc_manager: DocManager):
        self.target_port = target_port
        self.proxy_port = proxy_port
        self.target_url = f"http://127.0.0.1:{target_port}"
        self.converter = converter
        self.doc_manager = doc_manager

    async def docs_handler(self, request):
        """回傳 API 文件的 HTML"""
        return web.Response(text=self.doc_manager.get_html(), content_type='text/html')

    async def root_redirect(self, request):
        """將根目錄重導向至文檔"""
        raise web.HTTPFound('/docs')

    async def proxy_handler(self, request):
        path = request.path
        method = request.method
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ('host', 'content-length')}
        
        body = await request.read()
        
        timeout = ClientTimeout(total=300)
        async with ClientSession(timeout=timeout) as session:
            try:
                async with session.request(
                    method, 
                    f"{self.target_url}{path}", 
                    headers=headers, 
                    params=request.query, 
                    data=body
                ) as resp:
                    
                    if "application/json" in resp.headers.get("Content-Type", ""):
                        # 處理 JSON 回應
                        content = await resp.json()
                        processed_content = self.convert_json(content)
                        return web.json_response(processed_content, status=resp.status)
                    
                    elif "text/event-stream" in resp.headers.get("Content-Type", ""):
                        # 處理 Streaming 回應
                        proxy_resp = web.StreamResponse(status=resp.status, headers=dict(resp.headers))
                        await proxy_resp.prepare(request)
                        
                        async for line in resp.content:
                            line_text = line.decode('utf-8')
                            if line_text.startswith("data: "):
                                data_str = line_text[6:].strip()
                                if data_str and data_str != "[DONE]":
                                    try:
                                        data_json = json.loads(data_str)
                                        converted_json = self.convert_json(data_json)
                                        line_text = f"data: {json.dumps(converted_json, ensure_ascii=False)}\n\n"
                                    except Exception as e:
                                        logging.debug(f"Streaming JSON parse error: {e}")
                            
                            await proxy_resp.write(line_text.encode('utf-8'))
                        
                        return proxy_resp
                    else:
                        # 其他類型直接透傳
                        content = await resp.read()
                        return web.Response(body=content, status=resp.status, headers=dict(resp.headers))
                        
            except Exception as e:
                logging.error(f"Proxy error: {e}")
                return web.json_response({"error": str(e)}, status=500)

    def convert_json(self, data):
        """遞迴轉換 JSON 中的簡體字為繁體字 (台灣正體)"""
        if isinstance(data, dict):
            return {k: self.convert_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.convert_json(i) for i in data]
        elif isinstance(data, str):
            # 使用注入的 converter 進行轉換
            return self.converter.convert(data)
        else:
            return data

    async def start(self):
        app = web.Application()
        
        # 註冊文檔與重導向路由 (優先匹配)
        app.router.add_get('/', self.root_redirect)
        app.router.add_get('/docs', self.docs_handler)
        
        # 註冊萬用代理路由
        app.router.add_route('*', '/{tail:.*}', self.proxy_handler)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.proxy_port)
        await site.start()
        logging.info(f"Proxy started: http://0.0.0.0:{self.proxy_port} -> {self.target_url}")
        logging.info(f"API Documentation available at: http://localhost:{self.proxy_port}/docs")
        
        # 保持運行
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sakura Translation Proxy (SOLID)")
    parser.add_argument("--target-port", type=int, required=True)
    parser.add_argument("--proxy-port", type=int, required=True)
    parser.add_argument("--lan-ip", type=str, default="127.0.0.1")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 初始化依賴
    converter = ZhConvConverter()
    doc_manager = DocManager(args.target_port, args.proxy_port, args.lan_ip)
    
    # 啟動代理伺服器
    proxy = TranslationProxy(args.target_port, args.proxy_port, converter, doc_manager)
    try:
        asyncio.run(proxy.start())
    except KeyboardInterrupt:
        pass
