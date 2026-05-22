# Sakura Launcher GUI 用戶手冊

## 0. 簡介

Sakura Launcher GUI 是一個用於啟動和管理SakuraLLM相關任務的圖形界面工具（當然，也可以用來啟動其他的llama.cpp支持的LLM）。

本手冊將詳細指導您如何使用該工具的各項功能，包括啟動llama-server、運行llama-batched-bench、下載資源、管理配置、共享等。

## 1. 快速上手

這一節將指導你如何快速上手使用Sakura Launcher GUI。

雙擊打開程序，點擊左邊的`下載`按鈕。

認真閱讀說明，選擇適合你的顯卡的Sakura版本，並點擊`下載`按鈕進行下載。
你可以在`下載進度`中查看下載進度。

<div align=center><img src="assets/image.png" width="540px"></div>

然後，切換到`llama.cpp下載`界面，點擊`下載`按鈕，認真閱讀說明，並點擊`下載`按鈕進行下載。

返回`啟動`界面，直接點擊`啟動`。

如果遇到網絡問題導致下載失敗，你可以：
1. 清理已下載的失敗文件後重新下載
2. 手動下載模型文件和llama.cpp，然後在程序中設置對應路徑

現在，你可以在需要使用sakura的工具，如[輕小說機翻機器人](https://books.fishhawk.top/)、[GalTransl](https://github.com/xd2333/GalTransl)、[BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)中填入你設置好的地址開始使用了。

如果你遇到了警告彈窗，請按照彈窗提示的解決方案進行操作。

***如果你使用的是7000系AMD CPU和AMD獨立顯卡，有概率會出現錯誤地啟動在核顯上的情況。如果你遇到這個問題，請查看下方的"2.1.2 GPU設置"這一節。***

## 2. 高級設置

### 2.1 啟動頁面高級設置

#### 2.1.1 模型參數和自動配置

- 對於不了解模型參數的用戶，可以點擊`自動配置`按鈕，程序會根據你選擇的模型，自動設置合適的參數。自動配置**僅支持**存在於`下載`頁面中的模型。

- 上下文長度（-c）：設置模型的上下文長度，範圍256-131072
  - 對於即時翻譯任務，如[LunaTranslator](https://github.com/HIllya51/LunaTranslator)，每個線程的上下文長度不應當小於512
  - 對於翻譯工具，如[GalTransl](https://github.com/xd2333/GalTransl)或[輕小說機翻機器人](https://books.fishhawk.top/)，每個線程的上下文長度不應當小於1536
- 並行工作線程數（-np）：設置並行處理的線程數，範圍1-32
  - 設置線程大於1時，context數量將會平均分配給每個線程。程序會自動計算實際上每個線程的上下文長度，並顯示在UI上，請注意查看
    - <div align=left><img src="https://github.com/user-attachments/assets/df59bffd-a29e-4dc3-94f6-a0d394d2e09d" width="540px"></div>


#### 2.1.2 GPU設置和自定義命令
- GPU選擇：從下拉菜單中選擇要使用的GPU
  - 會自動識別所有存在的NVIDIA、AMD顯卡，並列表顯示。
    - 對於N卡，直接選擇你需要的GPU即可。如果需要多顯卡，請選擇`自動`。如果需要指定某些顯卡，請在下方的自定義命令中輸入： `CUDA_VISIBLE_DEVICES=a,b,c %cmd%`，其中a,b,c為顯卡序號，從0開始，%cmd%為GUI設置的啟動命令。
    - 對於A卡，由於缺少類似nvidia-smi的工具，獲取的顯卡順序可能會出錯。如果llamacpp啟動的顯卡不正確，如啟動在了核顯上，請在下方的自定義命令中輸入： `HIP_VISIBLE_DEVICES=x %cmd%`，其中x為顯卡序號，可以嘗試0、1，%cmd%為GUI設置的啟動命令。
- 自定義命令：
  - `%cmd%`會被替換為GUI生成的完整啟動命令，
  - `%cmd_raw%` 會替換成GUI生成的命令和模型選項，但不包括其他選項。

#### 2.1.3 其他啟動選項
- **啟用 Flash Attention (-fa)**：加速模型運算並減少顯存佔用。
- **啟用 --no-mmap**：不使用內存映射加載模型，這在某些磁碟效能較差或網絡驅動器上能提高載入穩定性。
- **後臺執行**：勾選後，啟動服務時將不再彈出新的終端機視窗，服務直接在背景執行。當您關閉啟動器時，這些背景服務也會自動被終止。

- **繁體中文服務**：本專案專為台灣用戶優化，啟動後會自動開啟繁體代理伺服器（預設埠口 8081）。該服務會確保翻譯結果完全符合 **台灣繁體中文慣用語（如：軟體、人工智慧）**。請務必連線至代理埠口以獲得最佳翻譯品質。

#### 2.1.4 配置預設與命令行啟動
- **配置預設**：您可以將目前所有的參數設定儲存為預設集，方便快速切換。
- **命令行啟動**：
    - 您可以在不啟動 GUI 的情況下，透過命令行背景啟動特定的預設配置：
      `python main.py --run-preset "您的預設名稱"`
    - 使用 `python main.py --list-presets` 可以查看目前所有已儲存的預設。
- **管理腳本**：專案根目錄提供了 `sakura.ps1` (PowerShell) 與 `manage.bat` (Batch)，可用於一鍵啟動/停止服務或開啟 GUI。

#### 2.1.5 性能測試
- 點擊`性能測試`按鈕，程序會自動運行llama-batched-bench，並顯示測試結果。
- 其中，`Prompt數量`為測試的Prompt數量，`生成文本數量`為每個Prompt生成的文本數量，`並行Prompt數量`為並行處理的Prompt數量，也就是線程數。一般推薦使用默認配置的參數，並查看最終的S_TG輸出，以確定合適的參數。


### 2.2 共享
- 上線：開始共享
- 下線：停止共享
- 刷新在線數量：刷新當前在線的slot數量和狀態
- 連結：自定義自行部署的worker url（不推薦）
- 令牌：設置共享的令牌，用於累計共享信息，參加在線排行榜 （在當前版本中1.1.0中，由於服務端想逛功能尚未開發，所以**無法使用**）
- 本地數據統計：查看本地共享數據，包含所有的請求數據，未區分本地使用和共享
- share工具的[API](https://github.com/PiDanShouRouZhouXD/Sakura_Launcher_GUI/blob/main/src/sakura_share_api.py)是與GUI完全解耦的，並另外提供了[CLI工具](https://github.com/PiDanShouRouZhouXD/Sakura_Launcher_GUI/blob/main/src/sakura_share_cli.py)，如有需要，可以脫離GUI使用。
- 關於共享功能的說明，請查看：[sakura-share](https://github.com/1PercentSync/sakura-share)

### 2.3 設置頁面功能
- 記住窗口位置和大小：啟動器會記住上次關閉時的窗口位置和大小
- 記住高級設置狀態：記住啟動頁面中高級設置面板的展開/摺疊狀態
- 關閉 GPU 能力檢測：關閉啟動時的GPU顯存檢查功能
- 關閉每線程上下文長度檢查：關閉對每個線程最小上下文長度的檢查
- 模型列表排序：可選擇按"修改時間"、"文件名"或"文件大小"對模型列表進行排序
- llama.cpp文件夾：可手動指定llama.cpp的安裝路徑
- 模型搜索路徑：可添加多個模型搜索路徑，每行一個路徑（默認包含當前目錄），將會遍歷所有子目錄

### 2.4 配置預設功能
- 預設可以上下移動調整順序，支持刪除操作
- 長按向上/向下箭頭可以快速移動預設

### 2.5 日誌功能
- 程序運行過程中的重要信息會記錄在日誌中
- 可以在設置頁面的"日誌輸出"標籤頁查看
- 支持清空日誌功能

### 2.6 自動更新
- 程序會自動檢查新版本
- 可以在設置頁面手動檢查更新
- 發現新版本時會提示下載更新

## 3. 技術支持

如需進一步幫助或報告問題，請訪問以下項目地址：

模型相關：

- SakuraLLM: https://github.com/SakuraLLM/SakuraLLM

GUI相關：

- Sakura Launcher GUI: https://github.com/PiDanShouRouZhouXD/Sakura_Launcher_GUI

您可以在這些項目的Issues頁面提出問題或建議，或者查看已有的討論以尋找解決方案。
