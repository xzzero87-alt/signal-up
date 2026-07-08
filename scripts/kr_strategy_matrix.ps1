# kr_strategy_matrix.ps1 — 국장 일봉 kr_fractal 엣지 매트릭스 (ADR-0022 Phase 1 게이트 입력)
# 코인 strategy_matrix.ps1과 동일 패턴. 전략은 kr_fractal 고정, 타임프레임 1440(일봉).
# 실행: cd C:\Users\user3\Desktop\VibeCoding\signal-up
#   빠른 감(10종):  powershell -ExecutionPolicy Bypass -File scripts\kr_strategy_matrix.ps1 -Quick
#   전체 게이트(43종): powershell -ExecutionPolicy Bypass -File scripts\kr_strategy_matrix.ps1
# 산출: reports\compare\kr_strategy_matrix[_quick].csv  →  uv run python scripts\kr_gate_eval.py [--quick]
param(
    [switch]$Quick,
    [string]$Strategy = "kr_fractal",
    [string]$RegimeFilter = ""
)

$ErrorActionPreference = "Continue"
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # 콘솔 핸들 없는 비대화형(리다이렉트) 실행 환경 — 무시하고 계속 (PYTHONIOENCODING이 실제 출력 인코딩 담당)
}
$env:NO_COLOR = "1"
$env:PYTHONIOENCODING = "utf-8"

$Timeframe = "1440"
$MaxHold   = 10

$RegimeSuffixMap = @{ "above_sma" = "above"; "below_sma" = "below" }
if ($RegimeFilter) {
    if (-not $RegimeSuffixMap.ContainsKey($RegimeFilter)) {
        Write-Error "RegimeFilter must be 'above_sma' or 'below_sma' (got: $RegimeFilter)"
        exit 1
    }
    $env:V1_REGIME_FILTER = $RegimeFilter
}

# ── 유니버스 43종 (data/kr_universe.py와 동기) ──────────────────────────
$Full = @(
    @{Code="005930";Name="삼성전자"},      @{Code="000660";Name="SK하이닉스"},
    @{Code="009150";Name="삼성전기"},      @{Code="018260";Name="삼성에스디에스"},
    @{Code="066570";Name="LG전자"},        @{Code="373220";Name="LG에너지솔루션"},
    @{Code="006400";Name="삼성SDI"},       @{Code="247540";Name="에코프로비엠"},
    @{Code="086520";Name="에코프로"},      @{Code="051910";Name="LG화학"},
    @{Code="010130";Name="고려아연"},      @{Code="005490";Name="POSCO홀딩스"},
    @{Code="035420";Name="NAVER"},         @{Code="035720";Name="카카오"},
    @{Code="259960";Name="크래프톤"},      @{Code="036570";Name="엔씨소프트"},
    @{Code="251270";Name="넷마블"},        @{Code="263750";Name="펄어비스"},
    @{Code="293490";Name="카카오게임즈"},  @{Code="041510";Name="에스엠"},
    @{Code="035900";Name="JYP"},           @{Code="005380";Name="현대차"},
    @{Code="000270";Name="기아"},          @{Code="012330";Name="현대모비스"},
    @{Code="207940";Name="삼성바이오로직스"}, @{Code="068270";Name="셀트리온"},
    @{Code="196170";Name="알테오젠"},      @{Code="028300";Name="HLB"},
    @{Code="105560";Name="KB금융"},        @{Code="055550";Name="신한지주"},
    @{Code="086790";Name="하나금융지주"},  @{Code="032830";Name="삼성생명"},
    @{Code="000810";Name="삼성화재"},      @{Code="028260";Name="삼성물산"},
    @{Code="003550";Name="LG"},            @{Code="034730";Name="SK"},
    @{Code="017670";Name="SK텔레콤"},      @{Code="030200";Name="KT"},
    @{Code="015760";Name="한국전력"},      @{Code="096770";Name="SK이노베이션"},
    @{Code="010950";Name="S-Oil"},         @{Code="011200";Name="HMM"},
    @{Code="090430";Name="아모레퍼시픽"}
)

# 빠른 감용 10종 — 섹터 분산(반도체·인터넷·자동차·바이오·금융·유틸·운송·2차전지)
$QuickSet = @("005930","000660","035420","035720","005380","207940","105560","015760","011200","247540")

if ($Quick) {
    $Names = $Full | Where-Object { $QuickSet -contains $_.Code }
} else {
    $Names = $Full
}

if ($RegimeFilter) {
    $suffix  = $RegimeSuffixMap[$RegimeFilter]
    $OutName = if ($Quick) { "kr_v1_regime_${suffix}_quick.csv" } else { "kr_v1_regime_${suffix}.csv" }
} else {
    $OutName = if ($Quick) { "kr_strategy_matrix_quick.csv" } else { "kr_strategy_matrix.csv" }
}

# ── 기간: FULL + 연도 분할(강건성 검증용) ───────────────────────────────
$Periods = @(
    @{ Name = "FULL"; From = "2022-01-01"; To = "2025-12-31" },
    @{ Name = "2022"; From = "2022-01-01"; To = "2022-12-31" },
    @{ Name = "2023"; From = "2023-01-01"; To = "2023-12-31" },
    @{ Name = "2024"; From = "2024-01-01"; To = "2024-12-31" },
    @{ Name = "2025"; From = "2025-01-01"; To = "2025-12-31" }
)

# 레짐 필터(200일 SMA) 웜업 — RegimeFilter 지정 시에만 적용, 미지정 시 기존 동작 그대로
# 320 캘린더일 ≈ 거래일 230봉 (200일 SMA 요구치 + 여유 30봉)
$WarmupDays   = if ($RegimeFilter) { 320 } else { 0 }
$EarliestFrom = $Periods[0].From  # "FULL" 항목 — 정의상 항상 최솟값
$FetchFromDate = if ($RegimeFilter) {
    ([datetime]$EarliestFrom).AddDays(-$WarmupDays).ToString("yyyy-MM-dd")
} else {
    $EarliestFrom
}
$ProbeMonth = ([datetime]$FetchFromDate).ToString("yyyy-MM")

$OutDir = "reports\compare"
$RawDir = Join-Path $OutDir "kr_raw"
New-Item -ItemType Directory -Force -Path $RawDir | Out-Null

# ── 0) 일봉 캔들 확보 (1440 디렉토리에 parquet 없으면 다운로드) ──────────
foreach ($n in $Names) {
    # 시작월($ProbeMonth)을 콕 집어 확인 — 부분 수집(예: 2024~만 받힌 종목) 시 빈 구간 방지
    $probe = "data\candles\$($n.Code)\1440\$ProbeMonth.parquet"
    if (Test-Path $probe) {
        Write-Host "[skip ] $($n.Code) $($n.Name) 일봉 있음"
    } else {
        # rate limit 회피: 종목 간 2초 간격 + 데이터 착지 검증 + 최대 3회 재시도
        $ok = $false
        foreach ($attempt in 1..3) {
            Write-Host "[fetch] $($n.Code) $($n.Name) 일봉 다운로드 중... (시도 $attempt/3)"
            uv run signal fetch-candles-kr --market $n.Code --from $FetchFromDate | Out-Null
            Start-Sleep -Seconds 2
            if (Test-Path $probe) { $ok = $true; break }
            Write-Host "[retry] $($n.Code) 데이터 미수신 — 5초 대기 후 재시도"
            Start-Sleep -Seconds 5
        }
        if (-not $ok) { Write-Host "[FAIL ] $($n.Code) 3회 실패 — 건너뜀" }
    }
}

# ── 콘솔 표에서 지표 값 추출 (코인 스크립트와 동일) ─────────────────────
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

# ── Buy&Hold 수익률 (종목 x 구간별 1회, 1440 parquet 기준) ──────────────
$BhCache = @{}
function Get-BuyHold {
    param([string]$Code, [string]$From, [string]$To)
    $key = "$Code|$From|$To"
    if ($BhCache.ContainsKey($key)) { return $BhCache[$key] }
    $py = "import glob,pandas as pd; " +
          "fs=sorted(glob.glob('data/candles/$Code/1440/*.parquet')); " +
          "df=pd.concat([pd.read_parquet(f) for f in fs]).sort_values('opened_at'); " +
          "d=df[df.opened_at.dt.strftime('%Y-%m-%d').between('$From','$To')]; " +
          "print('%+.2f%%' % ((d.close.iloc[-1]/d.close.iloc[0]-1)*100) if len(d) else 'NA')"
    $val = (uv run python -c $py 2>$null | Select-Object -Last 1)
    if ([string]::IsNullOrWhiteSpace($val)) { $val = "NA" }
    $BhCache[$key] = $val
    return $val
}

# ── 1) 백테스트 루프 (종목 x 구간) ──────────────────────────────────────
$Rows  = @()
$total = $Names.Count * $Periods.Count
$i     = 0

foreach ($n in $Names) {
    foreach ($p in $Periods) {
        $i++
        Write-Host ("[{0,3}/{1}] {2} {3} {4}" -f $i, $total, $n.Code, $n.Name, $p.Name)
        $bh  = Get-BuyHold -Code $n.Code -From $p.From -To $p.To
        $raw = uv run signal backtest --market $n.Code --from $p.From --to $p.To `
                   --strategy $Strategy --timeframe $Timeframe --max-hold $MaxHold `
                   --warmup-days $WarmupDays 2>&1 |
               ForEach-Object { $_.ToString() }
        $rawPath = Join-Path $RawDir ("{0}_{1}.txt" -f $n.Code, $p.Name)
        $raw | Set-Content -Path $rawPath -Encoding UTF8

        $Rows += [pscustomobject]@{
            market        = $n.Code
            name          = $n.Name
            period        = $p.Name
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

# ── 2) CSV 저장 + 화면 요약 ─────────────────────────────────────────────
$csvPath = Join-Path $OutDir $OutName
$Rows | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
Write-Host ""
Write-Host "완료: $csvPath (raw: $RawDir)"
Write-Host "게이트 평가: uv run python scripts\kr_gate_eval.py$(if ($Quick) {' --quick'})"
$Rows | Where-Object { $_.period -eq "FULL" } |
    Format-Table market, name, trades, cum_return, buy_hold, sharpe, mdd -AutoSize
