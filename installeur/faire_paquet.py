"""Fabrique le paquet « Tout installer » de l'atelier : tout le dépôt suivi par git dans AtelierMontage/, zippé puis écrit en base64
(un fichier texte que la page de l'atelier publie à côté d'elle et rend en .zip au clic).

    python3 installeur/faire_paquet.py <sortie.txt>

Seuls les fichiers suivis par git y vont : jamais de fichier de client, de clé ni de .venv.
"""
import base64
import io
import subprocess
import sys
import zipfile

sortie = sys.argv[1]
fichiers = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout.decode().split("\0")
fichiers = [f for f in fichiers if f and not f.startswith(".github/")]
tampon = io.BytesIO()
with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for f in fichiers:
        info = zipfile.ZipInfo("AtelierMontage/" + f, date_time=(2026, 11, 24, 12, 0, 0))
        executable = f.endswith((".command", ".sh"))
        info.external_attr = ((0o755 if executable else 0o644) | 0o100000) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        with open(f, "rb") as h:
            z.writestr(info, h.read())
donnees = tampon.getvalue()
with open(sortie, "w") as h:
    h.write(base64.b64encode(donnees).decode())
print(f"{len(fichiers)} fichiers, zip {len(donnees) // 1024} Ko, texte {len(donnees) * 4 // 3 // 1024} Ko -> {sortie}")
