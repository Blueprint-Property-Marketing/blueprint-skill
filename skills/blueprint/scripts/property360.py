"""Blueprint 360: the address check, asking-price check, rents and yields, local facts (material information),
area-guide facts and brownfield sites. Registered as commands by blueprint.py:

    python blueprint.py address "<address with postcode>" [--asking N] [--type D|S|T|F] [--page] [--out DIR]
    python blueprint.py rents   <district> [--page]
    python blueprint.py local   "<postcode or address>" [--page]
    python blueprint.py guide   <district>
    python blueprint.py sites   <district>

Everything prints JSON for Claude. --page also writes one self-contained HTML page (show it as an artifact).
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

bp = None  # the blueprint module, set by register()
TYPE_CODES = {"detached": "D", "semi": "S", "semi-detached": "S", "terraced": "T", "terrace": "T", "flat": "F", "maisonette": "F",
              "apartment": "F", "d": "D", "s": "S", "t": "T", "f": "F"}
EPC_SEARCH = "https://find-energy-certificate.service.gov.uk/find-a-certificate/search-by-postcode?postcode="
COUNCIL_TAX = "https://www.gov.uk/council-tax-bands"
NRW_FLOOD = "https://flood-map-for-planning.naturalresources.wales/"
EA_FLOOD = "https://check-long-term-flood-risk.service.gov.uk/postcode"
GIAS = "https://www.get-information-schools.service.gov.uk/Establishments/Establishment/Details/"
OFCOM_CHECKER = "https://www.ofcom.org.uk/phones-and-broadband/coverage-and-speeds/ofcom-checker"


# ---------------------------------------------------------------- helpers
def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def toks(s: str) -> list[str]:
    return norm(s).split()


def med(xs):
    return int(statistics.median(xs)) if xs else None


def quartiles(xs):
    if len(xs) < 4:
        return None
    q = statistics.quantiles(sorted(xs), n=4)
    return [int(q[0]), int(q[2])]


def haversine(a, b) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    h = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12_742_000 * math.asin(math.sqrt(h))


def nice_distance(m: float) -> str:
    if m < 950:
        return f"{int(round(m / 10.0) * 10)} m"
    return f"{m / 1609.34:.1f} miles"


def addr_line(r: dict) -> str:
    return " ".join(x for x in (r.get("saon"), r.get("paon"), r.get("street")) if x)


def month_of(date: str) -> str:
    return date[:7]


def files(district: str) -> Path:
    return bp.area_dir(district)


def read_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_local(d: Path) -> dict:
    return bp.read_json(d / "local.json")


def load_epc(d: Path) -> dict:
    """{"postcode|flat|number": [floor area m2, rating, year]} when build_epc.py has run for the district, else {}"""
    return (bp.read_json(d / "epc.json") or {}).get("homes") or {}


def coords_for(d: Path, local: dict) -> dict:
    c = {pc: v["ll"] for pc, v in (local.get("postcodes") or {}).items() if v.get("ll")}
    for r in read_csv(d / "postcodes.csv"):
        c.setdefault(r["postcode"], [float(r["lat"]), float(r["lng"])])
    return c


# ---------------------------------------------------------------- the price index
class Index:
    def __init__(self, d: Path):
        self.j = bp.read_json(d / "index.json")

    def ok(self) -> bool:
        return bool(self.j.get("la"))

    def latest(self) -> str | None:
        return (self.j.get("la") or {}).get("to")

    def _at(self, geo: str, kind: str, series: str, month: str):
        g = self.j.get(geo) or {}
        if not g:
            return None
        y0, m0 = map(int, g["from"].split("-"))
        y, m = map(int, month.split("-"))
        i = (y - y0) * 12 + (m - m0)
        arr = (g.get(kind) or {}).get(series) or []
        if 0 <= i < len(arr):
            return arr[i]
        return None

    def factor(self, type_code: str, month: str, geo: str = "la"):
        """today's index / the index in `month`, for the property type (falls back to all types)"""
        to = self.latest()
        if not to or month >= to:
            return 1.0, "all", to
        series = type_code if type_code in ("D", "S", "T", "F") else "all"
        a, b = self._at(geo, "index", series, month), self._at(geo, "index", series, to)
        if not a or not b:
            series = "all"
            a, b = self._at(geo, "index", "all", month), self._at(geo, "index", "all", to)
        if not a or not b:
            return None, None, to
        return b / a, series, to

    def adjust(self, price: int, type_code: str, month: str):
        f, series, to = self.factor(type_code, month)
        if f is None:
            return None
        return {"value": int(round(price * f / 1000.0) * 1000) if price * f >= 100_000 else int(round(price * f / 500.0) * 500),
                "factor": round(f, 3), "index_series": series, "from_month": month, "to_month": to}

    def type_prices(self, since: str = "2016-01"):
        g = self.j.get("la") or {}
        if not g:
            return None
        y0, m0 = map(int, g["from"].split("-"))
        months = []
        n = len((g.get("price") or {}).get("all") or [])
        for i in range(n):
            y, m = divmod(m0 - 1 + i, 12)
            months.append(f"{y0 + y:04d}-{m + 1:02d}")
        keep = [i for i, mm in enumerate(months) if mm >= since]
        return {"months": [months[i] for i in keep],
                **{k: [(g["price"].get(k) or [None] * n)[i] for i in keep] for k in ("D", "S", "T", "F")}}


# ---------------------------------------------------------------- address matching
def property_key(r: dict) -> tuple:
    """a home = its postcode, flat and house number or name (older records sometimes lack the street)"""
    return (r["postcode"], norm(r.get("saon", "")), norm(r.get("paon", "")))


def match_property(text: str, rows: list[dict]):
    """rows: candidate sales (any period) in the postcode or on the street. Returns (key, candidates)."""
    words = set(toks(text))
    nums = {w for w in words if re.search(r"\d", w)}
    num_count = Counter(w for w in toks(text) if re.search(r"\d", w))
    keys = {}
    for r in rows:
        keys.setdefault(property_key(r), r)
    scored, partial = [], []
    for k, r in keys.items():
        pc, saon, paon = k
        pt, st = paon.split(), saon.split()
        # numbers must all be there; a building name ("Cloverley, 108") counts as a bonus when the number is given
        p_num = [w for w in pt if re.search(r"\d", w)]
        if not pt or not set(p_num or pt) <= words:
            continue
        s_num = [w for w in st if re.search(r"\d", w)]
        need = Counter(p_num + s_num)
        if (st and not set(s_num or [w for w in st if len(w) > 2 and w not in ("flat", "apartment", "unit")]) <= words) or \
                any(num_count[w] < n for w, n in need.items()):
            partial.append(k)  # the building matches but not the flat: offer the flats
            continue
        explained = set(p_num + s_num)
        score = len(set(pt) & words) + len(set(st) & words) - 2 * len(nums - explained - set(toks(pc)))
        scored.append((score, k))
    if not scored:
        return None, sorted(partial)[:15]
    scored.sort(key=lambda x: -x[0])
    best = scored[0][0]
    top = [k for s, k in scored if s == best]
    if len(top) == 1:
        return top[0], []
    return None, top[:15]


# ---------------------------------------------------------------- local facts (material information starter)
def local_facts(d: Path, postcode: str, local: dict, meta: dict) -> dict:
    rec = (local.get("postcodes") or {}).get(postcode)
    england = meta.get("country") == "England"
    out = {"postcode": postcode, "found": rec is not None, "note": "Facts are for the postcode's centre point. A postcode can "
           "straddle a boundary, so confirm anything that matters for a sale with the source or the council."}
    if rec is None:
        return out
    # flood
    if england:
        f = rec.get("f")
        if not f:
            out["flood"] = {"status": "not_listed", "text": "Not in the Environment Agency's list of postcodes in areas at risk of "
                            "flooding from rivers or the sea (its assessment takes account of flood defences).", "check": EA_FLOOD}
        else:
            res, h, m, l, vl = f
            bands = ((h, "high", "more than a 3.3% chance of flooding each year"), (m, "medium", "a 1% to 3.3% chance each year"),
                     (l, "low", "a 0.1% to 1% chance each year"), (vl, "very low", "less than a 0.1% chance each year"))
            parts = [f"{n} at {lab} risk" for n, lab, _ in bands if n]
            top = next(((lab, means) for n, lab, means in bands if n), None)
            text = (f"In an area at risk of flooding from rivers or the sea (Environment Agency, taking account of flood defences): "
                    f"of {res} homes in the postcode, " + (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else
                    (parts[0] if parts else "none are themselves at risk (other buildings are)")) + ".")
            if top:
                text += f" {top[0].capitalize()} risk means {top[1]}."
            out["flood"] = {"status": "listed", "homes_in_postcode": res, "high": h, "medium": m, "low": l, "very_low": vl,
                            "bands": {lab.replace(" ", "_"): means for _, lab, means in bands}, "text": text, "check": EA_FLOOD,
                            "say": "State this plainly with its source: flood risk is material information a buyer must be told. "
                                   "For one home's own result, give the GOV.UK check."}
        out["flood"]["not_covered"] = "Surface water, groundwater and reservoir risk aren't included: see the GOV.UK long-term flood risk check."
    else:
        out["flood"] = {"status": "wales", "text": "Flood risk in Wales: check Natural Resources Wales' Flood Map for Planning.", "check": NRW_FLOOD}
    # broadband and mobile
    if rec.get("bb"):
        sf, uf, gb = rec["bb"]
        out["broadband"] = {"superfast_pct": sf, "ultrafast_pct": uf, "gigabit_pct": gb,
                            "text": f"Premises in the postcode able to get superfast broadband (30 Mbit/s+): {sf}%; ultrafast (100 Mbit/s+): {uf}%; gigabit: {gb}%.",
                            "source": "Ofcom Connected Nations 2025", "check": OFCOM_CHECKER}
    mob = (local.get("council") or {}).get("mobile") or {}
    if mob:
        out["mobile"] = {**mob, "text": f"Across {meta.get('local_authority')}: {mob.get('4g_indoor_all')}% of premises have indoor 4G from all four networks"
                         + (f"; {mob['5g_outdoor_any']}% have outdoor 5G from at least one." if mob.get("5g_outdoor_any") is not None else "."),
                         "level": "council area, not the postcode", "check": OFCOM_CHECKER}
    # planning and heritage (England)
    plan = []
    if england:
        if rec.get("ca"):
            plan.append({"flag": "conservation_area", "text": f"In the {rec['ca']} conservation area (at the postcode's centre)."})
        if rec.get("a4"):
            plan.append({"flag": "article_4", "text": f"In an Article 4 direction area: {rec['a4']}. Some permitted development rights are removed."})
        if rec.get("gb"):
            plan.append({"flag": "green_belt", "text": "In the green belt."})
        if rec.get("np"):
            plan.append({"flag": "national_park", "text": f"In the {rec['np']} National Park."})
        if rec.get("nl"):
            plan.append({"flag": "national_landscape", "text": f"In the {rec['nl']} National Landscape (Area of Outstanding Natural Beauty)."})
        if rec.get("tpo"):
            plan.append({"flag": "tree_preservation", "text": "Inside a tree preservation area: some trees may be protected."})
        if rec.get("lb"):
            n, name, grade, dist = rec["lb"]
            plan.append({"flag": "listed_buildings_nearby", "text": f"{n} listed building{'s' if n > 1 else ''} within 100 m of the postcode's centre"
                         f"; nearest: {name.title() if name.isupper() else name} (Grade {grade}), about {dist} m."})
        if rec.get("sm"):
            n, name, dist = rec["sm"]
            plan.append({"flag": "scheduled_monument_nearby", "text": f"A scheduled monument within 250 m: {name} (about {dist} m)."})
        out["planning"] = {"flags": plan, "none": not plan,
                           "text": "No conservation area, Article 4, green belt, national park, National Landscape, tree preservation area or "
                                   "listed building within 100 m found at the postcode's centre." if not plan else None,
                           "coverage": "Planning Data covers what councils have published; check the council's own maps for anything decisive."}
    else:
        out["planning"] = {"flags": [], "text": "Planning constraints in Wales aren't in this data: check the council and Cadw.", "coverage": "England only"}
    out["coal"] = ({"in_high_risk_area": True, "text": "In a coal mining Development High Risk Area: a coal mining search (CON29M) is advisable."}
                   if rec.get("coal") else
                   {"in_high_risk_area": False, "text": "Not in a coal mining Development High Risk Area. The wider coalfield isn't covered here; a "
                                                         "conveyancer's coal search confirms."})
    # schools and stations
    ll = rec.get("ll")
    if ll:
        sch = []
        for s in local.get("schools") or []:
            sch.append({**{k: s[k] for k in ("name", "phase", "type", "ages", "gender", "faith", "pupils", "postcode")},
                        "distance_m": int(haversine(ll, (s["lat"], s["lng"]))), "details": GIAS + s["urn"]})
        sch.sort(key=lambda s: s["distance_m"])
        primary = [s for s in sch if s["phase"] in ("Primary", "Middle deemed primary", "All-through")][:3]
        secondary = [s for s in sch if s["phase"] in ("Secondary", "Middle deemed secondary", "All-through", "16 plus")][:3]
        for s in primary + secondary:
            s["distance"] = nice_distance(s["distance_m"])
        out["schools"] = {"primary": primary, "secondary": secondary,
                          "note": "Straight-line distance from the postcode's centre. Catchments and admissions depend on each school and the council; "
                                  "Ofsted reports are linked from each school's GIAS page."
                                  + ("" if england else " School data covers England only.")}
        st = sorted(({"name": s["name"], "kind": s["kind"], "distance_m": int(haversine(ll, (s["lat"], s["lng"])))} for s in local.get("stations") or []),
                    key=lambda s: s["distance_m"])[:3]
        for s in st:
            s["distance"] = nice_distance(s["distance_m"])
        out["stations"] = st
        out["lat_lng"] = ll
    out["links"] = {"epc": EPC_SEARCH + postcode.replace(" ", ""), "council_tax": COUNCIL_TAX}
    return out


def material_checklist(facts: dict, prop: dict | None) -> list[dict]:
    """National Trading Standards material information, Parts A to C: what the data fills in, and what the seller or agent supplies."""
    t = (prop or {}).get("type")
    ten = (prop or {}).get("tenure")
    fl = facts.get("flood") or {}
    plan = facts.get("planning") or {}
    rows = [
        ("A", "Council tax band", "link", "Check the band on GOV.UK.", COUNCIL_TAX),
        ("A", "Asking price", "supply", "", None),
        ("A", "Tenure", "data" if ten else "supply", f"{ten} at the last registered sale (HM Land Registry); confirm with the title." if ten else "", None),
        ("A", "Lease length, ground rent, service charge", "supply" if ten != "Freehold" else "n/a",
         "Leasehold: give the years remaining, ground rent and service charge." if ten != "Freehold" else "Freehold at the last sale.", None),
        ("B", "Property type", "data" if t else "supply", f"{t} (HM Land Registry)." if t else "", None),
        ("B", "Rooms, floor area and floorplan", "data" if (prop or {}).get("floor_area_m2") else "supply",
         f"Floor area {prop['floor_area_m2']} m² on the {prop.get('epc_year')} EPC; rooms and floorplan to supply." if (prop or {}).get("floor_area_m2") else "", None),
        ("B", "Utilities (electricity, water, sewerage, heating)", "supply", "", None),
        ("B", "Broadband", "data" if facts.get("broadband") else "link", (facts.get("broadband") or {}).get("text", "Check the Ofcom checker."), OFCOM_CHECKER),
        ("B", "Mobile signal", "data" if facts.get("mobile") else "link", (facts.get("mobile") or {}).get("text", "Check the Ofcom checker."), OFCOM_CHECKER),
        ("B", "Parking", "supply", "", None),
        ("C", "Building safety (cladding, structural issues)", "supply", "", None),
        ("C", "Restrictions and rights (covenants, listed status, conservation area, TPOs, rights of way)",
         "data" if (plan.get("flags") or plan.get("none")) else "supply", " ".join(f["text"] for f in plan.get("flags", [])) or (plan.get("text") or ""), None),
        ("C", "Flood risk", "data" if fl.get("status") in ("listed", "not_listed") else "link", fl.get("text", ""), fl.get("check")),
        ("C", "Coastal erosion", "link", "Check the National Coastal Erosion Risk Map if near the coast.", "https://www.gov.uk/check-coastal-erosion-management-in-your-area"),
        ("C", "Planning permission and proposals", "supply", "Check the council's planning register.", None),
        ("C", "Accessibility and adaptations", "supply", "", None),
        ("C", "Coal mining", "data", (facts.get("coal") or {}).get("text", ""), None),
        ("A", "Energy Performance Certificate", "data" if (prop or {}).get("epc_rating") else "link",
         f"Rated {prop['epc_rating']} ({prop.get('epc_year')}); check it's current on GOV.UK." if (prop or {}).get("epc_rating") else "Find the certificate on GOV.UK.",
         (facts.get("links") or {}).get("epc")),
    ]
    order = {"A": 0, "B": 1, "C": 2}
    rows.sort(key=lambda r: order[r[0]])
    return [{"part": p, "item": i, "status": s, "value": v, "link": l} for p, i, s, v, l in rows]


# ---------------------------------------------------------------- rents and yields
def rents_for(d: Path, rows: list[dict] | None = None) -> dict | None:
    r = bp.read_json(d / "rents.json")
    la = r.get("la")
    if not la:
        return None
    yields = []
    if rows:
        data_to = rows[0]["day"]
        start = bp.add_months(dt.date(data_to.year, data_to.month, 1), -11)
        by = defaultdict(list)
        for x in rows:
            if x["day"] >= start:
                by[x["type"]].append(x["price"])
        for code in ("D", "S", "T", "F"):
            rent = (la["types"].get(code) or {}).get("rent")
            prices = by.get(code, [])
            if rent and len(prices) >= 10:
                m = med(prices)
                yields.append({"type": bp.TYPE_NAMES[code], "average_rent": rent, "median_price": m, "sales": len(prices),
                               "gross_yield_pct": round(100 * rent * 12 / m, 1)})
    return {"council": la["name"], "month": bp.month_label(la["month"]), "average_rent": la["all"]["rent"], "annual_change_pct": la["all"]["change"],
            "by_bedrooms": [{"bedrooms": k, **v} for k, v in la["beds"].items()],
            "by_type": [{"type": bp.TYPE_NAMES[k], **v} for k, v in la["types"].items()],
            "region": {"name": (r.get("region") or {}).get("name"), **((r.get("region") or {}).get("all") or {})} if r.get("region") else None,
            "country": {"name": (r.get("country") or {}).get("name"), **((r.get("country") or {}).get("all") or {})} if r.get("country") else None,
            "series": la["series"], "gross_yields": yields,
            "notes": ["Average private rents are the ONS Price Index of Private Rents for the whole council area, by bedrooms and by property "
                      "type, for all tenancies (new and existing), not advertised rents and not this property.",
                      "Gross yield = the council's average rent for the type x 12 / the median registered sale price of that type in this "
                      "district over the last 12 months. Indicative only: before costs, voids, tax and mortgage."]}


# ---------------------------------------------------------------- comparables
def comparables(rows, idx: Index, coords: dict, type_code: str, postcode: str, street: str, exclude_key=None, months: int = 24, epc=None):
    data_to = rows[0]["day"]
    sector = bp.postcode_sector(postcode)
    centre = coords.get(postcode)
    def pool_for(scope, mths):
        start = bp.add_months(dt.date(data_to.year, data_to.month, 1), -(mths - 1))
        out = []
        for r in rows:
            if r["type"] != type_code or r["day"] < start or (exclude_key and property_key(r) == exclude_key):
                continue
            if scope == "sector" and bp.postcode_sector(r["postcode"]) != sector:
                continue
            out.append(r)
        return out, start
    scope, mths = "sector", months
    pool, start = pool_for(scope, mths)
    if len(pool) < 6:
        scope, mths = "sector", 36
        pool, start = pool_for(scope, mths)
    if len(pool) < 6:
        scope, mths = "district", months
        pool, start = pool_for(scope, mths)
    items = []
    for r in pool:
        adj = idx.adjust(r["price"], r["type"], month_of(r["date"])) if idx.ok() else None
        c = coords.get(r["postcode"])
        fa = (epc or {}).get("|".join(property_key(r)))
        items.append({"date": r["date"], "price": r["price"], "on_index_today": adj["value"] if adj else None,
                      "floor_area_m2": fa[0] if fa else None,
                      "per_m2_on_index_today": int(round(adj["value"] / fa[0])) if (fa and adj) else None,
                      "number_or_name": " ".join(x for x in (r["saon"], r["paon"]) if x), "street": r["street"], "postcode": r["postcode"],
                      "tenure": "Freehold" if r["tenure"] == "F" else "Leasehold", "new_build": r["new"] == "Y",
                      "same_street": norm(r["street"]) == norm(street) if street else False,
                      "distance_m": int(haversine(centre, c)) if centre and c else None})
    items.sort(key=lambda x: (not x["same_street"], x["distance_m"] if x["distance_m"] is not None else 10**7, x["date"][::-1]))
    # the figures use the nearest 20 (same street first), as a valuer would, and say how many there were in all
    core = items[:20]
    adj_prices = [x["on_index_today"] for x in core if x["on_index_today"]]
    raw = [x["price"] for x in core]
    label = {"sector": f"postcode sector {sector}", "district": f"the {postcode.split(' ')[0]} district"}[scope]
    return {"type": bp.TYPE_NAMES.get(type_code, type_code), "scope": label, "window": f"{bp.month_label(start, True)} to {bp.month_label(data_to, True)}",
            "sales": len(core), "sales_in_scope": len(items),
            "basis": (f"the {len(core)} nearest of {len(items)}" if len(items) > len(core) else f"all {len(items)}"),
            "median_price": med(raw) if len(raw) >= 5 else None,
            "median_on_index_today": med(adj_prices) if len(adj_prices) >= 5 else None,
            "middle_half_on_index_today": quartiles(adj_prices) if len(adj_prices) >= 8 else None,
            "range_on_index_today": [min(adj_prices), max(adj_prices)] if adj_prices else None,
            "median_per_m2_on_index_today": med([x["per_m2_on_index_today"] for x in core if x.get("per_m2_on_index_today")])
            if sum(1 for x in core if x.get("per_m2_on_index_today")) >= 5 else None,
            "with_floor_area": sum(1 for x in core if x.get("floor_area_m2")),
            "nearest": items[:12], "all_on_index_today": sorted(adj_prices)}


def asking_check(asking: int, comps: dict, own: dict | None) -> dict:
    xs = comps.get("all_on_index_today") or []
    out = {"asking": asking}
    if xs:
        below = sum(1 for x in xs if x < asking)
        out.update({"comparables": len(xs), "below_asking": below, "above_asking": sum(1 for x in xs if x > asking),
                    "position_pct": round(100 * below / len(xs)),
                    "vs_median_pct": round(100 * (asking - comps["median_on_index_today"]) / comps["median_on_index_today"], 1) if comps.get("median_on_index_today") else None,
                    "vs_highest_pct": round(100 * (asking - max(xs)) / max(xs), 1)})
        if asking > max(xs):
            out["reading"] = "above_all"
        elif comps.get("middle_half_on_index_today") and asking > comps["middle_half_on_index_today"][1]:
            out["reading"] = "upper_quarter"
        elif comps.get("middle_half_on_index_today") and asking < comps["middle_half_on_index_today"][0]:
            out["reading"] = "lower_quarter"
        else:
            out["reading"] = "middle"
    if own:
        out["vs_own_index_pct"] = round(100 * (asking - own["value"]) / own["value"], 1)
    out["say"] = ("State where the asking price sits among the comparable sales brought to today's index, with the count, scope and period; "
                  "never call it overpriced or a valuation. Size, condition, plot and layout aren't in this data.")
    return out


# ---------------------------------------------------------------- commands
def cmd_address(a) -> None:
    text = a.address
    m = bp.FULL_POSTCODE.search(text)
    district = (m.group(1).upper() if m else (a.district or "").upper())
    if not district:
        bp.fail("need_postcode", "Give the address with its postcode (or --district), then try again.")
    postcode = f"{m.group(1).upper()} {m.group(2).upper()}" if m else None
    d = files(district)
    rows, meta, _ = bp.load(district)
    hist = read_csv(d / "history.csv")
    local = load_local(d)
    coords = coords_for(d, local)
    idx = Index(d)
    epc = load_epc(d)
    rest = bp.FULL_POSTCODE.sub(" ", text)
    if postcode:
        cand = [r for r in rows if r["postcode"] == postcode] + [r for r in hist if r["postcode"] == postcode]
    else:
        street_words = toks(rest)
        streets = {r["street"] for r in rows} | {r["street"] for r in hist}
        hit = [s for s in streets if s and set(toks(s)) <= set(street_words)]
        hit.sort(key=len, reverse=True)
        if not hit:
            bp.fail("need_postcode", "Couldn't find that street in the district. Ask for the full postcode.")
        cand = [r for r in rows if r["street"] == hit[0]] + [r for r in hist if r["street"] == hit[0]]
    key, many = match_property(rest, cand)
    if many:
        street = {property_key(r): r.get("street", "") for r in cand}
        opts = sorted({f"{(k[1] + ' ' if k[1] else '')}{k[2]} {street.get(k, '')}".title().strip() + f", {k[0]}" for k in many})
        bp.out({"status": "ambiguous_property", "options": opts, "message": "Several homes match. Ask which one (flat number or house name)."})
        return
    prop = None
    history = []
    if key:
        mine = [r for r in rows if property_key(r) == key]
        old = [r for r in hist if property_key(r) == key]
        any_r = dict(next((r for r in mine + old if r.get("street")), (mine or old)[0]))
        if not any_r.get("street"):  # older records can lack the street: use the postcode's usual street
            common = Counter(r["street"] for r in cand if r.get("street") and r["postcode"] == any_r["postcode"]).most_common(1)
            any_r["street"] = common[0][0] if common else ""
        postcode = any_r["postcode"]
        for r in old:
            history.append({"date": r["date"], "price": int(r["price"]), "type": bp.TYPE_NAMES.get(r["type"], r["type"]),
                            "tenure": "Freehold" if r["tenure"] == "F" else "Leasehold", "new_build": r["new"] == "Y",
                            "note": f"latest of {r['sales']} registered sales from 1995 to 2020" if int(r["sales"]) > 1 else "registered sale from 1995 to 2020"})
        for r in sorted(mine, key=lambda r: r["date"]):
            history.append({"date": r["date"], "price": r["price"], "type": bp.TYPE_NAMES.get(r["type"], r["type"]),
                            "tenure": "Freehold" if r["tenure"] == "F" else "Leasehold", "new_build": r["new"] == "Y", "note": ""})
        history.sort(key=lambda h: h["date"])
        last = history[-1]
        type_code = (mine[-1]["type"] if mine else old[-1]["type"])
        prop = {"address": addr_line(any_r), "postcode": postcode, "type": bp.TYPE_NAMES.get(type_code), "type_code": type_code,
                "tenure": last["tenure"], "street": any_r["street"], "last_sale": last}
        fa = epc.get("|".join(key))
        if fa:
            prop["floor_area_m2"], prop["epc_rating"], prop["epc_year"] = fa
        adj = idx.adjust(last["price"], type_code, month_of(last["date"])) if idx.ok() else None
        if adj and fa:
            adj["per_m2"] = int(round(adj["value"] / fa[0]))
        if adj:
            prop["on_index_today"] = {**adj, "geography": meta.get("local_authority"),
                                      "text": f"£{last['price']:,} in {bp.month_label(month_of(last['date']))}, brought forward on the UK House Price Index "
                                              f"for {bp.TYPE_NAMES.get(adj['index_series'], 'all homes').lower() + ' homes' if adj['index_series'] != 'all' else 'all homes'} "
                                              f"in {meta.get('local_authority')} to {bp.month_label(adj['to_month'])}: £{adj['value']:,}."}
    else:
        if not postcode:
            bp.fail("not_found", "No registered sale found for that address since 1995, and no postcode to work from. Ask for the postcode.")
    type_code = (prop or {}).get("type_code") or TYPE_CODES.get((a.type or "").lower())
    comps = None
    if type_code in ("D", "S", "T", "F"):
        comps = comparables(rows, idx, coords, type_code, postcode, (prop or {}).get("street", ""), exclude_key=key, epc=epc)
    facts = local_facts(d, postcode, local, meta)
    asking = asking_check(a.asking, comps, (prop or {}).get("on_index_today")) if a.asking and comps else None
    if asking and (prop or {}).get("floor_area_m2"):
        asking["per_m2"] = int(round(a.asking / prop["floor_area_m2"]))
        if comps and comps.get("median_per_m2_on_index_today"):
            asking["per_m2_vs_comparables_pct"] = round(100 * (asking["per_m2"] - comps["median_per_m2_on_index_today"]) / comps["median_per_m2_on_index_today"], 1)
    rents = rents_for(d, rows)
    result = {"status": "ok" if prop else "no_sale_found", "district": district, "area": meta.get("name"), "council": meta.get("local_authority"),
              "property": prop, "history": history, "comparables": comps and {k: v for k, v in comps.items() if k != "all_on_index_today"},
              "asking_check": asking, "rents": rents and {k: rents[k] for k in ("council", "month", "by_type", "by_bedrooms", "gross_yields")},
              "local": facts, "material_information": material_checklist(facts, prop),
              "rules": ["'On today's index' is the last price moved with the UK House Price Index for the council area and property type. It "
                        "is not a valuation and knows nothing of condition, extensions or the market for this home: say so every time.",
                        "House numbers are for the user's own work (valuations, letters to this owner). Leave them out of anything published.",
                        "Sales before 2021 show the latest sale from 1995 to 2020 only (and how many there were).",
                        "Floor areas (when present) come from the home's latest EPC: quote £ per square metre with its source and year."]}
    if not prop:
        result["message"] = ("No registered sale found for this exact address since 1995 (it may not have sold, may be newly built, or the "
                             "number/name may differ in Land Registry's records). Comparables need --type when the home isn't found.")
    if a.page:
        payload = {"mode": "address", "result": result, "type_prices": idx.type_prices() if idx.ok() else None, **page_common(a, meta)}
        path = write_page(a, payload, f"{(postcode or district).replace(' ', '').lower()}-address-report")
        result["file"] = str(path)
        result["present"] = "Show this file to the user as an artifact, exactly as written. Never retype or rebuild it."
    bp.out(result)


def cmd_local(a) -> None:
    m = bp.FULL_POSTCODE.search(a.where)
    if not m:
        bp.fail("need_postcode", "Local facts need a full postcode.")
    district, postcode = m.group(1).upper(), f"{m.group(1).upper()} {m.group(2).upper()}"
    d = files(district)
    meta = bp.read_json(d / "meta.json")
    local = load_local(d)
    if not local:
        bp.fail("no_local", "This area's local facts aren't built yet.")
    facts = local_facts(d, postcode, local, meta)
    if not facts["found"]:
        bp.fail("unknown_postcode", f"{postcode} isn't a live postcode in the ONS Postcode Directory (Aug 2026). Check it.")
    result = {"status": "ok", "district": district, "council": meta.get("local_authority"), "local": facts,
              "material_information": material_checklist(facts, None)}
    if a.page:
        payload = {"mode": "material", "result": result, **page_common(a, meta)}
        result["file"] = str(write_page(a, payload, f"{postcode.replace(' ', '').lower()}-material-information"))
        result["present"] = "Show this file to the user as an artifact, exactly as written. Never retype or rebuild it."
    bp.out(result)


def cmd_rents(a) -> None:
    district = a.district.upper()
    d = files(district)
    rows, meta, _ = bp.load(district)
    r = rents_for(d, rows)
    if not r:
        bp.fail("no_rents", "No ONS rent figures for this council area.")
    result = {"status": "ok", "district": district, "area": meta.get("name"), "rents": r,
              "rules": ["Quote the council area and month with every rent figure, and say it's the ONS average for all tenancies.",
                        "For a rent review or tribunal, these are market background, not comparables for the property: add real "
                        "advertised or agreed rents for similar homes, and point to GOV.UK's guidance. No legal advice."]}
    if a.page:
        payload = {"mode": "rents", "result": result, **page_common(a, meta)}
        result["file"] = str(write_page(a, payload, f"{district.lower()}-rents"))
        result["present"] = "Show this file to the user as an artifact, exactly as written. Never retype or rebuild it."
    bp.out(result)


def cmd_guide(a) -> None:
    district = a.district.upper()
    d = files(district)
    s = bp.stats(district)
    rows, meta, _ = bp.load(district)
    local = load_local(d)
    pcs = local.get("postcodes") or {}
    ca = Counter(v["ca"] for v in pcs.values() if v.get("ca"))
    england = meta.get("country") == "England"
    flood_n = sum(1 for v in pcs.values() if v.get("f")) if england else None
    gig = sum(1 for v in pcs.values() if (v.get("bb") or [0, 0, 0])[2] >= 90)
    centre = None
    if pcs:
        lats = [v["ll"][0] for v in pcs.values()]; lngs = [v["ll"][1] for v in pcs.values()]
        centre = (statistics.median(lats), statistics.median(lngs))
    sch = local.get("schools") or []
    st = local.get("stations") or []
    if centre:
        st = sorted(st, key=lambda x: haversine(centre, (x["lat"], x["lng"])))
    phases = Counter("primary" if x["phase"] in ("Primary", "Middle deemed primary") else "secondary" if x["phase"] in ("Secondary", "Middle deemed secondary", "All-through") else "other" for x in sch)
    bf = local.get("brownfield") or []
    result = {"status": "ok", "district": district, "area": meta.get("name"), "council": meta.get("local_authority"),
              "market": {k: s[k] for k in ("price_trend", "last_12_months", "new_builds")},
              "rents": rents_for(d, rows),
              "places": {"conservation_areas": [n for n, _ in ca.most_common(8)],
                         "national_park_or_landscape": sorted({v.get("np") or v.get("nl") for v in pcs.values() if v.get("np") or v.get("nl")}),
                         "green_belt_postcodes_pct": round(100 * sum(1 for v in pcs.values() if v.get("gb")) / len(pcs)) if pcs else None},
              "schools": {"nearby_count": dict(phases), "note": "Schools within about a mile of the district (England only). Name them only "
                          "with care: catchments change and a guide shouldn't promise places."},
              "stations": [{"name": x["name"], "kind": x["kind"]} for x in st[:6]],
              "broadband": {"postcodes_with_gigabit_90pct_plus": round(100 * gig / len(pcs)) if pcs else None},
              "flood": {"postcodes_on_ea_at_risk_list_pct": round(100 * flood_n / len(pcs)) if (pcs and flood_n is not None) else None,
                        "say": "Mention flood risk only as a fact with its source; never as a selling point or a warning about named streets."},
              "development": {"brownfield_sites": len(bf), "brownfield_dwellings_min": sum(x.get("min_dwellings") or 0 for x in bf)},
              "write": "Use these for an area guide (website page, newsletter, LinkedIn): local guide first, agent second. Follow the "
                       "area-guide reference: every number with its source and month, no house numbers, no crime claims, no promises about schools."}
    bp.out(result)


def cmd_sites(a) -> None:
    district = a.district.upper()
    d = files(district)
    meta = bp.read_json(d / "meta.json")
    bf = (load_local(d).get("brownfield") or [])
    bf = sorted(bf, key=lambda x: -(x.get("hectares") or 0))
    bp.out({"status": "ok", "district": district, "council": meta.get("local_authority"), "sites": bf[:40], "count": len(bf),
            "source": "Brownfield land registers, as published by councils on the Planning Data platform (England only).",
            "rules": ["A register entry is the council's view of suitability; it isn't a planning permission unless the status says so.",
                      "Dwelling numbers are the council's estimates, often blank."]})


# ---------------------------------------------------------------- pages
def page_common(a, meta: dict) -> dict:
    today = dt.date.today()
    c = bp.common_payload(a)
    c["attribution"] = c["attribution"] + [s["licence"] for s in meta.get("sources", []) if s.get("name") not in
                                           ("HM Land Registry Price Paid Data", "ONS Postcode Directory")]
    c["dates"] = {"generated_label": f"{today.day} {bp.MONTHS[today.month - 1]} {today.year}"}
    c["area"] = {"name": meta.get("name"), "district": meta.get("district"), "local_authority": meta.get("local_authority")}
    c["caveats"] = ["Not a valuation. Figures come from official open data: HM Land Registry, the UK House Price Index, the ONS and "
                    "others listed below. Each has its own date; the latest months of sales are still being registered."]
    return c


def write_page(a, payload: dict, stem: str) -> Path:
    html = bp.render_page("report.html", payload)
    path = bp.output_dir(a.out) / f"{stem}-{dt.date.today().isoformat()}.html"
    path.write_text(html, encoding="utf-8")
    return path


def register(sub, module) -> None:
    global bp
    bp = module
    def brand_opts(p):
        p.add_argument("--name", "--agency", dest="agency")
        p.add_argument("--colour")
        p.add_argument("--out")
        p.add_argument("--blueprint-style", "--house", dest="house", action="store_true")
        p.add_argument("--page", action="store_true", help="also write a branded HTML page")
    p = sub.add_parser("address"); p.add_argument("address"); p.add_argument("--asking", type=int); p.add_argument("--type")
    p.add_argument("--district"); brand_opts(p); p.set_defaults(fn=cmd_address)
    p = sub.add_parser("local"); p.add_argument("where"); brand_opts(p); p.set_defaults(fn=cmd_local)
    p = sub.add_parser("rents"); p.add_argument("district"); brand_opts(p); p.set_defaults(fn=cmd_rents)
    p = sub.add_parser("guide"); p.add_argument("district"); p.set_defaults(fn=cmd_guide)
    p = sub.add_parser("sites"); p.add_argument("district"); p.set_defaults(fn=cmd_sites)
