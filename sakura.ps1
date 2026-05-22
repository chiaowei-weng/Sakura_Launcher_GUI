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
    Write-Host "`nSakura Launcher 管理腳本" -ForegroundColor Cyan
    Write-Host "用法: .\sakura.ps1 [action] [preset]"
    Write-Host "`n可用動作:"
    Write-Host "  start   - 使用指定的預設集在背景啟動服務 (預設: default)"
    Write-Host "  stop    - 停止所有執行中的 llama-server 服務"
    Write-Host "  gui     - 開啟圖形化介面進行詳細設定 (預設動作)"
    Write-Host "  status  - 檢查服務目前的運行狀態"
    Write-Host "  list    - 列出所有可用的預設集"
    Write-Host "`n範例:"
    Write-Host "  .\sakura.ps1 start"
    Write-Host "  .\sakura.ps1 stop"
    Write-Host "  .\sakura.ps1 gui"
}

switch ($Action) {
    "start" {
        Write-Host "🚀 正在背景啟動 Sakura 翻譯服務 (預設集: $Preset)..." -ForegroundColor Cyan
        & $VENV_PYTHON main.py --run-preset $Preset
    }
    "stop" {
        Write-Host "🛑 正在停止 Sakura 翻譯服務..." -ForegroundColor Yellow
        Stop-Process -Name "llama-server" -Force -ErrorAction SilentlyContinue
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
