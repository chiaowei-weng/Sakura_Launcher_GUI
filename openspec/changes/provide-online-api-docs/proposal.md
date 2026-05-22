## Why

目前 Sakura Launcher GUI 的 API 代理邏輯與轉換邏輯緊密耦合，且缺乏視覺化的 API 文件。採用 SOLID 原則重構，不僅能提供線上的 API 文件，更能將「網路轉發」、「文字轉換」與「文檔渲染」三個職責分離，使程式碼更易於維護與擴展。

## What Changes

- **職責分離 (SRP)**：
    - 將 `proxy.py` 中的簡繁轉換邏輯抽離至 `src/utils/converter.py`。
    - 建立 `src/utils/doc_manager.py` 專門負責生成與管理 API 文檔內容。
- **依賴反轉 (DIP)**：
    - `TranslationProxy` 將透過構造函數接收 `Converter` 與 `DocManager` 的實例。
- **功能新增**：
    - 在代理伺服器中提供 `/docs` 路由，顯示由 `DocManager` 生成的繁體中文 API 說明頁。

## Capabilities

### New Capabilities
- `online-api-docs`: 提供符合 SOLID 原則的模組化 API 參考文檔。
- `text-conversion-service`: 獨立的文字轉換抽象層。

## Impact

- `src/utils/proxy.py`: 程式碼將被大幅簡化，轉變為單純的路由轉發器。
- `src/utils/converter.py` & `src/utils/doc_manager.py`: 新增的邏輯單元。
