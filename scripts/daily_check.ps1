#Requires -Version 5.1
<#
.SYNOPSIS
업비트 시그널 프로그램 데일리 체크 (운영 가이드 §3)

.DESCRIPTION
운영 4축(안정성/시그널/텔레그램/settings) 점검 → JSONL append → 텔레그램 요약 전송.
매일 1회 실행 (Task Scheduler 또는 수동).

.PARAMETER NoTelegram
텔레그램 요약 전송 스킵 (콘솔/JSONL만)

.PARAMETER NoConsole
콘솔 출력 스킵 (Task Scheduler 자동 실행 시 유용)

.EXAMPLE
.\daily_check.ps1
.\daily_check.ps1 -NoTelegram
.\daily_check.ps1 -NoConsole       # Task Scheduler용
#>

param(
    [switch]$NoTelegram,
    [switch]$NoConsole
)

$ErrorActionPreference = "Continue"
$PROJECT = "C:\Users\user3\Desktop\VibeCoding\signal-up"
$SETTINGS = "$PROJECT\state\settings.json"
$SIGNAL_HISTORY = "$PROJECT\state\signal_history.jsonl"
$DAILY_LOG = "$PROJECT\state\daily_check.jsonl"

$now = Get-Date
$today_str = $now.ToString("yyyy-MM-dd")
$yest_str = $now.AddDays(-1).ToString("yyyy-MM-dd")
$ts = $now.ToString("yyyy-MM-ddTHH:mm:sszzz")

function Write-Line {
    param([string]$text, [string]$color = "White")
    if (-not $NoConsole) { Write-Host $text -ForegroundColor $color }
}

Write-Line "`n=== $today_str $($now.ToString('HH:mm')) Daily Check ===" "Cyan"

# A. 데몬 alive
$daemon_alive = $false
$daemon_pid = $null
$daemon_mem = $null
$daemon_uptime_min = $null
$listen = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    $proc = Get-Process -Id $listen[0].OwningProcess -ErrorAction SilentlyContinue
    if ($proc) {
        $daemon_alive = $true
        $daemon_pid = $proc.Id
        $daemon_mem = [math]::Round($proc.WorkingSet64 / 1MB, 1)
        $daemon_uptime_min = [int]((Get-Date) - $proc.StartTime).TotalMinutes
        Write-Line "[A] alive PID $daemon_pid, $daemon_mem MB, uptime $daemon_uptime_min min" "Green"
    }
}
if (-not $daemon_alive) {
    Write-Line "[A] 데몬 죽음 - 재기동 필요" "Red"
}

# B. 어제 시그널 + 마켓 분포
$signals_count = 0
$top_markets_str = ""
if (Test-Path $SIGNAL_HISTORY) {
    $yest_lines = Get-Content $SIGNAL_HISTORY | Where-Object { $_ -match "`"timestamp`":`"$yest_str" }
    $signals_count = $yest_lines.Count
    if ($signals_count -gt 0) {
        $market_groups = $yest_lines | ForEach-Object { ($_ | ConvertFrom-Json).market } | Group-Object | Sort-Object Count -Descending | Select-Object -First 5
        $top_markets_str = ($market_groups | ForEach-Object { "$($_.Name)x$($_.Count)" }) -join ", "
    }
}
Write-Line "[B] 어제($yest_str) 시그널 $signals_count 건 $top_markets_str"

# C. 텔레그램 토큰 sanity
$telegram_status = 0
$s = $null
try {
    $s = Get-Content $SETTINGS -Raw -Encoding utf8 | ConvertFrom-Json
    $r = Invoke-WebRequest -Uri "https://api.telegram.org/bot$($s.telegram_bot_token)/getMe" -UseBasicParsing -TimeoutSec 10
    $telegram_status = $r.StatusCode
    Write-Line "[C] getMe $telegram_status" "Green"
} catch {
    $telegram_status = -1
    Write-Line "[C] getMe 실패: $($_.Exception.Message)" "Red"
}

# D. 백업 누적
$baks_all = Get-ChildItem "$SETTINGS.bak*" -ErrorAction SilentlyContinue
$baks_total = if ($baks_all) { $baks_all.Count } else { 0 }
$baks_added = if ($baks_all) { ($baks_all | Where-Object { $_.LastWriteTime -gt $now.AddDays(-1) }).Count } else { 0 }
Write-Line "[D] 백업 누적 $baks_total 개 (어제 추가 $baks_added)"

# JSONL append
$entry = [ordered]@{
    date = $today_str
    timestamp = $ts
    daemon_alive = $daemon_alive
    daemon_pid = $daemon_pid
    daemon_memory_mb = $daemon_mem
    daemon_uptime_minutes = $daemon_uptime_min
    yesterday = $yest_str
    signals_count = $signals_count
    signals_top_markets = $top_markets_str
    telegram_status = $telegram_status
    backups_total = $baks_total
    backups_added = $baks_added
}
$line = $entry | ConvertTo-Json -Compress -Depth 5
Add-Content -Path $DAILY_LOG -Value $line -Encoding utf8
Write-Line "[JSONL] $DAILY_LOG"

# 텔레그램 데일리 요약 전송
if (-not $NoTelegram -and $s -and $telegram_status -eq 200) {
    $a_label = if ($daemon_alive) { "OK PID $daemon_pid, ${daemon_mem}MB, ${daemon_uptime_min}min" } else { "DOWN" }
    $c_label = if ($telegram_status -eq 200) { "OK" } else { "FAIL($telegram_status)" }
    $b_label = "$signals_count 건"
    if ($top_markets_str) { $b_label += "  $top_markets_str" }

    $msg = @(
        "[signal-up Daily $today_str]"
        "Daemon: $a_label"
        "Signals(${yest_str}): $b_label"
        "Telegram: $c_label"
        "Backups: $baks_total (+$baks_added)"
    ) -join "`n"

    $body = @{ chat_id = $s.telegram_chat_id; text = $msg } | ConvertTo-Json
    try {
        Invoke-WebRequest -Uri "https://api.telegram.org/bot$($s.telegram_bot_token)/sendMessage" -Method POST -Body $body -ContentType "application/json; charset=utf-8" -UseBasicParsing -TimeoutSec 10 | Out-Null
        Write-Line "[Telegram] 데일리 요약 전송 완료" "Green"
    } catch {
        Write-Line "[Telegram] 전송 실패: $($_.Exception.Message)" "Red"
    }
}

Write-Line "=== 완료 ===" "Cyan"
