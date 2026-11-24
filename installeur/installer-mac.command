#!/bin/bash
# Atelier montage : installe tout ce qu'il faut sur un Mac (double-clic dans le Finder).
# Ce qu'il installe : Homebrew (si absent), Python 3.12, ffmpeg, Node, les bibliothèques Python du logiciel (dans .venv, dans ce dossier)
# et le moteur vidéo (Remotion, dans montage/moteur). Rien n'est publié, aucun compte n'est touché.
set -e
cd "$(dirname "$0")"
DOSSIER="$(pwd)"
echo ""
echo "=== Atelier montage : installation dans $DOSSIER ==="
echo "Compte 10 à 20 minutes. Le Mac peut demander ton mot de passe (c'est normal)."
echo ""

if ! command -v brew >/dev/null 2>&1; then
  if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)";
  elif [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)";
  else
    echo "1/5 Installation de Homebrew (le gestionnaire d'applications du Mac)…"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; else eval "$(/usr/local/bin/brew shellenv)"; fi
  fi
fi

echo "2/5 Python, ffmpeg et Node (seulement ce qui manque ; rien de déjà installé n'est remplacé)…"
export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_UPGRADE=1
brew list python@3.12 >/dev/null 2>&1 || brew install python@3.12
command -v ffmpeg >/dev/null 2>&1 || brew install ffmpeg
command -v node >/dev/null 2>&1 || brew install node

echo "3/5 Bibliothèques Python du logiciel…"
PY="$(brew --prefix python@3.12)/bin/python3.12"
"$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r installeur/requirements.txt

echo "4/5 Moteur vidéo (Remotion)…"
( cd montage/moteur && npm install --no-audit --no-fund )

echo "5/5 Vérification…"
.venv/bin/python installeur/verifier_installation.py

echo ""
echo "=== C'est installé. ==="
echo "Il reste une étape : ouvre l'appli Claude, onglet Claude Code, choisis le dossier :"
echo "   $DOSSIER"
echo "et écris : Suis montage/atelier/MODE-EMPLOI.md, partie Brancher l'atelier sur l'ordinateur"
echo ""
read -n 1 -s -r -p "Appuie sur une touche pour fermer."
