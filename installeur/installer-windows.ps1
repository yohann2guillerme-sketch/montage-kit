# Atelier montage : installe tout ce qu'il faut sur un PC Windows (lance par installer-windows.bat).
# Ce qu'il installe (avec winget, l'outil d'installation de Windows) : Python 3.12, ffmpeg, Node, le runtime Visual C++ de Microsoft,
# les bibliotheques Python du logiciel (dans .venv, dans ce dossier) et le moteur video (Remotion, dans montage\moteur).
# Seulement ce qui manque : rien de deja installe n'est remplace. Rien n'est publie, aucun compte n'est touche.
# Fichier en ASCII seulement : Windows PowerShell 5.1 lit un fichier sans BOM comme de l'ANSI.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot\..
$Dossier = (Get-Location).Path
$env:PYTHONUTF8 = "1"
Write-Host ""
Write-Host "=== Atelier montage : installation dans $Dossier ==="
Write-Host "Compte 10 a 20 minutes. Windows peut demander une autorisation (c'est normal)."
Write-Host ""

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  Write-Host "winget manque : installe 'App Installer' depuis le Microsoft Store, puis relance ce fichier."
  Read-Host "Appuie sur Entree pour fermer"; exit 1
}

Write-Host "1/4 Python, ffmpeg, Node et Visual C++..."
$besoins = @(@("py", "Python.Python.3.12"), @("ffmpeg", "Gyan.FFmpeg"), @("node", "OpenJS.NodeJS.LTS"))
foreach ($b in $besoins) {
  $manque = -not (Get-Command $b[0] -ErrorAction SilentlyContinue)
  if (-not $manque -and $b[0] -eq "py") { try { & py -3.12 --version *> $null; $manque = ($LASTEXITCODE -ne 0) } catch { $manque = $true } }
  if ($manque) {
    winget install --id $b[1] -e --silent --accept-package-agreements --accept-source-agreements
  }
}
# runtime Visual C++ (onnxruntime, faster-whisper, opencv en ont besoin) : seulement s'il manque
$vc = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction SilentlyContinue
if (-not ($vc -and $vc.Installed -eq 1)) {
  winget install --id Microsoft.VCRedist.2015+.x64 -e --silent --accept-package-agreements --accept-source-agreements
}
# relire le PATH apres les installations
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "2/4 Bibliotheques Python du logiciel..."
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r installeur\requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "L'installation des bibliotheques a echoue (message ci-dessus)."; Read-Host "Appuie sur Entree pour fermer"; exit 1 }

Write-Host "3/4 Moteur video (Remotion)..."
Push-Location montage\moteur
npm install --no-audit --no-fund
$npmCode = $LASTEXITCODE
Pop-Location
if ($npmCode -ne 0) { Write-Host "L'installation du moteur video a echoue (message ci-dessus)."; Read-Host "Appuie sur Entree pour fermer"; exit 1 }

Write-Host "4/4 Verification..."
.\.venv\Scripts\python.exe installeur\verifier_installation.py

Write-Host ""
Write-Host "=== C'est installe. ==="
Write-Host "Il reste une etape : ouvre l'appli Claude, onglet Claude Code, choisis le dossier :"
Write-Host "   $Dossier"
Write-Host "et ecris : Suis montage/atelier/MODE-EMPLOI.md, partie Brancher l'atelier sur l'ordinateur"
Read-Host "Appuie sur Entree pour fermer"
