"""Vérifie que tout ce dont le logiciel de montage a besoin est là. Lancé à la fin de l'installation."""
import importlib
import shutil
import subprocess
import sys

manque = []
for mod, nom in [("PIL", "Pillow"), ("numpy", "numpy"), ("scipy", "scipy"), ("cv2", "opencv"), ("librosa", "librosa"),
                 ("soundfile", "soundfile"), ("faster_whisper", "faster-whisper"), ("rembg", "rembg")]:
    try:
        importlib.import_module(mod)
        print(f"  ok  {nom}")
    except Exception as e:  # noqa: BLE001
        print(f"  MANQUE  {nom} ({e.__class__.__name__})")
        manque.append(nom)
for prog in ["ffmpeg", "ffprobe", "node", "npm"]:
    chemin = shutil.which(prog)
    print(f"  {'ok' if chemin else 'MANQUE'}  {prog}")
    if not chemin:
        manque.append(prog)
if not manque:
    try:
        sortie = subprocess.run([sys.executable, "montage/montage.py", "sons"], capture_output=True, text=True, timeout=120)
        print("  ok  logiciel de montage" if sortie.returncode == 0 else "  MANQUE  logiciel de montage : " + sortie.stderr[-300:])
        if sortie.returncode != 0:
            manque.append("logiciel")
    except Exception as e:  # noqa: BLE001
        print("  MANQUE  logiciel de montage :", e)
        manque.append("logiciel")
if manque:
    print("\nIl manque : " + ", ".join(manque) + ". Relance l'installation, ou demande à Claude de finir l'installation (README.md).")
    sys.exit(1)
print("\nTout est prêt.")
