"""Baut den THeynis-Konfigurator v3 in die 1:1-Spiegelung (../original) ein.

Die Spiegelung bleibt sonst unverändert. Eingefügt wird auf /leistungen/theynis/ direkt vor der
Beispiel-Galerie; Styles kommen als eigenständige, auf den Konfigurator begrenzte Datei
(konfigurator-standalone.css), damit das Bridge-Theme nicht beeinflusst wird.
Aufruf nach konfigurator.py und build.py: python integrieren_original.py
"""
import os, re, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
ORIG = os.path.join(PROJ, "original")
SITE = os.path.join(PROJ, "site")

# 1) Assets übernehmen (gleiche absoluten Pfade wie im Redesign)
for rel in ("theynis/konfigurator", "assets/fonts"):
    src, dst = os.path.join(SITE, rel), os.path.join(ORIG, rel)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
os.makedirs(os.path.join(ORIG, "assets", "js"), exist_ok=True)
shutil.copy(os.path.join(SITE, "assets", "js", "konfigurator.js"), os.path.join(ORIG, "assets", "js", "konfigurator.js"))

# 2) Eigenständiges CSS: Tokens + Buttons + Konfigurator-Regeln, alles unter #konfigurator
css = open(os.path.join(SITE, "assets", "css", "main.css"), encoding="utf-8").read()
root = re.search(r":root\{.*?\n\}", css, re.S).group(0)
fonts = "\n".join(re.findall(r"@font-face\{[^}]*\}", css))
keep_sel = re.compile(r"(\.cfg|\.sw|\.mdl|\.btn|\.i\b|\.sr-only|\.eyebrow|\.lead|\.sec__head|@keyframes fadeIn)")


def scoped_rules(block):
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block):
        sel = sel.strip()
        if not keep_sel.search(sel) or sel.startswith("@") or sel.startswith("from") or sel.startswith("to"):
            continue
        parts = [f"#konfigurator {s.strip()}" for s in sel.split(",")]
        out.append(",".join(parts) + "{" + body + "}")
    return out


# Regeln außerhalb von @media
top = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
top = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", top)
rules = scoped_rules(top)
for m in re.finditer(r"(@media[^{]*)\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}", css):
    inner = scoped_rules(m.group(2))
    if inner:
        rules.append(m.group(1) + "{" + "".join(inner) + "}")
standalone = (f"/* THeynis-Konfigurator, eigenständig für die Spiegelung (aus main.css erzeugt) */\n{fonts}\n{root}\n"
              "#konfigurator{font-family:Rubik,system-ui,sans-serif;color:var(--text);line-height:1.6;padding:80px 0;background:linear-gradient(180deg,#fff,#f6f2ea 30%)}\n"
              "#konfigurator *,#konfigurator *::before,#konfigurator *::after{box-sizing:border-box}\n"
              "#konfigurator .wrap{max-width:1240px;margin:0 auto;padding:0 24px}\n"
              "#konfigurator h2{font-size:clamp(1.75rem,1.3rem + 1.9vw,2.875rem);color:var(--ink);letter-spacing:-.02em;line-height:1.12;margin:0 0 .5em;font-weight:600;text-transform:none;font-family:Rubik,sans-serif}\n"
              "#konfigurator h3,#konfigurator legend{font-family:Rubik,sans-serif;text-transform:none;letter-spacing:-.01em}\n"
              "#konfigurator img{max-width:100%;height:auto;display:block}\n"
              "#konfigurator [hidden]{display:none!important}\n"
              "#konfigurator ul,#konfigurator ol{margin:0;padding:0}\n"
              "#konfigurator .reveal{opacity:1!important;transform:none!important}\n"
              "@keyframes fadeIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}\n"
              + "\n".join(rules) + "\n")
os.makedirs(os.path.join(ORIG, "assets", "css"), exist_ok=True)
open(os.path.join(ORIG, "assets", "css", "konfigurator-standalone.css"), "w", encoding="utf-8").write(standalone)

# 3) Sektion in die THeynis-Seite einsetzen (idempotent)
page = os.path.join(ORIG, "leistungen", "theynis", "index.html")
h = open(page, encoding="utf-8").read()
h = re.sub(r"<!-- THEYNIS-KONFIGURATOR:START -->.*?<!-- THEYNIS-KONFIGURATOR:ENDE -->", "", h, flags=re.S)
section = open(os.path.join(PROJ, "_daten", "konfigurator.html"), encoding="utf-8").read()
block = ("<!-- THEYNIS-KONFIGURATOR:START -->\n<link rel=\"stylesheet\" href=\"/assets/css/konfigurator-standalone.css\">\n"
         + section + "\n<script src=\"/assets/js/konfigurator.js\" defer></script>\n<!-- THEYNIS-KONFIGURATOR:ENDE -->\n")
anchor = h.find("Hier k")
if anchor < 0:
    raise SystemExit("Einfügepunkt (Beispiel-Galerie) nicht gefunden")
# Beginn des Elementor-Containers, der die Überschrift der Galerie enthält
start = h.rfind('<div class="elementor-element', 0, anchor)
while start > 0 and 'e-parent' not in h[start:h.find(">", start)]:
    start = h.rfind('<div class="elementor-element', 0, start)
h = h[:start] + block + h[start:]
open(page, "w", encoding="utf-8").write(h)
print("Konfigurator in", page, "eingesetzt,", len(rules), "CSS-Regeln")
