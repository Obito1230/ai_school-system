# ============================================================
# 校园互助平台 · 停止服务脚本（双击运行）
# 作用：结束本项目占用的 uvicorn / python 服务进程（端口 8000）
# ============================================================

$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $pids = $conn | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($p -and $p.ProcessName -match "python") {
            Write-Host "停止服务进程: $($_ = $p.ProcessName) (PID $procId)" -ForegroundColor Yellow
            Stop-Process -Id $procId -Force
        } else {
            Write-Host "端口 8000 被非本项目进程占用 (PID $procId, $($p.ProcessName))，未处理" -ForegroundColor Red
        }
    }
    Write-Host "服务已停止。" -ForegroundColor Green
} else {
    Write-Host "端口 8000 没有运行中的服务。" -ForegroundColor Gray
}
Read-Host "按回车键关闭"
