# What the site declares, and how to check it

Origenality is a static site with one hard constraint: no request leaves the
page. Everything below is written to hold that constraint rather than to work
around it. There is no analytics beacon, no tag manager, no remote font and no
third-party script anywhere, and the security policy served with every page says
so in a form a browser enforces.

Two audiences read a site before a human does: the search crawlers, and the
crawlers that feed the generated answers of search and assistant products. The
second kind quotes passages rather than ranking pages, so the
files below are written to be quotable: figures with their perimeter, answers
that stand on their own, and a machine-readable summary at `/llms.txt`.

## The files

| File | What it does |
|---|---|
| `_headers` | security policy and cache, applied by Cloudflare Pages |
| `_redirects` | the short addresses, `/` first of all, all permanent (`301`) |
| `404.html` | the answer, with status `404`, to any address that matches no file |
| `robots.txt` | opens the site to search and to the AI crawlers, points at the sitemap |
| `sitemap.xml` | the five pages and the documentation, each dated by its content |
| `data/sitemap-dates.json` | the SHA-256 of each document in the sitemap and the date it last changed |
| `llms.txt` | the short guide for an agent: pages, data files, key facts, contact |
| `llms-full.txt` | the read me and the methodology in one file |
| `scripts/build_seo_assets.py` | writes the three files above, `--check` says if they are stale |
| `site/tools/build_og_image.py` | draws `site/assets/marks/og.png`, the share image |

The head of each page carries a distinct title, a description, a canonical
address, Open Graph and Twitter cards, and a JSON-LD graph. Nothing in a head is
loaded from elsewhere.

## The decisions worth knowing

**The root redirects, it does not rewrite.** The pages live under `/site/` and
address their assets relatively, so a `200` rewrite of `/` onto
`/site/index.html` would leave the browser at `/` and resolve `assets/base.css`
to `/assets/base.css`: a 404 on the stylesheet, the fonts and the script. `/`
therefore answers `301` to `/site/welcome`. The redirect is permanent because the
`/site/` layout is settled: the canonical tags and the sitemap give it, and the
JSON-LD `WebSite` keeps `https://origenality.com/` as the address of the site.
Browsers cache a `301`. If the pages ever move to the root, these addresses have
to keep answering (a `200` rewrite to the new page), never go back to `302`.

**Cloudflare Pages drops the `.html`.** A request for `/site/methode.html`
answers `308` to `/site/methode`, and that extensionless form is what the site
serves with a `200`. The canonical tags and the sitemap therefore give
`https://origenality.com/site/methode`, never the file name. The four short
addresses in `_redirects` (`/explorer`, `/observatory`, `/method`, `/credits`)
point at that extensionless form, so each costs a single `301`. Two more send
`/site/llms.txt` and `/site/robots.txt` to the files at the root, where agents
look for them first. The links between pages keep the `.html` name, so following
one costs a `308`.

**An unknown address answers 404.** Without a `404.html` at the root of the
deployment, Pages answered any unknown path with `index.html` and a `200`,
`/data/*.json` included. The page it serves now carries `noindex`, no canonical
tag and no script, and it addresses its stylesheets and links from the root
(`/site/assets/base.css`), since it is served at every depth.
`python3 scripts/qa_checks.py served-pages` fails if the file is missing,
indexable, canonised, or uses a relative path.

**The policy allows inline style attributes, and nothing else.** The charts and
the legend are drawn by writing `style="width: 42%"` into the markup from
JavaScript, so a policy without `'unsafe-inline'` on `style-src` empties them. It
was measured rather than assumed: served under `style-src 'self'`, the stacked
columns of the Observatory compute to a height of `0px`; under the policy that
ships, they render. Inline styles carry no execution risk here, and every other
directive stays closed:

```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none';
form-action 'none'; frame-ancestors 'none'; object-src 'none';
upgrade-insecure-requests
```

`img-src` admits `data:` for one thing: the grain of the background is an SVG
written into the stylesheet as a data URI. `connect-src 'self'` covers the four
`fetch` calls that read the data layer. The JSON-LD blocks are data rather than
code and raise no violation under `script-src 'self'`; that too was checked in a
browser, on all five pages, with a listener on `securitypolicyviolation` and
zero events recorded.

**Cache follows the fingerprint.** File names stay stable (`explorer.js` is
`explorer.js` from one build to the next), but every reference to a stylesheet
or a script carries `?v=` and the first eight hex digits of the SHA-256 of the
file as served, in the pages and in the ES-module imports alike
(`scripts/stamp_assets.py`, verified by `--check`). The address changes when the
bytes change, so `/site/assets/*.js` and `*.css` take a year of `immutable`, and
so do the fonts. The HTML pages and `404.html` take `max-age=0,
must-revalidate`, because they hold the fingerprints. What changes without a
fingerprint takes a short cache with `stale-while-revalidate`: ten minutes for
`/data/*` and the JSON under `/site/assets/`, a week for the marks and the share
image. `/data/*` also sends `Access-Control-Allow-Origin: *`, since those files
are meant to be reused. The patterns in `_headers` do not overlap: when two rules
set the same header, Pages joins their values with a comma.

The zone can override all of this. A zone-level Browser Cache TTL (four hours by
default) replaces any shorter `max-age`, so until the zone is set to respect
existing headers, the `600` and the `max-age=0` above arrive as `14400`. Only a
`curl -sI` on the deployed site shows which one a reader receives.

**The share image is drawn, not typed.** `build_og_image.py` renders a 1200×630
PNG from the site's own fonts and colours, and takes its figure from the same
recount as the pages, so the image cannot drift from the map. An SVG would have
been lighter and is not an option: no social platform renders one.

**No FAQPage markup.** Google restricted that rich result to government and
health sites in August 2023. The questions at the foot of the Method page are
plain HTML headings and paragraphs, which is what an AI crawler extracts anyway,
and each answer is written to stand alone at the length those systems quote.

## Regenerating

```bash
python3 scripts/build_seo_assets.py            # sitemap.xml, llms.txt, llms-full.txt
python3 scripts/build_seo_assets.py --check    # exits 1 if one of them is stale
python3 site/tools/build_og_image.py           # site/assets/marks/og.png
```

The first needs nothing but the standard library. The second needs
Pillow and fontTools with brotli, which is why it sits with the build tools
rather than with the commands a fresh clone runs; its output is committed, so
nobody has to run it to serve the site.

Run `build_seo_assets.py --check` after any change to a page or a document. A
document's `lastmod` is the date its SHA-256 last changed, kept in
`data/sitemap-dates.json`; the check fails when a document has changed and its
date has not. No git history enters the calculation, since the working tree and
the public tree do not share one. Run `stamp_assets.py` before it, because stamping
changes the pages.

## Checking a deployment

```bash
SITE=https://origenality.com

# redirects: 301 with the right Location, 308 for a file name
curl -sI $SITE/                          | grep -i '^HTTP\|^location'   # 301, /site/welcome
curl -sI $SITE/explorer                  | grep -i '^HTTP\|^location'   # 301, /site/
curl -sI $SITE/method                    | grep -i '^HTTP\|^location'   # 301, /site/methode
curl -sI $SITE/site/llms.txt             | grep -i '^HTTP\|^location'   # 301, /llms.txt
curl -sI $SITE/site/methode.html         | grep -i '^HTTP\|^location'   # 308, /site/methode

# a real 404, at any depth and under /data/
curl -s -o /dev/null -w '%{http_code}\n' $SITE/no-such-page            # 404
curl -s -o /dev/null -w '%{http_code}\n' $SITE/site/a/b/c              # 404
curl -s -o /dev/null -w '%{http_code}\n' $SITE/data/no-such-file.json  # 404
curl -s $SITE/no-such-page | grep -c 'noindex'                          # 1

# the policy on a page
curl -sI $SITE/site/methode | grep -i 'content-security\|permissions\|referrer\|strict-transport'

# cache: pages revalidate, stamped assets and fonts are immutable, data is short
curl -sI $SITE/site/methode | grep -i '^cache-control'                  # max-age=0, must-revalidate
curl -sI "$SITE/site/$(curl -s $SITE/site/methode | grep -o 'assets/base.css?v=[0-9a-f]*' | head -1)" \
  | grep -i '^cache-control'                                            # max-age=31536000, immutable
curl -sI $SITE/site/assets/fonts/literata-var.woff2 | grep -i '^cache-control'   # immutable
curl -sI $SITE/data/graph.json | grep -i '^cache-control\|^access-control'      # max-age=600, *
# a max-age of 14400 on any of these means the zone's Browser Cache TTL overrides _headers

# the files agents read: ours, not the host's defaults
curl -s  $SITE/robots.txt | head -5
curl -s  $SITE/llms.txt   | head -5
```

Cloudflare serves a managed `robots.txt` when a site has none, which is what
answered before this file existed. The first command that matters after a deploy
is the one that shows our own text there.

Then, in a browser:

- **Rich Results Test** (`search.google.com/test/rich-results`): paste each of
  the four addresses and read the detected items. Expect `WebSite`, `Person` and
  `WebPage` on the Explorer, `Dataset` on the Method page, `SoftwareSourceCode`
  and `Person` on the Credits, `BreadcrumbList` on the three inner pages. The
  tool reports `Dataset` as unsupported for rich results, which is expected: the
  block is there for Google Dataset Search and for the AI crawlers, not for a
  snippet.
- **Schema Markup Validator** (`validator.schema.org`): the same four addresses,
  for the types the Rich Results Test ignores.
- **Open Graph**: any card debugger, or simply open `/site/assets/marks/og.png`.
  The image is 1200×630 and declares its dimensions in the head, so a scraper
  does not have to fetch it to lay out a card.

## What is left to do outside this repository

**The custom domain.** Everything here names `https://origenality.com`. Until
that domain is attached to the Pages project, the canonical tags, the sitemap
and `llms.txt` point at a host that does not answer, and the `.pages.dev`
address will be indexed instead. Attach the domain first, and send `www` to the
apex with a redirect rule at the zone level rather than in `_redirects`.

**Search Console.** Add `origenality.com` as a Domain property, which verifies
by a single TXT record at the apex. Google generates the value, so it cannot be
written here: take it from the verification screen and place it. A Domain
property covers `www`, the apex and every path in one go. Once verified, submit
`https://origenality.com/sitemap.xml`.

**Bing Webmaster Tools.** Import the Search Console property rather than
verifying again. Several assistant products read the Bing index.

**IndexNow.** Cloudflare can do it without a line of code: in the zone, under
Caching, Configuration, turn on Crawler Hints. Cloudflare then notifies IndexNow
whenever content changes, which reaches Bing, Yandex and the products behind
them. The alternative, a key file at the root and a GET on the IndexNow
endpoint at each deploy, is only worth it if the hints prove insufficient.

**Analytics, without a script.** Cloudflare Web Analytics is a client-side
beacon: enabling it, even through the dashboard's automatic setup, injects a
script into every page and breaks the promise the Credits page makes. Use the
zone's own traffic analytics instead, which are measured at the edge and cost
the reader nothing: requests, top paths, referrers, countries, all in the
dashboard, with no code on the page. It gives fewer numbers than a beacon, and
it gives them without asking the reader for anything.

**Brand presence.** AI systems cite what is mentioned elsewhere more readily
than what merely ranks. The things that would move that here are academic
rather than promotional: a page for the project on a laboratory site, a mention
in an Origen bibliography or a digital humanities index, an entry in a directory
of patristics tools, and the repository itself being findable. None of it is
work for this repository, and all of it counts more than any tag in a head.
