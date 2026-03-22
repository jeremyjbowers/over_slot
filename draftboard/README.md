# Mock Draft Simulator

A client-side MLB-style mock draft simulator. No server required for gameplay—all data is embedded. Terminal/ASCII aesthetic.

## Setup

1. **Build data** (parses CSVs into `js/data.js`):
   ```bash
   node build-data.js
   ```

2. **Serve locally** (required—browsers block loading local files):
   ```bash
   npx serve -l 8000 .
   # or: python -m http.server 8000
   ```

3. Open `http://localhost:8000` in a browser.

## How to Play

- **Human teams**: Select one or more teams (Ctrl/Cmd+click) to control. Other teams are AI.
- **Pace**: Delay between AI picks—choose 0.5 sec, 1 sec (default), 2 sec, or 5 sec.
- **START DRAFT**: Begins the draft. Human picks have no timer; choose a player and click to select.
- **SKIP**: Let the AI pick the best available for your slot.
- **Filter**: Type in the search box to narrow the player list.
- **Click past picks**: Click any completed pick on the board to re-read the quote and rationale.
- **Pause**: During AI picks, click Pause to stop the auto-advance. Review the board, click past picks to see rationale, then Resume to continue.

## Rules

- Each pick has a **slot value**—the maximum you can spend.
- **Rounds 1–3**: Teams cannot spend less than 75% of slot (MLB Combine rule). Players below that minimum are not available.
- **College in Comp A, Round 2, Round 3**: College players sign at slot or slightly under (60% at slot, 40% with 1–3% discount). Preps continue to sign for over slot.
- Player costs: college seniors minimum $150k, high school minimum $400k.
- AI teams follow their draft rules (from `data/mock_draft_sim_team_rules.csv`) when applicable, always respecting slot value.

## Data Files

- `data/mock_draft_sim_players_cost.csv` — Players and costs
- `data/mock_draft_sim_team_rules.csv` — Teams and draft tendencies
- `data/mock_draft_sim_pick_order.csv` — Pick order and slot values
