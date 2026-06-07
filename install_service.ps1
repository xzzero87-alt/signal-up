# install_service.ps1 — 업비트 시그널 프로그램 Windows Service 등록
# 반드시 "관리자 권한으로 실행" 후 사용하세요.
# 참조: ADR-0011 (docs/adr/0011-windows-service.md)

$ErrorActionPreference = "Stop"
$SvcName  = "SignalUp"
$AppDir   = $PSScriptRoot

# ── 1. nssm 경로 탐색 ──────────────────────────────────────────
$NssmLocal = Join-Path $AppDir "tools\nssm.exe"
if (Test-Path $NssmLocal) {
    $Nssm = $NssmLocal
} else {
    $found = Get-Command nssm -ErrorAction SilentlyContinue
    if ($found) {
        $Nssm = $found.Source
    } else {
        Write-Host ""
        Write-Host "  [오류] nssm.exe 를 찾을 수 없습니다." -ForegroundColor Red
        Write-Host ""
        Write-Host "  아래 중 하나로 설치 후 다시 실행하세요:"
        Write-Host "    1) Chocolatey : choco install nssm"
        Write-Host "    2) Scoop      : scoop install nssm"
        Write-Host "    3) 수동 다운로드 후 tools\nssm.exe 로 배치 : https://nssm.cc/download"
        Write-Host ""
        exit 1
    }
}

# ── 2. uv 경로 확인 ────────────────────────────────────────────
$UvCmd = Get-Command uv -ErrorAction SilentlyContinue
if (-not $UvCmd) {
    Write-Host "  [오류] uv 를 찾을 수 없습니다. 먼저 uv 를 설치하세요." -ForegroundColor Red
    Write-Host "         powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`""
    exit 1
}
$UvPath = $UvCmd.Source

# ── 3. .env 파일 확인 ──────────────────────────────────────────
$EnvFile = Join-Path $AppDir ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "  [경고] .env 파일이 없습니다. 먼저 .env.example 을 복사해 작성하세요." -ForegroundColor Yellow
    Write-Host "         copy .env.example .env"
    Write-Host ""
    $ans = Read-Host "  계속 진행하시겠습니까? (y/N)"
    if ($ans -ne "y") { exit 1 }
}

# ── 4. 이미 등록된 서비스 확인 ────────────────────────────────
$existing = sc.exe query $SvcName 2>&1
if ($existing -notmatch "FAILED") {
    Write-Host ""
    Write-Host "  [경고] '$SvcName' 서비스가 이미 등록되어 있습니다." -ForegroundColor Yellow
    $ans = Read-Host "  재설치하려면 기존 서비스를 먼저 제거합니다. 계속할까요? (y/N)"
    if ($ans -ne "y") { exit 0 }
    Stop-Service $SvcName -ErrorAction SilentlyContinue
    & $Nssm remove $SvcName confirm
}

# ── 5. logs 폴더 생성 ──────────────────────────────────────────
$LogDir = Join-Path $AppDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory $LogDir | Out-Null }

# ── 6. 서비스 등록 ────────────────────────────────────────────
Write-Host ""
Write-Host "  서비스 등록 중..." -ForegroundColor Cyan

& $Nssm install   $SvcName $UvPath
& $Nssm set       $SvcName AppParameters   "run signal serve"
& $Nssm set       $SvcName AppDirectory    $AppDir
& $Nssm set       $SvcName AppEnvironmentExtra "SIGNAL_ENV_FILE=$EnvFile"
& $Nssm set       $SvcName AppStdout       "$LogDir\service_stdout.log"
& $Nssm set       $SvcName AppStderr       "$LogDir\service_stderr.log"
& $Nssm set       $SvcName AppRotateFiles  1
& $Nssm set       $SvcName AppRotateBytes  10485760   # 10 MB
& $Nssm set       $SvcName AppRestartDelay 5000       # 재기동 대기 5초
& $Nssm set       $SvcName Start           SERVICE_AUTO_START
& $Nssm set       $SvcName DisplayName     "업비트 시그널 프로그램"
& $Nssm set       $SvcName Description     "업비트/국내주식 BB+CCI/Fractal 시그널 알림 (ADR-0011)"

# ── 7. 서비스 시작 ────────────────────────────────────────────
Write-Host "  서비스 시작 중..." -ForegroundColor Cyan
Start-Service $SvcName

Start-Sleep -Seconds 2
$state = (Get-Service $SvcName).Status
Write-Host ""
if ($state -eq "Running") {
    Write-Host "  [완료] '$SvcName' 서비스가 실행 중입니다." -ForegroundColor Green
    Write-Host "  대시보드 : http://127.0.0.1:8000"
    Write-Host "  로그     : $LogDir\service_stdout.log"
    Write-Host ""
    Write-Host "  관리 명령어:"
    Write-Host "    Stop-Service $SvcName      # 중지"
    Write-Host "    Start-Service $SvcName     # 시작"
    Write-Host "    Restart-Service $SvcName   # 재시작"
    Write-Host "    .\uninstall_service.ps1    # 서비스 제거"
} else {
    Write-Host "  [경고] 서비스 상태: $state" -ForegroundColor Yellow
    Write-Host "  로그를 확인하세요: $LogDir\service_stderr.log"
}
Write-Host ""
