"""Read an agency's name, logo and brand colours from its website, or from a logo file.

Used by blueprint.py:
    brand --site https://www.agency.co.uk        needs the sandbox to reach the site
    brand --logo /path/logo.png [--name N]        always works; colours come from the logo
Standard library only, plus Pillow for raster logos (installed on demand).
"""
from __future__ import annotations

import base64
import colorsys
import io
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
MAX_PAGE, MAX_CSS, MAX_IMG = 3_000_000, 1_500_000, 2_000_000
VOID = {"meta", "link", "img", "br", "hr", "input", "source", "area", "base", "col", "embed", "param", "track", "wbr"}

# Logos that appear on agency sites but are not the agency: portals, trade bodies, schemes, socials, payments.
NOT_THE_AGENCY = re.compile(
    r"rightmove|zoopla|onthemarket|on-the-market|propertymark|naea|arla|\btpo\b|ombudsman|trustpilot|feefo|google|"
    r"facebook|instagram|twitter|linkedin|youtube|tiktok|whatsapp|pinterest|allagents|getagent|\brics\b|safeagent|"
    r"\bcmp\b|client-money|\bprs\b|redress|\bdps\b|\btds\b|mydeposits|award|partner|accredit|member|badge|"
    r"visa|mastercard|paypal|cookie|reapit|alto|jupix|vebra|street\.co|starberry|eurolink|loading|spinner|"
    r"placeholder|avatar|flag|icon-|sprite", re.I)

# Colours that come from frameworks, WordPress defaults and social icons rather than the brand.
FRAMEWORK = {
    "007bff", "0d6efd", "337ab7", "6c757d", "28a745", "198754", "dc3545", "ffc107", "17a2b8", "0dcaf0", "343a40",
    "0073aa", "2271b1", "21759b", "135e96", "72aee6", "d63638", "00a32a", "dba617",
    "cf2e2e", "ff6900", "fcb900", "7bdcb5", "00d084", "8ed1fc", "0693e3", "abb8c3", "9b51e0", "f78da7",
    "4285f4", "34a853", "fbbc05", "ea4335", "3b5998", "1877f2", "1da1f2", "25d366", "0077b5", "0a66c2",
    "e4405f", "c13584", "ff0000", "bd081c", "00b67a", "ff3e00", "2196f3", "4caf50", "f44336", "9c27b0",
    # Bootstrap 3 states and buttons
    "dff0d8", "3c763d", "d9edf7", "31708f", "fcf8e3", "8a6d3b", "f2dede", "a94442", "23527c", "286090", "204d74",
    "5cb85c", "449d44", "5bc0de", "31b0d5", "f0ad4e", "ec971f", "d9534f", "c9302c", "2e6da4", "428bca", "3071a9",
    # WordPress block editor and Tailwind defaults
    "007cba", "006ba1", "005a87", "2563eb", "3b82f6", "1d4ed8", "60a5fa", "ef4444", "dc2626", "10b981", "22c55e",
    "f59e0b", "6366f1", "4f46e5", "8b5cf6", "ec4899",
    # Bootstrap 5 tints and shades
    "cfe2ff", "9ec5fe", "6ea8fe", "3d8bfd", "0a58ca", "084298", "052c65", "d1e7dd", "a3cfbb", "75b798", "479f76",
    "146c43", "0f5132", "f8d7da", "f1aeb5", "ea868f", "e35d6a", "b02a37", "842029", "fff3cd", "ffe69b", "ffda6a",
    "ffcd39", "cc9a06", "997404", "664d03", "cff4fc", "9eeaf9", "6edff6", "3dd5f3", "087990", "055160", "6610f2",
    "6f42c1", "d63384", "fd7e14", "20c997", "e9ecef", "dee2e6", "ced4da", "adb5bd", "495057", "212529", "f8f9fa",
}


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.icons: list[dict] = []
        self.css: list[str] = []
        self.styles: list[str] = []
        self.imgs: list[dict] = []
        self.title = ""
        self._stack: list[tuple[str, bool, str | None]] = []
        self._in: str | None = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        ident = " ".join(a.get(k, "") for k in ("class", "id", "alt", "title", "aria-label", "src", "data-src", "href")).lower()
        logoish = "logo" in ident or "brand" in a.get("class", "").lower()
        region = tag if tag in ("header", "nav", "footer") else None
        parent_logo = any(s[1] for s in self._stack)
        parent_region = next((s[2] for s in reversed(self._stack) if s[2]), None)
        if tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link":
            rel, href = a.get("rel", "").lower(), a.get("href", "")
            if "stylesheet" in rel and href:
                self.css.append(href)
            if "icon" in rel and href:
                self.icons.append({"href": href, "rel": rel, "sizes": a.get("sizes", ""), "color": a.get("color", "")})
        elif tag == "img":
            src = (a.get("src") or a.get("data-src") or a.get("data-lazy-src")
                   or (a.get("srcset", "").split(",")[0].strip().split(" ")[0] if a.get("srcset") else ""))
            if src:
                self.imgs.append({"src": src, "ident": ident, "logo": logoish, "parent_logo": parent_logo,
                                  "region": parent_region, "order": len(self.imgs), "alt": a.get("alt", "")})
        elif tag == "style":
            self._in = "style"
        elif tag == "title":
            self._in = "title"
        if a.get("style"):
            self.styles.append(a["style"])
        if tag not in VOID:
            self._stack.append((tag, logoish, region or parent_region))

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break
        if tag in ("style", "title"):
            self._in = None

    def handle_data(self, data):
        if self._in == "style":
            self.styles.append(data)
        elif self._in == "title":
            self.title += data


# ---------------------------------------------------------------- colour helpers


def parse_colour(text: str) -> tuple[int, int, int] | None:
    text = text.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})([0-9a-f]{2})?", text)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if m.group(2) and int(m.group(2), 16) < 0x80:  # mostly transparent
            return None
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)(?:[\s,/]+([\d.]+%?))?\s*\)", text)
    if m:
        if m.group(4):
            alpha = float(m.group(4).rstrip("%")) / (100 if m.group(4).endswith("%") else 1)
            if alpha < 0.5:
                return None
        return tuple(min(255, int(m.group(i))) for i in (1, 2, 3))
    return None


def to_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def luminance(rgb) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = map(ch, rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_neutral(rgb) -> bool:
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
    return s < 0.18 or l > 0.93 or l < 0.06


class Palette:
    def __init__(self) -> None:
        self.items: list[list] = []  # [rgb, weight, sources]

    def add(self, colour, weight: float, source: str) -> None:
        rgb = colour if isinstance(colour, tuple) else parse_colour(colour)
        if not rgb or weight <= 0:
            return
        if "{:02x}{:02x}{:02x}".format(*rgb) in FRAMEWORK:
            weight *= 0.1
        if is_neutral(rgb):
            weight *= 0.15
        elif colorsys.rgb_to_hls(*(v / 255 for v in rgb))[1] > 0.85:  # pale tints are backgrounds, rarely the brand
            weight *= 0.3
        for item in self.items:
            if sum((a - b) ** 2 for a, b in zip(item[0], rgb)) < 28 ** 2:
                item[1] += weight
                item[2].add(source)
                return
        self.items.append([rgb, weight, {source}])

    def ranked(self) -> list[dict]:
        out = sorted(self.items, key=lambda i: -i[1])
        return [{"hex": to_hex(i[0]), "weight": round(i[1], 1), "neutral": is_neutral(i[0]), "sources": sorted(i[2])}
                for i in out]

    def primary(self) -> dict | None:
        ranked = self.ranked()
        for c in ranked:
            if not c["neutral"]:
                return c
        dark = [c for c in ranked if luminance(parse_colour(c["hex"])) < 0.05]  # a black-and-white brand
        return dark[0] if dark else None


# ---------------------------------------------------------------- fetching


def fetch(url: str, limit: int, accept: str = "*/*") -> tuple[str, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en-GB,en;q=0.9",
                                               "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.geturl(), r.headers.get("Content-Type", ""), r.read(limit)
    except urllib.error.URLError as exc:
        # Small agency sites often run on lapsed certificates. We only read public branding and send nothing,
        # so retry without verification rather than fail.
        if not isinstance(getattr(exc, "reason", None), ssl.SSLError):
            raise
        with urllib.request.urlopen(req, timeout=20, context=ssl._create_unverified_context()) as r:
            return r.geturl(), r.headers.get("Content-Type", ""), r.read(limit)


def decode(data: bytes, ctype: str) -> str:
    m = re.search(r"charset=([\w-]+)", ctype or "")
    for enc in ([m.group(1)] if m else []) + ["utf-8", "latin-1"]:
        try:
            return data.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", "replace")


# ---------------------------------------------------------------- logos


def need_pillow():
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pillow"], check=False)
    from PIL import Image
    return Image


def svg_info(svg: str) -> dict:
    fills = re.findall(r"(?:fill|stroke|stop-color)\s*[:=]\s*[\"']?\s*(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))", svg)
    rgbs = [c for c in (parse_colour(f) for f in fills) if c]
    lum = sum(luminance(c) for c in rgbs) / len(rgbs) if rgbs else None
    return {"colours": rgbs, "tone": "unknown" if lum is None else ("light" if lum > 0.6 else "dark" if lum < 0.35 else "mixed")}


def raster_info(data: bytes) -> dict:
    Image = need_pillow()
    im = Image.open(io.BytesIO(data))
    im.seek(0)
    im = im.convert("RGBA")
    if im.height > 200:
        im = im.resize((max(1, round(im.width * 200 / im.height)), 200))
    if im.width > 900:
        im = im.resize((900, max(1, round(im.height * 900 / im.width))))
    px = [p for p in im.getdata() if p[3] > 200]
    lum = sum(luminance(p[:3]) for p in px) / len(px) if px else None
    small = im.copy()
    small.thumbnail((120, 120))
    counts = {}
    for p in small.getdata():
        if p[3] > 200:
            key = tuple(v // 16 * 16 + 8 for v in p[:3])
            counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values()) or 1
    colours = [(rgb, n / total) for rgb, n in sorted(counts.items(), key=lambda kv: -kv[1])[:12]]
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return {"png": buf.getvalue(), "colours": colours, "width": im.width, "height": im.height,
            "tone": "unknown" if lum is None else ("light" if lum > 0.6 else "dark" if lum < 0.35 else "mixed")}


def logo_from_bytes(data: bytes, ctype: str, source: str) -> dict | None:
    head = data[:2000].lstrip().lower()
    if b"<svg" in head or "svg" in ctype:
        svg = decode(data, ctype)
        if "<svg" not in svg.lower():
            return None
        info = svg_info(svg)
        return {"mime": "image/svg+xml", "data": base64.b64encode(svg.encode("utf-8")).decode(), "tone": info["tone"],
                "colours": [(c, 1 / max(1, len(info["colours"]))) for c in info["colours"]], "source": source}
    try:
        info = raster_info(data)
    except Exception:
        return None
    if info["width"] < 40 or info["height"] < 16:
        return None
    return {"mime": "image/png", "data": base64.b64encode(info["png"]).decode(), "tone": info["tone"],
            "colours": info["colours"], "source": source}


def logo_candidates(page: Page, raw: str, css_text: str, base: str, label: str) -> list[tuple[float, str, str | None]]:
    cands: list[tuple[float, str, str | None]] = []  # (score, url or "", inline svg)
    for c in page.imgs:
        compact = re.sub(r"[^a-z0-9]", "", c["ident"])
        s = 0.0
        s += 6 if c["logo"] else 0
        s += 4 if c["parent_logo"] else 0
        s += 3 if c["region"] in ("header", "nav") else 0
        s -= 3 if c["region"] == "footer" else 0
        src = c["src"].lower()
        s += 2 if re.search(r"\.svg(\?|$)", src) else 1 if re.search(r"\.png(\?|$)", src) else 0
        s += 3 if label and label in compact else 0
        s -= 9 if NOT_THE_AGENCY.search(c["ident"]) else 0
        s -= 6 if src.startswith("data:") and len(src) < 300 else 0
        s -= c["order"] * 0.05
        cands.append((s, urllib.parse.urljoin(base, c["src"]), None))
    for m in re.finditer(r"<svg\b[^>]*>.*?</svg>", raw, re.S | re.I):
        before = raw[max(0, m.start() - 400):m.start()].lower()
        tag = m.group(0)[:400].lower()
        if "logo" in tag or "logo" in before[-250:]:
            svg = m.group(0)
            if 200 < len(svg) < 300_000 and not NOT_THE_AGENCY.search(tag):
                s = 7 + (2 if "<header" in raw[max(0, m.start() - 3000):m.start()].lower() else 0)
                if "xmlns" not in svg[:200]:
                    svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
                cands.append((s, "", svg))
    for m in re.finditer(r"([^{}]*logo[^{}]*)\{[^}]*?url\(\s*['\"]?([^'\")]+)", css_text, re.I):
        if not NOT_THE_AGENCY.search(m.group(1) + m.group(2)):
            cands.append((5.0, urllib.parse.urljoin(base, m.group(2).strip()), None))
    for ic in page.icons:  # last resort: the touch icon is usually the brand mark
        size = max([int(x) for x in re.findall(r"\d+", ic["sizes"])] or [0])
        if "apple-touch" in ic["rel"] or size >= 120:
            cands.append((1.0, urllib.parse.urljoin(base, ic["href"]), None))
    cands.sort(key=lambda c: -c[0])
    return cands


# ---------------------------------------------------------------- name


def agency_name(page: Page, label: str, logo_alt: str) -> str:
    title = re.sub(r"\s+", " ", page.title).strip()
    parts = [p.strip() for p in re.split(r"\s+[|\-–—:·•]\s+", title) if p.strip()]
    pool = [page.meta.get("og:site_name", ""), page.meta.get("application-name", "")] + parts + [logo_alt]
    pool = [re.sub(r"(?i)^(welcome to|home)\s*[|\-–:]?\s*|\s*[|\-–:]?\s*(home|homepage)$", "", p).strip() for p in pool if p]
    for p in pool:
        compact = re.sub(r"[^a-z0-9]", "", p.lower())
        if label and len(label) >= 4 and (label in compact or (compact and compact in label and len(compact) >= 4)):
            return p if len(p) <= 60 else p[:60].rsplit(" ", 1)[0]
    for p in pool:
        if p and "logo" not in p.lower() and len(p) <= 60:
            return p
    return label.title() if label else ""


# ---------------------------------------------------------------- entry points


def from_site(site: str) -> dict:
    if not re.match(r"https?://", site, re.I):
        site = "https://" + site.strip().lstrip("/")
    try:
        final, ctype, data = fetch(site, MAX_PAGE, "text/html,application/xhtml+xml")
    except Exception as exc:
        return {"status": "unreachable", "site": site, "detail": str(exc)[:300]}
    raw = decode(data, ctype)
    page = Page()
    try:
        page.feed(raw)
    except Exception:
        pass
    host = (urllib.parse.urlparse(final).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    label = re.sub(r"[^a-z0-9]", "", host.split(".")[0])

    css_text = "\n".join(page.styles)
    for href in page.css[:5]:
        try:
            _, ct, body = fetch(urllib.parse.urljoin(final, href), MAX_CSS, "text/css,*/*")
            css_text += "\n" + decode(body, ct)
        except Exception:
            continue

    pal = Palette()
    for key, w in (("theme-color", 12), ("msapplication-tilecolor", 6)):
        if page.meta.get(key):
            pal.add(page.meta[key], w, key)
    for ic in page.icons:
        if ic["color"]:
            pal.add(ic["color"], 6, "mask-icon")
    for m in re.finditer(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\))", css_text):
        name = m.group(1).lower()
        if name.startswith(("wp--preset", "bs-")):  # WordPress and Bootstrap defaults, not the brand
            continue
        w = 6 if re.search(r"primary|brand|main|theme", name) else 3 if re.search(r"accent|secondary|highlight", name) else 0.4
        pal.add(m.group(2), w, "css-variable")
    counts: dict[str, int] = {}
    for m in re.finditer(r"(?<![\w-])(color|background(?:-color)?|border(?:-[a-z]+)?-color|fill|stroke)\s*:\s*([^;{}]+)", css_text, re.I):
        for c in re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", m.group(2)):
            key = c.lower()
            counts[key] = counts.get(key, 0) + 1
    for c, n in counts.items():
        pal.add(c, min(n, 40) * 0.5, "css")

    logo = None
    tried = 0
    for score, url, inline in logo_candidates(page, raw, css_text, final, label):
        if score < 1 or tried >= 6:
            break
        tried += 1
        if inline:
            logo = logo_from_bytes(inline.encode("utf-8"), "image/svg+xml", "inline svg")
        else:
            try:
                _, ct, body = fetch(url, MAX_IMG, "image/svg+xml,image/*,*/*")
                logo = logo_from_bytes(body, ct, url)
            except Exception:
                logo = None
        if logo:
            logo["score"] = round(score, 1)
            break
    if logo:
        for rgb, share in logo["colours"]:
            pal.add(rgb, 14 * share, "logo")
    primary = pal.primary()
    alt = next((c["alt"] for c in page.imgs if c["logo"] and c["alt"]), "")
    return {
        "status": "ok",
        "site": final,
        "name": agency_name(page, label, alt),
        "colour": primary["hex"] if primary else None,
        "colour_sources": primary["sources"] if primary else [],
        "palette": [c["hex"] for c in pal.ranked()[:5]],
        "logo": {k: logo[k] for k in ("mime", "data", "tone", "source")} if logo else None,
    }


def from_logo_file(path: str) -> dict:
    with open(path, "rb") as f:
        data = f.read(MAX_IMG)
    ctype = "image/svg+xml" if path.lower().endswith(".svg") else ""
    logo = logo_from_bytes(data, ctype, path)
    if not logo:
        return {"status": "error", "message": "That file doesn't look like a logo image (PNG, JPG, WebP or SVG)."}
    pal = Palette()
    for rgb, share in logo["colours"]:
        pal.add(rgb, 14 * share, "logo")
    primary = pal.primary()
    return {"status": "ok", "colour": primary["hex"] if primary else None, "colour_sources": ["logo"],
            "palette": [c["hex"] for c in pal.ranked()[:5]],
            "logo": {k: logo[k] for k in ("mime", "data", "tone", "source")}}
