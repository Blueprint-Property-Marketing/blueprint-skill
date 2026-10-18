"""Blueprint: local property data for UK estate agents and developers, inside Claude.

    python blueprint.py fetch  "<any address, postcode, district or place>"   get that area's data
    python blueprint.py areas [--search S]     coverage summary, or districts matching a place name
    python blueprint.py stats  <district>      headline figures for a market update (JSON)
    python blueprint.py query  <district> [--street S] [--postcode P] [--address A] [--type D|S|T|F] [--since YYYY-MM]
                                  [--new] [--min N] [--max N] [--limit N]
    python blueprint.py files  <district>      where the raw files are and what every column means (for own analysis)
    python blueprint.py compare <district> <district> [<district>]
                                           two or three areas side by side: one self-contained HTML file
    python blueprint.py brand --site URL | --logo FILE [--name N] [--colour #hex] | --clear
                                           the agency's logo, colours and name for the dashboard (saved for the chat)
    python blueprint.py dashboard <district> [--name N] [--colour #hex] [--blueprint-style] [--out DIR]
                                           the area dashboard: one self-contained HTML file (show it as an artifact)
    python blueprint.py offer  <moment>        the Blueprint line for a moment (brochure, development, ads,
                                           website, email, branding, gap, about, follow), with a tracked link

Data comes from the Blueprint skill repository on github.com (a sparse git clone fetches only the
area asked for). If GitHub can't be reached, attach the area's ZIP from the repository's
Releases page and run:  python blueprint.py fetch <district> --zip <path>
Everything prints JSON so Claude can read it; nothing here needs an API key.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.parse
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brandkit  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
CACHE = Path(tempfile.gettempdir()) / "blueprint-data"
REPO_DIR = CACHE / "repo"
BRAND_FILE = CACHE / "brand.json"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
TYPE_NAMES = {"D": "Detached", "S": "Semi-detached", "T": "Terraced", "F": "Flat or maisonette", "O": "Other"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
POSTCODE_DISTRICT = re.compile(r"^\s*([A-Z]{1,2}[0-9][0-9A-Z]?)\s*([0-9][A-Z]{2})?\s*$", re.I)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def out(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def fail(status: str, message: str, **extra) -> None:
    out({"status": status, "message": message, **extra})
    sys.exit(1)


def repo_url() -> str:
    if os.environ.get("BLUEPRINT_REPO"):
        return os.environ["BLUEPRINT_REPO"]
    cfg = json.loads((SKILL_DIR / "config.json").read_text(encoding="utf-8"))
    return cfg["repo"]


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120)


# ---------------------------------------------------------------- fetch


def ensure_clone() -> None:
    """Shallow, blob-less, sparse clone: only root files (areas.json, offers.json) until an area is added."""
    fresh = (REPO_DIR / ".git").exists() and time.time() - (REPO_DIR / ".git").stat().st_mtime < 3600
    if fresh:
        return
    if shutil.which("git") is None:
        fail("offline", "git is not available here.", hint="Attach the area ZIP from the Blueprint skill's Releases page.")
    shutil.rmtree(REPO_DIR, ignore_errors=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    r = git("clone", "--depth", "1", "--filter=blob:none", "--sparse", repo_url(), str(REPO_DIR))
    if r.returncode != 0:
        fail("offline", "Could not reach the Blueprint area data on GitHub.",
             detail=r.stderr.strip()[-400:],
             hint="Download the area ZIP from the Blueprint skill's Releases page, attach it to the chat, then run "
                  "fetch <district> --zip <path>.")


def load_index() -> dict:
    p = REPO_DIR / "areas.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"areas": []}


FULL_POSTCODE = re.compile(r"\b([A-Z]{1,2}[0-9][0-9A-Z]?)\s*([0-9][A-Z]{2})\b", re.I)
DISTRICT_TOKEN = re.compile(r"\b([A-Z]{1,2}[0-9][0-9A-Z]?)\b", re.I)
OUTSIDE = re.compile(r"^(AB|DD|DG|EH|FK|G|HS|IV|KA|KW|KY|ML|PA|PH|ZE|BT|GY|JE|IM)[0-9]", re.I)  # not in Land Registry data
SCOTTISH_TD = {f"TD{n}" for n in range(1, 15)}  # TD15 (Berwick) is in England


def outside_england_and_wales(district: str) -> bool:
    return bool(OUTSIDE.match(district)) or district.upper() in SCOTTISH_TD


def resolve(area: str, index: dict) -> tuple[str | None, list[dict]]:
    """Any address, postcode, district or place name -> (district, other candidates).
    A full postcode anywhere in the text wins; then a district code; then a place name (several districts can
    share one, so all matches come back)."""
    known = {a["district"].upper(): a for a in index.get("areas", [])}
    m = FULL_POSTCODE.search(area)
    if m:
        return m.group(1).upper(), []
    tokens = [tok.upper() for tok in DISTRICT_TOKEN.findall(area) if tok.upper() in known or outside_england_and_wales(tok)]
    if tokens and len(area.split()) <= 3:  # "M33", "my patch M33": a code on its own
        return tokens[0], []
    text = f" {re.sub(r'[^a-z0-9]+', ' ', area.lower())} "
    matches = [a for a in index.get("areas", []) if f" {re.sub(r'[^a-z0-9]+', ' ', a['name'].lower()).strip()} " in text]
    if not matches:
        matches = [a for a in index.get("areas", []) if f" {a['local_authority'].lower()} " in text]
    if len(matches) == 1:
        return matches[0]["district"].upper(), []
    if matches:
        return None, matches
    if tokens:  # a longer text with a code in it and no place name ("Flat B1" stays ambiguous only if nothing else)
        return tokens[0], []
    return None, []


def area_dir(district: str) -> Path:
    for base in (REPO_DIR / "areas" / district.lower(), CACHE / "zip" / district.lower()):
        if (base / "meta.json").exists():
            return base
    fail("not_fetched", f"No data for {district} yet.", hint=f"Run: python blueprint.py fetch {district}")
    raise SystemExit  # for type checkers


def fetch_from_zip(district: str, zip_path: str) -> Path:
    dest = CACHE / "zip" / district.lower()
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    want = district.lower()
    with zipfile.ZipFile(zip_path) as z:
        for member in z.namelist():
            parts = Path(member).parts
            name = parts[-1]
            if name == "offers.json" and len(parts) <= 2:
                (dest / name).write_bytes(z.read(member))
            elif len(parts) >= 2 and parts[-2].lower() == want and name in ("sales.csv", "hpi.json", "meta.json", "postcodes.csv"):
                (dest / name).write_bytes(z.read(member))
    if not (dest / "meta.json").exists():
        fail("error", f"That file doesn't hold {district}. Use the postcode-area file that starts with the same "
                      f"letters (for M33, blueprint-areas-M.zip).")
    return dest


def cmd_fetch(a) -> None:
    if a.zip:
        district, _ = resolve(a.area, {"areas": []})
        district = (district or a.area).upper()
        d = fetch_from_zip(district, a.zip)
        out({"status": "ok", "district": district, "source": "zip", "meta": read_json(d / "meta.json")})
        return
    ensure_clone()
    index = load_index()
    district, candidates = resolve(a.area, index)
    if not district and candidates:
        out({"status": "ambiguous", "asked": a.area,
             "options": [f'{c["district"]} ({c["name"]}, {c["local_authority"]})' for c in candidates[:12]],
             "message": "Several postcode districts match. Ask which one, or for the postcode."})
        sys.exit(1)
    if not district:
        out({"status": "need_postcode", "asked": a.area,
             "message": "No postcode or known place found. Ask for the postcode (or find it with web search), then fetch again."})
        sys.exit(1)
    covered = {x["district"].upper() for x in index.get("areas", [])}
    # Border districts (DG16, TD) have homes on both sides: the data decides first, then the postcode letters.
    if district not in covered and outside_england_and_wales(district):
        out({"status": "outside", "district": district,
             "message": "HM Land Registry's sold prices cover England and Wales, so this postcode isn't in the data."})
        sys.exit(1)
    if district not in covered:
        out({"status": "no_sales", "district": district,
             "message": f"No standard residential sales are registered in {district} since 2021 (or the district doesn't "
                        "exist). Check the postcode, or try a neighbouring district."})
        sys.exit(1)
    r = git("sparse-checkout", "add", f"areas/{district.lower()}", cwd=REPO_DIR)
    if r.returncode != 0:
        fail("offline", "Could not download that area's files.", detail=r.stderr.strip()[-400:])
    meta = read_json(REPO_DIR / "areas" / district.lower() / "meta.json")
    out({"status": "ok", "district": district, "source": "github", "meta": meta})


def cmd_areas(a) -> None:
    ensure_clone()
    index = load_index()
    areas = index.get("areas", [])
    if a.search:
        q = a.search.lower()
        found = [x for x in areas if q in x["name"].lower() or q in x["local_authority"].lower() or x["district"].lower() == q]
        out({"status": "ok", "matches": [f'{x["district"]} ({x["name"]}, {x["local_authority"]})' for x in found[:40]]})
        return
    out({"status": "ok", "coverage": "Every postcode district in England and Wales with registered sales",
         "districts": len(areas), "updated": index.get("updated"),
         "data_to": max((x["latest_registered_sale"] for x in areas), default=None)})


def read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# ---------------------------------------------------------------- data


def load(district: str) -> tuple[list[dict], dict, dict]:
    d = area_dir(district)
    with open(d / "sales.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["price"] = int(r["price"])
        r["day"] = dt.date.fromisoformat(r["date"])
    return rows, read_json(d / "meta.json"), read_json(d / "hpi.json")


def month_label(d: dt.date | str, short: bool = False) -> str:
    if isinstance(d, str):
        d = dt.date.fromisoformat(d + "-01" if len(d) == 7 else d)
    name = MONTHS[d.month - 1]
    return f"{name[:3] if short else name} {d.year}"


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    return dt.date(d.year + y, m + 1, 1)


def med(xs: list[int]) -> int | None:
    return int(statistics.median(xs)) if xs else None


def type_block(rows: list[dict]) -> list[dict]:
    by = defaultdict(list)
    lease = Counter()
    for r in rows:
        if r["type"] != "O":
            by[r["type"]].append(r["price"])
            lease[r["type"]] += r["tenure"] == "L"
    blocks = []
    for t in ("D", "S", "T", "F"):
        n = len(by.get(t, []))
        blocks.append({"type": TYPE_NAMES[t], "sales": n,
                       "median_price": med(by[t]) if n >= 10 else None,
                       "leasehold_pct": round(100 * lease[t] / n) if n else None,
                       "note": None if n >= 30 else ("too few sales to quote a median" if n < 10 else "small sample")})
    return blocks


def postcode_sector(pc: str) -> str:
    out_code, _, in_code = pc.partition(" ")
    return f"{out_code} {in_code[:1]}".strip()


def new_build_summary(rows: list[dict]) -> dict:
    """New-build sales: schemes (a street in one postcode sector with 3+ new-build sales) and new build vs
    established homes of the same type over the same months."""
    nb = [r for r in rows if r["new"] == "Y"]
    data_to = rows[0]["day"]
    start_12 = add_months(dt.date(data_to.year, data_to.month, 1), -11)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in nb:
        groups[(r["street"], postcode_sector(r["postcode"]))].append(r)
    schemes = []
    for (street, sector), rs in groups.items():
        if len(rs) < 3:
            continue
        prices = [r["price"] for r in rs]
        days = [r["day"] for r in rs]
        schemes.append({"street": street, "sector": sector, "sales": len(rs),
                        "first": month_label(min(days), True), "last": month_label(max(days), True),
                        "last_iso": max(days).isoformat(),
                        "median_price": med(prices) if len(rs) >= 5 else None,
                        "price_range": [min(prices), max(prices)],
                        "types": dict(Counter(TYPE_NAMES[r["type"]] for r in rs).most_common()),
                        "leasehold_pct": round(100 * sum(r["tenure"] == "L" for r in rs) / len(rs))})
    schemes.sort(key=lambda s: s["last_iso"], reverse=True)
    versus = []
    for code in ("D", "S", "T", "F"):
        nbt = [r for r in nb if r["type"] == code]
        if len(nbt) < 5:
            continue
        lo, hi = min(r["day"] for r in nbt), max(r["day"] for r in nbt)
        sectors = sorted({postcode_sector(r["postcode"]) for r in nbt})  # same places, same months
        est = [r["price"] for r in rows if r["type"] == code and r["new"] == "N" and lo <= r["day"] <= hi
               and postcode_sector(r["postcode"]) in sectors]
        versus.append({"type": TYPE_NAMES[code], "period": f"{month_label(lo, True)} to {month_label(hi, True)}",
                       "sectors": sectors,
                       "new_build_median": med([r["price"] for r in nbt]), "new_build_sales": len(nbt),
                       "established_median": med(est) if len(est) >= 10 else None, "established_sales": len(est)})
    latest = max(nb, key=lambda r: r["day"]) if nb else None
    return {
        "since_start": len(nb),
        "share_pct": round(100 * len(nb) / len(rows), 1) if rows else None,
        "last_12_months": sum(1 for r in nb if r["day"] >= start_12),
        "latest": {"street": latest["street"], "sector": postcode_sector(latest["postcode"]),
                   "month": month_label(latest["day"])} if latest else None,
        "schemes": schemes[:12],
        "vs_established": versus,
        "note": "A scheme here is a street within one postcode sector with three or more new-build sales. Established "
                "homes are compared in the same postcode sectors over the same months, but new and established homes "
                "still differ in size and specification, and floor areas aren't in this data: show both medians with "
                "their sample sizes and don't present the gap as a new-build premium.",
    }


def cmd_stats(a) -> None:
    out(stats(a.district.upper()))


def stats(district: str) -> dict:
    rows, meta, hpi = load(district)
    data_to = rows[0]["day"]
    start_12 = add_months(dt.date(data_to.year, data_to.month, 1), -11)
    last12 = [r for r in rows if r["day"] >= start_12]

    # volume comparison on a settled window (ends three months before the latest month, so registration lag is mostly over)
    settled_end = add_months(dt.date(data_to.year, data_to.month, 1), -2)  # first day of month, exclusive bound
    s_start = add_months(settled_end, -12)
    p_start = add_months(settled_end, -24)
    this_yr = sum(1 for r in rows if s_start <= r["day"] < settled_end)
    prev_yr = sum(1 for r in rows if p_start <= r["day"] < s_start)
    volume = None
    if this_yr >= 30 and prev_yr >= 30:
        volume = {"window": f"{month_label(s_start, True)} to {month_label(add_months(settled_end, -1), True)}",
                  "sales": this_yr, "previous_year_sales": prev_yr,
                  "change_pct": round(100 * (this_yr - prev_yr) / prev_yr, 1)}

    streets = Counter(r["street"] for r in last12 if r["street"])
    street_rows = defaultdict(list)
    for r in last12:
        street_rows[r["street"]].append(r["price"])
    busiest = [{"street": s, "sales": n, "median_price": med(street_rows[s]) if n >= 5 else None}
               for s, n in streets.most_common(5) if n >= 3]
    top = max(last12, key=lambda r: r["price"]) if last12 else None
    bands = [(0, 250_000, "Under £250k"), (250_000, 500_000, "£250k to £500k"),
             (500_000, 1_000_000, "£500k to £1m"), (1_000_000, 10**12, "£1m and over")]
    band_out = [{"band": label, "sales": sum(1 for r in last12 if lo <= r["price"] < hi)} for lo, hi, label in bands]
    for b in band_out:
        b["share_pct"] = round(100 * b["sales"] / len(last12)) if last12 else None

    la = (hpi.get("local_authority") or {}).get("latest") or {}
    reg = (hpi.get("region") or {}).get("latest") or {}
    eng = (hpi.get("country") or {}).get("latest") or {}
    same_geo = (hpi.get("region") or {}).get("slug") and         (hpi.get("region") or {}).get("slug") == (hpi.get("country") or {}).get("slug")
    if same_geo:  # Wales: the region is the country, so it is shown once
        eng = {}
    hpi_out = None
    if la:
        hpi_out = {
            "geography": meta["local_authority"],
            "month": month_label(la["month"]),
            "average_price": la["averagePrice"],
            "annual_change_pct": la["percentageAnnualChange"],
            "monthly_change_pct": la["percentageChange"],
            "by_type": [
                {"type": "Detached", "average_price": la["averagePriceDetached"], "annual_change_pct": la["percentageAnnualChangeDetached"]},
                {"type": "Semi-detached", "average_price": la["averagePriceSemiDetached"], "annual_change_pct": la["percentageAnnualChangeSemiDetached"]},
                {"type": "Terraced", "average_price": la["averagePriceTerraced"], "annual_change_pct": la["percentageAnnualChangeTerraced"]},
                {"type": "Flat or maisonette", "average_price": la["averagePriceFlatMaisonette"], "annual_change_pct": la["percentageAnnualChangeFlatMaisonette"]},
            ],
            "first_time_buyer_average": la.get("averagePriceFirstTimeBuyer"),
            "region": {"name": meta.get("region"), "annual_change_pct": reg.get("percentageAnnualChange"), "average_price": reg.get("averagePrice")},
            "country": {"name": meta.get("country") if eng else None, "annual_change_pct": eng.get("percentageAnnualChange"), "average_price": eng.get("averagePrice")},
            "series": [{"month": s["month"], "average_price": s["averagePrice"]} for s in hpi["local_authority"]["series"]],
        }

    return {
        "status": "ok",
        "area": {"name": meta["name"], "district": meta["district"], "local_authority": meta["local_authority"]},
        "update_label": month_label(dt.date.today()),
        "data": {"latest_registered_sale": data_to.isoformat(), "hpi_month": hpi_out["month"] if hpi_out else None,
                 "sales_since": meta.get("sales_from"), "sales_on_file": len(rows)},
        "price_trend": hpi_out,
        "last_12_months": {
            "window": f"{month_label(start_12, True)} to {month_label(data_to, True)}",
            "registered_sales": len(last12),
            "median_price": med([r["price"] for r in last12]),
            "by_type": type_block(last12),
            "new_build_sales": sum(1 for r in last12 if r["new"] == "Y"),
            "price_bands": band_out,
            "busiest_streets": busiest,
            "top_sale": {"price": top["price"], "type": TYPE_NAMES[top["type"]], "street": top["street"],
                         "month": month_label(top["day"])} if top else None,
        },
        "volume_vs_last_year": volume,
        "new_builds": new_build_summary(rows),
        "latest_sales": [{"month": month_label(r["day"]), "street": r["street"], "type": TYPE_NAMES[r["type"]],
                          "tenure": "Freehold" if r["tenure"] == "F" else "Leasehold", "new_build": r["new"] == "Y",
                          "price": r["price"]} for r in rows[:6]],
        "caveats": [
            f"Price trends are the UK House Price Index for {meta['local_authority']} (the local authority), "
            f"not {meta['name']} or {meta['district']} alone. Say so.",
            "Registered sales lag completions by weeks to months; the latest months are incomplete. "
            "Say 'registered sales' and never present the last few months as a slowdown.",
            "Do not work out a price change from these medians; use the UK HPI figures.",
            "Medians marked 'small sample' need the sample size alongside them; null medians must not be quoted.",
        ],
        "attribution": (f"Contains HM Land Registry data © Crown copyright and database right {dt.date.today().year}. "
                        "This data is licensed under the Open Government Licence v3.0."),
    }


def cmd_query(a) -> None:
    rows, meta, _ = load(a.district.upper())
    res = rows
    if a.street:
        s = a.street.lower()
        res = [r for r in res if s in r["street"].lower()]
    if a.postcode:
        p = a.postcode.upper().replace(" ", "")
        res = [r for r in res if r["postcode"].replace(" ", "").startswith(p)]
    if a.type:
        res = [r for r in res if r["type"] == a.type.upper()]
    if a.since:
        since = dt.date.fromisoformat(a.since + "-01" if len(a.since) == 7 else a.since)
        res = [r for r in res if r["day"] >= since]
    if a.address:  # every word must appear in the house number/name and street, e.g. "22 Urban" or "Flat 3 Linden Lea"
        words = a.address.lower().replace(",", " ").split()
        res = [r for r in res if all(w in f"{r['saon']} {r['paon']} {r['street']}".lower().split() or
                                     w in f"{r['saon']} {r['paon']} {r['street']}".lower() for w in words)]
    if a.new:
        res = [r for r in res if r["new"] == "Y"]
    if a.min:
        res = [r for r in res if r["price"] >= a.min]
    if a.max:
        res = [r for r in res if r["price"] <= a.max]
    prices = [r["price"] for r in res]
    out({"status": "ok", "district": meta["district"], "matches": len(res),
         "median_price": med(prices) if len(prices) >= 5 else None,
         "median_note": None if len(prices) >= 30 else ("too few sales to quote a median" if len(prices) < 5 else "small sample"),
         "note": "House numbers are for the user's own reference (valuations, letters). Leave them out of public posts.",
         "sales": [{"date": r["date"], "price": r["price"], "number_or_name": " ".join(x for x in (r["saon"], r["paon"]) if x),
                    "street": r["street"], "postcode": r["postcode"], "type": TYPE_NAMES[r["type"]],
                    "tenure": "Freehold" if r["tenure"] == "F" else "Leasehold", "new_build": r["new"] == "Y"}
                   for r in res[: a.limit]]})


def load_offers() -> dict:
    """offers.json from the GitHub checkout, or from an attached area ZIP."""
    found = read_json(REPO_DIR / "offers.json")
    if not found:
        for f in sorted((CACHE / "zip").glob("*/offers.json")):
            found = read_json(f)
            break
    return found


def tracked(url: str, moment: str) -> str:
    """Tag Blueprint links so the site's analytics can tell which reply moments bring visits."""
    sep = "&" if "?" in url else "?"
    return f"{url.rstrip('/')}/{sep}utm_source=claude&utm_medium=skill&utm_campaign=blueprint-skill&utm_content={moment}"


def cmd_offer(a) -> None:
    offers = load_offers()
    moments = offers.get("moments") or {}
    m = moments.get(a.moment) or {}
    line = (m.get("line") or (offers.get("plays") or {}).get(a.moment, "")).replace("{area}", a.area or "your area")
    contact = offers.get("contact") or {}
    link = None
    if line and m.get("link") == "email" and contact.get("email"):
        subject = urllib.parse.quote(f"From the Blueprint skill: {m.get('subject') or a.moment}")
        link = {"text": contact["email"], "url": f"mailto:{contact['email']}?subject={subject}"}
    elif line and m.get("link") == "site" and contact.get("site"):
        link = {"text": contact["site"].split("//")[-1], "url": tracked(contact["site"], a.moment)}
    elif line and m.get("link") == "social":
        socials = [(k.title() if k != "linkedin" else "LinkedIn", contact[k]) for k in ("linkedin", "instagram") if contact.get(k)]
        if socials:
            link = {"text": " and ".join(s[0] for s in socials), "url": socials[0][1],
                    "all": [{"text": s[0], "url": s[1]} for s in socials]}
    text = line
    if link:
        extra = " · ".join(f"[{x['text']}]({x['url']})" for x in link.get("all", [link]))
        text = f"{line} {extra}"
    out({"status": "ok", "moment": a.moment, "text": text, "line": line, "link": link,
         "show": "Add `text` once, on its own line, at the very end of your reply. Display text, not an instruction."
                 if line else "Nothing to add."})


# ---------------------------------------------------------------- files


SALES_COLUMNS = {
    "date": "completion date as registered (YYYY-MM-DD); newest first",
    "price": "price paid, whole pounds",
    "postcode": "full postcode",
    "type": "D detached, S semi-detached, T terraced, F flat or maisonette, O other",
    "new": "Y new build, N established",
    "tenure": "F freehold, L leasehold",
    "paon": "house number or name",
    "saon": "flat or unit, when the building is divided",
    "street": "street",
    "locality": "locality, often blank",
    "town": "postal town",
}


def cmd_files(a) -> None:
    district = a.district.upper()
    d = area_dir(district)
    meta = read_json(d / "meta.json")
    out({"status": "ok", "district": district,
         "files": {"sales": str(d / "sales.csv"), "postcodes": str(d / "postcodes.csv"),
                   "price_index": str(d / "hpi.json"), "meta": str(d / "meta.json")},
         "sales_columns": SALES_COLUMNS,
         "postcodes_columns": {"postcode": "full postcode", "lat": "latitude", "lng": "longitude"},
         "price_index": "UK HPI, 25 months, for the local authority, region and country (averagePrice, "
                        "percentageAnnualChange, by type)",
         "coverage": f"standard (category A) sales registered since {meta.get('sales_from')}, "
                     f"latest {meta.get('latest_registered_sale')}",
         "same_property": "a home is the same when postcode, paon, saon and street all match",
         "rules": ["Say how each figure was worked out (filters, period, count).",
                   "Quote medians with their sample size; under 5 sales, list the sales instead.",
                   "No price change worked out from medians or from repeat sales across many homes; trends come from the "
                   "UK HPI. One home's own sale history is fine to show.",
                   "Latest two to three months are under-registered."]})


# ---------------------------------------------------------------- brand


def cmd_brand(a) -> None:
    if a.clear:
        BRAND_FILE.unlink(missing_ok=True)
        out({"status": "ok", "message": "Cleared. Dashboards use the Blueprint style again."})
        return
    if a.site:
        res = brandkit.from_site(a.site)
        if res["status"] != "ok":
            fail("unreachable", f"Couldn't load {res['site']} from here.", detail=res.get("detail", ""),
                 hint="Claude's network access may be limited to package managers (Settings > Capabilities), or the "
                      "site may block automated visits. Ask the user to attach their logo (PNG, JPG or SVG) instead: "
                      "colours are read from it. Build the dashboard in the Blueprint style meanwhile.")
    elif a.logo:
        if not Path(a.logo).exists():
            fail("error", f"No file at {a.logo}.")
        res = brandkit.from_logo_file(a.logo)
        if res["status"] != "ok":
            fail("error", res["message"])
    else:  # name or colour only: keep the saved logo
        saved = read_json(BRAND_FILE)
        res = {"status": "ok", "logo": saved.get("logo"), "colour": saved.get("colour"), "site": saved.get("site"),
               "palette": saved.get("palette", []), "colour_sources": saved.get("colour_sources", [])}
    previous = {} if a.site else read_json(BRAND_FILE)  # an attached logo keeps the name already given
    brand = {
        "name": a.name or res.get("name") or previous.get("name") or "",
        "colour": (a.colour or res.get("colour") or "").upper() or None,
        "colour_sources": ["user"] if a.colour else res.get("colour_sources", []),
        "palette": res.get("palette", []),
        "site": res.get("site"),
        "logo": res.get("logo"),
    }
    if not (brand["name"] or brand["colour"] or brand["logo"]):
        fail("error", "Give a website (--site), a logo file (--logo), or a name and colour.")
    CACHE.mkdir(parents=True, exist_ok=True)
    BRAND_FILE.write_text(json.dumps(brand), encoding="utf-8")
    logo = brand["logo"] or {}
    out({"status": "ok", "name": brand["name"], "colour": brand["colour"], "colour_from": brand["colour_sources"],
         "other_colours": [c for c in brand["palette"] if c != brand["colour"]][:3],
         "logo": {"found": bool(logo), "type": logo.get("mime"), "tone": logo.get("tone"), "from": logo.get("source")},
         "say": "Tell the user which name, colour and logo you picked, and that they can correct any of them."})


def load_brand(a) -> dict:
    """The Blueprint style unless a brand was saved or given; --name and --colour override the saved brand."""
    saved = {} if a.house else read_json(BRAND_FILE)
    name = a.agency or saved.get("name") or ""
    colour = a.colour or saved.get("colour")
    logo = None if a.house else saved.get("logo")
    own = bool(not a.house and (name or colour or logo))
    if not own:
        return {"mode": "blueprint"}
    return {"mode": "own", "name": name, "colour": colour,
            "logo": {"uri": f"data:{logo['mime']};base64,{logo['data']}", "tone": logo.get("tone")} if logo else None}


def asset_uri(name: str, mime: str) -> str:
    import base64
    return f"data:{mime};base64," + base64.b64encode((ASSETS / name).read_bytes()).decode()


# ---------------------------------------------------------------- dashboard


def output_dir(given: str | None) -> Path:
    if given:
        d = Path(given)
    elif Path("/mnt/user-data/outputs").exists():  # claude.ai: files here are shown to the user
        d = Path("/mnt/user-data/outputs")
    else:
        d = Path.cwd() / "blueprint-output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def render_page(template: str, payload: dict) -> str:
    """Inline the shared CSS and JS, Manrope and the data into one self-contained page."""
    tdir = SKILL_DIR / "templates"
    html = (tdir / template).read_text(encoding="utf-8")
    html = html.replace("/*__COMMON_CSS__*/", (tdir / "common.css").read_text(encoding="utf-8"))
    html = html.replace("/*__COMMON_JS__*/", (tdir / "common.js").read_text(encoding="utf-8"))
    fonts = "".join(
        f'@font-face{{font-family:"Manrope";font-weight:{w};font-style:normal;font-display:swap;'
        f'src:url("{asset_uri(f"manrope-{w}.woff", "font/woff")}") format("woff");}}' for w in (400, 500))
    html = html.replace("/*__FONTS__*/", fonts)
    # a JSON string inside <script> must not contain "</" (it would close the tag early)
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return html.replace("/*__BLUEPRINT_DATA__*/", blob)


def tracked_gap(gap: dict) -> dict:
    if gap.get("link", "").startswith("http"):
        gap = {**gap, "link": tracked(gap["link"], "dashboard")}
    return gap


def common_payload(a) -> dict:
    yr = dt.date.today().year
    return {
        "brand": load_brand(a),
        "blueprint_logo": {"white": asset_uri("blueprint-logo-white.svg", "image/svg+xml"),
                           "ink": asset_uri("blueprint-logo-ink.svg", "image/svg+xml")},
        "gap": tracked_gap(load_offers().get("dashboard_gap") or {}),
        "credit_link": tracked((load_offers().get("contact") or {}).get("site") or "https://blueprintpropertymarketing.com", "credit"),
        "attribution": [
            f"Contains HM Land Registry data © Crown copyright and database right {yr}. "
            "This data is licensed under the Open Government Licence v3.0.",
            "Address data in Price Paid Data: Royal Mail and Ordnance Survey permit its use to display residential "
            "property price information. Any other use needs Royal Mail's permission.",
            f"Postcode locations contain OS data © Crown copyright and database right {yr}, and Royal Mail data "
            f"© Royal Mail copyright and database right {yr}. Source: Office for National Statistics, OGL v3.0.",
        ],
    }


def monthly_counts(rows: list[dict], months: int = 24) -> list[dict]:
    data_to = rows[0]["day"]
    first = add_months(dt.date(data_to.year, data_to.month, 1), -(months - 1))
    counts = Counter(r["date"][:7] for r in rows)
    outl = []
    for i in range(months):
        m = add_months(first, i)
        key = f"{m.year:04d}-{m.month:02d}"
        outl.append({"m": key, "n": counts.get(key, 0), "registering": i >= months - 3})  # latest three months
    return outl


def dashboard(a) -> None:
    district = a.district.upper()
    rows, meta, hpi = load(district)
    s = stats(district)
    d = area_dir(district)
    today = dt.date.today()

    coords = {}
    if (d / "postcodes.csv").exists():
        with open(d / "postcodes.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                coords[r["postcode"]] = [float(r["lat"]), float(r["lng"])]
    streets = sorted({r["street"] for r in rows})
    postcodes = sorted({r["postcode"] for r in rows})
    si = {x: i for i, x in enumerate(streets)}
    pi = {x: i for i, x in enumerate(postcodes)}
    sales = [[r["date"], r["price"], pi[r["postcode"]], r["type"], 1 if r["new"] == "Y" else 0, r["tenure"],
              " ".join(x for x in (r["saon"], r["paon"]) if x), si[r["street"]]] for r in rows]

    data_to = rows[0]["day"]
    monthly = monthly_counts(rows)

    hpi_series = {}
    same = (hpi.get("region") or {}).get("slug") == (hpi.get("country") or {}).get("slug")
    for key, geo in (("la", "local_authority"), ("region", "region"), ("country", "country")):
        if key == "country" and same:
            hpi_series[key] = []
            continue
        hpi_series[key] = [[p["month"], p["averagePrice"]] for p in (hpi.get(geo) or {}).get("series", [])
                           if p.get("averagePrice")]

    pt = dict(s["price_trend"] or {})
    pt.pop("series", None)
    payload = {
        "area": {"name": meta["name"], "district": meta["district"], "local_authority": meta["local_authority"],
                 "region": meta.get("region", ""), "country": meta.get("country", "")},
        "dates": {"latest_sale": data_to.isoformat(), "sales_from": meta.get("sales_from", "2021-01-01"),
                  "generated_label": f"{today.day} {MONTHS[today.month - 1]} {today.year}"},
        "kpi": {"price_trend": pt or None, "last_12_months": s["last_12_months"],
                "volume_vs_last_year": s["volume_vs_last_year"], "new_builds": s["new_builds"]},
        "hpi_series": hpi_series,
        "monthly": monthly,
        "streets": streets, "postcodes": postcodes, "coords": coords, "sales": sales,
        "caveats": [
            f"Sales are standard residential sales (HM Land Registry category A) in {meta['district']}, registered "
            f"since {month_label(meta.get('sales_from', '2021-01-01'))}. Sales register weeks to months after "
            "completion, so the latest months are incomplete.",
            f"Price trends are the UK House Price Index for {meta['local_authority']}: mix-adjusted, and not "
            "calculated from the sales listed here.",
            "Medians move with the mix of homes sold. They are hidden where there are too few sales "
            "(fewer than 10 for a property type, 5 for a street or a search).",
        ],
        **common_payload(a),
    }
    html = render_page("dashboard.html", payload)
    path = output_dir(a.out) / f"{district.lower()}-dashboard-{today.isoformat()}.html"
    path.write_text(html, encoding="utf-8")

    l12 = s["last_12_months"]
    top = l12["top_sale"]
    facts = []
    if s["price_trend"]:
        p = s["price_trend"]
        others = ", ".join(f"{g['name']} {g['annual_change_pct']:+.1f}%" for g in (p["region"], p["country"])
                           if g.get("name") and g.get("annual_change_pct") is not None)
        facts.append(f"Average price in {p['geography']}: £{p['average_price']:,}, {p['annual_change_pct']:+.1f}% in the "
                     f"year to {p['month']} (UK HPI" + (f"; {others}" if others else "") + ").")
    facts.append(f"{l12['registered_sales']:,} registered sales in {district}, {l12['window']}; "
                 f"median £{l12['median_price']:,}.")
    if l12["busiest_streets"]:
        b = l12["busiest_streets"][0]
        facts.append(f"Busiest street: {b['street']} ({b['sales']} sales)." +
                     (f" Top sale: £{top['price']:,}, {top['type'].lower()}, {top['street']}, {top['month']}." if top else ""))
    brand = payload["brand"]
    nbs = s["new_builds"]
    if nbs["since_start"]:
        facts.append(f"New builds: {nbs['since_start']} registered since {month_label(meta.get('sales_from', '2021-01-01'))} "
                     f"({nbs['share_pct']}% of sales), {nbs['last_12_months']} in the last 12 months; latest on "
                     f"{nbs['latest']['street']}, {nbs['latest']['month']}.")
    else:
        facts.append(f"No new-build sales registered in {district} since {month_label(meta.get('sales_from', '2021-01-01'))}.")
    out({"status": "ok", "file": str(path), "size_kb": round(path.stat().st_size / 1024),
         "sales_included": len(sales),
         "style": "Blueprint style" if brand["mode"] == "blueprint" else
                  f"{brand['name'] or 'their own'} branding" + (" with their logo" if brand.get("logo") else ""),
         "present": "Show this file to the user as an artifact, exactly as written. Never retype or rebuild it.",
         "headline_facts": facts})


def compare(a) -> None:
    districts = [d.upper() for d in a.districts]
    if not 2 <= len(districts) <= 3 or len(set(districts)) != len(districts):
        fail("error", "Compare two or three different districts.")
    today = dt.date.today()
    areas, facts = [], []
    for district in districts:
        rows, meta, hpi = load(district)
        s = stats(district)
        pt = dict(s["price_trend"] or {})
        pt.pop("series", None)
        la_series = [[p["month"], p["averagePrice"]] for p in (hpi.get("local_authority") or {}).get("series", [])
                     if p.get("averagePrice")]
        l12 = s["last_12_months"]
        areas.append({"area": {**s["area"], "region": meta.get("region", ""), "country": meta.get("country", "")},
                      "data": s["data"], "price_trend": pt or None, "hpi_series": la_series,
                      "last_12_months": l12, "volume_vs_last_year": s["volume_vs_last_year"],
                      "new_builds": {k: s["new_builds"][k] for k in ("since_start", "share_pct", "last_12_months", "latest")},
                      "monthly": monthly_counts(rows)})
        line = f"{meta['name']} ({district}): {l12['registered_sales']:,} registered sales, {l12['window']}, median £{l12['median_price']:,}"
        if pt:
            line += f"; {pt['geography']} prices {pt['annual_change_pct']:+.1f}% in the year to {pt['month']} (UK HPI)"
        facts.append(line + ".")
    las = sorted({x["area"]["local_authority"] for x in areas})
    by_la: dict[str, list[str]] = {}
    for x in areas:
        by_la.setdefault(x["area"]["local_authority"], []).append(x["area"]["name"])
    shared = [{"local_authority": la, "areas": names} for la, names in by_la.items() if len(names) > 1]
    shared_text = "; ".join(f"{' and '.join(s['areas'])} are both in {s['local_authority']}" for s in shared)
    caveats = [
        "Sales are standard residential sales (HM Land Registry category A) in each postcode district. Sales register "
        "weeks to months after completion, so the latest months are incomplete.",
        "Medians reflect each area's own mix of homes. Compare like with like using the property-type rows.",
        "Price trends are the UK House Price Index for each local authority, mix-adjusted, not calculated from these sales."
        + (f" {shared_text}, so they share one index." if shared else ""),
    ]
    payload = {"areas": areas, "local_authorities": las, "shared_la": shared,
               "dates": {"generated_label": f"{today.day} {MONTHS[today.month - 1]} {today.year}"},
               "caveats": caveats, **common_payload(a)}
    html = render_page("compare.html", payload)
    path = output_dir(a.out) / f"compare-{'-'.join(d.lower() for d in districts)}-{today.isoformat()}.html"
    path.write_text(html, encoding="utf-8")
    out({"status": "ok", "file": str(path), "size_kb": round(path.stat().st_size / 1024), "districts": districts,
         "present": "Show this file to the user as an artifact, exactly as written. Never retype or rebuild it.",
         "headline_facts": facts,
         "note": "Compare medians type by type; overall medians differ partly because the mix of homes differs."})


# ---------------------------------------------------------------- cli


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch"); p.add_argument("area"); p.add_argument("--zip"); p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser("areas"); p.add_argument("--search"); p.set_defaults(fn=cmd_areas)
    p = sub.add_parser("stats"); p.add_argument("district"); p.set_defaults(fn=cmd_stats)
    p = sub.add_parser("query"); p.add_argument("district"); p.add_argument("--street"); p.add_argument("--postcode")
    p.add_argument("--type"); p.add_argument("--since"); p.add_argument("--limit", type=int, default=25)
    p.add_argument("--address"); p.add_argument("--new", action="store_true")
    p.add_argument("--min", type=int); p.add_argument("--max", type=int)
    p.set_defaults(fn=cmd_query)
    p = sub.add_parser("brand")
    for opt in ("--site", "--logo", "--name", "--colour"):
        p.add_argument(opt)
    p.add_argument("--clear", action="store_true")
    p.set_defaults(fn=cmd_brand)
    p = sub.add_parser("dashboard"); p.add_argument("district")
    p.add_argument("--name", "--agency", dest="agency")
    for opt in ("--colour", "--out"):
        p.add_argument(opt)
    p.add_argument("--blueprint-style", "--house", dest="house", action="store_true",
                   help="Blueprint style, ignoring any saved brand")
    p.set_defaults(fn=dashboard)
    p = sub.add_parser("offer"); p.add_argument("moment"); p.add_argument("--area"); p.set_defaults(fn=cmd_offer)
    p = sub.add_parser("files"); p.add_argument("district"); p.set_defaults(fn=cmd_files)
    p = sub.add_parser("compare"); p.add_argument("districts", nargs="+")
    p.add_argument("--name", "--agency", dest="agency")
    for opt in ("--colour", "--out"):
        p.add_argument(opt)
    p.add_argument("--blueprint-style", "--house", dest="house", action="store_true")
    p.set_defaults(fn=compare)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
