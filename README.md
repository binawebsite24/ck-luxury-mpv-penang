# CK Luxury MPV Car Rental & Tour Penang

Lead-gen site for CK Luxury MPV (Google listing: *Kereta Sewa MPV Luxury Rental
Penang*), George Town, Penang. Built to the same pattern as `rayme-car-rental`.

**Live:** https://ck-luxury-mpv-penang.pages.dev

```
CK Luxury MPV Penang.html   design source — the exported self-extracting bundle
build/build.py              unpacks it into public/
build/make_share_assets.py  share card + favicons, drawn from the site's own assets
build/asset-names.json      sha256 -> stable photo name, so filenames survive re-exports
public/                     what gets served
```

## Build

```bash
python3 build/build.py
```

Re-run after every re-export of the HTML, then commit `public/`.

The build:

- unpacks the bundle's 25 assets into `public/assets/{images,fonts,js}`
- fingerprints every asset (`hero.bd5cb9f8.jpg`) so `/assets/*` can be served
  immutable for a year without a changed photo getting stuck behind caches
- names photos from their sha256, so a re-export with renumbered uuids keeps the
  same filenames
- drops the Google Fonts preconnect — all fonts are self-hosted
- injects description, canonical, Open Graph, Twitter card and `AutoRental`
  JSON-LD, and writes `robots.txt`, `sitemap.xml`, `_headers` and a 404
- generates the WhatsApp share card and favicons

## Two fixes the build applies

Both guard themselves: if the source stops matching, the build stops rather than
shipping something subtly broken.

1. **`componentDidUpdate`.** The page is authored as
   `componentDidUpdate(_, prevState)` but dc-runtime calls it with one argument,
   so `prev` is undefined and `prev.sheet` throws on every update. The throw
   lands after `applyLang()`, so the language toggle keeps working and it looks
   cosmetic — but the mobile menu never animates open and the enquiry steps
   never slide. Previous values are tracked on the instance instead.
2. **Latin font subset.** Each family ships as several `unicode-range` subsets
   under one name and only one carries A–Z. The share card generator reads the
   page's own `@font-face` rules to find it; picking by filename, size, or by
   probing a render all fail, because a `.notdef` box has a bounding box like
   any real glyph and the card silently comes out as tofu.

## Deploying

Cloudflare, connected to this repo — no build command, output directory
`public`. `wrangler.jsonc` is there for `wrangler deploy` from the CLI, and
`vercel.json` for Vercel, but Cloudflare + Git is the live path.

`CANONICAL` in `build/build.py` is the one constant to change if the site moves
to a custom domain; `og:image` has to be absolute, so it is not derivable at
runtime. Change it, rebuild, commit.

## Content

Every price, review, phone number and service area comes from the business's own
Google Business Profile, its owner-posted rate cards, its Facebook page and its
Instagram. See `scraped/KS001-kereta-sewa-mpv-penang/` in the research repo.

**Before sending this to the client, confirm:** the fleet photos are matched by
eye — AGH30 vs AGH40 is hard to call from a photo, and the Vellfire card shows
an earlier-generation car than the AGH40 rates beside it. There are no photos at
all of the Innova, Starex, Staria or Myvi, which is why those sit in a rate
table rather than getting cards. The address differs between Google and
Facebook, the interstate rates were truncated by Google in the owner's own post,
and cash-only is taken from the Google profile.
