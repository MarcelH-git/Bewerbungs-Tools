#!/usr/bin/env python3
"""
anschreiben_bot.py - Wrapper für anschreiben_generator.py
Ermöglicht nicht-interaktive Nutzung durch OpenClaw Bot.

Verwendung:
  # Nur Optionen anzeigen (Bot liest sie und wählt dann aus):
  python3 ~/anschreiben_bot.py --refnr "stepstone_123" --template 1

  # Direkt mit Auswahl (Zahl oder eigener Text):
  python3 ~/anschreiben_bot.py --refnr "stepstone_123" --template 1 --auswahl 3
  python3 ~/anschreiben_bot.py --refnr "stepstone_123" --template 2 --auswahl "KI-Agenten produktionsreif deployen"

  # Template auto-detect (Bot entscheidet anhand der Stelle):
  python3 ~/anschreiben_bot.py --refnr "stepstone_123" --auswahl 2
"""

import argparse
import os
import sys
import re

# Sicherstellen dass anschreiben_generator.py importierbar ist
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anschreiben_generator as ag

TEMPLATE_KI = os.path.expanduser('~/.openclaw/anschreiben_template.txt')
TEMPLATE_DATA = os.path.expanduser('~/.openclaw/anschreiben_template_data_analyst.txt')

DATA_KEYWORDS = ['data analyst', 'data scientist', 'data engineer', 'business intelligence',
                 'bi ', 'analytics', 'sql', 'tableau', 'power bi', 'reporting']

def auto_template(stelle):
    """Wählt Template anhand der Stellenbeschreibung."""
    text = (stelle.get('titel', '') + ' ' + stelle.get('beschreibung', '')).lower()
    if any(kw in text for kw in DATA_KEYWORDS):
        return 2
    return 1

def main():
    parser = argparse.ArgumentParser(description='Anschreiben-Generator für OpenClaw Bot')
    parser.add_argument('--refnr', required=True,
                        help='Referenznummer, Stepstone-URL oder LinkedIn-URL')
    parser.add_argument('--template', type=int, choices=[1, 2], default=None,
                        help='Template: 1=KI/Automatisierung, 2=Data Analyst (auto wenn nicht angegeben)')
    parser.add_argument('--auswahl', default=None,
                        help='Brückensatz: Zahl 1-5 oder eigener Text. Wenn nicht angegeben, werden nur Optionen ausgegeben.')
    args = parser.parse_args()

    # Stelle laden
    print(f"Lade Stelle: {args.refnr}")
    stelle = ag.hole_stelle(args.refnr)

    if not stelle.get('titel'):
        print("FEHLER: Stelle konnte nicht geladen werden.", file=sys.stderr)
        sys.exit(1)

    print(f"Stelle: {stelle['titel']} @ {stelle['firma']}")

    # Template bestimmen
    template_nr = args.template if args.template else auto_template(stelle)
    if template_nr == 2:
        ag.PATH_TEMPLATE = TEMPLATE_DATA
        print("Template: Data Analyst")
    else:
        ag.PATH_TEMPLATE = TEMPLATE_KI
        print("Template: KI/Automatisierung")

    # Groq Key aus Umgebungsvariable
    groq_key = os.environ.get('GROQ_API_KEY', '')
    if not groq_key:
        print("FEHLER: GROQ_API_KEY nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    # Optionen generieren
    print("\n--- Optionen für Brückensatz ---")
    optionen, abschnitt = ag.hole_aufgabe_optionen(stelle['beschreibung'], groq_key)
    print(optionen)

    # Wenn keine Auswahl angegeben → nur Optionen ausgeben und beenden
    if args.auswahl is None:
        print("\nHINWEIS: Keine --auswahl angegeben. Skript erneut mit --auswahl <1-5 oder Text> aufrufen.")
        sys.exit(0)

    # Auswahl verarbeiten
    auswahl = args.auswahl.strip()
    if auswahl in ['1', '2', '3', '4', '5']:
        aufgabe = None
        for zeile in optionen.split('\n'):
            if zeile.strip().startswith(auswahl + '.') or zeile.strip().startswith(auswahl + ')'):
                aufgabe = re.sub(r'^\d+[.)\s]+', '', zeile).strip().rstrip('.').lstrip('.')
                break
        if not aufgabe:
            print(f"FEHLER: Option {auswahl} nicht gefunden.", file=sys.stderr)
            sys.exit(1)
        # Artikel bereinigen
        aufgabe = aufgabe.strip('"').strip()
        aufgabe = aufgabe.lstrip('...').strip().rstrip('.')
        for art in ('Die ', 'Der ', 'Das ', 'die ', 'der ', 'das '):
            if aufgabe.startswith(art):
                aufgabe = aufgabe[len(art):]
                break
    else:
        aufgabe = auswahl.rstrip('.')

    # Anschreiben bauen
    # Stelle['beschreibung'] temporär für erstelle_anschreiben verfügbar machen
    # Wir patchen den input()-Aufruf indem wir erstelle_anschreiben's Abhängigkeit umgehen
    print(f"\nBrückensatz: {aufgabe}")

    # Entwurf bauen — persönliche Daten werden NICHT hier eingesetzt.
    # Platzhalter %%PRIVAT_..%% werden von finalize_anschreiben.py lokal ersetzt.
    from datetime import datetime

    with open(ag.PATH_TEMPLATE, 'r', encoding='utf-8') as f:
        template = f.read()

    datum = datetime.now().strftime('%d.%m.%Y')
    empfaenger = f"{stelle['firma']}\n{stelle['adresse']}"
    anrede = f"Sehr geehrte/r {stelle['ansprechpartner']}," if stelle['ansprechpartner'] else "Sehr geehrte Damen und Herren,"
    aufgabe_final = aufgabe[0].upper() + aufgabe[1:] + '.'

    text = template
    text = text.replace('{BRIEFKOPF}', '%%PRIVAT_BRIEFKOPF%%')
    text = text.replace('{EMPFAENGER}', empfaenger)
    text = text.replace('{DATUM}', datum)
    text = text.replace('{TITEL}', stelle['titel'])
    text = text.replace('Sehr geehrte Damen und Herren,', anrede)
    text = text.replace('{GROQ_SATZ}', aufgabe_final)
    text = text.replace('{NAME}', '%%PRIVAT_NAME%%')

    pfad = ag.speichern(text, stelle['firma'])
    print(f"\nEntwurf gespeichert: {pfad}")
    print(f"HINWEIS: Persönliche Daten noch nicht eingesetzt.")
    print(f"Finalisieren mit: python3 ~/bewerbungs-tools/finalize_anschreiben.py \"{pfad}\"")

if __name__ == '__main__':
    main()
