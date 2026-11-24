# Atelier montage : installe tout ce qu'il faut sur un PC Windows (lancé par installer-windows.bat).
# Ce qu'il installe (avec winget, l'outil d'installation de Windows) : Python 3.12, ffmpeg, Node, les bibliothèques Python du
# logiciel (dans .venv, dans ce dossier) et le moteur vidéo (Remotion, dans montage\moteur). Rien n'est publié, aucun compte n'est touché.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot\..
$Dossier = (Get-Location).Path
Write-Host ""
Write-Host "=== Atelier montage : installation dans $Dossier ==="
Write-Host "Compte 10 a 20 minutes. Windows peut demander une autorisation (c'est normal)."
Write-Host ""

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  Write-Host "winget manque : installe « App Installer » depuis le Microsoft Store, puis relance ce fichier."
  Read-Host "Appuie sur Entree pour fermer"; exit 1
}

Write-Host "1/4 Python, ffmpeg et Node..."
foreach ($id in @("Python.Python.3.12", "Gyan.FFmpeg", "OpenJS.NodeJS.LTS")) {
  winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements
}
# relire le PATH apres les installations
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "2/4 Bibliotheques Python du logiciel..."
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r installeur\requirements.txt

Write-Host "3/4 Moteur video (Remotion)..."
Push-Location montage\moteur
npm install --no-audit --no-fund
Pop-Location

Write-Host "4/4 Verification..."
.\.venv\Scripts\python.exe installeur\verifier_installation.py

Write-Host ""
Write-Host "=== C'est installe. ==="
Write-Host "Il reste une etape : ouvre l'appli Claude, onglet Claude Code, choisis le dossier :"
Write-Host "   $Dossier"
Write-Host "et ecris : Suis montage/atelier/MODE-EMPLOI.md, partie Brancher l'atelier sur l'ordinateur"
Read-Host "Appuie sur Entree pour fermer"
