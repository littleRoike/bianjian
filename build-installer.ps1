param(
    [switch]$NoClean
)
$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if ($NoClean) {
    Write-Host "[1/4] 已启用 -NoClean，跳过 dist 清空。" -ForegroundColor Cyan
} else {
    if (Test-Path ".\dist") {
        Write-Host "[1/4] 检测到 dist 目录，先清空..." -ForegroundColor Cyan
        Get-ChildItem ".\dist" -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    } else {
        Write-Host "[1/4] 未检测到 dist 目录，自动创建..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Path ".\dist" | Out-Null
    }
}

Write-Host "[2/4] 构建 EXE..." -ForegroundColor Cyan
.\build.ps1

Write-Host "[3/4] 查找 Inno Setup (ISCC.exe)..." -ForegroundColor Cyan
$isccCandidates = @(
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe"
)
$iscc = $null
foreach ($p in $isccCandidates) {
    if (Test-Path $p) {
        $iscc = $p
        break
    }
}
if (-not $iscc) {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}
if (-not $iscc) {
    throw "未找到 Inno Setup 编译器 ISCC.exe。请先安装 Inno Setup 6。"
}

Write-Host "[4/4] 生成安装包..." -ForegroundColor Cyan
& $iscc ".\installer.iss"

Write-Host "`n完成！安装包位于:" -ForegroundColor Green
Write-Host "  $here\dist\便笺-安装包.exe" -ForegroundColor Yellow
