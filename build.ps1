# TokenBoard 一键打包
#
#   .\build.ps1            完整打包（应用 + 安装器 + 免安装包）
#   .\build.ps1 -AppOnly   只打包应用
#   .\build.ps1 -Installer 只打包安装器
#
# 依赖：pyinstaller（pip install pyinstaller）
param(
    [switch]$PortableOnly,
    [switch]$InstallerOnly
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Step "生成图标"
python tools\make_ico.py

if (-not $InstallerOnly) {
    Step "打包免安装单文件版（dist\portable\TokenBoard.exe）"
    python -m PyInstaller --noconfirm --clean `
        --distpath dist\portable --workpath build\portable tokenboard_onefile.spec
    if ($LASTEXITCODE -ne 0) { throw "免安装版打包失败" }
}

if (-not $PortableOnly) {
    Step "打包应用目录版（dist\TokenBoard\）"
    python -m PyInstaller --noconfirm --clean tokenboard.spec
    if ($LASTEXITCODE -ne 0) { throw "应用打包失败" }

    Step "打包单文件安装器（TokenBoard-Setup-1.0.0.exe）"
    python -m PyInstaller --noconfirm --clean installer\setup_onefile.spec
    if ($LASTEXITCODE -ne 0) { throw "安装器打包失败" }
}

Step "生成免安装 ZIP"
python tools\package.py

Step "完成"
Get-ChildItem dist -Recurse -File |
    Where-Object { $_.Extension -in '.exe', '.zip' } |
    ForEach-Object { "{0,-40} {1,8:N2} MB" -f $_.FullName.Replace("$PSScriptRoot\dist\", ''), ($_.Length / 1MB) }
