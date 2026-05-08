# site/ — GitHub Pages landing + deck

Published to [p0intman.github.io/liftwork](https://p0intman.github.io/liftwork/)
on every push to `main` that touches `site/**`. The workflow lives at
[.github/workflows/pages.yaml](../.github/workflows/pages.yaml) and uses
the official Pages Actions (`configure-pages`, `upload-pages-artifact`,
`deploy-pages`) — no `gh-pages` branch involved.

## What's here

- **`index.html`** — responsive landing page. Hero, six features, install
  block, roadmap, footer. Fetches the live ★ count from the GitHub API
  (cached 30 min in `localStorage` to avoid burning the unauth rate
  limit). Mobile-first, no framework.
- **`deck.html`** — the 1920×1080 pitch deck. 12 slides:
  cover, problem, promise, architecture, pipeline, stack, quick-start,
  repo layout, **diagnostics**, **observability**, roadmap, closing.
  Same web component (`<deck-stage>`) as the source — keyboard nav,
  thumbnails, print-to-PDF, and hidden speaker notes all work.
  Every external link points at the real GitHub URL; CTAs are clickable.
- **`deck-stage.js`** — the deck web component (vendored as-is; ~70KB).
  See its top-of-file docstring for the full feature list (keyboard
  nav, thumbnail rail, print, scaling, etc.).
- **`styles.css`** — landing styles only. The deck has its own inline
  `<style>` block tuned for the projection viewport.
- **`script.js`** — the live star count fetch for the landing.

## First-time setup (one-time, in repo Settings)

1. **Settings → Pages → Source**: pick `GitHub Actions` (not the legacy
   "Deploy from a branch" option).
2. Push a commit that touches `site/**` and the workflow takes it from
   there. The first run also publishes the URL to the workflow output.

## Local preview

```bash
cd site && python3 -m http.server 8765
open http://localhost:8765
```

That's it. No build step, no node_modules.

## Updating the deck

Edit `deck.html`. The slides are plain `<section>` elements inside
`<deck-stage>` — add one and the rail / counter / nav pick it up
automatically. To keep links honest:

- Use `class="deck-link"` on inline links so they pick up the
  underline-on-hover styling that fits the editorial look.
- Use `class="pill-link"` for pill-shaped CTAs (matches the cover meta).
- Pages outside the repo go in `target="_blank" rel="noopener"`.

Speaker notes live in the JSON `<script id="speaker-notes">` and pair to
slides by index. Keep the array length matching the slide count.
