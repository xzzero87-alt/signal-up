# strategy_matrix.ps1 — 전략 비교 매트릭스 (5전략 x 5구간 x 3마켓 = 75회)
# 설계: 시그널 프로그램/plans/strategy-comparison-matrix.md
# 실행: cd C:\Users\user3\Desktop\VibeCoding\signal-up
#       powershell -ExecutionPolicy Bypass -File scripts\strategy_matrix.ps1
# PS5.1에서 네이티브 명령 stderr(2>&1)와 EAP Stop이 충돌하므로 Continue + 명시적 exit code 체크
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:NO_COLOR = "1"
$env:PYTHONIOENCODING = "utf-8"

$Markets    = @("KRW-BTC", "KRW-ETH", "KRW-XRP")
$Strategies = @("v1", "v2", "v3", "v4", "v5")
$Periods    = @(
    @{ Name = "FULL";   From = "2025-01-01"; To = "2026-05-31" },
    @{ Name = "2025H1"; From = "2025-01-01"; To = "2025-06-30" },
    @{ Name = "2025H2"; From = "2025-07-01"; To = "2025-12-31" },
    @{ Name = "2026Q1"; From = "2026-01-01"; To = "2026-03-31" },
    @{ Name = "2026Q2"; From = "2026-04-01"; To = "2026-05-31" }
)

$OutDir = "reports\compare"
$RawDir = Join-Path $OutDir "raw"
New-Item -ItemType Directory -Force -Path $RawDir | Out-Null

# ── 0) 캔들 확보 (2025-01 parquet 없으면 전체 다운로드) ──────────────────
foreach ($m in $Markets) {
    $probe = "data\candles\$m\60\2025-01.parquet"
    if (Test-Path $probe) {
        Write-Host "[skip ] $m 캔들 있음"
    } else {
        Write-Host "[fetch] $m 캔들 다운로드 중..."
        uv run signal fetch-candles --market $m --from 2025-01-01 --to 2026-05-31
        if ($LASTEXITCODE -ne 0) { throw "fetch-candles 실패: $m" }
    }
}

# ── 콘솔 표에서 지표 값 추출 ─────────────────────────────────────────────
function Get-Metric {
    param([string[]]$Lines, [string]$Label)
    foreach ($line in $Lines) {
        if ($line -match [regex]::Escape($Label)) {
            $m = [regex]::Match($line, "$([regex]::Escape($Label))[^\d+\-]*([+\-]?[\d,]+\.?\d*\s?%?)")
            if ($m.Success) { return $m.Groups[1].Value.Trim() }
        }
    }
    return "NA"
}

# ── Buy&Hold 수익률 (마켓 x 구간별 1회 계산, 캐시) ──────────────────────
$BhCache = @{}
function Get-BuyHold {
    param([string]$Market, [string]$From, [string]$To)
    $key = "$Market|$From|$To"
    if ($BhCache.ContainsKey($key)) { return $BhCache[$key] }
    $py = "import glob,pandas as pd; " +
          "fs=sorted(glob.glob('data/candles/$Market/60/*.parquet')); " +
          "df=pd.concat([pd.read_parquet(f) for f in fs]).sort_values('opened_at'); " +
          "d=df[df.opened_at.dt.strftime('%Y-%m-%d').between('$From','$To')]; " +
          "print('%+.2f%%' % ((d.close.iloc[-1]/d.close.iloc[0]-1)*100) if len(d) else 'NA')"
    $val = (uv run python -c $py 2>$null | Select-Object -Last 1)
    if ([string]::IsNullOrWhiteSpace($val)) { $val = "NA" }
    $BhCache[$key] = $val
    return $val
}

# ── 1) 75회 백테스트 ─────────────────────────────────────────────────────
$Rows  = @()
$total = $Markets.Count * $Periods.Count * $Strategies.Count
$i     = 0

foreach ($m in $Markets) {
    foreach ($p in $Periods) {
        $bh = Get-BuyHold -Market $m -From $p.From -To $p.To
        foreach ($s in $Strategies) {
            $i++
            Write-Host ("[{0,2}/{1}] {2} {3} {4}" -f $i, $total, $m, $p.Name, $s)
            $raw = uv run signal backtest --market $m --from $p.From --to $p.To --strategy $s 2>&1 |
                   ForEach-Object { $_.ToString() }
            $rawPath = Join-Path $RawDir ("{0}_{1}_{2}.txt" -f $m, $p.Name, $s)
            $raw | Set-Content -Path $rawPath -Encoding UTF8

            $Rows += [pscustomobject]@{
                market        = $m
                period        = $p.Name
                strategy      = $s
                trades        = Get-Metric $raw "거래 횟수"
                win_rate      = Get-Metric $raw "승률"
                avg_pnl       = Get-Metric $raw "평균 수익률"
                cum_return    = Get-Metric $raw "누적 수익률"
                mdd           = Get-Metric $raw "MDD"
                sharpe        = Get-Metric $raw "샤프"
                avg_bars_held = Get-Metric $raw "평균 보유봉"
                buy_hold      = $bh
            }
        }
    }
}

# ── 2) CSV 저장 + 화면 요약 ──────────────────────────────────────────────
$csvPath = Join-Path $OutDir "strategy_matrix.csv"
$Rows | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
Write-Host ""
Write-Host "완료: $csvPath (raw: $RawDir)"
$Rows | Format-Table market, period, strategy, trades, win_rate, cum_return, mdd, sharpe, buy_hold -AutoSize
