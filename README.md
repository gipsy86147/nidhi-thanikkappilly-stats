# Nidhi Thanikkappilly Stats (GitHub Pages)

This repo scrapes and publishes Nidhi Thanikkappilly competition stats from:

- https://www.hipenta.com/live/events/46b72a21-cef6-4404-a527-6618600bf67f/categories/e6889cfc-828c-4792-82e2-c6fb8980b624/result
- https://www.hipenta.com/live/events/f14078fe-cd99-4f90-b2c2-994adeb4293e/categories/b2e43a82-0ae8-446c-a926-2f67312d4235/result
- https://pentathlonscore.com/

## Regenerate Data

```bash
python3 scripts/scrape_nidhi_stats.py
```

This writes `docs/data/nidhi_stats.json`.

## Local Preview

```bash
cd docs
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

## GitHub Pages

This site is intended to be served from `main` branch and `/docs` folder.
