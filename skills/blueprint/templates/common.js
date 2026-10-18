// Shared by every Blueprint page (dashboard, compare): formatting helpers, the two looks, gap panel and footer.
// Inlined into each page by blueprint.py, so pages stay single self-contained files.
var BP_TYPES = { D: "Detached", S: "Semi-detached", T: "Terraced", F: "Flat or maisonette", O: "Other" };
var BP_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
var BP_MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
function money(v) { return v == null ? "n/a" : "£" + Math.round(v).toLocaleString("en-GB"); }
function short(v) {
  if (v == null) return "n/a";
  if (v >= 1e6) return "£" + (v / 1e6).toFixed(v >= 1e7 ? 0 : 2).replace(/\.?0+$/, "") + "m";
  if (v >= 1e3) return "£" + Math.round(v / 1e3) + "k";
  return "£" + v;
}
function pct(v) { return v == null ? "n/a" : (v > 0 ? "+" : "") + v.toFixed(1) + "%"; }
function cls(v) { return v == null ? "" : v > 0 ? "up" : v < 0 ? "down" : ""; }
function mlabel(m, long) { var p = m.split("-"); return (long ? BP_MONTHS_LONG : BP_MONTHS)[+p[1] - 1] + " " + (long ? p[0] : p[0].slice(2)); }
function median(xs) {
  if (!xs.length) return null;
  var s = xs.slice().sort(function (a, b) { return a - b; }), h = s.length >> 1;
  return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2;
}
function el(id) { return document.getElementById(id); }
function hexRgb(h) { h = h.replace("#", ""); if (h.length === 3) h = h.replace(/./g, "$&$&"); return [0, 2, 4].map(function (i) { return parseInt(h.substr(i, 2), 16); }); }
function lum(rgb) { var c = rgb.map(function (v) { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]; }

// The Blueprint style, or the user's own colour and logo. Never both in the header.
function applyBrand(D) {
  var B = D.brand || { mode: "blueprint" };
  var HOUSE = B.mode !== "own";
  var INK = [26, 28, 41];
  function validHex(h) { return /^#?[0-9a-f]{3}([0-9a-f]{3})?$/i.test(h || "") ? (h[0] === "#" ? h : "#" + h) : null; }
  function mix(a, b, t) { return a.map(function (v, i) { return Math.round(v * (1 - t) + b[i] * t); }); }
  function rgbHex(c) { return "#" + c.map(function (v) { return ("0" + v.toString(16)).slice(-2); }).join(""); }
  var primary = HOUSE ? "#243873" : (validHex(B.colour) || "#1A1C29");
  var prgb = hexRgb(primary);
  var rgb = lum(prgb) > .4 ? mix(prgb, INK, .55) : prgb;  // the brand, darkened if too pale to read on white
  var accent = rgbHex(rgb);
  var second = HOUSE ? "#4A66B0" : "rgba(" + rgb.join(",") + ",.5)";
  var third = HOUSE ? "#9AA9D6" : "rgba(" + rgb.join(",") + ",.25)";
  var root = document.documentElement.style;
  root.setProperty("--primary", primary);
  root.setProperty("--on-primary", lum(prgb) < .45 ? "#fff" : "#1A1C29");
  root.setProperty("--accent", accent);
  root.setProperty("--soft", "rgba(" + rgb.join(",") + ",.08)");
  root.setProperty("--gap-rule", HOUSE ? "#243873" : "#1A1C29");
  var hdr = el("hdr"), slot = el("logo-slot");
  if (HOUSE) {
    hdr.className = "bp";
    slot.innerHTML = '<img class="bp-logo" alt="Blueprint" src="' + D.blueprint_logo.white + '">';
  } else {
    hdr.className = "own" + (B.logo && B.logo.tone === "light" ? " light-logo" : "");
    slot.innerHTML = B.logo ? '<img class="own-logo" alt="' + esc(B.name || "Logo") + '" src="' + B.logo.uri + '">'
                            : '<span class="own-name">' + esc(B.name || "") + "</span>";
  }
  return {
    house: HOUSE, brand: B, accent: accent, rgb: rgb, second: second,
    series: [accent, second, third],
    shade: function (t) { return "rgba(" + rgb.join(",") + "," + t + ")"; },
    prepared: function (label) {
      return !HOUSE && B.name ? "Prepared for " + B.name + ", " + label + "." : "Generated " + label + ".";
    }
  };
}

function renderGapAndFooter(D) {
  var G = D.gap || {};
  if (G.title) {
    el("gap").innerHTML = "<h2>" + esc(G.title) + "</h2><p>" + esc(G.body) + "</p>" + (G.link ? "<p><a href='" + esc(G.link) + "' target='_blank' rel='noopener'>" + esc(G.link_text || G.link) + "</a></p>" : "");
  } else { el("gap").style.display = "none"; }
  el("footer").innerHTML = D.caveats.map(function (c) { return "<p>" + esc(c) + "</p>"; }).join("") +
    D.attribution.map(function (c) { return "<p>" + esc(c) + "</p>"; }).join("") +
    "<div class='credit'><img alt='Blueprint' src='" + D.blueprint_logo.ink + "'><span>Made with the Blueprint skill for Claude, from " +
    "<a href='" + esc(D.credit_link || "https://blueprintpropertymarketing.com") + "' target='_blank' rel='noopener'>Blueprint Property Marketing</a>. Not a valuation.</span></div>";
}
