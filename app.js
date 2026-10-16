const state = {
  view: "ashare",
  sample: true,
  ashare: null,
  us: null,
  asia: null,
  multibagger: null,
  backtest: null,
  history: [],
  dailyMarkdown: "",
  selected: null,
  loading: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const icons = {
  scan: '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 12.5 5.5 5.8l7 3.5M23.5 12.5l3-6.7-7 3.5"/><rect x="6.5" y="10" width="19" height="16" rx="7" fill="var(--icon-fill)"/><path d="M10.5 20h3l2.2-4.8 2.5 7 2-4.2h2.8"/><path d="M11.4 15.4h.1M20.5 15.4h.1"/></svg>',
  target: '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M8.2 12.2 5.8 6.2l6 3.2M23.8 12.2l2.4-6-6 3.2"/><rect x="7" y="10" width="18" height="16" rx="7" fill="var(--icon-fill)"/><path d="M12 20c1.3 2.2 6.7 2.2 8 0"/><path d="M12.5 15.8h.1M19.5 15.8h.1"/><path d="M16 7.5v4M16 23v3M8 17h3M21 17h3"/></svg>',
  archive: '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M7 12h18l-1.4 14H8.4L7 12Z" fill="var(--icon-fill)"/><path d="M10 12 12.5 7l3.5 4 3.5-4L22 12"/><path d="M12 17h8M13 22h6"/><path d="M6 12h20"/></svg>',
  refresh: '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 12.5 7 6.8l6.5 2.4"/><path d="M23 12a8.2 8.2 0 0 0-14.5-2.4"/><path d="M21.5 19.5 25 25.2l-6.5-2.4"/><path d="M9 20a8.2 8.2 0 0 0 14.5 2.4"/><circle cx="16" cy="16" r="3.6" fill="var(--icon-fill)"/></svg>',
  doc: '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M10 5h9l5 5v17H10z" fill="var(--icon-fill)"/><path d="M19 5v6h5"/><path d="M13.5 16h7M13.5 20h7M13.5 24h4"/><path d="M8.5 8.5 6.5 5l4.4 1.3"/></svg>',
  copy: '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><rect x="11" y="10" width="14" height="15" rx="4" fill="var(--icon-fill)"/><path d="M7 18V9a3 3 0 0 1 3-3h9"/><path d="M15 16h6M15 20h5"/><path d="M23 8.5c1.7-.4 3 .8 2.4 2.4"/></svg>',
  chart: '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><rect x="5.5" y="7" width="21" height="18" rx="5" fill="var(--icon-fill)"/><path d="M10 21V11M16 21v-6M22 21v-9"/><path d="M9 24.5c1.5 2.5 5.5 2.5 7 0 1.5 2.5 5.5 2.5 7 0"/></svg>',
  spark: '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4c4 2.7 6.1 6 6.1 10.2 0 5.5-3.4 9.4-6.1 12-2.7-2.6-6.1-6.5-6.1-12C9.9 10 12 6.7 16 4Z" fill="var(--icon-fill)"/><path d="M16 4v7.3"/><path d="M12.2 23.2 8.5 27M19.8 23.2l3.7 3.8"/><path d="M13.4 14.4h5.2M16 11.8v5.2"/></svg>',
};

function init() {
  document.body.dataset.view = state.view;
  $$(".icon").forEach((el) => {
    el.innerHTML = icons[el.dataset.icon] || "";
  });
  $("#reportDate").value = localDateInputValue(new Date());
  configureStaticMode();
  bindEvents();
  loadAll();
}

function configureStaticMode() {
  if (!isGithubPages()) return;
  state.sample = true;
  $("#sampleMode").textContent = "静态";
  $("#liveMode").disabled = true;
  $("#liveMode").title = "GitHub Pages 备用域名只提供静态快照，不支持实时行情接口。";
}

function bindEvents() {
  $$(".nav-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });
  $("#sampleMode").addEventListener("click", () => setSampleMode(true));
  $("#liveMode").addEventListener("click", () => setSampleMode(false));
  $("#refreshBtn").addEventListener("click", loadAll);
  $("#historyBtn").addEventListener("click", loadHistory);
  $("#copyReportBtn").addEventListener("click", copyDailyReport);
  $("#ashareSearch").addEventListener("input", renderAshareTable);
  $("#themeFilter").addEventListener("change", renderAshareTable);
  $("#usSearch").addEventListener("input", renderUsTable);
  $("#ratingFilter").addEventListener("change", renderUsTable);
  $("#asiaSearch").addEventListener("input", renderAsiaTable);
  $("#asiaMarketFilter").addEventListener("change", renderAsiaTable);
  $("#asiaRatingFilter").addEventListener("change", renderAsiaTable);
  $("#multiSearch").addEventListener("input", renderMultibaggerTable);
  $("#multiMarketFilter").addEventListener("change", renderMultibaggerTable);
  $("#multiRatingFilter").addEventListener("change", renderMultibaggerTable);
}

function switchView(view) {
  state.view = view;
  document.body.dataset.view = view;
  $$(".nav-tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === view));
  $$("[data-panel]").forEach((panel) => panel.classList.toggle("hidden", panel.dataset.panel !== view));
  if (view === "history") loadHistory();
  if (view === "evidence") renderBacktestPanel();
  if (view === "daily") renderDailyReport();
  if (view === "ashare") selectFirstAshare();
  if (view === "us") selectFirstUs();
  if (view === "asia") selectFirstAsia();
  if (view === "multibagger") selectFirstMultibagger();
}

function setSampleMode(sample) {
  if (isGithubPages() && !sample) {
    setStatus("GitHub Pages 备用域名只提供静态快照，不支持实时行情接口。");
    return;
  }
  state.sample = sample;
  $("#sampleMode").classList.toggle("selected", sample);
  $("#liveMode").classList.toggle("selected", !sample);
  loadAll();
}

async function loadAll() {
  if (state.loading) return;
  state.loading = true;
  setStatus(state.sample ? "正在加载样例数据" : "正在拉取实时行情，首次可能需要几十秒");
  try {
    const [ashare, us, asia, multibagger, backtest] = await Promise.all([fetchAshare(), fetchUsQuality(), fetchAsiaMarkets(), fetchMultibagger(), fetchBacktest()]);
    state.ashare = ashare.result;
    state.us = us.result;
    state.asia = asia.result;
    state.multibagger = multibagger.result;
    state.backtest = backtest.result;
    state.dailyMarkdown = ashare.markdown || "";
    $("#reportPath").textContent = ashare.markdownPath ? compactPath(ashare.markdownPath) : "尚未生成";
    renderSummary(ashare.result, us.result);
    renderThemes();
    renderAshareTable();
    renderUsTable();
    renderAsiaTable();
    renderMultibaggerTable();
    renderBacktestPanel();
    renderDailyReport();
    loadHistory();
    await refreshAshareQuotes();
    setStatus(reportStatusText(ashare.result));
  } catch (error) {
    setStatus(`加载失败：${error.message}`);
  } finally {
    state.loading = false;
  }
}

async function fetchAshare() {
  const params = new URLSearchParams({
    sample: String(state.sample),
    date: $("#reportDate").value,
    top: "5",
    maxThemes: "6",
    lookback: state.sample ? "260" : "420",
  });
  return api(`/api/report?${params.toString()}`);
}

async function fetchUsQuality() {
  const params = new URLSearchParams({
    sample: String(state.sample),
    date: $("#reportDate").value,
    top: "20",
    lookback: state.sample ? "220" : "260",
  });
  return api(`/api/us-quality?${params.toString()}`);
}

async function fetchAsiaMarkets() {
  const params = new URLSearchParams({
    sample: String(state.sample),
    date: $("#reportDate").value,
    top: "24",
    lookback: state.sample ? "220" : "260",
  });
  return api(`/api/asia-markets?${params.toString()}`);
}

async function fetchMultibagger() {
  const params = new URLSearchParams({
    sample: String(state.sample),
    date: $("#reportDate").value,
    top: "24",
    lookback: state.sample ? "260" : "360",
  });
  return api(`/api/multibagger?${params.toString()}`);
}

async function fetchBacktest() {
  const params = new URLSearchParams({
    sample: String(state.sample),
    date: $("#reportDate").value,
    window: "182",
    lookback: state.sample ? "220" : "260",
  });
  return api(`/api/backtest?${params.toString()}`);
}

async function loadHistory() {
  try {
    const data = await api("/api/history");
    state.history = data.items || [];
    renderHistory();
  } catch (error) {
    $("#historyList").innerHTML = `<div class="empty-state">读取历史失败：${escapeHtml(error.message)}</div>`;
  }
}

async function api(url) {
  if (isStaticHost()) {
    const staticUrl = staticFallbackFor(url);
    if (staticUrl) {
      const staticResponse = await fetch(staticUrl);
      const data = await staticResponse.json();
      if (!staticResponse.ok || data.ok === false) throw new Error(data.error || `HTTP ${staticResponse.status}`);
      return data;
    }
  }
  const response = await fetch(url);
  if (response.ok) {
    const data = await response.json();
    if (data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }
  const fallback = staticFallbackFor(url);
  if (fallback) {
    const fallbackResponse = await fetch(fallback);
    const data = await fallbackResponse.json();
    if (!fallbackResponse.ok || data.ok === false) throw new Error(data.error || `HTTP ${fallbackResponse.status}`);
    return data;
  }
  throw new Error(`HTTP ${response.status}`);
}

function staticFallbackFor(url) {
  if (url.startsWith("/api/report")) return staticAsset("data/report.json");
  if (url.startsWith("/api/us-quality")) return staticAsset("data/us-quality.json");
  if (url.startsWith("/api/asia-markets")) return staticAsset("data/asia-markets.json");
  if (url.startsWith("/api/multibagger")) return staticAsset("data/multibagger.json");
  if (url.startsWith("/api/backtest")) return staticAsset("data/backtest.json");
  if (url.startsWith("/api/history")) return staticAsset("data/history.json");
  return "";
}

function isStaticHost() {
  return location.hostname.endsWith(".netlify.app") || location.hostname.endsWith(".github.io") || location.protocol === "file:";
}

function isGithubPages() {
  return location.hostname.endsWith(".github.io");
}

function staticAsset(path) {
  return new URL(path.replace(/^\/+/, ""), document.baseURI).href;
}

function reportStatusText(result) {
  const mode = isGithubPages() ? "静态快照" : state.sample ? "样例数据" : "实时数据";
  const dataDate = result?.date || "-";
  const generated = result?.generated_at ? new Date(result.generated_at).toLocaleString("zh-CN", { hour12: false }) : "-";
  const selected = $("#reportDate").value;
  const mismatch = selected && dataDate !== selected ? ` · 当前选择 ${selected}` : "";
  return `${mode} · 数据日期 ${dataDate} · 生成 ${generated}${mismatch}`;
}

function renderSummary(ashare, us) {
  const topTheme = ashare?.themes?.[0];
  $("#topTheme").textContent = topTheme ? topTheme.theme.name : "-";
  $("#themeSignal").textContent = topTheme ? `${fmtPct(topTheme.signal.avg_pct)} / ${topTheme.signal.score.toFixed(1)}` : "-";
  const counts = us?.summary?.rating_counts || {};
  $("#usBuyCount").textContent = `${(counts.Buy || 0) + (counts.Outperform || 0)} 只`;
  const multi = state.multibagger?.summary || {};
  $("#multiFocusCount").textContent = `${multi.focus_count || 0} 只`;
}

function renderThemes() {
  const select = $("#themeFilter");
  const themes = state.ashare?.themes || [];
  select.innerHTML = `<option value="all">全部板块</option>` + themes.map((block) => `<option value="${escapeHtml(block.theme.name)}">${escapeHtml(block.theme.name)}</option>`).join("");
  $("#themeCards").innerHTML = themes
    .map((block, index) => {
      const width = Math.max(5, Math.min(100, block.signal.score));
      return `<button class="theme-card ${index === 0 ? "active" : ""}" type="button" data-theme="${escapeHtml(block.theme.name)}">
        <strong>${escapeHtml(block.theme.name)}</strong>
        <div class="muted">${fmtPct(block.signal.avg_pct)} · 信号 ${block.signal.score.toFixed(1)}</div>
        <div class="mini-line" aria-hidden="true"><span style="width:${width}%"></span></div>
      </button>`;
    })
    .join("");
  $$(".theme-card").forEach((btn) => {
    btn.addEventListener("click", () => {
      select.value = btn.dataset.theme;
      renderAshareTable();
    });
  });
}

function flattenAshare() {
  const rows = [];
  (state.ashare?.themes || []).forEach((block) => {
    (block.top || []).forEach((item) => rows.push({ ...item, themeName: block.theme.name, themeSignal: block.signal }));
  });
  return rows;
}

function renderAshareTable() {
  const q = $("#ashareSearch").value.trim().toLowerCase();
  const theme = $("#themeFilter").value || "all";
  let rows = flattenAshare();
  if (theme !== "all") rows = rows.filter((row) => row.themeName === theme);
  if (q) {
    rows = rows.filter((row) => {
      const f = row.formatted || {};
      return [f.code, f.name, f.industry, row.themeName].join(" ").toLowerCase().includes(q);
    });
  }
  $("#ashareRows").innerHTML = rows.map(renderAshareRow).join("") || `<tr><td colspan="10" class="empty-state">暂无匹配结果</td></tr>`;
  $$("#ashareRows tr[data-kind]").forEach((tr) => tr.addEventListener("click", () => selectAshare(tr.dataset.key)));
  if (state.view === "ashare") selectFirstAshare();
}

function renderAshareRow(row) {
  const f = row.formatted;
  const key = `a:${f.code}:${row.themeName}`;
  return `<tr data-kind="ashare" data-key="${escapeHtml(key)}">
    <td><span class="stock-id"><strong>${escapeHtml(f.name)}</strong><span>${escapeHtml(f.code)}</span></span></td>
    <td class="change-cell">${pctBadge(f.day_pct)}<span>${escapeHtml(changeMeta(f))}</span></td>
    <td>${ratingPill(row.analyst?.rating || "Neutral")}</td>
    <td>${convictionCell(row.analyst?.conviction)}</td>
    <td>${gatePill(row.analyst?.risk_gate || "Watch")}</td>
    <td>${escapeHtml(row.themeName)}</td>
    <td>${escapeHtml(f.industry)}</td>
    <td>${escapeHtml(f.hit_rate)}</td>
    <td class="entry-cell">${escapeHtml(row.analyst?.entry_plan || f.rationale)}</td>
    <td>${scoreCell(Number(f.score))}</td>
  </tr>`;
}

function renderUsTable() {
  const q = $("#usSearch").value.trim().toLowerCase();
  const rating = $("#ratingFilter").value || "all";
  let rows = state.us?.top || [];
  if (rating !== "all") rows = rows.filter((row) => row.rating === rating);
  if (q) {
    rows = rows.filter((row) => [row.ticker, row.name, row.sector].join(" ").toLowerCase().includes(q));
  }
  $("#usRows").innerHTML = rows.map(renderUsRow).join("") || `<tr><td colspan="9" class="empty-state">暂无匹配结果</td></tr>`;
  $$("#usRows tr[data-kind]").forEach((tr) => tr.addEventListener("click", () => selectUs(tr.dataset.ticker)));
  if (state.view === "us") selectFirstUs();
}

function renderAsiaTable() {
  const q = $("#asiaSearch").value.trim().toLowerCase();
  const market = $("#asiaMarketFilter").value || "all";
  const rating = $("#asiaRatingFilter").value || "all";
  let rows = state.asia?.top || [];
  if (market !== "all") rows = rows.filter((row) => row.market === market);
  if (rating !== "all") rows = rows.filter((row) => row.rating === rating);
  if (q) {
    rows = rows.filter((row) => [row.ticker, row.name, row.market, row.sector, row.market_cap_bucket].join(" ").toLowerCase().includes(q));
  }
  $("#asiaRows").innerHTML = rows.map(renderAsiaRow).join("") || `<tr><td colspan="10" class="empty-state">暂无匹配结果</td></tr>`;
  $$("#asiaRows tr[data-kind]").forEach((tr) => tr.addEventListener("click", () => selectAsia(tr.dataset.ticker)));
  if (state.view === "asia") selectFirstAsia();
}

function multibaggerRows() {
  return state.multibagger?.combined || [];
}

function renderMultibaggerTable() {
  const q = $("#multiSearch").value.trim().toLowerCase();
  const market = $("#multiMarketFilter").value || "all";
  const rating = $("#multiRatingFilter").value || "all";
  let rows = multibaggerRows();
  if (market !== "all") rows = rows.filter((row) => row.market === market);
  if (rating !== "all") rows = rows.filter((row) => row.rating === rating);
  if (q) {
    rows = rows.filter((row) => [row.ticker, row.name, row.industry, row.theme, row.stage, row.market].join(" ").toLowerCase().includes(q));
  }
  const method = state.multibagger?.method || {};
  $("#multiMethod").innerHTML = method.summary
    ? `<strong>挖掘口径</strong><span>${escapeHtml(method.summary)} ${escapeHtml(method.not_buy_signal || "")}</span>`
    : "";
  $("#multiRows").innerHTML = rows.map(renderMultibaggerRow).join("") || `<tr><td colspan="10" class="empty-state">暂无匹配结果</td></tr>`;
  $$("#multiRows tr[data-kind]").forEach((tr) => tr.addEventListener("click", () => selectMultibagger(tr.dataset.key)));
  if (state.view === "multibagger") selectFirstMultibagger();
}

function selectFirstAshare() {
  const first = $("#ashareRows tr[data-key]");
  if (first) selectAshare(first.dataset.key);
}

function selectFirstUs() {
  const first = $("#usRows tr[data-ticker]");
  if (first) selectUs(first.dataset.ticker);
}

function selectFirstAsia() {
  const first = $("#asiaRows tr[data-ticker]");
  if (first) selectAsia(first.dataset.ticker);
}

function selectFirstMultibagger() {
  const first = $("#multiRows tr[data-key]");
  if (first) selectMultibagger(first.dataset.key);
}

function renderUsRow(row) {
  const f = row.formatted || {};
  return `<tr data-kind="us" data-ticker="${escapeHtml(row.ticker)}">
    <td><span class="stock-id"><strong>${escapeHtml(row.ticker)}</strong><span>${escapeHtml(row.market_cap_bucket)}</span></span></td>
    <td>${escapeHtml(row.name)}</td>
    <td>${ratingPill(row.rating)}</td>
    <td>${convictionCell(row.conviction)}</td>
    <td>${gatePill(row.risk_gate || "Watch")}</td>
    <td>${escapeHtml(row.sector)}</td>
    <td>${escapeHtml(f.price || "未知")}</td>
    <td class="entry-cell">${escapeHtml(row.buy_zone || "")}</td>
    <td>${scoreCell(row.score)}</td>
  </tr>`;
}

function renderAsiaRow(row) {
  const f = row.formatted || {};
  const metrics = row.metrics || {};
  const returns = `${f.return_20d || "-"} / ${f.return_60d || "-"}`;
  return `<tr data-kind="asia" data-ticker="${escapeHtml(row.ticker)}">
    <td><span class="stock-id"><strong>${escapeHtml(row.ticker)}</strong><span>${escapeHtml(row.market_cap_bucket)}</span></span></td>
    <td>${escapeHtml(row.market)}</td>
    <td>${escapeHtml(row.name)}</td>
    <td>${ratingPill(row.rating)}</td>
    <td>${convictionCell(row.conviction)}</td>
    <td>${gatePill(row.risk_gate || "Watch")}</td>
    <td>${escapeHtml(row.sector)}</td>
    <td>${escapeHtml(f.price || "未知")}</td>
    <td class="${signedClass(metrics.return_20d)}">${escapeHtml(returns)}</td>
    <td>${scoreCell(row.score)}</td>
  </tr>`;
}

function renderMultibaggerRow(row) {
  const f = row.formatted || {};
  const key = `${row.kind}:${row.ticker}`;
  const returns = `${f.return_60d || "-"} / ${f.return_120d || "-"}`;
  const trigger = (row.trigger_conditions || [])[0] || "";
  return `<tr data-kind="multi" data-key="${escapeHtml(key)}">
    <td><span class="stock-id"><strong>${escapeHtml(row.ticker)}</strong><span>${escapeHtml(row.name)}</span></span></td>
    <td>${escapeHtml(row.market)}</td>
    <td><span class="stage-tag">${escapeHtml(row.stage)}</span></td>
    <td>${opportunityPill(row.rating)}</td>
    <td>${gatePill(row.risk_gate || "Watch")}</td>
    <td>${escapeHtml(row.market_cap_bucket || f.market_cap || "未知")}</td>
    <td>${escapeHtml(row.industry || row.theme || "-")}</td>
    <td class="${signedClass(row.metrics?.return_60d)}">${escapeHtml(returns)}</td>
    <td class="entry-cell">${escapeHtml(trigger)}</td>
    <td>${scoreCell(row.score)}</td>
  </tr>`;
}

function selectAshare(key) {
  const row = flattenAshare().find((item) => `a:${item.formatted.code}:${item.themeName}` === key);
  if (!row) return;
  state.selected = row;
  $$("#ashareRows tr").forEach((tr) => tr.classList.toggle("selected", tr.dataset.key === key));
  $("#detailType").textContent = "A 股候选";
  $("#detailTitle").textContent = `${row.formatted.code} ${row.formatted.name}`;
  $("#detailBody").classList.remove("empty-state");
  $("#detailBody").innerHTML = renderAshareDetail(row);
  refreshLiveKline("a", row.formatted.code);
}

function selectUs(ticker) {
  const row = (state.us?.top || []).find((item) => item.ticker === ticker);
  if (!row) return;
  state.selected = row;
  $$("#usRows tr").forEach((tr) => tr.classList.toggle("selected", tr.dataset.ticker === ticker));
  $("#detailType").textContent = "美股优选";
  $("#detailTitle").textContent = `${row.ticker} ${row.name}`;
  $("#detailBody").classList.remove("empty-state");
  $("#detailBody").innerHTML = renderUsDetail(row);
  refreshLiveKline("us", row.ticker);
}

function selectAsia(ticker) {
  const row = (state.asia?.top || []).find((item) => item.ticker === ticker) || (state.asia?.all || []).find((item) => item.ticker === ticker);
  if (!row) return;
  state.selected = row;
  $$("#asiaRows tr").forEach((tr) => tr.classList.toggle("selected", tr.dataset.ticker === ticker));
  $("#detailType").textContent = "日韩市场";
  $("#detailTitle").textContent = `${row.ticker} ${row.name}`;
  $("#detailBody").classList.remove("empty-state");
  $("#detailBody").innerHTML = renderAsiaDetail(row);
  refreshLiveKline("us", row.ticker);
}

function selectMultibagger(key) {
  const row = multibaggerRows().find((item) => `${item.kind}:${item.ticker}` === key);
  if (!row) return;
  state.selected = row;
  $$("#multiRows tr").forEach((tr) => tr.classList.toggle("selected", tr.dataset.key === key));
  $("#detailType").textContent = "高倍潜力";
  $("#detailTitle").textContent = `${row.ticker} ${row.name}`;
  $("#detailBody").classList.remove("empty-state");
  $("#detailBody").innerHTML = renderMultibaggerDetail(row);
  refreshLiveKline(row.kind === "ashare" ? "a" : "us", row.ticker);
}

function renderAshareDetail(row) {
  const f = row.formatted;
  const factors = row.factors || {};
  const analyst = row.analyst || {};
  const dimensions = analyst.dimensions || {};
  const news = (row.news || []).slice(0, 5);
  return `
    <section class="detail-section">
      <h3>Analyst Call</h3>
      <div class="callout-line">
        ${ratingPill(analyst.rating || "Neutral")}
        ${gatePill(analyst.risk_gate || "Watch")}
        <span class="mini-stat">Conviction ${num(analyst.conviction)}</span>
        <span class="mini-stat ${pctClass(f.day_pct)}">当前涨跌 ${escapeHtml(f.day_pct)}</span>
      </div>
      <div class="thesis-box">${escapeHtml(analyst.entry_plan || f.rationale)}</div>
    </section>
    <section class="detail-section">
      <h3>行情快照</h3>
      <div class="evidence-mini">
        <div><span>价格</span><strong>${escapeHtml(f.price || "-")}</strong></div>
        <div><span>当前涨跌</span><strong class="${pctClass(f.day_pct)}">${escapeHtml(f.day_pct || "-")}</strong></div>
        <div><span>市值</span><strong>${escapeHtml(f.market_cap || "-")}</strong></div>
        <div><span>来源</span><strong>${escapeHtml(changeMeta(f) || "行情快照")}</strong></div>
      </div>
    </section>
    <section class="detail-section">
      <h3>Score Waterfall</h3>
      <div class="factor-row"><span>Catalyst</span>${factorTrack(dimensions.catalyst || factors.signal || 0, 100)}<strong>${num(dimensions.catalyst)}</strong></div>
      <div class="factor-row"><span>History Edge</span>${factorTrack(dimensions.history_edge || 0, 100)}<strong>${num(dimensions.history_edge)}</strong></div>
      <div class="factor-row"><span>Quality Proxy</span>${factorTrack(dimensions.quality_proxy || 0, 100)}<strong>${num(dimensions.quality_proxy)}</strong></div>
      <div class="factor-row"><span>Momentum</span>${factorTrack(dimensions.momentum || 0, 100)}<strong>${num(dimensions.momentum)}</strong></div>
      <div class="factor-row"><span>News</span>${factorTrack(dimensions.news || 0, 100)}<strong>${num(dimensions.news)}</strong></div>
      <div class="factor-row"><span>Risk</span>${factorTrack(dimensions.risk || 0, 100)}<strong>${num(dimensions.risk)}</strong></div>
    </section>
    <section class="detail-section">
      <h3>实时/近半年 K 线</h3>
      <div id="liveKlineMount">${klineChart(row.kline || [])}${klineStats(row.kline || [])}</div>
    </section>
    <section class="detail-section">
      <h3>半年回测证据</h3>
      ${backtestEvidence("ashare", row)}
    </section>
    <section class="detail-section">
      <h3>板块触发</h3>
      <div class="thesis-box">${escapeHtml(row.themeSignal.summary || "")}</div>
    </section>
    <section class="detail-section">
      <h3>情景分析</h3>
      ${scenarioList(analyst.scenario)}
    </section>
    <section class="detail-section">
      <h3>近期新闻</h3>
      <ul class="news-list">${news.map((item) => `<li>${escapeHtml([item.time, item.source, item.title].filter(Boolean).join(" / "))}</li>`).join("") || "<li>暂无新闻</li>"}</ul>
    </section>`;
}

function renderMultibaggerDetail(row) {
  const f = row.formatted || {};
  const factors = row.factors || {};
  const metrics = row.metrics || {};
  const news = (row.news || []).slice(0, 5);
  const risks = row.news_risks || row.risks || [];
  const catalystLabel = row.kind === "us" ? "Fundamentals" : "Catalyst";
  const catalystValue = row.kind === "us" ? factors.fundamentals : factors.catalyst;
  return `
    <section class="detail-section">
      <h3>结论</h3>
      <div class="callout-line">
        ${opportunityPill(row.rating)}
        ${gatePill(row.risk_gate || "Watch")}
        <span class="mini-stat">Conviction ${num(row.conviction)}</span>
        <span class="mini-stat">${escapeHtml(row.stage)}</span>
      </div>
      <div class="thesis-box">${escapeHtml(row.thesis || "")}</div>
    </section>
    <section class="detail-section">
      <h3>早期高倍评分</h3>
      <div class="factor-row"><span>市值甜点</span>${factorTrack(factors.market_cap_sweet_spot || 0, 100)}<strong>${num(factors.market_cap_sweet_spot)}</strong></div>
      <div class="factor-row"><span>赛道期权</span>${factorTrack(factors.industry_optionality || 0, 100)}<strong>${num(factors.industry_optionality)}</strong></div>
      <div class="factor-row"><span>${catalystLabel}</span>${factorTrack(catalystValue || 0, 100)}<strong>${num(catalystValue)}</strong></div>
      <div class="factor-row"><span>趋势确认</span>${factorTrack(factors.trend_confirmation || 0, 100)}<strong>${num(factors.trend_confirmation)}</strong></div>
      <div class="factor-row"><span>资金确认</span>${factorTrack(factors.accumulation || 0, 100)}<strong>${num(factors.accumulation)}</strong></div>
      <div class="factor-row"><span>风险控制</span>${factorTrack(factors.risk_control || 0, 100)}<strong>${num(factors.risk_control)}</strong></div>
    </section>
    <section class="detail-section">
      <h3>量价位置</h3>
      <div class="evidence-mini">
        <div><span>价格</span><strong>${escapeHtml(f.price || "-")}</strong></div>
        <div><span>20日</span><strong class="${signedClass(metrics.return_20d)}">${escapeHtml(f.return_20d || "-")}</strong></div>
        <div><span>60日</span><strong class="${signedClass(metrics.return_60d)}">${escapeHtml(f.return_60d || "-")}</strong></div>
        <div><span>120日</span><strong class="${signedClass(metrics.return_120d)}">${escapeHtml(f.return_120d || "-")}</strong></div>
      </div>
    </section>
    <section class="detail-section">
      <h3>触发条件</h3>
      <ul class="risk-list">${(row.trigger_conditions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>
    <section class="detail-section">
      <h3>失效条件</h3>
      <ul class="risk-list">${(row.invalid_conditions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>
    <section class="detail-section">
      <h3>实时/近半年 K 线</h3>
      <div id="liveKlineMount">${klineChart(row.kline || [])}${klineStats(row.kline || [])}</div>
    </section>
    <section class="detail-section">
      <h3>${row.kind === "ashare" ? "近期新闻" : "主要风险"}</h3>
      ${row.kind === "ashare"
        ? `<ul class="news-list">${news.map((item) => `<li>${escapeHtml([item.time, item.source, item.title].filter(Boolean).join(" / "))}</li>`).join("") || "<li>暂无新闻</li>"}</ul>`
        : `<ul class="risk-list">${risks.map((risk) => `<li>${escapeHtml(risk)}</li>`).join("") || "<li>暂无风险标签</li>"}</ul>`}
    </section>`;
}

function renderUsDetail(row) {
  const factors = row.factors || {};
  const metrics = row.metrics || {};
  return `
    <section class="detail-section">
      <h3>Analyst Call</h3>
      <div class="callout-line">
        ${ratingPill(row.rating)}
        ${gatePill(row.risk_gate || "Watch")}
        <span class="mini-stat">Conviction ${num(row.conviction)}</span>
      </div>
      <div class="thesis-box">${escapeHtml(row.buy_zone)}</div>
    </section>
    <section class="detail-section">
      <h3>核心逻辑</h3>
      <div class="thesis-box">${escapeHtml(row.thesis)}</div>
    </section>
    <section class="detail-section">
      <h3>Score Waterfall</h3>
      <div class="factor-row"><span>质量</span>${factorTrack(factors.quality || 0, 24)}<strong>${num(factors.quality)}</strong></div>
      <div class="factor-row"><span>成长</span>${factorTrack(factors.growth || 0, 18)}<strong>${num(factors.growth)}</strong></div>
      <div class="factor-row"><span>估值</span>${factorTrack(factors.valuation || 0, 14)}<strong>${num(factors.valuation)}</strong></div>
      <div class="factor-row"><span>护城河</span>${factorTrack(factors.moat || 0, 16)}<strong>${num(factors.moat)}</strong></div>
      <div class="factor-row"><span>趋势</span>${factorTrack(factors.trend || 0, 12)}<strong>${num(factors.trend)}</strong></div>
      <div class="factor-row"><span>盈利动量</span>${factorTrack(factors.earnings_momentum || 0, 8)}<strong>${num(factors.earnings_momentum)}</strong></div>
      <div class="factor-row"><span>风险扣分</span>${factorTrack(factors.risk_penalty || 0, 12)}<strong>${num(factors.risk_penalty)}</strong></div>
    </section>
    <section class="detail-section">
      <h3>情景分析</h3>
      ${scenarioList(row.scenario)}
    </section>
    <section class="detail-section">
      <h3>实时/近半年 K 线</h3>
      <div id="liveKlineMount">${klineChart(row.kline || [])}${klineStats(row.kline || [])}</div>
    </section>
    <section class="detail-section">
      <h3>半年回测证据</h3>
      ${backtestEvidence("us", row)}
    </section>
    <section class="detail-section">
      <h3>主要风险</h3>
      <ul class="risk-list">${(row.risks || []).map((risk) => `<li>${escapeHtml(risk)}</li>`).join("")}</ul>
    </section>`;
}

function renderAsiaDetail(row) {
  const f = row.formatted || {};
  const factors = row.factors || {};
  const metrics = row.metrics || {};
  const riskNote = state.asia?.method?.risk_note || "仅以娱乐为主，不构成投资建议。";
  return `
    <section class="detail-section">
      <h3>娱乐观察结论</h3>
      <div class="callout-line">
        ${ratingPill(row.rating)}
        ${gatePill(row.risk_gate || "Watch")}
        <span class="mini-stat">Conviction ${num(row.conviction)}</span>
        <span class="mini-stat">${escapeHtml(row.market)} · ${escapeHtml(row.currency || "")}</span>
      </div>
      <div class="thesis-box">${escapeHtml(row.buy_zone || "")}</div>
    </section>
    <section class="detail-section">
      <h3>核心逻辑</h3>
      <div class="thesis-box">${escapeHtml(row.thesis || "")}</div>
    </section>
    <section class="detail-section">
      <h3>市场画像</h3>
      <div class="evidence-mini">
        <div><span>产业</span><strong>${escapeHtml(row.sector || "-")}</strong></div>
        <div><span>市值层级</span><strong>${escapeHtml(row.market_cap_bucket || "-")}</strong></div>
        <div><span>价格</span><strong>${escapeHtml(f.price || "-")}</strong></div>
        <div><span>当日涨跌</span><strong class="${signedClass(metrics.day_pct)}">${escapeHtml(f.day_pct || "-")}</strong></div>
      </div>
    </section>
    <section class="detail-section">
      <h3>Score Waterfall</h3>
      <div class="factor-row"><span>质量</span>${factorTrack(factors.quality || 0, 24)}<strong>${num(factors.quality)}</strong></div>
      <div class="factor-row"><span>成长</span>${factorTrack(factors.growth || 0, 18)}<strong>${num(factors.growth)}</strong></div>
      <div class="factor-row"><span>估值</span>${factorTrack(factors.valuation || 0, 14)}<strong>${num(factors.valuation)}</strong></div>
      <div class="factor-row"><span>护城河</span>${factorTrack(factors.moat || 0, 16)}<strong>${num(factors.moat)}</strong></div>
      <div class="factor-row"><span>产业催化</span>${factorTrack(factors.catalyst || 0, 12)}<strong>${num(factors.catalyst)}</strong></div>
      <div class="factor-row"><span>趋势</span>${factorTrack(factors.trend || 0, 10)}<strong>${num(factors.trend)}</strong></div>
      <div class="factor-row"><span>盈利动量</span>${factorTrack(factors.earnings_momentum || 0, 8)}<strong>${num(factors.earnings_momentum)}</strong></div>
      <div class="factor-row"><span>风险扣分</span>${factorTrack(factors.risk_penalty || 0, 12)}<strong>${num(factors.risk_penalty)}</strong></div>
    </section>
    <section class="detail-section">
      <h3>量价位置</h3>
      <div class="evidence-mini">
        <div><span>20日</span><strong class="${signedClass(metrics.return_20d)}">${escapeHtml(f.return_20d || "-")}</strong></div>
        <div><span>60日</span><strong class="${signedClass(metrics.return_60d)}">${escapeHtml(f.return_60d || "-")}</strong></div>
        <div><span>60日波动</span><strong>${escapeHtml(f.volatility_60d || "-")}</strong></div>
        <div><span>20日均线距离</span><strong class="${signedClass(metrics.ma20_distance)}">${escapeHtml(f.ma20_distance || "-")}</strong></div>
      </div>
    </section>
    <section class="detail-section">
      <h3>情景分析</h3>
      ${scenarioList(row.scenario)}
    </section>
    <section class="detail-section">
      <h3>实时/近半年 K 线</h3>
      <div id="liveKlineMount">${klineChart(row.kline || [])}${klineStats(row.kline || [])}</div>
    </section>
    <section class="detail-section">
      <h3>主要风险</h3>
      <ul class="risk-list">${(row.risks || []).map((risk) => `<li>${escapeHtml(risk)}</li>`).join("") || "<li>暂无风险标签</li>"}</ul>
    </section>
    <section class="detail-section">
      <h3>免责声明</h3>
      <div class="thesis-box">${escapeHtml(riskNote)} 所有候选只用于观察、学习和复盘。</div>
    </section>`;
}

function renderBacktestPanel() {
  const target = $("#backtestBody");
  if (!target) return;
  const backtest = state.backtest;
  if (!backtest) {
    target.innerHTML = `<div class="empty-state">回测数据加载中。</div>`;
    return;
  }
  const ashare = backtest.ashare || {};
  const us = backtest.us || {};
  target.innerHTML = `
    <div class="evidence-note">
      <strong>数据支撑口径</strong>
      <span>窗口 ${backtest.window_days || 182} 天；训练回看 ${backtest.lookback_days || 260} 天；只使用回测日之前 K 线和已完成美股交易日。历史新闻无法逐日归档，回测中按中性处理。</span>
    </div>
    <div class="evidence-grid">
      ${summaryCard("A股 1日命中", fmtMetric(ashare.summary?.hit_rate_1d, "%"), `平均 ${fmtSigned(ashare.summary?.avg_return_1d)} / 超额 ${fmtSigned(ashare.summary?.excess_return_1d)}`)}
      ${summaryCard("A股 3日平均", fmtSigned(ashare.summary?.avg_return_3d), `样本 ${ashare.summary?.trade_count || 0} 笔 / ${ashare.summary?.day_count || 0} 天`)}
      ${summaryCard("美股 1日命中", fmtMetric(us.summary?.hit_rate_1d, "%"), `平均 ${fmtSigned(us.summary?.avg_return_1d)} / 超额 ${fmtSigned(us.summary?.excess_return_1d)}`)}
      ${summaryCard("美股 3日平均", fmtSigned(us.summary?.avg_return_3d), `样本 ${us.summary?.trade_count || 0} 笔 / ${us.summary?.day_count || 0} 天`)}
    </div>
    <div class="evidence-columns">
      <section>
        <h3>A股分板块回测</h3>
        ${backtestTable(ashare.by_theme || [], "theme")}
      </section>
      <section>
        <h3>美股分行业回测</h3>
        ${backtestTable(us.by_sector || [], "sector")}
      </section>
    </div>
    <section class="evidence-list">
      <h3>最近历史信号样本</h3>
      ${recentSignalsTable(ashare.recent_signals || [], "ashare")}
    </section>`;
}

function summaryCard(label, value, sub) {
  return `<div class="summary-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(sub)}</small></div>`;
}

function backtestTable(rows, labelKey) {
  if (!rows.length) return `<div class="empty-state">暂无可用回测数据。</div>`;
  return `<div class="table-wrap evidence-table"><table>
    <thead><tr><th>${labelKey === "theme" ? "板块" : "行业"}</th><th>样本</th><th>1日命中</th><th>3日均值</th><th>5日最差</th></tr></thead>
    <tbody>${rows
      .map(
        (row) => `<tr>
          <td>${escapeHtml(row[labelKey] || "-")}</td>
          <td>${escapeHtml(row.trade_count || 0)}</td>
          <td>${escapeHtml(fmtMetric(row.hit_rate_1d, "%"))}</td>
          <td class="${signedClass(row.avg_return_3d)}">${escapeHtml(fmtSigned(row.avg_return_3d))}</td>
          <td class="${signedClass(row.worst_return_5d)}">${escapeHtml(fmtSigned(row.worst_return_5d))}</td>
        </tr>`,
      )
      .join("")}</tbody>
  </table></div>`;
}

function recentSignalsTable(rows, kind) {
  if (!rows.length) return `<div class="empty-state">暂无历史信号样本。</div>`;
  return `<div class="table-wrap evidence-table"><table>
    <thead><tr><th>日期</th><th>标的</th><th>评级</th><th>Risk</th><th>1日</th><th>3日</th><th>5日</th></tr></thead>
    <tbody>${rows
      .slice(0, 18)
      .map((row) => {
        const label = kind === "us" ? `${row.ticker} ${row.name || ""}` : `${row.code} ${row.name || ""}`;
        return `<tr>
          <td>${escapeHtml(row.date)}</td>
          <td>${escapeHtml(label)}</td>
          <td>${ratingPill(row.rating)}</td>
          <td>${gatePill(row.risk_gate || "Watch")}</td>
          <td class="${signedClass(row.return_1d)}">${escapeHtml(fmtSigned(row.return_1d))}</td>
          <td class="${signedClass(row.return_3d)}">${escapeHtml(fmtSigned(row.return_3d))}</td>
          <td class="${signedClass(row.return_5d)}">${escapeHtml(fmtSigned(row.return_5d))}</td>
        </tr>`;
      })
      .join("")}</tbody>
  </table></div>`;
}

function backtestEvidence(kind, row) {
  const bt = state.backtest;
  if (!bt) return `<div class="empty-state">回测数据加载中。</div>`;
  if (kind === "ashare") {
    const item = (bt.ashare?.by_theme || []).find((entry) => entry.theme === row.themeName);
    return evidenceMini(item, "该板块半年样本");
  }
  return evidenceMini(bt.us?.summary, "美股优选半年样本");
}

function evidenceMini(summary, label) {
  if (!summary || !summary.trade_count) return `<div class="empty-state">暂无足够回测样本。</div>`;
  return `<div class="evidence-mini">
    <div><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(summary.trade_count))}</strong></div>
    <div><span>1日命中</span><strong>${escapeHtml(fmtMetric(summary.hit_rate_1d, "%"))}</strong></div>
    <div><span>3日均值</span><strong class="${signedClass(summary.avg_return_3d)}">${escapeHtml(fmtSigned(summary.avg_return_3d))}</strong></div>
    <div><span>1日超额</span><strong class="${signedClass(summary.excess_return_1d)}">${escapeHtml(fmtSigned(summary.excess_return_1d))}</strong></div>
  </div>`;
}

function klineStats(kline) {
  if (!kline.length) return `<div class="empty-state">暂无 K 线数据。</div>`;
  const last = kline[kline.length - 1];
  const first = kline[0];
  const periodReturn = first.close ? (last.close / first.close - 1) * 100 : null;
  return `<div class="kline-meta">
    <span>${escapeHtml(first.date)} 至 ${escapeHtml(last.date)}</span>
    <span>最新 ${escapeHtml(priceFmt(last.close))}</span>
    <span class="${signedClass(last.pct)}">当日 ${escapeHtml(fmtSigned(last.pct))}</span>
    <span class="${signedClass(periodReturn)}">区间 ${escapeHtml(fmtSigned(periodReturn))}</span>
  </div>`;
}

async function refreshLiveKline(kind, symbol) {
  const mount = $("#liveKlineMount");
  if (!mount || !symbol || !location.hostname.endsWith(".netlify.app")) return;
  try {
    const response = await fetch(`/api/live-kline?kind=${encodeURIComponent(kind)}&symbol=${encodeURIComponent(symbol)}&limit=120`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || !data.ok || !Array.isArray(data.kline) || !data.kline.length) return;
    mount.innerHTML = `${klineChart(data.kline)}${klineStats(data.kline)}<div class="kline-source">Live source: ${escapeHtml(data.source || "market API")}</div>`;
  } catch (error) {
    // Keep the build-time snapshot if the live proxy is unavailable.
  }
}

async function refreshAshareQuotes() {
  if (!location.hostname.endsWith(".netlify.app")) return;
  const rows = flattenAshare();
  const symbols = [...new Set(rows.map((row) => row.formatted?.code).filter(Boolean))];
  if (!symbols.length) return;
  try {
    const response = await fetch(`/api/live-quotes?kind=a&symbols=${encodeURIComponent(symbols.join(","))}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || !data.ok || !Array.isArray(data.quotes)) return;
    const bySymbol = new Map(data.quotes.map((quote) => [quote.symbol, quote]));
    let changed = 0;
    (state.ashare?.themes || []).forEach((block) => {
      [...(block.top || []), ...(block.all || [])].forEach((item) => {
        const quote = bySymbol.get(item.formatted?.code);
        if (quote && applyAshareQuote(item, quote)) changed += 1;
      });
    });
    if (changed) {
      const selectedKey = state.selected?.formatted ? `a:${state.selected.formatted.code}:${state.selected.themeName}` : "";
      renderAshareTable();
      if (selectedKey && state.view === "ashare") selectAshare(selectedKey);
    }
  } catch (error) {
    // Keep the build-time quote if the live quote proxy is unavailable.
  }
}

function applyAshareQuote(item, quote) {
  const pct = Number(quote.pct);
  const price = Number(quote.price);
  if (!Number.isFinite(pct) || !Number.isFinite(price)) return false;
  item.snapshot = {
    ...(item.snapshot || {}),
    price,
    pct,
    pct_source: "live_quote",
    pct_date: quote.date || "",
    snapshot_time: quote.time || "",
  };
  item.formatted = {
    ...(item.formatted || {}),
    name: quote.name || item.formatted?.name,
    price: priceFmt(price),
    day_pct: fmtSigned(pct),
    day_pct_source: quote.source || "实时快照",
    day_pct_asof: [quote.date, quote.time].filter(Boolean).join(" "),
  };
  return true;
}

function klineChart(kline) {
  const rows = (kline || []).filter((item) => Number.isFinite(Number(item.close))).slice(-64);
  if (!rows.length) return `<div class="empty-state">暂无 K 线数据。</div>`;
  const values = rows.flatMap((item) => [numOr(item.high, item.close), numOr(item.low, item.close), Number(item.close)]).filter(Number.isFinite);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 360;
  const height = 150;
  const pad = 12;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const step = innerW / rows.length;
  const candleW = Math.max(2, Math.min(7, step * 0.56));
  const y = (value) => pad + (max - value) / range * innerH;
  const candles = rows
    .map((item, index) => {
      const open = numOr(item.open, rows[index - 1]?.close ?? item.close);
      const close = Number(item.close);
      const high = numOr(item.high, Math.max(open, close));
      const low = numOr(item.low, Math.min(open, close));
      const x = pad + index * step + step / 2;
      const positive = close >= open;
      const color = positive ? "#16794c" : "#bd3030";
      const bodyY = Math.min(y(open), y(close));
      const bodyH = Math.max(1.5, Math.abs(y(open) - y(close)));
      return `<g>
        <line x1="${x.toFixed(2)}" y1="${y(high).toFixed(2)}" x2="${x.toFixed(2)}" y2="${y(low).toFixed(2)}" stroke="${color}" stroke-width="1"/>
        <rect x="${(x - candleW / 2).toFixed(2)}" y="${bodyY.toFixed(2)}" width="${candleW.toFixed(2)}" height="${bodyH.toFixed(2)}" rx="1" fill="${color}"/>
      </g>`;
    })
    .join("");
  return `<svg class="kline-chart" viewBox="0 0 ${width} ${height}" aria-label="K线图">
    <rect x="0" y="0" width="${width}" height="${height}" rx="8" fill="#f8fafd"/>
    <path d="M${pad} ${height - pad}H${width - pad}" stroke="#dfe6ef"/>
    ${candles}
  </svg>`;
}

function renderHistory() {
  $("#historyList").innerHTML =
    state.history
      .map(
        (item) => `<div class="history-item">
          <strong>${escapeHtml(item.name)}</strong>
          <div class="muted">${escapeHtml(compactPath(item.path))}</div>
          <div class="muted">${new Date(item.modified).toLocaleString("zh-CN", { hour12: false })}</div>
        </div>`,
      )
      .join("") || `<div class="empty-state">还没有网页版生成的历史报告。</div>`;
}

function renderDailyReport() {
  const target = $("#dailyReport");
  if (!target) return;
  target.innerHTML = state.dailyMarkdown
    ? markdownToHtml(state.dailyMarkdown)
    : `<div class="empty-state">刷新报告后会在这里显示完整日报。</div>`;
}

async function copyDailyReport() {
  if (!state.dailyMarkdown) return;
  await navigator.clipboard.writeText(state.dailyMarkdown);
  const btn = $("#copyReportBtn");
  const old = btn.innerHTML;
  btn.textContent = "已复制";
  setTimeout(() => {
    btn.innerHTML = old;
    $$(".icon").forEach((el) => {
      if (!el.innerHTML.trim()) el.innerHTML = icons[el.dataset.icon] || "";
    });
  }, 1200);
}

function markdownToHtml(markdown) {
  const lines = markdown.split("\n");
  const html = [];
  let inList = false;
  let inTable = false;

  function closeList() {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  }

  function closeTable() {
    if (inTable) {
      html.push("</tbody></table></div>");
      inTable = false;
    }
  }

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      closeTable();
      continue;
    }
    if (trimmed.startsWith("|")) {
      closeList();
      const cells = trimmed.split("|").slice(1, -1).map((cell) => cell.trim());
      if (cells.every((cell) => /^:?-{3,}:?$/.test(cell))) continue;
      if (!inTable) {
        html.push('<div class="table-wrap"><table><tbody>');
        inTable = true;
      }
      const tag = html[html.length - 1]?.includes("<tbody>") ? "th" : "td";
      html.push(`<tr>${cells.map((cell) => `<${tag}>${inlineMarkdown(cell)}</${tag}>`).join("")}</tr>`);
      continue;
    }
    closeTable();
    if (trimmed.startsWith("- ")) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${inlineMarkdown(trimmed.slice(2))}</li>`);
      continue;
    }
    closeList();
    if (trimmed.startsWith("# ")) html.push(`<h1>${inlineMarkdown(trimmed.slice(2))}</h1>`);
    else if (trimmed.startsWith("## ")) html.push(`<h2>${inlineMarkdown(trimmed.slice(3))}</h2>`);
    else if (trimmed.startsWith("### ")) html.push(`<h3>${inlineMarkdown(trimmed.slice(4))}</h3>`);
    else if (trimmed.startsWith("> ")) html.push(`<blockquote>${inlineMarkdown(trimmed.slice(2))}</blockquote>`);
    else html.push(`<p>${inlineMarkdown(trimmed)}</p>`);
  }
  closeList();
  closeTable();
  return html.join("");
}

function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function scoreCell(score) {
  const safe = Number.isFinite(score) ? score : 0;
  return `<span class="score"><span class="score-bar"><span style="width:${Math.max(0, Math.min(100, safe))}%"></span></span>${safe.toFixed(1)}</span>`;
}

function ratingPill(rating) {
  const cls = ["Buy", "Outperform"].includes(rating) ? "buy" : ["Neutral", "Watch"].includes(rating) ? "watch" : "avoid";
  return `<span class="pill ${cls}">${escapeHtml(rating || "未知")}</span>`;
}

function opportunityPill(rating) {
  const cls = rating === "Focus" ? "buy" : ["Watch", "Track"].includes(rating) ? "watch" : "avoid";
  return `<span class="pill ${cls}">${escapeHtml(rating || "Track")}</span>`;
}

function gatePill(gate) {
  const cls = gate === "Pass" ? "buy" : gate === "Watch" ? "watch" : "avoid";
  return `<span class="pill gate ${cls}">${escapeHtml(gate || "Watch")}</span>`;
}

function pctBadge(value) {
  const label = value || "未知";
  const cls = pctClass(label);
  return `<span class="pct-badge ${cls || "muted"}">${escapeHtml(label)}</span>`;
}

function changeMeta(formatted) {
  return [formatted?.day_pct_source, formatted?.day_pct_asof].filter(Boolean).join(" · ");
}

function convictionCell(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '<span class="muted">-</span>';
  return `<span class="score compact"><span class="score-bar"><span style="width:${Math.max(0, Math.min(100, n))}%"></span></span>${n.toFixed(0)}</span>`;
}

function scenarioList(scenario) {
  if (!scenario) return '<div class="empty-state">暂无情景分析</div>';
  return `<div class="scenario-grid">
    <div><strong>Bull</strong><span>${escapeHtml(scenario.bull || "")}</span></div>
    <div><strong>Base</strong><span>${escapeHtml(scenario.base || "")}</span></div>
    <div><strong>Bear</strong><span>${escapeHtml(scenario.bear || "")}</span></div>
  </div>`;
}

function factorTrack(value, max) {
  const width = Math.max(0, Math.min(100, (Number(value) / max) * 100));
  return `<span class="factor-track"><span style="width:${width}%"></span></span>`;
}

function sparkline(values) {
  if (!values.length) return `<div class="muted">暂无趋势图</div>`;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(1, values.length - 1)) * 90;
      const y = 24 - ((value - min) / range) * 20;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return `<svg class="sparkline" viewBox="0 0 90 26" fill="none" aria-hidden="true"><polyline points="${points}" stroke="#2868d8" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
}

function setStatus(text) {
  $("#statusLine").textContent = text;
}

function pctClass(value) {
  const n = parseFloat(String(value).replace("%", ""));
  if (!Number.isFinite(n)) return "";
  return n >= 0 ? "positive" : "negative";
}

function fmtPct(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${n >= 0 ? "+" : ""}${n.toFixed(2)}%` : "未知";
}

function fmtSigned(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${n >= 0 ? "+" : ""}${n.toFixed(2)}%` : "-";
}

function fmtMetric(value, suffix = "") {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(1)}${suffix}` : "-";
}

function priceFmt(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(2);
}

function signedClass(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "";
  return n > 0 ? "positive" : "negative";
}

function numOr(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : Number(fallback);
}

function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(1) : "-";
}

function compactPath(path) {
  return String(path).replace("/Users/qohfq/Documents/Playground/a-share-us-catalyst/", "");
}

function localDateInputValue(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
}

init();
