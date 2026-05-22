## 1. 核心邏輯重構 (SOLID)

- [x] 1.1 建立 `src/utils/converter.py` 並實作 `ZhConvConverter`
- [x] 1.2 建立 `src/utils/doc_manager.py` 並實作靜態 HTML 生成器
- [x] 1.3 重構 `src/utils/proxy.py`，移除內嵌邏輯，改用依賴注入

## 2. API 文件功能實作

- [x] 2.1 在 `DocManager` 中註冊 `/v1/chat/completions` 的繁體翻譯說明
- [x] 2.2 在 `proxy.py` 中新增 `/docs` 路由，呼叫 `DocManager` 生成頁面
- [x] 2.3 實作 `/` 自動跳轉至 `/docs`

## 3. 驗證與清理

- [x] 3.1 驗證代理功能是否依然正常（繁體轉換）
- [x] 3.2 驗證 `http://localhost:8081/docs` 是否可見且內容正確
- [x] 3.3 刪除舊的、不再使用的代碼片段
