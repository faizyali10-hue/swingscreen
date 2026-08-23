# Nifty Swing Screener — Scheduled + Static Web Page

A daily-scheduled screener that runs on GitHub's servers (free), writes results
to a JSON file, and serves them on a static web page via GitHub Pages. No CORS
proxy, no live browser API calls, no ongoing cost.

## How it works

```
GitHub Actions (runs 4pm IST, Mon-Fri)
        │
        ▼
  rsi_screener.py  ──►  docs/results.json  ──►  committed back to repo
                                                         │
                                                         ▼
                                          GitHub Pages serves docs/index.html
                                          which fetches ./results.json
                                          (same-origin, no CORS issue at all)
```

## Setup (10 minutes, one-time)

### 1. Create a GitHub repo
- Go to github.com → New repository (can be public or private)
- Note: if private, GitHub Pages requires a paid plan for private repos with Pages —
  use a public repo unless you have GitHub Pro/Team/Enterprise.

### 2. Upload these files
Push this entire folder structure to the repo root:
```
your-repo/
├── rsi_screener.py
├── requirements.txt
├── nifty500_tickers.csv
├── .github/
│   └── workflows/
│       └── screener.yml
└── docs/
    ├── index.html
    └── results.json
```

If using git locally:
```bash
cd your-repo
git init
git add .
git commit -m "Initial screener setup"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 3. Get the full Nifty 500 list
The included CSV only has ~50 starter tickers. Download the official list from
niftyindices.com (Indices → Nifty 500 → Downloads), append `.NS` to every
symbol, and replace `nifty500_tickers.csv` — keep the `Symbol` column header.

### 4. Enable GitHub Pages
- Repo → Settings → Pages
- Source: "Deploy from a branch"
- Branch: `main`, folder: `/docs`
- Save. Your site will be live at `https://YOUR_USERNAME.github.io/YOUR_REPO/`
  within a minute or two.

### 5. Run the screener for the first time
- Repo → Actions tab → "Daily RSI Screener" workflow → "Run workflow" button
  (this is the `workflow_dispatch` trigger — lets you run it manually instead
  of waiting for the schedule)
- Takes a few minutes depending on how many tickers are in your CSV
- Once it finishes, `docs/results.json` will be updated and committed automatically
- Refresh your GitHub Pages URL — results should now show

### 6. It now runs itself
The workflow is scheduled for `30 10 * * 1-5` (UTC) = 4:00 PM IST, Monday–Friday,
after the NSE closes at 3:30 PM IST. Every day it re-scans your full universe and
updates the page automatically — nothing to run manually going forward.

## Tuning
Edit the config constants at the top of `rsi_screener.py`:
- `RSI_ENTRY_TRIGGER`, `WEEKLY_RSI_MIN`, `RSI_OVERSOLD_FLOOR`
- `EMA_TREND`, `EMA_FAST`
- `MIN_AVG_TURNOVER_CR`

Commit and push changes — the next scheduled run (or a manual "Run workflow")
will pick them up. The current settings are also displayed on the page itself
so you always know what filters produced the results you're looking at.

## Notes
- GitHub Actions free tier gives you 2,000 minutes/month on public repos (unlimited,
  actually, for public repos) — a daily scan of 500 tickers takes a few minutes,
  well within any reasonable usage.
- If a run fails (e.g., Yahoo Finance rate-limits the runner), check the Actions
  tab for logs. Rerunning manually usually resolves transient failures.
- Want intraday updates instead of once a day? Just add more cron entries in
  `screener.yml`, e.g. add a second `- cron: '00 6 * * 1-5'` line for an
  additional run at 11:30 AM IST.
