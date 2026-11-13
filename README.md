# montage-kit

Logiciel de montage de Reels, stories et clips : une fiche `montage.json` donne une vidéo HD aux normes, contrôlée (garde-tête, zones
d'Instagram, son à -14 LUFS).

- Mode d'emploi : `montage/README.md`
- Skill pour Claude : `.claude/skills/montage-pro/SKILL.md`
- Essais : `python3 montage/tests/test_kit.py`

Installation : Python 3 avec Pillow, numpy, scipy, opencv, librosa, soundfile (rembg pour le détourage, faster-whisper pour les paroles),
ffmpeg, Node 18 ou plus. Le moteur (Remotion) s'installe tout seul au premier rendu.

Copie du logiciel tiré du dépôt de Yohann (version de main 4b2264b, 13/11/2026).
