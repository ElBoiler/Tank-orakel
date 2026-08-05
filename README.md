# Tank-Orakel

Eine Frage, eine Antwort: **jetzt tanken oder warten?**

Seit dem 1. April 2026 gilt in Deutschland die 12-Uhr-Regel
(Kraftstoffpreisanpassungsgesetz): Eine Tankstelle darf ihren Preis nur einmal
am Tag erhöhen — um 12:00 Uhr. Vor 12 Uhr kann er nur fallen oder gleich
bleiben. Das macht den Tagesverlauf asymmetrisch und teilweise vorhersehbar.
Tank-Orakel nutzt diese Regel plus eine historische Tageskurve, um für einen
Fahrer an einem Ort zu einem Zeitpunkt eine ehrliche Einschätzung zu geben —
keine Vorhersage, eine statistische Tendenz.

## Aufbau

| Datei | Zweck |
|-------|-------|
| `index.html` | Die komplette App (HTML, CSS, JS inline). Kein Build, kein Framework. |
| `curve.json` | Historische Tageskurve. Anfangs **Demo-/Platzhalterdaten**; wird vom Kurven-Job (`tools/`) durch echte Auswertung ersetzt. Fällt auf eine eingebettete Kopie zurück, falls die Datei fehlt. |
| `functions/api/list.js` | Serverless-Proxy → Tankerkönig `list.php`. |
| `functions/api/prices.js` | Serverless-Proxy → Tankerkönig `prices.php`. |
| `functions/api/_proxy.js` | Gemeinsame Proxy-Logik (Validierung, Key-Injektion, Caching). |
| `tools/build_curve.py` | Berechnet `curve.json` aus den historischen Tankerkönig-Daten (siehe `tools/README.md`). |
| `impressum.html`, `datenschutz.html` | Platzhalter — noch auszufüllen. |

## Tageskurve aktualisieren (regelmäßiger Job)

`curve.json` wird nicht in Cloudflare berechnet, sondern von einem lokalen Job
(z. B. Windows Task Scheduler) aus den **historischen Tankerkönig-Daten**
(CC BY-NC-SA 4.0, nicht-kommerziell) erzeugt und ins Repository gepusht — worauf
Cloudflare Pages automatisch neu deployt. Details und Einrichtung:
[`tools/README.md`](tools/README.md).

## API-Schlüssel & Hosting (Cloudflare Pages)

Der Tankerkönig-API-Schlüssel wird **nicht** im Browser oder im Repository
abgelegt. Ein Cloudflare Pages Function hält ihn serverseitig; die Seite ruft
den gleichen Origin unter `/api/list` bzw. `/api/prices` auf, und der Proxy
ergänzt den Schlüssel. So ist der Schlüssel für Besucher nicht sichtbar.

### Deploy

1. Dieses Repository mit **Cloudflare Pages** verbinden.
2. Build-Einstellungen:
   - **Build command:** *(leer)*
   - **Build output directory:** `/` (Projektwurzel — es gibt keinen Build-Schritt)
   - Der Ordner `functions/` wird von Pages automatisch als Functions deployt.
3. Unter **Settings → Environment variables** ein **Secret** setzen:
   - `TANKERKOENIG_KEY` = dein Tankerkönig-API-Schlüssel
   (einen kostenlosen, nicht-kommerziellen Schlüssel gibt es bei
   <https://creativecommons.tankerkoenig.de/>).
4. Deployen. Fertig.

> Nicht über GitHub Pages hosten — dort würde der Function-Proxy nicht laufen,
> und ein clientseitiger Schlüssel wäre für jeden Besucher lesbar.

Ohne gesetzten `TANKERKOENIG_KEY` funktioniert die Seite weiterhin: Sie zeigt
die kurvenbasierte Empfehlung und weist darauf hin, dass Live-Preise gerade
nicht verfügbar sind.

## Lizenz / Daten

Preisdaten stammen aus der **Tankerkönig-Spritpreis-API**, lizenziert unter
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.de). Dies ist ein
nicht-kommerzielles, privates Projekt: keine Werbung, kein Tracking, keine
Analyse, keine externen Schriften. Die Tageskurve (`curve.json`) besteht
zurzeit aus Beispieldaten.

## Entwicklung / Test

Kein Build nötig. Zum lokalen Ansehen die Dateien mit einem beliebigen
statischen Server ausliefern (die Live-Preise brauchen die Cloudflare Function;
ohne sie greift die Fehler-/Fallback-Anzeige).

Testhilfe: Mit `#t=HH:MM` an der Adresse lässt sich die „aktuelle" Uhrzeit
überschreiben, z. B. `index.html#t=15:30`, um die Nachmittags-Logik zu prüfen.
