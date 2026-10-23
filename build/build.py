"""Unpack the exported CK Luxury MPV bundle into a static public/ directory.

The export is a single self-extracting HTML: a manifest of base64 assets, a
page template that refers to each asset by uuid, and a resource map the page's
JS reads at runtime. This turns that into ordinary files a CDN can cache, and
adds the SEO and social metadata the export has no way to carry.

Run:  python3 build/build.py
"""
import base64, gzip, hashlib, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
SRC  = os.path.join(PROJ, "CK Luxury MPV Penang.html")
OUT  = os.path.join(PROJ, "public")

# Where the site will be served. og:image has to be absolute, so this is the
# one constant to change if the site moves to a custom domain.
CANONICAL = "https://ck-luxury-mpv-penang.pages.dev"

TITLE = ("CK Luxury MPV Car Rental & Tour Penang — Alphard, Vellfire "
         "& Chauffeur Service")
DESCRIPTION = (
    "Luxury MPV rental and private chauffeur in Penang. Toyota Alphard, "
    "Vellfire, Staria, Starex and Innova. Airport transfers from RM180, "
    "day packages from RM480 including fuel, tolls and parking. "
    "5.0 on Google from 368 reviews. Open 24 hours."
)

html = open(SRC, encoding="utf-8").read()

def tag(name):
    m = re.search(r'<script type="__bundler/%s">(.*?)</script>' % name, html, re.S)
    if not m:
        raise SystemExit("bundle has no __bundler/%s block" % name)
    return m.group(1).strip()

manifest = json.loads(tag("manifest"))
template = json.loads(tag("template"))
ext      = json.loads(tag("ext_resources"))

id_by_uuid = {e["uuid"]: e["id"] for e in ext}

# sha256 -> stable name, so a photo keeps its filename across re-exports even
# though every uuid is renumbered. Generated from the design source folder.
NAMES = json.load(open(os.path.join(HERE, "asset-names.json")))

EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
       "font/woff2": ".woff2", "text/javascript": ".js",
       "application/javascript": ".js"}

def kebab(s):
    s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '-', s)
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

def asset_path(uuid, mime, data):
    ext_ = EXT.get(mime)
    if ext_ is None:
        raise SystemExit("unknown mime %r for %s" % (mime, uuid))
    ident = id_by_uuid.get(uuid, "")

    if mime == "font/woff2":
        # Named after the family its own @font-face declares. Several subsets
        # share a family; the content hash keeps their filenames apart.
        m = re.search(r"font-family:\s*'([^']+)'(?:(?!@font-face).)*?"
                      r'url\("%s"\)' % re.escape(uuid), template, re.S)
        if not m:
            raise SystemExit("no @font-face rule for font %s" % uuid)
        return "assets/fonts/%s%s" % (kebab(m.group(1)), ext_)

    if ext_ == ".js":
        if ident.startswith("http"):           # react / react-dom
            return "assets/js/" + ident.rsplit("/", 1)[-1]
        if b"dc-runtime" in data[:400]:
            return "assets/js/dc-runtime.js"
        if b"@ds-bundle" in data[:400]:
            return "assets/js/design-system.js"
        raise SystemExit("unrecognised script asset %s" % uuid)

    name = NAMES.get(hashlib.sha256(data).hexdigest())
    if name is None:
        name = kebab(ident) if ident else "photo-" + hashlib.sha256(data).hexdigest()[:8]
        print("  note: unnamed image %s -> %s" % (uuid[:8], name))
    return "assets/images/%s%s" % (name, ext_)

def fingerprint(path, data):
    """foo.jpg -> foo.<hash>.jpg

    /assets/* is served immutable for a year, so content that changes has to
    change its name too, or browsers keep showing the old file.
    """
    root, ext_ = os.path.splitext(path)
    return "%s.%s%s" % (root, hashlib.sha256(data).hexdigest()[:8], ext_)

# Decode and place everything before touching public/, so a bundle this script
# no longer understands fails without leaving a half-built site behind.
unpacked = []
for uuid, entry in manifest.items():
    data = base64.b64decode(entry["data"])
    if entry.get("compressed"):
        data = gzip.decompress(data)
    unpacked.append((uuid, fingerprint(asset_path(uuid, entry["mime"], data), data), data))

paths = [p for _, p, _ in unpacked]
dupes = sorted({p for p in paths if paths.count(p) > 1})
if dupes:
    raise SystemExit("two assets map to the same path: %s" % ", ".join(dupes))

if os.path.isdir(OUT):
    shutil.rmtree(OUT)
written = {}
for uuid, path, data in unpacked:
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "wb").write(data)
    written[uuid] = path

# Which subset of each family carries basic Latin. The family ships as several
# unicode-range subsets under one name and only one has A-Z; a .notdef box has
# a bounding box like any glyph, so the file cannot be identified by probing a
# render. The page's own @font-face rules say it outright, so read them here
# and hand the answer to the card generator.
latin = {}
for uuid, path in written.items():
    if not path.endswith(".woff2"):
        continue
    m = re.search(r"@font-face\s*\{(?:(?!@font-face).)*?url\(\"%s\"\)"
                  r"(?:(?!@font-face).)*?\}" % re.escape(uuid), template, re.S)
    if not m:
        continue
    rule = m.group(0)
    fam = re.search(r"font-family:\s*'([^']+)'", rule)
    rng = re.search(r"unicode-range:\s*([^;}]+)", rule, re.I)
    if fam and rng and "U+0000-00FF" in rng.group(1).upper():
        latin[kebab(fam.group(1))] = path
if len(latin) < 2:
    raise SystemExit("could not identify the Latin subsets: %r" % latin)
json.dump(latin, open(os.path.join(HERE, "latin-fonts.json"), "w"), indent=2)

# Share card and favicons are drawn from the unpacked photos and fonts, so they
# are made once those exist and before the metadata that has to name them.
subprocess.run([sys.executable, os.path.join(HERE, "make_share_assets.py")], check=True)
_card = os.path.join(OUT, "assets", "social", "share-card.jpg")
_digest = hashlib.sha256(open(_card, "rb").read()).hexdigest()[:8]
SHARE_CARD = "assets/social/share-card.%s.jpg" % _digest
os.rename(_card, os.path.join(OUT, SHARE_CARD))

out = template

# --- Fix: dc-runtime calls componentDidUpdate(prevProps) with ONE argument,
# but the page component is written as componentDidUpdate(_, prevState). `prev`
# is therefore undefined and `prev.sheet` throws on every single update. The
# throw lands after applyLang(), so the language toggle still works and the bug
# looks cosmetic, but showSheet() and animStep() below it never run: the mobile
# menu does not animate open and the enquiry steps do not slide. Track the
# previous values on the instance instead of trusting the argument.
_BAD = """componentDidUpdate(_, prev){
    this.applyLang();
    if (!prev.sheet && this.state.sheet) this.showSheet();
    if (prev.step !== this.state.step) this.animStep(this.state.step > prev.step ? 1 : -1);
  }"""
_GOOD = """componentDidUpdate(){
    this.applyLang();
    const prev = this._prevUI || {};
    if (!prev.sheet && this.state.sheet) this.showSheet();
    if (prev.step !== undefined && prev.step !== this.state.step) this.animStep(this.state.step > prev.step ? 1 : -1);
    this._prevUI = { sheet: this.state.sheet, step: this.state.step };
  }"""
if _BAD not in out:
    raise SystemExit("componentDidUpdate patch no longer matches source - review before building")
out = out.replace(_BAD, _GOOD, 1)

for uuid, path in written.items():
    out = out.replace(uuid, path)
resource_map = {e["id"]: written[e["uuid"]] for e in ext}

# The export preconnects to Google Fonts, but every font is self-hosted here,
# so the hint only costs a DNS lookup and a TLS handshake that go unused.
out = re.sub(r'\s*<link rel="preconnect" href="https://fonts\.(googleapis|gstatic)\.com"[^>]*>', '', out)

ld = {
    "@context": "https://schema.org",
    "@type": "AutoRental",
    "name": "CK Luxury MPV Car Rental and Tour Penang",
    "description": DESCRIPTION,
    "url": CANONICAL,
    "image": CANONICAL + "/" + SHARE_CARD,
    "telephone": "+60164106262",
    "email": "luxurympvsupercar@gmail.com",
    "priceRange": "RM180-RM1600",
    "currenciesAccepted": "MYR",
    "paymentAccepted": "Cash",
    "openingHours": "Mo-Su 00:00-23:59",
    "aggregateRating": {"@type": "AggregateRating", "ratingValue": "5.0",
                        "reviewCount": "368", "bestRating": "5"},
    "address": {"@type": "PostalAddress",
                "streetAddress": "1A-23A-3A, Urban Suite, Lintang Hajjah Rehmah 1, Jelutong",
                "addressLocality": "George Town", "postalCode": "11600",
                "addressRegion": "Pulau Pinang", "addressCountry": "MY"},
    "geo": {"@type": "GeoCoordinates", "latitude": 5.3881181, "longitude": 100.3168844},
    "areaServed": [{"@type": "City", "name": n} for n in
                   ["George Town", "Penang", "Ipoh", "Taiping", "Kulim",
                    "Alor Setar", "Sungai Petani"]],
    "sameAs": ["https://www.facebook.com/abudanishcarrentalpenang/",
               "https://www.instagram.com/luxury_mpv_vip_transportpenang"],
    "potentialAction": {"@type": "ReserveAction",
                        "target": "https://wa.me/60164106262",
                        "name": "WhatsApp Booking"},
}

def esc(t):
    return t.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")

inject = """
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}/">
<meta name="theme-color" content="#0C0E11">
<meta name="robots" content="index, follow, max-image-preview:large">

<meta property="og:type" content="website">
<meta property="og:site_name" content="CK Luxury MPV Penang">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}/">
<meta property="og:image" content="{url}/{card}">
<meta property="og:image:secure_url" content="{url}/{card}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="CK Luxury MPV Penang — Alphard and Vellfire chauffeur hire, airport transfer from RM180">
<meta property="og:locale" content="en_MY">
<meta property="og:locale:alternate" content="ms_MY">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{url}/{card}">

<link rel="icon" href="favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="apple-touch-icon.png">

<script type="application/ld+json">{ld}</script>
<script>window.__resources = {res};</script>
""".format(desc=esc(DESCRIPTION), title=esc(TITLE), url=CANONICAL, card=SHARE_CARD,
           ld=json.dumps(ld, separators=(",", ":")).replace("</", "<\\/"),
           res=json.dumps(resource_map).replace("</", "<\\/"))

# Injected after the charset/viewport metas, not straight after <head>: the
# charset has to land in the first 1024 bytes, and this block is several KB.
anchor = None
for m in re.finditer(r'<meta[^>]+(?:charset|viewport)[^>]*>', out, re.I):
    anchor = m
if anchor is None:
    anchor = re.search(r"<head[^>]*>", out, re.I)
out = out[:anchor.end()] + inject + out[anchor.end():]

open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(out)
shutil.copy(os.path.join(OUT, "index.html"), os.path.join(OUT, "404.html"))
open(os.path.join(OUT, ".nojekyll"), "w").close()

open(os.path.join(OUT, "_headers"), "w").write(
    "/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n\n"
    "/\n  Cache-Control: public, max-age=0, must-revalidate\n")
open(os.path.join(OUT, "robots.txt"), "w").write(
    "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % CANONICAL)
open(os.path.join(OUT, "sitemap.xml"), "w").write(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    '  <url><loc>%s/</loc><changefreq>monthly</changefreq><priority>1.0</priority></url>\n'
    '</urlset>\n' % CANONICAL)

open(os.path.join(PROJ, "SHARE-LINK.txt"), "w").write(
    "SEND THIS TO CLIENTS\n    %s/\n\n"
    "IF WHATSAPP SHOWS AN OLD PREVIEW, SEND THIS ONCE INSTEAD\n    %s/?v=%s\n\n"
    "WhatsApp caches a link preview for about a week with no way to purge it.\n"
    "The ?v= value is the share card's content hash, so that is a URL WhatsApp\n"
    "has not cached and it fetches the new preview. The site ignores the\n"
    "parameter, and canonical/og:url stay on the bare address for search.\n\n"
    "Rebuild with: python3 build/build.py\n" % (CANONICAL, CANONICAL, _digest))

total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs)
count = sum(len(fs) for _, _, fs in os.walk(OUT))
print("index.html  %.1f KB" % (os.path.getsize(os.path.join(OUT, "index.html")) / 1024))
print("total       %.1f MB across %d files" % (total / 1048576, count))
for r, _, fs in sorted(os.walk(OUT)):
    for f in sorted(fs):
        p = os.path.join(r, f)
        print("  %-54s %8.1f KB" % (os.path.relpath(p, OUT), os.path.getsize(p) / 1024))
