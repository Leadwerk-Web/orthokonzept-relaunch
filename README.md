# orthokonzept.de – Redesign 2026

Statische Website der orthoKonzept GmbH, Karlsruhe (Orthopädie-Schuhtechnik), mit integriertem
THeynis-Konfigurator.

**Vorschau:** https://leadwerk-web.github.io/orthokonzept-relaunch/
(nicht indexiert, Formular öffnet in der Vorschau das E-Mail-Programm)

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `site/` | Fertige Website für die Auslieferung unter www.orthokonzept.de (wurzelrelative Pfade, `.htaccess`, `kontakt/senden.php`). |
| `_werkzeuge/` | Skripte, mit denen `site/` erzeugt und geprüft wird. |
| `_daten/` | Inhalte aller Seiten (`inhalte.json`), Schreibweisen der Überschriften, SEO-Titel und -Beschreibungen, Konfigurator-Sektion. |
| Zweig `gh-pages` | Automatisch erzeugte Vorschau (Präfix `/orthokonzept-relaunch`, noindex). |

Nicht im Repository (lokal vorhanden oder per Skript erzeugbar): `original/` (Spiegel der
bisherigen Seite, `spiegeln.py`) und `theynis-configurator/` (Materialbilder des Konfigurators).

## Ablauf

```
python _werkzeuge/spiegeln.py        # bisherige Seite spiegeln -> original/
python _werkzeuge/extrahieren.py     # Inhalte -> _daten/inhalte.json
python _werkzeuge/konfigurator.py    # Materialien/Modelle -> site/theynis/konfigurator/
python _werkzeuge/build.py           # Website -> site/ (AVIF + WebP, Sitemap, llms.txt, Favicons)
python _werkzeuge/pruefen.py         # Prüfung: Links, H1, Meta, Bilder, strukturierte Daten
python _werkzeuge/veroeffentlichen.py --push   # Vorschau bauen und auf gh-pages schieben
```

Handgeschriebene Quellen in `site/`: `assets/css/main.css`, `assets/js/main.js`,
`assets/js/konfigurator.js`, `kontakt/senden.php`, `.htaccess`. Alles andere erzeugt `build.py`.

## Technik

- Kein CMS, kein jQuery, keine externen Schriften oder Skripte; Bilder als AVIF/WebP in mehreren Breiten.
- Strukturierte Daten (LocalBusiness/MedicalBusiness, Service, BlogPosting, Breadcrumbs), `sitemap.xml`,
  `robots.txt`, `llms.txt`.
- Google Maps und YouTube laden erst nach Klick, Statistik (Google Tag Manager) nur nach Einwilligung
  und nur auf www.orthokonzept.de.
- THeynis-Konfigurator: fünf Modelle, Materialien aus `daten.json`, Vorschau als SVG mit
  Materialtexturen, Zustand im Link (`?cfg=…`), Übergabe ins Kontaktformular.
