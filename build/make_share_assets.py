"""Generate the WhatsApp/Open Graph share card and the favicons.

Run via build/build.py, after the bundle's assets have been unpacked: the card
is drawn from the site's own hero photo and its own Wix Madefor fonts, so it
matches the page it links to.
"""
import glob, os, site, sys

_usp = site.getusersitepackages()
sys.path[:0] = _usp if isinstance(_usp, list) else [_usp]

from PIL import Image, ImageDraw, ImageFont

INK    = (12, 14, 17)       # #0C0E11  page background
GOLD   = (217, 184, 114)    # #D9B872  accent
SOFT   = (240, 220, 174)    # #F0DCAE
WHITE  = (255, 255, 255)
MUTE   = (155, 163, 174)    # #9BA3AE

W, H = 1200, 630
PAD   = 70
LEFT  = 690                 # where the photo panel starts

HERE   = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(os.path.dirname(HERE), "public")


def _asset(folder, stem, ext):
    """Assets carry a content hash in the name, so match on the stem."""
    hits = sorted(glob.glob(os.path.join(PUBLIC, "assets", folder, stem + ".*" + ext)))
    if not hits:
        raise SystemExit("no %s asset matching %r" % (folder, stem))
    return hits[0]


def _latin_face(stem):
    """The family ships as several unicode-range subsets under one name.

    Only one carries basic Latin, and which file that is changes with every
    export. build.py reads the page's own @font-face rules to find it; without
    that the card renders as tofu boxes, and a render probe cannot tell the
    difference because a .notdef box has a bounding box like any other glyph.
    """
    import json
    path = json.load(open(os.path.join(HERE, "latin-fonts.json")))[stem]
    return os.path.join(PUBLIC, path)


_FACE = {}

def font(stem, size, weight=800):
    """Wix Madefor is variable (wght 400-800); pin the axis per use.

    Falls back to the default bitmap face if FreeType here was built without
    brotli and cannot open a woff2 - the card is still generated, just plainer.
    """
    try:
        if stem not in _FACE:
            _FACE[stem] = _latin_face(stem)
        f = ImageFont.truetype(_FACE[stem], size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        return f
    except SystemExit:
        raise
    except Exception as e:
        print("  note: %s unavailable (%s); using default face" % (stem, e))
        return ImageFont.load_default(size)


def display(size, weight=800):
    return font("wix-madefor-display", size, weight)


def body(size, weight=500):
    return font("wix-madefor-text", size, weight)


def tracked(draw, xy, s, fnt, fill, tracking=0.0):
    x, y = xy
    for ch in s:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + tracking
    return x - xy[0]


def wrap(draw, s, fnt, width):
    lines, cur = [], ""
    for word in s.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= width or not cur:
            cur = trial
        else:
            lines.append(cur); cur = word
    if cur:
        lines.append(cur)
    return lines


def star_glyph(draw, cx, cy, r, fill):
    """A five-pointed star, drawn rather than set as text."""
    import math
    pts = []
    for i in range(10):
        a = math.radians(-90 + i * 36)
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    draw.polygon(pts, fill=fill)


def photo_panel(card, path, left, feather=250):
    """Right-hand photo, cover-fitted, fading left into the background."""
    img = Image.open(path).convert("RGB")
    pw, ph = W - left, H
    scale = max(pw / img.width, ph / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    ox = (img.width - pw) // 2
    oy = int((img.height - ph) * 0.45)
    img = img.crop((ox, oy, ox + pw, oy + ph))

    mask = Image.new("L", (pw, ph), 255)
    md = ImageDraw.Draw(mask)
    for i in range(feather):
        md.line([(i, 0), (i, ph)], fill=int(255 * (i / feather) ** 1.4))
    card.paste(img, (left, 0), mask)


def build_card():
    card = Image.new("RGB", (W, H), INK)
    photo_panel(card, _asset("images", "hero", "jpg"), LEFT)
    d = ImageDraw.Draw(card)

    y = PAD
    tracked(d, (PAD, y), "CK LUXURY MPV", display(34, 800), GOLD, 2.6)
    y += 46
    tracked(d, (PAD, y), "CAR RENTAL & TOUR PENANG", body(15, 600), MUTE, 3.4)
    y += 62

    head = display(49, 800)
    for line in wrap(d, "Luxury MPV, with a driver who knows Penang.", head, LEFT - PAD - 40):
        d.text((PAD, y), line, font=head, fill=WHITE)
        y += 58
    y += 16

    sub = body(21, 500)
    for line in ["Airport transfer from RM180 · Day packages",
                 "from RM480, fuel and tolls included."]:
        d.text((PAD, y), line, font=sub, fill=MUTE)
        y += 31

    y += 26
    # The star is drawn, not typed: U+2605 is outside the Latin subset these
    # fonts ship, so as text it comes out as a .notdef box.
    star_glyph(d, PAD + 11, y + 14, 12, GOLD)
    w = tracked(d, (PAD + 30, y), "5.0", display(23, 800), GOLD, 1.0)
    tracked(d, (PAD + 30 + w + 12, y + 3), "368 Google reviews · Open 24 hours",
            body(18, 600), SOFT, 0.4)

    out = os.path.join(PUBLIC, "assets", "social")
    os.makedirs(out, exist_ok=True)
    card.save(os.path.join(out, "share-card.jpg"), "JPEG", quality=88, optimize=True)


def build_icons():
    """Favicons from the page's own logo."""
    logo = Image.open(_asset("images", "logo", "jpg")).convert("RGB")
    s = min(logo.size)
    logo = logo.crop(((logo.width - s) // 2, (logo.height - s) // 2,
                      (logo.width + s) // 2, (logo.height + s) // 2))
    logo.resize((512, 512), Image.LANCZOS).save(os.path.join(PUBLIC, "icon-512.png"), optimize=True)
    logo.resize((180, 180), Image.LANCZOS).save(os.path.join(PUBLIC, "apple-touch-icon.png"), optimize=True)
    logo.resize((64, 64), Image.LANCZOS).save(
        os.path.join(PUBLIC, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])


if __name__ == "__main__":
    build_card()
    build_icons()
    print("  share card + favicons written")
