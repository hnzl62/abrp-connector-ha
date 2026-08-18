# MySkoda → ABRP Telemetry

Home-Assistant-Integration, die Fahrzeugdaten aus der [MySkoda-Integration](https://github.com/skodaconnect/homeassistant-myskoda) an die [ABRP (A Better Routeplanner) Telemetry API](https://documenter.getpostman.com/view/7396339/SWTK5a8w) sendet. API-Key, User-Token, ABRP-Fahrzeugmodell, Entity-Zuordnung und Sendeintervall werden komplett über die Home-Assistant-UI konfiguriert.

> **Vor der Veröffentlichung:** Diese Vorlage enthält Platzhalter, die vor dem ersten Release ersetzt werden sollten: `YOUR_GITHUB_USER` in [`custom_components/myskoda_abrp/manifest.json`](custom_components/myskoda_abrp/manifest.json) (documentation-URL, issue_tracker, codeowners), der Copyright-Name in [`LICENSE`](LICENSE), sowie `icon.png`/`icon@2x.png` (aktuell ein einfacher Platzhalter-Kreis).

## Was diese Integration tut

- Liest State-of-Charge, Ladezustand, Ladeleistung, Lademodus (AC/DC), Kilometerstand, Restreichweite und Außentemperatur aus den Entities der MySkoda-Integration.
- Sendet diese Werte im konfigurierten Intervall an ABRP, zusätzlich sofort bei Änderung von Ladezustand oder SoC.
- API-Key, User-Token, Fahrzeugmodell, Entity-Zuordnung und Intervall sind jederzeit über *Einstellungen → Geräte & Dienste → Konfigurieren* änderbar.

## Bekannte Grenzen (bitte vor der Einrichtung lesen)

- **Kein GPS während der Fahrt.** Die Skoda-API liefert Positionsdaten nur im Stand. `lat`/`lon` werden von dieser Integration deshalb grundsätzlich **nie** gesendet.
- **Kein Sekundentakt.** MySkoda pollt das Fahrzeug standardmäßig alle 30 Minuten (einstellbar 1–1440 min) und ergänzt das um Push-Events bei Ladevorgängen. Diese Integration kann daher keine Live-Fahrtelemetrie im ABRP-typischen 10-Sekunden-Takt liefern.
- **Realistischer Nutzen:** korrekter SoC bei der Routenplanung, Ladekurven-Tracking (Leistung, AC/DC) in ABRP, sowie Kilometerstand/Restreichweite/Außentemperatur. Nicht geeignet für Live-Navigation mit Sekundengenauigkeit.

## Voraussetzungen

- Home Assistant 2024.12 oder neuer
- [MySkoda-Integration](https://github.com/skodaconnect/homeassistant-myskoda) eingerichtet, mit mindestens einem Fahrzeug
- Ein ABRP-Konto

## Installation

### Über HACS (empfohlen)

1. HACS öffnen → Drei-Punkte-Menü (oben rechts) → **Custom repositories**
2. Repository-URL eintragen, Kategorie **Integration** wählen, **Add**
3. "MySkoda → ABRP Telemetry" in HACS suchen und herunterladen
4. Home Assistant neu starten

**Hinweis zur eigenen Domain:** HACS unterstützt ausschließlich öffentliche Repositories auf **GitHub** ([siehe HACS-Doku](https://www.hacs.xyz/docs/faq/other_git_providers/)). Soll dieses Repository über eine eigene Domain erreichbar sein, funktioniert nur ein Weiterleitungs-/Vanity-Link (z. B. `abrp.deine-domain.de` → `https://github.com/<user>/<repo>`) — in das HACS-Dialogfeld muss trotzdem die tatsächliche GitHub-URL eingetragen werden, da HACS Dateien und Releases über die GitHub-API auflöst. Ein vollständig selbst gehosteter Git-Server (Gitea, GitLab, eigener Server, ganz ohne GitHub) lässt sich **nicht** als HACS-Custom-Repository hinzufügen; in dem Fall bleibt nur die manuelle Installation unten.

### Manuell (ohne HACS)

1. Den Ordner [`custom_components/myskoda_abrp`](custom_components/myskoda_abrp) nach `<config>/custom_components/myskoda_abrp` kopieren
2. Home Assistant neu starten

Updates müssen in diesem Fall von Hand eingespielt werden (Ordner erneut kopieren).

## Einrichtung

1. **API-Key** besorgen: [abetterrouteplanner.com/resources/api](https://abetterrouteplanner.com/resources/api) → *Manage your telemetry API keys* (kostenlos, Telemetry-Only-Key genügt)
2. **User-Token** besorgen: ABRP-App oder Web-App → Fahrzeugverwaltung → *Live Data Setup* / "Generic"-Abschnitt
3. In Home Assistant: *Einstellungen → Geräte & Dienste → Integration hinzufügen → "MySkoda → ABRP Telemetry"*
4. Den Schritten folgen: Zugangsdaten → Fahrzeug auswählen → Hersteller/Modell (bei nicht erreichbarer ABRP-Modellliste: manuelle Eingabe der Modellkennung) → Entity-Zuordnung (automatisch anhand des Fahrzeugs vorbelegt, bei Bedarf anpassbar) → Sendeintervall

Alle Werte lassen sich danach jederzeit über *Konfigurieren* an der Integration ändern — auch API-Key, User-Token und Sendeintervall.

## Was gesendet wird

| ABRP-Feld | Quelle (MySkoda) | Bedingung |
|---|---|---|
| `soc` | Ladezustand (%) | immer — Pflichtfeld, ohne gültigen Wert wird nichts gesendet |
| `utc` | Zeitstempel der Fahrzeugdaten | immer |
| `is_charging` | Ladezustand-Sensor | immer |
| `power` (negiert), `is_dcfc` | Ladeleistung, Lademodus AC/DC | nur während aktiven Ladens |
| `is_parked` | Bewegungssensor (invertiert) | wenn Entity vorhanden |
| `odometer` | Kilometerstand | wenn Entity vorhanden |
| `est_battery_range` | Restreichweite | wenn Entity vorhanden |
| `ext_temp` | Außentemperatur | wenn Entity vorhanden |
| `car_model` | Konfiguration | wenn gesetzt |

`lat`/`lon` werden nicht unterstützt (siehe oben). Nicht von MySkoda bereitgestellt und daher nicht gesendet: `speed`, `voltage`, `current`, `batt_temp`, `soh`, `heading`, `elevation`, Reifendrücke, HVAC-Felder.

## Entities dieser Integration

| Entity | Zweck |
|---|---|
| `sensor.*_last_successful_send` | Zeitpunkt der letzten erfolgreichen Übertragung; enthält den zuletzt gesendeten Payload als Attribut |
| `sensor.*_last_error` | Letzte Fehlermeldung (diagnostisch) |
| `switch.*_telemetry_enabled` | Übertragung pausieren, ohne die Integration zu entfernen |

## Lizenz

[MIT](LICENSE)
