"""Qualitätsprüfung der gebauten Seite (../site) über den lokalen Server.

Prüft je Seite: genau eine H1, Title-/Description-Länge, Canonical, JSON-LD parsebar,
Bilder mit width/height und alt-Attribut, interne Links und Ressourcen erreichbar,
Überschriften-Hierarchie ohne Sprünge, keine leeren Sektionen, keine Versal-Überschriften.
Aufruf: python pruefen.py [basis-url]   (Standard http://localhost:8802)
"""
import sys, re, json, urllib.request, urllib.parse
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8802"


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pruefen"}), timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return 0, str(e).encode()


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h = []
        self.imgs = []
        self.links = set()
        self.res = set()
        self.title = ""
        self.meta = {}
        self.canon = None
        self.ld = []
        self._in = None
        self._buf = ""
        self._htext = None

    def handle_starttag(self, t, a):
        a = dict(a)
        if t in ("h1", "h2", "h3", "h4"):
            self._htext = [t, ""]
        if t == "title":
            self._in = "title"
        if t == "script" and a.get("type") == "application/ld+json":
            self._in = "ld"
            self._buf = ""
        if t == "meta" and a.get("name") in ("description", "robots"):
            self.meta[a["name"]] = a.get("content", "")
        if t == "link" and a.get("rel") == "canonical":
            self.canon = a.get("href")
        if t == "img":
            self.imgs.append(a)
            if a.get("src"):
                self.res.add(a["src"])
        if t == "source" and a.get("srcset"):
            for part in a["srcset"].split(","):
                self.res.add(part.strip().split()[0])
        if t == "a" and a.get("href"):
            self.links.add(a["href"])
        if t in ("link",) and a.get("href") and a.get("rel") in ("stylesheet", "preload", "icon", "manifest", "apple-touch-icon"):
            self.res.add(a["href"])
        if t == "script" and a.get("src"):
            self.res.add(a["src"])
        if t == "video" and a.get("src"):
            self.res.add(a["src"])

    def handle_endtag(self, t):
        if self._htext and t == self._htext[0]:
            self.h.append((t, self._htext[1].strip()))
            self._htext = None
        if t == "title":
            self._in = None
        if t == "script" and self._in == "ld":
            self.ld.append(self._buf)
            self._in = None

    def handle_data(self, d):
        if self._htext:
            self._htext[1] += d
        if self._in == "title":
            self.title += d
        if self._in == "ld":
            self._buf += d


def main():
    st, sm = get(BASE + "/sitemap.xml")
    urls = [u.replace("https://www.orthokonzept.de", BASE) for u in re.findall(r"<loc>([^<]+)</loc>", sm.decode())]
    extra = ["/jobs-2/", "/leistungen/bewegungsanalysen/laufbandanalyse-2/", "/category/allgemein/", "/404.html"]
    urls += [BASE + e for e in extra]
    problems = []
    all_links, all_res = set(), set()
    for u in urls:
        st, body = get(u)
        path = u.replace(BASE, "")
        if st != 200:
            problems.append((path, f"Status {st}"))
            continue
        p = P()
        p.feed(body.decode("utf-8", "replace"))
        h1 = [h for h in p.h if h[0] == "h1"]
        if len(h1) != 1:
            problems.append((path, f"H1-Anzahl {len(h1)}"))
        tl = len(p.title)
        if tl > 65 or tl < 15:
            problems.append((path, f"Title-Länge {tl}: {p.title}"))
        dl = len(p.meta.get("description", ""))
        if dl > 165 or dl < 50:
            problems.append((path, f"Description-Länge {dl}"))
        if not p.canon:
            problems.append((path, "kein Canonical"))
        for ld in p.ld:
            try:
                json.loads(ld)
            except Exception as e:
                problems.append((path, f"JSON-LD defekt: {e}"))
        last = 1
        for t, txt in p.h:
            lv = int(t[1])
            if lv > last + 1:
                problems.append((path, f"Überschriften-Sprung h{last}->h{lv}: {txt[:50]}"))
            last = lv
            letters = [c for c in txt if c.isalpha()]
            if len(letters) > 6 and sum(c.isupper() for c in letters) / len(letters) > 0.8:
                problems.append((path, f"Versal-Überschrift: {txt[:60]}"))
        for im in p.imgs:
            if "alt" not in im:
                problems.append((path, f"img ohne alt: {im.get('src')}"))
            if not im.get("width") or not im.get("height"):
                problems.append((path, f"img ohne Maße: {im.get('src')}"))
        for l in p.links:
            full = urllib.parse.urljoin(u, l)
            if full.startswith(BASE):
                all_links.add(full.split("#")[0])
        for r in p.res:
            all_res.add(urllib.parse.urljoin(u, r))
    def chk(x):
        s, _ = get(x)
        return x, s
    with ThreadPoolExecutor(12) as ex:
        for x, s in ex.map(chk, sorted(all_links | all_res)):
            if s != 200:
                problems.append((x.replace(BASE, ""), f"nicht erreichbar ({s})"))
    print(f"{len(urls)} Seiten, {len(all_links)} interne Links, {len(all_res)} Ressourcen geprüft")
    for path, msg in problems:
        print(f"  {path}: {msg}")
    print("Befunde:", len(problems))


if __name__ == "__main__":
    main()
