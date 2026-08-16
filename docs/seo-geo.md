# What the site declares, and how to check it

Origenality is a static site with one hard constraint: no request leaves the
page. Everything below is written to hold that constraint rather than to work
around it. There is no analytics beacon, no tag manager, no remote font and no
third-party script anywhere, and the security policy served with every page says
so in a form a browser enforces.

Two audiences read a site before a human does: the search crawlers, and the
crawlers that feed answers in ChatGPT, Perplexity, Claude and Google's AI
overviews. The second kind quotes passages rather than ranking pages, so the
files below are written to be quotable: figures with their perimeter, answers
that stand on their own, and a machine-readable summary at `/llms.txt`.

## The files

| File | What it does |
|---|---|
| `_headers` | security policy and cache, applied by Cloudflare Pages |
| `_redirects` | the short addresses, `/` first of all |
| `robots.txt` | opens the site to search and to the AI crawlers, points at the sitemap |
| `sitemap.xml` | the four pages and the documentation, dated from git |
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
therefore answers `302` to `/site/`. A rewrite becomes possible the day the
pages carry absolute paths, and not before.

**Cloudflare Pages drops the `.html`.** A request for `/site/methode.html`
answers `308` to `/site/methode`, and that extensionless form is what the site
serves with a `200`. The canonical tags and the sitemap therefore give
`https://origenality.com/site/methode`, never the file name. The four vanity
paths in `_redirects` point at the `.html` file, which costs one further hop
(`302` then `308`); pointing them at `/site/methode` would spend one redirect
instead of two.

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
browser, on all four pages, with a listener on `securitypolicyviolation` and
zero events recorded.

**Cache is short where the name is stable.** No asset carries a hash in its
name, so `explorer.js` stays `explorer.js` across builds and a year of
`immutable` would pin an old version in a reader's browser. The fonts, whose
content only changes with their name, keep the year. Everything else takes ten
minutes of cache with `stale-while-revalidate`, which serves the copy at hand
while the browser fetches the new one. Hash the file names in the build and the
whole of `/site/assets/` can move to `immutable`.

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

The first needs nothing but the standard library and git. The second needs
Pillow and fontTools with brotli, which is why it sits with the build tools
rather than with the commands a fresh clone runs; its output is committed, so
nobody has to run it to serve the site.

Run `build_seo_assets.py --check` after any commit that touches a page or a
document: the dates in the sitemap come from the last commit of each file.

## Checking a deployment

```bash
curl -sI https://origenality.com/                     # 302 to /site/
curl -sI https://origenality.com/site/methode.html    # 308 to /site/methode
curl -s  https://origenality.com/robots.txt | head -5 # ours, not Cloudflare's default
curl -s  https://origenality.com/llms.txt  | head -5
curl -sI https://origenality.com/site/assets/fonts/literata-var.woff2 | grep -i cache
curl -sI https://origenality.com/site/methode | grep -i 'content-security\|permissions\|referrer'
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
verifying again. Bing feeds Copilot, and its index is the one several AI
products read.

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
