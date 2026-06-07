# uninstall_service.ps1 — Windows Service 제거
# 반드시 "관리자 권한으로 실행" 후 사용하세요.

$ErrorActionPreference = "Stop"
$SvcName = "SignalUp"
$AppDir  = $PSScriptRoot

$NssmLocal = Join-Path $AppDir "tools\nssm.exe"
if (Test-Path $NssmLocal) { $Nssm = $NssmLocal }
else {
    $found = Get-Command nssm -ErrorAction SilentlyContinue
    if ($found) { $Nssm = $found.Source }
    else { Write-Host "  [오류] nssm.exe 를 찾을 수 없습니다." -ForegroundColor Red; exit 1 }
}

$existing = sc.exe query $SvcName 2>&1
if ($existing -match "FAILED") {
    Write-Host "  '$SvcName' 서비스가 등록되어 있지 않습니다." -ForegroundColor Yellow
    exit 0
}

Write-Host "  '$SvcName' 서비스 중지 및 제거 중..." -ForegroundColor Cyan
Stop-Service $SvcName -ErrorAction SilentlyContinue
& $Nssm remove $SvcName confirm

Write-Host "  [완료] 서비스가 제거되었습니다." -ForegroundColor Green
