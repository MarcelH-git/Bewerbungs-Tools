#!/usr/bin/env python3
"""
finalize_anschreiben.py - Setzt private Daten in Anschreiben-Entwurf ein.

WICHTIG: Dieses Script darf NICHT über den Cloud-Agenten ausgeführt werden.
         Nur lokal oder via lokalem Modell (z.B. Qwen) aufrufen.

Verwendung:
  python3 ~/bewerbungs-tools/finalize_anschreiben.py /pfad/zum/anschreiben_entwurf.txt
"""

import argparse
import subprocess
import sys
import os


def privat(feld):
    r = subprocess.run(
        ['sudo', '-u', 'private_data', 'python3', '/opt/openclaw/private_resolver.py', feld],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"FEHLER beim Lesen von {feld}: {r.stderr}", file=sys.stderr)
        sys.exit(1)
    return r.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description='Setzt private Daten in Anschreiben-Entwurf ein')
    parser.add_argument('pfad', help='Pfad zur Entwurfsdatei (mit %%PRIVAT_..%% Platzhaltern)')
    args = parser.parse_args()

    if not os.path.exists(args.pfad):
        print(f"FEHLER: Datei nicht gefunden: {args.pfad}", file=sys.stderr)
        sys.exit(1)

    with open(args.pfad, 'r', encoding='utf-8') as f:
        text = f.read()

    if '%%PRIVAT_' not in text:
        print("FEHLER: Keine Platzhalter gefunden — ist das wirklich ein Entwurf?", file=sys.stderr)
        sys.exit(1)

    name = privat('NAME')
    briefkopf = f"{name}\n{privat('ADRESSE')}\n{privat('PLZ_ORT')}\n{privat('TELEFON')}\n{privat('EMAIL')}"

    text = text.replace('%%PRIVAT_BRIEFKOPF%%', briefkopf)
    text = text.replace('%%PRIVAT_NAME%%', name)

    with open(args.pfad, 'w', encoding='utf-8') as f:
        f.write(text)

    print(f"Fertig: {args.pfad}")


if __name__ == '__main__':
    main()
