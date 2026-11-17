# Creates a self-contained GUI executable on a Windows host, not game data.
# Requires Python 3 with pip. Run from the repository root, or via GitHub Actions.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$gui = Join-Path $root 'win\hooklink_gui.pyw'
if (!(Test-Path -LiteralPath $gui)) { throw "GUI missing: $gui" }
$python = (Get-Command python -ErrorAction Stop).Source
& $python -m pip install 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'Could not install PyInstaller' }
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name HookLinkWindows --distpath (Join-Path $root 'dist') --workpath (Join-Path $root 'build\gui-pyinstaller') --specpath (Join-Path $root 'build') $gui
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
$exe = Join-Path $root 'dist\HookLinkWindows.exe'
if (!(Test-Path -LiteralPath $exe)) { throw 'Executable was not created' }
Write-Host "Built: $exe"
Write-Host 'Copy this executable into the root of the complete HookLinkWindows checkout alongside the win directory.'
Write-Host 'The GUI executable has no bundled game files or Apple SDK/Metal toolchain.'
