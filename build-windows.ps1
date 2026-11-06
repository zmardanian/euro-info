# Build the Euro Info Windows release.
#
#   .\build-windows.ps1              checks, tests, app, self-test, installer and portable zip
#   .\build-windows.ps1 -SkipTests
#
# Output in dist\:
#   Euro-Info-<version>-windows-x64-setup.exe   per-user installer (Inno Setup)
#   Euro-Info-<version>-windows-x64.zip         portable app folder
#   SHA256SUMS-windows.txt                      checksums with plain file names
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
# The version has one source: euroinfo/__init__.py.
$Version = & $Python -c "import re, pathlib; print(re.search(r'__version__ = \`"([^\`"]+)\`"', pathlib.Path('euroinfo/__init__.py').read_text()).group(1))"
if (-not $Version) { throw "Could not read the version from euroinfo/__init__.py" }
Write-Host "== Euro Info $Version (Windows x64)"

Write-Host "== Checks"
& $Python -m ruff check euroinfo tests app.py
if ($LASTEXITCODE) { throw "Lint failed" }
if (-not $SkipTests) {
    $env:QT_QPA_PLATFORM = "offscreen"
    & $Python -m unittest discover -s tests -q
    if ($LASTEXITCODE) { throw "Tests failed" }
    Remove-Item Env:QT_QPA_PLATFORM
}

Write-Host "== PyInstaller"
Remove-Item -Recurse -Force build, dist\euro-info -ErrorAction SilentlyContinue
& $Python -m PyInstaller --noconfirm --clean --log-level WARN euro-info.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }
$Bundle = "dist\euro-info"
if (-not (Test-Path "$Bundle\euro-info.exe")) { throw "PyInstaller output missing" }

# Keep Qt WebEngine browser strings and Qt translations for the seven interface languages.
$Keep = @("en-US.pak", "en-GB.pak", "fr.pak", "de.pak", "it.pak", "ro.pak", "pl.pak", "es.pak", "es-419.pak")
Get-ChildItem "$Bundle\_internal\PySide6\translations\qtwebengine_locales\*.pak" -ErrorAction SilentlyContinue |
    Where-Object { $Keep -notcontains $_.Name } | Remove-Item
Get-ChildItem "$Bundle\_internal\PySide6\translations\*.qm" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notmatch '_(en|fr|de|it|ro|pl|es)\.qm$' } | Remove-Item

Write-Host "== Self-test"
$Report = Join-Path $PWD "dist\self-test-windows.json"
Remove-Item $Report -ErrorAction SilentlyContinue
$process = Start-Process -FilePath "$Bundle\euro-info.exe" -ArgumentList "--self-test", "`"$Report`"" -Wait -PassThru
Get-Content $Report
if ($process.ExitCode -ne 0) { throw "Self-test failed (exit $($process.ExitCode))" }

Write-Host "== Portable zip"
$Zip = "dist\Euro-Info-$Version-windows-x64.zip"
Remove-Item $Zip -ErrorAction SilentlyContinue
Compress-Archive -Path $Bundle -DestinationPath $Zip -CompressionLevel Optimal

Write-Host "== Installer"
$Iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { throw "Inno Setup 6 is not installed (choco install innosetup)" }
& $Iscc "/DAppVersion=$Version" "/DSourceDir=$PWD\$Bundle" "/DOutputDir=$PWD\dist" "packaging\windows\euro-info.iss"
if ($LASTEXITCODE) { throw "Inno Setup failed" }

Write-Host "== Checksums"
Push-Location dist
$files = @("Euro-Info-$Version-windows-x64-setup.exe", "Euro-Info-$Version-windows-x64.zip")
$lines = foreach ($file in $files) { "{0}  {1}" -f (Get-FileHash $file -Algorithm SHA256).Hash.ToLower(), $file }
Set-Content -Path "SHA256SUMS-windows.txt" -Value $lines -Encoding ascii
Get-Content "SHA256SUMS-windows.txt"
Pop-Location
Write-Host "== Done"
