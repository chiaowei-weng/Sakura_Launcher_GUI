from typing import List, Dict, Any

class DocManager:
    """管理 API 文件與 HTML 渲染的類別"""
    
    def __init__(self, target_port: int, proxy_port: int, lan_ip: str = "127.0.0.1"):
        self.target_port = target_port
        self.proxy_port = proxy_port
        self.lan_ip = lan_ip
        self.endpoints: List[Dict[str, Any]] = []
        self._init_default_docs()

    def register_endpoint(self, path: str, method: str, description: str, payload_example: str = None, response_example: str = None):
        """註冊一個新的 API 端點說明"""
        self.endpoints.append({
            "path": path,
            "method": method,
            "description": description,
            "payload_example": payload_example,
            "response_example": response_example
        })

    def _init_default_docs(self):
        """初始化預設的端點說明"""
        self.register_endpoint(
            path="/v1/chat/completions",
            method="POST",
            description="OpenAI 相容的聊天補全介面。翻譯結果將自動轉換為台灣繁體中文。",
            payload_example="""{
  "model": "sakura",
  "messages": [
    {"role": "system", "content": "你是一個翻譯模型。"},
    {"role": "user", "content": "翻譯：こんにちは"}
  ],
  "stream": false
}""",
            response_example="""{
  "choices": [
    {
      "message": {
        "content": "翻譯：你好"
      }
    }
  ]
}"""
        )

        self.register_endpoint(
            path="/v1/chat/completions (多行範例)",
            method="POST",
            description="針對長篇輕小說段落，支援多行換行符號 `\\n`。建議在 messages 中使用正確的格式引導。",
            payload_example="""{
  "model": "sakura",
  "messages": [
    {"role": "system", "content": "你是一個輕小說翻譯模型。"},
    {"role": "user", "content": "將下面的日文文本翻譯成中文：\\n\\n「お兄ちゃん、起きて！」\\n\\n妹の声が響く。"}
  ]
}""",
            response_example="""{
  "choices": [
    {
      "message": {
        "content": "「哥哥，起床啦！」\\n\\n妹妹的聲音響起。"
      }
    }
  ]
}"""
        )

    def get_html(self) -> str:
        """生成 API 文件的 HTML 字串"""
        endpoint_html = ""
        for ep in self.endpoints:
            payload_section = f"<h6>請求範例：</h6><pre><code>{ep['payload_example']}</code></pre>" if ep['payload_example'] else ""
            response_section = f"<h6>回應範例：</h6><pre><code>{ep['response_example']}</code></pre>" if ep['response_example'] else ""
            
            endpoint_html += f"""
            <div class="card mb-4">
                <div class="card-header">
                    <span class="badge bg-primary">{ep['method']}</span> <code>{ep['path']}</code>
                </div>
                <div class="card-body">
                    <p class="card-text">{ep['description']}</p>
                    <div class="row">
                        <div class="col-md-6">
                            {payload_section}
                        </div>
                        <div class="col-md-6">
                            {response_section}
                        </div>
                    </div>
                </div>
            </div>
            """

        return f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sakura 翻譯代理 API 文件</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background-color: #f8f9fa; padding-top: 50px; }}
        .container {{ max-width: 900px; }}
        pre {{ background-color: #e9ecef; padding: 15px; border-radius: 5px; font-size: 0.85em; }}
        .badge {{ font-size: 0.9em; }}
        .card-header {{ font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mb-4">🌸 Sakura 翻譯代理</h1>
        <div class="alert alert-info shadow-sm">
            <strong>目前連線設定：</strong><hr>
            - 外部存取位址：<code>http://{self.lan_ip}:{self.proxy_port}</code> (區域網路)<br>
            - 本機存取位址：<code>http://localhost:{self.proxy_port}</code><br>
            - 目標服務位址：<code>http://127.0.0.1:{self.target_port}</code> (本機隔離)
        </div>
        
        <div class="card mb-4 border-0 shadow-sm">
            <div class="card-body">
                <h5 class="card-title">繁體中文轉換說明</h5>
                <p class="card-text text-secondary">
                    本代理伺服器已內建 <strong>zhconv</strong> 轉換引擎。
                    所有發往本機 <code>llama-server</code> 的請求，其回傳內容（包含 Streaming）
                    都會被即時攔截並轉換為 <strong>台灣繁體中文 (zh-tw)</strong>，並修正慣用語（如：軟體、埠口、執行緒）。
                </p>
            </div>
        </div>

        <h3 class="mt-5 mb-3">API 端點說明</h3>
        {endpoint_html}

        <footer class="mt-5 mb-5 text-muted text-center">
            <small>由 Sakura Launcher GUI 自動生成</small>
        </footer>
    </div>
</body>
</html>
        """
