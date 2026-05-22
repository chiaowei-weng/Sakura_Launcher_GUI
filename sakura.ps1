param (
    [Parameter(Mandatory=$false, Position=0)]
    [ValidateSet("start", "stop", "gui", "status", "list")]
    [string]$Action = "gui",

    [Parameter(Mandatory=$false, Position=1)]
    [string]$Preset = "default"
)

# 設定路徑
$VENV_PYTHON = ".\venv\Scripts\python.exe"
if (-not (Test-Path $VENV_PYTHON)) {
    $VENV_PYTHON = "python"
}

function Show-Help {
    Write-Host "`nSakura Launcher 台灣在地化管理腳本" -ForegroundColor Cyan
    Write-Host "用法: .\sakura.ps1 [action] [preset]"
    Write-Host "`n可用動作:"
    Write-Host "  start   - 背景啟動服務與繁體轉換代理 (預設集: default)"
    Write-Host "  stop    - 停止所有執行中的服務與代理"
    Write-Host "  gui     - 開啟繁體中文設定介面"
    Write-Host "  status  - 檢查服務運行狀態 (含代理埠口)"
    Write-Host "  list    - 列出所有可用的預設集"
}

switch ($Action) {
    "start" {
        Write-Host "🚀 正在背景啟動 Sakura 翻譯服務與繁體代理 (預設集: $Preset)..." -ForegroundColor Cyan
        & $VENV_PYTHON main.py --run-preset $Preset
        Write-Host "💡 請將翻譯軟體連線至埠口 8081 以取得繁體中文輸出。" -ForegroundColor Magenta
    }
    "stop" {
        Write-Host "🛑 正在停止 Sakura 翻譯服務與代理..." -ForegroundColor Yellow
        Stop-Process -Name "llama-server" -Force -ErrorAction SilentlyContinue
        # 停止運行 proxy.py 的 python 進程
        Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%proxy.py%'" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        if ($?) {
            Write-Host "✅ 服務已成功停止。" -ForegroundColor Green
        } else {
            Write-Host "ℹ️ 未發現正在執行的服務。" -ForegroundColor Gray
        }
    }
    "gui" {
        Write-Host "🎨 正在啟動 Sakura Launcher GUI..." -ForegroundColor Cyan
        Start-Process $VENV_PYTHON "main.py"
    }
    "status" {
        $proc = Get-Process -Name "llama-server" -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "🟢 服務正在運行中 (PID: $($proc.Id))" -ForegroundColor Green
            Write-Host "   監聽埠口請參考預設集設定。"
        } else {
            Write-Host "🔴 服務目前已停止。" -ForegroundColor Red
        }
    }
    "list" {
        Write-Host "📋 可用的預設集清單：" -ForegroundColor Cyan
        & $VENV_PYTHON main.py --list-presets
    }
    default {
        Show-Help
    }
}
