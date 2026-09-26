"""Spiegelt www.orthokonzept.de als statisches HTML nach ../original/.

Alle Seiten aus den Yoast-Sitemaps werden geladen, CSS/JS/Bilder/Fonts (auch aus
url() in CSS und srcset) lokal abgelegt und die Links auf relative Pfade umgeschrieben.
Aufruf: python spiegeln.py
"""
import os, re, sys, html, hashlib, posixpath, threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse, unquote
import urllib.request

BASE = "https://www.orthokonzept.de"
HOST = "www.orthokonzept.de"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "original"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Leadwerk-Spiegel"}

lock = threading.Lock()
done_assets = {}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), r.headers.get("Content-Type", "")


def sitemap_urls():
    urls = []
    for s in ("page", "post", "category"):
        xml = fetch(f"{BASE}/{s}-sitemap.xml")[0].decode("utf-8")
        urls += re.findall(r"<loc>([^<]+)</loc>", xml)
    return [u for u in urls if not re.search(r"\.(jpg|png|webp|pdf)$", u)]


def page_path(url):
    p = urlparse(url).path
    if not p.endswith("/"):
        p += "/"
    return p.lstrip("/") + "index.html"


def asset_path(url):
    u = urlparse(url)
    p = unquote(u.path).lstrip("/")
    if u.netloc and u.netloc != HOST:
        p = "_extern/" + u.netloc + "/" + p
    if not p or p.endswith("/"):
        p += "index"
    if p.endswith("_callback.php"):
        p = p[:-4] + (".js" if "/js/" in p else ".css")
    if u.query and not re.search(r"\.(css|js)$", p):
        pass  # Versionsparameter ignorieren
    return p


def rel(from_file, to_file):
    return posixpath.relpath(to_file, posixpath.dirname(from_file) or ".")


def is_local(url):
    h = urlparse(url).netloc
    return h in ("", HOST, "orthokonzept.de")


def get_asset(url):
    url = url.split("#")[0]
    ap = asset_path(url)
    with lock:
        if url in done_assets:
            return done_assets[url]
        done_assets[url] = ap
    dest = os.path.join(ROOT, ap)
    if os.path.exists(dest):
        return ap
    try:
        data, ctype = fetch(url)
    except Exception as e:
        print("  ! Asset fehlt", url, e)
        return ap
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if ap.endswith(".css"):
        css = data.decode("utf-8", "replace")
        css = rewrite_css(css, url, ap)
        data = css.encode("utf-8")
    with open(dest, "wb") as f:
        f.write(data)
    return ap


def rewrite_css(css, css_url, css_ap):
    def rep(m):
        raw = m.group(1).strip("'\" ")
        if raw.startswith("data:") or raw.startswith("#"):
            return m.group(0)
        full = urljoin(css_url, raw)
        if not full.startswith("http"):
            return m.group(0)
        ap = get_asset(full)
        return "url('" + rel(css_ap, ap) + "')"
    css = re.sub(r"url\(([^)]+)\)", rep, css)
    def imp(m):
        full = urljoin(css_url, m.group(1))
        ap = get_asset(full)
        return "@import '" + rel(css_ap, ap) + "'"
    css = re.sub(r"@import\s+['\"]([^'\"]+)['\"]", imp, css)
    return css


ASSET_EXT = re.compile(r"\.(css|js|png|jpe?g|gif|webp|svg|avif|woff2?|ttf|eot|otf|ico|mp4|webm|pdf|json)(\?|$)", re.I)


def rewrite_html(doc, page_url, page_ap, page_set):
    def conv(u):
        u0 = html.unescape(u)
        if u0.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            return u
        full = urljoin(page_url, u0)
        pu = urlparse(full)
        if pu.netloc not in ("", HOST, "orthokonzept.de", "fonts.googleapis.com", "fonts.gstatic.com"):
            return u
        if pu.netloc in (HOST, "orthokonzept.de"):
            path = pu.path
            if ASSET_EXT.search(path) or path.startswith(('/wp-content/', '/wp-includes/')):
                ap = get_asset(full)
                return rel(page_ap, ap)
            if path.startswith(("/wp-json", "/xmlrpc", "/wp-admin", "/feed", "/comments")):
                return u
            target = page_path(BASE + path)
            frag = ("#" + pu.fragment) if pu.fragment else ""
            return rel(page_ap, target) + frag
        if pu.netloc.startswith("fonts."):
            ap = get_asset(full if pu.netloc == "fonts.gstatic.com" else full)
            return rel(page_ap, ap)
        return u

    def attr(m):
        if m.group(1).startswith("content") and not m.group(2).startswith(("http", "/")):
            return m.group(0)
        return m.group(1) + conv(m.group(2)) + m.group(3)
    doc = re.sub(r'((?:href|src|data-src|poster|data-lazy-src|content)=")([^"]+)(")', attr, doc)
    doc = re.sub(r"((?:href|src)=')([^']+)(')", attr, doc)

    def srcset(m):
        parts = []
        for item in m.group(2).split(","):
            item = item.strip()
            if not item:
                continue
            bits = item.split()
            bits[0] = conv(bits[0])
            parts.append(" ".join(bits))
        return m.group(1) + ", ".join(parts) + m.group(3)
    doc = re.sub(r'((?:srcset|data-srcset)=")([^"]+)(")', srcset, doc)

    def style_url(m):
        raw = html.unescape(m.group(1)).strip("'\" ")
        if raw.startswith("data:"):
            return m.group(0)
        full = urljoin(page_url, raw)
        if not is_local(full):
            return m.group(0)
        return "url(" + rel(page_ap, get_asset(full)) + ")"
    doc = re.sub(r"url\((?:&quot;|['\"])?([^)'\"&]+)(?:&quot;|['\"])?\)", style_url, doc)

    # Elementor-Settings (Slideshow-Hintergründe) enthalten escapte URLs
    def json_url(m):
        full = m.group(0).replace("\\/", "/")
        ap = get_asset(full)
        return rel(page_ap, ap).replace("/", "\\/")
    doc = re.sub(r"https:\\/\\/www\.orthokonzept\.de\\/wp-content\\/uploads\\/[^&\"]+?\.(?:png|jpe?g|webp)", json_url, doc)
    return doc


def do_page(url, page_set):
    ap = page_path(url)
    try:
        data, _ = fetch(url)
    except Exception as e:
        print("! Seite fehlt", url, e)
        return
    doc = data.decode("utf-8", "replace")
    doc = rewrite_html(doc, url, ap, page_set)
    dest = os.path.join(ROOT, ap)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(doc)
    print("ok", ap)


def main():
    urls = sitemap_urls()
    extra = [BASE + "/jobs/", BASE + "/aktuelles/"]
    urls = list(dict.fromkeys(urls + extra))
    print(len(urls), "Seiten")
    page_set = set(urls)
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda u: do_page(u, page_set), urls))
    for chunk in ("consents.pd3ENblc", "observer.CqbHLzbb", "vue.DUDw4U1y"):
        get_asset(BASE + "/wp-content/plugins/borlabs-cookie/assets/javascript/" + chunk + ".min.js")
    print("Assets:", len(done_assets))


if __name__ == "__main__":
    main()
