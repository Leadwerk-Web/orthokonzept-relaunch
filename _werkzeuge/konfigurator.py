"""Bereitet den THeynis-Konfigurator für die statische Seite vor.

Quelle: ../theynis-configurator (Materialordner assets/Materialien_Farben und Logo, nicht Teil dieses
Repos), Modellbilder aus der Live-Seite (../original, per spiegeln.py).
Ausgabe: ../site/theynis/konfigurator/ (daten.json, Material- und Modellbilder, Logos)
         ../_daten/konfigurator.html (Markup der Sektion, wird von build.py eingesetzt)

Der Konfigurator ist datengetrieben und braucht keine Datenbank: neue Materialien = Datei in den
Ordner legen, Skript laufen lassen. Namen kommen aus NAMEN oder aus dem Dateinamen.
"""
import os, re, json, hashlib
from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
SRC = os.path.join(PROJ, "theynis-configurator", "assets")
MAT = os.path.join(SRC, "Materialien_Farben")
ORIG = os.path.join(PROJ, "original")
OUT = os.path.join(PROJ, "site", "theynis", "konfigurator")

# Anzeigenamen für Dateien ohne sprechenden Namen (nach Sichtung der Muster, 26.09.2026)
NAMEN = {
    "Riemen/flip/1": "Silbergrau",
    "Riemen/flip/2": "Grau Wabenprägung",
    "Riemen/flip/3": "Taupe Wirbelprägung",
    "Riemen/flip/4": "Reptil Anthrazit",
    "Riemen/flip/5-#901D2A": "Bordeaux",
    "Riemen/flip/6": "Bordeaux Glitzer",
    "Riemen/flip/7-#7F4A3A": "Kastanie",
    "Riemen/flip/8": "Kroko Dunkelbraun",
    "Riemen/flip/9": "Braun Wirbelprägung",
    "Riemen/flip/10-#5F4137": "Mokka",
    "Riemen/flip/11-#202A4C": "Nachtblau",
    "Riemen/flip/12-#282A3F": "Marine",
    "Fußbett für alle THeynis-Modelle/#242323": "Schwarz",
    "Fußbett für alle THeynis-Modelle/#4C6B80": "Taubenblau",
    "Fußbett für alle THeynis-Modelle/#848381": "Anthrazit",
    "Fußbett für alle THeynis-Modelle/#C99F63": "Sand gesprenkelt",
    "Fußbett für alle THeynis-Modelle/IMG_7510": "Marmor Rot",
    "Fußbett für alle THeynis-Modelle/IMG_7512": "Marmor Grün",
    "Fußbett für alle THeynis-Modelle/IMG_7514": "Marmor Blau",
    "Fußbett für alle THeynis-Modelle/IMG_7574": "Marmor Schwarz",
}
FARBEN = {
    "#EEEEEE": "Weiß", "#8F939D": "Grau", "#000000": "Schwarz", "#B18D49": "Gold", "#1B97B3": "Türkis",
    "#6B5445": "Braun", "#A4122D": "Rot", "#0038BF": "Königsblau", "#8B2E9B": "Violett", "#BAF200": "Neongelb",
    "#228E5B": "Grün", "#919098": "Grau", "#F3F6F4": "Weiß", "#DA1831": "Rot", "#158749": "Grün",
    "#E66A0A": "Orange", "#3D85C6": "Blau", "#999999": "Hellgrau", "#B8C41A": "Limette", "#3D3336": "Anthrazit",
    "#F3CF00": "Gelb", "#131017": "Schwarz", "#242E40": "Nachtblau", "#7F5541": "Braun", "#AA496D": "Beere",
    "#502B4F": "Aubergine", "#254088": "Blau", "#AD9C80": "Graubraun", "#D32C38": "Rot", "#111010": "Schwarz",
    "#705748": "", "#8F5D32": "",
}

KATEGORIEN = [
    # id, Titel, Ordner, gilt für Modelle, Hinweis
    ("riemen_flip", "Riemen", "Riemen/flip", ["flip"], "Das Obermaterial des Flip-Riemens."),
    ("riemen", "Riemen", "Riemen/steg, single,double, triple", ["steg", "single", "double", "triple"], "Leder, Nubuk oder Muster für Ihre Riemen."),
    ("baender", "Bänder", "Bänder für flip-Modelle", ["flip"], "Das farbige Band am Flip-Riemen."),
    ("fussbett", "Fußbett", "Fußbett für alle THeynis-Modelle", None, "Die Oberfläche, auf der Ihr Fuß steht."),
    ("zwischensohle", "Zwischensohle", "Zwischensohlen für alle THeynis-Modelle", None, "Die farbige Schicht zwischen Fußbett und Laufsohle."),
    ("sohle", "Laufsohle", "Sohlen für alle THeynis-Modelle", None, "Die Laufsohle mit Profil."),
]

MODELLE = [
    ("flip", "Flip", "wp-content/uploads/2026/03/THeynis-Flip-1.png", "Sommerliche Leichtigkeit mit Zehensteg und Fersenstabilisierung."),
    ("steg", "Steg", "wp-content/uploads/2026/03/THeynis-Steg.png", "Die elegante Interpretation des klassischen Flipflops."),
    ("single", "Single", "wp-content/uploads/2026/03/THeynis-Single.png", "Ein Riemen: klare Form, hoher Tragekomfort."),
    ("double", "Double", "wp-content/uploads/2026/03/THeynis-Double.png", "Zwei Riemen für zusätzliche Führung."),
    ("triple", "Triple", "wp-content/uploads/2026/03/THeynis-Triple.png", "Drei Riemen für die feinste Anpassung."),
]


def slug(s):
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def nice_name(folder, fn):
    base = os.path.splitext(fn)[0]
    key = folder + "/" + base
    if key in NAMEN:
        return NAMEN[key]
    hexm = re.search(r"#([0-9A-Fa-f]{6})", base)
    words = re.sub(r"^\d+\s*-?\s*", "", base)
    words = re.sub(r"-?#[0-9A-Fa-f]{6}", "", words).strip(" -")
    if words:
        w = " ".join(x if x.isupper() else x.capitalize() for x in words.split())
        w = {"Hell Braun": "Hellbraun", "Rose": "Rosé", "Perlmut": "Perlmutt", "Camo Woodland": "Camo Woodland", "Blume Creme": "Blume Creme"}.get(w, w)
        return w
    if hexm:
        return FARBEN.get("#" + hexm.group(1).upper()) or "#" + hexm.group(1).upper()
    return base


def avg_hex(im):
    s = im.convert("RGB").resize((1, 1), Image.LANCZOS).getpixel((0, 0))
    return "#%02x%02x%02x" % s


def save_variants(im, dest_base, sizes):
    out = {}
    for s in sizes:
        fn = f"{dest_base}-{s}.webp"
        if not os.path.exists(os.path.join(OUT, fn)):
            os.makedirs(os.path.dirname(os.path.join(OUT, fn)), exist_ok=True)
            r = ImageOps.fit(im.convert("RGB"), (s, s), Image.LANCZOS, centering=(0.5, 0.5))
            r.save(os.path.join(OUT, fn), "WEBP", quality=82, method=5)
        out[s] = fn
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    cats = []
    for cid, title, folder, models, hint in KATEGORIEN:
        path = os.path.join(MAT, folder)
        files = sorted(os.listdir(path), key=lambda f: (int(re.match(r"(\d+)", f).group(1)) if re.match(r"\d+", f) else 999, f.lower()))
        opts = []
        seen = set()
        for fn in files:
            if not fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            im = Image.open(os.path.join(path, fn))
            name = nice_name(folder, fn)
            oid = slug(name) or "farbe"
            while oid in seen:
                oid += "-2"
            seen.add(oid)
            big = 1024 if cid == "fussbett" else 512
            v = save_variants(im, f"materialien/{cid}/{oid}", (160, big))
            opts.append({"id": oid, "name": name, "thumb": v[160], "tex": v[big], "hex": avg_hex(im)})
        cats.append({"id": cid, "title": title, "models": models, "hint": hint, "options": opts})
        print(cid, len(opts))

    models = []
    for mid, name, src, desc in MODELLE:
        im = Image.open(os.path.join(ORIG, src))
        fn = f"modelle/{mid}.webp"
        os.makedirs(os.path.join(OUT, "modelle"), exist_ok=True)
        im.convert("RGB").save(os.path.join(OUT, fn), "WEBP", quality=84, method=5)
        th = f"modelle/{mid}-240.webp"
        t = im.convert("RGB").copy()
        t.thumbnail((240, 240), Image.LANCZOS)
        t.save(os.path.join(OUT, th), "WEBP", quality=82)
        models.append({"id": mid, "name": name, "photo": fn, "thumb": th, "desc": desc})

    # Logos: Original (petrol) und weiß für dunkle Flächen
    logo = Image.open(os.path.join(SRC, "theynis-logo.png")).convert("RGBA")
    bbox = logo.getbbox()
    logo = logo.crop(bbox)
    logo.thumbnail((440, 200), Image.LANCZOS)
    logo.save(os.path.join(OUT, "theynis-logo.webp"), "WEBP", quality=90)
    white = Image.new("RGBA", logo.size, (255, 255, 255, 0))
    white.putalpha(logo.getchannel("A"))
    wl = Image.new("RGBA", logo.size, (255, 255, 255, 255))
    wl.putalpha(logo.getchannel("A"))
    wl.save(os.path.join(OUT, "theynis-logo-weiss.webp"), "WEBP", quality=90)

    data = {"version": 3, "stand": "2026-09-26", "models": models, "categories": cats}
    json.dump(data, open(os.path.join(OUT, "daten.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    h = hashlib.md5(json.dumps(data).encode()).hexdigest()[:8]
    open(os.path.join(PROJ, "_daten", "konfigurator.html"), "w", encoding="utf-8").write(markup(h, logo.size))
    print("Modelle", len(models))


def markup(h, logo_size):
    return f'''<section class="sec cfg-sec" id="konfigurator" aria-labelledby="cfg-h">
  <div class="wrap">
    <header class="sec__head cfg-head reveal">
      <p class="eyebrow">THeynis-Konfigurator</p>
      <h2 id="cfg-h">Gestalte deinen THeynis</h2>
      <p class="lead">Modell wählen, Riemen, Fußbett, Zwischensohle und Laufsohle kombinieren und die Konfiguration direkt zur Beratung mitbringen. Die Passform entsteht bei uns im Geschäft per 3D-Scan.</p>
    </header>
    <div class="cfg" data-cfg data-src="/theynis/konfigurator/daten.json?v={h}">
      <div class="cfg__stage">
        <div class="cfg__view" role="img" aria-label="Vorschau deiner Konfiguration" data-cfg-view>
          <div class="cfg__svg" data-cfg-svg></div>
          <img class="cfg__photo" data-cfg-photo alt="" width="600" height="600" hidden>
          <div class="cfg__toggle" role="group" aria-label="Ansicht">
            <button type="button" class="is-on" data-cfg-mode="design" aria-pressed="true">Dein Design</button>
            <button type="button" data-cfg-mode="photo" aria-pressed="false">Modellfoto</button>
          </div>
        </div>
        <ul class="cfg__chips" data-cfg-chips aria-label="Deine Auswahl"></ul>
        <p class="cfg__note">Schematische Vorschau. Farben und Strukturen können je nach Bildschirm abweichen, jedes Paar wird nach deinem 3D-Scan gefertigt.</p>
      </div>
      <div class="cfg__panel">
        <ol class="cfg__steps" data-cfg-steps aria-label="Schritte"></ol>
        <form class="cfg__form" data-cfg-form onsubmit="return false">
          <div data-cfg-body><p class="cfg__loading">Konfigurator wird geladen …</p></div>
          <div class="cfg__nav">
            <button type="button" class="btn btn--ghost" data-cfg-prev><span>Zurück</span></button>
            <button type="button" class="btn btn--light cfg__dice" data-cfg-random title="Zufällige Kombination"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8.5" cy="8.5" r="1.3" fill="currentColor"/><circle cx="15.5" cy="15.5" r="1.3" fill="currentColor"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/></svg><span>Inspiration</span></button>
            <button type="button" class="btn btn--primary" data-cfg-next><span>Weiter</span><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
          </div>
        </form>
        <p class="sr-only" aria-live="polite" data-cfg-live></p>
      </div>
    </div>
  </div>
</section>'''


if __name__ == "__main__":
    main()
