# 一键打包脚本 - 在已激活的虚拟环境中运行
# 用法: .\build.ps1

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "[1/3] 创建虚拟环境..." -ForegroundColor Cyan
    py -3 -m venv venv
}

Write-Host "[2/3] 安装依赖..." -ForegroundColor Cyan
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "[3/3] 使用 PyInstaller 打包..." -ForegroundColor Cyan

# 清理旧构建产物
if (Test-Path ".\build") { Remove-Item -Recurse -Force ".\build" }
if (Test-Path ".\dist")  { Remove-Item -Recurse -Force ".\dist"  }
Get-ChildItem -Filter "*.spec" | Remove-Item -Force -ErrorAction SilentlyContinue

# -w 隐藏控制台；-F 单文件；--name 指定产物名
.\venv\Scripts\python.exe -m PyInstaller -w -F --name "便笺" --clean `
    --hidden-import pystray._win32 `
    --hidden-import PIL._tkinter_finder `
    main.py

Write-Host "`n完成！产物位于:" -ForegroundColor Green
Write-Host "  $here\dist\便笺.exe" -ForegroundColor Yellow
