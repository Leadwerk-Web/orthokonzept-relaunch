"""Zieht aus der Spiegelung (../original) den Inhalt jeder Seite als Blockfolge nach ../_daten/inhalte.json.

Elementor-Widgets werden in neutrale Blöcke übersetzt (heading, text, image, button, list,
accordion, gallery, video, form, map, divider), gruppiert nach Elementor-Sektionen bzw. Containern.
Kopf, Fuß und Navigation werden separat einmal erfasst.
"""
import os, re, json, html
from bs4 import BeautifulSoup, NavigableString

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "original"))
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "_daten"))


def clean_inline(el):
    """Inline-HTML mit erlaubten Tags behalten (strong, em, a, br, ul/li)."""
    allowed = {"strong", "b", "em", "i", "a", "br", "ul", "ol", "li", "p", "span", "sup", "h4", "h5", "h6"}
    el = BeautifulSoup(str(el), "html.parser")
    for t in el.find_all(True):
        if t.name not in allowed:
            t.unwrap()
            continue
        attrs = {}
        if t.name == "a" and t.get("href"):
            attrs["href"] = t["href"]
            if t.get("target"):
                attrs["target"] = t["target"]
        t.attrs = attrs
        if t.name == "span":
            t.unwrap()
    s = str(el)
    s = s.replace("\xa0", " ")
    s = re.sub(r"<p>\s*</p>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def img_info(img):
    src = img.get("src") or img.get("data-src") or ""
    return {
        "src": src,
        "alt": (img.get("alt") or "").strip(),
        "w": img.get("width"),
        "h": img.get("height"),
        "srcset": img.get("srcset"),
    }


def widget_blocks(w):
    t = w.get("data-widget_type", "")
    name = t.split(".")[0]
    out = []
    if name in ("heading", "theme-post-title", "animated-headline"):
        h = w.find(["h1", "h2", "h3", "h4", "h5", "h6", "p", "div"], class_=re.compile("title|headline"))
        if h:
            txt = clean_inline(h.decode_contents())
            out.append({"type": "heading", "level": h.name if h.name.startswith("h") else "p", "html": txt})
    elif name in ("text-editor", "theme-post-content", "tp-heading-title"):
        c = w.find(class_="elementor-widget-container") or w
        out.append({"type": "text", "html": clean_inline(c.decode_contents())})
    elif name in ("image", "theme-post-featured-image"):
        img = w.find("img")
        if img:
            b = {"type": "image", **img_info(img)}
            a = w.find("a")
            if a and a.get("href"):
                b["href"] = a["href"]
            cap = w.find("figcaption")
            if cap:
                b["caption"] = cap.get_text(" ", strip=True)
            out.append(b)
    elif name == "button":
        a = w.find("a")
        if a:
            out.append({"type": "button", "text": a.get_text(" ", strip=True), "href": a.get("href", "#")})
    elif name in ("icon-list",):
        items = []
        for li in w.find_all("li"):
            a = li.find("a")
            items.append({"text": li.get_text(" ", strip=True), "href": a.get("href") if a else None})
        out.append({"type": "list", "items": items})
    elif name in ("accordion", "toggle", "nested-accordion"):
        items = []
        titles = w.find_all(class_=re.compile(r"elementor-(tab|toggle)-title|e-n-accordion-item-title-text"))
        contents = w.find_all(class_=re.compile(r"elementor-tab-content|elementor-toggle-content"))
        if titles and contents and len(titles) == len(contents):
            for ti, co in zip(titles, contents):
                items.append({"title": ti.get_text(" ", strip=True), "html": clean_inline(co.decode_contents())})
        else:
            for det in w.find_all("details"):
                s = det.find("summary")
                body = det.find(class_=re.compile("e-con|content")) or det
                items.append({"title": s.get_text(" ", strip=True) if s else "", "html": clean_inline(body.decode_contents()) if body is not det else ""})
        out.append({"type": "accordion", "items": items})
    elif name in ("image-gallery", "gallery", "image-carousel", "media-carousel", "basic-gallery"):
        imgs = []
        for a in w.find_all(["a", "figure", "div"], recursive=True):
            pass
        for img in w.find_all("img"):
            info = img_info(img)
            a = img.find_parent("a")
            if a and a.get("href") and re.search(r"\.(jpe?g|png|webp)$", a["href"], re.I):
                info["full"] = a["href"]
            imgs.append(info)
        # Swiper-Duplikate entfernen
        seen, uniq = set(), []
        for i in imgs:
            if i["src"] in seen:
                continue
            seen.add(i["src"]); uniq.append(i)
        out.append({"type": "gallery", "images": uniq})
    elif name in ("video",):
        st = json.loads(html.unescape(w.get("data-settings") or "{}"))
        v = w.find("video")
        out.append({"type": "video", "youtube": st.get("youtube_url"), "hosted": (v.get("src") if v else None),
                    "poster": (v.get("poster") if v else None)})
    elif name in ("google_maps",):
        f = w.find("iframe")
        out.append({"type": "map", "src": f.get("src") if f else None, "title": f.get("title") if f else None})
    elif name in ("shortcode", "html", "wp-widget-formcraft", "formcraft"):
        c = w.find(class_="elementor-widget-container") or w
        txt = c.get_text(" ", strip=True)
        if c.find("form") or "fc-form" in str(c):
            fields = []
            for f in c.find_all(["input", "textarea", "select"]):
                if f.get("type") in ("hidden", "submit"):
                    continue
                lab = ""
                fid = f.get("id")
                fe = f.find_parent(class_=re.compile("form-element"))
                if fe:
                    l = fe.find(class_=re.compile("main-label|label"))
                    lab = l.get_text(" ", strip=True) if l else ""
                fields.append({"tag": f.name, "type": f.get("type"), "name": f.get("name"), "label": lab, "placeholder": f.get("placeholder")})
            out.append({"type": "form", "fields": fields})
        elif txt:
            out.append({"type": "text", "html": clean_inline(c.decode_contents())})
    elif name in ("divider", "spacer", "icon"):
        pass
    elif name == "tp-clients-listout":
        items = []
        for it in w.find_all(class_="client-post-content"):
            img = it.find("img")
            a = it.find("a")
            ti = it.find(class_="post-title")
            items.append({"img": img_info(img) if img else None, "href": a.get("href") if a else None,
                          "name": ti.get_text(" ", strip=True) if ti else "",
                          "text": it.get_text(" ", strip=True)})
        out.append({"type": "logos", "items": items})
    elif name in ("icon-box", "image-box"):
        img = w.find("img")
        title = w.find(class_=re.compile("box-title"))
        desc = w.find(class_=re.compile("box-description"))
        a = w.find("a")
        out.append({"type": "card", "title": title.get_text(" ", strip=True) if title else "",
                    "html": clean_inline(desc.decode_contents()) if desc else "",
                    "img": img_info(img) if img else None, "href": a.get("href") if a else None})
    elif name in ("call-to-action",):
        title = w.find(class_=re.compile("cta__title"))
        desc = w.find(class_=re.compile("cta__description"))
        a = w.find("a")
        bg = w.find(class_=re.compile("cta__bg-wrapper"))
        out.append({"type": "cta", "title": title.get_text(" ", strip=True) if title else "",
                    "html": clean_inline(desc.decode_contents()) if desc else "",
                    "button": a.get_text(" ", strip=True) if a else "", "href": a.get("href") if a else None})
    elif name in ("posts", "archive-posts", "loop-grid"):
        items = []
        for art in w.find_all("article"):
            a = art.find("a")
            img = art.find("img")
            ti = art.find(class_=re.compile("title"))
            ex = art.find(class_=re.compile("excerpt"))
            dt = art.find(class_=re.compile("date"))
            items.append({"href": a.get("href") if a else None, "title": ti.get_text(" ", strip=True) if ti else "",
                          "img": img_info(img) if img else None, "excerpt": ex.get_text(" ", strip=True) if ex else "",
                          "date": dt.get_text(" ", strip=True) if dt else ""})
        out.append({"type": "posts", "items": items})
    else:
        txt = w.get_text(" ", strip=True)
        imgs = [img_info(i) for i in w.find_all("img")]
        out.append({"type": "unknown", "widget": name, "text": txt[:2000], "images": imgs,
                    "html": clean_inline((w.find(class_="elementor-widget-container") or w).decode_contents())[:6000]})
    return out


def section_bg(sec):
    s = sec.get("data-settings") or ""
    m = re.findall(r'"url":"([^"]+)"', s)
    return [html.unescape(u).replace("\\/", "/") for u in m]


def find_bg(soup, path, data_id):
    base = os.path.dirname(path)
    for l in soup.find_all("link", rel="stylesheet"):
        href = l.get("href", "")
        if "elementor/css/post-" not in href:
            continue
        f = os.path.normpath(os.path.join(base, href.split("?")[0]))
        if not os.path.exists(f):
            continue
        css = open(f, encoding="utf-8", errors="replace").read()
        m = None
        for sel, body in re.findall(r"([^{}]*)\{([^}]*)\}", css):
            if "elementor-element-" + data_id in sel and "background-image" in body:
                m = re.search(r"background-image:\s*url\(['\"]?([^'\")]+)", body)
                if m:
                    break
        if m:
            u = m.group(1)
            return os.path.relpath(os.path.normpath(os.path.join(os.path.dirname(f), u)), ROOT).replace("\\", "/")
    st = soup.find("style", string=re.compile(data_id))
    return None


def extract_page(path):
    soup = BeautifulSoup(open(path, encoding="utf-8").read(), "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    desc = soup.find("meta", attrs={"name": "description"})
    main = soup.find(attrs={"data-elementor-type": re.compile("wp-page|single-post|wp-post|single")})
    if not main:
        main = soup.find(class_="content") or soup.body
    sections = []
    tops = main.find_all(lambda t: t.has_attr("data-element_type") and t["data-element_type"] in ("section", "container")
                         and not t.find_parent(attrs={"data-element_type": ["section", "container"]}))
    if not tops:
        tops = [main]
    for sec in tops:
        blocks = []
        for w in sec.find_all(attrs={"data-element_type": "widget"}):
            if w.find_parent(attrs={"data-element_type": "widget"}):
                continue
            blocks += widget_blocks(w)
        # Spalten-Info: Anzahl direkter Spalten
        cols = sec.find_all(attrs={"data-element_type": ["column"]})
        sections.append({"id": sec.get("data-id"), "cols": len(cols), "bg": section_bg(sec), "blocks": blocks,
                         "classes": " ".join(c for c in sec.get("class", []) if not c.startswith("elementor-element-"))})
    # WordPress-Beitragsinhalt ohne Elementor
    if not any(s["blocks"] for s in sections):
        c = soup.find(class_=re.compile("post_text_inner|entry-content|post_content"))
        if c:
            sections = [{"id": "post", "cols": 1, "bg": [], "blocks": [{"type": "text", "html": clean_inline(c.decode_contents())}]}]
    date = soup.find("meta", attrs={"property": "article:published_time"})
    post_title = soup.find(class_="entry_title")
    post_date = None
    if post_title:
        after = post_title.find_next(string=re.compile(r"\d{1,2}\. \w+ \d{4}"))
        if after:
            post_date = re.search(r"\d{1,2}\. \w+ \d{4}", after).group(0)
    hero_bg = None
    hh = soup.find(class_="header_hoehe")
    if hh and hh.get("data-id"):
        hero_bg = find_bg(soup, path, hh["data-id"])
    ogimg = soup.find("meta", attrs={"property": "og:image"})
    return {
        "title": title,
        "description": desc.get("content") if desc else "",
        "published": date.get("content") if date else None,
        "og_image": ogimg.get("content") if ogimg else None,
        "post_title": post_title.get_text(" ", strip=True) if post_title else None,
        "post_date": post_date,
        "hero_bg": hero_bg,
        "is_post": bool(soup.find("body", class_=re.compile(r"\bsingle-post\b"))),
        "sections": sections,
    }


def extract_nav(soup):
    nav = soup.find("nav", class_=re.compile("main_menu")) or soup.find("nav")
    def walk(ul):
        items = []
        for li in ul.find_all("li", recursive=False):
            a = li.find("a")
            sub = li.find("ul")
            items.append({"text": a.get_text(" ", strip=True) if a else "", "href": a.get("href") if a else None,
                          "children": walk(sub) if sub else []})
        return items
    ul = nav.find("ul") if nav else None
    return walk(ul) if ul else []


def main():
    os.makedirs(OUT, exist_ok=True)
    pages = {}
    for dp, dn, fn in os.walk(ROOT):
        if "wp-content" in dp or "wp-includes" in dp or "_extern" in dp:
            continue
        if "index.html" in fn:
            rel = os.path.relpath(dp, ROOT).replace("\\", "/")
            rel = "" if rel == "." else rel + "/"
            pages[rel] = extract_page(os.path.join(dp, "index.html"))
    home = BeautifulSoup(open(os.path.join(ROOT, "index.html"), encoding="utf-8").read(), "html.parser")
    data = {"nav": extract_nav(home), "pages": pages}
    json.dump(data, open(os.path.join(OUT, "inhalte.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    unk = {}
    for k, p in pages.items():
        for s in p["sections"]:
            for b in s["blocks"]:
                if b["type"] == "unknown":
                    unk.setdefault(b["widget"], []).append(k)
    print(len(pages), "Seiten")
    for k, v in unk.items():
        print("unbekannt:", k, len(v), v[:4])


if __name__ == "__main__":
    main()
