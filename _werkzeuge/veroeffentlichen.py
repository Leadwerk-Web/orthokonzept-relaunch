"""Erzeugt aus site/ die öffentliche Vorschau für GitHub Pages und schiebt sie auf den Zweig gh-pages.

Vorschau-URL: https://leadwerk-web.github.io/orthokonzept-relaunch/
- alle wurzelrelativen Pfade (/assets/…, /leistungen/…) bekommen das Präfix /orthokonzept-relaunch
- jede Seite noindex, nofollow (die Vorschau darf nicht mit der Live-Seite konkurrieren; Canonicals
  zeigen weiter auf www.orthokonzept.de)
- Kontaktformular im statischen Modus (öffnet das E-Mail-Programm), PHP und .htaccess entfallen
- .nojekyll, damit GitHub Pages die Dateien unverändert ausliefert

Aufruf: python veroeffentlichen.py            (nur bauen nach ../_pages_root/orthokonzept-relaunch)
        python veroeffentlichen.py --push     (bauen und auf gh-pages schieben)
"""
import os, re, shutil, subprocess, sys
from pathlib import Path

REPO = "orthokonzept-relaunch"
BASE = "/" + REPO
ORG_REMOTE = f"https://github.com/Leadwerk-Web/{REPO}.git"
HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
SRC = PROJ / "site"
OUT = PROJ / "_pages_root" / REPO

ATTR = re.compile(r'(\s(?:href|src|action|data-full|data-src|poster)=")/(?!/)')
SRCSET = re.compile(r'(\s(?:srcset|imagesrcset)=")([^"]+)(")')
CSSURL = re.compile(r"url\((['\"]?)/(?!/)")


def fix_html(s):
    s = ATTR.sub(lambda m: m.group(1) + BASE + "/", s)
    s = SRCSET.sub(lambda m: m.group(1) + ", ".join(
        (BASE + p.strip() if p.strip().startswith("/") and not p.strip().startswith("//") else p.strip())
        for p in m.group(2).split(",")) + m.group(3), s)
    s = CSSURL.sub(lambda m: "url(" + m.group(1) + BASE + "/", s)
    s = re.sub(r'<meta name="robots" content="[^"]*">', '<meta name="robots" content="noindex, nofollow">', s)
    inject = f'<script>window.OK_BASE="{BASE}";window.OK_STATIC=true</script>\n'
    s = s.replace('<script>document.documentElement.classList.add("js")</script>',
                  inject + '<script>document.documentElement.classList.add("js")</script>', 1)
    return s


def build():
    if OUT.exists():
        # .git behalten, Rest ersetzen
        for p in OUT.iterdir():
            if p.name == ".git":
                continue
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    n_html = 0
    for src in SRC.rglob("*"):
        rel = src.relative_to(SRC)
        if src.is_dir():
            continue
        if rel.name in (".htaccess",) or rel.suffix == ".php":
            continue
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".html":
            dst.write_text(fix_html(src.read_text(encoding="utf-8")), encoding="utf-8")
            n_html += 1
        elif src.suffix == ".css":
            dst.write_text(CSSURL.sub(lambda m: "url(" + m.group(1) + BASE + "/", src.read_text(encoding="utf-8")), encoding="utf-8")
        elif src.name == "site.webmanifest":
            t = src.read_text(encoding="utf-8").replace('"start_url": "/"', f'"start_url": "{BASE}/"').replace('"/assets/', f'"{BASE}/assets/')
            dst.write_text(t, encoding="utf-8")
        elif src.name == "robots.txt":
            dst.write_text("# Vorschau, nicht indexieren\nUser-agent: *\nDisallow: /\n", encoding="utf-8")
        else:
            shutil.copy2(src, dst)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Vorschau orthokonzept.de (Redesign)\n\nÖffentliche Vorschau: https://leadwerk-web.github.io/orthokonzept-relaunch/\n\n"
        "Automatisch erzeugt aus `site/` im Zweig `main` (`_werkzeuge/veroeffentlichen.py`). Nicht von Hand bearbeiten.\n", encoding="utf-8")
    # Kontrolle: keine wurzelrelativen Pfade ohne Präfix mehr
    bad = []
    for f in OUT.rglob("*.html"):
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r'\s(?:href|src|action|data-full|data-src)="(/[^"]*)"', t):
            if not m.group(1).startswith(BASE + "/") and not m.group(1).startswith("//"):
                bad.append((f.relative_to(OUT), m.group(1)))
    print(f"Vorschau gebaut: {OUT} ({n_html} HTML-Seiten)")
    if bad:
        print("WARNUNG: Pfade ohne Präfix:", bad[:10])
        sys.exit(1)


def git(*a, cwd=OUT):
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit(f"git {' '.join(a)} fehlgeschlagen")
    return r.stdout.strip()


def push():
    if not (OUT / ".git").exists():
        git("init", "-b", "gh-pages")
        git("remote", "add", "origin", ORG_REMOTE)
    git("add", "-A")
    if git("status", "--porcelain"):
        git("commit", "-m", "Vorschau aus site/ aktualisiert\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    git("push", "-f", "origin", "gh-pages")
    print("gh-pages gepusht:", ORG_REMOTE)


if __name__ == "__main__":
    build()
    if "--push" in sys.argv:
        push()
