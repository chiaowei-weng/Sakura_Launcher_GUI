import asyncio
import argparse
import logging
import os
import signal
import sys
from typing import Optional

# 將項目根目錄添加到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sakura_share_api import SakuraShareAPI

async def main():
    parser = argparse.ArgumentParser(description="Sakura Share CLI")
    parser.add_argument("--port", type=int, required=True, help="Local server port")
    parser.add_argument("--worker-url", type=str, default="https://sakura-share.one", required=False, help="Worker URL, default is https://sakura-share.one")
    parser.add_argument("--tg-token", type=str, help="Telegram token (optional)")
    parser.add_argument("--action", choices=["start", "stop", "status", "metrics", "ranking", "nodes"], required=True, help="Action to perform")
    parser.add_argument("--mode", choices=["ws"], default="ws", help="Operation mode: ws (WebSocket)")

    args = parser.parse_args()

    api = SakuraShareAPI(args.port, args.worker_url)

    if args.action == "start":
        await start_sharing(api, args.tg_token)
    elif args.action == "stop":
        await stop_sharing(api)
    elif args.action == "status":
        await get_status(api)
    elif args.action == "metrics":
        await get_metrics(api)
    elif args.action == "ranking":
        await get_ranking(api)
    elif args.action == "nodes":
        await get_nodes(api, args.tg_token)

async def start_sharing(api: SakuraShareAPI, tg_token: str):
    stop_event = asyncio.Event()
    
    def signal_handler():
        print("接收到停止信號，正在準備停止分享...")
        stop_event.set()

    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
    else:
        signal.signal(signal.SIGINT, lambda s, f: signal_handler())
        signal.signal(signal.SIGTERM, lambda s, f: signal_handler())

    try:
        if await api.start(tg_token):
            print("成功啟動分享")
            
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=600)
                except asyncio.TimeoutError:
                    pass
        else:
            print("啟動失敗，請檢查配置和網絡連接")
    except Exception as e:
        print(f"啟動失敗: {str(e)}")
    finally:
        print("正在停止分享...")
        api.stop()
        await api.take_node_offline()
        print("已成功停止分享")

async def stop_sharing(api: SakuraShareAPI):
    try:
        api.stop()
        if await api.take_node_offline():
            print("已停止分享")
        else:
            print("停止分享失敗")
    except Exception as e:
        print(f"停止分享時發生錯誤: {str(e)}")

async def get_status(api: SakuraShareAPI):
    status = await api.get_slots_status()
    print(status)

async def get_metrics(api: SakuraShareAPI):
    metrics = await api.get_metrics()
    if "error" in metrics:
        print(f"獲取指標失敗: {metrics['error']}")
    else:
        for key, value in metrics.items():
            print(f"{key}: {value}")

async def get_ranking(api: SakuraShareAPI):
    ranking = await api.get_ranking()
    if "error" in ranking:
        print(f"獲取排名失敗: {ranking['error']}")
    else:
        for username, count in sorted(ranking.items(), key=lambda item: int(item[1]), reverse=True):
            print(f"{username}: {count}")

async def get_nodes(api: SakuraShareAPI, token: Optional[str] = None):
    """獲取並顯示節點列表"""
    nodes = await api.get_nodes(token)
    if isinstance(nodes, list) and len(nodes) > 0 and "error" in nodes[0]:
        print(f"獲取節點列表失敗: {nodes[0]['error']}")
    else:
        print("節點列表:")
        for node in nodes:
            print(f"節點信息: {node}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
