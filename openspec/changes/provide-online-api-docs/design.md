## Context

目前的 `src/utils/proxy.py` 是一個典型的上帝物件 (God Object)，它直接實作了 aiohttp server、zhconv 轉換邏輯、JSON 遞迴處理。為了符合 SOLID，必須進行模組化拆解。

## Goals / Non-Goals

**Goals:**
- **SRP**: 每個類別只負責一件事。
- **OCP**: 增加新的 API 端點說明或新的文字轉換引擎時，不需要修改 Proxy 核心。
- **DIP**: Proxy 依賴於抽象介面而非具體實作。

## Decisions

1. **文字轉換介面化**
   - 定義 `BaseConverter` 抽象類別。
   - 實作 `ZhConvConverter` (當前使用的引擎)。

2. **文檔管理註冊制 (Registry)**
   - `DocManager` 負責持有 API 資訊清單。
   - 允許動態註冊端點說明。

3. **ProxyServer 的演進**
   - 移除所有轉換硬編碼。
   - 使用 aiohttp 提供的 `Application.on_startup` 初始化依賴。

## Risks / Trade-offs

- [Risk] 過度工程化 → [Mitigation] 保持介面簡單，僅在必要處進行抽象。
- [Trade-off] 檔案數量增加 → 這是為了換取更好的維護性。
