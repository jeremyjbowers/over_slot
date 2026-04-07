#!/usr/bin/env node
/**
 * Disposable Monte Carlo: White Sox @ pick 1 vs Roch Cholowsky + top-3 floor.
 * Runs the real draftboard/js/draft.js under JSDOM (sync timers), first 3 AI picks only.
 *
 * One-time: cd draftboard/scripts && npm install
 * Run: node disposable-monte-carlo-cholowsky.mjs [iterations]
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { JSDOM } from 'jsdom';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DRAFTBOARD_ROOT = path.join(__dirname, '..');

const ITERATIONS = Math.max(1, parseInt(process.argv[2] || '2500', 10) || 2500);

const MINIMAL_HTML = `<!doctype html>
<html><head><meta charset="utf-8"></head>
<body class="bg-overslot-black">
  <main>
    <section id="setup">
      <div id="human-teams">
        <div id="draft-money-primer">
          <button type="button" id="btn-draft-money-read-more">Read more</button>
        </div>
      </div>
      <div>
        <button type="button" id="btn-pace-0.5" class="pace-btn" data-ms="500">0.5</button>
        <button type="button" id="btn-pace-1" class="pace-btn selected" data-ms="1000">1</button>
        <button type="button" id="btn-pace-2" class="pace-btn" data-ms="2000">2</button>
        <button type="button" id="btn-pace-5" class="pace-btn" data-ms="5000">5</button>
      </div>
      <button id="btn-start" type="button">Start</button>
    </section>
    <section id="draft" class="hidden">
      <div id="draft-complete" class="hidden"><div id="draft-complete-inner"></div></div>
      <div id="draft-body">
        <div>
          <div id="round-breadcrumbs" class="hidden"></div>
          <div id="board"></div>
          <div id="status"></div>
          <button type="button" id="btn-simulate-rest" class="hidden">Sim</button>
          <button type="button" id="btn-pause" class="hidden">Pause</button>
          <button type="button" id="btn-resume" class="hidden">Resume</button>
          <button type="button" id="btn-restart" class="hidden">Restart</button>
        </div>
        <div id="draft-side">
          <div id="human-budget-summary" class="hidden"></div>
          <div id="pick-panel">
            <div id="ai-reasoning" class="hidden">
              <div id="ai-reasoning-team" class="hidden"></div>
              <div id="ai-reasoning-text"></div>
            </div>
            <div id="current-pick" class="hidden">
              <div id="mobile-pick-sheet-handle"></div>
              <div>
                <div id="pick-header-area"></div>
                <button id="btn-skip" type="button">Skip</button>
                <button id="btn-show-highest" type="button" data-mode="highestRanked">Ranked</button>
                <button id="btn-show-bestfit" type="button" data-mode="bestFit">Best fit</button>
                <input type="text" id="player-filter" />
                <div id="player-list-label"></div>
                <div id="available-players"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </main>
  <div id="modal-draft-money" class="hidden">
    <div id="modal-draft-money-backdrop"></div>
    <button type="button" id="modal-draft-money-close">Close</button>
  </div>
</body></html>`;

function readFirstThreePicks(window) {
  const board = window.document.getElementById('board');
  const rows = [...board.querySelectorAll('[data-pick-index]')].sort(
    (a, b) => Number(a.dataset.pickIndex) - Number(b.dataset.pickIndex)
  );
  const top = rows.slice(0, 3);
  return top.map(r => {
    const slotEl = r.querySelector('.w-10');
    const teamEl = r.querySelector('.col-team');
    const playerEl = r.querySelector('.col-player');
    const overall = slotEl ? parseInt(slotEl.textContent.trim(), 10) : NaN;
    const team = teamEl ? teamEl.textContent.replace(/\s+/g, ' ').trim() : '';
    const player = playerEl ? playerEl.textContent.replace(/\s+/g, ' ').trim() : '';
    return { overall, team, player };
  });
}

function wilsonCI(successes, n, z = 1.96) {
  if (n === 0) return { low: 0, high: 1 };
  const p = successes / n;
  const denom = 1 + z ** 2 / n;
  const center = (p + z ** 2 / (2 * n)) / denom;
  const margin =
    (z / denom) * Math.sqrt((p * (1 - p)) / n + z ** 2 / (4 * n ** 2));
  return { low: Math.max(0, center - margin), high: Math.min(1, center + margin) };
}

function main() {
  const dataCode = fs.readFileSync(path.join(DRAFTBOARD_ROOT, 'js/data.js'), 'utf8');
  const draftCode = fs.readFileSync(path.join(DRAFTBOARD_ROOT, 'js/draft.js'), 'utf8');

  const dom = new JSDOM(MINIMAL_HTML, {
    url: 'http://localhost/mock-draft/',
    pretendToBeVisual: true,
    runScripts: 'dangerously'
  });
  const { window } = dom;

  window.Element.prototype.scrollIntoView = function () {};
  window.HTMLElement.prototype.scrollIntoView = function () {};

  window.matchMedia = (q) => ({
    matches: String(q).includes('min-width: 1024px'),
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {}
  });

  window.requestAnimationFrame = (fn) => {
    try {
      fn();
    } catch (e) {
      console.error(e);
    }
    return 0;
  };

  const timeoutQueue = [];

  window.setTimeout = (fn) => {
    timeoutQueue.push(fn);
    return timeoutQueue.length;
  };
  window.clearTimeout = () => {};

  function filledSlotsInFirstThree(window) {
    const board = window.document.getElementById('board');
    const rows = [...board.querySelectorAll('[data-pick-index]')].sort(
      (a, b) => Number(a.dataset.pickIndex) - Number(b.dataset.pickIndex)
    );
    return rows.slice(0, 3).filter((r) => {
      const p = r.querySelector('.col-player');
      const t = p ? p.textContent.replace(/\s+/g, ' ').trim() : '';
      return t && t !== '--' && !/^—/.test(t);
    }).length;
  }

  /** Run queued timeouts until the first three overall picks show a player (not placeholder). */
  function drainUntilThreePicks() {
    let guard = 0;
    const maxSteps = 50000;
    while (timeoutQueue.length && filledSlotsInFirstThree(window) < 3 && guard < maxSteps) {
      timeoutQueue.shift()();
      guard++;
    }
    timeoutQueue.length = 0;
    if (guard >= maxSteps) {
      throw new Error('drainUntilThreePicks: exceeded maxSteps (possible runaway setTimeout loop)');
    }
  }

  const dataScript = window.document.createElement('script');
  dataScript.textContent = dataCode;
  window.document.body.appendChild(dataScript);

  const draftScript = window.document.createElement('script');
  draftScript.textContent = draftCode;
  window.document.body.appendChild(draftScript);

  const start = window.document.getElementById('btn-start');
  const restart = window.document.getElementById('btn-restart');

  let soxCholowskyAt1 = 0;
  let cholowskyOverallSlots = [];
  let failuresPast3 = 0;

  for (let i = 0; i < ITERATIONS; i++) {
    if (i === 0) {
      start.click();
    } else {
      restart.click();
      start.click();
    }
    drainUntilThreePicks();

    const picks = readFirstThreePicks(window);
    const p0 = picks[0];
    if (p0 && p0.team.includes('White Sox') && p0.player.includes('Cholowsky')) {
      soxCholowskyAt1++;
    }

    const idx = picks.findIndex((p) => p.player.includes('Cholowsky'));
    if (idx < 0) {
      failuresPast3++;
      cholowskyOverallSlots.push(null);
    } else {
      cholowskyOverallSlots.push(picks[idx].overall);
      if (!Number.isFinite(picks[idx].overall) || picks[idx].overall > 3) {
        failuresPast3++;
      }
    }
  }

  const pHat = soxCholowskyAt1 / ITERATIONS;
  const ci = wilsonCI(soxCholowskyAt1, ITERATIONS);

  const slotCounts = {};
  for (const s of cholowskyOverallSlots) {
    const key = s == null ? 'not-in-top-3' : String(s);
    slotCounts[key] = (slotCounts[key] || 0) + 1;
  }

  console.log(`Iterations: ${ITERATIONS}`);
  console.log(
    `White Sox take Roch Cholowsky at overall pick 1: ${soxCholowskyAt1} / ${ITERATIONS} (${(pHat * 100).toFixed(2)}%)`
  );
  console.log(
    `Wilson 95% CI for P(Sox @1): [${(ci.low * 100).toFixed(2)}%, ${(ci.high * 100).toFixed(2)}%] (expect ~85%)`
  );
  console.log(`Cholowsky draft position (overall slot among first 3 picks):`);
  console.log(slotCounts);
  console.log(
    failuresPast3 === 0
      ? 'OK: Cholowsky always appeared by overall pick 3 in this harness.'
      : `WARNING: ${failuresPast3} runs where Cholowsky was missing or listed past pick 3.`
  );
}

main();
