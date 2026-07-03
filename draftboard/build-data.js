#!/usr/bin/env node
/**
 * Build script: parses CSV data files and outputs js/data.js for client-side use.
 * Run: node build-data.js
 */

const fs = require('fs');
const path = require('path');

function parseCSV(content) {
  const rows = [];
  let currentRow = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < content.length; i++) {
    const c = content[i];
    if (c === '"') {
      if (inQuotes && content[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (c === ',' && !inQuotes) {
      currentRow.push(current.trim());
      current = '';
    } else if ((c === '\n' || c === '\r') && !inQuotes) {
      if (c === '\r' && content[i + 1] === '\n') i++;
      currentRow.push(current.trim());
      current = '';
      if (currentRow.length > 0 && currentRow.some(cell => cell !== '')) {
        rows.push(currentRow);
      }
      currentRow = [];
    } else {
      current += c;
    }
  }
  currentRow.push(current.trim());
  if (currentRow.length > 0 && currentRow.some(cell => cell !== '')) {
    rows.push(currentRow);
  }
  if (rows.length === 0) return [];
  const headers = rows[0];
  return rows.slice(1).map(row => {
    const obj = {};
    headers.forEach((h, i) => { obj[h] = row[i] ?? ''; });
    return obj;
  });
}

/**
 * Parse currency from CSV cells. Ignores non-money decimals and small bare integers
 * (e.g. stray "21.2" or "20" in a money field) so they don’t become bogus bonuses.
 */
function parseDollar(str) {
  if (!str || typeof str !== 'string') return 0;
  const trimmed = str.trim();
  if (!trimmed) return 0;
  const hasDollar = trimmed.includes('$');
  const cleaned = trimmed.replace(/[$,\s]/g, '');
  if (!cleaned) return 0;
  // Small-number decimals are not bonus amounts in this sheet.
  if (/^\d{1,2}\.\d+$/.test(cleaned)) return 0;
  const asFloat = parseFloat(cleaned);
  if (!Number.isFinite(asFloat) || asFloat <= 0) return 0;
  const n = Math.round(asFloat);
  if (!hasDollar && n < 10000) return 0;
  return n;
}

const dataDir = path.join(__dirname, 'data');
const outDir = path.join(__dirname, 'js');
const djangoStaticJsDir = path.join(__dirname, '..', 'overslot', 'static', 'mock_draft', 'js');
// List ranks at/after this with no Player Cost / Note → senior-sign default (sync with draft.js LATE_BOARD_SENIOR_SIGN_RANK_MIN).
const LATE_BOARD_SENIOR_SIGN_RANK_MIN = 300;
const LATE_BOARD_SENIOR_SIGN_AMOUNT = 150000;
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
if (!fs.existsSync(djangoStaticJsDir)) fs.mkdirSync(djangoStaticJsDir, { recursive: true });

// Parse players
const playersCsv = fs.readFileSync(path.join(dataDir, 'mock_draft_sim_players_cost.csv'), 'utf8');
const playersRaw = parseCSV(playersCsv);
const players = playersRaw.map((row, idx) => {
  let rank = parseInt(row.Rank, 10) || idx + 1;
  let cost = parseDollar(row['Player Cost']) || parseDollar(row['Player Cost Note']);
  if (!cost) {
    cost =
      rank >= LATE_BOARD_SENIOR_SIGN_RANK_MIN
        ? LATE_BOARD_SENIOR_SIGN_AMOUNT
        : row.Class === 'H'
          ? 400000
          : 150000;
  }
  return {
    rank,
    name: row.Player || '',
    position: row.Position || '',
    school: row.School || '',
    class: row.Class || 'C',
    cost,
    photoUrl: (row.Photo_Url || '').trim() || null
  };
});

// Parse team IDs (MLB team IDs for logos, API, etc.)
const teamIdsCsv = fs.readFileSync(path.join(dataDir, 'mock_draft_sim_team_ids.csv'), 'utf8');
const teamIdsRaw = parseCSV(teamIdsCsv);
const teamNameToId = {};
teamIdsRaw.forEach(row => {
  const id = parseInt(row.Team_ID, 10);
  const name = (row.Team_Name || '').trim();
  if (id && name) teamNameToId[name] = id;
});
teamNameToId['Athletics'] = teamNameToId['Oakland Athletics'] || 133;

// Parse teams
const teamsCsv = fs.readFileSync(path.join(dataDir, 'mock_draft_sim_team_rules_updated.csv'), 'utf8');
const teamsRaw = parseCSV(teamsCsv);
const teams = teamsRaw.map(row => {
  const name = row.team || '';
  return {
    name,
    id: teamNameToId[name] || null,
    pool: parseDollar(row.pool || ''),
    rules: (row.rules || '').trim()
  };
});

// Parse picks (first 10 rounds only - 30 teams * 10 = 300 picks, but pick order varies)
const picksCsv = fs.readFileSync(path.join(dataDir, 'mock_draft_sim_pick_order.csv'), 'utf8');
const picksRaw = parseCSV(picksCsv);
let prevRound = '';
let sectionIndex = 0;
const allPicks = picksRaw.map(row => {
  const label = (row.round_label || '').trim();
  if (label && label !== prevRound) {
    prevRound = label;
    sectionIndex++;
  }
  const team = (row.team || '').replace(/white Sox/i, 'White Sox');
  return {
    pick: parseInt(row.pick, 10),
    team,
    teamId: teamNameToId[team] || null,
    value: parseDollar(row.value),
    round: label,
    roundSectionIndex: sectionIndex
  };
});

const picks = allPicks;

/** Bump when pick order, teams, or player list changes so shared URLs stay consistent. */
const DRAFT_DATA_VERSION = 1;

const output = `/**
 * Draft simulator data - generated by build-data.js
 * Do not edit manually.
 */
const DRAFT_DATA = {
  version: ${DRAFT_DATA_VERSION},
  players: ${JSON.stringify(players, null, 0)},
  teams: ${JSON.stringify(teams, null, 0)},
  picks: ${JSON.stringify(picks, null, 0)}
};
`;

fs.writeFileSync(path.join(outDir, 'data.js'), output);
fs.writeFileSync(path.join(djangoStaticJsDir, 'data.js'), output);
const djangoStaticCssDir = path.join(__dirname, '..', 'overslot', 'static', 'mock_draft', 'css');
if (!fs.existsSync(djangoStaticCssDir)) fs.mkdirSync(djangoStaticCssDir, { recursive: true });
fs.copyFileSync(path.join(__dirname, 'js', 'draft.js'), path.join(djangoStaticJsDir, 'draft.js'));
fs.copyFileSync(path.join(__dirname, 'css', 'draft.css'), path.join(djangoStaticCssDir, 'draft.css'));
console.log('Generated data.js → draftboard/js/ and overslot/static/mock_draft/js/');
console.log('Synced draft.js + draft.css → overslot/static/mock_draft/');
console.log('Site /my-mock-draft/: template loads {% static \'mock_draft/css/draft.css\' %} + {% static \'mock_draft/js/data.js\' %}; run collectstatic (or dev STATICFILES_DIRS) after this.');
console.log('  -', players.length, 'players');
console.log('  -', teams.length, 'teams');
console.log('  -', picks.length, 'picks');
