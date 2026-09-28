"""Baut das Redesign von orthokonzept.de als statische Seite nach ../site/.

Quelle: ../_daten/inhalte.json (aus extrahieren.py), Bilder aus ../original, Schreibweisen aus
../_daten/ueberschriften.json, SEO-Angaben aus ../_daten/seo.json. Der THeynis-Konfigurator
kommt aus konfigurator.py (Daten und Materialbilder).

Aufruf: python build.py
"""
import os, re, json, html, shutil, hashlib, posixpath, datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
ORIG = os.path.join(PROJ, "original")
SITE = os.path.join(PROJ, "site")
DATA = os.path.join(PROJ, "_daten")
MEDIA = os.path.join(SITE, "media")
DOMAIN = "https://www.orthokonzept.de"
BUILD_DATE = datetime.date.today().isoformat()

D = json.load(open(os.path.join(DATA, "inhalte.json"), encoding="utf-8"))
PAGES = D["pages"]
CASE = {k: v for k, v in json.load(open(os.path.join(DATA, "ueberschriften.json"), encoding="utf-8")).items() if not k.startswith("_")}
SEO = json.load(open(os.path.join(DATA, "seo.json"), encoding="utf-8"))

FIRMA = {
    "name": "orthoKonzept GmbH",
    "strasse": "Hirschstraße 35 a",
    "plz": "76133",
    "ort": "Karlsruhe",
    "tel": "0721 1208575",
    "tel_link": "+497211208575",
    "fax": "0721 1208576",
    "mail": "info@orthokonzept.de",
    "lat": 49.0070466,
    "lng": 8.3915914,
    "maps": "https://www.google.com/maps/search/?api=1&query=orthoKonzept+GmbH+Hirschstra%C3%9Fe+35a+76133+Karlsruhe",
    "route": "https://www.google.com/maps/dir/?api=1&destination=Hirschstra%C3%9Fe+35a,+76133+Karlsruhe",
}
ZEITEN = [("Mo", "Monday"), ("Di", "Tuesday"), ("Mi", "Wednesday"), ("Do", "Thursday"), ("Fr", "Friday")]

# Doppelte Seiten im Original: gleiche Inhalte, kanonisch auf die Hauptseite
DUPLIKATE = {
    "jobs-2/": "jobs/",
    "leistungen/bewegungsanalysen/laufbandanalyse-2/": "leistungen/bewegungsanalysen/laufbandanalyse/",
    "category/allgemein/": "aktuelles/",
}
CTA_TITLE = "NA, WO DRÜCKT DER SCHUH?"


# ─────────────────────────── Hilfsfunktionen ───────────────────────────

def esc(s):
    return html.escape(s or "", quote=True)


def strip_tags(s):
    s = re.sub(r"<br\s*/?>", " ", s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xad", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def norm_key(s):
    t = "".join(c if c == "ß" else c.upper() for c in strip_tags(s))
    t = re.sub(r"\s*/\s*", " / ", t)
    t = re.sub(r"\s+([®™])", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def casing(s):
    """Versal-Überschrift -> Schreibweise aus ueberschriften.json, sonst unverändert."""
    raw = strip_tags(s)
    if raw in CASE:
        return CASE[raw]
    letters = [c for c in raw if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.8:
        return inline(s)
    k = norm_key(s)
    for cand in (k, k.replace(" / ", "/"), re.sub(r"(ORTHOPÄDISCHE|PRODUKTE|UNSERE)(?=[A-ZÄÖÜ])", r"\1 ", k)):
        if cand in CASE:
            return CASE[cand]
    print("  ? Schreibweise fehlt:", k)
    return esc(raw.capitalize())


def inline(s):
    s = (s or "").replace("\xa0", " ")
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"</?(p|span|h\d)[^>]*>", "", s)
    return s.strip()


def slug(s):
    s = strip_tags(s).lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]


def page_url(key):
    return "/" + key


def resolve_file(page_key, src):
    """Pfad eines Bildes im Original, relativ zur Seite angegeben -> Pfad relativ zu ORIG."""
    if not src:
        return None
    src = html.unescape(src).split("?")[0]
    if src.startswith("http"):
        m = re.search(r"orthokonzept\.de/(.+)$", src)
        if not m:
            return None
        src = m.group(1)
        p = src
    else:
        p = posixpath.normpath(posixpath.join(page_key, src))
    p = p.lstrip("/")
    if os.path.exists(os.path.join(ORIG, p)):
        return p
    # häufig: relative Pfade mit einer Ebene zu viel oder zu wenig
    m = re.search(r"(wp-content/.+)$", src)
    if m and os.path.exists(os.path.join(ORIG, m.group(1))):
        return m.group(1)
    return None


def best_source(page_key, info):
    """Größte verfügbare Variante aus src/srcset wählen."""
    cands = []
    if info.get("srcset"):
        for item in info["srcset"].split(","):
            bits = item.strip().split()
            if not bits:
                continue
            w = int(bits[1][:-1]) if len(bits) > 1 and bits[1].endswith("w") else 0
            cands.append((w, bits[0]))
    cands.append((int(info.get("w") or 0) if str(info.get("w") or "").isdigit() else 0, info.get("src")))
    # Originaldatei ohne -123x456-Suffix bevorzugen, falls vorhanden
    extra = []
    for w, c in cands:
        if c:
            base = re.sub(r"-\d+x\d+(?=\.\w+$)", "", c)
            if base != c:
                extra.append((99999, base))
    for w, c in sorted(extra + cands, key=lambda x: -x[0]):
        f = resolve_file(page_key, c)
        if f:
            return f
    return None


# ─────────────────────────── Bildverarbeitung ───────────────────────────

IMG_CACHE = {}
WIDTHS = (480, 800, 1200, 1800)


def media(rel_path, max_w=1800, crop=None):
    """Erzeugt AVIF + WebP in mehreren Breiten. Gibt dict mit srcset, w, h, fallback."""
    if not rel_path:
        return None
    key = (rel_path, max_w)
    if key in IMG_CACHE:
        return IMG_CACHE[key]
    src = os.path.join(ORIG, rel_path)
    name = os.path.splitext(os.path.basename(rel_path))[0]
    name = re.sub(r"-\d+x\d+$", "", name)
    name = slug(name) or "bild"
    h8 = hashlib.md5(rel_path.encode()).hexdigest()[:6]
    try:
        im = Image.open(src)
        im.load()
    except Exception as e:
        print("  ! Bild nicht lesbar", rel_path, e)
        return None
    if im.mode == "P":
        im = im.convert("RGBA")
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    ow, oh = im.size
    widths = sorted({w for w in WIDTHS if w < min(ow, max_w)} | {min(ow, max_w)})
    cut = False
    px = im.convert("RGBA")
    for x, y in ((0, 0), (ow - 1, 0), (0, oh - 1), (ow - 1, oh - 1), (ow // 2, 0), (ow - 1, oh // 2)):
        r, g, b, a = px.getpixel((x, y))
        if a < 20 or (r > 243 and g > 243 and b > 243):
            cut = True
            break
    out = {"w": min(ow, max_w), "h": round(oh * min(ow, max_w) / ow), "avif": [], "webp": [], "alpha": cut}
    os.makedirs(MEDIA, exist_ok=True)
    for w in widths:
        h = round(oh * w / ow)
        for fmt in ("avif", "webp"):
            fn = f"{name}-{h8}-{w}.{fmt}"
            dest = os.path.join(MEDIA, fn)
            if not os.path.exists(dest):
                r = im.resize((w, h), Image.LANCZOS) if w != ow else im
                if fmt == "avif":
                    r.save(dest, "AVIF", quality=58, speed=8)
                else:
                    r.save(dest, "WEBP", quality=80, method=5)
            out[fmt].append((f"/media/{fn}", w))
    out["fallback"] = out["webp"][-1][0]
    out["og"] = out["webp"][-1][0]
    IMG_CACHE[key] = out
    return out


def picture(m, alt="", sizes="100vw", cls="", loading="lazy", fetchpriority=None, extra=""):
    if not m:
        return ""
    fp = f' fetchpriority="{fetchpriority}"' if fetchpriority else ""
    avif = ", ".join(f"{u} {w}w" for u, w in m["avif"])
    webp = ", ".join(f"{u} {w}w" for u, w in m["webp"])
    c = f' class="{cls}"' if cls else ""
    return (f'<picture><source type="image/avif" srcset="{avif}" sizes="{sizes}">'
            f'<source type="image/webp" srcset="{webp}" sizes="{sizes}">'
            f'<img src="{m["fallback"]}" alt="{esc(alt)}" width="{m["w"]}" height="{m["h"]}" loading="{loading}" decoding="async"{fp}{c}{extra}></picture>')


def pic_from(page_key, info, alt=None, **kw):
    f = best_source(page_key, info)
    m = media(f)
    a = info.get("alt", "") if alt is None else alt
    if re.fullmatch(r"[\w\-]+", a or "") and ("_" in a or "-" in a):
        a = ""  # Dateinamen als Alt-Text sind wertlos
    return picture(m, a, **kw), m


# ─────────────────────────── Links ───────────────────────────

PAGE_KEYS = set(PAGES.keys())
# Links im Original auf Seiten, die es nicht mehr gibt
ALT_LINKS = {"flip-flops-nach-mass": "leistungen/theynis/"}


def fix_href(href, page_key):
    if not href:
        return "#"
    href = html.unescape(href).strip()
    if href.startswith(("mailto:", "tel:", "#")):
        return href
    if "suparo.de" in href or "orthokonzept.de" in href:
        href = "/" + re.sub(r"^https?://[^/]+/?", "", href)
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        p = href.lstrip("/")
    else:
        p = posixpath.normpath(posixpath.join(page_key, href))
    frag = ""
    if "#" in p:
        p, frag = p.split("#", 1)
        frag = "#" + frag
    p = re.sub(r"index\.html$", "", p).lstrip("./")
    if p and not p.endswith("/") and not re.search(r"\.\w{2,4}$", p):
        p += "/"
    if p in ("", "./"):
        return "/" + frag
    if p.startswith("wp-content/"):
        src = os.path.join(ORIG, p)
        dest = os.path.join(SITE, p)
        if os.path.exists(src) and not os.path.exists(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(src, dest)
        elif not os.path.exists(src):
            print("  ! Datei fehlt", p)
        return "/" + p + frag
    p = ALT_LINKS.get(p.rstrip("/").split("/")[-1], p)
    if p not in PAGE_KEYS:
        last = p.rstrip("/").split("/")[-1]
        hits = [k for k in PAGE_KEYS if k.rstrip("/").split("/")[-1] == last]
        if hits:
            p = sorted(hits, key=len)[0]
        else:
            print("  ! Link ohne Ziel", page_key, href)
    p = DUPLIKATE.get(p, p) if p != "category/allgemein/" else "aktuelles/"
    return "/" + p + frag


def fix_links_in(html_s, page_key):
    def rep(m):
        href = m.group(1)
        new = fix_href(href, page_key)
        ext = new.startswith("http")
        extra = ' target="_blank" rel="noopener"' if ext else ""
        return f'<a href="{esc(new)}"{extra}>'
    return re.sub(r'<a href="([^"]*)"(?: target="[^"]*")?>', rep, html_s)


# ─────────────────────────── Texte ───────────────────────────

BULLET = re.compile(r"^\s*(?:[•·–✓✔*]|-(?=\s))\s*")


def prose(html_s, page_key):
    """Originaltext -> saubere Absätze und Listen.

    Zeilen mit Aufzählungszeichen (•, –, -) werden zu Listen, Zeilen, die im Original mitten im
    Satz umbrechen (beginnen klein), werden angehängt, Satzende + Umbruch wird ein neuer Absatz.
    Vorhandene Listen und Links bleiben erhalten."""
    s = (html_s or "").replace("\xad", "&shy;")
    s = fix_links_in(s, page_key)
    keep = []

    def stash(m):
        keep.append(m.group(0))
        return f"\n\n§{len(keep) - 1}§\n\n"
    s = re.sub(r"<(ul|ol)\b.*?</\1>", stash, s, flags=re.S)
    s = re.sub(r"<h[4-6][^>]*>(.*?)</h[4-6]>", lambda m: f"\n\n§S§{m.group(1)}\n\n", s, flags=re.S)
    s = re.sub(r"</?p[^>]*>", "\n\n", s)
    out = []
    for para in re.split(r"\n{2,}", s):
        para = para.strip()
        if not strip_tags(para) and not re.fullmatch(r"§\d+§", para):
            continue
        m = re.fullmatch(r"§(\d+)§", para)
        if m:
            out.append(keep[int(m.group(1))])
            continue
        if para.startswith("§S§"):
            out.append(f'<p class="subhead">{para[3:].strip()}</p>')
            continue
        lines = [x.strip() for x in re.split(r"<br\s*/?>", para) if strip_tags(x)]
        expanded = []
        for ln in lines:
            if ln.count("•") >= 2:
                head, *items = re.split(r"\s*•\s*", ln)
                if strip_tags(head):
                    expanded.append(head)
                expanded += ["• " + i for i in items if strip_tags(i)]
            else:
                expanded.append(ln)
        merged = []
        for ln in expanded:
            first = strip_tags(ln)[:1]
            prev_open = merged and not re.search(r"[.!?:]\s*(</\w+>)*\s*$", merged[-1])
            in_item = merged and BULLET.match(strip_tags(merged[-1]))
            if prev_open and not BULLET.match(strip_tags(ln)) and (first.islower() or in_item):
                merged[-1] = merged[-1] + " " + ln
            else:
                merged.append(ln)
        blocks, cur, cur_list = [], [], []
        for ln in merged:
            if BULLET.match(strip_tags(ln)) or BULLET.match(ln):
                if cur:
                    blocks.append(("p", cur))
                    cur = []
                cur_list.append(BULLET.sub("", ln, count=1) if BULLET.match(ln) else re.sub(r"^(\s*<[^>]+>)\s*(?:[•·–✓✔*]|-(?=\s))\s*", r"\1", ln))
            else:
                if cur_list:
                    blocks.append(("ul", cur_list))
                    cur_list = []
                if cur and re.search(r"[.!?…]\s*(</\w+>)*\s*$", cur[-1]) and re.match(r"\s*(<[^>]+>)*\s*[A-ZÄÖÜ„\"0-9]", ln):
                    blocks.append(("p", cur))
                    cur = []
                cur.append(ln)
        if cur_list:
            blocks.append(("ul", cur_list))
        if cur:
            blocks.append(("p", cur))
        for kind, items in blocks:
            if kind == "ul" and len(items) >= 2:
                out.append('<ul class="ticks">' + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
            elif kind == "ul":
                out.append(f"<p>{items[0]}</p>")
            else:
                out.append("<p>" + "<br>".join(items) + "</p>")
    return "".join(out)


def btn(text, href, page_key, variant="primary", icon="arrow"):
    t = casing(text)
    h = fix_href(href, page_key)
    ext = ' target="_blank" rel="noopener"' if h.startswith("http") else ""
    ic = ICONS.get(icon, "")
    return f'<a class="btn btn--{variant}" href="{esc(h)}"{ext}><span>{t}</span>{ic}</a>'


ICONS = {
    "arrow": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    "phone": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/></svg>',
    "mail": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/></svg>',
    "pin": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0z"/><circle cx="12" cy="10" r="3"/></svg>',
    "clock": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
    "check": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
    "calendar": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>',
    "route": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="m3 11 19-9-9 19-2-8-8-2z"/></svg>',
    "play": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor" stroke="none"/></svg>',
    "chev": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
    "external": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>',
    "spark": '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>',
}


def heading(b, level=None, cls=""):
    lv = level or b.get("level", "h2")
    if not lv.startswith("h"):
        lv = "p"
    c = f' class="{cls}"' if cls else ""
    return f"<{lv}{c}>{casing(b['html'])}</{lv}>"


# ─────────────────────────── Sektionen klassifizieren ───────────────────────────

def is_cta_section(sec):
    hs = [b for b in sec["blocks"] if b["type"] == "heading"]
    return bool(hs) and norm_key(hs[0]["html"]) == CTA_TITLE


def clean_sections(key, page):
    secs = []
    for s in page["sections"]:
        cls = s.get("classes", "")
        if "elementor-hidden-desktop" in cls:
            continue
        bl = []
        for b in s["blocks"]:
            if b["type"] == "heading" and strip_tags(b["html"]) in (".", ""):
                continue
            if b["type"] == "text" and not strip_tags(b["html"]):
                continue
            if b["type"] == "text" and "formcraft" in b["html"]:
                bl.append({"type": "form", "fields": []})
                continue
            if b["type"] == "image" and "Logo-Ortho-Konzept" in (b.get("src") or ""):
                continue
            bl.append(b)
        if not bl:
            continue
        secs.append({**s, "blocks": bl})
    return secs


def groups_by_image(blocks):
    """Teilt Blockfolge in Gruppen, die jeweils mit einem Bild oder h3 beginnen."""
    groups, cur = [], None
    for b in blocks:
        starts = b["type"] == "image" or (b["type"] == "heading" and b.get("level") == "h3" and (cur is None or any(x["type"] == "heading" for x in cur)))
        if starts and cur and (b["type"] == "image" and any(x["type"] != "image" for x in cur) or b["type"] == "heading"):
            groups.append(cur)
            cur = None
        if cur is None:
            cur = []
        cur.append(b)
    if cur:
        groups.append(cur)
    return groups


def has_address(sec):
    return any(b["type"] == "heading" and strip_tags(b["html"]).lower() == "orthokonzept gmbh" for b in sec["blocks"])


def without_address(blocks):
    """Blöcke vor dem Adressblock (h3 orthoKonzept GmbH, Adresse, Telefon, Mail, Zeiten, Anfahrt-Button)."""
    out = []
    for b in blocks:
        if b["type"] == "heading" and strip_tags(b["html"]).lower() == "orthokonzept gmbh":
            break
        out.append(b)
    return out


def classify(sec):
    bl = sec["blocks"]
    if any(b["type"] == "form" for b in bl):
        return "form"
    if has_address(sec):
        return "address"
    types = [b["type"] for b in bl]
    n = {t: types.count(t) for t in set(types)}
    hs = [b for b in bl if b["type"] == "heading"]
    if types == ["heading"]:
        return "title"
    for t in ("posts", "logos", "accordion", "form", "map"):
        if t in n:
            return t
    if "gallery" in n:
        return "gallery"
    if "video" in n:
        return "videos"
    if set(types) == {"image"}:
        return "images"
    texts = [b for b in bl if b["type"] == "text"]
    if set(types) <= {"text"} and len(texts) >= 3 and all(len(strip_tags(t["html"])) < 260 for t in texts):
        return "checklist"
    h3_img_groups = 0
    if n.get("image", 0) >= 2 and n.get("heading", 0) >= 2:
        gs = groups_by_image(bl)
        h3_img_groups = sum(1 for g in gs if any(x["type"] == "image" for x in g) and any(x["type"] == "heading" for x in g))
        if h3_img_groups >= 2 and all(x.get("level") in ("h3", "h2") for x in hs):
            # mehrere gleichartige Gruppen -> Karten
            levels = {x.get("level") for x in hs}
            if levels == {"h3"} or h3_img_groups >= 3:
                return "cards"
    if hs and norm_key(hs[0]["html"]) in ("BRAUCHEN SIE HILFE?",):
        return "help"
    if "image" in n:
        return "split"
    return "prose"


# ─────────────────────────── Renderer ───────────────────────────

def br_list(html_s, key):
    """Nach prose(): ein Absatz aus vielen kurzen Zeilen -> Liste; lange Listen zweispaltig (Fachseiten)."""
    if not key.startswith(("leistungen/", "service/", "produkte/")):
        return None
    out = prose(html_s, key)
    m = re.fullmatch(r"<p>(.*)</p>", out, flags=re.S)
    if m and "</p><p>" not in m.group(1):
        parts = [x.strip() for x in m.group(1).split("<br>") if strip_tags(x)]
        if len(parts) >= 5 and max(len(strip_tags(x)) for x in parts) <= 220:
            return '<ul class="ticks ticks--cols">' + "".join(f"<li>{x}</li>" for x in parts) + "</ul>"
    m = re.fullmatch(r'<ul class="ticks">(.*)</ul>', out, flags=re.S)
    if m and m.group(1).count("<li>") >= 6 and all(len(strip_tags(x)) < 160 for x in m.group(1).split("</li>")):
        return '<ul class="ticks ticks--cols">' + m.group(1) + "</ul>"
    return None


def render_blocks_content(blocks, key, heading_level_map=None):
    """Inhaltsspalte: Überschriften, Texte, Listen, Buttons in Reihenfolge."""
    out, btns = [], []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        t = b["type"]
        if t == "heading":
            lv = b.get("level", "h2")
            if lv == "h1":
                lv = "h2"
            nxt = blocks[i + 1] if i + 1 < len(blocks) else None
            if lv in ("h3", "h4") and nxt and nxt["type"] == "heading" and nxt.get("level") == "h2":
                out.append(f'<p class="eyebrow">{casing(b["html"])}</p>')
                i += 1
                continue
            out.append(heading(b, lv))
            # kurze Textfolge nach h3 ("Materialeigenschaften:") als Liste
            j = i + 1
            run = []
            while j < len(blocks) and blocks[j]["type"] == "text" and len(strip_tags(blocks[j]["html"])) < 200:
                run.append(blocks[j])
                j += 1
            if len(run) >= 3:
                out.append('<ul class="ticks">' + "".join(f"<li>{inline(prose(r['html'], key))}</li>" for r in run) + "</ul>")
                i = j
                continue
        elif t == "text":
            lst = br_list(b["html"], key)
            out.append(lst if lst else f'<div class="rich">{prose(b["html"], key)}</div>')
        elif t == "list":
            out.append('<ul class="ticks">' + "".join(
                f'<li>{esc(it["text"])}</li>' if not it.get("href") else f'<li><a href="{esc(fix_href(it["href"], key))}">{esc(it["text"])}</a></li>'
                for it in b["items"]) + "</ul>")
        elif t == "button":
            btns.append(b)
        elif t == "card":
            out.append(f'<div class="rich"><h3>{esc(b["title"])}</h3>{prose(b["html"], key)}</div>')
        i += 1
    if btns:
        out.append('<div class="actions">' + "".join(
            btn(b["text"], b["href"], key, "primary" if k == 0 else "ghost") for k, b in enumerate(btns)) + "</div>")
    return "\n".join(out)


def sec_wrap(inner, cls="", sid=None, tone=""):
    idattr = f' id="{sid}"' if sid else ""
    return f'<section class="sec {cls} {tone}"{idattr}><div class="wrap">{inner}</div></section>'


def render_split(sec, key, idx, pending_title=None):
    bl = sec["blocks"]
    imgs = [b for b in bl if b["type"] == "image"]
    content = [b for b in bl if b["type"] != "image"]
    # h3-Gruppe vor h2 -> h2-Gruppe nach vorn
    hs = [k for k, b in enumerate(content) if b["type"] == "heading"]
    if hs and content[hs[0]].get("level") == "h3":
        h2s = [k for k in hs if content[k].get("level") == "h2"]
        if h2s:
            k = h2s[0]
            content = content[k:] + content[:k]
    img_first = bl[0]["type"] == "image"
    reverse = img_first
    media_html = ""
    if len(imgs) == 1:
        p, m = pic_from(key, imgs[0], sizes="(min-width: 960px) 46vw, 100vw")
        cut = "media--cutout" if m and m.get("alpha") else ""
        if m and m["w"] < 700:
            cut += " media--small"
        media_html = f'<figure class="media {cut}">{p}</figure>'
    else:
        items = "".join(f'<figure class="media">{pic_from(key, im, sizes="(min-width: 960px) 23vw, 50vw")[0]}</figure>' for im in imgs[:4])
        media_html = f'<div class="collage collage--{min(len(imgs), 4)}">{items}</div>'
    head = f'<h2>{casing(pending_title["html"])}</h2>' if pending_title else ""
    body = render_blocks_content(content, key)
    inner = f'<div class="split {"split--rev" if reverse else ""}"><div class="split__text reveal">{head}{body}</div><div class="split__media reveal">{media_html}</div></div>'
    return sec_wrap(inner, "sec--split")


def render_cards(sec, key, pending_title=None):
    bl = sec["blocks"]
    lead = []
    # führende Überschrift/Text ohne Bild als Kopf
    while bl and bl[0]["type"] in ("heading", "text") and bl[0].get("level") != "h3":
        lead.append(bl[0])
        bl = bl[1:]
    gs = groups_by_image(bl)
    cards = []
    for g in gs:
        imgs = [b for b in g if b["type"] == "image"]
        hs = [b for b in g if b["type"] == "heading"]
        texts = [b for b in g if b["type"] == "text"]
        bts = [b for b in g if b["type"] == "button"]
        href = fix_href(bts[0]["href"], key) if bts else None
        img_html = ""
        if imgs:
            p, m = pic_from(key, imgs[0], sizes="(min-width: 1100px) 360px, (min-width: 700px) 45vw, 100vw")
            cut = " card__img--cutout" if m and m.get("alpha") else ""
            img_html = f'<div class="card__img{cut}">{p}</div>'
        title = casing(hs[0]["html"]) if hs else ""
        extra_heads = "".join(heading(h, "h4") for h in hs[1:])
        tx = "".join(prose(t["html"], key) for t in texts)
        if len(texts) >= 3 and all(len(strip_tags(t["html"])) < 140 for t in texts):
            tx = '<ul class="ticks">' + "".join(f"<li>{inline(t['html'])}</li>" for t in texts) + "</ul>"
        link = ""
        if href:
            link = f'<a class="card__link" href="{esc(href)}"><span>{casing(bts[0]["text"])}</span>{ICONS["arrow"]}</a>'
        tag = "article"
        cards.append(f'<{tag} class="card reveal">{img_html}<div class="card__body"><h3>{title}</h3>{extra_heads}<div class="rich">{tx}</div>{link}</div></{tag}>')
    head = ""
    if pending_title:
        head = f'<header class="sec__head reveal"><h2>{casing(pending_title["html"])}</h2></header>'
    if lead:
        head += f'<header class="sec__head reveal">{render_blocks_content(lead, key)}</header>'
    cols = 3 if len(cards) % 3 == 0 or len(cards) > 4 else 2
    if len(cards) == 4:
        cols = 4 if all("card__img--cutout" in c or "card__img" not in c for c in cards) else 2
    return sec_wrap(head + f'<div class="cards cards--{cols}">' + "".join(cards) + "</div>", "sec--cards")


def render_checklist(sec, key, pending_title=None):
    items = [b for b in sec["blocks"] if b["type"] == "text"]
    head = f'<header class="sec__head reveal"><h2>{casing(pending_title["html"])}</h2></header>' if pending_title else ""
    lis = "".join(f'<li class="reveal">{ICONS["check"]}<span>{inline(prose(b["html"], key))}</span></li>' for b in items)
    return sec_wrap(head + f'<ul class="checklist">{lis}</ul>', "sec--checklist", tone="tone-soft")


def render_prose(sec, key, pending_title=None):
    head = f'<h2>{casing(pending_title["html"])}</h2>' if pending_title else ""
    body = render_blocks_content(sec["blocks"], key)
    long = sum(len(strip_tags(b.get("html", ""))) for b in sec["blocks"] if b["type"] == "text")
    cls = "prose prose--long" if long > 2500 else "prose"
    return sec_wrap(f'<div class="{cls} reveal">{head}{body}</div>', "sec--prose")


def render_gallery(sec, key, pending_title=None, logos=False):
    imgs = []
    heads = [b for b in sec["blocks"] if b["type"] == "heading"]
    for b in sec["blocks"]:
        if b["type"] == "gallery":
            imgs += b["images"]
        elif b["type"] == "image":
            imgs.append(b)
    title = pending_title or (heads[0] if heads else None)
    head = f'<header class="sec__head reveal"><h2>{casing(title["html"])}</h2></header>' if title else ""
    if logos:
        items = []
        for im in imgs:
            p, m = pic_from(key, im, sizes="200px", cls="logo-img")
            items.append(f'<li>{p}</li>')
        track = "".join(items)
        return sec_wrap(head + f'<div class="marquee" aria-label="Referenzen"><ul class="marquee__track">{track}</ul><ul class="marquee__track" aria-hidden="true">{track}</ul></div>', "sec--logos")
    figs = []
    for k, im in enumerate(imgs):
        f = best_source(key, {"src": im.get("full") or im["src"], "srcset": im.get("srcset")}) or best_source(key, im)
        m = media(f)
        if not m:
            continue
        alt = im.get("alt", "")
        if re.fullmatch(r"[\w\-]+", alt or ""):
            alt = ""
        figs.append(f'<figure class="gal__item reveal"><button class="gal__btn" type="button" data-full="{m["webp"][-1][0]}" data-w="{m["w"]}" data-h="{m["h"]}" aria-label="Bild vergrößern{": " + esc(alt) if alt else ""}">{picture(m, alt, sizes="(min-width: 1100px) 360px, (min-width: 700px) 33vw, 50vw")}</button></figure>')
    cols = "gal--2" if len(figs) == 2 else ("gal--3" if len(figs) in (3, 6, 9) else "")
    return sec_wrap(head + f'<div class="gal {cols}">' + "".join(figs) + "</div>", "sec--gallery")


def yt_id(url):
    m = re.search(r"(?:v=|youtu\.be/|embed/)([\w-]{11})", url or "")
    return m.group(1) if m else None


def render_videos(sec, key, pending_title=None):
    bl = sec["blocks"]
    items, cur = [], None
    for b in bl:
        if b["type"] == "video":
            cur = {"v": b, "caption": None, "texts": []}
            items.append(cur)
        elif cur and b["type"] == "heading" and not cur["caption"]:
            cur["caption"] = b
        elif cur:
            cur["texts"].append(b)
    rest = [b for it in items for b in it["texts"]]
    out = []
    for it in items:
        v = it["v"]
        cap = f'<figcaption>{casing(it["caption"]["html"])}</figcaption>' if it["caption"] and not rest else ""
        vid = yt_id(v.get("youtube"))
        if vid:
            thumb = youtube_thumb(vid)
            th = picture(thumb, "", sizes="(min-width: 960px) 560px, 100vw") if thumb else ""
            out.append(f'<figure class="video reveal"><button class="video__btn" type="button" data-yt="{vid}" aria-label="Video abspielen (lädt YouTube)">{th}<span class="video__play">{ICONS["play"]}</span><span class="video__note">Mit Klick wird YouTube geladen (Datenschutz)</span></button>{cap}</figure>')
        elif v.get("hosted"):
            f = resolve_file(key, v["hosted"])
            if f:
                dest = os.path.join(SITE, "media", os.path.basename(f))
                if not os.path.exists(dest):
                    shutil.copy(os.path.join(ORIG, f), dest)
                out.append(f'<figure class="video reveal"><video controls preload="metadata" playsinline src="/media/{esc(os.path.basename(f))}"></video>{cap}</figure>')
    head = f'<header class="sec__head reveal"><h2>{casing(pending_title["html"])}</h2></header>' if pending_title else ""
    if rest:
        # Video neben Text (Pedographie)
        return sec_wrap(f'<div class="split split--rev"><div class="split__text reveal">{render_blocks_content(rest, key)}</div><div class="split__media">{"".join(out)}</div></div>', "sec--split")
    return sec_wrap(head + f'<div class="videos">{"".join(out)}</div>', "sec--videos")


def youtube_thumb(vid):
    dest_rel = f"_yt/{vid}.jpg"
    dest = os.path.join(ORIG, dest_rel)
    if not os.path.exists(dest):
        import urllib.request
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        for q in ("maxresdefault", "hqdefault"):
            try:
                data = urllib.request.urlopen(f"https://i.ytimg.com/vi/{vid}/{q}.jpg", timeout=20).read()
                if len(data) > 5000:
                    open(dest, "wb").write(data)
                    break
            except Exception:
                pass
    return media(dest_rel, 1280) if os.path.exists(dest) else None


def render_accordion(sec, key, pending_title=None):
    heads = [b for b in sec["blocks"] if b["type"] == "heading"]
    acc = [b for b in sec["blocks"] if b["type"] == "accordion"]
    title = pending_title or (heads[0] if heads else None)
    head = f'<header class="sec__head reveal"><h2>{casing(title["html"])}</h2></header>' if title else ""
    items = []
    for a in acc:
        for k, it in enumerate(a["items"]):
            items.append(f'<details class="acc reveal"{" open" if k == 0 else ""}><summary><span>{esc(it["title"])}</span>{ICONS["chev"]}</summary><div class="acc__body rich">{prose(it["html"], key)}</div></details>')
    return sec_wrap(head + f'<div class="accs">{"".join(items)}</div>', "sec--acc")


def render_logos(sec, key, pending_title=None):
    items = []
    for b in sec["blocks"]:
        if b["type"] != "logos":
            continue
        for it in b["items"]:
            p = ""
            if it.get("img"):
                p = pic_from(key, it["img"], sizes="240px", cls="logo-img")[0]
            name = it.get("name", "")
            sub = strip_tags(it.get("text", "").replace(name, "", 1)).strip()
            href = it.get("href")
            inner = f'<div class="partner__logo">{p}</div><div class="partner__txt"><strong>{esc(name)}</strong>{f"<span>{esc(sub)}</span>" if sub else ""}</div>'
            if href:
                items.append(f'<li class="partner reveal"><a href="{esc(href)}" target="_blank" rel="noopener">{inner}{ICONS["external"]}</a></li>')
            else:
                items.append(f'<li class="partner reveal"><div>{inner}</div></li>')
    head = f'<header class="sec__head reveal"><h2>{casing(pending_title["html"])}</h2></header>' if pending_title else ""
    return head, items


def render_posts_grid(items, limit=None, cls=""):
    cards = []
    for p in items[:limit] if limit else items:
        img = p.get("img_html", "")
        if not img:
            img = '<img class="post-card__ph" src="/assets/img/logo.png" alt="" width="120" height="120" loading="lazy">'
        cards.append(f'<article class="post-card reveal"><a href="{esc(p["url"])}"><div class="post-card__img">{img}</div><div class="post-card__body"><time datetime="{p["iso"]}">{esc(p["date"])}</time><h3>{esc(p["title"])}</h3><p>{esc(p["excerpt"])}</p><span class="card__link"><span>Weiterlesen</span>{ICONS["arrow"]}</span></div></a></article>')
    return f'<div class="posts {cls}">' + "".join(cards) + "</div>"


# ─────────────────────────── Beiträge ───────────────────────────

MONATE = {m: i + 1 for i, m in enumerate(["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"])}


def parse_de_date(s):
    m = re.match(r"(\d{1,2})\. (\w+) (\d{4})", s or "")
    if not m:
        return None
    return datetime.date(int(m.group(3)), MONATE.get(m.group(2), 1), int(m.group(1)))


def collect_posts():
    posts = []
    for key, p in PAGES.items():
        if not p.get("post_title") or key.startswith("category/"):
            continue
        blocks = [b for s in p["sections"] for b in s["blocks"]]
        text = next((b for b in blocks if b["type"] == "text"), None)
        imgs = [b for b in blocks if b["type"] == "image"]
        d = parse_de_date(p.get("post_date")) or datetime.date(2023, 1, 1)
        img_html, m = ("", None)
        if imgs:
            img_html, m = pic_from(key, imgs[0], alt=imgs[0].get("alt") or p["post_title"], sizes="(min-width: 1100px) 380px, (min-width: 700px) 45vw, 100vw")
        ex = strip_tags(text["html"]) if text else ""
        ex = (ex[:150].rsplit(" ", 1)[0] + " …") if len(ex) > 150 else ex
        posts.append({"key": key, "url": "/" + key, "title": strip_tags(p["post_title"]), "date": d.strftime("%d.%m.%Y"),
                      "iso": d.isoformat(), "d": d, "excerpt": ex, "img_html": img_html, "img": m})
    posts.sort(key=lambda x: x["d"], reverse=True)
    return posts


# ─────────────────────────── Navigation ───────────────────────────

NAV_TEXT = {
    "ELEKTRONISCHE FUßDRUCKMESSUNG | PEDOGRAPHIE": "Elektronische Fußdruckmessung | Pedographie",
    "SCHUHINFORMATION & -BERATUNG": "Schuhinformation & -beratung",
    "KOSTENERSTATTUNG SICHERHEITSSCHUHE": "Kostenerstattung Sicherheitsschuhe",
}


def nav_text(t):
    t = re.sub(r"^\s*[»«]\s*", "", t).strip()
    return NAV_TEXT.get("".join(c if c == "ß" else c.upper() for c in t), t)


def nav_tree():
    def conv(items):
        out = []
        for it in items:
            out.append({"text": nav_text(it["text"]), "href": fix_href(it["href"], ""), "children": conv(it["children"])})
        return out
    return conv(D["nav"])


NAV = nav_tree()


def is_active(href, cur):
    return href != "/" and ("/" + cur).startswith(href) or (href == "/" and cur == "")


def render_header(cur):
    items = []
    for it in NAV:
        if it["text"] == "Home":
            continue
        act = " is-active" if is_active(it["href"], cur) else ""
        if it["children"]:
            if it["text"] == "Leistungen":
                cols = []
                for c in it["children"]:
                    if c["children"]:
                        sub = "".join(f'<li><a href="{c2["href"]}">{esc(c2["text"])}</a></li>' for c2 in c["children"])
                        cols.append(f'<div class="mega__col"><a class="mega__title" href="{c["href"]}">{esc(c["text"])}</a><ul>{sub}</ul></div>')
                singles = "".join(f'<li><a href="{c["href"]}">{esc(c["text"])}</a></li>' for c in it["children"] if not c["children"])
                cols.append(f'<div class="mega__col"><span class="mega__title">Weitere Leistungen</span><ul>{singles}</ul>'
                            f'<a class="mega__promo" href="/leistungen/theynis/#konfigurator"><span class="mega__promo-k">Neu</span><strong>THeynis-Konfigurator</strong><span>Deinen Maß-Flipflop gestalten</span></a></div>')
                panel = f'<div class="mega" role="region" aria-label="Leistungen"><div class="mega__inner"><a class="mega__all" href="{it["href"]}">Alle Leistungen im Überblick {ICONS["arrow"]}</a><div class="mega__cols">{"".join(cols)}</div></div></div>'
                items.append(f'<li class="nav__item has-mega{act}"><a class="nav__link" href="{it["href"]}" aria-haspopup="true" aria-expanded="false">{esc(it["text"])}{ICONS["chev"]}</a>{panel}</li>')
            else:
                sub = "".join(f'<li><a href="{c["href"]}">{esc(c["text"])}</a></li>' for c in it["children"])
                items.append(f'<li class="nav__item has-drop{act}"><a class="nav__link" href="{it["href"]}" aria-haspopup="true" aria-expanded="false">{esc(it["text"])}{ICONS["chev"]}</a><ul class="drop">{sub}</ul></li>')
        else:
            if it["text"] == "Kontakt":
                continue
            items.append(f'<li class="nav__item{act}"><a class="nav__link" href="{it["href"]}">{esc(it["text"])}</a></li>')
    # mobiles Menü
    def mob(items, lvl=0):
        out = []
        for it in items:
            if it["children"]:
                out.append(f'<li><details><summary><a href="{it["href"]}">{esc(it["text"])}</a>{ICONS["chev"]}</summary><ul>{mob(it["children"], lvl + 1)}</ul></details></li>')
            else:
                out.append(f'<li><a href="{it["href"]}">{esc(it["text"])}</a></li>')
        return "".join(out)
    logo = '<img src="/assets/img/logo.png" alt="orthoKonzept – Vom Maßschuh bis zur Sportler-Versorgung, seit 2009" width="64" height="64">'
    return f'''<a class="skip" href="#inhalt">Zum Inhalt springen</a>
<header class="hdr" data-hdr>
  <div class="hdr__bar">
    <div class="wrap hdr__barin">
      <span class="hdr__status" data-open-status>{ICONS["clock"]}<span>Mo–Fr 9–13 & 14–18 Uhr</span></span>
      <a href="tel:{FIRMA["tel_link"]}">{ICONS["phone"]}<span>{FIRMA["tel"]}</span></a>
      <a href="mailto:{FIRMA["mail"]}">{ICONS["mail"]}<span>{FIRMA["mail"]}</span></a>
      <a href="/anfahrt/">{ICONS["pin"]}<span>{FIRMA["strasse"]}, {FIRMA["plz"]} {FIRMA["ort"]}</span></a>
    </div>
  </div>
  <div class="wrap hdr__in">
    <a class="brand" href="/" aria-label="orthoKonzept Startseite">{logo}<span class="brand__txt"><span class="brand__name">ortho<b>Konzept</b></span><span class="brand__claim">Orthopädie-Schuhtechnik Karlsruhe</span></span></a>
    <nav class="nav" aria-label="Hauptnavigation"><ul class="nav__list">{"".join(items)}</ul></nav>
    <div class="hdr__cta">
      <a class="btn btn--ghost btn--sm hide-sm" href="tel:{FIRMA["tel_link"]}">{ICONS["phone"]}<span>Anrufen</span></a>
      <a class="btn btn--primary btn--sm" href="/kontakt/"><span>Termin vereinbaren</span></a>
      <button class="burger" type="button" aria-label="Menü öffnen" aria-expanded="false" aria-controls="mnav" data-burger><span></span><span></span><span></span></button>
    </div>
  </div>
</header>
<div class="mnav" id="mnav" hidden>
  <nav aria-label="Mobile Navigation"><ul class="mnav__list">{mob(NAV)}</ul></nav>
  <div class="mnav__foot">
    <a class="btn btn--primary" href="/kontakt/"><span>Termin vereinbaren</span>{ICONS["arrow"]}</a>
    <a class="btn btn--ghost" href="tel:{FIRMA["tel_link"]}">{ICONS["phone"]}<span>{FIRMA["tel"]}</span></a>
  </div>
</div>'''


def render_closing_cta():
    home = PAGES[""]
    sec = next(s for s in home["sections"] if is_cta_section(s))
    txt = next(b for b in sec["blocks"] if b["type"] == "text")
    return f'''<section class="closing" aria-labelledby="closing-h">
  <div class="wrap closing__in">
    <div class="closing__text reveal">
      <p class="eyebrow">Persönlich für Sie da</p>
      <h2 id="closing-h">{casing(CTA_TITLE)}</h2>
      <div class="rich">{prose(txt["html"], "")}</div>
      <div class="actions"><a class="btn btn--primary btn--lg" href="/kontakt/"><span>{casing("HIER KONTAKTIEREN")}</span>{ICONS["arrow"]}</a><a class="btn btn--light btn--lg" href="tel:{FIRMA["tel_link"]}">{ICONS["phone"]}<span>{FIRMA["tel"]}</span></a></div>
    </div>
    <div class="closing__card reveal">
      <dl class="facts">
        <div><dt>{ICONS["pin"]}Adresse</dt><dd>{FIRMA["name"]}<br>{FIRMA["strasse"]}<br>{FIRMA["plz"]} {FIRMA["ort"]}</dd></div>
        <div><dt>{ICONS["clock"]}Öffnungszeiten</dt><dd>Montag – Freitag<br>09.00 – 13.00 Uhr | 14.00 – 18.00 Uhr<br><small>oder nach Vereinbarung</small><span class="status" data-open-badge></span></dd></div>
        <div><dt>{ICONS["mail"]}E-Mail</dt><dd><a href="mailto:{FIRMA["mail"]}">{FIRMA["mail"]}</a></dd></div>
      </dl>
      <a class="closing__route" href="{FIRMA["route"]}" target="_blank" rel="noopener">{ICONS["route"]}<span>Route planen</span></a>
    </div>
  </div>
</section>'''


def render_footer():
    lst = lambda items: "".join(f'<li><a href="{it["href"]}">{esc(it["text"])}</a></li>' for it in items)
    leist = next(i for i in NAV if i["text"] == "Leistungen")
    orth = next(c for c in leist["children"] if c["text"] == "Orthopädie")
    weitere = [c for c in leist["children"] if c["text"] != "Orthopädie"]
    unternehmen = [{"text": "Über uns", "href": "/ueber-uns/"}, {"text": "Unsere Partner", "href": "/ueber-uns/partner/"},
                   {"text": "Präqualifizierung / Zertifizierung", "href": "/ueber-uns/zertifizierung/"}, {"text": "Aktuelles", "href": "/aktuelles/"},
                   {"text": "Jobs", "href": "/jobs/"}, {"text": "Produkte", "href": "/produkte/"}, {"text": "Service", "href": "/service/"}, {"text": "Anfahrt", "href": "/anfahrt/"}]
    year = datetime.date.today().year
    return f'''<footer class="ftr">
  <div class="wrap ftr__grid">
    <div class="ftr__brand">
      <img src="/assets/img/logo.png" alt="" width="112" height="112" loading="lazy">
      <p>Orthopädie-Schuhtechnik in Karlsruhe. Vom Maßschuh bis zur Sportler-Versorgung, seit 2009.</p>
      <p class="ftr__contact"><a href="tel:{FIRMA["tel_link"]}">{ICONS["phone"]}{FIRMA["tel"]}</a><a href="mailto:{FIRMA["mail"]}">{ICONS["mail"]}{FIRMA["mail"]}</a><a href="/anfahrt/">{ICONS["pin"]}{FIRMA["strasse"]}, {FIRMA["plz"]} {FIRMA["ort"]}</a></p>
    </div>
    <nav class="ftr__col" aria-label="Orthopädie"><h2>Orthopädie</h2><ul>{lst(orth["children"])}</ul></nav>
    <nav class="ftr__col" aria-label="Leistungen"><h2>Leistungen</h2><ul>{lst([{"text": "Alle Leistungen", "href": "/leistungen/"}] + [{"text": c["text"], "href": c["href"]} for c in weitere])}</ul></nav>
    <nav class="ftr__col" aria-label="Unternehmen"><h2>Unternehmen</h2><ul>{lst(unternehmen)}</ul></nav>
  </div>
  <div class="wrap ftr__legal">
    <p>© {year} {FIRMA["name"]} · Fax {FIRMA["fax"]}</p>
    <ul><li><a href="/impressum/">Impressum</a></li><li><a href="/datenschutzerklaerung/">Datenschutz</a></li><li><a href="/nutzungsbedingungen/">Nutzungsbedingungen</a></li><li><a href="/erklaerung-zur-barrierefreiheit/">Barrierefreiheit</a></li><li><button type="button" class="linkbtn" data-consent-open>Cookie-Einstellungen</button></li></ul>
  </div>
</footer>
<nav class="dock" aria-label="Schnellzugriff">
  <a href="tel:{FIRMA["tel_link"]}">{ICONS["phone"]}<span>Anrufen</span></a>
  <a href="{FIRMA["route"]}" target="_blank" rel="noopener">{ICONS["route"]}<span>Route</span></a>
  <a class="dock__main" href="/kontakt/">{ICONS["calendar"]}<span>Termin</span></a>
</nav>
<div class="consent" data-consent hidden role="dialog" aria-modal="false" aria-labelledby="consent-h">
  <div class="consent__in">
    <h2 id="consent-h">Datenschutz-Einstellungen</h2>
    <p>Wir verwenden technisch notwendige Speicherungen. Mit Ihrer Zustimmung nutzen wir zusätzlich Statistik (Google Analytics über den Google Tag Manager), um unser Angebot zu verbessern. Externe Inhalte wie Google Maps oder YouTube laden wir erst, wenn Sie diese anklicken. Mehr in der <a href="/datenschutzerklaerung/">Datenschutzerklärung</a>.</p>
    <div class="consent__actions"><button class="btn btn--ghost btn--sm" type="button" data-consent-choice="essential">Nur notwendige</button><button class="btn btn--primary btn--sm" type="button" data-consent-choice="all">Alle akzeptieren</button></div>
  </div>
</div>
<dialog class="lightbox" data-lightbox aria-label="Bildansicht"><button class="lightbox__close" type="button" aria-label="Schließen" data-lb-close>×</button><button class="lightbox__nav lightbox__prev" type="button" aria-label="Vorheriges Bild" data-lb-prev>‹</button><button class="lightbox__nav lightbox__next" type="button" aria-label="Nächstes Bild" data-lb-next>›</button></dialog>'''


# ─────────────────────────── SEO ───────────────────────────

def breadcrumb(key):
    crumbs = [("Startseite", "/")]
    parts = key.strip("/").split("/") if key else []
    acc = ""
    for p in parts:
        acc += p + "/"
        if acc in PAGES and acc != key:
            crumbs.append((page_name(acc), "/" + acc))
    if key:
        crumbs.append((page_name(key), "/" + key))
    return crumbs


def page_name(key):
    for it in walk_nav(NAV):
        if it["href"] == "/" + key:
            return it["text"]
    p = PAGES.get(key, {})
    if p.get("post_title"):
        return strip_tags(p["post_title"])
    h1 = find_h1(p)
    return strip_tags(casing(h1)) if h1 else key.strip("/").split("/")[-1]


def walk_nav(items):
    for it in items:
        yield it
        yield from walk_nav(it["children"])


def find_h1(p):
    for s in p.get("sections", []):
        for b in s["blocks"]:
            if b["type"] == "heading" and b.get("level") == "h1":
                return b["html"]
    return None


BUSINESS_ID = DOMAIN + "/#business"


def jsonld_business():
    return {
        "@type": ["LocalBusiness", "MedicalBusiness"],
        "@id": BUSINESS_ID,
        "name": FIRMA["name"],
        "alternateName": ["orthoKonzept", "Ortho Konzept Karlsruhe"],
        "description": "Fachbetrieb für Orthopädie-Schuhtechnik in Karlsruhe: orthopädische Maßschuhe, Einlagen und Sporteinlagen, Schuhzurichtungen, Bandagen und Orthesen, Kompressionsversorgung, Diabetiker-Schutzschuhe, Bewegungsanalysen (Laufbandanalyse, Pedographie), Laufschuhberatung, orthopädische Sicherheitsschuhe und THeynis Maß-Sandalen.",
        "url": DOMAIN + "/",
        "logo": DOMAIN + "/assets/img/logo-512.png",
        "image": DOMAIN + "/assets/img/og-default.jpg",
        "telephone": "+49 721 1208575",
        "faxNumber": "+49 721 1208576",
        "email": FIRMA["mail"],
        "foundingDate": "2009",
        "address": {"@type": "PostalAddress", "streetAddress": "Hirschstraße 35a", "postalCode": "76133", "addressLocality": "Karlsruhe", "addressRegion": "Baden-Württemberg", "addressCountry": "DE"},
        "geo": {"@type": "GeoCoordinates", "latitude": FIRMA["lat"], "longitude": FIRMA["lng"]},
        "hasMap": FIRMA["maps"],
        "openingHoursSpecification": [
            {"@type": "OpeningHoursSpecification", "dayOfWeek": [e for _, e in ZEITEN], "opens": "09:00", "closes": "13:00"},
            {"@type": "OpeningHoursSpecification", "dayOfWeek": [e for _, e in ZEITEN], "opens": "14:00", "closes": "18:00"},
        ],
        "areaServed": [{"@type": "City", "name": c} for c in ("Karlsruhe", "Ettlingen", "Rheinstetten", "Stutensee", "Eggenstein-Leopoldshafen", "Pfinztal", "Weingarten (Baden)", "Bruchsal")],
        "medicalSpecialty": "Orthopedic",
        "knowsAbout": ["Orthopädieschuhtechnik", "Orthopädische Einlagen", "Orthopädische Maßschuhe", "Sensomotorische Einlagen", "Kompressionstherapie", "Diabetisches Fußsyndrom", "Laufbandanalyse", "Pedographie", "Sicherheitsschuhe nach DGUV 112-191"],
        "hasCredential": [
            {"@type": "EducationalOccupationalCredential", "credentialCategory": "Zertifizierung", "name": "DIN EN ISO 13485"},
            {"@type": "EducationalOccupationalCredential", "credentialCategory": "Präqualifizierung", "name": "Präqualifizierung nach § 126 Abs. 1 S. 2 SGB V"},
        ],
        "founder": [{"@type": "Person", "name": n} for n in ("Jan Theune", "Gunnar Heyne", "Rainer Granget")],
        "brand": {"@type": "Brand", "name": "THeynis"},
        "priceRange": "€€",
        "currenciesAccepted": "EUR",
        "sameAs": [],
    }


def jsonld(key, meta, kind, crumbs, extra=None):
    url = DOMAIN + "/" + key
    graph = [
        {"@type": "WebSite", "@id": DOMAIN + "/#website", "url": DOMAIN + "/", "name": "orthoKonzept", "inLanguage": "de-DE", "publisher": {"@id": BUSINESS_ID}},
        jsonld_business(),
        {"@type": {"contact": "ContactPage", "about": "AboutPage", "post": "WebPage", "list": "CollectionPage"}.get(kind, "WebPage"),
         "@id": url + "#webpage", "url": url, "name": meta["title"], "description": meta["description"], "inLanguage": "de-DE",
         "isPartOf": {"@id": DOMAIN + "/#website"}, "about": {"@id": BUSINESS_ID}, "breadcrumb": {"@id": url + "#breadcrumb"},
         **({"primaryImageOfPage": DOMAIN + meta["image"]} if meta.get("image") else {}), "dateModified": BUILD_DATE},
        {"@type": "BreadcrumbList", "@id": url + "#breadcrumb", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": DOMAIN + h} for i, (n, h) in enumerate(crumbs)]},
    ]
    if extra:
        graph += extra
    return '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False) + "</script>"


def head(key, meta, crumbs, kind="page", extra_ld=None, preload=None, noindex=False):
    canon = DOMAIN + "/" + DUPLIKATE.get(key, key)
    img = DOMAIN + (meta.get("image") or "/assets/img/og-default.jpg")
    robots = "noindex, follow" if noindex else "index, follow, max-image-preview:large, max-snippet:-1"
    pre = ""
    if preload:
        avif = ", ".join(f"{u} {w}w" for u, w in preload["avif"])
        pre = f'<link rel="preload" as="image" type="image/avif" imagesrcset="{avif}" imagesizes="100vw" fetchpriority="high">'
    ogtype = "article" if kind == "post" else "website"
    return f'''<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(meta["title"])}</title>
<meta name="description" content="{esc(meta["description"])}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{canon}">
<link rel="alternate" hreflang="de-DE" href="{canon}">
<meta name="theme-color" content="#00857e">
<meta name="geo.region" content="DE-BW"><meta name="geo.placename" content="Karlsruhe"><meta name="geo.position" content="{FIRMA["lat"]};{FIRMA["lng"]}"><meta name="ICBM" content="{FIRMA["lat"]}, {FIRMA["lng"]}">
<meta property="og:type" content="{ogtype}"><meta property="og:locale" content="de_DE"><meta property="og:site_name" content="orthoKonzept">
<meta property="og:title" content="{esc(meta["title"])}"><meta property="og:description" content="{esc(meta["description"])}"><meta property="og:url" content="{canon}"><meta property="og:image" content="{img}">
<meta name="twitter:card" content="summary_large_image">
<link rel="preload" href="/assets/fonts/rubik-normal-latin.woff2" as="font" type="font/woff2" crossorigin>
{pre}
<link rel="stylesheet" href="/assets/css/main.css?v={ASSET_V}">
<link rel="icon" href="/favicon.ico" sizes="32x32"><link rel="icon" href="/assets/img/icon-192.png" type="image/png" sizes="192x192"><link rel="apple-touch-icon" href="/assets/img/apple-touch-icon.png"><link rel="manifest" href="/site.webmanifest">
<script>document.documentElement.classList.add("js")</script>
<script src="/assets/js/main.js?v={ASSET_V}" defer></script>{'<script src="/assets/js/konfigurator.js?v=' + ASSET_V + '" defer></script>' if key == "leistungen/theynis/" else ""}
{jsonld(key, meta, kind, crumbs, extra_ld)}
</head>'''


def crumbs_html(crumbs):
    items = []
    for i, (n, h) in enumerate(crumbs):
        if i == len(crumbs) - 1:
            items.append(f'<li aria-current="page">{esc(n)}</li>')
        else:
            items.append(f'<li><a href="{h}">{esc(n)}</a></li>')
    return f'<nav class="crumbs" aria-label="Brotkrumen"><ol>{"".join(items)}</ol></nav>'


def clip(t, n):
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[:n - 1].rsplit(" ", 1)[0].rstrip(",;:–-") + " …"


def meta_for(key, page, image=None):
    s = SEO.get(key, {})
    if s.get("title"):
        title = s["title"]
    elif page.get("post_title"):
        pt = strip_tags(page["post_title"])
        title = pt + " | orthoKonzept Karlsruhe" if len(pt) <= 34 else pt + " | orthoKonzept"
        if len(title) > 62:
            title = clip(pt, 62)
    else:
        title = re.sub(r"\s*[-|–]\s*orthoKonzept.*$", "", page["title"]).strip() + " | orthoKonzept Karlsruhe"
    desc = s.get("description") or re.sub(r"/index\.html$", "", page.get("description") or "")
    desc = clip(desc, 158)
    if not desc:
        desc = "orthoKonzept GmbH – Orthopädie-Schuhtechnik in Karlsruhe, Hirschstraße 35a. Einlagen, Maßschuhe, Kompression, Bewegungsanalysen. Tel. 0721 1208575."
    return {"title": title, "description": desc, "image": image}


# ─────────────────────────── Seiten ───────────────────────────

def page_hero(key, page, title_html, sub=None, crumbs=None, bg=None, eyebrow=None, actions=""):
    m = media(bg) if bg else None
    bgp = picture(m, "", sizes="100vw", cls="phero__img", loading="eager", fetchpriority="high") if m else ""
    cls = "phero" + (" phero--img" if m else "")
    return f'''<section class="{cls}">
  {f'<div class="phero__bg">{bgp}</div>' if bgp else ''}
  <div class="wrap phero__in">
    {crumbs_html(crumbs) if crumbs else ''}
    {f'<p class="eyebrow">{esc(eyebrow)}</p>' if eyebrow else ''}
    <h1>{title_html}</h1>
    {f'<p class="phero__sub">{sub}</p>' if sub else ''}
    {actions}
  </div>
</section>''', m


def render_sections(key, secs):
    out = []
    pending = None
    i = 0
    logos_head, logos_items = "", []
    # aufeinanderfolgende reine Bildsektionen zu einer Galerie zusammenfassen
    merged = []
    for s in secs:
        c = classify(s)
        if c == "images" and merged and merged[-1][0] == "images":
            merged[-1][1]["blocks"] += s["blocks"]
            continue
        merged.append((c, {**s, "blocks": list(s["blocks"])}))
    merged = merge_runs(merged)
    for c, s in merged:
        if c == "title":
            pending = s["blocks"][0]
            continue
        if c == "split":
            out.append(render_split(s, key, i, pending))
        elif c == "cards":
            out.append(render_cards(s, key, pending))
        elif c == "checklist":
            out.append(render_checklist(s, key, pending))
        elif c in ("gallery", "images"):
            out.append(render_gallery(s, key, pending))
        elif c == "videos":
            out.append(render_videos(s, key, pending))
        elif c == "accordion":
            out.append(render_accordion(s, key, pending))
        elif c == "logos":
            h, its = render_logos(s, key, pending)
            if h:
                logos_head = h
            logos_items += its
            pending = None
            i += 1
            continue
        elif c == "help":
            out.append(render_help(s, key))
        elif c == "form":
            out.append(render_contact(s, key))
        elif c == "address":
            rest = without_address(s["blocks"])
            left = render_blocks_content(rest, key) if rest else ""
            out.append(sec_wrap(f'<div class="contact"><div class="contact__form prose">{left}</div><aside class="contact__aside">{contact_block(key, [])}</aside></div>', "sec--contact"))
        elif c == "map":
            out.append(render_map(s, key))
        elif c == "posts":
            continue
        else:
            out.append(render_prose(s, key, pending))
        pending = None
        i += 1
    if pending:
        out.append(sec_wrap(f'<header class="sec__head reveal"><h2>{casing(pending["html"])}</h2></header>', "sec--prose"))
    if logos_items:
        out.append(sec_wrap(logos_head + f'<ul class="partners">{"".join(logos_items)}</ul>', "sec--partners"))
    return "\n".join(out)


def is_card_like(sec):
    bl = sec["blocks"]
    imgs = [b for b in bl if b["type"] == "image"]
    hs = [b for b in bl if b["type"] == "heading"]
    if len(imgs) != 1 or not hs:
        return False
    if any(b["type"] in ("button", "gallery", "video", "list") for b in bl):
        return False
    h3 = [h for h in hs if h.get("level") == "h3"]
    h2 = [h for h in hs if h.get("level") == "h2"]
    text_len = sum(len(strip_tags(b["html"])) for b in bl if b["type"] == "text")
    return len(h3) == 1 and len(h2) <= 1 and text_len < 1400


def merge_runs(merged):
    """Drei oder mehr aufeinanderfolgende Sektionen der Form Bild + h3 + Text werden ein Kartenraster."""
    out, i = [], 0
    while i < len(merged):
        j = i
        while j < len(merged) and merged[j][0] == "split" and is_card_like(merged[j][1]):
            if j > i and any(b["type"] == "heading" and b.get("level") == "h2" for b in merged[j][1]["blocks"]):
                break
            j += 1
        if j - i >= 3:
            blocks = []
            for k in range(i, j):
                bl = merged[k][1]["blocks"]
                lead = [b for b in bl if b["type"] == "heading" and b.get("level") == "h2"]
                if k == i:
                    blocks += lead
                blocks += [b for b in bl if b["type"] == "image"]
                blocks += [b for b in bl if b["type"] != "image" and b not in lead]
            out.append(("cards", {**merged[i][1], "blocks": blocks}))
            i = j
        else:
            out.append(merged[i])
            i += 1
    return out


def render_help(sec, key):
    bl = sec["blocks"]
    h = next(b for b in bl if b["type"] == "heading")
    txt = [b for b in bl if b["type"] == "text"]
    bts = [b for b in bl if b["type"] == "button"]
    imgs = [b for b in bl if b["type"] == "image"]
    img = ""
    if imgs:
        img = f'<div class="help__img">{pic_from(key, imgs[0], sizes="(min-width: 960px) 420px, 80vw")[0]}</div>'
    b = btn(bts[0]["text"], bts[0]["href"], key, "light") if bts else ""
    return f'''<section class="help-band"><div class="wrap"><div class="help reveal{" help--img" if img else ""}">
  <div class="help__text"><h2>{casing(h["html"])}</h2>{"".join(prose(t["html"], key) for t in txt)}<div class="actions">{b}<a class="btn btn--outline-light" href="tel:{FIRMA["tel_link"]}">{ICONS["phone"]}<span>{FIRMA["tel"]}</span></a></div></div>{img}
</div></div></section>'''


def render_map(sec, key):
    return ""


def contact_block(key, sec_blocks):
    """Adressblock aus Kontakt/Anfahrt."""
    return f'''<div class="addr reveal">
  <img src="/assets/img/logo.png" alt="" width="96" height="96" loading="lazy">
  <h3>{FIRMA["name"]}</h3>
  <p>{FIRMA["strasse"]}<br>{FIRMA["plz"]} {FIRMA["ort"]}</p>
  <ul class="addr__list">
    <li>{ICONS["phone"]}<a href="tel:{FIRMA["tel_link"]}">Tel. {FIRMA["tel"]}</a></li>
    <li>{ICONS["phone"]}<span>Fax {FIRMA["fax"]}</span></li>
    <li>{ICONS["mail"]}<a href="mailto:{FIRMA["mail"]}">{FIRMA["mail"]}</a></li>
    <li>{ICONS["clock"]}<span>Montag – Freitag: 09.00 – 13.00 Uhr | 14.00 – 18.00 Uhr oder nach Vereinbarung <span class="status" data-open-badge></span></span></li>
  </ul>
  {'' if key == 'anfahrt/' else f'<a class="btn btn--ghost" href="/anfahrt/"><span>{casing("ANFAHRT - IHR WEG ZU UNS")}</span>{ICONS["arrow"]}</a>'}
</div>'''


def render_contact(sec, key):
    h = next((b for b in sec["blocks"] if b["type"] == "heading" and b.get("level") == "h2"), None)
    form = f'''<form class="form reveal" action="/kontakt/senden.php" method="post" data-form novalidate>
  <div class="form__row"><label for="f-name">Name <span aria-hidden="true">*</span></label><input id="f-name" name="name" autocomplete="name" required></div>
  <div class="form__grid">
    <div class="form__row"><label for="f-mail">E-Mail <span aria-hidden="true">*</span></label><input id="f-mail" name="email" type="email" autocomplete="email" required></div>
    <div class="form__row"><label for="f-tel">Telefon (optional)</label><input id="f-tel" name="telefon" type="tel" autocomplete="tel"></div>
  </div>
  <div class="form__row"><label for="f-betreff">Betreff <span aria-hidden="true">*</span></label><input id="f-betreff" name="betreff" required></div>
  <div class="form__row"><label for="f-msg">Ihre Mitteilung an uns <span aria-hidden="true">*</span></label><textarea id="f-msg" name="nachricht" rows="6" maxlength="3000" required></textarea><small class="form__count" data-count>0 / 3000</small></div>
  <div class="form__hp" aria-hidden="true"><label for="f-web">Website</label><input id="f-web" name="website" tabindex="-1" autocomplete="off"></div>
  <div class="form__check"><input id="f-ds" name="datenschutz" type="checkbox" required><label for="f-ds">Datenschutz <span aria-hidden="true">*</span>: Ich habe die <a href="/datenschutzerklaerung/">Datenschutzerklärung</a> zur Kenntnis genommen. Ich stimme einer elektronischen Speicherung und Verarbeitung meiner eingegebenen Daten zur Beantwortung meiner Anfrage zu.</label></div>
  <button class="btn btn--primary btn--lg" type="submit"><span>Nachricht abschicken</span>{ICONS["arrow"]}</button>
  <p class="form__msg" role="status" aria-live="polite" data-form-msg></p>
</form>'''
    return sec_wrap(f'''<div class="contact">
  <div class="contact__form">{f"<h2>{casing(h['html'])}</h2>" if h else ""}<p class="lead">Schreiben Sie uns, wir melden uns zeitnah. Für eine schnelle Terminvereinbarung erreichen Sie uns auch telefonisch unter <a href="tel:{FIRMA["tel_link"]}">{FIRMA["tel"]}</a>.</p>{form}</div>
  <aside class="contact__aside">{contact_block(key, sec["blocks"])}</aside>
</div>''', "sec--contact")


def map_embed():
    q = "https://maps.google.com/maps?q=orthoKonzept%20GmbH%2C%20Hirschstra%C3%9Fe%2035a%2C%2076133%20Karlsruhe&t=m&z=16&output=embed&iwloc=near"
    return f'''<div class="map reveal" data-map="{esc(q)}">
  <div class="map__ph">
    <svg viewBox="0 0 400 240" aria-hidden="true" class="map__art"><defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0v24" fill="none" stroke="currentColor" stroke-opacity=".12"/></pattern></defs><rect width="400" height="240" fill="url(#grid)"/><path d="M0 150 C80 130 140 170 220 140 S330 90 400 110" fill="none" stroke="currentColor" stroke-opacity=".25" stroke-width="10"/><path d="M180 0 V240" stroke="currentColor" stroke-opacity=".18" stroke-width="7"/><circle cx="200" cy="118" r="14" fill="#87bc25"/><circle cx="200" cy="118" r="30" fill="#87bc25" fill-opacity=".2"/></svg>
    <p><strong>{FIRMA["name"]}</strong><br>{FIRMA["strasse"]}, {FIRMA["plz"]} {FIRMA["ort"]}</p>
    <div class="actions"><button class="btn btn--primary" type="button" data-map-load>{ICONS["pin"]}<span>Karte laden</span></button><a class="btn btn--ghost" href="{FIRMA["route"]}" target="_blank" rel="noopener">{ICONS["route"]}<span>Route planen</span></a></div>
    <small>Beim Laden der Karte werden Daten an Google übertragen.</small>
  </div>
</div>'''


def build_generic(key, page):
    secs = clean_sections(key, page)
    secs = [s for s in secs if not is_cta_section(s)]
    h1 = None
    hero_sec = None
    if secs and secs[0]["blocks"][0]["type"] == "heading" and secs[0]["blocks"][0].get("level") == "h1":
        hero_sec = secs[0]
        h1 = secs[0]["blocks"][0]
        rest0 = secs[0]["blocks"][1:]
        secs = ([{**secs[0], "blocks": rest0}] if rest0 else []) + secs[1:]
    crumbs = breadcrumb(key)
    title_html = casing(h1["html"]) if h1 else esc(page_name(key))
    hero, hm = page_hero(key, page, title_html, crumbs=crumbs, bg=page.get("hero_bg"), eyebrow=eyebrow_for(key))
    body = render_sections(key, secs)
    if key == "anfahrt/":
        body = render_anfahrt(key, secs)
    if key == "kontakt/":
        body = body + sec_wrap(map_embed(), "sec--map")
    if key in ("leistungen/", "leistungen/orthopaedie/", "leistungen/bewegungsanalysen/", "service/", "produkte/"):
        body += overview_cards(key)
    return hero, body, hm, crumbs


def eyebrow_for(key):
    if key.startswith("leistungen/orthopaedie/") and key != "leistungen/orthopaedie/":
        return "Orthopädie"
    if key.startswith("leistungen/bewegungsanalysen/") and key != "leistungen/bewegungsanalysen/":
        return "Bewegungsanalysen"
    if key.startswith("leistungen/") and key != "leistungen/":
        return "Leistungen"
    if key.startswith("produkte/") and key != "produkte/":
        return "Produkte"
    if key.startswith("service/") and key != "service/":
        return "Service"
    if key.startswith("ueber-uns/") and key != "ueber-uns/":
        return "Über uns"
    return None


def overview_cards(key):
    """Unterseiten-Übersicht (Navigation als Karten), falls die Seite selbst keine hat."""
    node = next((it for it in walk_nav(NAV) if it["href"] == "/" + key), None)
    if not node or not node["children"]:
        return ""
    if key in ("service/", "produkte/"):
        return ""  # haben eigene Karten
    cards = []
    for c in node["children"]:
        ck = c["href"].lstrip("/")
        p = PAGES.get(ck, {})
        bg = p.get("hero_bg")
        m = media(bg) if bg else None
        if not m and ck == "leistungen/theynis/":
            m = media("wp-content/uploads/2026/03/Theynis-Bildcollage.png")
        img = picture(m, "", sizes="(min-width: 1100px) 360px, (min-width: 700px) 45vw, 100vw") if m else ""
        desc = re.sub(r"/index\.html$", "", SEO.get(ck, {}).get("teaser") or p.get("description") or "")
        desc = (desc[:130].rsplit(" ", 1)[0] + " …") if len(desc) > 130 else desc
        sub = ""
        if c["children"]:
            sub = '<ul class="card__sub">' + "".join(f"<li>{esc(x['text'])}</li>" for x in c["children"]) + "</ul>"
        cards.append(f'<article class="card card--link reveal"><a href="{c["href"]}"><div class="card__img">{img}</div><div class="card__body"><h3>{esc(c["text"])}</h3><p>{esc(desc)}</p>{sub}<span class="card__link"><span>Mehr erfahren</span>{ICONS["arrow"]}</span></div></a></article>')
    return sec_wrap(f'<header class="sec__head reveal"><p class="eyebrow">Im Überblick</p><h2>{esc(node["text"])}: alle Bereiche</h2></header><div class="cards cards--3">{"".join(cards)}</div>', "sec--cards", tone="tone-soft")


def render_anfahrt(key, secs):
    h = None
    for s in secs:
        for b in s["blocks"]:
            if b["type"] == "heading" and b.get("level") == "h2":
                h = b
                break
        if h:
            break
    return sec_wrap(f'''<div class="contact">
  <div class="contact__form">{f"<h2>{casing(h['html'])}</h2>" if h else ""}{map_embed()}</div>
  <aside class="contact__aside">{contact_block(key, [])}</aside>
</div>''', "sec--contact")


# ─────────────────────────── Startseite ───────────────────────────

def build_home():
    key = ""
    page = PAGES[key]
    secs = clean_sections(key, page)
    s0 = secs[0]
    h1 = next(b for b in s0["blocks"] if b["type"] == "heading")
    intro = next(b for b in s0["blocks"] if b["type"] == "text")
    b0 = next(b for b in s0["blocks"] if b["type"] == "button")
    slides = [media(p) for p in (resolve_file(key, u) for u in s0["bg"]) if p]
    slides = [m for m in slides if m]
    slide_html = "".join(
        f'<div class="hero__slide{" is-on" if i == 0 else ""}">{picture(m, "", sizes="100vw", loading="eager" if i == 0 else "lazy", fetchpriority="high" if i == 0 else None)}</div>'
        for i, m in enumerate(slides))
    dots = "".join(f'<button type="button" class="hero__dot{" is-on" if i == 0 else ""}" aria-label="Bild {i + 1} von {len(slides)}" data-slide="{i}"></button>' for i in range(len(slides)))

    def find(title):
        for s in secs:
            for b in s["blocks"]:
                if b["type"] == "heading" and norm_key(b["html"]) == title:
                    return s
        return None

    refs = find("UNSERE REFERENZEN")
    ref_html = render_gallery(refs, key, logos=True) if refs else ""
    ref_html = ref_html.replace('<section class="sec sec--logos', '<section class="sec sec--logos sec--dark', 1)

    # Intro "Vom Maßschuh …"
    i_title = find("VOM MAßSCHUH BIS ZUR SPORTLER-VERSORGUNG")
    idx = secs.index(i_title)
    intro_txt = secs[idx + 1]
    services = secs[idx + 2]
    services_btn = secs[idx + 3]
    intro_html = "".join(f'<div class="rich">{prose(b["html"], key)}</div>' for b in intro_txt["blocks"] if b["type"] == "text")

    # Leistungskarten (Bento)
    gs = groups_by_image(services["blocks"])
    targets = {
        "ORTHOPÄDISCHE MAßSCHUHE": "/leistungen/orthopaedie/orthopaedischer-massschuh/",
        "THEYNIS - DIE LÖSUNG FÜR DEN SOMMER": "/leistungen/theynis/",
        "ORTHOPÄDISCHE EINLAGEN": "/leistungen/orthopaedie/orthopaedische-einlagen/",
        "KOMPRESSIONSVERSORGUNG": "/leistungen/orthopaedie/kompressionsversorgung/",
        "BANDAGEN & ORTHESEN": "/leistungen/orthopaedie/bandagen-orthesen/",
        "LAUFBAND- & GANGANALYSE": "/leistungen/bewegungsanalysen/",
    }
    bento = []
    for n, g in enumerate(gs):
        im = next((b for b in g if b["type"] == "image"), None)
        h = next((b for b in g if b["type"] == "heading"), None)
        t = next((b for b in g if b["type"] == "text"), None)
        if not h:
            continue
        href = targets.get(norm_key(h["html"]), "/leistungen/")
        p = pic_from(key, im, sizes="(min-width: 1100px) 400px, (min-width: 700px) 45vw, 100vw")[0] if im else ""
        badge = '<span class="bento__badge">Neu · Konfigurator</span>' if "theynis" in href else ""
        bento.append(f'<article class="bento__item bento__item--{n} reveal"><a href="{href}"><div class="bento__img">{p}</div><div class="bento__body">{badge}<h3>{casing(h["html"])}</h3><p>{inline(prose(t["html"], key)) if t else ""}</p><span class="card__link"><span>Mehr erfahren</span>{ICONS["arrow"]}</span></div></a></article>')
    sb = next(b for b in services_btn["blocks"] if b["type"] == "button")

    help_sec = find("BRAUCHEN SIE HILFE?")
    sport = find("SPORTLERBERATUNG UND -VERSORGUNG")
    helfer = find("PRAKTISCHE HELFER FÜR DEN ALLTAG")
    hidx = secs.index(helfer)
    prod_imgs = secs[hidx + 1]
    prod_btn = next(b for b in secs[hidx + 2]["blocks"] if b["type"] == "button")
    akt = find("AKTUELLES")

    helfer_txt = next(b for b in helfer["blocks"] if b["type"] == "text")
    prods = "".join(f'<li class="reveal">{pic_from(key, im, sizes="200px")[0]}</li>' for im in prod_imgs["blocks"] if im["type"] == "image")

    posts = collect_posts()
    abtn = next(b for b in akt["blocks"] if b["type"] == "button")

    body = f'''
<section class="hero" aria-label="Willkommen">
  <div class="hero__slides" data-slider>{slide_html}</div>
  <div class="hero__shade"></div>
  <div class="wrap hero__in">
    <div class="hero__content">
      <p class="hero__kicker"><span class="dot"></span>Orthopädie-Schuhtechnik in Karlsruhe · seit 2009</p>
      <h1>{casing(h1["html"])}</h1>
      <div class="hero__lead">{prose(intro["html"], key)}</div>
      <div class="actions">{btn(b0["text"], b0["href"], key, "primary")}<a class="btn btn--light" href="/kontakt/">{ICONS["calendar"]}<span>{casing("TERMIN VEREINBAREN")}</span></a></div>
    </div>
    <aside class="hero__card" aria-label="Kurzinfo">
      <p class="hero__card-k">Ihr Fachbetrieb in der Innenstadt-West</p>
      <ul>
        <li>{ICONS["pin"]}<span>{FIRMA["strasse"]}<br>{FIRMA["plz"]} {FIRMA["ort"]}</span></li>
        <li>{ICONS["clock"]}<span>Mo–Fr 9–13 & 14–18 Uhr<br><span class="status" data-open-badge></span></span></li>
        <li>{ICONS["phone"]}<a href="tel:{FIRMA["tel_link"]}">{FIRMA["tel"]}</a></li>
      </ul>
      <p class="hero__seals"><span>ISO 13485 zertifiziert</span><span>präqualifiziert nach § 126 SGB V</span></p>
    </aside>
  </div>
  <div class="hero__dots" role="group" aria-label="Bilder">{dots}<button type="button" class="hero__pause" data-pause aria-label="Animation pausieren"><span></span></button></div>
</section>
{ref_html}
<section class="sec sec--intro">
  <div class="wrap intro">
    <div class="intro__head reveal"><p class="eyebrow">Über orthoKonzept</p><h2>{casing(i_title["blocks"][0]["html"])}</h2></div>
    <div class="intro__text reveal">{intro_html}</div>
  </div>
</section>
<section class="sec sec--bento">
  <div class="wrap">
    <div class="bento">{"".join(bento)}</div>
    <div class="actions actions--center reveal">{btn(sb["text"], sb["href"], key, "primary")}</div>
  </div>
</section>
{render_help(help_sec, key)}
{render_split(sport, key, 0)}
<section class="sec sec--helfer tone-soft">
  <div class="wrap helfer">
    <div class="helfer__text reveal"><h2>{casing(helfer["blocks"][0]["html"])}</h2>{prose(helfer_txt["html"], key)}<div class="actions">{btn(prod_btn["text"], prod_btn["href"], key, "primary")}</div></div>
    <ul class="helfer__prods">{prods}</ul>
  </div>
</section>
<section class="sec sec--posts">
  <div class="wrap">
    <header class="sec__head sec__head--row reveal"><div><p class="eyebrow">Engagement & Neuigkeiten</p><h2>{casing(akt["blocks"][0]["html"])}</h2></div>{btn(abtn["text"], abtn["href"], key, "ghost")}</header>
    {render_posts_grid(posts, 6, "posts--scroll")}
  </div>
</section>'''
    meta = meta_for(key, page, slides[0]["og"] if slides else None)
    crumbs = [("Startseite", "/")]
    return meta, body, slides[0] if slides else None, crumbs


# ─────────────────────────── THeynis ───────────────────────────

def build_theynis():
    key = "leistungen/theynis/"
    page = PAGES[key]
    secs = [s for s in clean_sections(key, page) if not is_cta_section(s)]
    s0 = secs[0]
    h1 = s0["blocks"][0]
    slides = [media(p, 2400) for p in (resolve_file(key, u) for u in s0["bg"]) if p]
    slides = [m for m in slides if m]
    slide_html = "".join(f'<div class="hero__slide{" is-on" if i == 0 else ""}">{picture(m, "", sizes="100vw", loading="eager" if i == 0 else "lazy", fetchpriority="high" if i == 0 else None)}</div>' for i, m in enumerate(slides))
    crumbs = breadcrumb(key)
    hero = f'''<section class="thero" aria-label="THeynis">
  <div class="thero__slides" data-slider>{slide_html}</div>
  <div class="thero__shade"></div>
  <div class="wrap thero__in">
    {crumbs_html(crumbs)}
    <img class="thero__logo" src="/theynis/konfigurator/theynis-logo.webp" alt="THeynis" width="220" height="60">
    <h1>{casing(h1["html"])}</h1>
    <div class="actions"><a class="btn btn--primary btn--lg" href="#konfigurator">{ICONS["spark"]}<span>Jetzt im Konfigurator gestalten</span></a><a class="btn btn--light btn--lg" href="/kontakt/?betreff=THeynis%20Beratung">{ICONS["calendar"]}<span>{casing("HIER BERATEN LASSEN")}</span></a></div>
  </div>
</section>'''
    rest = secs[1:]
    # Varianten-Karten + Galerie ans Ende, Konfigurator dazwischen
    out = []
    var_start = None
    for k, s in enumerate(rest):
        hs = [b for b in s["blocks"] if b["type"] == "heading"]
        if hs and norm_key(hs[0]["html"]) == "DIE VERSCHIEDENEN VARIANTEN IM ÜBERBLICK":
            var_start = k
    before = rest[:var_start]
    variants = rest[var_start + 1:]
    gallery_secs = [s for s in variants if classify(s) == "gallery"]
    card_secs = [s for s in variants if classify(s) != "gallery"]
    out.append(render_sections(key, before))
    # Varianten als Modellkarten
    vblocks = [b for s in card_secs for b in s["blocks"]]
    gs = groups_by_image(vblocks)
    models = []
    for g in gs:
        im = next((b for b in g if b["type"] == "image"), None)
        h = next((b for b in g if b["type"] == "heading"), None)
        t = next((b for b in g if b["type"] == "text"), None)
        if not h:
            continue
        name = strip_tags(h["html"])
        models.append(f'<article class="model reveal"><div class="model__img">{pic_from(key, im, alt="THeynis " + name, sizes="(min-width: 1100px) 360px, (min-width: 700px) 45vw, 100vw")[0] if im else ""}</div><div class="model__body"><h3><span>THeynis</span> {esc(name)}</h3>{prose(t["html"], key) if t else ""}<button class="card__link" type="button" data-cfg-model="{slug(name)}"><span>{esc(name)} konfigurieren</span>{ICONS["arrow"]}</button></div></article>')
    vh = rest[var_start]["blocks"][0]
    out.append(sec_wrap(f'<header class="sec__head reveal"><p class="eyebrow">Fünf Modelle</p><h2>{casing(vh["html"])}</h2></header><div class="models">{"".join(models)}</div>', "sec--models", tone="tone-soft"))
    out.append(open(os.path.join(DATA, "konfigurator.html"), encoding="utf-8").read())
    for g in gallery_secs:
        out.append(render_gallery(g, key))
    meta = meta_for(key, page, slides[0]["og"] if slides else None)
    extra = [{
        "@type": "Service", "@id": DOMAIN + "/" + key + "#service", "name": "THeynis – orthopädische Maß-Sandalen und Flip-Flops nach 3D-Scan",
        "serviceType": "Orthopädische Maßanfertigung", "provider": {"@id": BUSINESS_ID}, "brand": {"@type": "Brand", "name": "THeynis"},
        "areaServed": {"@type": "City", "name": "Karlsruhe"}, "url": DOMAIN + "/" + key,
        "hasOfferCatalog": {"@type": "OfferCatalog", "name": "THeynis Modelle", "itemListElement": [
            {"@type": "Offer", "itemOffered": {"@type": "Product", "name": "THeynis " + n, "brand": {"@type": "Brand", "name": "THeynis"}, "manufacturer": {"@id": BUSINESS_ID}}}
            for n in ("Flip", "Steg", "Single", "Double", "Triple")]},
    }]
    return hero, "\n".join(out), slides[0] if slides else None, crumbs, meta, extra


# ─────────────────────────── Beitrag / Liste ───────────────────────────

def build_post(key, page, posts):
    secs = clean_sections(key, page)
    blocks = [b for s in secs for b in s["blocks"]]
    texts = [b for b in blocks if b["type"] == "text"]
    imgs = [b for b in blocks if b["type"] == "image"]
    title = strip_tags(page["post_title"])
    d = parse_de_date(page.get("post_date"))
    crumbs = [("Startseite", "/"), ("Aktuelles", "/aktuelles/"), (title, "/" + key)]
    feat = ""
    fm = None
    if imgs:
        feat, fm = pic_from(key, imgs[0], alt=imgs[0].get("alt") or title, sizes="(min-width: 900px) 760px, 100vw", loading="eager", fetchpriority="high")
    more = "".join(f'<figure class="post__fig">{pic_from(key, im, sizes="(min-width: 900px) 760px, 100vw")[0]}</figure>' for im in imgs[1:])
    idx = next(i for i, p in enumerate(posts) if p["key"] == key)
    prev_p = posts[idx + 1] if idx + 1 < len(posts) else None
    next_p = posts[idx - 1] if idx > 0 else None
    pn = '<nav class="postnav" aria-label="Weitere Beiträge">'
    if prev_p:
        pn += f'<a class="postnav__prev" href="{prev_p["url"]}"><small>Älterer Beitrag</small><span>{esc(prev_p["title"])}</span></a>'
    if next_p:
        pn += f'<a class="postnav__next" href="{next_p["url"]}"><small>Neuerer Beitrag</small><span>{esc(next_p["title"])}</span></a>'
    pn += "</nav>"
    body = f'''<article class="post">
  <header class="post__head wrap wrap--narrow">
    {crumbs_html(crumbs)}
    <p class="eyebrow"><time datetime="{d.isoformat() if d else ""}">{d.strftime("%d.%m.%Y") if d else ""}</time> · Aktuelles</p>
    <h1>{esc(title)}</h1>
  </header>
  {f'<figure class="post__feat wrap wrap--narrow">{feat}</figure>' if feat else ''}
  <div class="post__body wrap wrap--narrow rich">{"".join(prose(t["html"], key) for t in texts)}{more}</div>
  <div class="wrap wrap--narrow">{pn}<p><a class="btn btn--ghost" href="/aktuelles/"><span>Alle Beiträge</span>{ICONS["arrow"]}</a></p></div>
</article>'''
    meta = meta_for(key, page, fm["og"] if fm else None)
    extra = [{"@type": "BlogPosting", "@id": DOMAIN + "/" + key + "#article", "headline": title, "datePublished": d.isoformat() if d else None,
              "dateModified": d.isoformat() if d else None, "author": {"@id": BUSINESS_ID}, "publisher": {"@id": BUSINESS_ID},
              "mainEntityOfPage": DOMAIN + "/" + key, "image": DOMAIN + fm["og"] if fm else None, "inLanguage": "de-DE"}]
    return body, meta, crumbs, extra, fm


def build_list(key, page, posts):
    secs = clean_sections(key, page)
    h1 = find_h1(page) or "AKTUELLES"
    h2 = None
    for s in secs:
        for b in s["blocks"]:
            if b["type"] == "heading" and b.get("level") == "h2" and norm_key(b["html"]) != CTA_TITLE:
                h2 = b
    crumbs = breadcrumb("aktuelles/")
    hero, hm = page_hero(key, page, casing(h1), crumbs=crumbs, bg=PAGES["aktuelles/"].get("hero_bg"))
    body = sec_wrap((f'<header class="sec__head reveal"><h2>{casing(h2["html"])}</h2></header>' if h2 else "") + render_posts_grid(posts), "sec--posts")
    return hero, body, hm, crumbs


# ─────────────────────────── Ausgabe ───────────────────────────

ASSET_V = "1"


def write_page(key, html_s):
    dest = os.path.join(SITE, key.replace("/", os.sep), "index.html")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "w", encoding="utf-8").write(html_s)


def fix_headings(html_s):
    """Keine Sprünge in der Überschriften-Hierarchie (h1 -> h3 wird h2 usw.)."""
    last = [1]
    def rep(m):
        lv = int(m.group(1))
        if lv > last[0] + 1:
            lv = last[0] + 1
        last[0] = lv
        return f"<h{lv}{m.group(2)}>{m.group(3)}</h{lv}>"
    return re.sub(r"<h([1-6])([^>]*)>(.*?)</h\1>", rep, html_s, flags=re.S)


def assemble(key, meta, crumbs, main, kind="page", extra_ld=None, preload=None, noindex=False, body_cls="", closing=True):
    main = fix_headings(main)
    return (head(key, meta, crumbs, kind, extra_ld, preload, noindex) +
            f'\n<body class="{body_cls}">\n{render_header(key)}\n<main id="inhalt" tabindex="-1">\n{main}\n{render_closing_cta() if closing else ""}\n</main>\n{render_footer()}\n</body>\n</html>\n')


def service_ld(key, meta):
    if not key.startswith("leistungen/"):
        return None
    return [{"@type": "Service", "@id": DOMAIN + "/" + key + "#service", "name": page_name(key), "description": meta["description"],
             "provider": {"@id": BUSINESS_ID}, "areaServed": {"@type": "City", "name": "Karlsruhe"}, "url": DOMAIN + "/" + key}]


# ─────────────────────── Begrüßungsseite (Vorschau) ───────────────────────
# Persönliche Seite für Herrn Theune, erreichbar nur über den QR-Code im Begrüßungsbrief:
# noindex, nicht im Menü, nicht in der Sitemap, ohne Kontakt-Abschluss und ohne Cookie-Hinweis beim
# Öffnen (die Seite lädt nichts von Dritten). Vor einem Livegang der neuen Seite abschalten.
WILLKOMMEN = True
FILM_DAUER = "0:58"


def copy_media_dir(name):
    """Kopiert ../_medien/<name>/ nach site/media/<name>/ (nur geänderte Dateien)."""
    src, dst = os.path.join(PROJ, "_medien", name), os.path.join(MEDIA, name)
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        s, d = os.path.join(src, f), os.path.join(dst, f)
        if not os.path.exists(d) or os.path.getsize(s) != os.path.getsize(d) or os.path.getmtime(s) > os.path.getmtime(d):
            shutil.copy2(s, d)


def build_willkommen():
    copy_media_dir("willkommen")
    key = "willkommen/"
    meta = {"title": "Willkommen zurück | orthoKonzept",
            "description": "Ein erster Blick auf den neuen Webauftritt von orthoKonzept, als kurzer Film.",
            "image": "/media/willkommen/film-poster.jpg"}
    crumbs = [("Startseite", "/"), ("Willkommen zurück", "/" + key)]
    ton = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/></svg>'
    nochmal = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>'
    zu = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>'
    handy = '<svg class="film__phone" viewBox="0 0 24 24" aria-hidden="true"><rect x="6.5" y="2" width="11" height="20" rx="2.6"/><path d="M10.5 18.6h3"/></svg>'
    main = f'''<section class="whero" aria-labelledby="willkommen-h">
  <div class="wrap">
    <div class="whero__head">
      <p class="eyebrow">Willkommen zurück</p>
      <h1 id="willkommen-h">Schön, dass Sie wieder da sind, Herr Theune.</h1>
      <p class="whero__sub">Wir haben etwas für orthoKonzept vorbereitet: einen ersten Blick auf Ihren neuen Webauftritt, in knapp einer Minute.</p>
    </div>
    <figure class="film" data-film>
      <div class="film__frame">
        <div class="film__stage">
          <video class="film__video" controls playsinline preload="none" poster="/media/willkommen/film-poster.jpg" width="1280" height="720" controlslist="nodownload noremoteplayback" disablepictureinpicture aria-label="Film: ein erster Blick auf den neuen Webauftritt von orthoKonzept">
            <source src="/media/willkommen/film.mp4" type="video/mp4">
          </video>
          <button type="button" class="film__play" data-film-play aria-label="Film abspielen, {FILM_DAUER} Minuten, mit Ton"><span class="film__icon">{ICONS["play"]}</span><span class="film__label">Film ansehen</span><span class="film__dur">{FILM_DAUER}</span></button>
          <div class="film__end">
            <p class="film__endtxt">Jetzt selbst entdecken</p>
            <a class="btn btn--primary btn--lg" href="/"><span>Zum neuen Webauftritt</span>{ICONS["arrow"]}</a>
            <button type="button" class="film__again" data-film-again>{nochmal}<span>Noch einmal ansehen</span></button>
          </div>
          <button type="button" class="film__close" data-film-close aria-label="Großansicht schließen">{zu}</button>
        </div>
        <div class="film__turn" aria-hidden="true">{handy}<strong>Handy quer halten</strong><span>für das volle Bild</span></div>
      </div>
      <figcaption class="film__cap"><span class="film__cap-d">{ton}Am besten mit Ton.</span><span class="film__cap-m">{handy}Am besten mit Ton und im Querformat.</span></figcaption>
    </figure>
  </div>
</section>
<section class="sec wthanks">
  <div class="wrap">
    <blockquote class="wquote"><p>„Das Schönste an der Arbeit sind die Menschen, mit denen man sie teilt.“</p></blockquote>
    <p class="lead">Danke für fast zwei Jahre gute Zusammenarbeit und für Ihr Vertrauen. Wir freuen uns auf alles, was jetzt kommt.</p>
    <p class="wsign">Florian Schück und Fatih Madak<span>Leadwerk</span></p>
  </div>
</section>
<section class="sec tone-soft wcta">
  <div class="wrap wcta__in">
    <p class="eyebrow">Die Vorschau</p>
    <h2>Jetzt selbst entdecken</h2>
    <p>Alle Seiten und Inhalte von orthoKonzept, neu gestaltet und komplett durchklickbar.</p>
    <a class="btn btn--primary btn--lg" href="/"><span>Zum neuen Webauftritt</span>{ICONS["arrow"]}</a>
  </div>
</section>'''
    return key, meta, crumbs, main


def main():
    global ASSET_V
    css = open(os.path.join(SITE, "assets", "css", "main.css"), "rb").read()
    js = open(os.path.join(SITE, "assets", "js", "main.js"), "rb").read() + open(os.path.join(SITE, "assets", "js", "konfigurator.js"), "rb").read()
    ASSET_V = hashlib.md5(css + js).hexdigest()[:8]
    posts = collect_posts()
    sitemap = []

    meta, body, pre, crumbs = build_home()
    write_page("", assemble("", meta, crumbs, body, preload=pre, body_cls="is-home"))
    sitemap.append(("", 1.0))

    for key, page in sorted(PAGES.items()):
        if key == "":
            continue
        noindex = key in DUPLIKATE
        if key == "leistungen/theynis/":
            hero, body, pre, crumbs, meta, extra = build_theynis()
            write_page(key, assemble(key, meta, crumbs, hero + body, extra_ld=extra, preload=pre, body_cls="is-theynis"))
        elif page.get("post_title") and not key.startswith("category/"):
            body, meta, crumbs, extra, fm = build_post(key, page, posts)
            write_page(key, assemble(key, meta, crumbs, body, kind="post", extra_ld=extra))
        elif key in ("aktuelles/", "category/allgemein/"):
            hero, body, hm, crumbs = build_list(key, page, posts)
            meta = meta_for(key, page, hm["og"] if hm else None)
            write_page(key, assemble(key, meta, crumbs, hero + body, kind="list", preload=hm, noindex=noindex))
        else:
            hero, body, hm, crumbs = build_generic(key, page)
            meta = meta_for(key, page, hm["og"] if hm else None)
            kind = "contact" if key in ("kontakt/", "anfahrt/") else ("about" if key.startswith("ueber-uns") else "page")
            write_page(key, assemble(key, meta, crumbs, hero + body, kind=kind, extra_ld=service_ld(key, meta), preload=hm, noindex=noindex))
        if not noindex:
            prio = 0.9 if key.startswith("leistungen/") else (0.5 if page.get("post_title") else 0.7)
            if key in ("impressum/", "datenschutzerklaerung/", "nutzungsbedingungen/", "erklaerung-zur-barrierefreiheit/"):
                prio = 0.2
            sitemap.append((key, prio))

    if WILLKOMMEN:  # bewusst nicht in der Sitemap
        key, meta, crumbs, body = build_willkommen()
        write_page(key, assemble(key, meta, crumbs, body, noindex=True, body_cls="is-welcome consent-quiet", closing=False))

    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for k, pr in sitemap:
        sm.append(f"  <url><loc>{DOMAIN}/{k}</loc><lastmod>{BUILD_DATE}</lastmod><priority>{pr:.1f}</priority></url>")
    sm.append("</urlset>")
    open(os.path.join(SITE, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(sm) + "\n")
    write_404()
    write_static()
    print("Seiten:", len(sitemap), "| Bilder:", len(IMG_CACHE))


def write_static():
    from PIL import ImageOps, ImageDraw
    img_dir = os.path.join(SITE, "assets", "img")
    os.makedirs(img_dir, exist_ok=True)
    logo = Image.open(os.path.join(ORIG, "wp-content/uploads/2023/03/Logo-Ortho-Konzept_200.png")).convert("RGBA")
    logo.save(os.path.join(img_dir, "logo.png"), optimize=True)

    def icon(size, pad=0.06, bg=(255, 255, 255, 255)):
        c = Image.new("RGBA", (size, size), bg)
        inner = int(size * (1 - 2 * pad))
        c.alpha_composite(logo.resize((inner, inner), Image.LANCZOS), (int(size * pad), int(size * pad)))
        return c

    icon(180).convert("RGB").save(os.path.join(img_dir, "apple-touch-icon.png"))
    icon(192).save(os.path.join(img_dir, "icon-192.png"))
    icon(512).save(os.path.join(img_dir, "icon-512.png"))
    icon(512, 0.14).save(os.path.join(img_dir, "icon-maskable-512.png"))
    icon(512).save(os.path.join(img_dir, "logo-512.png"))
    icon(64, 0.0, (255, 255, 255, 0)).save(os.path.join(SITE, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    # Standard-OG-Bild: erstes Hero-Motiv mit Logo-Plakette
    hero = PAGES[""]["sections"][0]["bg"]
    src = resolve_file("", hero[0]) if hero else None
    if src:
        og = ImageOps.fit(Image.open(os.path.join(ORIG, src)).convert("RGB"), (1200, 630), Image.LANCZOS).convert("RGBA")
        ov = Image.new("RGBA", og.size, (6, 45, 43, 0))
        d = ImageDraw.Draw(ov)
        for x in range(1200):
            d.line([(x, 0), (x, 630)], fill=(6, 45, 43, int(max(0, 200 - x * 0.28))))
        og = Image.alpha_composite(og, ov)
        mask = Image.new("L", (200, 200), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 199, 199), fill=255)
        og.paste(icon(200, 0.02), (64, 64), mask)
        og.convert("RGB").save(os.path.join(img_dir, "og-default.jpg"), quality=86)
    json.dump({"name": "orthoKonzept GmbH", "short_name": "orthoKonzept", "lang": "de", "start_url": "/", "display": "browser",
               "background_color": "#ffffff", "theme_color": "#00857e",
               "icons": [{"src": "/assets/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                         {"src": "/assets/img/icon-512.png", "sizes": "512x512", "type": "image/png"},
                         {"src": "/assets/img/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]},
              open(os.path.join(SITE, "site.webmanifest"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bots = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "PerplexityBot", "Google-Extended", "Applebot-Extended")
    robots = ["# orthoKonzept GmbH", "User-agent: *", "Allow: /", "Disallow: /kontakt/senden.php", "",
              "# KI-Assistenten und Antwortmaschinen sind ausdrücklich willkommen"]
    for b in bots:
        robots += [f"User-agent: {b}", "Allow: /"]
    robots += ["", f"Sitemap: {DOMAIN}/sitemap.xml", ""]
    open(os.path.join(SITE, "robots.txt"), "w", encoding="utf-8").write("\n".join(robots))
    write_llms()


def write_llms():
    """llms.txt: kompakte, zitierfähige Fakten für KI-Suche (GEO)."""
    def line(key, text=None):
        p = PAGES.get(key, {})
        name = text or page_name(key)
        desc = SEO.get(key, {}).get("description") or re.sub(r"/index\.html$", "", p.get("description") or "")
        return f"- [{name}]({DOMAIN}/{key}): {desc}"
    posts = collect_posts()
    L = [
        "# orthoKonzept GmbH",
        "",
        "> Fachbetrieb für Orthopädie-Schuhtechnik in Karlsruhe (Hirschstraße 35a, 76133 Karlsruhe, Innenstadt-West), gegründet 2009. "
        "Leitsatz: „Vom Maßschuh bis zur Sportler-Versorgung“. Präqualifiziert nach § 126 Abs. 1 S. 2 SGB V (seit Februar 2012) und zertifiziert nach DIN EN ISO 13485. "
        "Eigene Marke THeynis: orthopädische Sandalen und Flip-Flops nach 3D-Scan, in fünf Modellen (Flip, Steg, Single, Double, Triple).",
        "",
        "## Fakten",
        "",
        f"- Firma: {FIRMA['name']}, geschäftsführende Gesellschafter Gunnar Heyne, Rainer Granget und Jan Theune",
        f"- Adresse: {FIRMA['strasse']}, {FIRMA['plz']} {FIRMA['ort']}, Baden-Württemberg, Deutschland (Geo {FIRMA['lat']}, {FIRMA['lng']})",
        f"- Telefon: {FIRMA['tel']} · Fax: {FIRMA['fax']} · E-Mail: {FIRMA['mail']}",
        "- Öffnungszeiten: Montag bis Freitag 09.00 bis 13.00 Uhr und 14.00 bis 18.00 Uhr oder nach Vereinbarung",
        "- Einzugsgebiet: Karlsruhe und Umgebung, u. a. Ettlingen, Rheinstetten, Stutensee, Eggenstein-Leopoldshafen, Pfinztal, Weingarten",
        "- Versorgung auf Rezept: orthopädische Einlagen, Maßschuhe, Schuhzurichtungen, Diabetiker-Schutzschuhe, Verband- und Fußteilentlastungsschuhe, Kompression, Bandagen und Orthesen (Hilfsmittelkatalog der Krankenkassen)",
        "- Betriebe: orthopädische Sicherheitsschuh-Versorgung (Einlagen und Sicherheitsschuhe nach Maß), Kooperationspartner Schöffler + Wörner in Karlsruhe-Hagsfeld",
        "- Sport: Laufbandanalyse, Pedographie (elektronische Fußdruckmessung), Sporteinlagen, Laufschuhberatung; Engagement bei Baden-Marathon, Pfinztallauf, Träublelauf und dem orthoKonzept AH-Kreispokal",
        "",
        "## Leistungen",
        "",
    ] + [line(k) for k in (
        "leistungen/orthopaedie/orthopaedischer-massschuh/", "leistungen/orthopaedie/orthopaedische-einlagen/",
        "leistungen/orthopaedie/orthopaedische-sporteinlagen/", "leistungen/orthopaedie/orthopaedische-schuhzurichtung/",
        "leistungen/orthopaedie/bandagen-orthesen/", "leistungen/orthopaedie/kompressionsversorgung/",
        "leistungen/orthopaedie/fussteilentlastungs-verbandschuh/", "leistungen/orthopaedie/diabetiker-schutzschuhe/",
        "leistungen/bewegungsanalysen/", "leistungen/bewegungsanalysen/laufbandanalyse/", "leistungen/bewegungsanalysen/pedographie/",
        "leistungen/laufschuhe/", "leistungen/sicherheitsschuhe/")] + [line("leistungen/theynis/", "THeynis und THeynis-Konfigurator"), "",
        "## Service und Produkte", ""] + [line(k) for k in (
        "service/schuhinformation/", "service/kostenerstattung/", "service/fussgymnastik/",
        "produkte/rund-um-den-fuss/", "produkte/rund-um-den-schuh/", "produkte/rund-um-die-kompression/")] + ["",
        "## Unternehmen", ""] + [line(k) for k in ("ueber-uns/", "ueber-uns/zertifizierung/", "ueber-uns/partner/", "kontakt/", "anfahrt/", "jobs/")] + [
        "", "## Aktuelles", ""] + [f"- [{p['title']}]({DOMAIN}{p['url']}) ({p['date']})" for p in posts[:8]]
    open(os.path.join(SITE, "llms.txt"), "w", encoding="utf-8").write("\n".join(L) + "\n")


def write_404():
    meta = {"title": "Seite nicht gefunden | orthoKonzept Karlsruhe", "description": "Diese Seite gibt es nicht (mehr). Hier geht es zurück zu orthoKonzept.", "image": None}
    main = f'''<section class="phero"><div class="wrap phero__in"><p class="eyebrow">Fehler 404</p><h1>Na, wo drückt der Schuh?</h1><p class="phero__sub">Diese Seite konnten wir leider nicht finden. Vielleicht hilft Ihnen einer dieser Wege weiter:</p><div class="actions"><a class="btn btn--primary" href="/"><span>Zur Startseite</span>{ICONS["arrow"]}</a><a class="btn btn--ghost" href="/leistungen/"><span>Unsere Leistungen</span></a><a class="btn btn--ghost" href="/kontakt/"><span>Kontakt</span></a></div></div></section>'''
    open(os.path.join(SITE, "404.html"), "w", encoding="utf-8").write(assemble("404", meta, [("Startseite", "/")], main, noindex=True))


if __name__ == "__main__":
    main()
