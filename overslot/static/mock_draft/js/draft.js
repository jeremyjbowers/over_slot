/**
 * Mock Draft Simulator - client-side only, no server
 */

(function () {
  'use strict';

  const MIN_COLLEGE = 150000;
  const MIN_HS = 400000;
  /** Random senior sign amount and per-future-pick reserve (no pass picks — always sign someone). */
  const RANDOM_SENIOR_SIGN = 150000;
  const MIN_SLOT_PCT_TOP3 = 0.75; // First 3 rounds: teams cannot spend less than 75% of slot (MLB Combine rule)
  /** After Round 2 ends: chance that 1–3 top remaining HS players “go to college” and leave the pool. */
  const HS_GTC_AFTER_R2_CHANCE = 0.08;

  const TEAM_LOGO_BASE = 'https://www.mlbstatic.com/team-logos/team-cap-on-dark';
  const TEAM_LOGO_PLACEHOLDER = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="w-5 h-5 text-neutral-300"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>';

  /**
   * Share URLs: primary <code>/my-mock-draft/&lt;uuid&gt;/</code> (DB); legacy
   * <code>/my-mock-draft/s/&lt;base64url&gt;/</code>. No <code>?</code> or <code>#</code> on primary links
   * so iMessage keeps one tappable URL. Legacy query/hash still work.
   */
  const MOCK_DRAFT_CANONICAL_ORIGIN = 'https://overslotbaseball.com';
  const MOCK_DRAFT_UUID_PATH =
    /^\/my-mock-draft\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/?$/i;

  /** Single in-flight POST to save share; copy/address bar wait on this so URLs use UUID, not /s/… payload. */
  let sharePersistPromise = null;

  function isDraftCompleteForShare() {
    return state.currentPickIndex >= state.picks.length;
  }

  function getCsrfToken() {
    const m = typeof document !== 'undefined' && document.cookie
      ? document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
      : null;
    return m ? decodeURIComponent(m[1]) : '';
  }

  function parseUuidFromMockDraftPath() {
    const m = location.pathname.match(MOCK_DRAFT_UUID_PATH);
    return m ? m[1] : null;
  }

  function getMockDraftHomePath() {
    const m = location.pathname.match(
      /^(\/my-mock-draft)(?:\/s\/[^/]+|\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?\/?$/i
    );
    if (m) return m[1];
    return '/my-mock-draft';
  }

  function onMockDraftSimulatorPage() {
    return /^\/my-mock-draft/.test(location.pathname);
  }

  /** Public tool entry (no share payload) for brag cards and off-site fallbacks. */
  function getMockDraftToolHomeUrl() {
    if (onMockDraftSimulatorPage()) {
      return `${location.origin}${getMockDraftHomePath()}/`;
    }
    return `${MOCK_DRAFT_CANONICAL_ORIGIN}${getMockDraftHomePath()}/`;
  }

  function extractEndgamePayloadRaw() {
    if (typeof window.__MOCK_DRAFT_SHARE_PAYLOAD_B64__ === 'string' && window.__MOCK_DRAFT_SHARE_PAYLOAD_B64__.length) {
      return window.__MOCK_DRAFT_SHARE_PAYLOAD_B64__;
    }
    const pathM = location.pathname.match(/\/my-mock-draft\/s\/([^/]+)\/?$/);
    if (pathM) return pathM[1];

    if (location.hash && location.hash.startsWith('#d=')) {
      return location.hash.slice(3);
    }
    const q = location.search;
    if (!q || q === '?') return null;
    const body = q.slice(1);
    if (!body.includes('=')) {
      return body;
    }
    if (body.startsWith('d=') && body.indexOf('&') === -1) {
      return body.slice(2);
    }
    const params = new URLSearchParams(q);
    const d = params.get('d');
    return d || null;
  }

  function normalizePathname(p) {
    return (p || '').replace(/\/+$/, '') || '/';
  }

  function getShareableDraftUrl() {
    const home = getMockDraftHomePath();
    const uuid =
      parseUuidFromMockDraftPath() ||
      (typeof window.__MOCK_DRAFT_SHARE_UUID__ === 'string' && window.__MOCK_DRAFT_SHARE_UUID__.length
        ? window.__MOCK_DRAFT_SHARE_UUID__
        : null);
    if (uuid) {
      const sharePath = `${home}/${uuid}/`;
      if (onMockDraftSimulatorPage()) return `${location.origin}${sharePath}`;
      return `${MOCK_DRAFT_CANONICAL_ORIGIN}${sharePath}`;
    }
    const raw = extractEndgamePayloadRaw();
    if (!raw) {
      if (onMockDraftSimulatorPage()) return `${location.origin}${home}/`;
      return `${MOCK_DRAFT_CANONICAL_ORIGIN}${home}/`;
    }
    const sharePath = `${home}/s/${raw}/`;
    if (onMockDraftSimulatorPage()) return `${location.origin}${sharePath}`;
    return `${MOCK_DRAFT_CANONICAL_ORIGIN}${sharePath}`;
  }

  function teamLogoHtml(teamId, sizeClass = 'w-8 h-8') {
    if (!teamId) return '';
    const url = `${TEAM_LOGO_BASE}/${teamId}.svg`;
    return `<img src="${url}" alt="" class="${sizeClass} flex-shrink-0 object-contain align-middle" onerror="this.style.display='none'">`;
  }

  const WEIRD_LEVELS = { default: 0.03, more: 0.16, crazy: 0.40 };

  let state = {
    players: [],
    teams: [],
    picks: [],
    humanTeams: new Set(),
    /** Teams the user selected as human at Start Draft (persists if Simulate to end clears `humanTeams`). */
    originalHumanTeams: new Set(),
    pickDelay: 1000,
    weirdPickChance: WEIRD_LEVELS.default,
    currentPickIndex: 0,
    drafted: new Set(), // player rank
    /** HS players who left the pool (enrolled in college); same effect as drafted for availability. */
    hsGoToCollege: new Set(),
    _hsGtcAppliedThisDraft: false,
    _draftNewsFlash: '',
    boardRows: [],
    visibleRound: 1,
    pickIndexToRow: {}, // pickIndex -> { row, roundEl }
    teamSpent: {}, // teamName -> total spent
    teamPicks: {}, // teamName -> [{ name, cost }]
    topViewMode: 'bestFit', // 'bestFit' | 'highestRanked'
    _topViewRefresh: null, // set by showHumanPickUI
    pickRationales: {}, // pickIndex -> { reason, player, weirdEvent, isHuman }
    paused: false,
    _pickTimeoutId: null,
    _pendingAdvance: null, // { pick, result, row } when paused during AI pick
    _pickDelayBeforeSim: null, // restored when simulated draft completes or restarts
    /** After draft: which endgame tab is active. */
    endgameTab: 'my', // 'my' | 'team' | 'browse'
    endgameTeamChoice: null, // string | null — "Any team" brag sheet
    endgameBrowseIndex: 0 // pick index in state.picks
  };

  function resetPhraseEntropy() {
    state._phraseRecent = {};
  }

  /**
   * Pick from a phrase pool while avoiding recent repeats (rolling window).
   * Scales with pool size so we never exclude every option.
   */
  function pickVaried(arr, bucketKey) {
    if (!arr || arr.length === 0) return '';
    if (!state._phraseRecent) state._phraseRecent = {};
    let recent = state._phraseRecent[bucketKey];
    if (!recent) recent = state._phraseRecent[bucketKey] = [];
    const maxRecent = arr.length <= 1 ? 0 : Math.min(56, arr.length - 1);
    const tail = maxRecent > 0 ? recent.slice(-maxRecent) : [];
    const candidates = maxRecent === 0 ? arr : arr.filter(x => !tail.includes(x));
    const pool = candidates.length ? candidates : arr;
    const choice = pool[Math.floor(Math.random() * pool.length)];
    recent.push(choice);
    if (recent.length > 140) recent.splice(0, recent.length - 70);
    return choice;
  }

  const $ = id => document.getElementById(id);
  const $setup = $('setup');
  const $draft = $('draft');
  const $board = $('board');
  const $currentPick = $('current-pick');
  const $aiReasoning = $('ai-reasoning');
  const $availablePlayers = $('available-players');
  const $status = $('status');
  const $btnStart = $('btn-start');
  const $btnSkip = $('btn-skip');
  const $btnPause = $('btn-pause');
  const $btnResume = $('btn-resume');
  const $btnRestart = $('btn-restart');
  const $btnSimulateRest = $('btn-simulate-rest');
  const $draftSide = $('draft-side');
  const $draftComplete = $('draft-complete');
  const $draftCompleteInner = $('draft-complete-inner');

  function fmt(n) {
    if (n >= 1000000) return '$' + (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return '$' + (n / 1000).toFixed(0) + 'k';
    return '$' + n;
  }

  function init() {
    if (typeof DRAFT_DATA === 'undefined') {
      removeEndgamePendingClass();
      $status.textContent = 'Error: data.js not loaded. Run: node build-data.js';
      return;
    }
    state.players = DRAFT_DATA.players;
    state.teams = DRAFT_DATA.teams;
    state.picks = DRAFT_DATA.picks;

    const container = $('human-teams');
    container.querySelectorAll('.team-square').forEach(el => el.remove());
    [...state.teams].sort((a, b) => a.name.localeCompare(b.name)).forEach(t => {
      const pickCount = state.picks.filter(p => p.team === t.name).length;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'team-square px-3 py-2 border border-overslot-grey-border bg-overslot-grey text-white text-sm font-medium hover:border-red-500/50 transition-colors flex items-center gap-2 text-left';
      btn.innerHTML = `${teamLogoHtml(t.id, 'w-8 h-8')}<span class="flex flex-col gap-0.5 min-w-0"><span class="break-words">${escapeHtml(t.name)}</span><span class="text-xs text-neutral-100 font-normal">${pickCount} pick${pickCount !== 1 ? 's' : ''}</span></span>`;
      btn.dataset.team = t.name;
      btn.addEventListener('click', () => {
        container.querySelectorAll('.team-square.selected').forEach(el => el.classList.remove('selected'));
        btn.classList.add('selected');
      });
      container.appendChild(btn);
    });

    $btnStart.addEventListener('click', startDraft);
    $btnRestart?.addEventListener('click', restartToSetup);
    $btnSimulateRest?.addEventListener('click', simulateRestOfDraft);
    $btnSkip.addEventListener('click', () => makeHumanPick(null));

    function updateWeirdButtons() {
      const level = state.weirdPickChance === WEIRD_LEVELS.default ? 'default' : state.weirdPickChance === WEIRD_LEVELS.more ? 'more' : 'crazy';
      document.querySelectorAll('.weird-btn').forEach(btn => {
        btn.classList.toggle('selected', btn.dataset.level === level);
      });
    }
    $('btn-weird-default')?.addEventListener('click', () => { state.weirdPickChance = WEIRD_LEVELS.default; updateWeirdButtons(); });
    $('btn-weird-more')?.addEventListener('click', () => { state.weirdPickChance = WEIRD_LEVELS.more; updateWeirdButtons(); });
    $('btn-weird-crazy')?.addEventListener('click', () => { state.weirdPickChance = WEIRD_LEVELS.crazy; updateWeirdButtons(); });
    updateWeirdButtons();

    function updatePaceButtons() {
      document.querySelectorAll('.pace-btn').forEach(btn => {
        btn.classList.toggle('selected', btn.dataset.ms === String(state.pickDelay));
      });
    }
    document.querySelectorAll('.pace-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        state.pickDelay = parseInt(btn.dataset.ms, 10);
        updatePaceButtons();
      });
    });
    updatePaceButtons();

    const $modalDraftMoney = $('modal-draft-money');
    const $modalDraftMoneyClose = $('modal-draft-money-close');
    const $modalDraftMoneyBackdrop = $('modal-draft-money-backdrop');
    let draftMoneyModalPreviousFocus = null;

    function openDraftMoneyModal() {
      draftMoneyModalPreviousFocus = document.activeElement;
      if ($modalDraftMoney) $modalDraftMoney.classList.remove('hidden');
      $setup?.classList.add('overflow-hidden');
      $modalDraftMoneyClose?.focus();
    }

    function closeDraftMoneyModal() {
      if ($modalDraftMoney) $modalDraftMoney.classList.add('hidden');
      $setup?.classList.remove('overflow-hidden');
      const prev = draftMoneyModalPreviousFocus;
      draftMoneyModalPreviousFocus = null;
      if (prev && typeof prev.focus === 'function') prev.focus();
    }

    $('btn-draft-money-read-more')?.addEventListener('click', openDraftMoneyModal);
    $modalDraftMoneyClose?.addEventListener('click', closeDraftMoneyModal);
    $modalDraftMoneyBackdrop?.addEventListener('click', closeDraftMoneyModal);
    document.addEventListener('keydown', e => {
      if (e.key !== 'Escape') return;
      if (!$modalDraftMoney || $modalDraftMoney.classList.contains('hidden')) return;
      closeDraftMoneyModal();
    });

    $board.addEventListener('click', (e) => {
      const row = e.target.closest('.board-row.past-pick');
      if (!row) return;
      const pickIndex = parseInt(row.dataset.pickIndex, 10);
      const draftDone = state.currentPickIndex >= state.picks.length;
      if (draftDone && $draftComplete && !$draftComplete.classList.contains('hidden')) {
        state.endgameTab = 'browse';
        state.endgameBrowseIndex = pickIndex;
        renderEndgame();
        requestAnimationFrame(() => {
          $draftComplete?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
        return;
      }
      const r = state.pickRationales[pickIndex];
      if (r) showPastPickRationale(pickIndex, r);
    });

    document.addEventListener('keydown', e => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      if (!$draftComplete || $draftComplete.classList.contains('hidden')) return;
      if (state.endgameTab !== 'browse') return;
      const tag = e.target && e.target.tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      e.preventDefault();
      const n = state.picks.length;
      if (!n) return;
      if (e.key === 'ArrowLeft') {
        state.endgameBrowseIndex = Math.max(0, state.endgameBrowseIndex - 1);
      } else {
        state.endgameBrowseIndex = Math.min(n - 1, state.endgameBrowseIndex + 1);
      }
      const rowEl = $draftCompleteInner?.querySelector(`[data-endgame-browse-row="${state.endgameBrowseIndex}"]`);
      rowEl?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });

    $btnPause?.addEventListener('click', () => {
      state.paused = true;
      if (state._pickTimeoutId) {
        clearTimeout(state._pickTimeoutId);
        state._pickTimeoutId = null;
      }
      updatePauseButtonUI();
      $status.textContent = 'Paused. Click Resume to continue.';
    });
    $btnResume?.addEventListener('click', () => {
      state.paused = false;
      updatePauseButtonUI();
      if (state._pendingAdvance) {
        const { pick, result, row, effectiveCost } = state._pendingAdvance;
        state._pendingAdvance = null;
        if ($aiReasoning) {
          $aiReasoning.classList.remove('weird-event');
          $aiReasoning.querySelector('.weird-event-label')?.classList.add('hidden');
        }
        recordPick(pick, result.player, row, result.reason, { weirdEvent: result.weirdEvent, isHuman: false, effectiveCost });
        state.currentPickIndex++;
        maybeHsGoToCollegeAfterRound2();
        renderHumanBudgetSummary();
        processNextPick();
      }
    });

    if (tryRestoreEndgameFromUrl()) {
      return;
    }
  }

  function updateSimulateRestButtonUI() {
    const draftActive = $setup.classList.contains('hidden') && !$draft.classList.contains('hidden');
    const draftComplete = state.currentPickIndex >= state.picks.length;
    if (!draftActive || draftComplete) {
      $btnSimulateRest?.classList.add('hidden');
    } else {
      $btnSimulateRest?.classList.remove('hidden');
    }
  }

  function updatePauseButtonUI() {
    const draftActive = $setup.classList.contains('hidden') && !$draft.classList.contains('hidden');
    const isHumanTurn = state.picks[state.currentPickIndex] && state.humanTeams.has(state.picks[state.currentPickIndex].team);
    const draftComplete = state.currentPickIndex >= state.picks.length;
    if (!draftActive || draftComplete) {
      $btnPause?.classList.add('hidden');
      $btnResume?.classList.add('hidden');
    } else if (isHumanTurn) {
      $btnPause?.classList.add('hidden');
      $btnResume?.classList.add('hidden');
    } else if (state.paused) {
      $btnPause?.classList.add('hidden');
      $btnResume?.classList.remove('hidden');
    } else {
      $btnPause?.classList.remove('hidden');
      $btnResume?.classList.add('hidden');
    }
    updateSimulateRestButtonUI();
  }

  function showPastPickRationale(pickIndex, r) {
    const pick = state.picks[pickIndex];
    if (!pick || !$aiReasoning) return;
    const displayCost = r.effectiveCost ?? r.player?.cost;
    let reasonText = r.reason || (r.player ? 'Best player available' : 'Passing');
    if (r.player && pick.value != null) {
      const slotPhrase = getSlotValuePhrase(displayCost, pick.value);
      if (slotPhrase) reasonText = reasonText + (reasonText ? ' ' : '') + slotPhrase;
    }
    const costClass = r.player && pick.value != null
      ? (displayCost > pick.value ? 'text-overslot-red' : displayCost < pick.value ? 'text-green-400' : 'text-white')
      : 'text-white';
    const quotedReason = '"' + escapeHtml(reasonText) + '"';
    $aiReasoning.classList.remove('hidden');
    $aiReasoning.classList.toggle('weird-event', !!r.weirdEvent);
    const badge = $aiReasoning.querySelector('.weird-event-label');
    if (badge) badge.classList.toggle('hidden', !r.weirdEvent);
    const teamEl = $aiReasoning.querySelector('#ai-reasoning-team');
    teamEl.innerHTML = '';
    teamEl.classList.add('hidden');
    const headerContent = r.player
      ? `<div class="flex items-center gap-4 flex-wrap">${teamLogoHtml(pick.teamId, 'w-20 h-20')}<div class="min-w-0 flex-1"><span class="text-white font-semibold text-2xl">#${r.player.rank} ${escapeHtml(r.player.name)} ${escapeHtml(r.player.position)}, ${escapeHtml(r.player.school)}</span> <span class="${costClass} font-medium text-2xl">${fmt(displayCost)}</span></div>${playerPhotoHtml(r.player, 'w-24 h-24', true)}</div>`
      : `<div class="flex items-center gap-4">${teamLogoHtml(pick.teamId, 'w-20 h-20')}<span class="text-neutral-400 text-2xl">Passing</span></div>`;
    const textEl = $aiReasoning.querySelector('#ai-reasoning-text');
    textEl.innerHTML = `<div class="ai-reasoning-pick flex flex-col gap-3">${headerContent}<blockquote class="ai-reasoning-quote text-white text-xl leading-relaxed m-0 border-l-2 border-overslot-red/50 pl-3">${quotedReason}</blockquote></div>`;
    textEl.classList.remove('reasoning-appear');
    textEl.offsetHeight;
    textEl.classList.add('reasoning-appear');
  }

  function getRoundSections() {
    const sections = [];
    let prev = null;
    state.picks.forEach(p => {
      if (p.round && p.round !== prev) {
        sections.push({ label: p.round, index: p.roundSectionIndex });
        prev = p.round;
      }
    });
    return sections;
  }

  /** Compact labels for the top round nav only (full names remain in data and section titles). */
  const ROUND_NAV_SHORT = {
    'Prospect Promotion Incentive': 'PPI',
    'Competitive Balance Round A': 'CB-A',
    'Competitive Balance Round B': 'CB-B',
    'Compensation Pick A': 'CP-A',
    'Compensation Pick B': 'CP-B'
  };

  function shortRoundNavLabel(fullLabel) {
    if (!fullLabel) return '';
    if (ROUND_NAV_SHORT[fullLabel]) return ROUND_NAV_SHORT[fullLabel];
    const m = /^Round (\d+)$/.exec(fullLabel.trim());
    if (m) return 'R' + m[1];
    return fullLabel;
  }

  function getLastPickIndexForRound(roundLabel) {
    let last = -1;
    state.picks.forEach((p, i) => {
      if (p.round === roundLabel) last = i;
    });
    return last;
  }

  function isPlayerSelectableInPool(p) {
    return !state.drafted.has(p.rank) && !state.hsGoToCollege.has(p.rank);
  }

  function consumeDraftNewsFlash() {
    const s = state._draftNewsFlash || '';
    state._draftNewsFlash = '';
    return s;
  }

  /**
   * Once per draft, right after the last Round 2 pick resolves: low chance that 1–3 top
   * remaining HS players commit to school and are removed from the board (not drafted).
   */
  function maybeHsGoToCollegeAfterRound2() {
    const lastR2 = getLastPickIndexForRound('Round 2');
    if (lastR2 < 0) return;
    const justFinished = state.currentPickIndex - 1;
    if (justFinished !== lastR2) return;
    if (state._hsGtcAppliedThisDraft) return;
    state._hsGtcAppliedThisDraft = true;
    if (Math.random() >= HS_GTC_AFTER_R2_CHANCE) return;

    const hs = state.players
      .filter(p => p.class === 'H' && isPlayerSelectableInPool(p))
      .sort((a, b) => a.rank - b.rank);
    if (hs.length === 0) return;

    const n = Math.min(1 + Math.floor(Math.random() * 3), hs.length);
    const chosen = hs.slice(0, n);
    chosen.forEach(p => state.hsGoToCollege.add(p.rank));
    const names = chosen.map(p => p.name).join(', ');
    state._draftNewsFlash = `Commitment news: ${names} ${n === 1 ? 'heads' : 'head'} to college — off the board. `;
  }

  function getPicksForRound(roundLabel) {
    return state.picks
      .map((p, i) => ({ pick: p, index: i }))
      .filter(({ pick }) => pick.round === roundLabel);
  }

  function renderRound(roundLabel) {
    const roundPicks = getPicksForRound(roundLabel);
    if (roundPicks.length === 0) return null;

    const sectionIndex = roundPicks[0].pick.roundSectionIndex;
    const roundEl = document.createElement('div');
    roundEl.className = 'mb-3 p-2 bg-overslot-grey border border-overslot-grey-border overflow-hidden';
    roundEl.dataset.roundSection = String(sectionIndex);
    const h3 = document.createElement('h3');
    h3.className = 'text-sm font-semibold text-overslot-red mb-2';
    h3.textContent = roundLabel;
    roundEl.appendChild(h3);

    const header = document.createElement('div');
    header.className = 'grid grid-cols-[2.5rem_minmax(6rem,1fr)_5rem_minmax(10rem,1fr)_5rem] gap-1.5 py-1 border-b border-overslot-grey-border text-neutral-100 text-xs';
    header.innerHTML = '<span>#</span><span>TEAM</span><span>SLOT</span><span>PLAYER</span><span>COST</span>';
    roundEl.appendChild(header);

    roundPicks.forEach(({ pick, index }) => {
      const row = document.createElement('div');
      row.className = 'board-row flex border-b border-overslot-grey-border';
      row.dataset.pickIndex = String(index);
      const teamLogo = teamLogoHtml(pick.teamId, 'w-6 h-6');
      row.innerHTML = `<div class="w-10 flex-shrink-0 bg-overslot-red flex items-center justify-center text-white font-bold text-sm">${pick.pick}</div><div class="flex-1 min-w-0 grid grid-cols-[minmax(6rem,1fr)_5rem_minmax(10rem,1fr)_5rem] gap-1.5 py-1 px-2 items-center bg-overslot-grey/50 text-sm"><span class="col-team break-words flex items-center gap-1.5">${teamLogo}${escapeHtml(pick.team)}</span><span>${fmt(pick.value)}</span><span class="col-player truncate">--</span><span class="col-cost">--</span></div>`;
      state.boardRows[index] = row;
      state.pickIndexToRow[index] = { row, roundEl };
      roundEl.appendChild(row);
    });

    return roundEl;
  }

  function ensureRoundVisible(roundLabel) {
    const section = getRoundSections().find(s => s.label === roundLabel);
    const sectionIndex = section ? section.index : 0;
    const existing = $board.querySelector(`[data-round-section="${sectionIndex}"]`);
    if (existing) return;
    const roundEl = renderRound(roundLabel);
    if (roundEl) {
      $board.appendChild(roundEl);
      roundEl.scrollIntoView({ behavior: state.pickDelay === 0 ? 'auto' : 'smooth', block: 'nearest' });
    }
  }

  function renderRoundBreadcrumbs() {
    const container = $('round-breadcrumbs');
    if (!container) return;
    container.classList.remove('hidden');
    container.innerHTML = '';
    container.setAttribute('role', 'navigation');
    container.setAttribute('aria-label', 'Jump to draft round');
    const sections = getRoundSections();
    const currentRound = state.currentPickIndex < state.picks.length
      ? state.picks[state.currentPickIndex].round
      : (sections.length ? sections[sections.length - 1].label : '');
    sections.forEach((section, i) => {
      if (i > 0) {
        const sep = document.createElement('span');
        sep.className = 'text-neutral-500 select-none px-0.5';
        sep.textContent = '·';
        sep.setAttribute('aria-hidden', 'true');
        container.appendChild(sep);
      }
      const span = document.createElement('span');
      span.className = (section.label === currentRound
        ? 'text-overslot-red font-semibold underline cursor-default'
        : 'text-neutral-100 hover:text-white cursor-pointer') + ' whitespace-nowrap';
      const shortLabel = shortRoundNavLabel(section.label);
      span.textContent = shortLabel;
      span.title = section.label;
      span.setAttribute('aria-label', section.label);
      span.addEventListener('click', () => {
        ensureRoundVisible(section.label);
        const roundEl = $board.querySelector(`[data-round-section="${section.index}"]`);
        if (roundEl) roundEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      container.appendChild(span);
    });
  }

  function startDraft() {
    clearEndgameStateFromUrl();
    $('modal-draft-money')?.classList.add('hidden');
    $setup?.classList.remove('overflow-hidden');

    const container = $('human-teams');
    state.humanTeams = new Set([...container.querySelectorAll('.team-square.selected')].map(el => el.dataset.team));
    state.originalHumanTeams = new Set([...state.humanTeams]);
    state.currentPickIndex = 0;
    state.drafted = new Set();
    state.hsGoToCollege = new Set();
    state._hsGtcAppliedThisDraft = false;
    state._draftNewsFlash = '';
    state.teamSpent = {};
    state.teamPicks = {};
    state.boardRows = [];
    state.pickIndexToRow = {};
    state.pickRationales = {};
    state.paused = false;
    state._pickTimeoutId = null;
    state._pendingAdvance = null;
    state._pickDelayBeforeSim = null;
    resetPhraseEntropy();
    state.endgameTab = 'my';
    state.endgameTeamChoice = null;
    state.endgameBrowseIndex = 0;
    sharePersistPromise = null;
    try {
      delete window.__MOCK_DRAFT_SHARE_UUID__;
      delete window.__MOCK_DRAFT_SHARE_PAYLOAD_B64__;
    } catch (_) { /* ignore */ }

    $setup.classList.add('hidden');
    $draft.classList.remove('hidden');
    $btnRestart?.classList.remove('hidden');
    if ($draftComplete) {
      $draftComplete.classList.add('hidden');
      if ($draftCompleteInner) $draftCompleteInner.innerHTML = '';
    }
    if ($draftSide) $draftSide.classList.remove('hidden');
    if ($draft) $draft.classList.remove('draft-finished');
    $board.innerHTML = '';
    $('round-breadcrumbs').innerHTML = '';
    $currentPick.classList.add('hidden');
    $status.textContent = '';

    const firstSection = getRoundSections()[0];
    if (firstSection) ensureRoundVisible(firstSection);
    renderRoundBreadcrumbs();
    renderHumanBudgetSummary();
    processNextPick();
  }

  function restorePickDelayAfterSimulate() {
    if (state._pickDelayBeforeSim != null) {
      state.pickDelay = state._pickDelayBeforeSim;
      state._pickDelayBeforeSim = null;
    }
  }

  function simulateRestOfDraft() {
    if ($setup.classList.contains('hidden') === false || $draft.classList.contains('hidden')) return;
    if (state.currentPickIndex >= state.picks.length) return;

    state.paused = false;
    if (state._pickTimeoutId) {
      clearTimeout(state._pickTimeoutId);
      state._pickTimeoutId = null;
    }
    const pending = state._pendingAdvance;
    state._pendingAdvance = null;

    if (state._pickDelayBeforeSim == null) {
      state._pickDelayBeforeSim = state.pickDelay;
    }
    state.pickDelay = 0;

    state.humanTeams = new Set();

    const $budget = $('human-budget-summary');
    if ($budget) {
      $budget.classList.add('hidden');
      $budget.innerHTML = '';
    }

    if (pending) {
      if ($aiReasoning) {
        $aiReasoning.classList.remove('weird-event');
        $aiReasoning.querySelector('.weird-event-label')?.classList.add('hidden');
      }
      recordPick(pending.pick, pending.result.player, pending.row, pending.result.reason, { weirdEvent: pending.result.weirdEvent, isHuman: false, effectiveCost: pending.effectiveCost });
      state.currentPickIndex++;
      maybeHsGoToCollegeAfterRound2();
      renderHumanBudgetSummary();
    }

    $currentPick.classList.add('hidden');
    processNextPick();
  }

  function restartToSetup() {
    clearEndgameStateFromUrl();
    if ($setup.classList.contains('hidden') === false || $draft.classList.contains('hidden')) return;
    if (state._pickTimeoutId) {
      clearTimeout(state._pickTimeoutId);
      state._pickTimeoutId = null;
    }
    state._pendingAdvance = null;
    state.paused = false;
    state.currentPickIndex = 0;
    state.drafted = new Set();
    state.hsGoToCollege = new Set();
    state._hsGtcAppliedThisDraft = false;
    state._draftNewsFlash = '';
    state.teamSpent = {};
    state.teamPicks = {};
    state.boardRows = [];
    state.pickIndexToRow = {};
    state.pickRationales = {};
    state.originalHumanTeams = new Set();
    state.endgameTab = 'my';
    state.endgameTeamChoice = null;
    state.endgameBrowseIndex = 0;
    sharePersistPromise = null;
    try {
      delete window.__MOCK_DRAFT_SHARE_UUID__;
      delete window.__MOCK_DRAFT_SHARE_PAYLOAD_B64__;
    } catch (_) { /* ignore */ }

    $board.innerHTML = '';
    const $crumbs = $('round-breadcrumbs');
    if ($crumbs) {
      $crumbs.innerHTML = '';
      $crumbs.classList.add('hidden');
    }
    $status.textContent = '';
    $status.classList.remove('picking');
    $currentPick.classList.add('hidden');
    $btnPause?.classList.add('hidden');
    $btnResume?.classList.add('hidden');
    $btnRestart?.classList.add('hidden');
    $btnSimulateRest?.classList.add('hidden');
    restorePickDelayAfterSimulate();

    const $budget = $('human-budget-summary');
    if ($budget) {
      $budget.classList.add('hidden');
      $budget.innerHTML = '';
    }

    if ($draftComplete) {
      $draftComplete.classList.add('hidden');
      if ($draftCompleteInner) $draftCompleteInner.innerHTML = '';
    }
    if ($draftSide) $draftSide.classList.remove('hidden');
    if ($draft) $draft.classList.remove('draft-finished');

    if ($aiReasoning) {
      $aiReasoning.classList.add('hidden');
      $aiReasoning.classList.remove('weird-event');
      $aiReasoning.querySelector('.weird-event-label')?.classList.add('hidden');
      const teamEl = $aiReasoning.querySelector('#ai-reasoning-team');
      if (teamEl) {
        teamEl.innerHTML = '';
        teamEl.classList.add('hidden');
      }
      const textEl = $aiReasoning.querySelector('#ai-reasoning-text');
      if (textEl) {
        textEl.textContent = '';
        textEl.classList.remove('reasoning-appear');
      }
    }

    $draft.classList.add('hidden');
    $setup.classList.remove('hidden');
  }

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  /** k-th selection for this pick's team in draft order (aligns with teamPicks arrays). */
  function getSelectionForPickIndex(pickIndex) {
    const pick = state.picks[pickIndex];
    if (!pick) return null;
    const k = state.picks.slice(0, pickIndex).filter(p => p.team === pick.team).length;
    const arr = state.teamPicks[pick.team];
    return arr && arr[k] ? arr[k] : null;
  }

  /** Binary share payload after draft (bare <code>?…</code> or legacy <code>#d=</code> / <code>?d=</code>); client-side only. */
  const ENDGAME_URL_MAGIC = [0x4f, 0x53, 0x44, 0x31];

  function bytesToBase64Url(u8) {
    let bin = '';
    for (let i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
    return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  }

  function base64UrlToBytes(s) {
    if (!s) return null;
    let t = s.replace(/-/g, '+').replace(/_/g, '/');
    const pad = t.length % 4;
    if (pad) t += '='.repeat(4 - pad);
    try {
      const bin = atob(t);
      const out = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
      return out;
    } catch {
      return null;
    }
  }

  function buildEndgamePayloadBinary() {
    const nPicks = state.picks.length;
    const humanIndices = [...state.originalHumanTeams]
      .map(name => state.teams.findIndex(t => t.name === name))
      .filter(i => i >= 0)
      .sort((a, b) => a - b);
    const nHuman = humanIndices.length;
    const headerLen = 4 + 2 + 2 + 1 + nHuman;
    const bodyLen = nPicks * (2 + 4);
    const buf = new ArrayBuffer(headerLen + bodyLen);
    const u8 = new Uint8Array(buf);
    const dv = new DataView(buf);
    ENDGAME_URL_MAGIC.forEach((b, i) => { u8[i] = b; });
    let o = 4;
    dv.setUint16(o, DRAFT_DATA.version, false);
    o += 2;
    dv.setUint16(o, nPicks, false);
    o += 2;
    dv.setUint8(o, nHuman);
    o += 1;
    for (let i = 0; i < nHuman; i++) {
      dv.setUint8(o, humanIndices[i]);
      o += 1;
    }
    for (let i = 0; i < nPicks; i++) {
      const pick = state.picks[i];
      const k = state.picks.slice(0, i).filter(p => p.team === pick.team).length;
      const sel = state.teamPicks[pick.team][k];
      let rank = 0;
      let cost = 0;
      if (sel && sel.name !== '(pass)') {
        rank = sel.rank != null ? sel.rank : 0;
        cost = sel.cost != null ? sel.cost >>> 0 : 0;
      }
      dv.setUint16(o, rank, false);
      o += 2;
      dv.setUint32(o, cost, false);
      o += 4;
    }
    return u8;
  }

  /**
   * Fills teamPicks, teamSpent, drafted, originalHumanTeams, currentPickIndex.
   * Returns false if bytes are invalid or do not match DRAFT_DATA.version / pick count.
   */
  function applyEndgamePayloadBytes(bytes) {
    if (!bytes || bytes.length < 9) return false;
    for (let i = 0; i < 4; i++) {
      if (bytes[i] !== ENDGAME_URL_MAGIC[i]) return false;
    }
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let o = 4;
    const dataVersion = dv.getUint16(o, false);
    o += 2;
    const nPicks = dv.getUint16(o, false);
    o += 2;
    const nHuman = dv.getUint8(o);
    o += 1;
    if (dataVersion !== DRAFT_DATA.version || nPicks !== state.picks.length) return false;
    const expectedLen = 9 + nHuman + nPicks * 6;
    if (bytes.length !== expectedLen) return false;
    const humanIndices = [];
    for (let i = 0; i < nHuman; i++) {
      const idx = dv.getUint8(o);
      o += 1;
      if (idx >= state.teams.length) return false;
      humanIndices.push(idx);
    }
    const rows = [];
    for (let i = 0; i < nPicks; i++) {
      const rank = dv.getUint16(o, false);
      o += 2;
      const cost = dv.getUint32(o, false) >>> 0;
      o += 4;
      if (rank !== 0 && !getPlayerByRank(rank) && !isSyntheticRandomSeniorRank(rank)) return false;
      rows.push({ rank, cost });
    }

    state.teamPicks = {};
    state.teamSpent = {};
    state.drafted = new Set();
    state.originalHumanTeams = new Set(humanIndices.map(i => state.teams[i].name));
    state.humanTeams = new Set();
    state.pickRationales = {};
    state.currentPickIndex = nPicks;

    for (let i = 0; i < nPicks; i++) {
      const { rank, cost } = rows[i];
      const pick = state.picks[i];
      if (!state.teamPicks[pick.team]) state.teamPicks[pick.team] = [];
      if (rank === 0) {
        state.teamPicks[pick.team].push({ name: '(pass)', cost: 0 });
      } else if (isSyntheticRandomSeniorRank(rank)) {
        state.drafted.add(rank);
        state.teamSpent[pick.team] = (state.teamSpent[pick.team] || 0) + cost;
        state.teamPicks[pick.team].push({
          name: 'Random senior sign',
          cost,
          rank,
          photoUrl: null
        });
      } else {
        const player = getPlayerByRank(rank);
        state.drafted.add(rank);
        state.teamSpent[pick.team] = (state.teamSpent[pick.team] || 0) + cost;
        state.teamPicks[pick.team].push({
          name: player.name,
          cost,
          rank: player.rank,
          photoUrl: player.photoUrl
        });
      }
    }
    return true;
  }

  function clearEndgameStateFromUrl() {
    const home = getMockDraftHomePath();
    const hadPathShare = /\/my-mock-draft\/s\/[^/]+\/?$/.test(location.pathname);
    const hadPathShareUuid = MOCK_DRAFT_UUID_PATH.test(location.pathname);

    const q = location.search;
    const body = q.startsWith('?') ? q.slice(1) : '';
    const hadLegacyHash = !!(location.hash && location.hash.startsWith('#d='));
    const params = new URLSearchParams(q);
    const hadDParam = params.has('d');
    const hadBarePayload = body.length > 0 && !body.includes('=');

    if (!hadLegacyHash && !hadDParam && !hadBarePayload && !hadPathShare && !hadPathShareUuid) return;

    let newPath = location.pathname;
    if (hadPathShare || hadPathShareUuid) newPath = `${home}/`;

    let newSearch;
    if (hadDParam) {
      params.delete('d');
      newSearch = params.toString() ? `?${params.toString()}` : '';
    } else if (hadBarePayload || hadPathShare || hadPathShareUuid) {
      newSearch = '';
    } else {
      newSearch = location.search;
    }
    const nextHash = hadLegacyHash ? '' : location.hash;
    history.replaceState(null, '', newPath + newSearch + nextHash);
  }

  /**
   * Saves finished draft to the server and rewrites the URL to <code>/my-mock-draft/&lt;uuid&gt;/</code>.
   * Returns the same Promise while a request is in flight so callers (copy button) await one save.
   * On failure, falls back to legacy <code>/my-mock-draft/s/&lt;payload&gt;/</code>.
   */
  function ensureSharePersisted() {
    if (!isDraftCompleteForShare()) {
      return Promise.resolve({ uuid: null });
    }
    const pathUuid = parseUuidFromMockDraftPath();
    if (pathUuid) {
      return Promise.resolve({ uuid: pathUuid });
    }
    const winUuid = typeof window.__MOCK_DRAFT_SHARE_UUID__ === 'string' && window.__MOCK_DRAFT_SHARE_UUID__.length
      ? window.__MOCK_DRAFT_SHARE_UUID__
      : null;
    if (winUuid) {
      return Promise.resolve({ uuid: winUuid });
    }
    if (sharePersistPromise) {
      return sharePersistPromise;
    }

    sharePersistPromise = (async () => {
      try {
        const bin = buildEndgamePayloadBinary();
        const enc = bytesToBase64Url(bin);
        const home = getMockDraftHomePath();
        const createUrl = (typeof window.__MOCK_DRAFT_SHARE_CREATE_URL__ === 'string' && window.__MOCK_DRAFT_SHARE_CREATE_URL__)
          ? window.__MOCK_DRAFT_SHARE_CREATE_URL__
          : '/api/my-mock-draft/share/';
        const res = await fetch(createUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
          },
          credentials: 'same-origin',
          body: JSON.stringify({ payload: enc })
        });
        if (!res.ok) throw new Error('share save failed');
        const data = await res.json();
        const id = data && data.id;
        if (!id || typeof id !== 'string') throw new Error('missing id');
        if (!isDraftCompleteForShare()) return { uuid: null };
        history.replaceState(null, '', `${home}/${id}/`);
        window.__MOCK_DRAFT_SHARE_UUID__ = id;
        try {
          delete window.__MOCK_DRAFT_SHARE_PAYLOAD_B64__;
        } catch (_) { window.__MOCK_DRAFT_SHARE_PAYLOAD_B64__ = ''; }
        return { uuid: id };
      } catch (e) {
        console.warn('Could not persist share URL; using inline path', e);
        if (!isDraftCompleteForShare()) return { uuid: null };
        try {
          const payload = buildEndgamePayloadBinary();
          const enc = bytesToBase64Url(payload);
          const home = getMockDraftHomePath();
          history.replaceState(null, '', `${home}/s/${enc}/`);
        } catch (e2) {
          console.warn('Could not update URL with draft state', e2);
        }
        return { uuid: null };
      } finally {
        sharePersistPromise = null;
      }
    })();

    return sharePersistPromise;
  }

  /**
   * When the draft is complete, persist UUID share URL once (re-renders share the same in-flight Promise).
   */
  function ensureEndgameShareUrl() {
    if (state.currentPickIndex >= state.picks.length) {
      void ensureSharePersisted();
    }
  }

  function buildDraftShareCallout() {
    const wrap = document.createElement('div');
    wrap.className =
      'draft-share-callout mb-4 p-3 sm:p-4 border border-overslot-grey-border bg-black/35 rounded-sm text-left max-w-3xl mx-auto w-full';
    const h = document.createElement('h3');
    h.className = 'text-base font-semibold text-white mb-1.5';
    h.textContent = 'Share your draft';
    const p = document.createElement('p');
    p.className = 'text-sm text-neutral-400 mb-3 leading-snug';
    p.textContent =
      'Copy a link to share this exact finished draft with anyone — they see all of the same picks, bonuses and mayhem!';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className =
      'draft-share-copy px-3 py-2 text-sm font-medium border border-overslot-red bg-red-950/40 text-white hover:bg-red-950/60 cursor-pointer';
    const labelDefault = 'Copy URL to my draft';
    btn.textContent = labelDefault;
    btn.addEventListener('click', async () => {
      await ensureSharePersisted();
      const url = getShareableDraftUrl();
      try {
        await navigator.clipboard.writeText(url);
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = labelDefault; }, 2200);
      } catch {
        try {
          const ta = document.createElement('textarea');
          ta.value = url;
          ta.setAttribute('aria-hidden', 'true');
          ta.style.position = 'fixed';
          ta.style.left = '-99rem';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          btn.textContent = 'Copied!';
          setTimeout(() => { btn.textContent = labelDefault; }, 2200);
        } catch {
          btn.textContent = 'Copy failed';
          setTimeout(() => { btn.textContent = labelDefault; }, 2200);
        }
      }
    });
    wrap.appendChild(h);
    wrap.appendChild(p);
    wrap.appendChild(btn);
    return wrap;
  }

  function setupUIForRestoredEndgame() {
    $setup?.classList.add('hidden');
    $draft?.classList.remove('hidden');
    $draft?.classList.add('draft-finished');
    if ($draftSide) $draftSide.classList.add('hidden');
    if ($draftComplete) {
      $draftComplete.classList.remove('hidden');
      if ($draftCompleteInner) $draftCompleteInner.innerHTML = '';
    }
    $btnRestart?.classList.add('hidden');
    $btnSimulateRest?.classList.add('hidden');
    $btnPause?.classList.add('hidden');
    $btnResume?.classList.add('hidden');
    $currentPick?.classList.add('hidden');
    if ($status) {
      $status.textContent = 'DRAFT COMPLETE.';
      $status.classList.remove('picking');
    }
    const $budgetDone = $('human-budget-summary');
    if ($budgetDone) $budgetDone.classList.add('hidden');
    if ($aiReasoning) {
      $aiReasoning.classList.add('hidden');
      $aiReasoning.classList.remove('weird-event');
      $aiReasoning.querySelector('.weird-event-label')?.classList.add('hidden');
    }

    $board.innerHTML = '';
    $('round-breadcrumbs').innerHTML = '';
    state.boardRows = [];
    state.pickIndexToRow = {};
    getRoundSections().forEach(s => ensureRoundVisible(s.label));

    for (let i = 0; i < state.picks.length; i++) {
      applyRestoredPickToRow(i);
    }
    renderRoundBreadcrumbs();
    state.endgameTab = 'my';
    state.endgameTeamChoice = null;
    state.endgameBrowseIndex = 0;
    renderDraftCompleteBragSheets();
    requestAnimationFrame(() => {
      $draftComplete?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  function applyRestoredPickToRow(pickIndex) {
    const pick = state.picks[pickIndex];
    const row = state.pickIndexToRow[pickIndex]?.row;
    if (!pick || !row) return;
    const k = state.picks.slice(0, pickIndex).filter(p => p.team === pick.team).length;
    const sel = state.teamPicks[pick.team][k];
    const playerEl = row.querySelector('.col-player');
    const costEl = row.querySelector('.col-cost');
    if (sel && sel.name !== '(pass)' && sel.rank != null) {
      const player = playerFromTeamSelection(sel);
      if (playerEl && player) {
        const rankBit = player.name === 'Random senior sign' ? '' : `#${player.rank} `;
        playerEl.className = 'col-player flex items-center gap-1.5 min-w-0';
        playerEl.innerHTML = playerPhotoHtml(player) + `<span class="truncate min-w-0">${rankBit}${player.position ? player.position + ' ' : ''}${escapeHtml(player.name)}</span>`;
      }
      if (costEl && pick.value != null) {
        const effectiveCost = sel.cost;
        costEl.textContent = fmt(effectiveCost);
        costEl.classList.remove('text-overslot-red', 'text-white', 'text-green-400');
        if (effectiveCost > pick.value) costEl.classList.add('text-overslot-red');
        else if (effectiveCost < pick.value) costEl.classList.add('text-green-400');
        else costEl.classList.add('text-white');
      }
    } else {
      if (playerEl) {
        playerEl.className = 'col-player truncate';
        playerEl.textContent = '(pass)';
      }
      if (costEl) {
        costEl.textContent = '—';
        costEl.classList.remove('text-overslot-red', 'text-green-400');
        costEl.classList.add('text-white');
      }
    }
    row.classList.remove('current', 'bg-red-900/20');
    row.querySelector('div:last-child')?.classList.remove('bg-red-900/10');
    row.classList.add('opacity-75', 'past-pick');
    if (state.originalHumanTeams.has(pick.team)) {
      row.classList.add('human-pick');
    }
  }

  function removeEndgamePendingClass() {
    document.documentElement.classList.remove('endgame-pending');
  }

  function tryRestoreEndgameFromUrl() {
    const raw = extractEndgamePayloadRaw();
    if (!raw) return false;
    const bytes = base64UrlToBytes(raw);
    if (!bytes || !applyEndgamePayloadBytes(bytes)) {
      console.warn('Invalid or outdated draft link');
      clearEndgameStateFromUrl();
      removeEndgamePendingClass();
      return false;
    }
    setupUIForRestoredEndgame();
    const home = getMockDraftHomePath();
    const uuid = parseUuidFromMockDraftPath() || (typeof window.__MOCK_DRAFT_SHARE_UUID__ === 'string' ? window.__MOCK_DRAFT_SHARE_UUID__ : null);
    const wantPath = uuid ? `${home}/${uuid}/` : `${home}/s/${raw}/`;
    const pathOk = normalizePathname(location.pathname) === normalizePathname(wantPath);
    const needStrip =
      !pathOk ||
      !!(location.hash && location.hash.startsWith('#d=')) ||
      !!location.search;
    if (needStrip) {
      history.replaceState(null, '', wantPath);
    }
    removeEndgamePendingClass();
    return true;
  }

  function getPlayerByRank(rank) {
    if (rank == null) return null;
    return state.players.find(p => p.rank === rank) || null;
  }

  /** Row / browse / brag: resolve teamPicks row to a player-shaped object (includes synthetic random senior). */
  function playerFromTeamSelection(sel) {
    if (!sel || sel.name === '(pass)') return null;
    if (sel.name === 'Random senior sign' && isSyntheticRandomSeniorRank(sel.rank)) {
      return {
        name: 'Random senior sign',
        rank: sel.rank,
        position: '—',
        school: 'College',
        class: 'C',
        photoUrl: sel.photoUrl ?? null
      };
    }
    return getPlayerByRank(sel.rank) || {
      name: sel.name,
      rank: sel.rank,
      position: '',
      school: '',
      class: 'C',
      photoUrl: sel.photoUrl
    };
  }

  function getAllTeamNamesSorted() {
    return [...state.teams].map(t => t.name).sort((a, b) => a.localeCompare(b));
  }

  /** One brag card: compact 3-column grid; tool URL in header row to the right of the team block. */
  function buildBragSheetWrap(teamName) {
    const teamData = state.teams.find(t => t.name === teamName);
    const teamId = teamData?.id;
    const roundPicks = state.picks.filter(p => p.team === teamName);
    const selections = state.teamPicks[teamName] || [];

    const wrap = document.createElement('div');
    wrap.className = 'brag-sheet-wrap flex flex-col gap-1';

    const exportRoot = document.createElement('div');
    exportRoot.className = 'brag-sheet-export brag-sheet-export--share bg-[#141414] border border-overslot-grey-border p-2 sm:p-2.5 w-full mx-auto';
    exportRoot.setAttribute('data-team', teamName);

    const header = document.createElement('div');
    header.className =
      'brag-share-header flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 sm:gap-4 pb-2 text-left';
    const logoHtml = teamLogoHtml(teamId, 'w-14 h-14 sm:w-16 sm:h-16');
    header.innerHTML = `
      <div class="flex flex-row gap-2 sm:gap-3 min-w-0 flex-1">
        <div class="flex-shrink-0">${logoHtml}</div>
        <div class="min-w-0 flex-1">
          <h3 class="brag-sheet-team-title text-xl sm:text-2xl font-bold text-white leading-tight tracking-tight">${escapeHtml(teamName)}</h3>
          <p class="text-sm text-neutral-400 mt-0.5 leading-snug">2026 Mock Draft class</p>
        </div>
      </div>
      <div class="brag-share-url-banner brag-share-url-banner--header">
        <span class="brag-share-url-label">Run your own mock draft at</span>
        <a class="brag-share-url-link" href="${escapeHtml(getMockDraftToolHomeUrl())}" target="_blank" rel="noopener noreferrer">${escapeHtml(getMockDraftToolHomeUrl())}</a>
      </div>`;

    const grid = document.createElement('div');
    grid.className = 'brag-pick-grid';

    roundPicks.forEach((pick, i) => {
      const sel = selections[i];
      const slotStr = pick.value != null ? fmt(pick.value) : '—';
      const cell = document.createElement('div');
      cell.className = 'brag-pick-cell';

      if (!sel || sel.name === '(pass)') {
        cell.innerHTML = `
          <div class="brag-pick-cell-inner brag-pick-pass">
            <span class="brag-pick-no">${pick.pick}</span>
            <span class="brag-pick-pass-label">Pass</span>
            <span class="brag-pick-slot">Slot ${escapeHtml(slotStr)}</span>
          </div>`;
        grid.appendChild(cell);
        return;
      }

      const player = playerFromTeamSelection(sel);
      const displayCost = sel.cost != null ? sel.cost : 0;
      const costClass = pick.value != null
        ? (displayCost > pick.value ? 'text-overslot-red' : displayCost < pick.value ? 'text-green-400' : 'text-white')
        : 'text-white';
      const photo = playerPhotoHtml(player, 'w-8 h-8 sm:w-9 sm:h-9', true, true);
      const schoolLine = player.school
        ? `<div class="brag-pick-school">${escapeHtml(player.school)}</div>`
        : '';
      const rankPosLine = player.name === 'Random senior sign'
        ? 'Pool saver'
        : `#${sel.rank != null ? sel.rank : '—'}${player.position ? ' · ' + escapeHtml(player.position) : ''}`;
      cell.innerHTML = `
        <div class="brag-pick-cell-inner">
          <div class="brag-pick-top">
            <span class="brag-pick-no">${pick.pick}</span>
            <div class="brag-pick-photo">${photo}</div>
            <div class="brag-pick-meta">
              <div class="brag-pick-name">${escapeHtml(player.name || sel.name)}</div>
              <div class="brag-pick-rank-pos">${rankPosLine}</div>
              ${schoolLine}
            </div>
            <div class="brag-pick-cost ${costClass}">${fmt(displayCost)}</div>
          </div>
          <div class="brag-pick-bottom">Slot ${escapeHtml(slotStr)}</div>
        </div>`;
      grid.appendChild(cell);
    });

    const pool = teamData ? teamData.pool : 0;
    const spent = getTeamSpent(teamName);
    const remaining = getTeamRemaining(teamName);
    const footer = document.createElement('div');
    footer.className = 'brag-share-footer mt-1 pt-1 border-t border-overslot-grey-border flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-neutral-500 leading-tight';
    footer.innerHTML = `
        <span>Pool <span class="text-neutral-300">${fmt(pool)}</span></span>
        <span>Spent <span class="text-neutral-300">${fmt(spent)}</span></span>
        <span>Left <span class="text-neutral-300">${fmt(remaining)}</span></span>
      `;

    exportRoot.appendChild(header);
    exportRoot.appendChild(grid);
    exportRoot.appendChild(footer);

    wrap.appendChild(exportRoot);
    return wrap;
  }

  function getBrowsePickDisplay(pickIndex) {
    const pick = state.picks[pickIndex];
    const r = state.pickRationales[pickIndex];
    const sel = getSelectionForPickIndex(pickIndex);
    if (!pick) {
      return { pick: null, r: null, displayCost: null, costClass: 'text-white', player: null };
    }
    const player = r?.player
      ?? (sel && sel.name !== '(pass)' && sel.rank != null ? playerFromTeamSelection(sel) : null);
    let displayCost = null;
    if (player) {
      if (r?.player) {
        displayCost = r.effectiveCost ?? r.player.cost;
      } else if (sel && sel.name !== '(pass)') {
        displayCost = sel.cost;
      }
    }
    const costClass = player && pick.value != null
      ? (displayCost > pick.value ? 'text-overslot-red' : displayCost < pick.value ? 'text-green-400' : 'text-white')
      : 'text-white';
    return { pick, r, displayCost, costClass, player };
  }

  /** One horizontal row in the full pick-by-pick list. */
  function buildBrowsePickRow(pickIndex) {
    const { pick, displayCost, costClass, player } = getBrowsePickDisplay(pickIndex);
    const row = document.createElement('div');
    row.className = 'endgame-browse-row';
    row.dataset.endgameBrowseRow = String(pickIndex);
    if (!pick) {
      row.textContent = '—';
      return row;
    }

    const playerCol = player
      ? `<div class="browse-cell browse-cell-player">${playerPhotoHtml(player, 'w-8 h-8', true)}<span class="browse-player-text"><span class="browse-player-name">#${player.rank} ${escapeHtml(player.name)}</span><span class="browse-player-pos">${escapeHtml(player.position)}</span></span></div>`
      : '<div class="browse-cell browse-cell-player"><span class="text-neutral-500">Pass</span></div>';

    const signStr = player && displayCost != null ? fmt(displayCost) : '—';
    const roundShort = escapeHtml(shortRoundNavLabel(pick.round || '') || (pick.round || '').slice(0, 12));

    row.innerHTML = `
      <div class="browse-cell browse-cell-pick tabular-nums">${pick.pick}</div>
      <div class="browse-cell browse-cell-round" title="${escapeHtml(pick.round || '')}">${roundShort}</div>
      <div class="browse-cell browse-cell-team">${teamLogoHtml(pick.teamId, 'w-6 h-6')}<span class="browse-team-name">${escapeHtml(pick.team)}</span></div>
      <div class="browse-cell browse-cell-slot tabular-nums">${pick.value != null ? fmt(pick.value) : '—'}</div>
      ${playerCol}
      <div class="browse-cell browse-cell-sign tabular-nums ${costClass}">${signStr}</div>`;

    return row;
  }

  function renderDraftCompleteBragSheets() {
    renderEndgame();
  }

  function renderEndgame() {
    if (!$draftCompleteInner) return;
    ensureEndgameShareUrl();
    $draftCompleteInner.innerHTML = '';

    const tab = state.endgameTab || 'my';
    const allNames = getAllTeamNamesSorted();
    if (!state.endgameTeamChoice && allNames.length) {
      state.endgameTeamChoice = allNames[0];
    } else if (state.endgameTeamChoice && !allNames.includes(state.endgameTeamChoice)) {
      state.endgameTeamChoice = allNames[0] || null;
    }

    const nPicks = state.picks.length;
    state.endgameBrowseIndex = Math.max(0, Math.min(state.endgameBrowseIndex, Math.max(0, nPicks - 1)));

    const toolbar = document.createElement('div');
    toolbar.className = 'endgame-toolbar flex flex-wrap items-center gap-2 sm:gap-2.5 mb-3';
    const tabDefs = [
      { id: 'my', label: 'My team(s)' },
      { id: 'team', label: 'Any team' },
      { id: 'browse', label: 'Browse picks' }
    ];
    tabDefs.forEach(({ id, label }) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'endgame-tab text-base px-3 py-1.5 border font-medium cursor-pointer transition-colors ' + (tab === id
        ? 'border-overslot-red bg-red-950/40 text-white'
        : 'border-overslot-grey-border bg-overslot-grey text-neutral-200 hover:border-neutral-500');
      b.textContent = label;
      b.addEventListener('click', () => {
        state.endgameTab = id;
        renderEndgame();
      });
      toolbar.appendChild(b);
    });

    const restartToolbar = document.createElement('button');
    restartToolbar.type = 'button';
    restartToolbar.className =
      'endgame-restart text-base px-3 py-1.5 border border-amber-500/80 bg-amber-950/55 text-amber-100 font-semibold cursor-pointer hover:bg-amber-900/70 hover:border-amber-400 transition-colors';
    restartToolbar.textContent = 'Restart';
    restartToolbar.addEventListener('click', () => restartToSetup());
    toolbar.appendChild(restartToolbar);

    const teamSel = document.createElement('select');
    teamSel.id = 'endgame-team-select';
    teamSel.setAttribute('aria-label', 'Team for brag sheet');
    teamSel.className = 'text-base bg-black/50 border border-overslot-grey-border text-white px-2 py-1.5 max-w-[min(100%,20rem)] ' + (tab === 'team' ? '' : 'hidden');
    allNames.forEach(name => {
      const o = document.createElement('option');
      o.value = name;
      o.textContent = name;
      teamSel.appendChild(o);
    });
    if (state.endgameTeamChoice) teamSel.value = state.endgameTeamChoice;
    teamSel.addEventListener('change', () => {
      state.endgameTeamChoice = teamSel.value;
      renderEndgame();
    });
    toolbar.appendChild(teamSel);

    $draftCompleteInner.appendChild(toolbar);

    const hero = document.createElement('div');
    hero.className = 'draft-complete-hero text-center mb-3 draft-complete-hero-appear';
    let title = 'Draft complete';
    let subtitle = '';
    if (tab === 'my') {
      title = state.originalHumanTeams.size ? 'Your mock draft class' : 'That\u2019s a wrap';
      subtitle = state.originalHumanTeams.size
        ? ''
        : 'You didn\u2019t select a human team—use <strong class="text-neutral-300">Any team</strong> for a brag sheet, or <strong class="text-neutral-300">Browse picks</strong> to review the draft.';
    } else if (tab === 'team') {
      const teamNameForHero = state.endgameTeamChoice || allNames[0] || '';
      title = teamNameForHero
        ? `The ${escapeHtml(teamNameForHero)}'s class`
        : 'Draft complete';
      subtitle = '';
    } else {
      title = 'Pick-by-pick';
      subtitle = 'Every selection in draft order—one long scrollable list. Click a pick on the draft board to jump here.';
    }
    hero.innerHTML = `
      <p class="text-overslot-red text-sm font-bold uppercase tracking-[0.18em] mb-1">Draft complete</p>
      <h2 class="brag-sheet-team-title text-3xl sm:text-4xl font-bold text-white mb-1.5 tracking-tight leading-tight">${title}</h2>
      ${subtitle ? `<p class="text-neutral-400 text-base sm:text-lg max-w-2xl mx-auto leading-snug">${subtitle}</p>` : ''}`;
    $draftCompleteInner.appendChild(hero);
    $draftCompleteInner.appendChild(buildDraftShareCallout());

    const content = document.createElement('div');
    content.className = 'endgame-content flex flex-col gap-4';
    $draftCompleteInner.appendChild(content);

    if (tab === 'my') {
      const myTeams = [...state.originalHumanTeams].sort((a, b) => a.localeCompare(b));
      if (myTeams.length === 0) {
        const p = document.createElement('p');
        p.className = 'text-neutral-500 text-base text-center leading-snug';
        p.innerHTML = 'Select a human team before <strong class="text-neutral-400">Start Draft</strong> next time to unlock &ldquo;My team(s)&rdquo; here.';
        content.appendChild(p);
      } else {
        myTeams.forEach(name => content.appendChild(buildBragSheetWrap(name)));
      }
    } else if (tab === 'team') {
      const name = state.endgameTeamChoice || allNames[0];
      if (name) content.appendChild(buildBragSheetWrap(name));
    } else {
      const intro = document.createElement('p');
      intro.className = 'text-center text-sm text-neutral-500 mb-2 leading-snug';
      intro.textContent = nPicks ? `${nPicks} pick${nPicks !== 1 ? 's' : ''} in draft order` : 'No picks';

      const headerRow = document.createElement('div');
      headerRow.className = 'endgame-browse-header';
      headerRow.innerHTML = `
        <div class="browse-cell browse-cell-pick">Pick</div>
        <div class="browse-cell browse-cell-round">Rd</div>
        <div class="browse-cell browse-cell-team">Team</div>
        <div class="browse-cell browse-cell-slot">Slot</div>
        <div class="browse-cell browse-cell-player">Player</div>
        <div class="browse-cell browse-cell-sign">Sign</div>`;

      const list = document.createElement('div');
      list.className = 'endgame-browse-list';
      for (let pi = 0; pi < nPicks; pi++) {
        list.appendChild(buildBrowsePickRow(pi));
      }

      const tableWrap = document.createElement('div');
      tableWrap.className = 'endgame-browse-table-wrap';
      tableWrap.appendChild(headerRow);
      tableWrap.appendChild(list);

      content.appendChild(intro);
      content.appendChild(tableWrap);
    }

    if (tab === 'browse' && nPicks > 0) {
      requestAnimationFrame(() => {
        const rowEl = $draftCompleteInner.querySelector(`[data-endgame-browse-row="${state.endgameBrowseIndex}"]`);
        rowEl?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    }
  }

  function playerPhotoHtml(player, sizeClass = 'w-8 h-8', square = false, imgCrossOrigin = false) {
    const url = player?.photoUrl;
    const initial = (player?.name || '?')[0].toUpperCase();
    const shapeStyle = square ? 'border-radius: 2px;' : 'border-radius: 50%;';
    const placeholder = `<span class="${sizeClass} flex-shrink-0 bg-overslot-grey flex items-center justify-center text-neutral-400 text-xs font-medium overflow-hidden" style="${shapeStyle}">${escapeHtml(initial)}</span>`;
    if (url) {
      const cors = imgCrossOrigin ? ' crossorigin="anonymous"' : '';
      return `<span class="player-photo-wrap ${sizeClass} flex-shrink-0 relative inline-block overflow-hidden" style="${shapeStyle}"><img src="${escapeHtml(url)}" alt="${escapeHtml(initial)}"${cors} class="w-full h-full object-cover" onerror="this.onerror=null;this.style.display='none';this.nextElementSibling.style.display='flex';"><span class="absolute inset-0 bg-overslot-grey flex items-center justify-center text-neutral-400 text-xs font-medium" style="display: none;">${escapeHtml(initial)}</span></span>`;
    }
    return placeholder;
  }

  function getTeamPool(team) {
    const t = state.teams.find(x => x.name === team);
    return t ? t.pool : 0;
  }

  function getTeamSpent(team) {
    return state.teamSpent[team] || 0;
  }

  function getTeamRemaining(team) {
    return getTeamPool(team) - getTeamSpent(team);
  }

  function getPicksRemaining(team, pickIndex) {
    const totalPicksForTeam = state.picks.filter(p => p.team === team).length;
    const picksMadeSoFar = state.picks.slice(0, pickIndex).filter(p => p.team === team).length;
    return totalPicksForTeam - picksMadeSoFar;
  }

  /** Pool reserved for picks after this one: $150k per future pick (random senior sign floor). */
  function getFuturePickReserve(picksLeft) {
    if (picksLeft <= 1) return 0;
    return (picksLeft - 1) * RANDOM_SENIOR_SIGN;
  }

  function isSyntheticRandomSeniorRank(rank) {
    return typeof rank === 'number' && rank >= 65000 && rank <= 65535;
  }

  /** Synthetic player when a signing would push the team past pool; rank is unique per draft pick index. */
  function makeRandomSeniorSignPlayer(pickIndex) {
    return {
      rank: 65000 + pickIndex,
      name: 'Random senior sign',
      position: '—',
      school: 'College',
      class: 'C',
      cost: RANDOM_SENIOR_SIGN,
      photoUrl: null
    };
  }

  /**
   * Never returns pass — teams always sign (Random senior sign if no named player fits or pool is tight).
   * Reserve leaves at least RANDOM_SENIOR_SIGN per future pick; emergency fallback uses remaining pool up to that amount.
   */
  function resolvePickForPool(pick, player, prefCost, pickIndex) {
    const team = pick.team;
    const maxThisPick = getMaxSpendThisPick(pick.value, team, pickIndex);
    const remaining = getTeamRemaining(team);

    function randomSeniorNoPass() {
      const senior = makeRandomSeniorSignPlayer(pickIndex);
      let cost = 0;
      if (maxThisPick > 0) {
        cost = Math.min(RANDOM_SENIOR_SIGN, maxThisPick);
      } else if (remaining > 0) {
        cost = Math.min(RANDOM_SENIOR_SIGN, remaining);
      }
      return { player: senior, effectiveCost: cost };
    }

    if (!player) {
      return randomSeniorNoPass();
    }

    let effectiveCost = 0;
    if (isSyntheticRandomSeniorRank(player.rank)) {
      effectiveCost = Math.min(RANDOM_SENIOR_SIGN, prefCost != null ? prefCost : RANDOM_SENIOR_SIGN);
    } else {
      effectiveCost = prefCost != null ? prefCost : getEffectiveSigningCost(player, pick, pick.value);
    }

    if (effectiveCost <= maxThisPick) {
      return { player, effectiveCost };
    }
    return randomSeniorNoPass();
  }

  function getMaxSpendThisPick(slotValue, team, pickIndex) {
    if (!team) return slotValue;
    const remaining = getTeamRemaining(team);
    const picksLeft = getPicksRemaining(team, pickIndex);
    const reserve = getFuturePickReserve(picksLeft);
    return Math.max(0, remaining - reserve);
  }

  function isTopThreeRounds(pick) {
    const r = (pick?.round || '').trim();
    return r === 'Round 1' || r === 'Round 2' || r === 'Round 3';
  }

  function isCompAOrRound2Or3(pick) {
    const r = (pick?.round || '').trim();
    return r === 'Competitive Balance Round A' || r === 'Round 2' || r === 'Round 3';
  }

  function isRound1(pick) {
    const r = (pick?.round || '').trim();
    return r === 'Round 1';
  }

  /** College-only: signing cost scales vs draft pick # (player rank). */
  function getCollegeRankVsPickMultiplier(player, pick) {
    if (player.class !== 'C' || !pick || pick.pick == null) return 1;
    const pickNum = pick.pick;
    const rank = player.rank;
    const spotsBelow = rank - pickNum;
    const spotsAbove = pickNum - rank;

    // Round 1: keep bonuses closer to slot when a player slides or is reached for
    if (isRound1(pick)) {
      if (spotsBelow >= 150) return 0.96;
      if (spotsBelow >= 100) return 0.97;
      if (spotsBelow >= 60) return 0.98;
      if (spotsBelow >= 30) return 0.99;
      if (spotsAbove >= 150) return 1.04;
      if (spotsAbove >= 100) return 1.03;
      if (spotsAbove >= 50) return 1.02;
      return 1;
    }

    if (spotsBelow >= 150) return 0.75;
    if (spotsBelow >= 100) return 0.80;
    if (spotsBelow >= 60) return 0.90;
    if (spotsBelow >= 30) return 0.95;
    if (spotsAbove >= 150) return 1.25;
    if (spotsAbove >= 100) return 1.20;
    if (spotsAbove >= 50) return 1.10;
    return 1;
  }

  function applyCollegeRankVsPickToCost(baseCost, player, pick) {
    const m = getCollegeRankVsPickMultiplier(player, pick);
    if (m === 1) return baseCost;
    return Math.floor(baseCost * m);
  }

  function getEffectiveSigningCost(player, pick, slotValue) {
    if (!player || !slotValue) return player?.cost ?? 0;
    if (player.class !== 'C') return player.cost;
    let base = player.cost;
    if (isRound1(pick)) {
      const roll = Math.random();
      if (roll < 0.62) base = slotValue;
      else if (roll < 0.88) {
        base = Math.floor(slotValue * (0.97 + Math.random() * 0.06));
      } else {
        const discountPct = 0.01 + Math.random() * 0.02;
        base = Math.floor(slotValue * (1 - discountPct));
      }
    } else if (isCompAOrRound2Or3(pick)) {
      if (Math.random() < 0.6) base = slotValue;
      else {
        const discountPct = 0.01 + Math.random() * 0.02;
        base = Math.floor(slotValue * (1 - discountPct));
      }
    }
    return applyCollegeRankVsPickToCost(base, player, pick);
  }

  /**
   * @param {object} [opts]
   * @param {boolean} [opts.useFullRemainingPoolForCap] — If true, cap by raw pool left (misleading vs Plan max).
   *   Default false: same cap as resolvePickForPool / human “Plan max”.
   */
  function getAvailablePlayers(slotValue, team, pickIndex, opts = {}) {
    const idx = pickIndex ?? state.currentPickIndex;
    const pick = state.picks[idx];
    const maxSpend = team
      ? (opts.useFullRemainingPoolForCap
        ? Math.max(0, getTeamRemaining(team))
        : getMaxSpendThisPick(slotValue, team, idx))
      : slotValue;
    const minSpend = (pick && slotValue && isTopThreeRounds(pick))
      ? Math.floor(slotValue * MIN_SLOT_PCT_TOP3)
      : 0;
    return state.players
      .filter(p => isPlayerSelectableInPool(p))
      .filter(p => {
        const collegeSlotBand = pick && p.class === 'C' && isCompAOrRound2Or3(pick);
        const effectiveMax = collegeSlotBand ? slotValue : p.cost;
        const effectiveMin = collegeSlotBand ? Math.floor(slotValue * 0.97) : p.cost;
        return effectiveMax <= maxSpend && effectiveMin >= minSpend;
      })
      .sort((a, b) => a.rank - b.rank);
  }

  function getTeamFitScore(player, team, pickIndex, slotValue) {
    const teamData = state.teams.find(t => t.name === team);
    if (!teamData || !teamData.rules) return 0;
    const rules = (teamData.rules || '').toLowerCase();
    const isFirstPick = !state.picks.slice(0, pickIndex).some(p => p.team === team);
    const isPitcher = p => /^(RHP|LHP|RHP\/|LHP\/)/.test(p.position);
    const isPositionPlayer = p => !isPitcher(p);
    let score = 0;
    if (!isFirstPick) return 0;
    if (/(?:college player|college performers|college position player|lean toward college|prefer.*college)/.test(rules) && player.class === 'C') score += 2;
    if (/college position player/.test(rules) && player.class === 'C' && isPositionPlayer(player)) score += 1;
    if (/(?:high school player|high school position player|prefer.*high school)/.test(rules) && player.class === 'H') score += 2;
    if (/high school position player/.test(rules) && player.class === 'H' && isPositionPlayer(player)) score += 1;
    if (/(?:position player|hitter|prioritize.*bat)/.test(rules) && isPositionPlayer(player)) score += 2;
    if (/(?:pitcher|pitching)/.test(rules) && isPitcher(player)) score += 2;
    if (/high school position player or college pitcher|high school posiiton player/.test(rules)) {
      if ((player.class === 'H' && isPositionPlayer(player)) || (player.class === 'C' && isPitcher(player))) score += 2;
    }
    if (/big discount|underslot/.test(rules) && slotValue && player.cost <= slotValue * 0.5) score += 2;
    if (/up-the-middle|athletic/.test(rules) && /^(SS|2B|CF|C)/.test(player.position)) score += 1;
    if (/avoid.*pitcher|will not draft.*pitcher/.test(rules) && isPitcher(player)) score -= 10;
    if (/avoid.*high school pitcher|prep pitcher/.test(rules) && player.class === 'H' && isPitcher(player)) score -= 10;
    if (/will not draft.*high school/.test(rules) && player.class === 'H') score -= 10;
    if (/will not draft.*c,? ?1b|will not draft.*3b/.test(rules) && /^(C|1B|3B)/.test(player.position)) score -= 10;
    return score;
  }

  function getMaxRankForRecommendations(pickNumber) {
    return Math.min(350, pickNumber + 80);
  }

  function getTeamFitCandidates(candidates, team, pickIndex, slotValue) {
    const pick = state.picks[pickIndex];
    const maxRank = pick ? getMaxRankForRecommendations(pick.pick) : 100;
    const rankCapped = candidates.filter(p => p.rank <= maxRank);
    const teamData = state.teams.find(t => t.name === team);
    if (!teamData || !teamData.rules) return [...rankCapped].sort((a, b) => a.rank - b.rank);
    const hardFiltered = applyTeamRulesHardFilter(rankCapped, team, pickIndex);
    return hardFiltered
      .map(p => ({
        player: p,
        score: getTeamFitScore(p, team, pickIndex, slotValue) + (Math.random() - 0.5) * 2
      }))
      .sort((a, b) => (b.score - a.score) || (a.player.rank - b.player.rank))
      .map(x => x.player);
  }

  function applyTeamRulesHardFilter(candidates, team, pickIndex) {
    const teamData = state.teams.find(t => t.name === team);
    if (!teamData || !teamData.rules) return candidates;
    const rules = (teamData.rules || '').toLowerCase();
    const isFirstPick = !state.picks.slice(0, pickIndex).some(p => p.team === team);
    const isPitcher = p => /^(RHP|LHP|RHP\/|LHP\/)/.test(p.position);
    const isPositionPlayer = p => !isPitcher(p);
    let filtered = candidates;
    if (!isFirstPick) return filtered;
    if (/will not draft a pitcher in the first round/.test(rules)) filtered = filtered.filter(isPositionPlayer);
    if (/will not draft a c,?\s*1b,?\s*or 3b/.test(rules)) filtered = filtered.filter(p => !/^(C|1B|3B)/.test(p.position));
    if (/will not draft a high school player with first pick/.test(rules)) filtered = filtered.filter(p => p.class === 'C');
    if (/will not draft.*jacob lombard|jacob lombard.*tyler bell/.test(rules)) {
      const avoid = ['Jacob Lombard', 'Tyler Bell', 'Sawyer Strosnider', 'Ace Reese', 'Logan Schmidt'];
      filtered = filtered.filter(p => !avoid.some(a => p.name.includes(a)));
    }
    if (/avoid prep pitchers in round 1|avoid high school pitchers/.test(rules)) {
      filtered = filtered.filter(p => p.class !== 'H' || isPositionPlayer(p));
    }
    return filtered;
  }

  function parseRuleStatements(rulesText) {
    if (!rulesText || typeof rulesText !== 'string') return [];
    return rulesText
      .split(/\n|(?=\s*-\s+)/)
      .map(s => s.replace(/^\s*-\s*/, '').trim())
      .filter(Boolean);
  }

  const OVER_SLOT_PHRASES = [
    'We feel he\'s worth going over slot for.',
    'We think he\'s worth the over-slot investment.',
    'We were comfortable going over to get our guy.',
    'We felt the talent justified the over-slot.',
    'We believe he\'s worth every dollar over slot.',
    'We had to go over to get the guy we wanted.',
    'The talent justified the over-slot commitment.',
    'We were willing to pay over slot for this profile.',
    'Over-slot was the right call for this player.',
    'We went over to secure our guy.',
    'The upside was worth the over-slot.',
    'We felt strongly about going over here.',
    'We stretched to a number we could live with.',
    'Pool-wise, we prioritized landing this profile.',
    'We weren\'t going to lose him on money.',
    'The ask was above slot; we said yes.',
    'We baked in some overage to close it.',
    'Signing cost runs over the assignment; we planned for it.',
    'We cleared the space to get to this number.',
    'It cost more than the slot; we\'re fine with that.',
    'We went past the slot line to finish the deal.',
    'The bonus lands north of slot—intentionally.',
    'We had conviction enough to pay above the pick value.',
    'Dollars over slot, but the board matched the spend.',
    'We matched an aggressive number to keep him in the fold.',
    'Overage here was always part of the scenario.',
    'We traded pool flexibility for the right player.',
    'The check clears above slot; that was the plan.'
  ];
  const UNDER_SLOT_PHRASES = [
    'We like the savings for later picks.',
    'We liked the underslot value here.',
    'The savings give us flexibility later.',
    'We were happy to get him under slot.',
    'Underslot play we were comfortable with.',
    'We were able to get him under and save pool.',
    'The underslot gives us room to maneuver.',
    'We liked the value and the flexibility.',
    'Under slot was a nice bonus for us.',
    'The savings help us later in the draft.',
    'We were comfortable with the underslot.',
    'We got our guy and saved some pool.',
    'We signed under the assignment and banked the difference.',
    'The number came in light relative to slot—by design.',
    'We preserved pool for harder signs down the line.',
    'Underslot here keeps powder dry for Day 2 and 3.',
    'We structured the bonus below the pick value on purpose.',
    'Savings versus slot were part of the overall map.',
    'We took the discount and will redeploy it.',
    'The deal tracks under slot; we\'ll use the margin.',
    'Pool efficiency mattered; this helped.',
    'We left meat on the bone versus the slot line.',
    'Below-slot money with a player we still wanted.',
    'We negotiated to a number under the assignment.',
    'The accounting works out under slot—good outcome.',
    'We bought flexibility with a lighter bonus.',
    'Underslot relative to the pick; we\'ll spend elsewhere.',
    'The contract lands under the slot figure.'
  ];
  const AT_SLOT_PHRASES = [
    'Right at our price point.',
    'Slot value we were comfortable with.',
    'Fits our number perfectly.',
    'Exactly what we had in mind for this pick.',
    'Right where we wanted to be.',
    'Slot value we were comfortable paying.',
    'Hit our number right on the nose.',
    'We were at slot and happy with it.',
    'Slot value fit our board.',
    'Right at slot for this spot.',
    'We were comfortable at slot here.',
    'Fits our number for this pick.',
    'We landed basically on the assignment.',
    'The bonus tracks the slot figure.',
    'No drama—right around the pick value.',
    'We matched the slot without much negotiation.',
    'Clean deal at the assigned number.',
    'The money lines up with MLB\'s slot for this pick.',
    'Straight slot economics.',
    'We stayed in the slot band we modeled.',
    'About what the industry expected for this range.',
    'The dollars match the slot chart.',
    'Neutral spend versus the assignment—works for us.',
    'We executed at slot and moved on.',
    'Roughly slot-neutral from a pool perspective.',
    'The signing aligns with the pick\'s slot value.',
    'We didn\'t need to stretch or shave—slot worked.',
    'Right in the pocket for this selection\'s number.'
  ];

  function getSlotValuePhrase(cost, slotValue) {
    if (cost == null || slotValue == null) return '';
    if (cost > slotValue) return pickVaried(OVER_SLOT_PHRASES, 'slot-over');
    if (cost < slotValue) return pickVaried(UNDER_SLOT_PHRASES, 'slot-under');
    return pickVaried(AT_SLOT_PHRASES, 'slot-at');
  }

  const RANDOM_PICK_NOTES = [
    'Owner overrides the draft director and demands this pick. ',
    'Surprise pick from the war room. ',
    'Scouting staff pushed hard for this selection. ',
    'Front office goes off the board. ',
    'Unexpected choice—internal debate settled at the last moment. ',
    'Area scout had him as a must-get. ',
    'Cross-checker loved the tools. ',
    'National supervisor made the call. ',
    'Analytics department flagged him weeks ago. ',
    'Pro model had him as a steal. ',
    'Ownership stepped in at the last second. ',
    'War room consensus after a long debate. ',
    'Scout\'s gut overrode the board. ',
    'Data and eyes aligned on this one. ',
    'Reached for upside—front office approved. ',
    'Late push from the regional guys carried the room. ',
    'Player development signed off after a second look. ',
    'Medical cleared; baseball ops accelerated the call. ',
    'International scouting crossed paths with domestic and agreed. ',
    'Amateur scouting won the argument on the clock. ',
    'The GM stepped out and the director made the final call. ',
    'Quiet favorite internally—finally surfaced on draft day. ',
    'Cross-check trip sealed what the area guy was saying. ',
    'Video room spotted an adjustment others hadn\'t priced in. ',
    'Strength staff liked the delivery and bought more velo. ',
    'We prioritized signability risk and still took the talent. ',
    'Industry noise didn\'t match what our people saw in person. ',
    'Private workout moved him up the internal list. ',
    'Cold-weather bias hurt the industry rank—not us. ',
    'Two teams passed; we didn\'t overthink it. ',
    'The board shook out messy; we trusted our sequence. ',
    'Not the chalk play—ownership still green-lit it. ',
    'Analytics flagged regression risk; scouts sold the ceiling. ',
    'Models were split; the tie went to the in-person eval. ',
    'We traded short-term PR for long-term upside. ',
    'Slot pressure was tight; we took the swing anyway. ',
    'Minority opinion in the room became the majority at the wire. ',
    'We\'d circled this name if he lasted—he lasted. ',
    'Cross-org intel said he wouldn\'t sign; we disagreed. ',
    'The industry comp was lazy; we see a different athlete. ',
    'We bet on the person as much as the stat line. ',
    'Last-minute medical re-check came back clean—pick stands. ',
    'Coordinator-level meeting last night flipped the order. ',
    'We didn\'t want to leave the draft without this profile. ',
    'Player\'s camp signaled flexibility; we accelerated. ',
    'Older demographic on the board; we prioritized youth here. ',
    'Younger demographic; we prioritized polish and proximity. ',
    'Two-way talk died down—we committed to the primary position. ',
    'Closer to home than most of our picks—relationship mattered. ',
    'Far from home; we think the player travels fine. ',
    'We\'ll slow-play the assignment and develop deliberately. ',
    'Aggressive assignment planned—he can handle the jump. '
  ];

  function applyTeamRules(candidates, team, pickIndex, slotValue) {
    const teamData = state.teams.find(t => t.name === team);
    if (!teamData || !teamData.rules) return { candidates, reason: null, weirdPick: false };

    const statements = parseRuleStatements(teamData.rules);
    const rules = statements.join(' ').toLowerCase();
    const isFirstPick = !state.picks.slice(0, pickIndex).some(p => p.team === team);

    let filtered = candidates;
    let reason = null;

    const isPitcher = p => /^(RHP|LHP|RHP\/|LHP\/)/.test(p.position);
    const isPositionPlayer = p => !isPitcher(p);

    if (isFirstPick) {
      if (Math.random() < state.weirdPickChance) return { candidates, reason: null, weirdPick: true };

      const soft = arr => arr[Math.floor(Math.random() * arr.length)];

      // Specific player: "Will draft Roch Cholowsky with the No. 1 pick X% of the time"
      const playerMatch = rules.match(/will draft ([a-z\s]+) with.*?(\d+)%/);
      if (playerMatch && pickIndex === 0) {
        const namePart = playerMatch[1].trim();
        const pct = parseInt(playerMatch[2], 10) / 100;
        const player = candidates.find(p => p.name.toLowerCase().includes(namePart));
        if (player && Math.random() < pct) {
          const r = soft([
            `We've had our eye on ${player.name} for a while; he was our guy at 1.`,
            `We were locked in on ${player.name} from the start.`,
            `${player.name} was at the top of our board; we're thrilled he was there.`
          ]);
          return { candidates: [player], reason: r, weirdPick: false };
        }
      }

      // "Will always do a big discount pick with first pick"
      if (/big discount pick.*first pick|always.*big discount/.test(rules) && slotValue) {
        filtered = candidates.filter(p => p.cost <= slotValue * 0.5).sort((a, b) => a.rank - b.rank);
        if (filtered.length > 0) {
          const r = soft([
            'We wanted to save pool money for later picks; we liked the value here.',
            'Underslot play to maximize flexibility in later rounds.',
            'We saw an opportunity to go under slot and still get a player we love.'
          ]);
          return { candidates: filtered, reason: r, weirdPick: false };
        }
      }

      // "Will not draft" rules (hard constraints) - first match wins
      if (!reason && /will not draft a pitcher in the first round/.test(rules)) {
        filtered = candidates.filter(isPositionPlayer);
        if (filtered.length > 0) reason = soft([
          'We feel strongly that first-round pitchers carry extra risk; we preferred a bat here.',
          'We\'re cautious with arms in round one; we wanted a position player.',
          'We prefer to build with bats early; this fit our philosophy.'
        ]);
      }
      if (!reason && /will not draft a c,?\s*1b,?\s*or 3b/.test(rules)) {
        filtered = candidates.filter(p => !/^(C|1B|3B)/.test(p.position));
        if (filtered.length > 0) reason = soft([
          'We tend to prioritize up-the-middle or corner outfield with our first pick; we liked the fit.',
          'We prefer premium positions early; this player fits our profile.',
          'We had a strong preference for a different defensive profile; this was our guy.'
        ]);
      }
      if (!reason && /will not draft a high school player with first pick/.test(rules)) {
        filtered = candidates.filter(p => p.class === 'C');
        if (filtered.length > 0) reason = soft([
          'We lean toward college performers with our first pick; we wanted that track record.',
          'We prefer the certainty of college production here.',
          'We like the polish of college players at this spot; he fit our board.'
        ]);
      }
      if (!reason && /will not draft.*jacob lombard|jacob lombard.*tyler bell/.test(rules)) {
        const avoid = ['Jacob Lombard', 'Tyler Bell', 'Sawyer Strosnider', 'Ace Reese', 'Logan Schmidt'];
        filtered = candidates.filter(p => !avoid.some(a => p.name.includes(a)));
        if (filtered.length > 0) reason = soft([
          'We had some players we steered away from; this one fit our board better.',
          'Our process led us elsewhere; we\'re confident in this choice.',
          'We went with our gut on this one; we liked the fit.'
        ]);
      }
      if (!reason && /avoid prep pitchers in round 1|avoid high school pitchers/.test(rules)) {
        filtered = candidates.filter(p => p.class !== 'H' || isPositionPlayer(p));
        if (filtered.length > 0) reason = soft([
          'We feel high school arms are risky in round one; we preferred a bat here.',
          'Prep pitchers carry more risk for us; we went with a position player.',
          'We\'re cautious with prep arms early; we liked the bat here.'
        ]);
      }

      // X% chance rules (probabilistic)
      const pctMatch = rules.match(/(\d+)%\s*chance first pick (?:will be|is)/);
      const pct = pctMatch ? parseInt(pctMatch[1], 10) / 100 : null;
      if (pct !== null && Math.random() < pct && !reason) {
        if (/high school position player/.test(rules)) {
          filtered = candidates.filter(p => p.class === 'H' && isPositionPlayer(p));
          if (filtered.length > 0) reason = soft([
            'We had a strong preference for a high school bat here; he fit our board.',
            'We were leaning toward a prep position player; this was our guy.',
            'We like the upside of high school bats here; he checked every box.'
          ]);
        } else if (/college position player/.test(rules)) {
          filtered = candidates.filter(p => p.class === 'C' && isPositionPlayer(p));
          if (filtered.length > 0) reason = soft([
            'We preferred a college bat here; we liked the track record.',
            'We were leaning toward a polished college position player; he fit.',
            'We value the certainty of college bats at this spot; he was our guy.'
          ]);
        } else if (/college player/.test(rules) || /college performers/.test(rules)) {
          filtered = candidates.filter(p => p.class === 'C');
          if (filtered.length > 0) reason = soft([
            'We lean toward college performers here; we liked the fit.',
            'We preferred the polish of a college player; he was our guy.',
            'We like college track records at this spot; he fit our board.'
          ]);
        } else if (/high school player/.test(rules)) {
          filtered = candidates.filter(p => p.class === 'H');
          if (filtered.length > 0) reason = soft([
            'We were open to the upside of a prep player here; he fit our board.',
            'We liked the ceiling of a high school talent; he was our guy.',
            'We were leaning toward a prep; we liked the projection.'
          ]);
        } else if (/position player/.test(rules)) {
          filtered = candidates.filter(isPositionPlayer);
          if (filtered.length > 0) reason = soft([
            'We had a strong preference for a bat here; he fit our board.',
            'We were leaning toward a position player; he was our guy.',
            'We prefer to build with bats early; he checked every box.'
          ]);
        } else if (/pitcher/.test(rules)) {
          filtered = candidates.filter(isPitcher);
          if (filtered.length > 0) reason = soft([
            'We were open to an arm here; we liked the upside.',
            'We had a strong preference for a pitcher; he was our guy.',
            'We liked the pitching depth in this spot; he fit our board.'
          ]);
        } else if (/hitter/.test(rules)) {
          filtered = candidates.filter(isPositionPlayer);
          if (filtered.length > 0) reason = soft([
            'We had a strong preference for a hitter here; he fit our board.',
            'We were leaning toward a bat; he was our guy.',
            'We like impact bats at this spot; he checked every box.'
          ]);
        }
      }

      // "Will draft X with first pick Y% of time" (no "with the No. 1" phrasing)
      const willDraftPct = rules.match(/will draft (?:a )?(?:high school|college) (?:position )?player (?:with first pick )?(\d+)%/);
      if (willDraftPct && !reason) {
        const threshold = parseInt(willDraftPct[1], 10) / 100;
        if (Math.random() < threshold) {
          if (/high school position player/.test(rules)) {
            filtered = candidates.filter(p => p.class === 'H' && isPositionPlayer(p));
            if (filtered.length > 0) reason = soft([
              'We had a strong preference for a high school bat here; he fit our board.',
              'We were leaning toward a prep position player; this was our guy.'
            ]);
          } else if (/high school player/.test(rules)) {
            filtered = candidates.filter(p => p.class === 'H');
            if (filtered.length > 0) reason = soft([
              'We were open to the upside of a prep here; he fit our board.',
              'We liked the ceiling of a high school talent; he was our guy.'
            ]);
          } else if (/college player/.test(rules)) {
            filtered = candidates.filter(p => p.class === 'C');
            if (filtered.length > 0) reason = soft([
              'We preferred a college player here; he fit our board.',
              'We were leaning toward a polished college performer; he was our guy.'
            ]);
          }
        }
      }

      // "Will draft college player with first pick" / "college players 95%"
      if (!reason && /will draft college player with first pick|college players 95%/.test(rules)) {
        const pct95 = /95%/.test(rules) ? 0.95 : 1;
        if (Math.random() < pct95) {
          filtered = candidates.filter(p => p.class === 'C');
          if (filtered.length > 0) reason = soft([
            'We strongly prefer college players here; we liked the fit.',
            'We lean toward college track records; he was our guy.',
            'We value the polish of college performers; he fit our board.'
          ]);
        }
      }

      // "Will select high school position player or college pitcher" (handles typo "posiiton")
      if (/high school (?:position |posiiton )?player or college pitcher/.test(rules) && !reason) {
        filtered = candidates.filter(p => (p.class === 'H' && isPositionPlayer(p)) || (p.class === 'C' && isPitcher(p)));
        if (filtered.length > 0) reason = soft([
          'We were looking for either a prep bat or a college arm; he fit our profile.',
          'We had a strong preference for a high school position player or college pitcher; he was our guy.',
          'We like that profile—prep bat or college arm—and he fit our board.'
        ]);
      }

      // "Will draft a high school player in rounds 1 or 2 X%" - for first pick, treat as HS chance
      const rounds12Match = rules.match(/high school player in rounds? 1 or 2 (\d+)%/);
      if (rounds12Match && !reason && Math.random() < parseInt(rounds12Match[1], 10) / 100) {
        filtered = candidates.filter(p => p.class === 'H');
        if (filtered.length > 0) reason = soft([
          'We were open to a prep here; he fit our board.',
          'We liked the upside of a high school talent; he was our guy.',
          'We were leaning toward a prep; we liked the projection.'
        ]);
      }
    }

    return { candidates: filtered, reason, weirdPick: false };
  }

  function getTeamDescriptionFlavor(team) {
    const teamData = state.teams.find(t => t.name === team);
    const rules = (teamData?.rules || '').toLowerCase();
    const name = (team || '').toLowerCase();
    const flavors = [];
    if (/college|polished|proven|track record/.test(rules)) flavors.push('college-lean');
    if (/high school|prep|upside|projectable/.test(rules)) flavors.push('upside-lean');
    if (/analytics|data|metrics|model/.test(rules) || /rays|guardians|dodgers/.test(name)) flavors.push('analytics');
    if (/scout|gut|makeup|tools|instinct/.test(rules) || /white sox|royals|tigers/.test(name)) flavors.push('scout-heavy');
    if (/athletic|up-the-middle|defense|premium position/.test(rules)) flavors.push('athletic');
    if (/power|bat|hitter|impact/.test(rules)) flavors.push('power');
    if (/pitcher|arm|mound/.test(rules)) flavors.push('pitching');
    return flavors.length ? flavors[Math.floor(Math.random() * flavors.length)] : 'neutral';
  }

  function getBPAAttributeReasoning(player, team) {
    const isPitcher = /^(RHP|LHP|RHP\/|LHP\/)/.test(player.position);
    const isUpTheMiddle = /^(SS|2B|CF|C)/.test(player.position);
    const isCollege = player.class === 'C';
    const flavor = getTeamDescriptionFlavor(team);

    const OLD_SCHOOL_OPENERS = [
      'Our scouts love the makeup.',
      'Gut says this kid can play.',
      'Five-tool player with plus makeup.',
      'Old-school baseball player.',
      'Instincts are off the charts.',
      'Scouting staff had him as a must-get.',
      'Area scout pounded the table.',
      'The kind of player who wins games.',
      'Baseball IQ shows up every inning.',
      'Internal evals loved the competitiveness.',
      'Looks the part on the field—in a good way.',
      'Plays with pace; scouts trust the instincts.',
      'He passes the eye test with multiple evaluators.',
      'Loud tools when you get him in our environment.',
      'We trust the hands and the internal clock.',
      'Makeup and work habits checked every box.',
      'The in-person look matched the summer noise.',
      'He\'s wired like a guy who figures it out.',
      'Scouting consensus was stronger than the industry\'s.',
      'We buy the athlete and the baseball feel.',
      'Old-school profile with real present ability.',
      'The cross-check came back enthusiastic.',
      'Our people have seen the swing hold vs. velocity.',
      'He plays with an edge we want in the org.'
    ];
    const NEW_SCHOOL_OPENERS = [
      'The data supports this pick.',
      'Projection models favor the upside.',
      'Analytics-driven selection.',
      'Metrics align with our board.',
      'Statcast loves the profile.',
      'Pro model had him as a steal.',
      'Data and eyes aligned on this one.',
      'Swing decisions grade out elite.',
      'Batted-ball quality backs up the hit tool.',
      'Stuff metrics and shape both play.',
      'Command numbers trend the right direction.',
      'Athletic testing matched what video showed.',
      'Age-relative performance stands out.',
      'Our projections land higher than public lists.',
      'Exit velo and approach both grade.',
      'Pitch mix and usage fit how we develop arms.',
      'Plate discipline numbers are real, not noise.',
      'Defensive metrics and timing agree with scouts.',
      'We weighted the underlying more than the surface stats.',
      'Comparable-player comps undersell the physicality.',
      'The model liked him before the industry caught up.',
      'Variance-adjusted, he\'s a value here.',
      'Risk is priced in; upside isn\'t.',
      'We ran it every which way—still like the bet.'
    ];
    const NEUTRAL_OPENERS = [
      'Best player on our board.',
      'We had him higher than most.',
      'Strong value at this spot.',
      'Best available at a position of need.',
      'We like the fit here.',
      'Fits our system.',
      'Clean fit with how we draft.',
      'We didn\'t overthink it—he was next.',
      'The sequence worked out for us.',
      'Board and pool lined up.',
      'We\'ll take the talent and figure out the path.',
      'This was the name we hoped would last.',
      'Value and need overlapped.',
      'We feel good about the process leading here.',
      'The industry had noise; we stayed disciplined.',
      'Internal rank and slot finally met.',
      'We\'ve tracked him a long time.',
      'No surprises—this was in our tier.',
      'We trust our board at this range.'
    ];

    let openers = NEUTRAL_OPENERS;
    if (flavor === 'analytics') openers = [...NEW_SCHOOL_OPENERS, ...NEUTRAL_OPENERS];
    else if (flavor === 'scout-heavy') openers = [...OLD_SCHOOL_OPENERS, ...NEUTRAL_OPENERS];
    else if (Math.random() < 0.4) openers = [...OLD_SCHOOL_OPENERS, ...NEW_SCHOOL_OPENERS, ...NEUTRAL_OPENERS];

    const PITCHER_PHRASES = [
      'Best arm on the board.', 'Top pitcher available.', 'Elite upside on the mound.',
      'Premier pitching talent.', 'Front-of-rotation potential.', 'Power stuff that plays.',
      'Premium velocity with feel.', 'Three pitches that all grade plus.', 'Ace ceiling.',
      'Swing-and-miss stuff.', 'Deceptive delivery.', 'Plus fastball, plus secondary.',
      'The fastball plays at the top of the zone.',
      'Secondaries flash swing-and-miss already.',
      'Starter traits with a reliever\'s aggression.',
      'Athletic delivery; repeatable enough to start.',
      'Arm speed gives us something to dream on.',
      'He generates whiffs without gimmicks.',
      'Pitch design fits what our dev staff does well.',
      'Stuff ticks up in short bursts—projection left.',
      'He attacks hitters; we like the mentality.',
      'Strike-throwing trend is encouraging.',
      'Miss bats in-zone—not just chase.',
      'Frame and extension help the stuff play up.',
      'He can sequence; not just a thrower.',
      'Innings build cleanly—no red flags mechanically.',
      'Track record vs. good competition holds up.',
      'We see mid-rotation floor with more in the tank.',
      'The arsenal depth is the selling point.'
    ];
    const UTM_PHRASES = [
      'Premium up-the-middle talent.', 'Best defender available.', 'Elite athleticism at a premium position.',
      'Sticks at short long-term.', 'Center fielder with impact.', 'Catches everything.',
      'Premium position, premium tools.', 'Glove-first with bat upside.', 'Up-the-middle athlete.',
      'Plus runner, plus defender.', 'Athletic enough to stay up the middle.', 'Impact defender.',
      'Range plays; arm strength is there.',
      'Foot speed should hold as he matures.',
      'Hands and feet work together—clean actions.',
      'He can slow the game down defensively.',
      'Throws are accurate; clock is solid.',
      'Reads off the bat look advanced for the age.',
      'We think he stays at a premium spot.',
      'Athleticism buys mistakes offensively.',
      'Catch-and-throw skillset is real.',
      'He impacts the game even when the bat is quiet.',
      'Up-the-middle profile with offensive upside.',
      'Instincts in space—plus defender toolkit.',
      'He\'s a run-prevention asset right away.',
      'The glove raises the offensive floor.',
      'Double-play turns are crisp; internal clock shows.',
      'We see a long-term anchor on the dirt or grass.'
    ];
    const CORNER_PHRASES = [
      'Best bat available.', 'Impact offensive upside.', 'Power potential at the plate.',
      'Runs into one.', 'Drives the ball to all fields.', 'Impact bat with defensive versatility.',
      'Power that plays in the middle of the order.', 'Bat-first with enough glove.',
      'Middle-of-the-order bat.', 'Impact power from the left side.', 'Plus raw power.',
      'Barrel frequency shows up in games—not just BP.',
      'He can do damage without selling out.',
      'Approach is tighter than the stat line suggests.',
      'He punishes mistakes; discipline can still grow.',
      'Physicality in the box stands out.',
      'Swing path works for our hitting philosophy.',
      'He elevates when he wants to—impact loft.',
      'Contact quality grades even when AVG wavers.',
      'Corner profile with real offensive ceiling.',
      'He changes innings with one swing.',
      'Strength plays; swing decisions are next chapter.',
      'We buy the bat speed and the adjustability.',
      'There\'s 30-homer DNA if the approach firms.',
      'He profiles as a run producer in our park.',
      'Corner defense is playable; bat carries him.',
      'Two-way value if he maxes the hit tool.'
    ];
    const posKey = isPitcher ? 'bpa-pos-p' : isUpTheMiddle ? 'bpa-pos-u' : 'bpa-pos-c';
    const posPhrases = isPitcher ? PITCHER_PHRASES : isUpTheMiddle ? UTM_PHRASES : CORNER_PHRASES;

    const COLLEGE_PHRASES = [
      'Polished college performer.', 'Proven track record.', 'Major conference experience.',
      'Advanced for his age.', 'Track record against top competition.', 'Pro-ready approach.',
      'College bat that will move fast.', 'Polished approach at the plate.',
      'SEC/Big 12 tested.', 'Performed against the best.', 'College track record.',
      'Weekend starter vs. Friday arms—real data.',
      'He\'s been scouted heavily—no mystery box.',
      'Mature approach; not a raw projection only.',
      'Performance trended the right way year over year.',
      'He handled velocity and spin in conference play.',
      'Older profile with less guesswork.',
      'Approach travels; not just a stat-padding split.',
      'We like the certainty relative to the class.',
      'He\'s closer to contributing than most here.',
      'Track record vs. draft-eligible arms matters.',
      'College production backs the tools.',
      'He\'s been in the fire—responds to failure.',
      'Physical maturity is further along.',
      'Short-season assignment is realistic.',
      'Pitch recognition already shows up.',
      'He\'s been coached hard—coachable profile.'
    ];
    const HS_PHRASES = [
      'High ceiling prep talent.', 'Projectable upside.', 'Young talent with room to grow.',
      'Impact potential.', 'Projectable frame.', 'High-risk, high-reward profile.',
      'Ceiling play.', 'Room to add strength.', 'Prep bat with huge upside.',
      'Youngest player on our board.', 'Dream on the tools.',
      'Body still has stages left.',
      'Athleticism should stick as he fills out.',
      'We\'re buying the long runway.',
      'Young bat—timing and strength will come.',
      'The upside is the story; patience required.',
      'He flashes now; consistency is the project.',
      'Prep competition noise—look at the athlete.',
      'Frame suggests more power is coming.',
      'He\'s still learning how strong he is.',
      'Development staff is excited about the canvas.',
      'Risk is real; reward matches it.',
      'We\'ll slow-play the assignment intentionally.',
      'He needs reps, not a rework.',
      'Youth shows up in chase—teachable.',
      'The tool set is loud enough to bet on.',
      'We see a different player in three years.'
    ];
    const pedigreePhrases = isCollege ? COLLEGE_PHRASES : HS_PHRASES;

    const TOP10_PHRASES = [
      'Consensus top-10 talent.', 'Elite prospect who fell.', 'Too much talent to pass up.',
      'Steal at this spot.', 'Shouldn\'t have been here.', 'Elite talent, elite value.',
      'No-brainer at this pick.', 'Franchise-type talent.',
      'Blue-chip profile—rare air.',
      'We didn\'t expect him to be available.',
      'The industry will ask how he lasted.',
      'Impact talent you don\'t overthink.',
      'This is the tier you sprint the card.',
      'Star-level upside if it clicks.',
      'He changes the talent base of the org.',
      'We\'re ecstatic the board broke this way.',
      'Premium pick; premium outcome.',
      'The phone line got hot when he was on the board.',
      'Rare combo of floor and ceiling here.',
      'We had a top-of-the-board grade.',
      'This is why you don\'t get cute early.'
    ];
    const ROUND1_PHRASES = [
      'Strong value at this spot.', 'First-round caliber talent.', 'Best available at a position of need.',
      'We had him in the first round.', 'Fits our board perfectly.', 'First-round talent who fell.',
      'Comp round value.', 'We had a first-round grade.',
      'Day-one talent at a later number.',
      'We never thought he\'d slide this far.',
      'First-round tools; we\'ll take the discount.',
      'He was in our tier from the spring.',
      'The industry had him higher—so did we.',
      'Clean profile for this range.',
      'We had a cushion on the internal rank.',
      'This is a first-round athlete in our eyes.',
      'We\'re comfortable calling him a round-one guy.',
      'The board value matches the pick slot.',
      'He profiles as an early contributor eventually.',
      'We would have considered him much earlier.',
      'The fall stopped here—good for us.',
      'This is how boards get silly—in our favor.',
      'We\'ll sign him like the talent he is.'
    ];
    const LATER_PHRASES = [
      'Best player on our board.', 'Strong fit for our system.', 'We like the upside here.',
      'Our guys had him higher.', 'Development play.', 'We believe in the profile.',
      'Over-slot talent.', 'We see something the industry missed.', 'Sleeper on our board.',
      'This range is about conviction and dev time.',
      'We\'ll invest coaching reps where it matters.',
      'The industry slept on the second half.',
      'We trust our area and cross-check here.',
      'Value emerges when lists get noisy.',
      'He\'s a lottery ticket with real signals.',
      'We like the swing of outcomes at this cost.',
      'Depth pick with real ceiling.',
      'This is where scouting pays rent.',
      'We see a path if the body cooperates.',
      'Medical and makeup checked out—bet on skill.',
      'Late-round helium isn\'t always smoke.',
      'We modeled the bonus and still liked the upside.',
      'He\'s a pop-up name internally.',
      'Industry rank lagged our live looks.',
      'We\'ll be patient—this isn\'t a rush pick.',
      'Good athlete for this point in the draft.',
      'We buy one loud tool and coach the rest.',
      'This is pool-efficient risk.',
      'We\'d rather bet on traits than safety this late.'
    ];
    const rankKey = player.rank <= 10 ? 'bpa-rank-t10' : player.rank <= 30 ? 'bpa-rank-r1' : 'bpa-rank-late';
    const rankPhrases = player.rank <= 10 ? TOP10_PHRASES : player.rank <= 30 ? ROUND1_PHRASES : LATER_PHRASES;

    const CLOSER_PHRASES = [
      'We\'ll get him into our dev pipeline immediately.',
      'Player development is fired up about the fit.',
      'Signing and assignment next—then development.',
      'We have a plan for the first pro summer.',
      'The org depth chart has room for this profile.',
      'We\'ll match innings and reps to his readiness.',
      'Instruction staff already watched the video package.',
      'He\'s a culture fit—clubhouse will like him.',
      'We\'ll monitor workload and progression carefully.',
      'This aligns with how we allocate coaching time.',
      'Minor-league staff signed off on the path.',
      'We see a clean onboarding in rookie ball.',
      'The player development plan is straightforward.',
      'We\'re not forcing a timeline—right player, right process.',
      'Scouting and PD are on the same page.',
      'We bought the person as much as the player.',
      'Medical and strength teams are aligned.',
      'This is a bet our player dev can maximize.',
      'We trust the infrastructure with this archetype.',
      'Long-term value over short-term headlines.'
    ];

    const parts = [
      pickVaried(openers, 'bpa-opener'),
      pickVaried(posPhrases, posKey),
      pickVaried(pedigreePhrases, 'bpa-pedigree'),
      pickVaried(rankPhrases, rankKey)
    ];
    if (Math.random() < 0.28) parts.pop();
    if (Math.random() < 0.18) parts.shift();
    if (Math.random() < 0.12 && parts.length) parts.push(pickVaried(CLOSER_PHRASES, 'bpa-closer'));
    const joiner = Math.random() < 0.16 ? '. ' : ' ';
    return parts.filter(Boolean).join(joiner);
  }

  function pickFromTopWithRandomness(candidates, topN = 5) {
    if (!candidates.length) return null;
    const top = candidates.slice(0, Math.min(topN, candidates.length));
    if (top.length === 1) return top[0];
    const weights = top.map((_, i) => Math.pow(0.6, i));
    const total = weights.reduce((a, b) => a + b, 0);
    let r = Math.random() * total;
    for (let i = 0; i < top.length; i++) {
      r -= weights[i];
      if (r <= 0) return top[i];
    }
    return top[0];
  }

  function getUndraftedByCostAsc() {
    return state.players
      .filter(p => isPlayerSelectableInPool(p))
      .sort((a, b) => a.cost - b.cost);
  }

  /** Prefer players whose listed cost fits current remaining pool (avoids burning the last-round reserve). */
  function firstAffordableUndrafted(team, pickIndex, slotValue) {
    const maxSpend = getMaxSpendThisPick(slotValue, team, pickIndex);
    const byCost = getUndraftedByCostAsc();
    const affordable = byCost.filter(p => p.cost <= maxSpend);
    return affordable[0] || null;
  }

  function aiPick(pick, slotValue, pickIndex) {
    let candidates = getAvailablePlayers(slotValue, pick.team, pickIndex);
    const maxRank = getMaxRankForRecommendations(pick.pick);
    candidates = candidates.filter(p => p.rank <= maxRank);
    if (candidates.length === 0) candidates = getAvailablePlayers(slotValue, pick.team, pickIndex);
    if (candidates.length === 0) {
      const maxSpend = getMaxSpendThisPick(slotValue, pick.team, pickIndex);
      candidates = getUndraftedByCostAsc().filter(p => p.cost <= maxSpend);
    }
    let { candidates: filtered, reason, weirdPick } = applyTeamRules(candidates, pick.team, pickIndex, slotValue);
    if (filtered.length === 0) filtered = candidates;
    let chosen = pickFromTopWithRandomness(filtered, 5) || filtered[0] || candidates[0];
    if (!chosen) chosen = firstAffordableUndrafted(pick.team, pickIndex, slotValue);
    if (!chosen) chosen = makeRandomSeniorSignPlayer(pickIndex);
    const reached = chosen && filtered[0] && chosen.rank !== filtered[0].rank;
    let baseReason = reason || (chosen ? getBPAAttributeReasoning(chosen, pick.team) : null);
    const randomNote = weirdPick || reached
      ? pickVaried(RANDOM_PICK_NOTES, 'random-pick-note')
      : '';
    return {
      player: chosen,
      reason: randomNote + (baseReason || ''),
      weirdEvent: weirdPick
    };
  }

  function processNextPick() {
    if (state.currentPickIndex >= state.picks.length) {
      restorePickDelayAfterSimulate();
      $btnRestart?.classList.add('hidden');
      $status.textContent = 'DRAFT COMPLETE.';
      $status.classList.remove('picking');
      $currentPick.classList.add('hidden');
      state._pendingAdvance = null;
      state._pickTimeoutId = null;
      updatePauseButtonUI();
      if ($aiReasoning) {
        $aiReasoning.classList.add('hidden');
        const teamEl = $aiReasoning.querySelector('#ai-reasoning-team');
        if (teamEl) {
          teamEl.innerHTML = '';
          teamEl.classList.add('hidden');
        }
        const textEl = $aiReasoning.querySelector('#ai-reasoning-text');
        if (textEl) {
          textEl.textContent = '';
          textEl.classList.remove('reasoning-appear');
        }
      }
      const $budgetDone = $('human-budget-summary');
      if ($budgetDone) $budgetDone.classList.add('hidden');
      if ($draftSide) $draftSide.classList.add('hidden');
      if ($draft) $draft.classList.add('draft-finished');
      renderDraftCompleteBragSheets();
      if ($draftComplete) {
        $draftComplete.classList.remove('hidden');
        requestAnimationFrame(() => {
          $draftComplete.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
      }
      renderRoundBreadcrumbs();
      return;
    }

    const pick = state.picks[state.currentPickIndex];
    const newsPrefix = consumeDraftNewsFlash();
    ensureRoundVisible(pick.round);
    const { row } = state.pickIndexToRow[state.currentPickIndex];
    const isHuman = state.humanTeams.has(pick.team);

    renderRoundBreadcrumbs();
    $board.querySelectorAll('.board-row.current').forEach(r => {
      r.classList.remove('current', 'bg-red-900/20');
      r.querySelector('div:last-child')?.classList.remove('bg-red-900/10');
    });
    row.classList.add('current', 'bg-red-900/20');
    row.querySelector('div:last-child')?.classList.add('bg-red-900/10');
    row.scrollIntoView({ behavior: state.pickDelay === 0 ? 'auto' : 'smooth', block: 'end' });

    if (isHuman) {
      state._pendingAdvance = null;
      state._pickTimeoutId = null;
      $status.textContent = newsPrefix + `Waiting for ${pick.team} to pick...`;
      $status.classList.add('picking');
      $currentPick.classList.remove('hidden');
      if ($aiReasoning) $aiReasoning.classList.add('hidden');
      updatePauseButtonUI();
      showHumanPickUI(pick);
    } else {
      $status.textContent = newsPrefix + `${pick.team} are picking...`;
      $status.classList.add('picking');
      $currentPick.classList.add('hidden');
      const result = aiPick(pick, pick.value, state.currentPickIndex);
      const prefCost = result.player ? getEffectiveSigningCost(result.player, pick, pick.value) : null;
      const poolResolved = resolvePickForPool(pick, result.player, prefCost, state.currentPickIndex);
      const displayPlayer = poolResolved.player;
      const displayCost = displayPlayer ? poolResolved.effectiveCost : null;
      state._pendingAdvance = { pick, result, row, effectiveCost: prefCost };
      updatePauseButtonUI();
      if ($aiReasoning) {
        if (state.pickDelay > 0) {
          $aiReasoning.classList.remove('hidden');
          $aiReasoning.classList.toggle('weird-event', !!result.weirdEvent);
          const badge = $aiReasoning.querySelector('.weird-event-label');
          if (badge) badge.classList.toggle('hidden', !result.weirdEvent);
          const teamEl = $aiReasoning.querySelector('#ai-reasoning-team');
          teamEl.innerHTML = '';
          teamEl.classList.add('hidden');
          let reasonText = result.reason || (displayPlayer ? 'Best player available' : 'Passing');
          if (displayPlayer && result.player && displayPlayer.name === 'Random senior sign' && result.player.name !== 'Random senior sign') {
            reasonText = (reasonText ? reasonText + ' ' : '') + 'Pool over budget — random senior sign.';
          }
          if (displayPlayer) {
            const slotPhrase = getSlotValuePhrase(displayCost, pick.value);
            if (slotPhrase) reasonText = reasonText + (reasonText ? ' ' : '') + slotPhrase;
          }
          const costClass = displayPlayer && pick.value != null
            ? (displayCost > pick.value ? 'text-overslot-red' : displayCost < pick.value ? 'text-green-400' : 'text-white')
            : 'text-white';
          const quotedReason = '"' + escapeHtml(reasonText) + '"';
          const headerContent = displayPlayer
            ? `<div class="flex items-center gap-4 flex-wrap">${teamLogoHtml(pick.teamId, 'w-20 h-20')}<div class="min-w-0 flex-1"><span class="text-white font-semibold text-2xl">#${displayPlayer.rank} ${escapeHtml(displayPlayer.name)} ${escapeHtml(displayPlayer.position)}, ${escapeHtml(displayPlayer.school)}</span> <span class="${costClass} font-medium text-2xl">${fmt(displayCost)}</span></div>${playerPhotoHtml(displayPlayer, 'w-24 h-24', true)}</div>`
            : `<div class="flex items-center gap-4">${teamLogoHtml(pick.teamId, 'w-20 h-20')}<span class="text-neutral-400 text-2xl">Passing</span></div>`;
          const textEl = $aiReasoning.querySelector('#ai-reasoning-text');
          textEl.innerHTML = `<div class="ai-reasoning-pick flex flex-col gap-3">${headerContent}<blockquote class="ai-reasoning-quote text-white text-xl leading-relaxed m-0 border-l-2 border-overslot-red/50 pl-3">${quotedReason}</blockquote></div>`;
          textEl.classList.remove('reasoning-appear');
          textEl.offsetHeight;
          textEl.classList.add('reasoning-appear');
        } else {
          $aiReasoning.classList.add('hidden');
        }
      }
      state._pickTimeoutId = setTimeout(() => {
        state._pickTimeoutId = null;
        if (state.paused) return;
        const pending = state._pendingAdvance;
        if (!pending) return;
        state._pendingAdvance = null;
        if ($aiReasoning) {
          $aiReasoning.classList.remove('weird-event');
          $aiReasoning.querySelector('.weird-event-label')?.classList.add('hidden');
        }
        recordPick(pending.pick, pending.result.player, pending.row, pending.result.reason, { weirdEvent: pending.result.weirdEvent, isHuman: false, effectiveCost: pending.effectiveCost });
        state.currentPickIndex++;
        maybeHsGoToCollegeAfterRound2();
        renderHumanBudgetSummary();
        processNextPick();
      }, state.pickDelay);
    }
  }

  function getTeamRules(team) {
    const t = state.teams.find(x => x.name === team);
    return t && t.rules ? t.rules.trim() : null;
  }

  function shortName(name) {
    const parts = (name || '').trim().split(/\s+/);
    return parts.length > 1 ? parts[parts.length - 1] : name || '';
  }

  function renderHumanBudgetSummary() {
    const el = $('human-budget-summary');
    if (!el || state.humanTeams.size === 0) return;
    el.classList.remove('hidden');
    el.innerHTML = '';
    el.className = 'p-3 bg-overslot-grey border border-overslot-grey-border flex flex-col gap-3 overflow-y-auto';
    const currentPick = state.picks[state.currentPickIndex];
    state.humanTeams.forEach(team => {
      const teamData = state.teams.find(t => t.name === team);
      const teamPicks = state.picks.filter(p => p.team === team);
      const selections = state.teamPicks[team] || [];
      const remaining = getTeamRemaining(team);
      const picksRemaining = teamPicks.length - selections.length;
      const section = document.createElement('div');
      section.className = 'flex flex-col gap-2';
      const header = document.createElement('div');
      header.className = 'font-semibold text-overslot-red text-sm flex items-center gap-2';
      header.innerHTML = teamLogoHtml(teamData?.id, 'w-6 h-6') + escapeHtml(team);
      section.appendChild(header);
      const cardsRow = document.createElement('div');
      cardsRow.className = 'flex flex-wrap gap-2';
      teamPicks.forEach((pick, i) => {
        const sel = selections[i];
        const isCurrent = currentPick && currentPick.team === team && pick.pick === currentPick.pick;
        const card = document.createElement('div');
        card.className = 'pick-card flex flex-col w-24 flex-shrink-0 p-2 border bg-overslot-black/50 overflow-hidden ' + (isCurrent ? 'border-overslot-red ring-1 ring-overslot-red' : 'border-overslot-grey-border');
        const costClass = sel && sel.cost != null ? (sel.cost > pick.value ? 'text-overslot-red' : sel.cost < pick.value ? 'text-green-400' : 'text-white') : '';
        const playerLine = sel
          ? (sel.name === 'Random senior sign'
            ? escapeHtml(sel.name)
            : (sel.rank != null ? `#${sel.rank} ${escapeHtml(sel.name)}` : escapeHtml(sel.name)))
          : '';
        const costLine = sel && sel.cost != null ? `<span class="${costClass} text-xs">${fmt(sel.cost)}</span>` : '';
        const playerContent = sel
          ? (playerLine ? playerLine + (costLine ? '<br>' + costLine : '') : '—')
          : '—';
        card.innerHTML = `
          <div class="inline-flex items-center gap-1 mb-1 -ml-2 -mt-2"><span class="bg-overslot-red text-white text-[10px] font-bold min-w-[1.75rem] h-5 px-1 flex items-center justify-center flex-shrink-0">${pick.pick}</span><span class="text-white text-xs font-bold">${fmt(pick.value)}</span></div>
          <div class="text-xs flex-1 min-h-[2.5rem] break-words ${sel ? 'text-white' : 'text-neutral-500'}">${playerContent}</div>
        `;
        cardsRow.appendChild(card);
      });
      section.appendChild(cardsRow);
      const footer = document.createElement('div');
      footer.className = 'text-neutral-100 text-xs';
      footer.textContent = `${fmt(remaining)} left · ${picksRemaining} pick${picksRemaining !== 1 ? 's' : ''} left`;
      section.appendChild(footer);
      el.appendChild(section);
    });
  }

  function getTokensFromPositionString(pos) {
    if (!pos || typeof pos !== 'string') return [];
    return pos.split(/[\/]/).map(s => s.trim().toUpperCase()).filter(Boolean);
  }

  /** Aligns with team-fit logic: primary slot is pitching if position starts with RHP/LHP. */
  function isPitcherPlayerProfile(p) {
    return /^(RHP|LHP|RHP\/|LHP\/)/.test(p.position || '');
  }

  function tokenIsPitcherOnly(t) {
    return t === 'RHP' || t === 'LHP';
  }

  /** True if the player has a mound profile (listed arm or RHP/LHP token). */
  function hasPitcherSide(p) {
    if (isPitcherPlayerProfile(p)) return true;
    return getTokensFromPositionString(p.position).some(tokenIsPitcherOnly);
  }

  /** True if the player has a non-pitching position (e.g. OF on RHP/OF). Pure RHP/LHP only → false. */
  function hasHitterSide(p) {
    const tokens = getTokensFromPositionString(p.position);
    if (tokens.length === 0) return !isPitcherPlayerProfile(p);
    return tokens.some(t => !tokenIsPitcherOnly(t));
  }

  function positionMatchesQuickFilter(player, posVal) {
    if (!posVal || posVal === 'all') return true;
    if (posVal === 'hitter') return hasHitterSide(player);
    if (posVal === 'pitcher') return hasPitcherSide(player);
    const want = String(posVal).toUpperCase();
    return getTokensFromPositionString(player.position).includes(want);
  }

  function pathMatchesQuickFilter(player, pathVal) {
    if (!pathVal || pathVal === 'all') return true;
    if (pathVal === 'college') return player.class === 'C';
    if (pathVal === 'hs') return player.class === 'H';
    return true;
  }

  function passesPlayerQuickFilters(player) {
    const posSel = $('player-filter-position');
    const pathSel = $('player-filter-path');
    const posVal = posSel ? posSel.value : 'all';
    const pathVal = pathSel ? pathSel.value : 'all';
    return pathMatchesQuickFilter(player, pathVal) && positionMatchesQuickFilter(player, posVal);
  }

  function uniquePositionTokensForFilter() {
    const seen = new Set();
    state.players.forEach(p => {
      getTokensFromPositionString(p.position).forEach(t => seen.add(t));
    });
    return [...seen].sort((a, b) => a.localeCompare(b));
  }

  function populatePlayerFilterPositionSelect() {
    const posSel = $('player-filter-position');
    if (!posSel) return;
    posSel.innerHTML = '';
    const add = (v, label) => {
      const o = document.createElement('option');
      o.value = v;
      o.textContent = label;
      posSel.appendChild(o);
    };
    add('all', 'All positions');
    add('hitter', 'Hitters');
    add('pitcher', 'Pitchers');
    uniquePositionTokensForFilter().forEach(t => {
      add(t, t);
    });
    posSel.value = 'all';
  }

  function showHumanPickUI(pick) {
    $currentPick.classList.remove('hidden');
    const pool = getTeamPool(pick.team);
    const spent = getTeamSpent(pick.team);
    const remaining = getTeamRemaining(pick.team);
    const maxThisPick = getMaxSpendThisPick(pick.value, pick.team, state.currentPickIndex);
    const picksLeft = getPicksRemaining(pick.team, state.currentPickIndex);
    const teamData = state.teams.find(t => t.name === pick.team);
    const futureReserve = getFuturePickReserve(picksLeft);
    const reserveNote = picksLeft > 1
      ? ` · reserves ${fmt(futureReserve)} for ${picksLeft - 1} pick${picksLeft - 1 !== 1 ? 's' : ''} after this`
      : '';
    const headerArea = $currentPick.querySelector('#pick-header-area');
    if (headerArea) {
      headerArea.innerHTML = `
        <div class="flex items-center gap-3 flex-wrap">
          <div class="flex items-center gap-2">
            ${teamLogoHtml(pick.teamId || teamData?.id, 'w-8 h-8')}
            <span class="text-overslot-red font-semibold">Pick #${pick.pick} ${escapeHtml(pick.team)}</span>
          </div>
          <div class="flex items-center gap-4 text-xs text-neutral-200 border-l border-overslot-grey-border pl-3">
            <span>Pool ${fmt(pool)}</span>
            <span>Spent ${fmt(spent)}</span>
            <span class="text-white font-medium">Remaining ${fmt(remaining)}</span>
            <span class="text-overslot-red/90" title="Pool left if you reserve money for remaining picks (AI uses this)">Plan max ${fmt(maxThisPick)}</span>${reserveNote ? `<span class="text-neutral-400">${reserveNote}</span>` : ''}
          </div>
        </div>`;
    }

    const available = getAvailablePlayers(pick.value, pick.team, state.currentPickIndex);
    const fitSorted = getTeamFitCandidates(available, pick.team, state.currentPickIndex, pick.value);
    const rankSorted = [...available].sort((a, b) => a.rank - b.rank);
    const filterInput = $('player-filter');
    if (filterInput) filterInput.value = '';
    populatePlayerFilterPositionSelect();
    const pathSel = $('player-filter-path');
    if (pathSel) pathSel.value = 'all';

    const labelEl = $('player-list-label');
    const availableEl = $availablePlayers;

    const playerSelectionEl = document.querySelector('.player-selection');
    if (playerSelectionEl && !playerSelectionEl.dataset.playerFilterSelectListeners) {
      playerSelectionEl.dataset.playerFilterSelectListeners = '1';
      playerSelectionEl.addEventListener('change', e => {
        const id = e.target && e.target.id;
        if (id === 'player-filter-position' || id === 'player-filter-path') {
          state._topViewRefresh?.();
        }
      });
    }

    function updateTopViewButtons() {
      document.querySelectorAll('.top-view-btn').forEach(btn => {
        btn.classList.toggle('selected', btn.dataset.mode === state.topViewMode);
      });
    }

    function renderList(filter) {
      const q = (filter || '').trim().toLowerCase();
      const playerCardClass = 'flex items-center gap-3 py-2 px-2 cursor-pointer hover:bg-overslot-grey border border-transparent hover:border-overslot-grey-border text-sm';

      const renderPlayers = (players, chalk) => {
        if (!availableEl) return;
        availableEl.innerHTML = '';
        players.forEach(p => {
          const div = document.createElement('div');
          div.className = playerCardClass;
          const isChalk = chalk && p.rank === chalk.rank;
          const rankClass = isChalk ? 'rank-badge rank-badge--chalk' : 'rank-badge';
          const baseListCost = (p.class === 'C' && (isCompAOrRound2Or3(pick) || isRound1(pick))) ? pick.value : p.cost;
          const listCost = p.class === 'C' ? applyCollegeRankVsPickToCost(baseListCost, p, pick) : baseListCost;
          const costClass = listCost > pick.value ? 'text-overslot-red' : listCost < pick.value ? 'text-green-400' : 'text-white';
          div.innerHTML = `${playerPhotoHtml(p)}<span class="${rankClass}">${p.rank}</span><span>${escapeHtml(p.position)} ${escapeHtml(p.name)}, ${escapeHtml(p.school)} » <span class="${costClass}">${fmt(listCost)}</span></span>`;
          div.dataset.rank = String(p.rank);
          div.addEventListener('click', () => makeHumanPick(p));
          availableEl.appendChild(div);
        });
      };

      function textMatchesPlayer(p, query) {
        if (!query) return true;
        return p.name.toLowerCase().includes(query) ||
          (p.school || '').toLowerCase().includes(query) ||
          (p.position || '').toLowerCase().includes(query);
      }

      const rankFiltered = rankSorted.filter(passesPlayerQuickFilters);
      const fitFiltered = fitSorted.filter(passesPlayerQuickFilters);

      if (q) {
        const pool = fitSorted.filter(passesPlayerQuickFilters).filter(p => textMatchesPlayer(p, q));
        const orderedFiltered = [...pool].sort((a, b) => a.rank - b.rank);
        if (labelEl) labelEl.textContent = `Search results (${orderedFiltered.length})`;
        const searchHighest = orderedFiltered.length
          ? orderedFiltered.reduce((best, p) => (!best || p.rank < best.rank ? p : best))
          : null;
        renderPlayers(orderedFiltered, searchHighest);
      } else {
        const labelText = state.topViewMode === 'highestRanked' ? 'Highest ranked:' : 'Best fits for ' + pick.team + ':';
        if (labelEl) labelEl.textContent = rankFiltered.length ? labelText : 'No players match filters';
        if (!rankFiltered.length) {
          renderPlayers([], null);
          return;
        }
        if (state.topViewMode === 'highestRanked') {
          const chalk = rankFiltered[0];
          renderPlayers(rankFiltered, chalk);
        } else {
          const highestRanked = rankFiltered[0];
          const orderedAvailable = [highestRanked, ...fitFiltered.filter(p => p.rank !== highestRanked.rank)];
          renderPlayers(orderedAvailable, highestRanked);
        }
      }
    }

    state._topViewRefresh = () => { updateTopViewButtons(); renderList(filterInput?.value); };
    updateTopViewButtons();
    renderList();
    if (filterInput) {
      filterInput.oninput = () => renderList(filterInput.value);
    }
    const btnHighest = $('btn-show-highest');
    const btnBestfit = $('btn-show-bestfit');
    if (btnHighest && !btnHighest.dataset.listenerAdded) {
      btnHighest.dataset.listenerAdded = '1';
      btnHighest.addEventListener('click', () => {
        state.topViewMode = 'highestRanked';
        state._topViewRefresh?.();
      });
    }
    if (btnBestfit && !btnBestfit.dataset.listenerAdded) {
      btnBestfit.dataset.listenerAdded = '1';
      btnBestfit.addEventListener('click', () => {
        state.topViewMode = 'bestFit';
        state._topViewRefresh?.();
      });
    }
  }

  function makeHumanPick(player) {
    const pick = state.picks[state.currentPickIndex];
    const row = state.pickIndexToRow[state.currentPickIndex]?.row;
    if (!row) return;
    let chosen = player;
    let reason = 'Human selection';
    if (!chosen) {
      const result = aiPick(pick, pick.value, state.currentPickIndex);
      chosen = result.player || firstAffordableUndrafted(pick.team, state.currentPickIndex, pick.value);
      if (!chosen) chosen = makeRandomSeniorSignPlayer(state.currentPickIndex);
      reason = result.reason || 'Best player available';
    }
    recordPick(pick, chosen, row, reason, { isHuman: true });
    state.currentPickIndex++;
    maybeHsGoToCollegeAfterRound2();
    $currentPick.classList.add('hidden');
    renderHumanBudgetSummary();
    processNextPick();
  }

  function recordPick(pick, player, row, reason, opts = {}) {
    const pickIndex = state.currentPickIndex;
    const prefCost = opts.effectiveCost != null ? opts.effectiveCost : (player ? getEffectiveSigningCost(player, pick, pick.value) : 0);
    const before = player;
    const resolved = resolvePickForPool(pick, player, prefCost, pickIndex);
    player = resolved.player;
    const effectiveCost = resolved.effectiveCost;
    if (before && player && player.name === 'Random senior sign' && before.name !== 'Random senior sign') {
      reason = (reason ? reason + ' ' : '') + 'Pool over budget — random senior sign.';
    } else if (!before && player && player.name === 'Random senior sign') {
      reason = reason || 'No listed player fit the pool — random senior sign.';
    }
    if (pickIndex >= 0 && pickIndex < state.picks.length) {
      state.pickRationales[pickIndex] = {
        reason: reason || (player ? 'Best player available' : ''),
        player: player || null,
        effectiveCost: player ? effectiveCost : null,
        weirdEvent: opts.weirdEvent || false,
        isHuman: opts.isHuman || false
      };
    }
    if (!state.teamPicks[pick.team]) state.teamPicks[pick.team] = [];
    state.drafted.add(player.rank);
    state.teamSpent[pick.team] = (state.teamSpent[pick.team] || 0) + effectiveCost;
    state.teamPicks[pick.team].push({ name: player.name, cost: effectiveCost, rank: player.rank, photoUrl: player.photoUrl });
    const playerEl = row.querySelector('.col-player');
    const costEl = row.querySelector('.col-cost');
    if (playerEl) {
      const rankBit = player.name === 'Random senior sign' ? '' : `#${player.rank} `;
      playerEl.className = 'col-player flex items-center gap-1.5 min-w-0';
      playerEl.innerHTML = playerPhotoHtml(player) + `<span class="truncate min-w-0">${rankBit}${player.position ? player.position + ' ' : ''}${escapeHtml(player.name)}</span>`;
    }
    if (costEl) {
      costEl.textContent = fmt(effectiveCost);
      costEl.classList.remove('text-overslot-red', 'text-white', 'text-green-400');
      if (effectiveCost > pick.value) costEl.classList.add('text-overslot-red');
      else if (effectiveCost < pick.value) costEl.classList.add('text-green-400');
      else costEl.classList.add('text-white');
    }
    row.classList.remove('current', 'bg-red-900/20');
    row.querySelector('div:last-child')?.classList.remove('bg-red-900/10');
    row.classList.add('opacity-75', 'past-pick');
    if (state.humanTeams.has(pick.team)) {
      row.classList.add('human-pick');
    }
    row.scrollIntoView({ behavior: state.pickDelay === 0 ? 'auto' : 'smooth', block: 'end' });
  }

  init();
})();
