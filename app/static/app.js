const DEFAULT_HORIZONS = ["D1", "D3", "W1", "M1"];
const THEME_STORAGE_KEY = "refined-oil-workbench-theme";
const CHAT_HISTORY_STORAGE_KEY = "refined-oil-chat-history-v1";
const CHAT_HISTORY_LIMIT = 20;
const THEME_OPTIONS = ["light", "dark"];
const LEGACY_THEME_MAP = {
  mist: "light",
  sand: "light",
  night: "dark",
};
const HORIZON_LABELS = {
  D1: "明日",
  D3: "三日",
  W1: "一周",
  M1: "一月",
};

const PRICE_LABELS = [
  ["brent_active_settlement", "布伦特"],
  ["sd_gas92_market", "山东 92#"],
  ["cn_gas92_market", "全国 92#"],
  ["east_china_gas92_market", "华东 92#"],
  ["north_china_gas92_market", "华北 92#"],
  ["south_china_gas92_market", "华南 92#"],
  ["central_china_gas92_market", "华中 92#"],
  ["northwest_gas92_market", "西北 92#"],
  ["southwest_gas92_market", "西南 92#"],
  ["northeast_gas92_market", "东北 92#"],
];

const PRICE_HISTORY_DEFAULT_SERIES = ["sd_gas92_market", "cn_gas92_market", "east_china_gas92_market"];
const PRICE_HISTORY_COLORS = ["#f97316", "#0f766e", "#2563eb", "#9333ea", "#dc2626", "#64748b"];

const FACTOR_LABELS = {
  business_scorecard_agent: "业务基准模型",
  crude_cost_agent: "原油成本",
  market_structure_agent: "市场结构",
  supply_inventory_agent: "供应与库存",
  demand_seasonality_agent: "需求与季节性",
  refined_oil_news_agent: "成品油资讯",
  shandong_spot_jump_agent: "山东现货跳变",
  agent_judge_agent: "智能体裁判",
  policy_cycle_agent: "调价窗口与政策",
  event_risk_agent: "事件风险",
};

const SCORECARD_GROUP_LABELS = {
  cost: "成本侧",
  supply: "供应侧",
  demand: "需求侧 / 产销率",
  sentiment: "情绪侧",
  inventory: "库存侧",
  policy: "政策侧",
  seasonality: "季节性",
};

const SCORECARD_FEATURE_LABELS = {
  brent_change_usd_d1: "Brent 日涨跌",
  brent_change_usd_d3: "Brent 三日涨跌",
  brent_change_usd_w1: "Brent 周度涨跌",
  brent_change_usd_mom: "Brent 月度涨跌",
  gasoline_crack_percentile: "汽油裂解价差分位",
  gasoline_crack_trend_d1: "汽油裂解趋势",
  gasoline_crack_trend_monthly: "汽油裂解月度趋势",
  shandong_cdu_utilization_weekly: "山东地炼常减压开工率",
  shandong_cdu_utilization_percentile_weekly: "山东地炼开工率分位",
  shandong_cdu_utilization_percentile_monthly: "山东地炼月度开工率分位",
  shandong_refinery_load_news_adjustment_d1: "山东炼厂负荷新闻修正",
  shandong_refinery_load_news_adjustment_d3: "山东炼厂负荷新闻修正",
  shandong_refinery_load_news_adjustment_w1: "山东炼厂负荷新闻修正",
  sales_production_ratio_d1: "产销率",
  sales_production_ratio_d3_avg: "三日产销率均值",
  sales_production_ratio_w1_avg: "周度产销率均值",
  trader_sentiment_label_d1: "贸易商情绪",
  trader_sentiment_label_d3: "贸易商情绪",
  trader_sentiment_label_w1: "贸易商情绪",
  inventory_trend_weekly: "库存趋势",
  price_window_expectation_w1: "发改委调价窗口预期",
  monthly_seasonality_phase: "月度季节性",
  next_month_maintenance_plan: "下月检修计划",
  monthly_utilization_band: "月度开工区间",
  restocking_rhythm_monthly: "补库节奏",
  holiday_demand_delta_monthly: "节假日需求变化",
  refinery_inventory_monthly: "炼厂库存",
  social_inventory_cycle_position: "社会库存周期",
  market_sentiment_monthly: "月度市场情绪",
};

const SCORECARD_BUCKET_LABELS = {
  low_utilization: "低开工率",
  medium_low_utilization: "中低开工率",
  middle_utilization: "中等开工率",
  medium_high_utilization: "中高开工率",
  high_utilization: "高开工率",
  large_up: "大幅上涨",
  small_up: "小幅上涨",
  flat: "持平",
  small_down: "小幅下跌",
  large_down: "大幅下跌",
  expanded: "裂解扩大",
  contracted: "裂解收窄",
  bullish_active: "偏多活跃",
  neutral_flat: "中性",
  unchanged_from_previous: "与前一条一致，按0分",
  bearish_selling: "偏空出货",
  peak: "旺季",
  off: "淡季",
  neutral: "平季",
  missing: "数据缺失",
  unmatched: "未命中",
  bounded_numeric: "数值修正",
  unsupported_method: "暂不支持",
  stable_load: "负荷稳定",
  mid_band_balanced: "中位均衡",
  stable_small_lots: "小单稳定",
  unchanged: "变化不大",
  balanced: "均衡",
  low_percentile: "低分位",
  medium_low_percentile: "中低分位",
  middle_percentile: "中位",
  medium_high_percentile: "中高分位",
  high_percentile: "高分位",
};

const FIELD_LABELS = {
  brent_change_usd: "Brent预测/结算变化",
  brent_change_1d: "Brent日变化",
  brent_change_3d: "Brent三日变化",
  brent_change_5d: "Brent周度变化",
  brent_change_20d: "Brent月度变化",
  gasoline_crack_percentile: "汽油裂解价差分位",
  mtbe_change_3d: "MTBE三日变化",
  naphtha_change_3d: "石脑油三日变化",
  avg_target_minus_shandong_spread: "区域均值-山东价差",
  sd_cn_spread: "山东-全国价差",
  gas_price_change: "山东92#价格变化",
  gas_price_change_1d: "山东92#日变化",
  gas_price_change_3d: "山东92#三日变化",
  shandong_cdu_utilization_weekly: "山东地炼常减压开工率",
  utilization_percentile: "山东地炼开工率分位",
  inventory_total_percentile: "库存合计分位",
  utilization_change: "山东地炼开工率变化",
  refining_profit: "山东炼油利润",
  sales_production_ratio: "山东地炼产销率",
  ratio_column: "产销率取数口径",
  monthly_ratio_change: "月度产销率变化",
  season_score: "季节性修正",
  holiday_score: "节假日修正",
  expected_adjustment_yuan: "调价预测金额",
  days_to_next_window: "距离调价窗口天数",
  last_adjust: "上轮调价幅度",
  llm_labels: "资讯标签",
  label: "成交标签",
  trader_mindset: "贸易商心态",
  quote_behavior: "报价行为",
  spot_strength_score: "山东现货跳变强度",
  regime: "现货跳变状态",
  jump_delta_d1: "D1点位修正",
  risk_gate: "事件风险闸门",
  brent_change_abs: "Brent波动绝对值",
};

const VIEW_PERMISSION_MAP = {
  home: "workbench.view",
  clearview: "workbench.view",
  accuracy: "workbench.view",
  policy: "policy.view",
  agents: "agents.view",
  profile: "profile.view",
  permissions: "permissions.manage",
};

const MODULE_LABELS = {
  workbench: "研究台",
  clearview: "一屏看清",
  accuracy: "预测复盘",
  policy: "政策与事件",
  agents: "智能体管理",
  profile: "个人中心",
  permissions: "权限管理",
};

const dom = {
  navLogo: document.getElementById("nav-logo"),
  mainTabs: Array.from(document.querySelectorAll(".main-tab")),
  views: Array.from(document.querySelectorAll(".view")),
  agentSubTabs: Array.from(document.querySelectorAll(".sub-tab")),
  agentSubViews: Array.from(document.querySelectorAll(".agent-subview")),
  sortTabs: Array.from(document.querySelectorAll(".sort-tab")),
  themeButtons: Array.from(document.querySelectorAll("[data-theme-value]")),
  agentsSubnav: document.getElementById("agents-subnav"),
  globalStatus: document.getElementById("global-status"),
  marketRefreshMeta: document.getElementById("market-refresh-meta"),
  accountEntry: document.getElementById("account-entry"),
  accountAvatar: document.getElementById("account-avatar"),
  accountName: document.getElementById("account-name"),
  accountTitle: document.getElementById("account-title"),
  logoutButton: document.getElementById("logout-button"),

  alertMeta: document.getElementById("alert-meta"),
  alertList: document.getElementById("alert-list"),
  priceHistoryMeta: document.getElementById("price-history-meta"),
  priceHistoryRange: document.getElementById("price-history-range"),
  priceHistorySeries: document.getElementById("price-history-series"),
  priceHistoryChart: document.getElementById("price-history-chart"),
  oilchemInventoryMeta: document.getElementById("oilchem-inventory-meta"),
  oilchemInventoryStart: document.getElementById("oilchem-inventory-start"),
  oilchemInventoryEnd: document.getElementById("oilchem-inventory-end"),
  oilchemInventoryRefresh: document.getElementById("oilchem-inventory-refresh"),
  oilchemInventoryExport: document.getElementById("oilchem-inventory-export"),
  oilchemInventoryFilters: document.getElementById("oilchem-inventory-filters"),
  oilchemInventorySelected: document.getElementById("oilchem-inventory-selected"),
  oilchemInventorySummary: document.getElementById("oilchem-inventory-summary"),
  oilchemInventoryTable: document.getElementById("oilchem-inventory-table"),
  accuracyMeta: document.getElementById("accuracy-meta"),
  accuracyRefresh: document.getElementById("accuracy-refresh"),
  accuracySummary: document.getElementById("accuracy-summary"),
  accuracyRuleMeta: document.getElementById("accuracy-rule-meta"),
  accuracyChart: document.getElementById("accuracy-chart"),
  accuracyList: document.getElementById("accuracy-list"),

  snapshotMode: document.getElementById("snapshot-mode"),
  snapshotDate: document.getElementById("snapshot-date"),
  priceSnapshot: document.getElementById("price-snapshot"),

  researchMeta: document.getElementById("research-meta"),
  narrativeStatus: document.getElementById("narrative-status"),
  researchForm: document.getElementById("research-form"),
  scenarioInput: document.getElementById("scenario-input"),
  newsToggle: document.getElementById("toggle-news"),
  eventToggle: document.getElementById("toggle-event"),
  narrativeToggle: document.getElementById("toggle-narrative"),
  refreshButton: document.getElementById("refresh-button"),
  horizonSwitch: document.getElementById("horizon-switch"),
  outrightPanel: document.getElementById("outright-panel"),
  spreadHeatmap: document.getElementById("spread-heatmap"),
  spreadGrid: document.getElementById("spread-grid"),
  freightSettingsPanel: document.getElementById("freight-settings-panel"),
  regionalHorizonLabel: document.getElementById("regional-horizon-label"),
  spreadDetailDialog: document.getElementById("spread-detail-dialog"),
  spreadDetailTitle: document.getElementById("spread-detail-title"),
  spreadDetailSubtitle: document.getElementById("spread-detail-subtitle"),
  spreadDetailContent: document.getElementById("spread-detail-content"),
  spreadDetailClose: document.getElementById("spread-detail-close"),

  briefingPanel: document.querySelector(".briefing-panel"),
  briefingMeta: document.getElementById("briefing-meta"),
  briefingToggle: document.getElementById("briefing-toggle"),
  briefingGenerate: document.getElementById("briefing-generate"),
  briefingContent: document.getElementById("briefing-content"),

  chatLog: document.getElementById("chat-log"),
  chatPanel: document.querySelector(".chat-panel"),
  chatReset: document.querySelector(".chat-reset-button"),
  chatHistoryToggle: document.querySelector(".chat-history-button"),
  chatHistoryPanel: document.getElementById("chat-history-panel"),
  chatHistoryList: document.getElementById("chat-history-list"),
  chatHistoryClear: document.getElementById("chat-history-clear"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  chatSubmit: document.getElementById("chat-submit"),
  quickAskButtons: Array.from(document.querySelectorAll("[data-quick-ask]")),

  policyPageMeta: document.getElementById("policy-page-meta"),
  newsDateSelect: document.getElementById("news-date-select"),
  policyDateSelect: document.getElementById("policy-date-select"),
  refinedNewsList: document.getElementById("refined-news-list"),
  eventNewsList: document.getElementById("event-news-list"),
  policyList: document.getElementById("policy-list"),

  agentStatusChip: document.getElementById("agent-status-chip"),
  agentRefresh: document.getElementById("agent-refresh"),
  agentOverviewGrid: document.getElementById("agent-overview-grid"),
  agentGraphSvg: document.getElementById("agent-graph-svg"),
  agentGraphNodes: document.getElementById("agent-graph-nodes"),
  scopeControls: document.getElementById("scope-controls"),
  optimizationScopeControls: document.getElementById("optimization-scope-controls"),
  runList: document.getElementById("run-list"),
  runDetailMeta: document.getElementById("run-detail-meta"),
  runDetail: document.getElementById("run-detail"),
  agentHistoryMeta: document.getElementById("agent-history-meta"),
  agentHistoryTabs: document.getElementById("agent-history-tabs"),
  agentHistoryList: document.getElementById("agent-history-list"),
  proposalGenerate: document.getElementById("proposal-generate"),
  proposalApprove: document.getElementById("proposal-approve"),
  proposalReject: document.getElementById("proposal-reject"),
  proposalStatus: document.getElementById("proposal-status"),
  proposalPanel: document.getElementById("proposal-panel"),

  profileStatusChip: document.getElementById("profile-status-chip"),
  profileUsername: document.getElementById("profile-username"),
  profileDisplayName: document.getElementById("profile-display-name"),
  profileLastLogin: document.getElementById("profile-last-login"),
  profileUpdatedAt: document.getElementById("profile-updated-at"),
  profileActiveStatus: document.getElementById("profile-active-status"),
  profilePermissionCount: document.getElementById("profile-permission-count"),
  profilePermissionGroups: document.getElementById("profile-permission-groups"),
  profileForm: document.getElementById("profile-form"),
  profileDisplayInput: document.getElementById("profile-display-input"),
  profileTitleInput: document.getElementById("profile-title-input"),
  profilePasswordInput: document.getElementById("profile-password-input"),
  profilePasswordConfirmInput: document.getElementById("profile-password-confirm-input"),
  profileFormMeta: document.getElementById("profile-form-meta"),
  profileSubmit: document.getElementById("profile-submit"),

  permissionMeta: document.getElementById("permission-meta"),
  permissionCounts: document.getElementById("permission-counts"),
  createUserForm: document.getElementById("user-create-form"),
  createUsername: document.getElementById("create-username"),
  createDisplayName: document.getElementById("create-display-name"),
  createTitle: document.getElementById("create-title"),
  createPassword: document.getElementById("create-password"),
  createIsActive: document.getElementById("create-is-active"),
  createRoleGroups: document.getElementById("create-role-groups"),
  createUserMeta: document.getElementById("create-user-meta"),
  createUserSubmit: document.getElementById("create-user-submit"),
  userList: document.getElementById("user-list"),
  userEditForm: document.getElementById("user-edit-form"),
  selectedUserCaption: document.getElementById("selected-user-caption"),
  selectedUserMeta: document.getElementById("selected-user-meta"),
  editDisplayName: document.getElementById("edit-display-name"),
  editTitle: document.getElementById("edit-title"),
  editIsActive: document.getElementById("edit-is-active"),
  editRoleGroups: document.getElementById("edit-role-groups"),
  editUserMeta: document.getElementById("edit-user-meta"),
  editUserSubmit: document.getElementById("edit-user-submit"),
  usageLogMeta: document.getElementById("usage-log-meta"),
  usageLogList: document.getElementById("usage-log-list"),
};

const state = {
  currentView: "home",
  currentAgentSubView: "overview",
  selectedHorizon: "D1",
  availableHorizons: [...DEFAULT_HORIZONS],
  dashboard: null,
  baselineDashboard: null,
  narrativeCache: {},
  marketSnapshot: null,
  oilchemInventory: null,
  oilchemInventoryFilters: {
    product: "不限",
    owner: "不限",
    regions: [],
  },
  priceHistory: null,
  priceHistoryRequestToken: 0,
  priceHistoryDays: 30,
  priceHistorySeries: [...PRICE_HISTORY_DEFAULT_SERIES],
  predictionAccuracy: null,
  freightSettings: [],
  dashboardLoading: false,
  freightLoading: false,
  policyFeed: null,
  latestBriefing: null,
  briefingCollapsed: false,
  briefingManualOverride: false,
  briefingCollapseTimer: null,
  chatMessages: [],
  chatSessions: [],
  currentChatSessionId: null,
  chatHistoryOpen: false,
  narrativeToken: 0,
  snapshotTimer: null,
  brentTimer: null,
  policyTimer: null,
  policyManualDate: false,
  policySortMode: "importance",
  agentOverview: null,
  agentGraph: null,
  agentRuns: [],
  selectedRunId: null,
  selectedRunDetail: null,
  selectedTraceAgent: null,
  agentHistory: null,
  optimizationState: null,
  theme: "light",
  brentLive: null,
  currentUser: null,
  permissionCatalog: [],
  roleCatalog: [],
  users: [],
  usageLogs: [],
  selectedUserId: null,
  permissionWorkspaceLoaded: false,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("\n", "&#10;");
}

function cloneData(value) {
  return JSON.parse(JSON.stringify(value));
}

function permissionCodes() {
  return new Set(state.currentUser?.permission_codes || []);
}

function hasPermission(permissionCode) {
  if (!permissionCode) return true;
  const codes = permissionCodes();
  return codes.has("admin") || codes.has(permissionCode);
}

function hasViewAccess(view) {
  return hasPermission(VIEW_PERMISSION_MAP[view]);
}

function firstAccessibleView(preferredView = "home") {
  const ordered = [preferredView, "home", "clearview", "accuracy", "policy", "agents", "profile", "permissions"];
  for (const view of ordered) {
    if (hasViewAccess(view)) return view;
  }
  return "profile";
}

function groupedPermissions(items) {
  const groups = new Map();
  for (const item of items || []) {
    const key = item.module_code || "others";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  return Array.from(groups.entries()).map(([moduleCode, permissions]) => ({
    moduleCode,
    moduleLabel: MODULE_LABELS[moduleCode] || moduleCode,
    permissions,
  }));
}

function initials(text) {
  const source = String(text || "").trim();
  if (!source) return "研";
  return source.slice(0, 1).toUpperCase();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatNumber(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
}

function formatNumberTrim(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  const fixed = Number(value).toFixed(digits);
  return fixed.includes(".") ? fixed.replace(/\.?0+$/, "") : fixed;
}

function formatDate(value) {
  if (!value) return "-";
  return String(value).slice(0, 10);
}

function formatDateTime(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 19);
}

function formatTime(value) {
  const normalized = formatDateTime(value);
  if (normalized === "-") return "-";
  return normalized.length >= 19 ? normalized.slice(11, 19) : normalized;
}

function priceSnapshotDate(key, snapshot) {
  if (key === "brent_active_settlement") return state.brentLive?.as_of_date || snapshot?.as_of_date;
  return snapshot?.as_of_date;
}

function priceSnapshotTime(key, snapshot) {
  if (key === "brent_active_settlement") {
    return state.brentLive?.generated_at || state.brentLive?.metadata?.wind?.time || snapshot?.generated_at;
  }
  return snapshot?.metadata?.quality?.[key]?.collect_time || snapshot?.generated_at;
}

function renderPriceTimestamp(dateValue, timeValue, options = {}) {
  const timeAttr = options.liveTime ? ' data-brent-live-time="true"' : "";
  return `
    <div class="price-time-meta">
      <span>价格日期 ${escapeHtml(formatDate(dateValue))}</span>
      <span${timeAttr}>刷新时间 ${escapeHtml(formatTime(timeValue))}</span>
    </div>`;
}

function toneClass(direction) {
  if (direction === "up") return "tone-up";
  if (direction === "down") return "tone-down";
  if (direction === "strong_up" || direction === "weak_up") return "tone-up";
  if (direction === "strong_down" || direction === "weak_down") return "tone-down";
  return "tone-flat";
}

function shortDirectionLabel(direction, isSpread = false) {
  const outright = {
    up: "上行",
    down: "下行",
    flat: "震荡",
  };
  const spreads = {
    up: "走扩",
    down: "收敛",
    flat: "震荡",
  };
  return (isSpread ? spreads : outright)[direction] || "未明";
}

function directionLabel(direction, isSpread = false) {
  const outright = {
    up: "价格上行",
    down: "价格下行",
    flat: "价格震荡",
  };
  const spreads = {
    up: "价差走扩",
    down: "价差收敛",
    flat: "价差震荡",
  };
  return (isSpread ? spreads : outright)[direction] || "方向未明";
}

function businessDirectionInfo(prediction, isSpread = false) {
  const business = prediction?.raw_context?.business_direction;
  if (business?.display_label) {
    return {
      label: business.display_label,
      tone: business.tone || prediction?.direction_label || "flat",
      usage: business.usage || "",
      reason: business.reason || "",
      grade: business.operating_grade || "-",
    };
  }
  return {
    label: directionLabel(prediction?.direction_label, isSpread),
    tone: prediction?.direction_label || "flat",
    usage: "",
    reason: "",
    grade: "-",
  };
}

function statusText(status) {
  return {
    online: "在线",
    attention: "关注",
    disabled: "停用",
    idle: "空闲",
  }[status] || status || "未知";
}

function statusClass(status) {
  return `status-${status || "idle"}`;
}

function marketModeLabel(metadata) {
  const mode = metadata?.market_data_mode;
  if (mode === "wind_price_api") return "Wind 实时";
  if (mode === "wind_eta") return "Wind + ETA";
  if (mode === "wind_eta_with_fallback_fill") return "Wind + ETA + 本地补齐";
  if (mode === "wind_with_local_snapshot") return "Wind + 本地快照";
  if (mode === "eta") return "ETA 实时";
  if (mode === "eta_with_fallback_fill") return "ETA 实时 + 本地补齐";
  if (mode === "fallback_local_snapshot") return "本地快照降级";
  return "数据模式未知";
}

function marketReasonLabel(reason) {
  if (!reason) return "实时口径";
  if (reason === "wind_unavailable") return "Wind 不可用，ETA 补位";
  if (reason === "wind_eta_unavailable") return "Wind/ETA 不可用，本地补位";
  if (reason === "eta_unavailable") return "本地补位";
  if (reason === "eta_snapshot_empty") return "快照补位";
  if (String(reason).startsWith("missing:")) return "部分补位";
  const text = String(reason);
  if (text.includes("local_market_overrides") || text.includes("local_factor_overlay")) {
    const marketMatch = text.match(/local_market_overrides=(\d+)/);
    const factorMatch = text.match(/local_factor_overlay=(\d+)/);
    const parts = [];
    if (marketMatch) parts.push(`人工价格修正 ${marketMatch[1]} 条`);
    if (factorMatch) parts.push(`本地因子补充 ${factorMatch[1]} 条`);
    return parts.join("；") || "本地数据修正";
  }
  return text;
}

function confidenceText(label, score) {
  const pct = valueToPercent(score);
  const mapping = {
    high: "高可靠",
    medium: "中可靠",
    low: "低可靠",
  };
  return `${mapping[label] || label || "-"} / ${pct}`;
}

function valueToPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function emptyState(text) {
  return `<div class="empty-state">${escapeHtml(text)}</div>`;
}

function formatPercentValue(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function predictionStatusLabel(status) {
  return status === "evaluated" ? "已验证" : "待验证";
}

function hitLabel(value) {
  if (value === true) return "命中";
  if (value === false) return "未命中";
  return "待验证";
}

function actualDirectionFromChange(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  if (Number(value) > 0) return "上行";
  if (Number(value) < 0) return "下行";
  return "震荡";
}

function normalizeMetricToken(key, value) {
  const mapping = {
    target_spread: ["目标价差", "元/吨", 2],
    current_spread: ["当前价差", "元/吨", 2],
    current_price: ["当前价格", "元/吨", 2],
    positive_hits: ["正向信号", "", 1],
    negative_hits: ["反向信号", "", 1],
    brent: ["布伦特", "美元/桶", 2],
    brent_change: ["布伦特变动", "美元/桶", 2],
    brent_change_usd_d1: ["Brent日涨跌", "美元/桶", 2],
    brent_change_usd_d3: ["Brent三日涨跌", "美元/桶", 2],
    brent_change_usd_w1: ["Brent周度涨跌", "美元/桶", 2],
    gasoline_crack_percentile: ["汽油裂解价差分位", "%", 2],
    sales_production_ratio_d1: ["产销率", "%", 2],
    freight: ["运费", "元/吨", 2],
    freight_spread: ["运费差", "元/吨", 2],
    arrival_premium: ["到岸升贴水", "元/吨", 2],
    discount: ["折价", "元/吨", 2],
    premium: ["升水", "元/吨", 2],
  };
  const normalizedKey = String(key || "").trim().toLowerCase();
  const [label, unit, digits] = mapping[normalizedKey] || [normalizedKey.replaceAll("_", " "), "", 2];
  const formattedValue = formatNumberTrim(value, digits);
  return `${label} ${formattedValue}${unit ? ` ${unit}` : ""}`.trim();
}

function normalizeNarrativeText(text) {
  if (text == null) return "";
  let normalized = String(text)
    .trim()
    .replace(/\bbullish_active\b/gi, "成交偏强")
    .replace(/\bneutral_flat\b/gi, "成交平稳")
    .replace(/\bbearish_selling\b/gi, "偏空出货")
    .replace(/\bsales_production_ratio_d1\b/gi, "产销率")
    .replace(/\bbrent_change_usd_d1\b/gi, "Brent日涨跌")
    .replace(/\bgasoline_crack_percentile\b/gi, "汽油裂解价差分位")
    .replace(/\bflat\b/gi, "震荡")
    .replace(/\bup\b/gi, "上行")
    .replace(/\bdown\b/gi, "下行")
    .replace(/([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(-?\d+(?:\.\d+)?)/g, (_, key, value) => normalizeMetricToken(key, value))
    .replace(/(-?\d+\.\d{4,})/g, (match) => formatNumberTrim(match))
    .replace(/,\s*/g, "，")
    .replace(/;\s*/g, "；")
    .replace(/\s{2,}/g, " ");
  return normalized;
}

function displaySourceLabel(source) {
  const normalized = String(source || "").trim();
  const mapping = {
    jinshi_crude_news: "事件快讯",
    brent_daily_report: "Brent日报",
    ndrc_refined_oil_policy: "发改委政策",
    jlc_refinedoil_hot_browser: "成品油资讯",
    jlc_refinedoil_archive_browser: "成品油资讯",
    oilchem_refinedoil_channel: "成品油资讯",
    oilchem_shandong_spot_daily_report: "隆众山东日评",
    cnenergy_oil_gas_fulltext: "成品油资讯",
  };
  return mapping[normalized] || normalized.replaceAll("_", " ") || "-";
}

function resolveStoredTheme() {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    const normalized = LEGACY_THEME_MAP[stored] || stored;
    return THEME_OPTIONS.includes(normalized) ? normalized : "light";
  } catch {
    return "light";
  }
}

function applyTheme(theme) {
  const normalized = LEGACY_THEME_MAP[theme] || theme;
  const nextTheme = THEME_OPTIONS.includes(normalized) ? normalized : "light";
  state.theme = nextTheme;
  document.body.dataset.theme = nextTheme;
  dom.themeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.themeValue === nextTheme);
  });
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
  } catch {}
}

function setupThemeControls() {
  const [lightButton, darkButton, ...extraButtons] = dom.themeButtons;
  if (lightButton) {
    lightButton.dataset.themeValue = "light";
    lightButton.textContent = "☀";
    lightButton.setAttribute("aria-label", "浅色主题");
  }
  if (darkButton) {
    darkButton.dataset.themeValue = "dark";
    darkButton.textContent = "◐";
    darkButton.setAttribute("aria-label", "深色主题");
  }
  extraButtons.forEach((button) => {
    button.hidden = true;
    button.dataset.themeValue = "";
  });
  dom.themeButtons = [lightButton, darkButton].filter(Boolean);
}

function renderMultilineText(text) {
  return escapeHtml(normalizeNarrativeText(text || "")).replaceAll("\n", "<br />");
}

async function fetchJson(url, options = {}) {
  const { timeoutMs, ...fetchOptions } = options;
  const controller = timeoutMs ? new AbortController() : null;
  let timeoutId = null;
  if (controller) {
    const externalSignal = fetchOptions.signal;
    fetchOptions.signal = controller.signal;
    if (externalSignal) {
      externalSignal.addEventListener("abort", () => controller.abort(), { once: true });
    }
    timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  }

  let response;
  try {
    response = await fetch(url, fetchOptions);
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error("请求超时，请稍后重试或缩小问题范围");
    }
    throw error;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
  if (response.status === 401) {
    if (window.location.pathname !== "/login") {
      window.location.replace("/login");
    }
    throw new Error("请先登录");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function setGlobalStatus(text, mode = "idle") {
  if (!dom.globalStatus || dom.globalStatus.hidden) return;
  dom.globalStatus.textContent = text;
  dom.globalStatus.className = `chip status-chip${mode === "loading" ? " is-loading" : ""}${mode === "error" ? " is-error" : ""}`;
}

function setChip(target, text, mode = "idle") {
  if (!target || target.hidden) return;
  const extraClasses = Array.from(target.classList).filter(
    (name) => !["chip", "is-loading", "is-error"].includes(name)
  );
  target.textContent = text;
  target.className = `chip ${extraClasses.join(" ")}${mode === "loading" ? " is-loading" : ""}${mode === "error" ? " is-error" : ""}`.trim();
}

function requestBody(overrides = {}) {
  return {
    horizon: state.selectedHorizon,
    horizons: state.availableHorizons,
    scenario_text: dom.scenarioInput.value.trim() || null,
    use_llm_explainer: false,
    enable_refined_news: dom.newsToggle.checked,
    enable_event_risk: dom.eventToggle.checked,
    persist_run: true,
    ...overrides,
  };
}

function freightSettingMap() {
  return Object.fromEntries((state.freightSettings || []).map((item) => [item.region_code, item]));
}

function applyFreightSettingsToRegionalPredictions() {
  if (!state.dashboard || !state.freightSettings?.length) return;
  const settings = freightSettingMap();
  const applyToItem = (item) => {
    const raw = item?.raw_context || {};
    const regionCode = raw.counter_region_code || item.region_code;
    const setting = settings[regionCode];
    if (!setting) return item;
    const nextRaw = { ...raw };
    const freight = Number(setting.freight_value);
    if (Number.isFinite(freight)) {
      nextRaw.freight_estimate = freight;
      const actualSpread = regionalActualSpread({ ...item, raw_context: nextRaw });
      const predictedSpread = regionalPredictedSpread({ ...item, raw_context: nextRaw });
      nextRaw.netback_spread = actualSpread == null ? null : Number((Number(actualSpread) - freight).toFixed(2));
      nextRaw.predicted_netback_spread = predictedSpread == null ? null : Number((Number(predictedSpread) - freight).toFixed(2));
    }
    nextRaw.freight_source = setting.source_type || nextRaw.freight_source;
    nextRaw.freight_updated_at = setting.updated_at || nextRaw.freight_updated_at;
    nextRaw.freight_as_of_date = setting.as_of_date || nextRaw.freight_as_of_date;
    nextRaw.freight_components = setting.components || nextRaw.freight_components || [];
    nextRaw.freight_calculation = setting.calculation || nextRaw.freight_calculation;
    nextRaw.freight_workbook_value = setting.workbook_value ?? nextRaw.freight_workbook_value;
    return { ...item, raw_context: nextRaw };
  };
  if (state.dashboard.regional_spread_predictions_by_horizon) {
    state.dashboard.regional_spread_predictions_by_horizon = Object.fromEntries(
      Object.entries(state.dashboard.regional_spread_predictions_by_horizon).map(([horizon, items]) => [
        horizon,
        (items || []).map(applyToItem),
      ])
    );
  }
  if (state.dashboard.regional_spread_predictions) {
    state.dashboard.regional_spread_predictions = state.dashboard.regional_spread_predictions.map(applyToItem);
  }
}

function refreshFreightDependentViews() {
  applyFreightSettingsToRegionalPredictions();
  const regional = selectedRegionalPredictions();
  renderSpreadHeatmap(regional);
  renderSpreadCards(regional);
  renderFreightSettings(regional);
}

function selectedOutrightPrediction() {
  if (!state.dashboard) return null;
  return (
    (state.dashboard.outright_predictions || []).find((item) => item.horizon === state.selectedHorizon) ||
    state.dashboard.outright_prediction ||
    null
  );
}

function selectedRegionalPredictions() {
  if (!state.dashboard) return [];
  return (
    state.dashboard.regional_spread_predictions_by_horizon?.[state.selectedHorizon] ||
    state.dashboard.regional_spread_predictions ||
    []
  );
}

function regionalPredictedPrice(item) {
  const raw = item?.raw_context || {};
  if (raw.predicted_region_price != null) return Number(raw.predicted_region_price);
  if (raw.predicted_shandong_price != null && item?.point_value != null) {
    return Number(raw.predicted_shandong_price) + Number(item.point_value);
  }
  return null;
}

function regionalPredictedSpread(item) {
  const raw = item?.raw_context || {};
  if (raw.predicted_region_minus_shandong_spread != null) {
    return Number(raw.predicted_region_minus_shandong_spread);
  }
  if (raw.predicted_shandong_minus_region_spread != null) {
    return -Number(raw.predicted_shandong_minus_region_spread);
  }
  return item?.point_value != null ? Number(item.point_value) : null;
}

function regionalActualSpread(item) {
  const raw = item?.raw_context || {};
  if (raw.actual_region_minus_shandong_spread != null) return Number(raw.actual_region_minus_shandong_spread);
  if (raw.actual_shandong_minus_region_spread != null) return -Number(raw.actual_shandong_minus_region_spread);
  if (raw.current_spread != null) return Number(raw.current_spread);
  return null;
}

function regionalPredictionVariants(item) {
  const raw = item?.raw_context || {};
  const variants = Array.isArray(raw.regional_prediction_variants) ? raw.regional_prediction_variants : [];
  if (variants.length) return variants;
  return [
    {
      model_name: "区域智能体综合预测",
      prediction_type: "regional_composite",
      direction_label: item?.direction_label,
      predicted_region_price: regionalPredictedPrice(item),
      predicted_region_minus_shandong_spread: regionalPredictedSpread(item),
      predicted_delta: raw.predicted_delta,
      predicted_region_minus_shandong_spread_range_lower: raw.predicted_region_minus_shandong_spread_range_lower,
      predicted_region_minus_shandong_spread_range_upper: raw.predicted_region_minus_shandong_spread_range_upper,
      basis: raw.prediction_method_note,
    },
  ];
}

function regionalVariantLabel(variant) {
  if (variant?.prediction_type === "regional_baseline") return "基准";
  if (variant?.prediction_type === "regional_composite") return "综合";
  return variant?.model_name || "预测";
}

function regionalVariantPrice(variant) {
  return variant?.predicted_region_price != null ? Number(variant.predicted_region_price) : null;
}

function regionalVariantSpread(variant) {
  if (variant?.predicted_region_minus_shandong_spread != null) {
    return Number(variant.predicted_region_minus_shandong_spread);
  }
  if (variant?.predicted_shandong_minus_region_spread != null) {
    return -Number(variant.predicted_shandong_minus_region_spread);
  }
  return null;
}

function renderRegionalVariantRows(item, options = {}) {
  const { compact = false } = options;
  const rows = regionalPredictionVariants(item).slice(0, 2);
  return rows
    .map((variant) => {
      const direction = variant.direction_label || item?.direction_label || "flat";
      return `
        <div class="${compact ? "regional-variant-row is-compact" : "regional-variant-row"}">
          <span>${escapeHtml(regionalVariantLabel(variant))}</span>
          <strong class="${toneClass(direction)}">${formatNumber(regionalVariantPrice(variant))}</strong>
          <em>${escapeHtml(shortDirectionLabel(direction, true))}</em>
          <small>区域-山东价差 ${formatNumber(regionalVariantSpread(variant))}</small>
        </div>`;
    })
    .join("");
}

function renderMarketSnapshot() {
  const snapshot = state.marketSnapshot;
  if (!snapshot) {
    dom.priceSnapshot.innerHTML = emptyState("价格快照加载中");
    return;
  }

  setChip(dom.snapshotMode, marketModeLabel(snapshot.metadata));
  dom.snapshotMode.className = "chip accent-chip";
  setChip(dom.snapshotDate, `更新于 ${formatDateTime(snapshot.generated_at)}`);
  setChip(dom.marketRefreshMeta, `快照 ${formatDateTime(snapshot.generated_at)}`);

  const previous = state.marketSnapshot?.__previousPrices || {};
  dom.priceSnapshot.innerHTML = PRICE_LABELS.map(([key, label], index) => {
    const value = snapshot.latest_prices?.[key];
    const changed = previous[key] != null && value != null && Number(previous[key]) !== Number(value);
    const featured = index === 0 ? " featured" : "";
    const flash = changed ? " is-flash" : "";
    const unit = key === "brent_active_settlement" ? "美元/桶" : "元/吨";
    return `
      <article class="metric-card${featured}${flash}">
        <div class="metric-top">
          <div class="metric-label">${escapeHtml(label)}</div>
          ${key === "brent_active_settlement" ? '<div class="live-pill">轮询中</div>' : ""}
        </div>
        <div class="metric-value">${formatNumber(value)}</div>
        <div class="metric-sub">
          <span>${unit}</span>
          <span>${escapeHtml(marketReasonLabel(snapshot.metadata?.market_data_reason))}</span>
        </div>
      </article>`;
  }).join("");
}

function renderHorizonButtons() {
  const predictions = state.dashboard?.outright_predictions || [];
  if (!predictions.length) {
    dom.horizonSwitch.innerHTML = "";
    return;
  }

  dom.horizonSwitch.innerHTML = predictions.map((item) => {
    const active = item.horizon === state.selectedHorizon ? " is-active" : "";
    const business = businessDirectionInfo(item);
    return `
      <button class="horizon-button${active}" type="button" data-horizon="${escapeHtml(item.horizon)}">
        <div class="horizon-code">${escapeHtml(item.horizon)} / ${escapeHtml(HORIZON_LABELS[item.horizon] || item.horizon)}</div>
        <div class="horizon-value ${toneClass(business.tone)}">${formatNumber(item.point_value)}</div>
        <small>${escapeHtml(business.label)}</small>
      </button>`;
  }).join("");

  dom.horizonSwitch.querySelectorAll("[data-horizon]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedHorizon = button.dataset.horizon;
      renderResearch();
      if (dom.narrativeToggle.checked) {
        await ensureNarrativeForSelectedHorizon();
      }
    });
  });
}

function renderFactorList(items, limit = 4) {
  const rows = [...(items || [])]
    .sort((a, b) => Math.abs(Number(b.contribution || 0)) - Math.abs(Number(a.contribution || 0)))
    .slice(0, limit);


  return rows.map((item) => {
    const label = FACTOR_LABELS[item.factor_name] || item.factor_name || "未命名因子";
    return `
      <div class="factor-item">
        <div class="factor-label">${escapeHtml(label)}</div>
        <div class="factor-value ${toneClass(item.contribution >= 0 ? "up" : "down")}">${formatNumber(item.contribution)}</div>
      </div>`;
  }).join("");
}

function scorecardGroupLabel(group) {
  return SCORECARD_GROUP_LABELS[group?.group_code] || group?.display_name || group?.group_code || "未命名分组";
}

function scorecardFeatureLabel(featureName) {
  return FIELD_LABELS[featureName] || SCORECARD_FEATURE_LABELS[featureName] || featureName || "未命名项目";
}

function fieldDisplayLabel(fieldName) {
  const key = String(fieldName || "").trim();
  if (!key) return "未命名字段";
  if (FIELD_LABELS[key] || SCORECARD_FEATURE_LABELS[key]) return FIELD_LABELS[key] || SCORECARD_FEATURE_LABELS[key];
  if (key.includes("inventory")) return "库存相关数据";
  if (key.includes("utilization") || key.includes("load")) return "开工率/负荷相关数据";
  if (key.includes("sales_production_ratio")) return "产销率数据";
  if (key.includes("brent")) return "Brent相关数据";
  if (key.includes("crack")) return "裂解价差数据";
  if (key.includes("spread")) return "价差数据";
  if (key.includes("adjust")) return "调价相关数据";
  return key.replace(/_/g, " ");
}

function scorecardMatchedLabel(label) {
  if (label == null || label === "") return "-";
  return SCORECARD_BUCKET_LABELS[label] || String(label);
}

function scorecardRuleHitText(feature, missing) {
  if (missing) return "缺失未计分";
  const matched = scorecardMatchedLabel(feature?.matched_label);
  if (matched && matched !== "-") return matched;
  const method = feature?.method;
  if (method === "bucket_score") return "按区间计分";
  if (method === "enum_score") return "按标签计分";
  if (method === "bounded_numeric") return "按修正值计分";
  if (method === "calendar_month_band") return "按月份计分";
  return "已按规则计分";
}

function scorecardValueText(value) {
  if (value == null || value === "") return "缺失";
  if (typeof value === "number") return formatNumber(value, Math.abs(value) >= 100 ? 2 : 4);
  if (typeof value === "boolean") return value ? "是" : "否";
  return SCORECARD_BUCKET_LABELS[value] || String(value);
}

function scorecardValueSourceText(feature) {
  if (!feature?.value_source) return "";
  const labels = {
    brent_daily_report: "Brent日报预测",
    feature_frame: "历史行情",
  };
  const source = labels[feature.value_source] || feature.value_source;
  const noteLabels = {
    rebound_to_previous_close: "回吐修复",
    settlement_change_vs_previous_settlement: "结算价-前日结算",
    daily_point_minus_anchor_close: "预测点位-前日结算",
    daily_point_minus_realtime: "预测点位-实时结算",
    weekly_delta: "周度delta",
  };
  const note = noteLabels[feature.value_note] || feature.value_note || "";
  return note ? `${source} / ${note}` : source;
}

function scorecardMethodText(method) {
  const labels = {
    bucket_score: "分档",
    enum_score: "枚举",
    bounded_numeric: "修正",
    calendar_month_band: "月份",
    manual_bucket: "人工阈值",
  };
  return labels[method] || method || "-";
}

function scorecardFeatureMethodText(feature) {
  const methodText = scorecardMethodText(feature?.method);
  if (methodText && methodText !== "-") return methodText;
  const name = String(feature?.feature_name || "");
  if (!name) return "规则项";
  if (name.includes("sentiment")) return "情绪标签";
  if (name.includes("adjustment")) return "修正项";
  if (name.includes("seasonality") || name.includes("holiday")) return "日历规则";
  if (name.includes("inventory") || name.includes("utilization") || name.includes("ratio") || name.includes("brent")) {
    return "分档";
  }
  if (name.includes("window") || name.includes("expectation")) return "窗口规则";
  return "规则项";
}

function scorecardUnresolvedReason(reason) {
  if (!reason) return "业务打分模型未给出明确阈值";
  const text = String(reason);
  if (text.includes("utilization-to-score thresholds")) return "原始业务模型未给出开工率到分数的明确阈值";
  return text;
}

function renderBusinessScorecard(scorecard) {
  const groups = scorecard?.group_scores || scorecard?.groups || [];
  if (!groups.length) {
    return '<div class="business-scorecard-empty muted-text">暂无业务打分明细</div>';
  }

  const unresolved = scorecard.unresolved_items || [];
  const quality = scorecard.data_quality || {};
  const available = Number(quality.available_count ?? 0);
  const missing = Number(quality.missing_count ?? 0);
  const total = groups.reduce((sum, group) => sum + Number(group.score || 0), 0);
  return `
    <div class="business-scorecard-summary">
      <div>
        <span>总分</span>
        <strong class="${toneClass(total >= 0 ? "up" : "down")}">${formatNumber(total)}</strong>
      </div>
      <div>
        <span>使用周期</span>
        <strong>${escapeHtml(scorecard.horizon_used || scorecard.horizon || "-")}</strong>
      </div>
      <div>
        <span>配置版本</span>
        <strong>${escapeHtml(scorecard.version || "-")}</strong>
      </div>
      <div>
        <span>数据覆盖</span>
        <strong class="${missing ? "is-warning" : ""}">${
          available + missing > 0 ? `${available}/${available + missing}` : "已核验"
        }</strong>
      </div>
    </div>

    <div class="business-scorecard-grid">
      ${groups
        .map((group) => {
          const features = group.features || [];
          const groupScore = Number(group.score || 0);
          const groupTone = groupScore >= 0 ? "up" : "down";
          return `
            <article class="business-scorecard-group">
              <div class="business-scorecard-group-head">
                <div>
                  <h4>${escapeHtml(scorecardGroupLabel(group))}</h4>
                  <span>封顶 ${formatNumber(group.score_cap)} 分</span>
                </div>
                <strong class="${toneClass(groupTone)}">${formatNumber(groupScore)}</strong>
              </div>
              <div class="business-scorecard-rows">
                ${features
                  .map((feature) => {
                    const score = Number(feature.score || 0);
                    const featureTone = score >= 0 ? "up" : "down";
                    const missing = feature.status === "missing";
                    return `
                      <div class="business-scorecard-row ${missing ? "is-missing" : ""}">
                        <div class="business-scorecard-name">
                          <span>${escapeHtml(scorecardFeatureLabel(feature.feature_name || feature.display_name))}</span>
                          <em>${escapeHtml(scorecardFeatureMethodText(feature))}${feature.is_adjustment ? " / 修正项" : ""}</em>
                        </div>
                        <div class="business-scorecard-value">
                          <span>取值</span>
                          <strong>${escapeHtml(scorecardValueText(feature.value))}</strong>
                          <em>${escapeHtml(missing ? "缺失按0分" : scorecardValueSourceText(feature) || "已取数")}</em>
                        </div>
                        <div class="business-scorecard-match">
                          <span>规则</span>
                          <strong>${escapeHtml(scorecardRuleHitText(feature, missing))}</strong>
                        </div>
                        <div class="business-scorecard-score">
                          <span>得分</span>
                          <strong class="${toneClass(featureTone)}">${formatNumber(score)}</strong>
                        </div>
                      </div>`;
                  })
                  .join("")}
            <div class="muted-text">区域价 - 山东价</div>
              </div>
            </article>`;
        })
        .join("")}
    </div>
    ${
      unresolved.length
        ? `<div class="business-scorecard-unresolved">
            ${unresolved
              .map(
                (item) => `
                  <div>
                    <strong>${escapeHtml(SCORECARD_GROUP_LABELS[item.group_code] || item.group_code || "未命名分组")}</strong>
                    <span>${escapeHtml(scorecardUnresolvedReason(item.reason))}</span>
                  </div>`
              )
              .join("")}
          </div>`
        : ""
    }`;
}

function renderBusinessScorecardPrediction(prediction) {
  if (!prediction) return "";
  const direction = prediction.direction_label || "flat";
  return `
    <div class="business-scorecard-prediction">
      <div class="business-scorecard-prediction-head">
        <span>业务模型预测</span>
        <strong class="${toneClass(direction)}">${escapeHtml(shortDirectionLabel(direction))}</strong>
      </div>
      <div class="business-scorecard-prediction-grid">
        <div>
          <span>预测点位</span>
          <strong>${formatNumber(prediction.point_value)}</strong>
        </div>
        <div>
          <span>预测变化</span>
          <strong class="${toneClass(direction)}">${formatNumber(prediction.predicted_delta)}</strong>
        </div>
        <div>
          <span>预测区间</span>
          <strong>${formatNumber(prediction.range_lower)} ~ ${formatNumber(prediction.range_upper)}</strong>
        </div>
        <div>
          <span>业务总分</span>
          <strong class="${toneClass(Number(prediction.score || 0) >= 0 ? "up" : "down")}">${formatNumber(prediction.score)}</strong>
        </div>
      </div>
      <p>${escapeHtml(prediction.basis || "业务打分模型独立预测，不参与智能体综合分加权。")}</p>
    </div>`;
}

function renderModelComparison(outright) {
  const businessPrediction = outright?.raw_context?.business_scorecard_prediction;
  if (!businessPrediction) return "";
  const agentDirection = outright.direction_label || "flat";
  const businessDirection = businessPrediction.direction_label || "flat";
  const agentDelta = outright.raw_context?.predicted_delta;
  return `
    <div class="model-comparison-strip">
      <article>
        <span>智能体综合预测</span>
        <strong class="${toneClass(agentDirection)}">${formatNumber(outright.point_value)}</strong>
        <em>${escapeHtml(shortDirectionLabel(agentDirection))} / ${formatNumber(agentDelta)} 元/吨</em>
        <small>${formatNumber(outright.range_lower)} ~ ${formatNumber(outright.range_upper)}</small>
      </article>
      <article>
        <span>业务打分模型预测</span>
        <strong class="${toneClass(businessDirection)}">${formatNumber(businessPrediction.point_value)}</strong>
        <em>${escapeHtml(shortDirectionLabel(businessDirection))} / ${formatNumber(businessPrediction.predicted_delta)} 元/吨</em>
        <small>${formatNumber(businessPrediction.range_lower)} ~ ${formatNumber(businessPrediction.range_upper)}</small>
      </article>
    </div>`;
}

function renderRegionalPriceForecastStrip(predictions) {
  if (!predictions?.length) return "";
  const cards = predictions.slice(0, 7).map((item) => {
    const region = item.raw_context?.counter_region_name || item.region_code;
    const current = regionalActualSpread(item);
    return `
      <article class="regional-forecast-card">
        <div class="regional-forecast-top">
          <span>${escapeHtml(region)}</span>
          <em class="${toneClass(item.direction_label)}">${escapeHtml(shortDirectionLabel(item.direction_label, true))}</em>
        </div>
        <div class="regional-variant-list">${renderRegionalVariantRows(item, { compact: true })}</div>
        <small>当前真实价差 ${formatNumber(current)}</small>
      </article>`;
  }).join("");
  return `
    <article class="info-card regional-forecast-panel">
      <div class="regional-forecast-head">
        <h3>区域单价预测</h3>
        <span>价差=区域预测价-山东预测价</span>
      </div>
      <div class="regional-forecast-strip">${cards}</div>
    </article>`;
}

function renderDriverList(items) {
  if (!items?.length) return '<div class="driver-item muted-text">暂无驱动信息</div>';
  return items.map((item) => `<div class="driver-item">${escapeHtml(normalizeNarrativeText(item))}</div>`).join("");
}

function renderAdviceList(items) {
  if (!items?.length) return '<div class="advice-item muted-text">暂无驱动信息</div>';
  return items.map((item) => {
    return `
      <div class="advice-item">
        <div class="advice-title">${escapeHtml(normalizeNarrativeText(item.title || "建议"))}</div>
        <div class="advice-action">${escapeHtml(normalizeNarrativeText(item.action || ""))}</div>
        ${
          item.trigger_condition || item.volume_suggestion || item.risk_stop
            ? `<div class="advice-meta-grid">
                ${item.trigger_condition ? `<span>触发：${escapeHtml(normalizeNarrativeText(item.trigger_condition))}</span>` : ""}
                ${item.volume_suggestion ? `<span>量化：${escapeHtml(normalizeNarrativeText(item.volume_suggestion))}</span>` : ""}
                ${item.risk_stop ? `<span>止损：${escapeHtml(normalizeNarrativeText(item.risk_stop))}</span>` : ""}
              </div>`
            : ""
        }
        <div class="advice-rationale">${escapeHtml(normalizeNarrativeText(item.rationale || ""))}</div>
      </div>`;
  }).join("");
}

function renderPredictionNarrativeSplit(outright) {
  const businessPrediction = outright?.raw_context?.business_scorecard_prediction || {};
  return `
    <article class="info-card insight-card narrative-split-card">
      <h3>核心驱动</h3>
      <div class="narrative-split-grid">
        <section>
          <span>智能体综合预测</span>
          <div class="driver-list">${renderDriverList(outright?.driver_summary)}</div>
        </section>
        <section>
          <span>业务打分模型预测</span>
          <div class="driver-list">${renderDriverList(businessPrediction.driver_summary)}</div>
        </section>
      </div>
    </article>

    <article class="info-card insight-card narrative-split-card">
      <h3>经营建议</h3>
      <div class="narrative-split-grid">
        <section>
          <span>智能体综合预测</span>
          <div class="advice-list">${renderAdviceList(outright?.operating_advice)}</div>
        </section>
        <section>
          <span>业务打分模型预测</span>
          <div class="advice-list">${renderAdviceList(businessPrediction.operating_advice)}</div>
        </section>
      </div>
    </article>`;
}

function llmAgentLabel(agentName) {
  const labels = {
    llm_event_interpreter_agent: "事件归因",
    llm_consistency_reviewer_agent: "一致性评审",
    llm_manual_review_agent: "人工复核",
  };
  return labels[agentName] || agentName || "智能体评审";
}

function renderLlmAgentReviews(reviews, limit = 3) {
  const items = (reviews || []).filter((item) => item?.agent_name?.startsWith("llm_")).slice(0, limit);
  if (!items.length) return "";
  return `
    <div class="llm-review-grid">
      ${items
        .map((item) => {
          const payload = item.structured_payload || {};
          const evidence = (item.evidence || []).slice(0, 2);
          const details = llmReviewDetails(item.agent_name, payload);
          return `
            <article class="llm-review-card">
              <div class="llm-review-top">
                <span>${escapeHtml(llmAgentLabel(item.agent_name))}</span>
                <em class="${toneClass(item.direction)}">${escapeHtml(shortDirectionLabel(item.direction))}</em>
              </div>
              <strong>${escapeHtml(normalizeNarrativeText(item.summary || ""))}</strong>
              ${details}
              ${
                evidence.length
                  ? `<div class="driver-list">${evidence
                      .map((line) => `<div class="driver-item">${escapeHtml(normalizeNarrativeText(line))}</div>`)
                      .join("")}</div>`
                  : ""
              }
              ${payload.recommendation ? `<small>${escapeHtml(normalizeNarrativeText(payload.recommendation))}</small>` : ""}
            </article>`;
        })
        .join("")}
    </div>`;
}

function renderPredictionEvidenceChain(prediction) {
  const raw = prediction?.raw_context || {};
  const refinedSources = raw.refined_news_sources || [];
  const eventSources = raw.event_news_sources || [];
  const hasOilchemDaily = refinedSources.includes("oilchem_shandong_spot_daily_report");
  const predictionCutoff = raw.prediction_news_cutoff || raw.refined_news_cutoff || raw.event_news_cutoff;
  const refinedCutoff = predictionCutoff
    ? `数据截止 ${formatDateTime(predictionCutoff)}`
    : "按预测日07:00截断";
  const refinedSourceText = hasOilchemDaily
    ? "已纳入隆众山东日评"
    : refinedSources.map(displaySourceLabel).join("、") || "暂无日评全文";
  const eventSourceText = eventSources.map(displaySourceLabel).join("、") || "暂无事件输入";
  const pointMapping = raw.point_mapping || {};
  const pointAdjustmentTotal = Object.values(raw.point_adjustments || {}).reduce((sum, value) => sum + Number(value || 0), 0);
  const predictedDelta = Number(raw.predicted_delta || 0);
  const mappedDelta = predictedDelta - pointAdjustmentTotal;
  const pointValue = Number(prediction?.point_value ?? raw.current_price + predictedDelta);
  const currentPrice = Number(raw.current_price || 0);
  const rangeHalfWidth = Number(raw.risk_range_half_width || raw.core_range_half_width || 0);
  const pointMappingIsDistribution = pointMapping.method === "historical_bucket_distribution_mapping";
  const rangeBasis = raw.range_basis || {};
  const refinedLabel = raw.llm_extracted_labels?.refined_news || raw.trade_sentiment || {};
  const eventLabel = raw.llm_extracted_labels?.event_risk || {};
  const labelDeterminism = refinedLabel._cache_key || eventLabel._cache_key ? "同批材料复用标签" : "固定规则兜底";
  const tradeLabelText =
    {
      bullish_active: "成交偏强",
      neutral_flat: "成交平稳",
      bearish_selling: "成交转弱",
      active: "成交偏强",
      flat: "成交平稳",
      weak: "成交转弱",
    }[refinedLabel.deal_activity || refinedLabel.label] ||
    refinedLabel.deal_activity ||
    refinedLabel.label ||
    "成交平稳";
  const eventLabelText =
    {
      none: "无高风险",
      low: "低风险",
      medium: "中风险",
      high: "高风险",
      extreme: "极高风险",
    }[eventLabel.severity] ||
    eventLabel.severity ||
    "无高风险";
  const rows = [
    {
      label: "价格锚点",
      value: `山东92# ${formatNumber(raw.current_price)} 元/吨`,
      meta: `布伦特 ${formatNumber(state.marketSnapshot?.latest_prices?.brent_active_settlement)} / ${marketReasonLabel(raw.market_data_reason)}`,
    },
    {
      label: "原油输入",
      value: raw.brent_forecast_basis?.daily_change_text || raw.brent_forecast_basis?.source || "Brent日报与结算价",
      meta: raw.brent_forecast_basis?.anchor_close == null ? "按当前可用口径" : `前日结算 ${formatNumber(raw.brent_forecast_basis.anchor_close)}`,
    },
    {
      label: "成品油资讯",
      value: `${formatNumberTrim(raw.refined_news_count || 0, 0)} 条 / 全文 ${formatNumberTrim(raw.refined_news_fulltext_count || 0, 0)} 条`,
      meta: `${refinedCutoff}；${refinedSourceText}`,
    },
    {
      label: "事件快讯",
      value: `${formatNumberTrim(raw.event_news_count || 0, 0)} 条`,
      meta: `${refinedCutoff}；07:00后只进入盘中预警，不进入早报预测；${eventSourceText}`,
    },
    {
      label: "点位映射",
      value:
        pointMappingIsDistribution
          ? `${formatNumber(currentPrice)} ${predictedDelta >= 0 ? "+" : "-"} ${formatNumber(Math.abs(predictedDelta))} = ${formatNumber(pointValue)}`
          : pointMapping.method || "未启用分桶映射",
      meta: pointMappingIsDistribution
        ? `状态桶 ${pointMapping.bucket || "-"}；分桶中位数 ${formatNumber(mappedDelta)}；强信号修正 ${formatNumber(pointAdjustmentTotal)}；样本 ${formatNumberTrim(pointMapping.sample_size || 0, 0)} 条`
        : `综合分 ${formatNumber(raw.score_value)}；修正 ${formatNumber(pointAdjustmentTotal)}`,
    },
    {
      label: "区间口径",
      value: rangeBasis.risk_label || "经营风险扩展区间",
      meta: rangeBasis.historical_error_available
        ? `半宽 ${formatNumber(rangeHalfWidth)} 元/吨，由历史误差、数据质量、因子分歧和事件风险共同决定`
        : rangeBasis.reason || "样本不足时不包装成历史误差承诺",
    },
    {
      label: "政策窗口",
      value: raw.days_to_next_window == null ? "未识别" : `${formatNumberTrim(raw.days_to_next_window, 0)} 天`,
      meta: raw.latest_policy_notice?.title || "仅使用已发布政策和可获取调价窗口",
    },
  ];
  rows.splice(3, 0, {
    label: "标签口径",
    value: `交易 ${tradeLabelText} / 事件 ${eventLabelText}`,
    meta: `${labelDeterminism}，标签只转成固定分值，不直接改价格点位`,
  });
  return `
    <div class="evidence-chain">
      ${rows
        .map(
          (item) => `
            <article class="evidence-chain-card">
              <span>${escapeHtml(item.label)}</span>
              <strong>${escapeHtml(normalizeNarrativeText(item.value || "-"))}</strong>
              <small>${escapeHtml(normalizeNarrativeText(item.meta || ""))}</small>
            </article>`
        )
        .join("")}
    </div>`;
}

function renderReliabilityBreakdown(prediction) {
  const components = prediction?.raw_context?.confidence_components || {};
  const rows = [
    ["信号强度", "signal_strength"],
    ["因子一致", "factor_alignment"],
    ["历史校准", "calibration_quality"],
    ["数据质量", "data_quality"],
    ["事件稳定", "event_stability"],
  ];
  if (!Object.keys(components).length) return "";
  return `
    <div class="reliability-breakdown">
      <div class="reliability-head">
        <strong>研判可靠度拆解</strong>
        <span>${escapeHtml(components.meaning || "研判可靠度，不等同于价格命中概率")}</span>
      </div>
      <div class="reliability-bars">
        ${rows
          .map(([label, key]) => {
            const value = Math.max(0, Math.min(1, Number(components[key] ?? 0)));
            return `
              <div class="reliability-bar">
                <span>${escapeHtml(label)}</span>
                <div><i style="width:${valueToPercent(value)}"></i></div>
                <strong>${valueToPercent(value)}</strong>
              </div>`;
          })
          .join("")}
      </div>
    </div>`;
}

function agentJudgeRelationLabel(value) {
  const labels = {
    support: "支持",
    counter: "反证",
    neutral: "中性",
  };
  return labels[value] || value || "-";
}

function agentJudgeEvidenceTypeLabel(value) {
  const labels = {
    hard: "硬数据",
    soft: "软信号",
    baseline: "业务基准",
  };
  return labels[value] || value || "-";
}

function renderAgentJudgementReview(prediction) {
  const review = prediction?.raw_context?.agent_judgement;
  if (!review) return "";
  const adjustment = Number(review.adjustment_delta || 0);
  const isFlatReview = review.direction_after_review === "flat";
  const metrics = isFlatReview
    ? [
        ["硬数据上行", review.hard_up],
        ["硬数据下行", review.hard_down],
        ["软信号上行", review.soft_up],
        ["软信号下行", review.soft_down],
        ["数据覆盖", valueToPercent(review.data_coverage)],
      ]
    : [
        ["硬数据支持", review.hard_support],
        ["硬数据反证", review.hard_counter],
        ["软信号支持", review.soft_support],
        ["软信号反证", review.soft_counter],
        ["数据覆盖", valueToPercent(review.data_coverage)],
      ];
  const items = (review.review_items || [])
    .filter((item) => item?.agent_name && item.evidence_type !== "baseline")
    .sort((a, b) => Math.abs(Number(b.contribution || 0)) - Math.abs(Number(a.contribution || 0)))
    .slice(0, 4);
  return `
    <div class="agent-judge-panel">
      <div class="agent-judge-head">
        <div>
          <span>智能体裁判</span>
          <strong>${escapeHtml(review.display_label || "证据通过")}</strong>
        </div>
        <em class="${adjustment === 0 ? "" : toneClass(adjustment > 0 ? "up" : "down")}">
          ${adjustment === 0 ? "未修正点位" : `点位修正 ${adjustment > 0 ? "+" : ""}${formatNumber(adjustment)} 元/吨`}
        </em>
      </div>
      <div class="agent-judge-metrics">
        ${metrics.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${typeof value === "string" ? escapeHtml(value) : formatNumber(value)}</strong></div>`).join("")}
      </div>
      <div class="agent-judge-reasons">
        ${(review.reasons || []).map((item) => `<span>${escapeHtml(normalizeNarrativeText(item))}</span>`).join("")}
      </div>
      ${
        items.length
          ? `<div class="agent-judge-items">
              ${items
                .map((item) => {
                  const name = FACTOR_LABELS[item.agent_name] || item.agent_name;
                  return `
                    <article>
                      <div>
                        <strong>${escapeHtml(name)}</strong>
                        <span>${escapeHtml(agentJudgeEvidenceTypeLabel(item.evidence_type))} / ${escapeHtml(agentJudgeRelationLabel(item.relation))}</span>
                      </div>
                      <em class="${toneClass(item.direction)}">${formatNumber(item.contribution)}</em>
                    </article>`;
                })
                .join("")}
            </div>`
          : ""
      }
    </div>`;
}

function renderSpotSignalLedger(claims) {
  const claim = (claims || []).find((item) => item?.agent_name === "shandong_spot_jump_agent");
  const signals = claim?.structured_payload?.optional_spot_signals || {};
  const labels = {
    low_price_resource: "低价资源",
    sealed_or_reluctant_sale: "封单惜售",
    trader_grab_or_restock: "抢货补库",
    trader_dump_or_discount: "抛货让利",
    shipment_strong: "出货偏强",
    shipment_weak: "出货偏弱",
  };
  const entries = Object.entries(labels).map(([key, label]) => {
    const signal = signals[key] || {};
    const hit = signal.status === "hit";
    const score = Number(signal.score_if_hit || 0);
    const words = (signal.matched_words || []).join("、");
    return `
      <div class="spot-signal ${hit ? "is-hit" : "is-missing"}">
        <div>
          <span>${escapeHtml(label)}</span>
          <strong>${hit ? escapeHtml(words || "已命中") : "未出现"}</strong>
        </div>
        <em>${hit ? `${score > 0 ? "+" : ""}${formatNumber(score)}` : "不打分"}</em>
      </div>`;
  });
  return `
    <div class="spot-signal-ledger">
      <div class="spot-signal-head">
        <strong>山东现货跳变信号</strong>
        <span>低频信号：有则强修正，无则不打分</span>
      </div>
      ${entries.join("")}
    </div>`;
}

function renderRuleAgentConclusions(claims, limit = 8) {
  const items = (claims || [])
    .filter((item) => item?.agent_name && !String(item.agent_name).startsWith("llm_"))
    .slice(0, limit);
  if (!items.length) return '<div class="muted-text">暂无智能体结论</div>';

  return `
    <div class="rule-agent-grid">
      ${items
        .map((item) => {
          const name = FACTOR_LABELS[item.agent_name] || item.agent_name || "规则智能体";
          const signals = item.numeric_signals || {};
          const payload = item.structured_payload || {};
          const dataQuality = payload.scorecard?.data_quality || payload.data_quality || {};
          const contribution = signals.weighted_score ?? signals.standalone_score ?? signals.score;
          const evidence = (item.evidence || []).slice(0, 2);
          const excluded = Number(signals.excluded_from_model_score || 0) === 1;
          const available = Number(dataQuality.available_count ?? 0);
          const missing = Number(dataQuality.missing_count ?? 0);
          const qualityText =
            available + missing > 0
              ? `数据 ${available}/${available + missing}`
              : "数据已核验";
          const missingFieldItems = (dataQuality.missing_fields || []).map(fieldDisplayLabel);
          const missingFields = missingFieldItems.slice(0, 3).join("、");
          return `
            <article class="rule-agent-card">
              <div class="rule-agent-top">
                <span>${escapeHtml(name)}</span>
                <em class="${toneClass(item.direction)}">${escapeHtml(shortDirectionLabel(item.direction))}</em>
              </div>
              <strong>${escapeHtml(normalizeNarrativeText(item.summary || "暂无结论"))}</strong>
              <div class="rule-agent-meta">
                <span>${excluded ? "独立对照" : "贡献"} ${formatNumber(contribution)}</span>
                <span>可靠度 ${confidenceText(item.confidence_label, item.confidence_score)}</span>
                <span class="${missing ? "is-warning" : ""}">${escapeHtml(qualityText)}</span>
              </div>
              ${
                missingFields
                  ? `<div class="rule-agent-quality">缺失按0分：${escapeHtml(missingFields)}${missingFieldItems.length > 3 ? "等" : ""}</div>`
                  : ""
              }
              ${
                evidence.length
                  ? `<div class="rule-agent-evidence">
                      ${evidence.map((line) => `<small>${escapeHtml(normalizeNarrativeText(line))}</small>`).join("")}
                    </div>`
                  : ""
              }
            </article>`;
        })
        .join("")}
    </div>`;
}

function llmReviewDetails(agentName, payload) {
  const fieldsByAgent = {
    llm_event_interpreter_agent: [
      ["事件类型", "event_type"],
      ["风险等级", "risk_level"],
      ["传导链", "transmission_chain"],
      ["复核事实", "facts_to_verify"],
    ],
    llm_consistency_reviewer_agent: [
      ["概率冲突", "probability_conflict"],
      ["最高概率", "highest_probability_direction"],
      ["校准底座", "calibration_summary"],
      ["展示口径", "suggested_display_tone"],
    ],
    llm_manual_review_agent: [
      ["复核等级", "review_level"],
      ["复核对象", "review_owner"],
      ["复核问题", "review_questions"],
      ["通过动作", "pass_action"],
      ["不通过动作", "fail_action"],
    ],
  };
  const rows = (fieldsByAgent[agentName] || [])
    .map(([label, key]) => {
      const value = formatReviewValue(payload?.[key]);
      return value ? `<div class="llm-review-detail"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>` : "";
    })
    .filter(Boolean)
    .join("");
  return rows ? `<div class="llm-review-details">${rows}</div>` : "";
}

function formatReviewValue(value) {
  if (value == null || value === "") return "";
  if (Array.isArray(value)) return value.map((item) => normalizeNarrativeText(item)).filter(Boolean).join("；");
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}:${item}`).join("；");
  return normalizeNarrativeText(String(value));
}

function renderPredictedDeltaLine(prediction) {
  const raw = prediction?.raw_context || {};
  const currentPrice = raw.current_price;
  const pointValue = prediction?.point_value;
  const deltaValue = prediction?.predicted_delta ?? raw.predicted_delta;
  if (deltaValue == null || Number.isNaN(Number(deltaValue))) {
    return "预测涨跌 -";
  }
  const delta = Number(deltaValue);
  const sign = delta > 0 ? "+" : delta < 0 ? "-" : "±";
  const absDelta = Math.abs(delta);
  if (currentPrice != null && pointValue != null) {
    return `预测涨跌 ${sign}${formatNumber(absDelta)} 元/吨（${formatNumber(currentPrice)} → ${formatNumber(pointValue)}）`;
  }
  return `预测涨跌 ${sign}${formatNumber(absDelta)} 元/吨`;
}
function renderRangeLine(prediction, label = "经营参考区间") {
  const core = `${label} ${formatNumber(prediction?.range_lower)} ~ ${formatNumber(prediction?.range_upper)} 元/吨`;
  const riskLower = prediction?.raw_context?.historical_error_lower ?? prediction?.raw_context?.risk_range_lower;
  const riskUpper = prediction?.raw_context?.historical_error_upper ?? prediction?.raw_context?.risk_range_upper;
  const coreHalf = Number(prediction?.raw_context?.core_range_half_width || 0);
  const riskHalf = Number(prediction?.raw_context?.historical_error_half_width || prediction?.raw_context?.risk_range_half_width || 0);
  const riskLabel = prediction?.raw_context?.range_basis?.risk_label || "经营风险扩展区间";
  if (riskLower == null || riskUpper == null || riskHalf <= coreHalf + 0.01) return core;
  return `${core} / ${riskLabel} ${formatNumber(riskLower)} ~ ${formatNumber(riskUpper)}`;
}

function renderCompactSpreadRange(prediction) {
  const riskLower = prediction?.raw_context?.historical_error_lower ?? prediction?.raw_context?.risk_range_lower;
  const riskUpper = prediction?.raw_context?.historical_error_upper ?? prediction?.raw_context?.risk_range_upper;
  const riskLabel = prediction?.raw_context?.range_basis?.risk_label || "风险区间";
  return `
    <span>${formatNumber(prediction?.range_lower)} ~ ${formatNumber(prediction?.range_upper)}</span>
    ${
      riskLower != null && riskUpper != null
        ? `<span>${escapeHtml(riskLabel)} ${formatNumber(riskLower)} ~ ${formatNumber(riskUpper)}</span>`
        : ""
    }`;
}

function buildDecisionSummary(prediction) {
  const delta = Number(prediction?.raw_context?.predicted_delta || 0);
  const daysToWindow = prediction?.raw_context?.days_to_next_window;
  const business = prediction?.raw_context?.business_direction || {};
  const eventGate = prediction?.raw_context?.event_gate || {};
  const strongMove = Boolean(business.allow_strong_action);
  const nearWindow = daysToWindow != null && Number(daysToWindow) <= 2;
  const grade = business.operating_grade || "-";

  if (eventGate.level === "high" || eventGate.level === "extreme") {
    return [
      ["今日动作", "暂停强单边动作，研究员人工确认"],
      ["触发条件", `${eventGate.label || "高"}风险事件；${eventGate.action || "自动结论降级"}`],
      ["风险止损", "事件证伪、Brent回归区间、山东成交同步验证后再恢复"],
    ];
  }

  if (prediction?.direction_label === "up") {
    return [
      ["今日动作", strongMove ? "逢低补库 / 缩短报价有效期" : "小批滚动补库，不追高"],
      ["触发条件", `较现货预计抬升 ${formatNumber(delta)} 元/吨，经营等级 ${grade}${nearWindow ? "，调价窗口临近" : ""}`],
      ["风险止损", "Brent回落或区域价差收窄时暂停追涨"],
    ];
  }

  if (prediction?.direction_label === "down") {
    return [
      ["今日动作", strongMove ? "控采去库 / 弱势区域加快成交" : "以销定采，不扩大让利"],
      ["触发条件", `较现货预计下移 ${formatNumber(Math.abs(delta))} 元/吨，经营等级 ${grade}${nearWindow ? "，跨窗口库存从严" : ""}`],
      ["风险止损", "政策上调或炼厂挺价时停止低价放量"],
    ];
  }

  return [
    ["今日动作", "滚动采购 / 报价跟随区域价差"],
    ["触发条件", nearWindow ? "调价窗口临近，避免跨窗口重仓" : "方向分歧，等待价格二次确认"],
    ["风险止损", "突发事件或Brent单边突破时人工复核"],
  ];
}

function renderResearch() {
  if (!state.dashboard) {
    dom.outrightPanel.innerHTML = emptyState("研究结论加载中");
    dom.spreadHeatmap.innerHTML = emptyState("区域价差加载中");
    dom.spreadGrid.innerHTML = emptyState("区域价差加载中");
    return;
  }

  renderHorizonButtons();

  const outright = selectedOutrightPrediction();
  const regional = selectedRegionalPredictions();
  if (!outright) {
    dom.outrightPanel.innerHTML = emptyState("暂无研究结论");
    return;
  }

  const probabilities = outright.raw_context?.probabilities || {};
  const business = businessDirectionInfo(outright);
  const eventGate = outright.raw_context?.event_gate || {};
  const decisionItems = buildDecisionSummary(outright);
  const modeText = outright.degrade_flag
    ? `结论基于降级数据：${marketReasonLabel(outright.degrade_reason)}`
    : `结论日期 ${formatDate(state.dashboard.as_of_date)}`;

  setChip(dom.researchMeta, modeText);
  setChip(dom.narrativeStatus, dom.narrativeToggle.checked ? "模型解释开启" : "规则解释");
  dom.regionalHorizonLabel.textContent = `${state.selectedHorizon} / 当前价差`;

  dom.outrightPanel.innerHTML = `
    <section class="research-hero">
      <div class="hero-top">
        <div class="hero-point-block">
          <div class="hero-kicker">${escapeHtml(outright.horizon)} / ${escapeHtml(HORIZON_LABELS[outright.horizon] || outright.horizon)}</div>
          <div class="hero-direction ${toneClass(business.tone)}">${escapeHtml(business.label)}</div>
          <div class="hero-point ${toneClass(business.tone)}">${formatNumber(outright.point_value)}</div>
          <div class="hero-delta ${toneClass(outright.direction_label)}">${escapeHtml(renderPredictedDeltaLine(outright))}</div>
          <div class="hero-range">${escapeHtml(renderRangeLine(outright))}</div>
        </div>

        <div class="hero-stats">
          <div class="stat-row"><span>当前山东 92#</span><strong>${formatNumber(outright.raw_context?.current_price)}</strong></div>
          <div class="stat-row"><span>综合分</span><strong>${formatNumber(outright.score_value)}</strong></div>
          <div class="stat-row"><span>经营可用性</span><strong>${escapeHtml(business.grade)} / ${escapeHtml(business.usage || confidenceText(outright.confidence_label, outright.confidence_score))}</strong></div>
          <div class="stat-row"><span>方向概率</span><strong>涨 ${valueToPercent(probabilities.up)} / 平 ${valueToPercent(probabilities.flat)} / 跌 ${valueToPercent(probabilities.down)}</strong></div>
          <div class="stat-row"><span>事件风控</span><strong>${escapeHtml(eventGate.label || "低")} / ${escapeHtml(eventGate.action || "模型正常展示")}</strong></div>
          <div class="stat-row"><span>布伦特</span><strong>${formatNumber(state.marketSnapshot?.latest_prices?.brent_active_settlement)}</strong></div>
        </div>
      </div>

      ${renderModelComparison(outright)}

      ${renderRegionalPriceForecastStrip(regional)}

      <article class="info-card insight-card evidence-panel">
        <h3>预测证据链</h3>
        ${renderPredictionEvidenceChain(outright)}
        ${renderReliabilityBreakdown(outright)}
        ${renderAgentJudgementReview(outright)}
        ${renderSpotSignalLedger(outright.agent_claims)}
      </article>

      <div class="decision-strip">
        ${decisionItems
          .map(
            ([label, value]) => `
              <article class="decision-card">
                <span>${escapeHtml(label)}</span>
                <strong>${escapeHtml(value)}</strong>
              </article>`
          )
          .join("")}
      </div>

      <div class="insight-stack">
        <article class="info-card insight-card">
          <h3>研判摘要</h3>
          <p class="body-text">${renderMultilineText(outright.explanation)}</p>
        </article>

        <article class="info-card insight-card">
          <h3>规则智能体结论</h3>
          ${renderRuleAgentConclusions(outright.agent_claims)}
        </article>

        <article class="info-card insight-card business-scorecard-panel">
          <h3>业务打分模型明细</h3>
          ${renderBusinessScorecardPrediction(outright.raw_context?.business_scorecard_prediction)}
          ${renderBusinessScorecard(outright.raw_context?.business_scorecard)}
        </article>

        ${
          renderLlmAgentReviews(outright.agent_claims)
            ? `<article class="info-card insight-card">
                <h3>智能体评审</h3>
                ${renderLlmAgentReviews(outright.agent_claims)}
              </article>`
            : ""
        }

        ${renderPredictionNarrativeSplit(outright)}
      </div>

      <article class="info-card factor-panel">
        <h3>因子贡献</h3>
        <div class="factor-list">${renderFactorList(outright.factor_breakdown)}</div>
      </article>
    </section>`;

  if (state.dashboard.metadata?.regional_spread_error && !regional.length) {
    const message = `区域价差加载失败：${state.dashboard.metadata.regional_spread_error}`;
    dom.spreadHeatmap.innerHTML = emptyState(message);
    dom.spreadGrid.innerHTML = emptyState(message);
    return;
  }
  renderSpreadHeatmap(regional);
  renderSpreadCards(regional);
}

function renderSpreadHeatmap(predictions) {
  if (!predictions?.length) {
    dom.spreadHeatmap.innerHTML = emptyState("暂无区域价差");
    if (dom.freightSettingsPanel) dom.freightSettingsPanel.innerHTML = emptyState("暂无区域运费");
    return;
  }

  const maxAbs = Math.max(...predictions.map((item) => Math.abs(Number(regionalActualSpread(item) || 0))), 1);
  dom.spreadHeatmap.innerHTML = predictions.map((item) => {
    const current = Number(regionalActualSpread(item) || 0);
    const width = Math.max((Math.abs(current) / maxAbs) * 50, 2);
    const left = current >= 0 ? 50 : 50 - width;
    const color = current >= 0 ? "var(--up)" : "var(--down)";
    const region = item.raw_context?.counter_region_name || item.region_code;
    return `
      <div class="heatmap-row">
        <div class="heatmap-label">${escapeHtml(region)}</div>
        <div class="heatmap-track">
          <div class="heatmap-axis"></div>
          <div class="heatmap-bar" style="left:${left}%; width:${width}%; background:${color};"></div>
        </div>
        <div class="heatmap-value">${formatNumber(current)}</div>
      </div>`;
  }).join("");

  renderFreightSettings(predictions);
}

function renderFreightSettings(predictions = []) {
  if (!dom.freightSettingsPanel) return;
  const predictionByRegion = Object.fromEntries(
    (predictions || []).map((item) => [item.raw_context?.counter_region_code || item.region_code, item.raw_context || {}])
  );
  const settings = state.freightSettings || [];

  if (!settings.length) {
    dom.freightSettingsPanel.innerHTML = `
      <div class="freight-load-state">
        <strong>\u533a\u57df\u8fd0\u8d39\u8bfb\u53d6\u4e2d</strong>
        <button type="button" data-freight-reload>\u91cd\u65b0\u8bfb\u53d6\u8fd0\u8d39\u914d\u7f6e</button>
      </div>`;
    if (!state.freightLoading) loadFreightSettings();
    return;
  }

  dom.freightSettingsPanel.innerHTML = settings.map((setting) => {
    const context = predictionByRegion[setting.region_code] || {};
    const region = setting.region_name || context.counter_region_name || setting.region_code;
    const freightEstimate = setting.freight_value ?? context.freight_estimate;
    const components = setting.components || [];
    const componentHtml = components.length
      ? components.map((component) => `
          <label class="freight-component-form" data-freight-component="${escapeHtml(component.component_key)}">
            <span>${escapeHtml(component.route_name || component.short_name || component.component_key)}</span>
            <input type="number" min="0" max="2000" step="1" value="${escapeHtml(component.freight_value ?? "")}" />
          </label>`).join("")
      : `<div class="freight-component-missing">\u672a\u8bfb\u5230\u8be5\u533a\u57df\u7684\u8fd0\u8d39\u660e\u7ec6\u914d\u7f6e\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u914d\u7f6e\u3002</div>`;
    return `
      <article class="freight-region-card ${components.length ? "has-components" : "is-missing-components"}">
        <div class="freight-region-head">
          <div>
            <span>${escapeHtml(region)}\u8fd0\u8d39\u5f55\u5165</span>
            <small>\u53ea\u5f55\u5165\u660e\u7ec6\u7ebf\u8def\uff0c\u533a\u57df\u8fd0\u8d39\u81ea\u52a8\u53d6\u660e\u7ec6\u5e73\u5747</small>
          </div>
          <strong>${formatNumber(freightEstimate)} <em>\u5143/\u5428</em></strong>
        </div>
        <div class="freight-component-grid">${componentHtml}</div>
      </article>`;
  }).join("");
}

function renderSpreadCards(predictions) {
  if (!predictions?.length) {
    dom.spreadGrid.innerHTML = emptyState("\u6682\u65e0\u533a\u57df\u4ef7\u5dee\u9884\u6d4b");
    return;
  }

  dom.spreadGrid.innerHTML = predictions.map((item, index) => {
    const context = item.raw_context || {};
    const region = context.counter_region_name || item.region_code;
    const currentRegionPrice = context.current_counter_region_price;
    const currentSpread = regionalActualSpread(item);
    const currentNetback = context.netback_spread;
    const predictedRegionPrice = regionalPredictedPrice(item);
    const predictedSpread = regionalPredictedSpread(item);
    const freight = context.freight_estimate;
    const predictedNetback = predictedSpread == null || freight == null ? null : Number(predictedSpread) - Number(freight);
    const currentSpreadTone = Number(currentSpread || 0) >= 0 ? "up" : "down";
    const predictedSpreadTone = Number(predictedSpread || 0) >= 0 ? "up" : "down";
    const currentNetbackTone = Number(currentNetback || 0) >= 0 ? "up" : "down";
    const predictedNetbackTone = Number(predictedNetback || 0) >= 0 ? "up" : "down";
    return `
      <article class="spread-card spread-card--regional">
        <div class="spread-card-accent"></div>
        <div class="spread-top">
          <div>
            <div class="spread-region">${escapeHtml(region)} - \u5c71\u4e1c</div>
            <div class="spread-subtitle">\u533a\u57df\u4ef7 - \u5c71\u4e1c\u4ef7</div>
          </div>
          <div class="spread-head-actions">
            <span class="spread-freight-pill">\u8fd0\u8d39 ${formatNumber(freight)} \u5143/\u5428</span>
            <button class="spread-detail-button" type="button" data-spread-detail-index="${index}">\u8be6\u60c5</button>
          </div>
        </div>
        <div class="spread-pair-grid">
          <div class="spread-pair-label">\u5f53\u524d\u533a\u57df\u4ef7</div>
          <div class="spread-pair-label">\u5f53\u524d\u4ef7\u5dee</div>
          <div class="spread-pair-value">${formatNumber(currentRegionPrice)}</div>
          <div class="spread-pair-value ${toneClass(currentSpreadTone)}">${formatNumber(currentSpread)}</div>
          <div class="spread-pair-label">\u9884\u6d4b\u533a\u57df\u4ef7</div>
          <div class="spread-pair-label">\u9884\u6d4b\u4ef7\u5dee</div>
          <div class="spread-pair-value">${formatNumber(predictedRegionPrice)}</div>
          <div class="spread-pair-value ${toneClass(predictedSpreadTone)}">${formatNumber(predictedSpread)}</div>
          <div class="spread-pair-label">\u5f53\u524d\u51c0\u56de\u6b3e</div>
          <div class="spread-pair-label">\u9884\u6d4b\u51c0\u56de\u6b3e</div>
          <div class="spread-pair-value ${toneClass(currentNetbackTone)}">${formatNumber(currentNetback)}</div>
          <div class="spread-pair-value ${toneClass(predictedNetbackTone)}">${formatNumber(predictedNetback)}</div>
        </div>
      </article>`;
  }).join("");
}

function showSpreadDetail(index) {
  const predictions = selectedRegionalPredictions();
  const item = predictions?.[Number(index)];
  if (!item || !dom.spreadDetailDialog) return;
  const region = item.raw_context?.counter_region_name || item.region_code;
  const tradeAction = item.raw_context?.trade_action || {};
  const variants = regionalPredictionVariants(item);
  const compositeVariant = variants.find((variant) => variant.prediction_type === "regional_composite") || variants[0] || {};
  const baselineVariant = variants.find((variant) => variant.prediction_type === "regional_baseline") || variants[1] || null;
  const predictedRegionPrice = regionalVariantPrice(compositeVariant);
  const predictedSpread = regionalVariantSpread(compositeVariant);
  const actualSpread = regionalActualSpread(item);
  if (dom.spreadDetailTitle) dom.spreadDetailTitle.textContent = `山东 - ${region}价差详情`;
  if (dom.spreadDetailSubtitle) {
    dom.spreadDetailSubtitle.textContent = `${item.horizon} / ${directionLabel(item.direction_label, true)} / ${confidenceText(item.confidence_label, item.confidence_score)}`;
  }
  if (dom.spreadDetailContent) {
    dom.spreadDetailContent.innerHTML = `
      <section class="spread-detail-hero">
        <div>
          <span>综合预测区域单价</span>
          <strong class="${toneClass(item.direction_label)}">${formatNumber(predictedRegionPrice)}</strong>
          <small>区域-山东价差 ${formatNumber(predictedSpread)}</small>
        </div>
        <div>
          <span>基准预测区域单价</span>
          <strong class="${toneClass(baselineVariant?.direction_label || "flat")}">${formatNumber(regionalVariantPrice(baselineVariant))}</strong>
          <small>区域-山东价差 ${formatNumber(regionalVariantSpread(baselineVariant))}</small>
        </div>
        <div>
          <span>当前真实价差</span>
          <strong>${formatNumber(actualSpread)}</strong>
          <small>当前区域价 ${formatNumber(item.raw_context?.current_counter_region_price)}</small>
        </div>
        <div>
          <span>当前净回款</span>
          <strong>${formatNumber(item.raw_context?.netback_spread)}</strong>
          <small>运费 ${formatNumber(item.raw_context?.freight_estimate)} 元/吨</small>
        </div>
      </section>

      <section class="spread-detail-grid">
        <article class="info-card">
          <h3>核心驱动</h3>
          <div class="driver-list">${renderDriverList(item.driver_summary)}</div>
        </article>
        <article class="info-card">
          <h3>经营建议</h3>
          <div class="advice-list">${renderAdviceList(item.operating_advice)}</div>
        </article>
        <article class="info-card">
          <h3>价差口径</h3>
          <div class="factor-list">
            <div class="factor-item"><div class="factor-label">价差公式</div><div class="factor-value">${escapeHtml(item.raw_context?.actual_spread_formula || "真实展示价差=当前目标区域92#价-当前山东92#价")}</div></div>
            <div class="factor-item"><div class="factor-label">净回款</div><div class="factor-value">价差 - 运费 ${formatNumber(item.raw_context?.freight_estimate)}</div></div>
            <div class="factor-item"><div class="factor-label">综合预测</div><div class="factor-value">${escapeHtml(compositeVariant?.basis || "状态表同状态变化中位数+区域规则修正")}</div></div>
            <div class="factor-item"><div class="factor-label">基准预测</div><div class="factor-value">${escapeHtml(baselineVariant?.basis || "区域规则基准未返回")}</div></div>
            <div class="factor-item"><div class="factor-label">区间口径</div><div class="factor-value">${escapeHtml(item.raw_context?.range_basis?.risk_label || "经营风险扩展区间")}</div></div>
            <div class="factor-item"><div class="factor-label">校准状态</div><div class="factor-value">${escapeHtml(item.raw_context?.calibration?.status || "-")} / 样本 ${formatNumberTrim(item.raw_context?.calibration?.sample_size ?? 0, 0)}</div></div>
          </div>
        </article>
        <article class="info-card">
          <h3>规则智能体结论</h3>
          ${renderRuleAgentConclusions(item.agent_claims)}
        </article>
        <article class="info-card">
          <h3>因子贡献</h3>
          <div class="factor-list">${renderFactorList(item.factor_breakdown, 8)}</div>
        </article>
      </section>`;
  }
  if (typeof dom.spreadDetailDialog.showModal === "function") {
    dom.spreadDetailDialog.showModal();
  } else {
    dom.spreadDetailDialog.setAttribute("open", "");
  }
}

function closeSpreadDetail() {
  if (!dom.spreadDetailDialog) return;
  if (typeof dom.spreadDetailDialog.close === "function") {
    dom.spreadDetailDialog.close();
  } else {
    dom.spreadDetailDialog.removeAttribute("open");
  }
}

async function saveAllFreightSettings() {
  if (!dom.freightSettingsPanel) return;
  const forms = Array.from(dom.freightSettingsPanel.querySelectorAll(".freight-component-form"));
  if (!forms.length) {
    setChip(dom.researchMeta, "\u6682\u65e0\u53ef\u4fdd\u5b58\u7684\u8fd0\u8d39\u660e\u7ec6", "error");
    return;
  }
  if (!silent) setChip(dom.researchMeta, "\u8fd0\u8d39\u4fdd\u5b58\u4e2d", "loading");
  try {
    for (const form of forms) {
      await saveFreightSetting(form, { silent: true });
    }
    setChip(dom.researchMeta, "\u8fd0\u8d39\u5df2\u4fdd\u5b58\uff0c\u533a\u57df\u8fd0\u8d39\u5df2\u91cd\u7b97");
  } catch (error) {
    console.error(error);
    if (!silent) setChip(dom.researchMeta, `\u8fd0\u8d39\u4fdd\u5b58\u5931\u8d25\uff1a${error.message || error}`, "error");
    throw error;
  }
}

async function saveFreightSetting(form, options = {}) {
  const componentKey = form?.dataset?.freightComponent;
  const input = form?.querySelector("input");
  const button = form?.querySelector("button");
  const silent = Boolean(options.silent);
  const freightValue = Number(input?.value);
  if (!componentKey || !Number.isFinite(freightValue) || freightValue < 0) {
    if (!silent) setChip(dom.researchMeta, "\u8bf7\u8f93\u5165\u6709\u6548\u8fd0\u8d39", "error");
    return;
  }
  if (button) button.disabled = true;
  if (!silent) setChip(dom.researchMeta, "\u8fd0\u8d39\u4fdd\u5b58\u4e2d", "loading");
  try {
    const payload = await fetchJson("/api/v1/regional-freight-components", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ component_key: componentKey, freight_value: freightValue }),
    });
    state.freightSettings = payload.items || [];
    refreshFreightDependentViews();
    if (!silent) setChip(dom.researchMeta, "\u660e\u7ec6\u8fd0\u8d39\u5df2\u4fdd\u5b58\uff0c\u533a\u57df\u8fd0\u8d39\u5df2\u91cd\u7b97");
  } catch (error) {
    console.error(error);
    if (!silent) setChip(dom.researchMeta, `\u8fd0\u8d39\u4fdd\u5b58\u5931\u8d25\uff1a${error.message || error}`, "error");
    throw error;
  } finally {
    if (button) button.disabled = false;
  }
}

function parseBriefingSections(markdown) {
  const sections = {};
  let currentTitle = "root";
  sections[currentTitle] = [];

  String(markdown || "")
    .split(/\r?\n/)
    .forEach((rawLine) => {
      const line = rawLine.trim();
      if (!line) return;
      if (line.startsWith("## ")) {
        currentTitle = line.slice(3).trim();
        sections[currentTitle] = [];
        return;
      }
      if (line.startsWith("# ")) return;
      if (line.startsWith("- ")) {
        sections[currentTitle].push(line.slice(2).trim());
        return;
      }
      sections[currentTitle].push(line);
    });

  return sections;
}

function fallbackBriefingSnapshotPrices(sections) {
  const items = sections["价格快照"] || [];
  const output = {};
  items.forEach((line) => {
    const [label, rawValue] = line.split(":");
    const value = Number(rawValue?.trim() || "");
    if (Number.isNaN(value)) return;
    if (label.includes("布伦特") || label.includes("Brent")) output.brent_active_settlement = value;
    if (label.includes("山东92#")) output.sd_gas92_market = value;
    if (label.includes("全国92#")) output.cn_gas92_market = value;
    if (label.includes("华东92#")) output.east_china_gas92_market = value;
  });
  return output;
}

function buildBriefingPolicyHighlights(payload, sections) {
  const existing = payload.metadata?.policy_highlights || [];
  if (existing.length) return latestPolicyHighlights(existing);
  const parsed = (sections["政策与风险"] || [])
    .filter((item) => item.includes("国家发展和改革委员会") || item.includes("国内成品油价格调整"))
    .map((item) => {
      const [title, time] = item.split("|");
      return { title: title?.trim(), time: time?.trim() || "-" };
    });
  return latestPolicyHighlights(parsed);
}

function latestPolicyHighlights(items) {
  const latest = {};
  items.forEach((item) => {
    const text = `${item.title || ""} ${item.impact || ""} ${item.action || ""}`;
    const direction = text.includes("上调") ? "up" : text.includes("下调") ? "down" : "";
    if (!direction) return;
    const time = String(item.time || "").trim();
    if (!latest[direction] || time > String(latest[direction].time || "")) {
      latest[direction] = item;
    }
  });
  return Object.values(latest).sort((a, b) => String(b.time || "").localeCompare(String(a.time || "")));
}

function buildBriefingEventHighlights(payload, sections) {
  const existing = payload.metadata?.event_highlights || [];
  if (existing.length) return existing;
  return (sections["政策与风险"] || [])
    .filter((item) => !(item.includes("国家发展和改革委员会") || item.includes("国内成品油价格调整")))
    .slice(0, 3)
    .map((item) => ({ title: item, time: "-", source: "事件快讯" }));
}

function markdownToHtml(markdown) {
  const lines = String(markdown || "").split(/\r?\n/);
  let html = "";
  let inList = false;

  function closeList() {
    if (inList) {
      html += "</ul>";
      inList = false;
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      closeList();
      continue;
    }

    if (line.startsWith("### ")) {
      closeList();
      html += `<h3>${escapeHtml(line.slice(4))}</h3>`;
      continue;
    }
    if (line.startsWith("## ")) {
      closeList();
      html += `<h2>${escapeHtml(line.slice(3))}</h2>`;
      continue;
    }
    if (line.startsWith("# ")) {
      closeList();
      html += `<h1>${escapeHtml(line.slice(2))}</h1>`;
      continue;
    }
    if (line.startsWith("- ")) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${escapeHtml(line.slice(2))}</li>`;
      continue;
    }

    closeList();
    html += `<p>${escapeHtml(line)}</p>`;
  }
  closeList();
  return html;
}

function renderMorningBriefing() {
  if (!state.latestBriefing) {
    dom.briefingContent.innerHTML = emptyState("暂无晨报");
    applyBriefingCollapseState();
    return;
  }

  const payload = state.latestBriefing;
  const sections = parseBriefingSections(payload.content_markdown);
  const outright = payload.outright_predictions || [];
  const regional = payload.regional_spread_predictions || [];
  const lead = outright.find((item) => item.horizon === "D1") || outright[0] || null;
  const leadBusiness = businessDirectionInfo(lead);
  const snapshot = payload.metadata?.snapshot_prices || fallbackBriefingSnapshotPrices(sections);
  const policyHighlights = buildBriefingPolicyHighlights(payload, sections);
  const eventHighlights = buildBriefingEventHighlights(payload, sections);
  const adviceItems = (lead?.operating_advice || []).slice(0, 3);
  const summaryText = normalizeNarrativeText(lead?.explanation || "暂无晨会摘要");
  const marketModeText =
    lead?.degrade_flag || payload.metadata?.market_data_reason
      ? `数据口径 ${marketReasonLabel(lead?.degrade_reason || payload.metadata?.market_data_reason)}`
      : "数据口径 实时";
  const windowText =
    lead?.raw_context?.days_to_next_window != null ? `距下轮调价窗口 ${formatNumberTrim(lead.raw_context.days_to_next_window, 0)} 天` : "调价窗口待核对";
  const snapshotCards = [
    ["布伦特", snapshot.brent_active_settlement, "美元/桶"],
    ["山东 92#", snapshot.sd_gas92_market ?? lead?.raw_context?.current_price, "元/吨"],
    ["全国 92#", snapshot.cn_gas92_market, "元/吨"],
    ["华东 92#", snapshot.east_china_gas92_market, "元/吨"],
  ].filter(([, value]) => value != null);
  const mixedHighlights = [
    ...policyHighlights.map((item) => ({
      type: "政策",
      title: item.impact || item.title,
      meta: item.time || "-",
      action: item.action || "跟踪调价窗口与限价兑现",
    })),
    ...eventHighlights.map((item) => ({
      type: "事件",
      title: item.impact || item.title,
      meta: `${displaySourceLabel(item.source || "事件快讯")} · ${item.time || "-"}`,
      action: item.action || "跟踪事件对Brent和现货报价的传导",
    })),
  ].slice(0, 6);

  setChip(dom.briefingMeta, `${formatDate(payload.as_of_date)} / ${formatDateTime(payload.generated_at)}`);
  dom.briefingContent.innerHTML = `
    <div class="briefing-sheet">
      <section class="briefing-hero">
        <div class="briefing-hero-main">
          <div class="briefing-kicker">晨会快览 / ${formatDate(payload.as_of_date)}</div>
          <div class="briefing-title-row">
            <div>
              <h3>${escapeHtml(payload.title.replace("|", "/"))}</h3>
              <p class="briefing-summary">${escapeHtml(summaryText)}</p>
            </div>
            <div class="briefing-direction-chip ${toneClass(leadBusiness.tone)}">${escapeHtml(leadBusiness.label)}</div>
          </div>
          <div class="briefing-hero-metrics">
            <div class="briefing-lead-point">${formatNumber(lead?.point_value)}</div>
            <div class="briefing-lead-range">D1 点位 · ${formatNumber(lead?.range_lower)} ~ ${formatNumber(lead?.range_upper)} 元/吨</div>
          </div>
        </div>

        <div class="briefing-hero-side">
          <article class="briefing-side-card">
            <span>多周期主判断</span>
            <strong>${escapeHtml(leadBusiness.label)}</strong>
            <small>${windowText}</small>
          </article>
          <article class="briefing-side-card">
            <span>资讯与事件</span>
            <strong>${formatNumberTrim(payload.metadata?.refined_news_count || 0, 0)} / ${formatNumberTrim(payload.metadata?.event_news_count || 0, 0)}</strong>
            <small>成品油资讯 / 事件快讯</small>
          </article>
          <article class="briefing-side-card">
            <span>政策更新</span>
            <strong>${formatNumberTrim(payload.metadata?.policy_count || 0, 0)}</strong>
            <small>${marketModeText}</small>
          </article>
        </div>
      </section>

      <section class="briefing-snapshot-strip">
        ${snapshotCards
          .map(
            ([label, value, unit]) => `
              <article class="briefing-snapshot-card">
                <span>${escapeHtml(label)}</span>
                <strong>${formatNumber(value)}</strong>
                <small>${escapeHtml(unit)}</small>
              </article>`
          )
          .join("")}
      </section>

      <div class="briefing-grid">
        <section class="briefing-block">
          <div class="briefing-block-head">
            <h4>多周期判断</h4>
            <span>${escapeHtml(leadBusiness.label)}为主</span>
          </div>
          <div class="briefing-horizon-grid">
            ${outright
              .map(
                (item) => `
                  <article class="briefing-horizon-card">
                    <div class="briefing-horizon-top">
                      <span>${escapeHtml(item.horizon)} / ${escapeHtml(HORIZON_LABELS[item.horizon] || item.horizon)}</span>
                      <em class="${toneClass(businessDirectionInfo(item).tone)}">${escapeHtml(businessDirectionInfo(item).label)}</em>
                    </div>
                    <strong>${formatNumber(item.point_value)}</strong>
                    <small>${formatNumber(item.range_lower)} ~ ${formatNumber(item.range_upper)}</small>
                  </article>`
              )
              .join("")}
          </div>
        </section>

        <section class="briefing-block">
          <div class="briefing-block-head">
            <h4>经营建议</h4>
            <span>当日执行</span>
          </div>
          <div class="briefing-list">
            ${
              adviceItems.length
                ? adviceItems
                    .map(
                      (item) => `
                        <article class="briefing-list-card">
                          <div class="briefing-list-title">${escapeHtml(normalizeNarrativeText(item.title || "建议"))}</div>
                          <div class="briefing-list-body">${escapeHtml(normalizeNarrativeText(item.action || ""))}</div>
                          <small>${escapeHtml(normalizeNarrativeText(item.rationale || ""))}</small>
                        </article>`
                    )
                    .join("")
                : '<div class="briefing-list-card muted-text">暂无经营建议</div>'
            }
          </div>
        </section>

        <section class="briefing-block">
          <div class="briefing-block-head">
            <h4>区域价差观察</h4>
            <span>D1 / 当前可视重点</span>
          </div>
          <div class="briefing-spread-grid">
            ${regional
              .slice(0, 4)
              .map(
                (item) => `
                  <article class="briefing-spread-card">
                    <div class="briefing-spread-head">
                      <span>山东 - ${escapeHtml(item.raw_context?.counter_region_name || item.region_code)}</span>
                      <em class="${toneClass(item.direction_label)}">${escapeHtml(shortDirectionLabel(item.direction_label, true))}</em>
                    </div>
                    <div class="regional-variant-list">${renderRegionalVariantRows(item, { compact: true })}</div>
                    <small>真实价差 ${formatNumber(regionalActualSpread(item))}</small>
                  </article>`
              )
              .join("")}
          </div>
        </section>

        <section class="briefing-block">
          <div class="briefing-block-head">
            <h4>政策与风险</h4>
            <span>按晨会优先级</span>
          </div>
          <div class="briefing-list">
            ${
              mixedHighlights.length
                ? mixedHighlights
                    .map(
                      (item) => `
                        <article class="briefing-list-card">
                          <div class="briefing-list-meta">${escapeHtml(item.type)}</div>
                          <div class="briefing-list-body">${escapeHtml(normalizeNarrativeText(item.title || ""))}</div>
                          <small>${escapeHtml(normalizeNarrativeText(item.meta || ""))}</small>
                          <small class="briefing-action-line">${escapeHtml(normalizeNarrativeText(item.action || ""))}</small>
                        </article>`
                    )
                    .join("")
                : '<div class="briefing-list-card muted-text">暂无事件提示</div>'
            }
          </div>
        </section>
      </div>
    </div>`;
}

function renderAlerts() {
  if (!hasPermission("policy.view")) {
    dom.alertList.innerHTML = emptyState("当前账号未开通预警查看权限");
    setChip(dom.alertMeta, "权限受限", "error");
    return;
  }
  const alerts = state.policyFeed?.alerts || [];
  if (!alerts.length) {
    dom.alertList.innerHTML = emptyState("暂无重点预警");
    setChip(dom.alertMeta, "无新增重点");
    return;
  }

  setChip(dom.alertMeta, `${alerts.length} 条重点`);
  dom.alertList.innerHTML = alerts.map((item) => {
    const severityClass = item.severity === "高" ? "severity-high" : "severity-medium";
    const impact = item.expected_impact || "需复核";
    const direction = item.direction || "扰动";
    const region = item.affected_region || "重点区域";
    const product = item.affected_product || "92#汽油";
    const statusMap = { new: "新触发", reviewing: "待确认", tracking: "跟踪中", resolved: "已解除", dismissed: "误报" };
    const status = statusMap[item.status] || item.status || "跟踪中";
    const confidence = item.confidence || "中";
    const action = item.recommended_action || item.action || "人工复核后再调整报价和库存动作";
    const titleHtml = item.url
      ? `<a class="alert-title" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>`
      : `<div class="alert-title">${escapeHtml(item.title)}</div>`;
    return `
      <article class="alert-card">
        <div class="alert-top">
          <span class="severity-pill ${severityClass}">${escapeHtml(item.severity || "中")}优先</span>
          <span class="tag">${escapeHtml(item.event_type || item.category || "预警")}</span>
        </div>
        ${titleHtml}
        <div class="alert-impact">
          <strong>${escapeHtml(direction)}</strong>
          <span>${escapeHtml(impact)}</span>
        </div>
        <div class="alert-scope">
          <span>${escapeHtml(region)}</span>
          <span>${escapeHtml(product)}</span>
          <span>${escapeHtml(status)}</span>
          <span>可靠度 ${escapeHtml(confidence)}</span>
        </div>
        <div class="alert-action">${escapeHtml(action)}</div>
        <div class="alert-controls">
          <button type="button" data-alert-action="tracking" data-alert-id="${escapeHtml(item.alert_id || "")}">跟踪</button>
          <button type="button" data-alert-action="resolved" data-alert-id="${escapeHtml(item.alert_id || "")}">解除</button>
          <button type="button" data-alert-action="dismissed" data-alert-id="${escapeHtml(item.alert_id || "")}">误报</button>
        </div>
        <div class="alert-meta">
          <span>${escapeHtml(displaySourceLabel(item.source))}</span>
          <span>${escapeHtml(item.time || "-")}</span>
          <span>预警分 ${formatNumber(item.alert_score ?? item.importance_score, 1)}</span>
        </div>
      </article>`;
  }).join("");
}

function renderPriceHistory() {
  if (!dom.priceHistoryChart || !dom.priceHistorySeries) return;
  const payload = state.priceHistory;
  if (!payload) {
    dom.priceHistorySeries.innerHTML = "";
    dom.priceHistoryChart.innerHTML = emptyState("价格走势加载中");
    setChip(dom.priceHistoryMeta, "待刷新");
    return;
  }

  setChip(dom.priceHistoryMeta, `${state.priceHistoryDays}天`);
  const available = payload.available_series || [];
  const selectedSeries = (payload.series || []).filter((item) => state.priceHistorySeries.includes(item.key));
  dom.priceHistorySeries.innerHTML = available.map((item) => {
    const active = state.priceHistorySeries.includes(item.key);
    const selectedIndex = selectedSeries.findIndex((series) => series.key === item.key);
    const color = selectedIndex >= 0 ? PRICE_HISTORY_COLORS[selectedIndex % PRICE_HISTORY_COLORS.length] : "";
    return `
      <label class="history-series-chip${active ? " is-active" : ""}">
        <input type="checkbox" value="${escapeHtml(item.key)}"${active ? " checked" : ""} />
        <i class="history-chip-dot" style="${color ? `--series-color:${escapeHtml(color)}` : ""}"></i>
        <span>${escapeHtml(item.label)}</span>
      </label>`;
  }).join("");

  const pointValues = selectedSeries.flatMap((series) =>
    (series.points || []).map((point) => Number(point.value)).filter((value) => Number.isFinite(value))
  );
  if (!selectedSeries.length || !pointValues.length) {
    dom.priceHistoryChart.innerHTML = emptyState("暂无历史价格");
    return;
  }

  const minValue = Math.min(...pointValues);
  const maxValue = Math.max(...pointValues);
  const padding = Math.max((maxValue - minValue) * 0.12, 20);
  const yMin = minValue - padding;
  const yMax = maxValue + padding;
  const isClearviewChart = Boolean(dom.priceHistoryChart.closest("#view-clearview"));
  const measuredChartWidth = Math.round(dom.priceHistoryChart.clientWidth || 0);
  const width = isClearviewChart ? Math.min(Math.max(measuredChartWidth, 520), 1100) : 260;
  const height = isClearviewChart ? 92 : 150;
  const left = 34;
  const right = 8;
  const top = 14;
  const bottom = 24;
  const innerWidth = width - left - right;
  const innerHeight = height - top - bottom;
  const allDates = selectedSeries.flatMap((series) => (series.points || []).map((point) => point.date)).sort();
  const uniqueDates = [...new Set(allDates)];
  const yFor = (value) => top + (1 - (Number(value) - yMin) / Math.max(yMax - yMin, 1)) * innerHeight;
  const xFor = (index, count) => left + (count <= 1 ? 0 : (index / (count - 1)) * innerWidth);
  const tickStep = Math.max(Math.ceil(uniqueDates.length / (isClearviewChart ? 7 : 3)), 1);
  const dateTicks = uniqueDates
    .map((dateValue, index) => ({ dateValue, index }))
    .filter((item, index, array) => item.index % tickStep === 0 || index === array.length - 1)
    .map((item) => {
      const x = xFor(item.index, Math.max(uniqueDates.length, 1));
      return `
        <line x1="${x.toFixed(1)}" y1="${height - bottom}" x2="${x.toFixed(1)}" y2="${height - bottom + 4}" class="history-tick" />
        <text x="${x.toFixed(1)}" y="${height - 5}" text-anchor="middle" class="history-date-label">${escapeHtml(formatDate(item.dateValue).slice(5))}</text>`;
    })
    .join("");

  const paths = selectedSeries.map((series, index) => {
    const color = PRICE_HISTORY_COLORS[index % PRICE_HISTORY_COLORS.length];
    const points = series.points || [];
    const d = points
      .map((point, pointIndex) => {
        const x = xFor(pointIndex, points.length);
        const y = yFor(point.value);
        return `${pointIndex === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
    const markers = points
      .map((point, pointIndex) => {
        const x = xFor(pointIndex, points.length);
        const y = yFor(point.value);
        const isLast = pointIndex === points.length - 1;
        const ariaLabel = `${series.label} ${formatDate(point.date)} ${formatNumber(point.value, 0)} 元/吨`;
        return `
          <g class="history-point-wrap"
             tabindex="0"
             role="button"
             aria-label="${escapeHtml(ariaLabel)}"
             data-history-label="${escapeHtml(series.label)}"
             data-history-date="${escapeHtml(formatDate(point.date))}"
             data-history-value="${escapeHtml(formatNumber(point.value, 0))}"
             data-history-unit="元/吨"
             data-history-color="${escapeHtml(color)}">
            <circle class="history-point-hit" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="9" fill="transparent" />
            <circle class="history-point" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${isLast ? 3.4 : 2.4}" fill="${color}" />
          </g>`;
      })
      .join("");
    return `
      <path d="${escapeHtml(d)}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
      ${markers}`;
  }).join("");

  const legend = selectedSeries.map((series, index) => {
    const color = PRICE_HISTORY_COLORS[index % PRICE_HISTORY_COLORS.length];
    const latest = series.points?.[series.points.length - 1]?.value;
    return `
      <div class="history-legend-item">
        <i style="background:${color}"></i>
        <span>${escapeHtml(series.label)}</span>
        <strong>${formatNumber(latest, 0)}</strong>
      </div>`;
  }).join("");

  dom.priceHistoryChart.innerHTML = `
    <svg class="history-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="历史价格走势图">
      <line x1="${left}" y1="${top}" x2="${left}" y2="${height - bottom}" class="history-axis" />
      <line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" class="history-axis" />
      <line x1="${left}" y1="${top + innerHeight / 2}" x2="${width - right}" y2="${top + innerHeight / 2}" class="history-gridline" />
      <text x="2" y="${top + 4}" class="history-axis-label">${formatNumber(maxValue, 0)}</text>
      <text x="2" y="${height - bottom}" class="history-axis-label">${formatNumber(minValue, 0)}</text>
      ${paths}
      ${dateTicks}
    </svg>
    <div class="history-legend">${legend}</div>
    <div class="history-tooltip" role="status" hidden></div>`;
  bindHistoryTooltip();
}

function bindHistoryTooltip() {
  if (!dom.priceHistoryChart) return;
  const tooltip = dom.priceHistoryChart.querySelector(".history-tooltip");
  if (!tooltip) return;

  const hideTooltip = () => {
    tooltip.hidden = true;
  };
  const showTooltip = (target, pointerLike) => {
    const label = target.dataset.historyLabel || "-";
    const dateValue = target.dataset.historyDate || "-";
    const value = target.dataset.historyValue || "-";
    const unit = target.dataset.historyUnit || "";
    const color = target.dataset.historyColor || PRICE_HISTORY_COLORS[0];
    tooltip.style.setProperty("--series-color", color);
    tooltip.innerHTML = `
      <div class="history-tooltip-title">
        <i></i>
        <strong>${escapeHtml(label)}</strong>
      </div>
      <div class="history-tooltip-row">
        <span>${escapeHtml(dateValue)}</span>
        <b>${escapeHtml(value)} ${escapeHtml(unit)}</b>
      </div>`;
    tooltip.hidden = false;
    positionHistoryTooltip(pointerLike, tooltip);
  };

  dom.priceHistoryChart.onpointermove = (event) => {
    const target = event.target?.closest?.(".history-point-wrap");
    if (!target) {
      hideTooltip();
      return;
    }
    showTooltip(target, event);
  };
  dom.priceHistoryChart.onpointerleave = hideTooltip;
  dom.priceHistoryChart.querySelectorAll(".history-point-wrap").forEach((point) => {
    point.addEventListener("focus", () => {
      const rect = point.getBoundingClientRect();
      showTooltip(point, {
        clientX: rect.left + rect.width / 2,
        clientY: rect.top + rect.height / 2,
      });
    });
    point.addEventListener("blur", hideTooltip);
  });
}

function positionHistoryTooltip(pointerLike, tooltip) {
  const chartRect = dom.priceHistoryChart.getBoundingClientRect();
  const rawX = Number(pointerLike.clientX || 0) - chartRect.left;
  const rawY = Number(pointerLike.clientY || 0) - chartRect.top;
  const tooltipWidth = tooltip.offsetWidth || 150;
  const tooltipHeight = tooltip.offsetHeight || 58;
  const left = Math.max(8, Math.min(rawX + 12, chartRect.width - tooltipWidth - 8));
  const top = Math.max(8, Math.min(rawY - tooltipHeight - 12, chartRect.height - tooltipHeight - 8));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

async function loadPriceHistory() {
  if (!hasPermission("workbench.view")) return;
  if (!dom.priceHistoryChart) return;
  const requestToken = ++state.priceHistoryRequestToken;
  setChip(dom.priceHistoryMeta, "刷新中", "loading");
  try {
    const params = new URLSearchParams({ days: String(state.priceHistoryDays) });
    state.priceHistorySeries.forEach((key) => params.append("series", key));
    const payload = await fetchJson(`/api/v1/market/price-history?${params.toString()}`);
    if (requestToken !== state.priceHistoryRequestToken) return;
    state.priceHistory = payload;
    renderPriceHistory();
  } catch (error) {
    if (requestToken !== state.priceHistoryRequestToken) return;
    console.error(error);
    dom.priceHistoryChart.innerHTML = emptyState(`走势加载失败：${error.message || error}`);
    setChip(dom.priceHistoryMeta, "加载失败", "error");
  }
}

function isoDateOffset(daysOffset) {
  const value = new Date();
  value.setDate(value.getDate() + daysOffset);
  return value.toISOString().slice(0, 10);
}

function currentMonthStartIsoDate() {
  const value = new Date();
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}-01`;
}

function ensureOilchemInventoryDateInputs() {
  if (!dom.oilchemInventoryStart || !dom.oilchemInventoryEnd) return;
  if (!dom.oilchemInventoryEnd.value) dom.oilchemInventoryEnd.value = isoDateOffset(0);
  if (!dom.oilchemInventoryStart.value) dom.oilchemInventoryStart.value = currentMonthStartIsoDate();
}

function oilchemInventoryParams() {
  ensureOilchemInventoryDateInputs();
  const params = new URLSearchParams();
  if (dom.oilchemInventoryStart?.value) params.set("start_date", dom.oilchemInventoryStart.value);
  if (dom.oilchemInventoryEnd?.value) params.set("end_date", dom.oilchemInventoryEnd.value);
  return params;
}

async function loadOilchemInventory() {
  if (!hasPermission("workbench.view")) return;
  if (!dom.oilchemInventoryTable) return;
  setChip(dom.oilchemInventoryMeta, "隆众库存加载中", "loading");
  try {
    const payload = await fetchJson(`/api/v1/oilchem-openapi/inventory?${oilchemInventoryParams().toString()}`);
    state.oilchemInventory = payload;
    renderOilchemInventory();
  } catch (error) {
    console.error(error);
    setChip(dom.oilchemInventoryMeta, "隆众库存加载失败", "error");
    dom.oilchemInventorySummary.innerHTML = "";
    dom.oilchemInventoryTable.innerHTML = emptyState(`隆众库存加载失败：${error.message || error}`);
  }
}

function csvCell(value) {
  const text = String(value ?? "");
  if (/[",\n\r]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

function oilchemInventoryFreqLabel(value) {
  const freq = String(value || "").toLowerCase();
  if (freq === "weekly") return "周度";
  if (freq === "daily") return "日度";
  if (freq === "monthly") return "月度";
  return value || "-";
}

function oilchemInventoryFreqValue(label) {
  if (label === "周度") return "weekly";
  if (label === "日度") return "daily";
  if (label === "月度") return "monthly";
  return label;
}

function oilchemInventoryFilterName(key) {
  return {
    product: "品类",
    owner: "库存主体",
    regions: "区域",
  }[key] || key;
}

function oilchemInventoryUnique(rows, getter) {
  return Array.from(new Set((rows || []).map(getter).filter(Boolean))).sort((left, right) => (
    String(left).localeCompare(String(right), "zh-CN")
  ));
}

function oilchemInventoryMaxDate(rows) {
  return (rows || []).reduce((latest, row) => {
    const date = String(row.date || "");
    return date > latest ? date : latest;
  }, "");
}

function oilchemInventoryFilteredRows(rows) {
  const filters = state.oilchemInventoryFilters || {};
  const selectedRegions = Array.isArray(filters.regions) ? filters.regions : [];
  return (rows || []).filter((row) => {
    if (filters.product !== "不限" && row.product !== filters.product) return false;
    if (filters.owner !== "不限" && row.owner !== filters.owner) return false;
    if (selectedRegions.length && !selectedRegions.includes(row.region)) return false;
    return true;
  });
}

function renderOilchemInventoryFilterRow(key, label, values) {
  const active = state.oilchemInventoryFilters?.[key] || "不限";
  const options = ["不限", ...values];
  return `
    <div class="oilchem-filter-row">
      <span class="oilchem-filter-label">${escapeHtml(label)}</span>
      <div class="oilchem-filter-options">
        ${options.map((value) => `
          <button class="oilchem-filter-chip${active === value ? " is-active" : ""}" type="button" data-oilchem-filter="${escapeHtml(key)}" data-oilchem-value="${escapeHtml(value)}">
            ${escapeHtml(value)}
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function renderOilchemInventoryRegionFilterRow(values) {
  const selectedRegions = Array.isArray(state.oilchemInventoryFilters?.regions)
    ? state.oilchemInventoryFilters.regions
    : [];
  const options = ["不限", ...values];
  return `
    <div class="oilchem-filter-row">
      <span class="oilchem-filter-label">区域</span>
      <div class="oilchem-filter-options">
        ${options.map((value) => {
          const active = value === "不限" ? selectedRegions.length === 0 : selectedRegions.includes(value);
          return `
            <button class="oilchem-filter-chip${active ? " is-active" : ""}" type="button" data-oilchem-filter="regions" data-oilchem-value="${escapeHtml(value)}">
              ${escapeHtml(value)}
            </button>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function renderOilchemInventoryFilters(rows) {
  if (!dom.oilchemInventoryFilters) return;
  const products = oilchemInventoryUnique(rows, (row) => row.product);
  const owners = oilchemInventoryUnique(rows, (row) => row.owner);
  const regions = oilchemInventoryUnique(rows, (row) => row.region);
  dom.oilchemInventoryFilters.innerHTML = [
    renderOilchemInventoryFilterRow("product", "品类", products),
    renderOilchemInventoryFilterRow("owner", "库存主体", owners),
    renderOilchemInventoryRegionFilterRow(regions),
  ].join("");
  dom.oilchemInventoryFilters.querySelectorAll("[data-oilchem-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.oilchemFilter;
      const value = button.dataset.oilchemValue || "不限";
      if (key === "regions") {
        const current = Array.isArray(state.oilchemInventoryFilters.regions)
          ? [...state.oilchemInventoryFilters.regions]
          : [];
        if (value === "不限") {
          state.oilchemInventoryFilters.regions = [];
        } else if (current.includes(value)) {
          state.oilchemInventoryFilters.regions = current.filter((item) => item !== value);
        } else {
          state.oilchemInventoryFilters.regions = [...current, value];
        }
      } else {
        state.oilchemInventoryFilters[key] = value;
      }
      renderOilchemInventory();
    });
  });
}

function renderOilchemInventorySelected() {
  if (!dom.oilchemInventorySelected) return;
  const filters = state.oilchemInventoryFilters || {};
  const active = [
    ...Object.entries(filters).filter(([key, value]) => key !== "regions" && value && value !== "不限"),
    ...((Array.isArray(filters.regions) ? filters.regions : []).map((region) => ["regions", region])),
  ];
  dom.oilchemInventorySelected.innerHTML = `
    <span class="oilchem-selected-label">当前筛选</span>
    <div class="oilchem-selected-list">
      ${active.length ? active.map(([key, value]) => `
        <button class="oilchem-selected-chip" type="button" data-oilchem-clear="${escapeHtml(key)}" data-oilchem-clear-value="${escapeHtml(value)}">
          ${escapeHtml(oilchemInventoryFilterName(key))}：${escapeHtml(value)} <i>×</i>
        </button>
      `).join("") : `<span class="oilchem-selected-empty">全部数据</span>`}
    </div>
  `;
  dom.oilchemInventorySelected.querySelectorAll("[data-oilchem-clear]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.oilchemClear;
      if (key === "regions") {
        const value = button.dataset.oilchemClearValue || "";
        state.oilchemInventoryFilters.regions = (state.oilchemInventoryFilters.regions || [])
          .filter((item) => item !== value);
      } else {
        state.oilchemInventoryFilters[key] = "不限";
      }
      renderOilchemInventory();
    });
  });
}

function buildOilchemInventoryCards(rows) {
  const latestDate = oilchemInventoryMaxDate(rows);
  const latestRows = rows.filter((row) => String(row.date || "") === latestDate);
  return latestRows.slice(0, 4).map((row) => ({
    label: row.project_label || row.indicator_name || "-",
    value: row.value,
    unit: row.unit || "万吨",
    sub: `${formatDate(row.date)} / ${row.region || "-"}`,
  }));
}

function renderOilchemInventory() {
  const payload = state.oilchemInventory;
  if (!payload) {
    dom.oilchemInventorySummary.innerHTML = "";
    dom.oilchemInventoryTable.innerHTML = emptyState("隆众库存加载中");
    return;
  }
  const allRows = payload.items || [];
  renderOilchemInventoryFilters(allRows);
  renderOilchemInventorySelected();
  const rows = oilchemInventoryFilteredRows(allRows);
  const latestDate = oilchemInventoryMaxDate(rows) || payload.latest_date || "-";
  setChip(dom.oilchemInventoryMeta, `范围内 ${rows.length} 条 / 最新 ${formatDate(latestDate)}`);
  const cards = buildOilchemInventoryCards(rows);
  dom.oilchemInventorySummary.innerHTML = cards.length
    ? cards.map((card) => `
      <article class="oilchem-inventory-card">
        <span>${escapeHtml(card.label)}</span>
        <strong>${formatNumberTrim(card.value, 2)}</strong>
        <small>${escapeHtml(card.unit || "万吨")} / ${escapeHtml(card.sub || "")}</small>
      </article>
    `).join("")
    : emptyState("暂无库存摘要");

  if (!rows.length) {
    dom.oilchemInventoryTable.innerHTML = emptyState("暂无隆众库存数据");
    return;
  }
  const visibleRows = rows.slice(0, 260);
  dom.oilchemInventoryTable.innerHTML = `
    <div class="oilchem-table-head">
      <span>日期</span>
      <span>指标</span>
      <span>区域</span>
      <span>数值</span>
    </div>
    ${visibleRows.map((row) => `
      <div class="oilchem-table-row">
        <span>${escapeHtml(formatDate(row.date))}</span>
        <span>${escapeHtml(row.project_label || row.indicator_name || "-")}</span>
        <span>${escapeHtml(row.region || "-")}</span>
        <strong>${formatNumberTrim(row.value, 2)} ${escapeHtml(row.unit || "")}</strong>
      </div>
    `).join("")}
    ${rows.length > visibleRows.length ? `<div class="oilchem-table-more">已显示前 ${visibleRows.length} 条，导出可获取当前筛选下全部 ${rows.length} 条</div>` : ""}
  `;
}

function exportOilchemInventory() {
  if (!hasPermission("workbench.view")) return;
  const rows = oilchemInventoryFilteredRows(state.oilchemInventory?.items || []);
  if (!rows.length) return;
  const header = ["日期", "指标", "品类", "库存主体", "区域", "频率", "数值", "单位"];
  const lines = [
    header.map(csvCell).join(","),
    ...rows.map((row) => [
      formatDate(row.date),
      row.project_label || row.indicator_name || "",
      row.product || "",
      row.owner || "",
      row.region || "",
      oilchemInventoryFreqLabel(row.freq),
      row.value ?? "",
      row.unit || "",
    ].map(csvCell).join(",")),
  ];
  const blob = new Blob([`\ufeff${lines.join("\n")}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `隆众已购库存_${dom.oilchemInventoryStart?.value || "start"}_${dom.oilchemInventoryEnd?.value || "end"}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function renderAccuracySummary() {
  if (!dom.accuracySummary) return;
  const payload = state.predictionAccuracy;
  if (!payload) {
    dom.accuracySummary.innerHTML = emptyState("复盘数据加载中");
    return;
  }
  const summary = payload.summary || {};
  const cards = [
    ["已验证样本", formatNumberTrim(summary.sample_size, 0), `待验证 ${formatNumberTrim(summary.pending_size, 0)} 条`],
    ["平均绝对偏差", summary.mae == null ? "-" : formatNumberTrim(summary.mae, 1), "元/吨"],
    ["方向命中率", formatPercentValue(summary.direction_accuracy), "涨跌方向"],
    ["区间命中率", formatPercentValue(summary.range_hit_rate), "真实价落入预测区间"],
    ["±50内占比", formatPercentValue(summary.within_50_rate), "经营可用性观察"],
  ];
  dom.accuracySummary.innerHTML = cards.map(([label, value, sub], index) => `
    <article class="accuracy-summary-card${index === 1 ? " is-primary" : ""}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(sub)}</small>
    </article>
  `).join("");
}

function renderAccuracyChart() {
  if (!dom.accuracyChart) return;
  const items = (state.predictionAccuracy?.items || []).filter((item) => item.status === "evaluated");
  if (!items.length) {
    dom.accuracyChart.innerHTML = emptyState("暂无已验证预测样本");
    return;
  }
  const visible = items.slice(0, 12).reverse();
  const maxError = Math.max(50, ...visible.map((item) => Math.abs(Number(item.point_error || 0))));
  dom.accuracyChart.innerHTML = `
    <div class="accuracy-axis">
      <span>预测偏低</span>
      <i></i>
      <span>预测偏高</span>
    </div>
    <div class="accuracy-bars">
      ${visible.map((item) => {
        const error = Number(item.point_error || 0);
        const magnitude = Math.min(100, Math.abs(error) / maxError * 100);
        const side = error >= 0 ? "right" : "left";
        const tone = error >= 0 ? "tone-down" : "tone-up";
        return `
          <article class="accuracy-bar-row">
            <div class="accuracy-bar-label">
              <strong>${escapeHtml(formatDate(item.target_date))}</strong>
              <span>${escapeHtml(item.source)} / ${escapeHtml(item.horizon)}</span>
            </div>
            <div class="accuracy-bar-track" aria-label="预测偏差 ${formatNumberTrim(error, 1)} 元每吨">
              <i class="accuracy-zero-line"></i>
              <span class="accuracy-error-bar ${side}" style="--error-size:${magnitude}%"></span>
            </div>
            <div class="accuracy-bar-value ${tone}">${formatNumberTrim(error, 1)}</div>
          </article>`;
      }).join("")}
    </div>`;
}

function renderAccuracyList() {
  if (!dom.accuracyList) return;
  const items = state.predictionAccuracy?.items || [];
  if (!items.length) {
    dom.accuracyList.innerHTML = emptyState("暂无预测复盘记录");
    return;
  }
  dom.accuracyList.innerHTML = items.slice(0, 40).map((item) => {
    const evaluated = item.status === "evaluated";
    const miss = evaluated && (item.range_hit === false || item.direction_hit === false);
    const statusClass = evaluated ? (miss ? "is-miss" : "is-hit") : "is-pending";
    return `
      <article class="accuracy-row ${statusClass}">
        <div class="accuracy-row-main">
          <div class="accuracy-row-title">
            <strong>${escapeHtml(item.product_label)} ${escapeHtml(item.horizon)}</strong>
            <span>${escapeHtml(item.source)}</span>
            <em>${escapeHtml(predictionStatusLabel(item.status))}</em>
          </div>
          <div class="accuracy-row-dates">
            <span>预测日 ${escapeHtml(formatDate(item.as_of_date))}</span>
            <span>基准价日期 ${escapeHtml(formatDate(item.base_price_date || item.as_of_date))}</span>
            <span>真实价日期 ${escapeHtml(formatDate(item.actual_price_date || item.target_date))}</span>
          </div>
        </div>
        <div class="accuracy-price-stack">
          <span>预测点位</span>
          <strong>${formatNumber(item.predicted_point)}</strong>
          <small>${formatNumber(item.range_lower)} ~ ${formatNumber(item.range_upper)}</small>
        </div>
        <div class="accuracy-price-stack">
          <span>真实价格</span>
          <strong>${item.actual_price == null ? "-" : formatNumber(item.actual_price)}</strong>
          <small>${item.actual_price_date ? formatDate(item.actual_price_date) : "待验证"} / ${item.actual_change == null ? "待验证" : `${actualDirectionFromChange(item.actual_change)} ${formatNumberTrim(item.actual_change, 1)}`}</small>
        </div>
        <div class="accuracy-hit-stack">
          <span class="${item.range_hit === false ? "tone-up" : ""}">区间${escapeHtml(hitLabel(item.range_hit))}</span>
          <span class="${item.direction_hit === false ? "tone-up" : ""}">方向${escapeHtml(hitLabel(item.direction_hit))}</span>
          <strong>${item.absolute_error == null ? "-" : `${formatNumberTrim(item.absolute_error, 1)} 元/吨`}</strong>
        </div>
      </article>`;
  }).join("");
}

function renderPredictionAccuracy() {
  const payload = state.predictionAccuracy;
  if (!payload) {
    setChip(dom.accuracyMeta, "待加载");
    setChip(dom.accuracyRuleMeta, "山东92#");
    renderAccuracySummary();
    renderAccuracyChart();
    renderAccuracyList();
    return;
  }
  setChip(dom.accuracyMeta, `更新于 ${formatDateTime(payload.generated_at)}`);
  setChip(dom.accuracyRuleMeta, payload.metadata?.evaluation_rule || "仅统计已验证样本");
  renderAccuracySummary();
  renderAccuracyChart();
  renderAccuracyList();
}

async function loadPredictionAccuracy() {
  if (!hasPermission("workbench.view")) return;
  if (!dom.accuracyChart) return;
  setChip(dom.accuracyMeta, "复盘刷新中", "loading");
  if (dom.accuracyRefresh) dom.accuracyRefresh.disabled = true;
  try {
    state.predictionAccuracy = await fetchJson("/api/v1/prediction-accuracy?days=45&limit=160");
    renderPredictionAccuracy();
  } catch (error) {
    console.error(error);
    setChip(dom.accuracyMeta, "复盘加载失败", "error");
    if (dom.accuracyChart) dom.accuracyChart.innerHTML = emptyState(`复盘加载失败：${error.message || error}`);
  } finally {
    if (dom.accuracyRefresh) dom.accuracyRefresh.disabled = false;
  }
}

function findAlertById(alertId) {
  return (state.policyFeed?.alerts || []).find((item) => String(item.alert_id || "") === String(alertId));
}

function buildAlertScenarioText(alert) {
  if (!alert) return "重点预警跟踪：请结合最新事件、Brent变化、发改委调价窗口和山东现货成交重新研判。";
  const parts = [
    `重点预警跟踪：${alert.title || "未命名预警"}`,
    `事件类型：${alert.event_type || alert.category || "预警"}`,
    `影响方向：${alert.direction || "扰动"}`,
    `预期影响：${alert.expected_impact || "需复核"}`,
    `影响范围：${alert.affected_region || "重点区域"} / ${alert.affected_product || "92#汽油"}`,
    `建议动作：${alert.recommended_action || alert.action || "人工复核后再调整报价和库存动作"}`,
    `预警时间：${alert.time || "-"}`,
  ];
  return parts.filter(Boolean).join("；");
}

async function trackAlertAndRefreshResearch(alertId, button) {
  const alert = findAlertById(alertId);
  activateMainView("home");
  if (dom.newsToggle) dom.newsToggle.checked = true;
  if (dom.eventToggle) dom.eventToggle.checked = true;
  if (dom.scenarioInput) {
    dom.scenarioInput.value = buildAlertScenarioText(alert);
  }
  document.querySelector(".research-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  setChip(dom.researchMeta, "按重点预警刷新研判中", "loading");

  const statusPromise = fetchJson(`/api/v1/alerts/${encodeURIComponent(alertId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "tracking" }),
  }).catch((error) => {
    console.error(error);
    return null;
  });

  try {
    await loadDashboard();
    await statusPromise;
    await loadPolicyFeed();
    setChip(dom.researchMeta, "已按重点预警刷新研判");
  } catch (error) {
    console.error(error);
    setChip(dom.researchMeta, `预警跟踪刷新失败：${error.message || error}`, "error");
    if (button) button.disabled = false;
  }
}

function fillSelect(target, values, selectedValue) {
  const selected = selectedValue || values?.[0] || "";
  target.innerHTML = (values || []).map((value) => {
    const active = value === selected ? ' selected="selected"' : "";
    return `<option value="${escapeHtml(value)}"${active}>${escapeHtml(value)}</option>`;
  }).join("");
}

function renderFeedCards(items, kind) {
  if (!items?.length) return emptyState("暂无数据");

  return items.map((item) => {
    const title = item.headline || item.title || "未命名";
    const excerpt = item.summary || item.content || item.description || "";
    const titleHtml = item.url
      ? `<a class="feed-title" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(title)}</a>`
      : `<div class="feed-title">${escapeHtml(title)}</div>`;
    const time = item.publish_time || item.publish_date || item.effective_time || "-";
    const source = displaySourceLabel(item.source || (kind === "policy" ? "政策" : "资讯"));
    const extra =
      kind === "policy"
        ? `汽油 ${formatNumber(item.gasoline_change_yuan_per_ton, 0)} / 柴油 ${formatNumber(item.diesel_change_yuan_per_ton, 0)}`
        : `重要度 ${formatNumber(item.importance_score, 1)}`;
    return `
      <article class="feed-card">
        ${titleHtml}
        <div class="feed-row">
          <span>${escapeHtml(source)}</span>
          <span>${escapeHtml(time)}</span>
        </div>
        <div class="feed-excerpt">${renderMultilineText(excerpt || extra)}</div>
        <div class="feed-meta">${escapeHtml(extra)}</div>
      </article>`;
  }).join("");
}

function renderPolicyPage() {
  if (!hasPermission("policy.view")) {
    const noPermission = emptyState("当前账号未开通政策与事件查看权限");
    dom.refinedNewsList.innerHTML = noPermission;
    dom.eventNewsList.innerHTML = noPermission;
    dom.policyList.innerHTML = noPermission;
    setChip(dom.policyPageMeta, "权限受限", "error");
    return;
  }
  if (!state.policyFeed) {
    dom.refinedNewsList.innerHTML = emptyState("资讯加载中");
    dom.eventNewsList.innerHTML = emptyState("事件加载中");
    dom.policyList.innerHTML = emptyState("政策加载中");
    return;
  }

  fillSelect(dom.newsDateSelect, state.policyFeed.available_news_dates, state.policyFeed.news_date);
  fillSelect(dom.policyDateSelect, state.policyFeed.available_policy_dates, state.policyFeed.policy_date);
  dom.sortTabs.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.sortMode === state.policySortMode);
  });

  const refinedDate = state.policyFeed.refined_news_date || state.policyFeed.news_date;
  const eventDate = state.policyFeed.event_news_date || state.policyFeed.news_date;
  setChip(
    dom.policyPageMeta,
    `资讯 ${formatDate(refinedDate)} / 快讯 ${formatDate(eventDate)} / 政策 ${formatDate(state.policyFeed.policy_date)}`
  );
  dom.refinedNewsList.innerHTML = renderFeedCards(state.policyFeed.refined_news_items, "news");
  dom.eventNewsList.innerHTML = renderFeedCards(state.policyFeed.event_news_items, "event");
  dom.policyList.innerHTML = renderFeedCards(state.policyFeed.policy_items, "policy");
}

function checkedPermissionCodes(target) {
  return Array.from(target?.querySelectorAll('input[type="checkbox"][value]:checked') || []).map((node) => node.value);
}

function renderPermissionGroups(target, permissions, selectedCodes = []) {
  if (!target) return;
  const selected = new Set(selectedCodes || []);
  const groups = groupedPermissions(permissions);
  if (!groups.length) {
    target.innerHTML = emptyState("暂无权限目录");
    return;
  }
  target.innerHTML = groups
    .map(
      (group) => `
        <section class="permission-group">
          <div class="permission-group-head">
            <h3>${escapeHtml(group.moduleLabel)}</h3>
            <span>${group.permissions.length} 项</span>
          </div>
          <div class="permission-grid">
            ${group.permissions
              .map(
                (item) => `
                  <label class="permission-item">
                    <div class="permission-item-top">
                      <input type="checkbox" value="${escapeHtml(item.permission_code)}" ${
                        selected.has(item.permission_code) ? 'checked="checked"' : ""
                      } />
                      <div class="permission-item-copy">
                        <span>${escapeHtml(item.permission_name)}</span>
                        <small>${escapeHtml(item.description || "无说明")}</small>
                      </div>
                    </div>
                  </label>`
              )
              .join("")}
          </div>
        </section>`
    )
    .join("");
}

function renderReadonlyPermissionGroups(target, permissions) {
  if (!target) return;
  const groups = groupedPermissions(permissions);
  if (!groups.length) {
    target.innerHTML = emptyState("暂无权限信息");
    return;
  }
  target.innerHTML = groups
    .map(
      (group) => `
        <section class="permission-group">
          <div class="permission-group-head">
            <h3>${escapeHtml(group.moduleLabel)}</h3>
            <span>${group.permissions.length} 项</span>
          </div>
          <div class="permission-tag-list">
            ${group.permissions
              .map(
                (item) =>
                  `<span class="tag">${escapeHtml(item.permission_name)}</span>`
              )
              .join("")}
          </div>
        </section>`
    )
    .join("");
}

function renderRoleTemplates(target, roles, selectedCodes = []) {
  if (!target) return;
  const selected = new Set(selectedCodes || []);
  if (!roles?.length) {
    target.innerHTML = emptyState("暂无角色模板");
    return;
  }
  target.innerHTML = roles
    .map((role) => {
      const permissionNames = (role.permissions || []).map((item) => item.permission_name).slice(0, 4);
      return `
        <label class="role-template-card">
          <input type="checkbox" value="${escapeHtml(role.role_code)}" ${
            selected.has(role.role_code) ? 'checked="checked"' : ""
          } />
          <span class="role-template-main">
            <strong>${escapeHtml(role.role_name)}</strong>
            <small>${escapeHtml(role.description || "无说明")}</small>
            <em>${escapeHtml(permissionNames.join(" / ") || "暂无权限")}</em>
          </span>
          <span class="role-template-count">${(role.permission_codes || []).length} 项</span>
        </label>`;
    })
    .join("");
}

function checkedRoleCodes(target) {
  return Array.from(target?.querySelectorAll('input[type="checkbox"][value]:checked') || []).map((node) => node.value);
}

function renderAccountChrome() {
  const user = state.currentUser;
  if (!user) return;
  if (dom.accountAvatar) dom.accountAvatar.textContent = initials(user.display_name || user.username);
  if (dom.accountName) dom.accountName.textContent = user.display_name || user.username;
  if (dom.accountTitle) dom.accountTitle.textContent = user.title || user.username;
}

function renderProfileView() {
  const user = state.currentUser;
  if (!user) return;

  dom.profileUsername.textContent = user.username || "-";
  dom.profileDisplayName.textContent = user.display_name || "-";
  dom.profileLastLogin.textContent = formatDateTime(user.last_login_at);
  dom.profileUpdatedAt.textContent = `最近更新 ${formatDateTime(user.updated_at)}`;
  dom.profileActiveStatus.textContent = user.is_active ? "启用中" : "已停用";
  dom.profilePermissionCount.textContent = `${(user.permission_codes || []).length} 项权限`;
  dom.profileDisplayInput.value = user.display_name || "";
  dom.profileTitleInput.value = user.title || "";
  dom.profilePasswordInput.value = "";
  dom.profilePasswordConfirmInput.value = "";
  renderReadonlyPermissionGroups(dom.profilePermissionGroups, user.permissions || []);
  setChip(dom.profileStatusChip, user.is_active ? "账号正常" : "账号停用", user.is_active ? "idle" : "error");
}

function selectedUser() {
  return state.users.find((item) => Number(item.user_id) === Number(state.selectedUserId)) || null;
}

function usageActionLabel(action) {
  const labels = {
    login: "登录成功",
    login_failed: "登录失败",
    login_request: "登录请求",
    logout: "退出登录",
    prediction: "价格预测",
    chat: "模型对话",
    briefing: "晨报",
    user_admin: "用户管理",
    permission_admin: "权限查看",
    agent_manage: "智能体管理",
    policy_event: "政策事件",
    freight_setting: "运费设置",
    freight_view: "运费查看",
    market_view: "市场查看",
    api_request: "接口访问",
  };
  return labels[action] || action || "-";
}

function renderUsageLogs() {
  if (!dom.usageLogList) return;
  const logs = state.usageLogs || [];
  setChip(dom.usageLogMeta, logs.length ? `最近 ${logs.length} 条` : "暂无记录");
  if (!logs.length) {
    dom.usageLogList.innerHTML = emptyState("暂无系统使用记录");
    return;
  }
  dom.usageLogList.innerHTML = logs
    .map((item) => {
      const statusClassName = Number(item.status_code || 0) >= 400 ? "is-error" : "is-ok";
      const userLabel = item.username || (item.user_id ? `用户 ${item.user_id}` : "未识别用户");
      const statusText = item.status_code ? `${item.status_code}` : "-";
      const durationText = item.duration_ms == null ? "-" : `${item.duration_ms}ms`;
      return `
        <article class="usage-log-row">
          <div class="usage-log-main">
            <strong>${escapeHtml(usageActionLabel(item.action))}</strong>
            <span>${escapeHtml(userLabel)}</span>
          </div>
          <div class="usage-log-path">
            <span>${escapeHtml(item.method || "-")}</span>
            <code>${escapeHtml(item.path || "-")}</code>
          </div>
          <div class="usage-log-meta">
            <span class="${statusClassName}">${escapeHtml(statusText)}</span>
            <span>${escapeHtml(durationText)}</span>
            <span>${escapeHtml(item.ip_address || "-")}</span>
          </div>
          <time>${escapeHtml(formatDateTime(item.created_at))}</time>
        </article>`;
    })
    .join("");
}

function renderPermissionWorkspace() {
  if (!hasPermission("permissions.manage")) return;
  renderUsageLogs();

  setChip(dom.permissionMeta, `用户 ${state.users.length} / 权限 ${state.permissionCatalog.length}`);
  dom.permissionCounts.innerHTML = `
    <div class="chip soft-chip">启用 ${state.users.filter((item) => item.is_active).length}</div>
    <div class="chip soft-chip">停用 ${state.users.filter((item) => !item.is_active).length}</div>
    <div class="chip soft-chip">角色 ${state.roleCatalog.length}</div>
  `;

  renderRoleTemplates(dom.createRoleGroups, state.roleCatalog, ["viewer"]);

  if (!state.users.length) {
    dom.userList.innerHTML = emptyState("暂无用户");
    dom.selectedUserCaption.textContent = "暂无可编辑用户";
    dom.selectedUserMeta.textContent = "未选择";
    dom.editDisplayName.value = "";
    dom.editTitle.value = "";
    dom.editIsActive.checked = false;
    renderRoleTemplates(dom.editRoleGroups, state.roleCatalog, []);
    return;
  }

  if (!selectedUser()) {
    state.selectedUserId = state.users[0].user_id;
  }
  const activeUser = selectedUser();

  dom.userList.innerHTML = state.users
    .map((user) => {
      const active = Number(user.user_id) === Number(state.selectedUserId) ? " is-active" : "";
      return `
        <button class="user-card${active}" type="button" data-user-id="${escapeHtml(user.user_id)}">
          <div class="user-card-head">
            <div>
              <strong>${escapeHtml(user.display_name || user.username)}</strong>
              <small>${escapeHtml(user.username)}</small>
            </div>
            <span class="status-badge ${statusClass(user.is_active ? "online" : "disabled")}">${user.is_active ? "启用" : "停用"}</span>
          </div>
          <div class="user-card-meta">
            <span>${escapeHtml(user.title || "未设置岗位")}</span>
            <span>${(user.role_codes || []).length} 个角色</span>
          </div>
        </button>`;
    })
    .join("");

  dom.userList.querySelectorAll("[data-user-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedUserId = Number(button.dataset.userId);
      renderPermissionWorkspace();
    });
  });

  if (!activeUser) return;

  dom.selectedUserCaption.textContent = `当前编辑：${activeUser.display_name || activeUser.username}`;
  setChip(dom.selectedUserMeta, `${activeUser.username} / ${(activeUser.role_codes || []).length} 个角色`);
  dom.editDisplayName.value = activeUser.display_name || "";
  dom.editTitle.value = activeUser.title || "";
  dom.editIsActive.checked = Boolean(activeUser.is_active);
  renderRoleTemplates(dom.editRoleGroups, state.roleCatalog, activeUser.role_codes || []);
}

function applyPermissionVisibility() {
  dom.mainTabs.forEach((button) => {
    const allowed = hasPermission(button.dataset.permission);
    button.hidden = !allowed;
  });

  if (dom.briefingGenerate) {
    dom.briefingGenerate.hidden = !hasPermission("briefing.generate");
  }
  const canChat = hasPermission("chat.use");
  if (dom.chatInput) dom.chatInput.disabled = !canChat;
  if (dom.chatSubmit) dom.chatSubmit.disabled = !canChat;
  dom.quickAskButtons.forEach((button) => {
    button.disabled = !canChat;
  });
}

function renderChatLog() {
  dom.chatPanel?.classList.toggle("has-messages", state.chatMessages.length > 0);
  if (!hasPermission("chat.use")) {
    dom.chatLog.innerHTML = '<div class="chat-empty"><strong>当前账号未开通模型对话权限</strong></div>';
    return;
  }
  if (!state.chatMessages.length) {
    dom.chatLog.innerHTML = `
      <div class="chat-empty">
        <strong>今天要判断什么？</strong>
        <span>输入问题后，我会结合当前预测、政策事件和区域价差给出结论。</span>
      </div>`;
    return;
  }

  dom.chatLog.innerHTML = state.chatMessages.map((message) => {
    const extra = message.prediction
      ? `
        <div class="chat-prediction">
          <div>${escapeHtml(message.prediction.horizon)} / ${escapeHtml(directionLabel(message.prediction.direction_label))}</div>
          <div>点位 ${formatNumber(message.prediction.point_value)}，区间 ${formatNumber(message.prediction.range_lower)} ~ ${formatNumber(message.prediction.range_upper)}</div>
        </div>`
      : "";
    return `
      <article class="chat-message ${escapeHtml(message.role)}" data-message-id="${escapeHtml(message.id)}">
        <div class="chat-head">
          <span class="chat-role">${message.role === "user" ? "你" : "模型"}</span>
          <span class="chat-meta">${escapeHtml(message.meta || "")}</span>
        </div>
        <div class="chat-text">${message.loading ? '<span class="chat-thinking"><span></span><span></span><span></span></span>' : renderMultilineText(message.text)}</div>
        ${extra}
      </article>`;
  }).join("");
  dom.chatLog.scrollTop = dom.chatLog.scrollHeight;
}

function appendChatMessage(message) {
  state.chatMessages.push(message);
  renderChatLog();
  if (!message.loading) {
    persistCurrentChatSession();
  }
}

function chatHistoryStorageKey() {
  const userKey = state.currentUser?.username || state.currentUser?.user_id || "anonymous";
  return `${CHAT_HISTORY_STORAGE_KEY}:${userKey}`;
}

function loadChatHistory() {
  try {
    const raw = window.localStorage.getItem(chatHistoryStorageKey());
    const parsed = raw ? JSON.parse(raw) : [];
    state.chatSessions = Array.isArray(parsed) ? parsed.filter((item) => Array.isArray(item.messages)) : [];
  } catch {
    state.chatSessions = [];
  }
}

function saveChatHistory() {
  const sessions = state.chatSessions
    .filter((session) => Array.isArray(session.messages) && session.messages.length > 0)
    .slice(0, CHAT_HISTORY_LIMIT);
  state.chatSessions = sessions;
  window.localStorage.setItem(chatHistoryStorageKey(), JSON.stringify(sessions));
}

function currentChatTitle() {
  const firstUser = state.chatMessages.find((message) => message.role === "user");
  const text = (firstUser?.text || "新对话").trim();
  return text.length > 18 ? `${text.slice(0, 18)}...` : text;
}

function persistCurrentChatSession() {
  if (!state.chatMessages.length) return;
  const now = new Date().toISOString();
  if (!state.currentChatSessionId) {
    state.currentChatSessionId = `session-${Date.now()}`;
  }
  const session = {
    id: state.currentChatSessionId,
    title: currentChatTitle(),
    updated_at: now,
    messages: cloneData(state.chatMessages),
  };
  const existingIndex = state.chatSessions.findIndex((item) => item.id === session.id);
  if (existingIndex >= 0) {
    state.chatSessions.splice(existingIndex, 1);
  }
  state.chatSessions.unshift(session);
  saveChatHistory();
  renderChatHistory();
}

function renderChatHistory() {
  if (!dom.chatHistoryPanel || !dom.chatHistoryList) return;
  dom.chatHistoryPanel.hidden = !state.chatHistoryOpen;
  dom.chatHistoryToggle?.classList.toggle("is-active", state.chatHistoryOpen);
  if (!state.chatHistoryOpen) return;
  if (!state.chatSessions.length) {
    dom.chatHistoryList.innerHTML = '<div class="chat-history-empty">暂无历史对话</div>';
    return;
  }
  dom.chatHistoryList.innerHTML = state.chatSessions.map((session) => {
    const active = session.id === state.currentChatSessionId ? " is-active" : "";
    return `
      <button class="chat-history-item${active}" type="button" data-session-id="${escapeHtml(session.id)}">
        <strong>${escapeHtml(session.title || "未命名对话")}</strong>
        <span>${escapeHtml(formatDateTime(session.updated_at))}</span>
      </button>`;
  }).join("");
  dom.chatHistoryList.querySelectorAll("[data-session-id]").forEach((button) => {
    button.addEventListener("click", () => restoreChatSession(button.dataset.sessionId));
  });
}

function restoreChatSession(sessionId) {
  const session = state.chatSessions.find((item) => item.id === sessionId);
  if (!session) return;
  state.currentChatSessionId = session.id;
  state.chatMessages = cloneData(session.messages || []);
  state.chatHistoryOpen = false;
  renderChatHistory();
  renderChatLog();
  dom.chatInput?.focus();
}

function startNewChatSession() {
  persistCurrentChatSession();
  state.currentChatSessionId = null;
  state.chatMessages = [];
  state.chatHistoryOpen = false;
  renderChatHistory();
  renderChatLog();
  dom.chatInput?.focus();
}

async function streamAssistantMessage(messageId, text, payload) {
  const message = state.chatMessages.find((item) => item.id === messageId);
  if (!message) return;
  message.loading = false;
  message.text = "";
  renderChatLog();

  const chunkSize = 6;
  for (let i = 0; i < text.length; i += chunkSize) {
    message.text += text.slice(i, i + chunkSize);
    const node = dom.chatLog.querySelector(`[data-message-id="${messageId}"] .chat-text`);
    if (node) {
      node.innerHTML = renderMultilineText(message.text);
      dom.chatLog.scrollTop = dom.chatLog.scrollHeight;
    }
    await sleep(18);
  }

  message.prediction = payload.answer_only ? null : payload.outright_prediction;
  message.meta = payload.answer_only ? "直接回答" : `${formatDate(payload.as_of_date)} / ${payload.selected_horizon}`;
  renderChatLog();
  persistCurrentChatSession();
}

function renderAgentOverview() {
  const agents = state.agentOverview?.agents || [];
  if (!agents.length) {
    dom.agentOverviewGrid.innerHTML = emptyState("暂无智能体状态");
    return;
  }

  dom.agentOverviewGrid.innerHTML = agents.map((agent) => {
    const controls = (agent.controls || [])
      .map((control) => `<span class="tag ${control.enabled ? "" : "tag-muted"}">${escapeHtml(control.scope_label)} ${formatNumber(control.weight, 2)}</span>`)
      .join("");
    return `
      <article class="agent-card">
        <div class="agent-card-head">
          <div>
            <div class="agent-name">${escapeHtml(agent.label)}</div>
            <div class="agent-role">${escapeHtml(agent.role)}</div>
          </div>
          <span class="status-badge ${statusClass(agent.status)}">${escapeHtml(statusText(agent.status))}</span>
        </div>
        <div class="agent-stats">
          <div class="driver-item">最近运行 ${agent.run_count} 次</div>
          <div class="driver-item">平均可靠度 ${agent.avg_confidence_score == null ? "-" : formatNumber(agent.avg_confidence_score, 2)}</div>
          <div class="driver-item">平均贡献 ${agent.avg_abs_contribution == null ? "-" : formatNumber(agent.avg_abs_contribution, 2)}</div>
        </div>
        <div class="agent-summary">${escapeHtml(agent.status_reason || "")}</div>
        <div class="agent-tags">${controls || '<span class="tag tag-muted">暂无控制项</span>'}</div>
      </article>`;
  }).join("");
}

function renderAgentGraph() {
  const payload = state.agentGraph;
  if (!payload?.nodes?.length) {
    dom.agentGraphSvg.innerHTML = "";
    dom.agentGraphNodes.innerHTML = emptyState("暂无关系图");
    return;
  }

  const nodeMap = {};
  payload.nodes.forEach((node) => {
    nodeMap[node.id] = node;
  });

  dom.agentGraphSvg.innerHTML = payload.edges.map((edge) => {
    const source = nodeMap[edge.source];
    const target = nodeMap[edge.target];
    if (!source || !target) return "";
    return `<line class="graph-edge" x1="${source.x * 1000}" y1="${source.y * 620}" x2="${target.x * 1000}" y2="${target.y * 620}" />`;
  }).join("");

  dom.agentGraphNodes.innerHTML = payload.nodes.map((node) => {
    return `
      <div class="graph-node ${statusClass(node.status)}" style="left:${node.x * 100}%; top:${node.y * 100}%;">
        <div class="graph-node-label">${escapeHtml(node.label)}</div>
        <div class="graph-node-role">${escapeHtml(node.role)}</div>
      </div>`;
  }).join("");
}

function renderScopeBlocks(target, scopes) {
  if (!target) return;
  if (!scopes?.length) {
    target.innerHTML = emptyState("暂无权重与启停数据");
    return;
  }
  target.innerHTML = scopes.map((scope) => {
    return `
      <section class="scope-block">
        <h3 class="scope-title">${escapeHtml(scope.scope_label)}</h3>
        <div class="scope-rows">
          ${(scope.controls || []).map((control) => {
            return `
              <div class="scope-row">
                <div>
                  <div class="scope-agent">${escapeHtml(control.label)}</div>
                  <div class="scope-note">${escapeHtml(control.role)}</div>
                </div>
                <div class="scope-values">
                  <span class="tag ${control.enabled ? "" : "tag-muted"}">${control.enabled ? "启用" : "停用"}</span>
                  <strong>${formatNumber(control.weight, 2)}</strong>
                  <span class="scope-note">默认 ${formatNumber(control.default_weight, 2)}</span>
                </div>
              </div>`;
          }).join("")}
        </div>
      </section>`;
  }).join("");
}

function renderRunStrip() {
  const items = state.agentRuns || [];
  if (!items.length) {
    dom.runList.innerHTML = emptyState("暂无运行记录");
    return;
  }

  dom.runList.innerHTML = items.map((item) => {
    const active = item.run_id === state.selectedRunId ? " is-active" : "";
    return `
      <button class="run-card${active}" type="button" data-run-id="${escapeHtml(item.run_id)}">
        <div class="run-card-head">
          <div>${escapeHtml(item.title)}</div>
          <div class="run-meta">${escapeHtml(item.horizon)}</div>
        </div>
        <div class="run-card-body">
          <span>${escapeHtml(directionLabel(item.direction_label, item.run_type === "regional_spread"))}</span>
          <span>${formatNumber(item.point_value)}</span>
          <span>${escapeHtml(formatDateTime(item.created_at))}</span>
        </div>
      </button>`;
  }).join("");

  dom.runList.querySelectorAll("[data-run-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      await loadRunDetail(button.dataset.runId);
    });
  });
}

function renderTraceTabs() {
  const outputs = state.selectedRunDetail?.agent_outputs || [];
  if (!outputs.length) {
    dom.agentHistoryTabs.innerHTML = "";
    return;
  }
  if (!state.selectedTraceAgent || !outputs.some((item) => item.agent_name === state.selectedTraceAgent)) {
    state.selectedTraceAgent = outputs[0].agent_name;
  }

  dom.agentHistoryTabs.innerHTML = outputs.map((item) => {
    const active = item.agent_name === state.selectedTraceAgent ? " is-active" : "";
    return `<button class="trace-tab${active}" type="button" data-agent-name="${escapeHtml(item.agent_name)}">${escapeHtml(item.label)}</button>`;
  }).join("");

  dom.agentHistoryTabs.querySelectorAll("[data-agent-name]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedTraceAgent = button.dataset.agentName;
      renderTraceTabs();
      await loadAgentHistory(state.selectedTraceAgent);
    });
  });
}

function renderRunDetail() {
  const detail = state.selectedRunDetail;
  if (!detail) {
    dom.runDetail.innerHTML = emptyState("请选择一条运行记录");
    dom.runDetailMeta.textContent = "未选择运行";
    return;
  }

  const outputs = detail.agent_outputs || [];
  const outputCards = outputs.map((output) => {
    return `
      <article class="agent-output-card">
        <div class="output-head">
          <div>
            <div class="output-name">${escapeHtml(output.label)}</div>
            <div class="output-role">${escapeHtml(output.role)}</div>
          </div>
          <span class="tag ${output.enabled ? "" : "tag-muted"}">${output.enabled ? "启用" : "停用"}</span>
        </div>
        <div class="output-metrics">
          权重 ${output.weight == null ? "-" : formatNumber(output.weight, 2)}
          · 原始分 ${output.raw_score == null ? "-" : formatNumber(output.raw_score, 2)}
          · 贡献 ${output.contribution == null ? "-" : formatNumber(output.contribution, 2)}
        </div>
        <div>${escapeHtml(output.summary || "")}</div>
        <div class="driver-list">${(output.evidence || []).slice(0, 3).map((item) => `<div class="driver-item">${escapeHtml(item)}</div>`).join("")}</div>
      </article>`;
  }).join("");

  dom.runDetailMeta.textContent = `${detail.run.title} / ${detail.run.horizon} / ${formatDateTime(detail.run.created_at)}`;
  dom.runDetail.innerHTML = `
    <section class="detail-panel">
      <div class="detail-hero">
        <div class="detail-title ${toneClass(detail.run.direction_label)}">${escapeHtml(directionLabel(detail.run.direction_label, detail.run.run_type === "regional_spread"))}</div>
        <div class="detail-point ${toneClass(detail.run.direction_label)}">${formatNumber(detail.run.point_value)}</div>
        <div class="detail-range">区间 ${formatNumber(detail.run.range_lower)} ~ ${formatNumber(detail.run.range_upper)} 元/吨</div>
        <div class="body-text">${renderMultilineText(detail.explanation)}</div>
      </div>

      <div class="detail-grid">
        ${renderPredictionNarrativeSplit({
          driver_summary: detail.driver_summary,
          operating_advice: detail.operating_advice,
          raw_context: detail.raw_context || detail.run?.raw_context || {},
        })}
      </div>

      <article class="info-card">
        <h3>单体输出</h3>
        <div class="detail-grid">${outputCards || emptyState("暂无单体输出")}</div>
      </article>
    </section>`;
}

function renderAgentHistory() {
  renderTraceTabs();
  const payload = state.agentHistory;
  if (!payload?.items?.length) {
    dom.agentHistoryList.innerHTML = emptyState("暂无该智能体历史输出");
    setChip(dom.agentHistoryMeta, "暂无历史");
    return;
  }

  setChip(dom.agentHistoryMeta, `${payload.label} / 最近 ${payload.items.length} 次`);
  dom.agentHistoryList.innerHTML = payload.items.map((item) => {
    return `
      <article class="history-card">
        <div class="history-head">
          <div>${escapeHtml(item.run.title)}</div>
          <div class="run-meta">${escapeHtml(formatDateTime(item.run.created_at))}</div>
        </div>
        <div>${escapeHtml(item.output.summary || "")}</div>
        <div class="feed-meta">
          <span>${escapeHtml(directionLabel(item.output.direction, item.run.run_type === "regional_spread"))}</span>
          <span>贡献 ${formatNumber(item.output.contribution)}</span>
          <span>${escapeHtml(confidenceText(item.output.confidence_label, item.output.confidence_score))}</span>
        </div>
      </article>`;
  }).join("");
}

function currentProposal() {
  const payload = state.optimizationState;
  return payload?.pending_proposals?.[0] || payload?.latest_proposal || null;
}

function setProposalStatus(text, mode = "") {
  if (!dom.proposalStatus) return;
  dom.proposalStatus.textContent = text;
  dom.proposalStatus.classList.toggle("is-loading", mode === "loading");
  dom.proposalStatus.classList.toggle("is-error", mode === "error");
  dom.proposalStatus.classList.toggle("is-success", mode === "success");
}

function renderProposalPanel() {
  const proposal = currentProposal();
  if (!proposal) {
    dom.proposalPanel.innerHTML = emptyState("尚未生成自优化提案");
    dom.proposalApprove.disabled = true;
    dom.proposalReject.disabled = true;
    setProposalStatus("待生成");
    return;
  }

  dom.proposalApprove.disabled = proposal.status !== "pending";
  dom.proposalReject.disabled = proposal.status !== "pending";
  const statusText = {
    pending: "待人工确认",
    confirmed: "已应用到运行时权重",
    rejected: "已驳回",
    superseded: "已被新提案替代",
  }[proposal.status] || proposal.status;
  setProposalStatus(statusText, proposal.status === "confirmed" ? "success" : "");

  const summary = `
    <section class="proposal-summary">
      <div class="proposal-row">
        <div>
          <div class="proposal-name">${escapeHtml(proposal.summary)}</div>
          <div class="feed-meta">${escapeHtml(formatDateTime(proposal.created_at))} / ${escapeHtml(proposal.status)}</div>
        </div>
        <span class="tag">${escapeHtml(proposal.proposal_id)}</span>
      </div>
      <div class="body-text">${renderMultilineText(proposal.rationale)}</div>
      ${
        proposal.backtest_snapshot && Object.keys(proposal.backtest_snapshot).length
          ? `<div class="driver-item">最近回测：方向准确率 ${proposal.backtest_snapshot.direction_accuracy ?? "-"} / MAE ${
              proposal.backtest_snapshot.mae ?? "-"
            } / ΔMAE ${proposal.backtest_snapshot.delta_mae ?? "-"}</div>`
          : ""
      }
    </section>`;

  const cards = (proposal.suggestions || []).length
    ? proposal.suggestions.map((item) => {
        return `
          <article class="proposal-card">
            <div class="proposal-row">
              <div>
                <div class="proposal-name">${escapeHtml(item.label)}</div>
                <div class="feed-meta">${escapeHtml(item.scope_label)}</div>
              </div>
              <span class="tag">${formatNumber(item.current_weight, 2)} → ${formatNumber(item.proposed_weight, 2)}</span>
            </div>
            <div>${escapeHtml(item.reason || "")}</div>
            <div class="feed-meta">
              <span>样本 ${item.metrics?.run_count ?? "-"}</span>
              <span>平均贡献 ${item.metrics?.avg_abs_contribution == null ? "-" : formatNumber(item.metrics.avg_abs_contribution, 2)}</span>
              <span>同向比例 ${item.metrics?.alignment_ratio == null ? "-" : valueToPercent(item.metrics.alignment_ratio)}</span>
            </div>
          </article>`;
      }).join("")
    : emptyState("本次没有形成新的优化建议");

  dom.proposalPanel.innerHTML = `${summary}<div class="proposal-grid">${cards}</div>`;
}

function mergeNarrativePayload(payload) {
  if (!state.dashboard || !payload) return;
  const horizon = payload.selected_horizon;
  state.narrativeCache[horizon] = cloneData(payload);
  state.dashboard.outright_predictions = (state.dashboard.outright_predictions || []).map((item) =>
    item.horizon === horizon ? payload.outright_prediction : item
  );
  state.dashboard.outright_prediction =
    horizon === state.dashboard.outright_prediction?.horizon ? payload.outright_prediction : state.dashboard.outright_prediction;
  state.dashboard.regional_spread_predictions_by_horizon = {
    ...(state.dashboard.regional_spread_predictions_by_horizon || {}),
    [horizon]: payload.regional_spread_predictions || [],
  };
  if (horizon === state.selectedHorizon) {
    state.dashboard.regional_spread_predictions = payload.regional_spread_predictions || [];
  }
}

function resetToBaselineDashboard() {
  if (!state.baselineDashboard) return;
  state.dashboard = cloneData(state.baselineDashboard);
}

async function loadCurrentUser() {
  state.currentUser = await fetchJson("/api/v1/auth/me");
  renderAccountChrome();
  renderProfileView();
  applyPermissionVisibility();
}

async function loadPermissionWorkspace(force = false) {
  if (!hasPermission("permissions.manage")) return;
  if (state.permissionWorkspaceLoaded && !force) {
    renderPermissionWorkspace();
    return;
  }
  setChip(dom.permissionMeta, "权限加载中", "loading");
  try {
    const [catalog, roles, users, usageLogs] = await Promise.all([
      fetchJson("/api/v1/permissions/catalog"),
      fetchJson("/api/v1/roles/catalog"),
      fetchJson("/api/v1/users"),
      fetchJson("/api/v1/system/usage-logs?limit=80"),
    ]);
    state.permissionCatalog = catalog.items || [];
    state.roleCatalog = roles.items || [];
    state.users = users.items || [];
    state.usageLogs = usageLogs.items || [];
    state.permissionWorkspaceLoaded = true;
    renderPermissionWorkspace();
  } catch (error) {
    console.error(error);
    dom.userList.innerHTML = emptyState(`权限数据加载失败：${error.message || error}`);
    setChip(dom.permissionMeta, "加载失败", "error");
  }
}

async function submitProfileUpdate() {
  const password = dom.profilePasswordInput.value.trim();
  const passwordConfirm = dom.profilePasswordConfirmInput.value.trim();
  if (password && password !== passwordConfirm) {
    setChip(dom.profileFormMeta, "两次密码输入不一致", "error");
    return;
  }

  dom.profileSubmit.disabled = true;
  setChip(dom.profileFormMeta, "保存中", "loading");
  try {
    state.currentUser = await fetchJson("/api/v1/auth/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        display_name: dom.profileDisplayInput.value.trim() || null,
        title: dom.profileTitleInput.value.trim() || null,
        password: password || null,
      }),
    });
    renderAccountChrome();
    renderProfileView();
    setChip(dom.profileFormMeta, "已保存");
    setGlobalStatus("个人信息已更新");
  } catch (error) {
    console.error(error);
    setChip(dom.profileFormMeta, `保存失败：${error.message || error}`, "error");
  } finally {
    dom.profileSubmit.disabled = false;
  }
}

async function submitCreateUser() {
  if (!dom.createUsername.value.trim() || !dom.createDisplayName.value.trim() || !dom.createPassword.value) {
    setChip(dom.createUserMeta, "请完整填写登录名、显示名称和初始密码", "error");
    return;
  }
  dom.createUserSubmit.disabled = true;
  setChip(dom.createUserMeta, "创建中", "loading");
  try {
    const payload = await fetchJson("/api/v1/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: dom.createUsername.value.trim(),
        display_name: dom.createDisplayName.value.trim(),
        title: dom.createTitle.value.trim() || null,
        password: dom.createPassword.value,
        is_active: dom.createIsActive.checked,
        role_codes: checkedRoleCodes(dom.createRoleGroups),
      }),
    });
    dom.createUserForm.reset();
    dom.createIsActive.checked = true;
    state.selectedUserId = payload.user_id;
    state.permissionWorkspaceLoaded = false;
    await loadPermissionWorkspace(true);
    setChip(dom.createUserMeta, "创建成功");
    setGlobalStatus("用户已创建");
  } catch (error) {
    console.error(error);
    setChip(dom.createUserMeta, `创建失败：${error.message || error}`, "error");
  } finally {
    dom.createUserSubmit.disabled = false;
  }
}

async function submitUpdateUser() {
  const user = selectedUser();
  if (!user) {
    setChip(dom.editUserMeta, "请先选择用户", "error");
    return;
  }
  dom.editUserSubmit.disabled = true;
  setChip(dom.editUserMeta, "保存中", "loading");
  try {
    await fetchJson(`/api/v1/users/${encodeURIComponent(user.user_id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        display_name: dom.editDisplayName.value.trim() || null,
        title: dom.editTitle.value.trim() || null,
        is_active: dom.editIsActive.checked,
        role_codes: checkedRoleCodes(dom.editRoleGroups),
      }),
    });
    state.permissionWorkspaceLoaded = false;
    await loadPermissionWorkspace(true);
    setChip(dom.editUserMeta, "已保存");
    setGlobalStatus("用户权限已更新");
  } catch (error) {
    console.error(error);
    setChip(dom.editUserMeta, `保存失败：${error.message || error}`, "error");
  } finally {
    dom.editUserSubmit.disabled = false;
  }
}

async function logoutCurrentUser() {
  try {
    await fetchJson("/api/v1/auth/logout", { method: "POST" });
  } catch (error) {
    console.error(error);
  } finally {
    window.location.replace("/login");
  }
}

async function loadMarketSnapshot() {
  if (!hasPermission("workbench.view")) return;
  try {
    const previous = state.marketSnapshot?.latest_prices || {};
    const payload = await fetchJson("/api/v1/market/snapshot");
    payload.__previousPrices = previous;
    state.marketSnapshot = payload;
    renderMarketSnapshot();
  } catch (error) {
    console.error(error);
  }
}

function syncDashboardPriceSnapshot(payload) {
  const latestPrices = payload?.latest_prices || {};
  const brentLive = payload?.metadata?.brent_live || null;
  if (!Object.keys(latestPrices).length && !brentLive) return;

  const previousPrices = state.marketSnapshot?.latest_prices || {};
  const mergedPrices = {
    ...(state.marketSnapshot?.latest_prices || {}),
    ...latestPrices,
  };
  if (brentLive?.latest_price != null) {
    mergedPrices.brent_active_settlement = brentLive.latest_price;
    state.brentLive = brentLive;
  }

  const existingMetadata = state.marketSnapshot?.metadata || {};
  state.marketSnapshot = {
    ...(state.marketSnapshot || {}),
    as_of_date: state.marketSnapshot?.as_of_date || payload.as_of_date,
    generated_at: state.marketSnapshot?.generated_at || brentLive?.generated_at || payload.as_of_date,
    __previousPrices: previousPrices,
    latest_prices: mergedPrices,
    metadata: {
      ...existingMetadata,
      market_data_mode: existingMetadata.market_data_mode || payload.metadata?.market_data_mode,
      market_data_reason: existingMetadata.market_data_reason || payload.metadata?.market_data_reason,
      brent_live_mode: brentLive?.metadata?.market_data_mode,
      brent_live_reason: brentLive?.metadata?.market_data_reason,
      quality: {
        ...(existingMetadata.quality || {}),
        ...(brentLive?.metadata?.quality || {}),
      },
    },
  };
  renderMarketSnapshot();
}

async function loadPolicyFeed(options = {}) {
  if (!hasPermission("policy.view")) {
    renderAlerts();
    renderPolicyPage();
    return;
  }
  try {
    const forceLatest = options.forceLatest === true;
    const newsDate = forceLatest ? "" : dom.newsDateSelect.value || "";
    const policyDate = forceLatest ? "" : dom.policyDateSelect.value || "";
    const params = new URLSearchParams();
    if (newsDate) params.set("news_date", newsDate);
    if (policyDate) params.set("policy_date", policyDate);
    params.set("sort_mode", state.policySortMode);
    const payload = await fetchJson(`/api/v1/policy-events?${params.toString()}`);
    state.policyFeed = payload;
    renderAlerts();
    renderPolicyPage();
  } catch (error) {
    console.error(error);
    dom.alertList.innerHTML = emptyState(`预警加载失败：${error.message || error}`);
    dom.refinedNewsList.innerHTML = emptyState(`资讯加载失败：${error.message || error}`);
    dom.eventNewsList.innerHTML = emptyState(`事件加载失败：${error.message || error}`);
    dom.policyList.innerHTML = emptyState(`政策加载失败：${error.message || error}`);
    setChip(dom.policyPageMeta, "加载失败", "error");
  }
}

async function loadLatestBriefing() {
  if (!hasPermission("workbench.view")) return;
  try {
    state.latestBriefing = await fetchJson("/api/v1/briefings/latest");
    renderMorningBriefing();
  } catch (error) {
    console.error(error);
    dom.briefingContent.innerHTML = emptyState(`晨报加载失败：${error.message || error}`);
  }
}

async function generateBriefing() {
  if (!hasPermission("briefing.generate")) return;
  dom.briefingGenerate.disabled = true;
  setChip(dom.briefingMeta, "晨报生成中", "loading");
  try {
    state.latestBriefing = await fetchJson("/api/v1/briefings/morning", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    renderMorningBriefing();
  } catch (error) {
    console.error(error);
    setChip(dom.briefingMeta, "晨报生成失败", "error");
  } finally {
    dom.briefingGenerate.disabled = false;
  }
}

async function loadLatestDashboard() {
  if (!hasPermission("workbench.view") || state.dashboardLoading) return;
  state.dashboardLoading = true;
  setGlobalStatus("\u52a0\u8f7d\u6700\u8fd1\u4e00\u6b21\u9884\u6d4b", "loading");
  try {
    const params = new URLSearchParams({ horizon: state.selectedHorizon || "D1" });
    const payload = await fetchJson(`/api/v1/dashboard/shandong-gasoline-92/latest?${params.toString()}`);
    state.baselineDashboard = cloneData(payload);
    state.dashboard = cloneData(payload);
    applyFreightSettingsToRegionalPredictions();
    syncDashboardPriceSnapshot(payload);
    state.availableHorizons = payload.metadata?.available_horizons || DEFAULT_HORIZONS;
    if (!state.availableHorizons.includes(state.selectedHorizon)) {
      state.selectedHorizon = state.availableHorizons[0] || "D1";
    }
    renderResearch();
    renderFreightSettings(selectedRegionalPredictions());
    setGlobalStatus("\u5df2\u52a0\u8f7d\u6700\u8fd1\u4e00\u6b21\u9884\u6d4b\uff1b\u70b9\u51fb\u751f\u6210\u65b0\u9884\u6d4b\u624d\u91cd\u65b0\u8ba1\u7b97");
  } catch (error) {
    console.error(error);
    setGlobalStatus("\u672a\u627e\u5230\u5386\u53f2\u9884\u6d4b\uff0c\u8bf7\u70b9\u51fb\u751f\u6210\u65b0\u9884\u6d4b", "error");
    renderFreightSettings([]);
  } finally {
    state.dashboardLoading = false;
  }
}

async function loadFreightSettings() {
  if (!hasPermission("workbench.view") || state.freightLoading) return;
  state.freightLoading = true;
  try {
    const payload = await fetchJson("/api/v1/regional-freight-components/settings");
    state.freightSettings = payload.items || [];
    refreshFreightDependentViews();
  } catch (error) {
    console.error(error);
    if (dom.freightSettingsPanel) dom.freightSettingsPanel.innerHTML = emptyState(`\u533a\u57df\u8fd0\u8d39\u8bfb\u53d6\u5931\u8d25\uff1a${error.message || error}`);
  }
}

async function loadDashboard() {
  if (!hasPermission("workbench.view")) return;
  setGlobalStatus("研究结论刷新中", "loading");
  dom.refreshButton.disabled = true;
  try {
    const payload = await fetchJson("/api/v1/dashboard/shandong-gasoline-92", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody()),
      timeoutMs: 180000,
    });
    state.baselineDashboard = cloneData(payload);
    state.dashboard = cloneData(payload);
    applyFreightSettingsToRegionalPredictions();
    syncDashboardPriceSnapshot(payload);
    state.narrativeCache = {};
    state.availableHorizons = payload.metadata?.available_horizons || DEFAULT_HORIZONS;
    if (!state.availableHorizons.includes(state.selectedHorizon)) {
      state.selectedHorizon = state.availableHorizons[0] || "D1";
    }
    renderResearch();
    renderFreightSettings(selectedRegionalPredictions());
    if (dom.narrativeToggle.checked) {
      await ensureNarrativeForSelectedHorizon();
    }
    setGlobalStatus("研究结论已更新");
  } catch (error) {
    console.error(error);
    dom.outrightPanel.innerHTML = emptyState(`研究结论加载失败：${error.message || error}`);
    dom.spreadHeatmap.innerHTML = emptyState("区域价差加载失败");
    dom.spreadGrid.innerHTML = emptyState("区域价差加载失败");
    setGlobalStatus("研究结论加载失败", "error");
  } finally {
    state.dashboardLoading = false;
    dom.refreshButton.disabled = false;
  }
}

async function ensureNarrativeForSelectedHorizon() {
  if (!hasPermission("workbench.view")) return;
  const horizon = state.selectedHorizon;
  if (state.narrativeCache[horizon]) {
    mergeNarrativePayload(state.narrativeCache[horizon]);
    renderResearch();
    return;
  }

  const token = ++state.narrativeToken;
  setChip(dom.narrativeStatus, `模型解释生成中 · ${horizon}`, "loading");
  try {
    const payload = await fetchJson("/api/v1/dashboard/shandong-gasoline-92/narrative", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        horizon,
        scenario_text: dom.scenarioInput.value.trim() || null,
        use_llm_explainer: true,
        enable_refined_news: dom.newsToggle.checked,
        enable_event_risk: dom.eventToggle.checked,
      }),
      timeoutMs: 90000,
    });
    if (token !== state.narrativeToken) return;
    mergeNarrativePayload(payload);
    renderResearch();
    setChip(dom.narrativeStatus, `模型解释已更新 · ${horizon}`);
  } catch (error) {
    console.error(error);
    setChip(dom.narrativeStatus, "模型解释失败，保留规则结果", "error");
  }
}

async function sendChatPrediction(prefill = "") {
  if (!hasPermission("chat.use")) {
    setGlobalStatus("当前账号未开通模型对话权限", "error");
    return;
  }
  const message = (prefill || dom.chatInput.value).trim();
  if (!message) return;

  const userId = `user-${Date.now()}`;
  const assistantId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  appendChatMessage({
    id: userId,
    role: "user",
    text: message,
    meta: `${state.selectedHorizon} / ${formatDate(state.dashboard?.as_of_date)}`,
  });
  appendChatMessage({
    id: assistantId,
    role: "assistant",
    text: "",
    meta: "推理中",
    loading: true,
  });
  dom.chatInput.value = "";
  dom.chatSubmit.disabled = true;

  try {
    const payload = await fetchJson("/api/v1/chat/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        horizon: state.selectedHorizon,
        conversation_id: state.currentChatSessionId,
        use_llm_explainer: true,
        enable_refined_news: dom.newsToggle.checked,
        enable_event_risk: dom.eventToggle.checked,
      }),
    });
    await streamAssistantMessage(assistantId, payload.answer, payload);
  } catch (error) {
    console.error(error);
    const msg = state.chatMessages.find((item) => item.id === assistantId);
    if (msg) {
      msg.loading = false;
      msg.text = `对话预测失败：${error.message || error}`;
      msg.meta = "错误";
    }
    renderChatLog();
    persistCurrentChatSession();
  } finally {
    dom.chatSubmit.disabled = false;
  }
}

async function loadAgentHistory(agentName) {
  if (!hasPermission("agents.view")) return;
  try {
    state.agentHistory = await fetchJson(`/api/v1/agents/${encodeURIComponent(agentName)}/outputs?limit=10`);
    renderAgentHistory();
  } catch (error) {
    console.error(error);
    dom.agentHistoryList.innerHTML = emptyState(`单体轨迹加载失败：${error.message || error}`);
    setChip(dom.agentHistoryMeta, "轨迹加载失败", "error");
  }
}

async function loadRunDetail(runId) {
  if (!hasPermission("agents.view")) return;
  try {
    state.selectedRunId = runId;
    renderRunStrip();
    state.selectedRunDetail = await fetchJson(`/api/v1/agents/runs/${encodeURIComponent(runId)}`);
    const outputs = state.selectedRunDetail.agent_outputs || [];
    if (!state.selectedTraceAgent || !outputs.some((item) => item.agent_name === state.selectedTraceAgent)) {
      state.selectedTraceAgent = outputs[0]?.agent_name || null;
    }
    renderRunDetail();
    if (state.selectedTraceAgent) {
      await loadAgentHistory(state.selectedTraceAgent);
    } else {
      dom.agentHistoryList.innerHTML = emptyState("该运行没有单体输出");
    }
  } catch (error) {
    console.error(error);
    dom.runDetail.innerHTML = emptyState(`运行详情加载失败：${error.message || error}`);
  }
}

async function loadAgentWorkspace() {
  if (!hasPermission("agents.view")) return;
  setGlobalStatus("智能体管理加载中", "loading");
  setChip(dom.agentStatusChip, "加载中", "loading");
  dom.agentRefresh.disabled = true;
  try {
    const [overview, graph, runs, optimization] = await Promise.all([
      fetchJson("/api/v1/agents/overview"),
      fetchJson("/api/v1/agents/graph"),
      fetchJson("/api/v1/agents/runs?limit=24"),
      fetchJson("/api/v1/agents/optimization/state"),
    ]);
    state.agentOverview = overview;
    state.agentGraph = graph;
    state.agentRuns = runs.items || [];
    state.optimizationState = optimization;

    renderAgentOverview();
    renderAgentGraph();
    renderScopeBlocks(dom.scopeControls, optimization.scopes);
    renderScopeBlocks(dom.optimizationScopeControls, optimization.scopes);
    renderRunStrip();
    renderProposalPanel();

    const keepSelection = state.agentRuns.some((item) => item.run_id === state.selectedRunId);
    if (state.agentRuns.length) {
      await loadRunDetail(keepSelection ? state.selectedRunId : state.agentRuns[0].run_id);
    } else {
      state.selectedRunDetail = null;
      state.agentHistory = null;
      dom.agentHistoryTabs.innerHTML = "";
      renderRunDetail();
      setChip(dom.agentHistoryMeta, "暂无轨迹");
      dom.agentHistoryList.innerHTML = emptyState("暂无历史输出");
    }

    setChip(dom.agentStatusChip, `已更新 / ${state.agentRuns.length} 条运行`);
    setGlobalStatus("智能体管理已更新");
  } catch (error) {
    console.error(error);
    dom.agentOverviewGrid.innerHTML = emptyState(`智能体总览加载失败：${error.message || error}`);
    dom.agentGraphNodes.innerHTML = emptyState("关系图加载失败");
    dom.scopeControls.innerHTML = emptyState("权重与启停加载失败");
    dom.optimizationScopeControls.innerHTML = emptyState("权重与启停加载失败");
    dom.runList.innerHTML = emptyState("运行记录加载失败");
    dom.runDetail.innerHTML = emptyState("运行详情加载失败");
    dom.proposalPanel.innerHTML = emptyState("自优化提案加载失败");
    setChip(dom.agentStatusChip, "加载失败", "error");
    setGlobalStatus("智能体管理加载失败", "error");
    setProposalStatus("自优化提案加载失败", "error");
  } finally {
    dom.agentRefresh.disabled = false;
  }
}

async function generateProposal() {
  if (!hasPermission("agents.view")) return;
  dom.proposalGenerate.disabled = true;
  setGlobalStatus("自优化提案生成中", "loading");
  setProposalStatus("正在读取最近预测运行与回测结果", "loading");
  try {
    const payload = await fetchJson("/api/v1/agents/optimization/proposals/generate", { method: "POST" });
    state.optimizationState = payload.state;
    renderProposalPanel();
    renderScopeBlocks(dom.scopeControls, payload.state.scopes);
    renderScopeBlocks(dom.optimizationScopeControls, payload.state.scopes);
    setGlobalStatus("自优化提案已生成");
    const count = payload.proposal?.suggestions?.length ?? 0;
    setProposalStatus(count ? `已生成 ${count} 条建议，等待人工确认` : "已生成提案，本次暂无新调整", "success");
  } catch (error) {
    console.error(error);
    setGlobalStatus("自优化提案生成失败", "error");
    setProposalStatus(`生成失败：${error.message || "接口异常"}`, "error");
  } finally {
    dom.proposalGenerate.disabled = false;
  }
}

async function confirmProposal(approved) {
  if (!hasPermission("agents.view")) return;
  const proposal = currentProposal();
  if (!proposal || proposal.status !== "pending") return;

  dom.proposalApprove.disabled = true;
  dom.proposalReject.disabled = true;
  setGlobalStatus(approved ? "正在应用提案" : "正在驳回提案", "loading");
  setProposalStatus(approved ? "正在应用到下一轮预测权重" : "正在记录驳回结果", "loading");
  try {
    const payload = await fetchJson(
      `/api/v1/agents/optimization/proposals/${encodeURIComponent(proposal.proposal_id)}/confirm`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved,
          reviewer: "workbench_manual_review",
          note: approved ? "前端手动确认应用" : "前端手动驳回",
        }),
      }
    );
    state.optimizationState = payload.state;
    renderProposalPanel();
    renderScopeBlocks(dom.scopeControls, payload.state.scopes);
    renderScopeBlocks(dom.optimizationScopeControls, payload.state.scopes);
    await loadAgentWorkspace();
    setGlobalStatus(approved ? "提案已应用" : "提案已驳回");
    setProposalStatus(approved ? "提案已应用，下一轮预测生效" : "提案已驳回，当前权重不变", approved ? "success" : "");
  } catch (error) {
    console.error(error);
    setGlobalStatus("提案处理失败", "error");
    setProposalStatus(`处理失败：${error.message || "接口异常"}`, "error");
    renderProposalPanel();
  }
}

function syncHash() {
  const hash = state.currentView === "agents" ? `agents:${state.currentAgentSubView}` : state.currentView;
  if (window.location.hash.replace("#", "") !== hash) {
    window.location.hash = hash;
  }
}

function activateMainView(view) {
  const nextView = hasViewAccess(view) ? view : firstAccessibleView(view);
  state.currentView = nextView;
  dom.mainTabs.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.viewTarget === nextView);
  });
  dom.views.forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.view === nextView);
  });
  dom.agentsSubnav.hidden = nextView !== "agents";
  syncHash();

  if (nextView === "policy" && !state.policyFeed) {
    loadPolicyFeed();
  }
  if (nextView === "accuracy" && !state.predictionAccuracy) {
    loadPredictionAccuracy();
  }
  if (nextView === "agents") {
    loadAgentWorkspace();
  }
  if (nextView === "profile") {
    renderProfileView();
  }
  if (nextView === "permissions") {
    loadPermissionWorkspace();
  }
}

function activateAgentSubView(subview) {
  state.currentAgentSubView = subview;
  dom.agentSubTabs.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.agentSubview === subview);
  });
  dom.agentSubViews.forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.agentSubview === subview);
  });
  syncHash();
}

function parseHash() {
  const raw = window.location.hash.replace("#", "").trim();
  if (!raw) return { view: "home", subview: "overview" };
  const [view, subview] = raw.split(":");
  return {
    view: ["home", "clearview", "accuracy", "policy", "agents", "profile", "permissions"].includes(view) ? view : "home",
    subview: subview === "optimization" ? "optimization" : "overview",
  };
}

function startSnapshotPolling() {
  if (state.snapshotTimer) clearInterval(state.snapshotTimer);
  state.snapshotTimer = setInterval(() => {
    loadMarketSnapshot();
  }, 15000);
}

function syncLiveBrentNodes() {
  const liveValue = formatNumber(state.marketSnapshot?.latest_prices?.brent_active_settlement);
  document.querySelectorAll("[data-brent-live-value]").forEach((node) => {
    node.textContent = liveValue;
  });
  const liveTime = formatTime(state.brentLive?.generated_at || state.brentLive?.metadata?.wind?.time);
  document.querySelectorAll("[data-brent-live-time]").forEach((node) => {
    node.textContent = `刷新时间 ${liveTime}`;
  });
}

function brentWindDetailText() {
  const wind = state.brentLive?.metadata?.wind;
  if (!wind) return "";
  const pieces = [];
  if (wind.rt_chg != null) pieces.push(`涨跌 ${formatNumber(wind.rt_chg)}`);
  if (wind.rt_pct_chg != null) pieces.push(`涨幅 ${valueToPercent(wind.rt_pct_chg)}`);
  if (wind.time) pieces.push(formatDateTime(wind.time));
  return pieces.join(" / ");
}

function renderSnapshotMetricCard({
  label,
  value,
  unit,
  meta,
  sub,
  featured = false,
  flash = false,
  live = false,
  priceKey = "",
  liveValue = false,
  liveTime = false,
  dateValue = null,
  timeValue = null,
}) {
  const className = `metric-card${featured ? " featured" : ""}${flash ? " is-flash" : ""}`;
  const liveValueAttr = liveValue ? ' data-brent-live-value="snapshot"' : "";
  const timestampHtml = timeValue || dateValue ? renderPriceTimestamp(dateValue, timeValue, { liveTime }) : "";
  const tooltipLines = [
    label,
    `${value}${unit ? ` ${unit}` : ""}`,
    sub,
    meta,
    dateValue ? `价格日期 ${formatDate(dateValue)}` : "",
    timeValue ? `刷新时间 ${formatTime(timeValue)}` : "",
  ].filter((item) => String(item || "").trim());
  const tooltipAttr = escapeAttr(tooltipLines.join("\n"));
  return `
    <article class="${className}" tabindex="0" data-metric-tooltip="${tooltipAttr}"${priceKey ? ` data-price-key="${escapeHtml(priceKey)}"` : ""}>
        <div class="metric-top">
          <div class="metric-label">${escapeHtml(label)}</div>
        ${live ? '<div class="live-pill">秒级</div>' : ""}
      </div>
      <div class="metric-value"${liveValueAttr}>${escapeHtml(value)}</div>
      <div class="metric-sub">
        <span>${escapeHtml(unit || "")}</span>
        <span>${escapeHtml(sub || "")}</span>
      </div>
      ${meta ? `<div class="metric-live-detail">${escapeHtml(meta)}</div>` : ""}
      ${timestampHtml}
    </article>`;
}

function oilchemMetricDate(record) {
  return formatDate(record?.observation_date || record?.period_end || record?.period_start);
}

function buildOilchemMetricCards(snapshot) {
  const metrics = snapshot.metadata?.oilchem_metrics || {};
  const ratio = metrics.production_sales_ratio;
  const capacity = metrics.capacity_utilization;
  const profit = metrics.refining_profit;
  const maintenance = metrics.maintenance_plan;
  const inventory = metrics.inventory;
  const cards = [
    ratio && renderSnapshotMetricCard({
      label: "汽油产销率",
      value: formatNumberTrim(ratio.gasoline_ratio, 2),
      unit: "%",
      sub: `日期 ${oilchemMetricDate(ratio)}`,
      meta: ratio.gasoline_change_pct != null ? `环比 ${formatNumberTrim(ratio.gasoline_change_pct, 2)}%` : "隆众日度",
    }),
    capacity && renderSnapshotMetricCard({
      label: "地炼开工率",
      value: formatNumberTrim(capacity.capacity_utilization, 2),
      unit: "%",
      sub: `日期 ${oilchemMetricDate(capacity)}`,
      meta: capacity.capacity_utilization_wow_pct != null
        ? `环比 ${formatNumberTrim(capacity.capacity_utilization_wow_pct, 2)}%`
        : "隆众周度",
    }),
    profit && renderSnapshotMetricCard({
      label: "炼油利润",
      value: formatNumberTrim(profit.refining_profit, 0),
      unit: "元/吨",
      sub: `日期 ${oilchemMetricDate(profit)}`,
      meta: profit.refining_profit_wow_pct != null
        ? `环比 ${formatNumberTrim(profit.refining_profit_wow_pct, 2)}%`
        : "隆众周度",
    }),
    inventory && renderSnapshotMetricCard({
      label: "汽油库存",
      value: formatNumberTrim(inventory.gasoline_inventory, 2),
      unit: "万吨",
      sub: `日期 ${oilchemMetricDate(inventory)}`,
      meta: inventory.gasoline_inventory_change_mom != null
        ? `环比 ${formatNumberTrim(inventory.gasoline_inventory_change_mom, 2)} 万吨`
        : "隆众库存",
    }),
    inventory && renderSnapshotMetricCard({
      label: "汽油库容率",
      value: formatNumberTrim(inventory.gasoline_inventory_capacity_rate, 2),
      unit: "%",
      sub: `日期 ${formatDate(inventory.gasoline_inventory_capacity_rate_date || inventory.observation_date || inventory.period_end || inventory.period_start)}`,
      meta: inventory.total_inventory != null
        ? `汽柴油总量 ${formatNumberTrim(inventory.total_inventory, 2)} 万吨`
        : "隆众库存",
    }),
    maintenance && renderSnapshotMetricCard({
      label: "检修产能",
      value: formatNumberTrim(maintenance.active_capacity, 0),
      unit: "万吨/年",
      sub: `日期 ${oilchemMetricDate(maintenance)}`,
      meta: `当前 ${formatNumberTrim(maintenance.active_count, 0)} 套装置`,
    }),
  ].filter(Boolean);

  if (cards.length) return cards;
  const errors = metrics.errors || {};
  const firstError = Object.values(errors)[0];
  return [
    renderSnapshotMetricCard({
      label: "隆众经营数据",
      value: "待抓取",
      unit: "",
      sub: "产销率 / 库存 / 开工率",
      meta: firstError ? String(firstError).slice(0, 80) : "等待日度任务或登录态刷新",
    }),
  ];
}

async function loadBrentLive() {
  if (!hasPermission("workbench.view")) return;
  try {
    const payload = await fetchJson("/api/v1/market/brent-live");
    const previousPrices = state.marketSnapshot?.latest_prices || {};
    state.brentLive = payload;
    if (!state.marketSnapshot) {
      state.marketSnapshot = {
        as_of_date: payload.as_of_date,
        generated_at: payload.generated_at,
        latest_prices: {
          brent_active_settlement: payload.latest_price,
        },
        metadata: payload.metadata || {},
      };
    } else {
      state.marketSnapshot = {
        ...state.marketSnapshot,
        __previousPrices: previousPrices,
        latest_prices: {
          ...(state.marketSnapshot.latest_prices || {}),
          brent_active_settlement: payload.latest_price,
        },
        metadata: {
          ...(state.marketSnapshot.metadata || {}),
          brent_live_mode: payload.metadata?.market_data_mode,
          brent_live_reason: payload.metadata?.market_data_reason,
        },
      };
    }
    renderMarketSnapshot();
  } catch (error) {
    console.error(error);
  }
}

function startBrentPolling() {
  if (state.brentTimer) clearInterval(state.brentTimer);
  state.brentTimer = setInterval(() => {
    loadBrentLive();
  }, 1000);
}

function startPolicyPolling() {
  if (state.policyTimer) clearInterval(state.policyTimer);
  state.policyTimer = setInterval(() => {
    if (!hasPermission("policy.view") || state.policyManualDate) return;
    loadPolicyFeed({ forceLatest: true });
  }, 30000);
}

function renderMarketSnapshot() {
  const snapshot = state.marketSnapshot;
  if (!snapshot) {
    dom.priceSnapshot.innerHTML = emptyState("价格快照加载中");
    return;
  }

  const previous = snapshot.__previousPrices || {};

  const priceCards = PRICE_LABELS.filter(([key]) =>
    ["brent_active_settlement", "sd_gas92_market", "cn_gas92_market"].includes(key)
  ).map(([key, label], index) => {
    const value = snapshot.latest_prices?.[key];
    const changed = previous[key] != null && value != null && Number(previous[key]) !== Number(value);
    const unit = key === "brent_active_settlement" ? "美元/桶" : "元/吨";
    const reason =
      key === "brent_active_settlement"
        ? marketReasonLabel(state.brentLive?.metadata?.market_data_reason)
        : marketReasonLabel(snapshot.metadata?.market_data_reason);
    const quality = key === "brent_active_settlement"
      ? state.brentLive?.metadata?.quality?.[key] || snapshot.metadata?.quality?.[key]
      : snapshot.metadata?.quality?.[key];
    const qualityText = quality
      ? `${quality.source || "数据源"} / ${quality.quality_flag || "ok"} / ${quality.confidence || "中"}`
      : reason;
    const brentDetail = key === "brent_active_settlement" ? brentWindDetailText() : "";
    return renderSnapshotMetricCard({
      label,
      value: formatNumber(value),
      unit,
      sub: `日期 ${formatDate(priceSnapshotDate(key, snapshot))}`,
      meta: "",
      featured: index === 0,
      flash: changed,
      live: key === "brent_active_settlement",
      priceKey: key,
      liveValue: key === "brent_active_settlement",
      liveTime: key === "brent_active_settlement",
      dateValue: priceSnapshotDate(key, snapshot),
      timeValue: priceSnapshotTime(key, snapshot),
    });
  });

  dom.priceSnapshot.innerHTML = [...priceCards, ...buildOilchemMetricCards(snapshot)].join("");

  syncLiveBrentNodes();
}

function renderMorningBriefing() {
  if (!state.latestBriefing) {
    dom.briefingContent.innerHTML = emptyState("暂无晨报");
    applyBriefingCollapseState();
    return;
  }

  const payload = state.latestBriefing;
  const sections = parseBriefingSections(payload.content_markdown);
  const outright = payload.outright_predictions || [];
  const regional = payload.regional_spread_predictions || [];
  const lead = outright.find((item) => item.horizon === "D1") || outright[0] || null;
  const leadBusiness = businessDirectionInfo(lead);
  const snapshot = {
    ...(payload.metadata?.snapshot_prices || fallbackBriefingSnapshotPrices(sections)),
  };
  if (state.marketSnapshot?.latest_prices?.brent_active_settlement != null) {
    snapshot.brent_active_settlement = state.marketSnapshot.latest_prices.brent_active_settlement;
  }
  const policyHighlights = buildBriefingPolicyHighlights(payload, sections);
  const eventHighlights = buildBriefingEventHighlights(payload, sections);
  const adviceItems = (lead?.operating_advice || []).slice(0, 3);
  const summaryText = normalizeNarrativeText(lead?.explanation || "暂无晨会摘要");
  const marketModeText =
    lead?.degrade_flag || payload.metadata?.market_data_reason
      ? `数据口径 ${marketReasonLabel(lead?.degrade_reason || payload.metadata?.market_data_reason)}`
      : "数据口径 实时";
  const windowText =
    lead?.raw_context?.days_to_next_window != null
      ? `距下轮调价窗口 ${formatNumberTrim(lead.raw_context.days_to_next_window, 0)} 天`
      : "调价窗口待核对";
  const briefingPriceDate = payload.metadata?.snapshot_price_date || payload.as_of_date;
  const briefingPriceTime = payload.metadata?.snapshot_price_time || payload.generated_at;
  const snapshotCards = [
    [
      "布伦特",
      snapshot.brent_active_settlement,
      "美元/桶",
      true,
      state.brentLive?.as_of_date || state.marketSnapshot?.as_of_date || briefingPriceDate,
      state.brentLive?.generated_at || state.brentLive?.metadata?.wind?.time || state.marketSnapshot?.generated_at || briefingPriceTime,
    ],
    ["山东 92#", snapshot.sd_gas92_market ?? lead?.raw_context?.current_price, "元/吨", false, briefingPriceDate, briefingPriceTime],
    ["全国 92#", snapshot.cn_gas92_market, "元/吨", false, briefingPriceDate, briefingPriceTime],
    ["华东 92#", snapshot.east_china_gas92_market, "元/吨", false, briefingPriceDate, briefingPriceTime],
  ].filter(([, value]) => value != null);
  const mixedHighlights = [
    ...policyHighlights.map((item) => ({
      type: "政策",
      title: item.impact || item.title,
      meta: item.time || "-",
      action: item.action || "跟踪调价窗口与限价兑现",
    })),
    ...eventHighlights.map((item) => ({
      type: "事件",
      title: item.impact || item.title,
      meta: `${displaySourceLabel(item.source || "事件快讯")} / ${item.time || "-"}`,
      action: item.action || "跟踪事件对Brent和现货报价的传导",
    })),
  ].slice(0, 6);

  setChip(dom.briefingMeta, `${formatDate(payload.as_of_date)} / ${formatDateTime(payload.generated_at)}`);
  dom.briefingContent.innerHTML = `
    <div class="briefing-sheet">
      <section class="briefing-hero">
        <div class="briefing-hero-main">
          <div class="briefing-kicker">晨会快览 / ${formatDate(payload.as_of_date)}</div>
          <div class="briefing-title-row">
            <div>
              <h3>${escapeHtml((payload.title || "").replace("|", "/"))}</h3>
              <p class="briefing-summary">${escapeHtml(summaryText)}</p>
            </div>
            <div class="briefing-direction-chip ${toneClass(leadBusiness.tone)}">${escapeHtml(leadBusiness.label)}</div>
          </div>
          <div class="briefing-hero-metrics">
            <div class="briefing-lead-point">${formatNumber(lead?.point_value)}</div>
            <div class="briefing-lead-range">D1参考中枢 / ${formatNumber(lead?.range_lower)} ~ ${formatNumber(lead?.range_upper)} 元/吨</div>
          </div>
        </div>

        <div class="briefing-hero-side">
          <article class="briefing-side-card">
            <span>主判断</span>
            <strong>${escapeHtml(leadBusiness.label)}</strong>
            <small>${escapeHtml(windowText)}</small>
          </article>
          <article class="briefing-side-card">
            <span>资讯与事件</span>
            <strong>${formatNumberTrim(payload.metadata?.refined_news_count || 0, 0)} / ${formatNumberTrim(payload.metadata?.event_news_count || 0, 0)}</strong>
            <small>成品油资讯 / 事件快讯</small>
          </article>
          <article class="briefing-side-card">
            <span>政策更新</span>
            <strong>${formatNumberTrim(payload.metadata?.policy_count || 0, 0)}</strong>
            <small>${escapeHtml(marketModeText)}</small>
          </article>
        </div>
      </section>

      <section class="briefing-snapshot-strip">
        ${snapshotCards
          .map(
            ([label, value, unit, isLive, priceDate, priceTime]) => `
              <article class="briefing-snapshot-card">
                <span>${escapeHtml(label)}</span>
                <strong${isLive ? ' data-brent-live-value="briefing"' : ""}>${formatNumber(value)}</strong>
                <small>${escapeHtml(unit)}${isLive ? " / 秒级刷新" : ""}</small>
                ${renderPriceTimestamp(priceDate, priceTime, { liveTime: isLive })}
              </article>`
          )
          .join("")}
      </section>

      <div class="briefing-grid">
        <section class="briefing-block briefing-block--wide">
          <div class="briefing-block-head">
            <h4>规则智能体结论</h4>
            <span>分智能体判断</span>
          </div>
          ${renderRuleAgentConclusions(lead?.agent_claims)}
        </section>

        ${
          renderLlmAgentReviews(lead?.agent_claims)
            ? `<section class="briefing-block briefing-block--wide">
                <div class="briefing-block-head">
                  <h4>智能体评审</h4>
                  <span>不参与点位计算</span>
                </div>
                ${renderLlmAgentReviews(lead?.agent_claims)}
              </section>`
            : ""
        }

        <section class="briefing-block briefing-block--wide briefing-block--horizons">
          <div class="briefing-block-head">
            <h4>多周期判断</h4>
            <span>D1与上方主卡为同一预测</span>
          </div>
          <div class="briefing-horizon-grid">
            ${outright
              .map(
                (item) => `
                  <article class="briefing-horizon-card">
                    <div class="briefing-horizon-top">
                      <span>${escapeHtml(item.horizon)} / ${escapeHtml(HORIZON_LABELS[item.horizon] || item.horizon)}</span>
                      <em class="${toneClass(businessDirectionInfo(item).tone)}">${escapeHtml(businessDirectionInfo(item).label)}</em>
                    </div>
                    <strong>${formatNumber(item.point_value)}</strong>
                    <small>区间 ${formatNumber(item.range_lower)} ~ ${formatNumber(item.range_upper)}</small>
                  </article>`
              )
              .join("")}
          </div>
        </section>

        <section class="briefing-block briefing-block--advice">
          <div class="briefing-block-head">
            <h4>经营建议</h4>
            <span>当日执行</span>
          </div>
          <div class="briefing-list">
            ${
              adviceItems.length
                ? adviceItems
                    .map(
                      (item) => `
                        <article class="briefing-list-card">
                          <div class="briefing-list-title">${escapeHtml(normalizeNarrativeText(item.title || "建议"))}</div>
                          <div class="briefing-list-body">${escapeHtml(normalizeNarrativeText(item.action || ""))}</div>
                          <small>${escapeHtml(normalizeNarrativeText(item.rationale || ""))}</small>
                        </article>`
                    )
                    .join("")
                : '<div class="briefing-list-card muted-text">暂无经营建议</div>'
            }
          </div>
        </section>

        <section class="briefing-block briefing-block--risk">
          <div class="briefing-block-head">
            <h4>政策与风险</h4>
            <span>按晨会优先级</span>
          </div>
          <div class="briefing-list">
            ${
              mixedHighlights.length
                ? mixedHighlights
                    .map(
                      (item) => `
                        <article class="briefing-list-card">
                          <div class="briefing-list-meta">${escapeHtml(item.type)}</div>
                          <div class="briefing-list-body">${escapeHtml(normalizeNarrativeText(item.title || ""))}</div>
                          <small>${escapeHtml(normalizeNarrativeText(item.meta || ""))}</small>
                          <small class="briefing-action-line">${escapeHtml(normalizeNarrativeText(item.action || ""))}</small>
                        </article>`
                    )
                    .join("")
                : '<div class="briefing-list-card muted-text">暂无事件提示</div>'
            }
          </div>
        </section>

        <section class="briefing-block briefing-block--wide briefing-block--spreads">
          <div class="briefing-block-head">
            <h4>区域价差观察</h4>
            <span>D1 / 当前可视重点</span>
          </div>
          <div class="briefing-spread-grid">
            ${regional.length
              ? regional
                  .slice(0, 6)
                  .map((item) => {
                    const actualSpread = regionalActualSpread(item);
                    return `
                      <article class="briefing-spread-card">
                        <div class="briefing-spread-head">
                          <span>山东 - ${escapeHtml(item.raw_context?.counter_region_name || item.region_code)}</span>
                          <em class="${toneClass(item.direction_label)}">${escapeHtml(shortDirectionLabel(item.direction_label, true))}</em>
                        </div>
                        <div class="regional-variant-list">${renderRegionalVariantRows(item, { compact: true })}</div>
                        <small>真实价差 ${formatNumber(actualSpread)}</small>
                      </article>`;
                  })
                  .join("")
              : '<div class="briefing-list-card muted-text">暂无经营建议</div>'
          }
          </div>
        </section>
      </div>
    </div>`;

  syncLiveBrentNodes();
  applyBriefingCollapseState();
}

function isAfterBriefingCutoff(now = new Date()) {
  return now.getHours() > 10 || (now.getHours() === 10 && now.getMinutes() >= 30);
}

function applyBriefingCollapseState() {
  if (!state.briefingManualOverride) {
    state.briefingCollapsed = isAfterBriefingCutoff();
  }
  dom.briefingPanel?.classList.toggle("is-collapsed", state.briefingCollapsed);
  if (dom.briefingToggle) {
    dom.briefingToggle.textContent = state.briefingCollapsed ? "展开晨报" : "收起晨报";
    dom.briefingToggle.setAttribute("aria-expanded", state.briefingCollapsed ? "false" : "true");
  }
}

function toggleBriefingCollapsed() {
  state.briefingManualOverride = true;
  state.briefingCollapsed = !state.briefingCollapsed;
  applyBriefingCollapseState();
}

function startBriefingCollapseTimer() {
  if (state.briefingCollapseTimer) clearInterval(state.briefingCollapseTimer);
  state.briefingCollapseTimer = setInterval(() => {
    applyBriefingCollapseState();
  }, 60 * 1000);
}

function bindEvents() {
  dom.navLogo?.addEventListener("click", () => activateMainView("home"));

  dom.alertList?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-alert-action]");
    if (!button) return;
    const alertId = button.dataset.alertId;
    const status = button.dataset.alertAction;
    if (!alertId || !status) return;
    button.disabled = true;
    if (status === "tracking") {
      await trackAlertAndRefreshResearch(alertId, button);
      return;
    }
    try {
      await fetchJson(`/api/v1/alerts/${encodeURIComponent(alertId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      await loadPolicyFeed();
    } catch (error) {
      console.error(error);
      button.disabled = false;
    }
  });

  dom.priceHistoryRange?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-history-days]");
    if (!button) return;
    state.priceHistoryDays = Number(button.dataset.historyDays || 30);
    dom.priceHistoryRange.querySelectorAll("[data-history-days]").forEach((item) => {
      item.classList.toggle("is-active", item === button);
    });
    await loadPriceHistory();
  });

  dom.priceHistorySeries?.addEventListener("change", async (event) => {
    const input = event.target.closest("input[type='checkbox']");
    if (!input) return;
    const nextSeries = Array.from(dom.priceHistorySeries.querySelectorAll("input[type='checkbox']:checked"))
      .map((item) => item.value);
    if (!nextSeries.length) {
      input.checked = true;
      return;
    }
    state.priceHistorySeries = nextSeries;
    await loadPriceHistory();
  });

  dom.oilchemInventoryRefresh?.addEventListener("click", loadOilchemInventory);
  dom.oilchemInventoryExport?.addEventListener("click", exportOilchemInventory);

  dom.accuracyRefresh?.addEventListener("click", loadPredictionAccuracy);

  dom.mainTabs.forEach((button) => {
    button.addEventListener("click", () => activateMainView(button.dataset.viewTarget));
  });

  dom.themeButtons.forEach((button) => {
    button.addEventListener("click", () => applyTheme(button.dataset.themeValue));
  });

  dom.accountEntry?.addEventListener("click", () => activateMainView(firstAccessibleView("profile")));
  dom.logoutButton?.addEventListener("click", logoutCurrentUser);

  dom.agentSubTabs.forEach((button) => {
    button.addEventListener("click", () => activateAgentSubView(button.dataset.agentSubview));
  });

  dom.sortTabs.forEach((button) => {
    button.addEventListener("click", async () => {
      state.policySortMode = button.dataset.sortMode;
      await loadPolicyFeed();
    });
  });

  dom.researchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadDashboard();
  });


  dom.spreadGrid?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-spread-detail-index]");
    if (!button) return;
    showSpreadDetail(button.dataset.spreadDetailIndex);
  });

  dom.spreadDetailClose?.addEventListener("click", closeSpreadDetail);
  dom.spreadDetailDialog?.addEventListener("click", (event) => {
    if (event.target === dom.spreadDetailDialog) closeSpreadDetail();
  });

  document.querySelector("[data-freight-save-all]")?.addEventListener("click", saveAllFreightSettings);

  dom.freightSettingsPanel?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-freight-reload]");
    if (!button) return;
    button.disabled = true;
    state.freightSettings = [];
    await loadFreightSettings();
  });

  dom.narrativeToggle.addEventListener("change", async () => {
    if (!dom.narrativeToggle.checked) {
      resetToBaselineDashboard();
      renderResearch();
      setChip(dom.narrativeStatus, "规则解释");
      return;
    }
    await ensureNarrativeForSelectedHorizon();
  });

  dom.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendChatPrediction();
  });

  dom.quickAskButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      await sendChatPrediction(button.dataset.quickAsk || "");
    });
  });

  dom.chatReset?.addEventListener("click", () => {
    startNewChatSession();
  });

  dom.chatHistoryToggle?.addEventListener("click", () => {
    state.chatHistoryOpen = !state.chatHistoryOpen;
    renderChatHistory();
  });

  dom.chatHistoryClear?.addEventListener("click", () => {
    state.chatSessions = [];
    state.currentChatSessionId = null;
    saveChatHistory();
    renderChatHistory();
  });

  dom.briefingToggle?.addEventListener("click", toggleBriefingCollapsed);
  dom.briefingGenerate.addEventListener("click", generateBriefing);

  dom.newsDateSelect.addEventListener("change", () => {
    state.policyManualDate = true;
    loadPolicyFeed();
  });
  dom.policyDateSelect.addEventListener("change", () => {
    state.policyManualDate = true;
    loadPolicyFeed();
  });

  dom.agentRefresh.addEventListener("click", loadAgentWorkspace);
  dom.proposalGenerate.addEventListener("click", generateProposal);
  dom.proposalApprove.addEventListener("click", async () => confirmProposal(true));
  dom.proposalReject.addEventListener("click", async () => confirmProposal(false));

  dom.profileForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitProfileUpdate();
  });

  dom.createUserForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitCreateUser();
  });

  dom.userEditForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitUpdateUser();
  });

  window.addEventListener("hashchange", () => {
    const { view, subview } = parseHash();
    if (state.currentView !== view) activateMainView(view);
    if (view === "agents" && state.currentAgentSubView !== subview) activateAgentSubView(subview);
  });
}

async function init() {
  setupThemeControls();
  applyTheme(resolveStoredTheme());
  await loadCurrentUser();
  loadChatHistory();
  bindEvents();
  const { view, subview } = parseHash();
  const accessibleView = firstAccessibleView(view);
  activateMainView(accessibleView);
  activateAgentSubView(subview);

  renderChatLog();
  renderChatHistory();
  renderMarketSnapshot();
  renderResearch();
  renderMorningBriefing();
  startBriefingCollapseTimer();
  renderAlerts();
  renderPriceHistory();
  ensureOilchemInventoryDateInputs();
  renderOilchemInventory();
  renderPredictionAccuracy();
  renderPolicyPage();
  renderProfileView();

  if (hasPermission("workbench.view")) {
    startSnapshotPolling();
    startBrentPolling();
  }
  if (hasPermission("policy.view")) {
    startPolicyPolling();
  }

  const initialTasks = [];
  if (hasPermission("workbench.view")) {
    initialTasks.push(
      loadMarketSnapshot(),
      loadBrentLive(),
      loadLatestBriefing(),
      loadPriceHistory(),
      loadOilchemInventory(),
      loadPredictionAccuracy(),
      loadFreightSettings(),
    );
  }
  if (hasPermission("policy.view")) {
    initialTasks.push(loadPolicyFeed());
  }
  await Promise.allSettled(initialTasks);
  if (accessibleView !== "agents" && hasPermission("workbench.view")) {
    await loadLatestDashboard();
  }
}

init();
