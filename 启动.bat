# ============================================================
# 校园互助平台 · 一键启动脚本（双击运行）
# 作用：检查虚拟环境 → 启动后端服务(127.0.0.1:8000) → 自动打开浏览器
# 说明：全部在 D 盘项目目录内运行，不占用 C 盘；GLM Key 可选，
#       未设置时 AI 自动降级规则引擎，功能完整可用（见 .env.example）
# ============================================================

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host ""
Write-Host "==== 校园互助平台 一键启动 ====" -ForegroundColor Cyan

# 1) 虚拟环境检查（首次运行自动创建，依赖已在 requirements.txt 中）
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "[1/3] 未检测到虚拟环境，正在创建（仅首次）..." -ForegroundColor Yellow
    python -m venv .venv
    & $venvPy -m pip install -r requirements.txt --no-cache-dir
} else {
    Write-Host "[1/3] 虚拟环境就绪 (.venv)"
}

# 2) 端口检查：8000 被占用说明服务已在跑，直接开浏览器
$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    Write-Host "[2/3] 端口 8000 已有服务在运行，跳过启动" -ForegroundColor Yellow
} else {
    Write-Host "[2/3] 启动后端服务 (uvicorn, 127.0.0.1:8000)..." -ForegroundColor Green
    Start-Process -FilePath $venvPy `
        -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory $root -WindowStyle Minimized
    # 等待健康检查通过（最多 20 秒）
    $ok = $false
    foreach ($i in 1..40) {
        Start-Sleep -Milliseconds 500
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200) { $ok = $true; break }
        } catch { }
    }
    if (-not $ok) {
        Write-Host "    服务启动超时，请查看弹出的后端窗口报错信息" -ForegroundColor Red
        Read-Host "按回车键退出"
        exit 1
    }
}

# 3) 打开浏览器（管理端 + 学生端 + 适老端，一次全开）
Write-Host "[3/3] 打开浏览器..." -ForegroundColor Green
Start-Process "http://127.0.0.1:8000/admin/"
Start-Process "http://127.0.0.1:8000/app/"
Start-Process "http://127.0.0.1:8000/elder/"

Write-Host ""
Write-Host "==== 启动完成 ====" -ForegroundColor Cyan
Write-Host ""
Write-Host "  管理端  http://127.0.0.1:8000/admin/   账号 admin / admin123"
Write-Host "  学生端  http://127.0.0.1:8000/app/     账号 stu01 / 123456（ stu02 同密码）"
Write-Host "  适老端  http://127.0.0.1:8000/elder/   账号 stu02 / 123456"
Write-Host ""
Write-Host "  停止服务：关闭最小化的后端窗口，或任务管理器结束 python 进程"
Write-Host "  （本窗口可以关闭，不影响服务运行）"
Write-Host ""
Read-Host "按回车键关闭本窗口"
