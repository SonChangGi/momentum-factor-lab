(() => {
  "use strict";

  const MANIFEST_URL = "data/grid/v1/manifest.json";
  const MANIFEST_SCHEMA_VERSION = 1;
  const MANIFEST_CONTRACT = "momentum-static-result-grid";
  const MANIFEST_GRID_VERSION = "v1";
  const RESULT_SCHEMA_VERSION = 4;
  const RESULT_IDENTITY_VERSION = "momentum-result-identity-v1";
  const CANONICAL_JSON_VERSION = "rfc8785-jcs-v1";
  const RESEARCH_INPUTS_VERSION = "research-inputs-v1";
  const ABSOLUTE_GUARDRAIL_VERSION = "absolute-factor-policy-v1";
  const LOCAL_API_BASE_URL = "http://127.0.0.1:8765";
  const LOCAL_API_POLL_INTERVAL_MS = 1000;
  const EXPECTED_INDEPENDENT_FACTOR_COUNT = 61;
  const EXPECTED_POLICY_COUNT = 4;
  const EXPECTED_INDEPENDENT_PAIR_COUNT = 244;
  const EXPECTED_ALIAS_FACTOR_COUNT = 3;
  const EXPECTED_ALIAS_PAIR_COUNT = 12;
  const LIVE_INPUT_HASH_FIELDS = [
    "prices",
    "volumes",
    "dollarVolumes",
    "rawCloses",
    "requestedSymbols",
    "returnedSymbols",
    "universeRecords",
    "priceSources",
    "dataSources",
  ];
  const PRESET_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
  const LOCAL_API_REQUIRED = (
    "이 입력 조합은 정적 grid에 사전 계산되지 않았습니다. "
    + "임의 조건은 로컬 Python backend/API로 새로 분석해야 합니다."
  );

  const INPUT_FIELDS = [
    { key: "rebalance_frequency", id: "input-rebalance-frequency", kind: "string" },
    { key: "evaluation_window_days", id: "input-evaluation-window-days", kind: "integer" },
    { key: "top_n", id: "input-top-n", kind: "integer" },
    { key: "max_weight", id: "input-max-weight", kind: "percent" },
    { key: "transaction_cost_bps", id: "input-transaction-cost", kind: "number" },
    { key: "slippage_bps", id: "input-slippage", kind: "number" },
    { key: "min_price", id: "input-min-price", kind: "number" },
    { key: "min_history_days", id: "input-min-history", kind: "integer" },
    { key: "min_avg_dollar_volume", id: "input-min-dollar-volume", kind: "number" },
    { key: "min_avg_volume", id: "input-min-volume", kind: "number" },
    { key: "liquidity_lookback_days", id: "input-liquidity-lookback", kind: "integer" },
    { key: "min_liquidity_observations", id: "input-liquidity-observations", kind: "integer" },
    { key: "max_price_missing_ratio", id: "input-price-missing", kind: "percent" },
    { key: "max_volume_missing_ratio", id: "input-volume-missing", kind: "percent" },
    { key: "max_extreme_daily_return", id: "input-extreme-return", kind: "percent" },
    { key: "selection_min_sharpe", id: "input-selection-min-sharpe", kind: "number" },
    { key: "selection_max_drawdown", id: "input-selection-max-drawdown", kind: "percent" },
    { key: "selection_max_annualized_cost_drag", id: "input-selection-max-cost-drag", kind: "percent" },
    { key: "selection_min_effective_names", id: "input-selection-min-effective-names", kind: "number" },
    { key: "selection_max_target_hhi", id: "input-selection-max-target-hhi", kind: "percent" },
    { key: "selection_max_target_weight", id: "input-selection-max-target-weight", kind: "percent" },
    { key: "selection_max_abs_security_day_contribution", id: "input-selection-max-day-contribution", kind: "percent" },
    { key: "selection_max_security_absolute_contribution_share", id: "input-selection-max-contribution-share", kind: "percent" },
    { key: "selection_max_leave_one_security_cagr_delta", id: "input-selection-max-leave-one-delta", kind: "percent" },
    { key: "selection_extreme_event_action", id: "input-selection-extreme-action", kind: "string" },
    { key: "selection_extreme_event_penalty_points", id: "input-selection-penalty-points", kind: "number" },
  ];

  const RESEARCH_INPUT_PARITY = {
    rebalanceFrequency: "rebalance_frequency",
    evaluationWindowDays: "evaluation_window_days",
    topN: "top_n",
    maxWeight: "max_weight",
    transactionCostBps: "transaction_cost_bps",
    slippageBps: "slippage_bps",
    minHistoryDays: "min_history_days",
    minPrice: "min_price",
    minAvgDollarVolume: "min_avg_dollar_volume",
    minAvgVolume: "min_avg_volume",
    liquidityLookbackDays: "liquidity_lookback_days",
    minLiquidityObservations: "min_liquidity_observations",
    maxPriceMissingRatio: "max_price_missing_ratio",
    maxVolumeMissingRatio: "max_volume_missing_ratio",
    maxExtremeDailyReturn: "max_extreme_daily_return",
    selectionMinSharpe: "selection_min_sharpe",
    selectionMaxDrawdown: "selection_max_drawdown",
    selectionMaxAnnualizedCostDrag: "selection_max_annualized_cost_drag",
    selectionMinEffectiveNames: "selection_min_effective_names",
    selectionMaxTargetHhi: "selection_max_target_hhi",
    selectionMaxTargetWeight: "selection_max_target_weight",
    selectionMaxAbsSecurityDayContribution: "selection_max_abs_security_day_contribution",
    selectionMaxSecurityAbsoluteContributionShare: "selection_max_security_absolute_contribution_share",
    selectionMaxLeaveOneSecurityCagrDelta: "selection_max_leave_one_security_cagr_delta",
    selectionExtremeEventAction: "selection_extreme_event_action",
    selectionExtremeEventPenaltyPoints: "selection_extreme_event_penalty_points",
  };

  const COMPONENT_LABELS = {
    sortino: "Sortino",
    calmar: "Calmar",
    max_drawdown: "MDD",
    cagr: "CAGR",
    sharpe: "Sharpe",
    stability: "기간 안정성",
  };

  const state = {
    manifest: null,
    manifestUrl: null,
    entry: null,
    payload: null,
    summary: null,
    detailPairKey: null,
    category: "all",
    search: "",
    loadToken: 0,
    controlsBound: false,
    resultSource: null,
  };

  const hasDom = typeof document !== "undefined";
  const $ = (selector) => document.querySelector(selector);
  const isRecord = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  const cloneJson = (value) => JSON.parse(JSON.stringify(value));
  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
  const finite = (value) => value !== null
    && value !== undefined
    && value !== ""
    && typeof value !== "boolean"
    && Number.isFinite(Number(value));
  const integer = (value) => finite(value) && Number.isInteger(Number(value));
  const validSha256 = (value) => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
  const fmtNumber = (value, digits = 2) => finite(value)
    ? Number(value).toLocaleString("ko-KR", { maximumFractionDigits: digits })
    : "—";
  const fmtCount = (value) => integer(value) ? Number(value).toLocaleString("ko-KR") : "—";
  const fmtPercent = (value, digits = 1) => finite(value)
    ? `${(Number(value) * 100).toLocaleString("ko-KR", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })}%`
    : "—";
  const fmtMoney = (value) => finite(value)
    ? Number(value).toLocaleString("ko-KR", {
      notation: Math.abs(Number(value)) >= 1e6 ? "compact" : "standard",
      maximumFractionDigits: 1,
    })
    : "—";
  const signClass = (value) => finite(value) && Number(value) < 0 ? "negative" : "positive";

  function canonicalValue(value) {
    if (Array.isArray(value)) return value.map(canonicalValue);
    if (!isRecord(value)) return value;
    return Object.keys(value).sort().reduce((result, key) => {
      result[key] = canonicalValue(value[key]);
      return result;
    }, {});
  }

  function canonicalString(value) {
    return JSON.stringify(canonicalValue(value));
  }

  function sameJson(left, right) {
    return canonicalString(left) === canonicalString(right);
  }

  function requireCondition(condition, message) {
    if (!condition) throw new Error(message);
  }

  function validateIdentity(identity, resultKey, label, options = {}) {
    requireCondition(isRecord(identity), `${label} resultIdentity가 없습니다.`);
    requireCondition(identity.identityVersion === RESULT_IDENTITY_VERSION, `${label} identityVersion이 지원되지 않습니다.`);
    requireCondition(identity.keyParts?.identityVersion === RESULT_IDENTITY_VERSION, `${label} keyParts identityVersion이 지원되지 않습니다.`);
    requireCondition(identity.keyParts?.canonicalJsonVersion === CANONICAL_JSON_VERSION, `${label} canonical JSON version이 지원되지 않습니다.`);
    requireCondition(identity.resultKey === resultKey && validSha256(identity.resultKey), `${label} resultKey가 일치하지 않습니다.`);
    requireCondition(isRecord(identity.keyParts), `${label} keyParts가 없습니다.`);
    requireCondition(isRecord(identity.keyParts.normalizedInputs), `${label} normalizedInputs가 없습니다.`);
    const canonicalTransport = identity.canonicalKeyPartsJson;
    if (options.requireCanonicalTransport !== false) {
      requireCondition(typeof canonicalTransport === "string" && canonicalTransport, `${label} canonicalKeyPartsJson이 없습니다.`);
    }
    if (canonicalTransport === undefined && options.requireCanonicalTransport === false) return;
    let canonicalKeyParts;
    try {
      canonicalKeyParts = JSON.parse(canonicalTransport);
    } catch (_error) {
      throw new Error(`${label} canonicalKeyPartsJson이 유효한 JSON이 아닙니다.`);
    }
    requireCondition(sameJson(canonicalKeyParts, identity.keyParts), `${label} canonicalKeyPartsJson이 keyParts와 다릅니다.`);
    requireCondition(canonicalString(identity.keyParts) === canonicalTransport, `${label} canonicalKeyPartsJson이 RFC 8785 JCS encoding이 아닙니다.`);
  }

  function validateManifest(manifest) {
    requireCondition(isRecord(manifest), "정적 grid manifest가 JSON 객체가 아닙니다.");
    requireCondition(manifest.schemaVersion === MANIFEST_SCHEMA_VERSION, "지원하지 않는 manifest schema입니다.");
    requireCondition(manifest.contract === MANIFEST_CONTRACT, "manifest contract가 일치하지 않습니다.");
    requireCondition(manifest.gridVersion === MANIFEST_GRID_VERSION, "manifest gridVersion이 일치하지 않습니다.");
    requireCondition(manifest.bounded === true, "정적 grid가 bounded 계약을 선언하지 않았습니다.");
    requireCondition(integer(manifest.maxEntries) && Number(manifest.maxEntries) >= 1 && Number(manifest.maxEntries) <= 64, "manifest maxEntries가 잘못되었습니다.");
    requireCondition(Array.isArray(manifest.entries) && manifest.entries.length > 0, "manifest entry가 없습니다.");
    requireCondition(manifest.entryCount === manifest.entries.length && manifest.entries.length <= manifest.maxEntries, "manifest entry 수가 일관되지 않습니다.");
    requireCondition(validSha256(manifest.defaultResultKey), "manifest defaultResultKey가 잘못되었습니다.");

    const resultKeys = new Set();
    const inputTuples = new Set();
    const presetIds = new Set();
    let declaredPresetCount = 0;
    manifest.entries.forEach((entry, index) => {
      const label = `manifest.entries[${index}]`;
      requireCondition(isRecord(entry) && validSha256(entry.resultKey), `${label} resultKey가 잘못되었습니다.`);
      requireCondition(!resultKeys.has(entry.resultKey), "manifest에 중복 resultKey가 있습니다.");
      resultKeys.add(entry.resultKey);
      requireCondition(isRecord(entry.normalizedInputs), `${label} normalizedInputs가 없습니다.`);
      validateIdentity(entry.identity, entry.resultKey, label);
      requireCondition(sameJson(entry.normalizedInputs, entry.identity.keyParts.normalizedInputs), `${label} normalizedInputs가 identity와 다릅니다.`);
      const inputTuple = canonicalString(entry.normalizedInputs);
      requireCondition(!inputTuples.has(inputTuple), "manifest에 중복 입력 tuple이 있습니다.");
      inputTuples.add(inputTuple);
      if (Object.prototype.hasOwnProperty.call(entry, "presetId")) {
        requireCondition(
          typeof entry.presetId === "string" && PRESET_ID_PATTERN.test(entry.presetId),
          `${label} presetId가 잘못되었습니다.`,
        );
        requireCondition(!presetIds.has(entry.presetId), "manifest에 중복 presetId가 있습니다.");
        presetIds.add(entry.presetId);
        declaredPresetCount += 1;
      }
      requireCondition(entry.detail?.path === `results/${entry.resultKey}.json`, `${label} detail path가 잘못되었습니다.`);
      requireCondition(entry.summary?.path === `summaries/${entry.resultKey}.json`, `${label} summary path가 잘못되었습니다.`);
      requireCondition(validSha256(entry.detail.sha256) && integer(entry.detail.bytes) && Number(entry.detail.bytes) > 0, `${label} detail reference가 잘못되었습니다.`);
      requireCondition(validSha256(entry.summary.sha256) && integer(entry.summary.bytes) && Number(entry.summary.bytes) > 0, `${label} summary reference가 잘못되었습니다.`);
    });
    requireCondition(
      declaredPresetCount === 0 || declaredPresetCount === manifest.entries.length,
      "manifest presetId는 모든 entry에 있거나 모두 없어야 합니다.",
    );
    requireCondition(resultKeys.has(manifest.defaultResultKey), "manifest 기본 entry가 없습니다.");
    return manifest;
  }

  function resolveExactEntry(manifest, normalizedInputs) {
    const requested = canonicalString(normalizedInputs);
    return manifest.entries.find((entry) => canonicalString(entry.normalizedInputs) === requested) || null;
  }

  function parseInputValue(field, raw) {
    const text = String(raw ?? "").trim();
    if (field.kind === "string") {
      if (!text) throw new Error(`${field.key}가 비어 있습니다.`);
      return text;
    }
    if (!text || !Number.isFinite(Number(text))) throw new Error(`${field.key}가 유효한 숫자가 아닙니다.`);
    const value = Number(text);
    if (field.kind === "integer" && !Number.isInteger(value)) throw new Error(`${field.key}는 정수여야 합니다.`);
    return field.kind === "percent" ? value / 100 : value;
  }

  function serializeInputValue(field, value) {
    if (field.kind === "percent") return String(Number(value) * 100);
    return String(value);
  }

  function entryByResultKey(manifest, resultKey) {
    return manifest.entries.find((entry) => entry.resultKey === resultKey) || null;
  }

  function entryByPresetId(manifest, presetId) {
    return manifest.entries.find((entry) => entry.presetId === presetId) || null;
  }

  function applyResearchInputDependencies(normalizedInputs) {
    if (integer(normalizedInputs.evaluation_window_days)) {
      const minimumObservations = Math.max(252, Number(normalizedInputs.evaluation_window_days) - 252);
      normalizedInputs.min_evaluation_observations = minimumObservations;
      normalizedInputs.min_daily_risk_observations = minimumObservations;
    }
    return normalizedInputs;
  }

  function researchInputsFromNormalizedInputs(normalizedInputs) {
    const result = { version: RESEARCH_INPUTS_VERSION };
    Object.entries(RESEARCH_INPUT_PARITY).forEach(([publicKey, normalizedKey]) => {
      requireCondition(
        Object.prototype.hasOwnProperty.call(normalizedInputs, normalizedKey),
        `로컬 API 입력에 ${normalizedKey}가 없습니다.`,
      );
      result[publicKey] = normalizedInputs[normalizedKey];
    });
    requireCondition(
      integer(normalizedInputs.evaluation_window_days)
        && Number(normalizedInputs.evaluation_window_days) % 252 === 0,
      "evaluation_window_days는 252의 정수배여야 합니다.",
    );
    result.evaluationYears = Number(normalizedInputs.evaluation_window_days) / 252;
    result.evaluationWindowDays = Number(normalizedInputs.evaluation_window_days);
    return result;
  }

  function localApiRequestFromStaticState(manifest, requestedInputs) {
    const baseEntry = entryByResultKey(manifest, manifest.defaultResultKey);
    requireCondition(baseEntry, "manifest 기본 최신 entry가 없습니다.");
    const normalizedInputs = cloneJson(baseEntry.normalizedInputs);
    INPUT_FIELDS.forEach((field) => {
      requireCondition(
        Object.prototype.hasOwnProperty.call(requestedInputs, field.key),
        `요청 URL에 공개 입력 ${field.key}가 없습니다.`,
      );
      normalizedInputs[field.key] = requestedInputs[field.key];
    });
    applyResearchInputDependencies(normalizedInputs);
    return { baseEntry, requestedInputs: normalizedInputs };
  }

  function requestFromSearch(manifest, search) {
    const params = new URLSearchParams(String(search || "").replace(/^\?/, ""));
    const requestedResultKey = params.get("result") || manifest.defaultResultKey;
    const requestedPresetId = params.get("preset");
    if (!validSha256(requestedResultKey)) {
      return { baseEntry: null, requestedInputs: null, entry: null, error: `resultKey가 잘못되었습니다. ${LOCAL_API_REQUIRED}` };
    }
    if (requestedPresetId !== null && !PRESET_ID_PATTERN.test(requestedPresetId)) {
      return { baseEntry: null, requestedInputs: null, entry: null, error: `presetId가 잘못되었습니다. ${LOCAL_API_REQUIRED}` };
    }
    let baseEntry = entryByResultKey(manifest, requestedResultKey);
    let recoveredFromRotatedResult = false;
    if (!baseEntry && requestedPresetId !== null) {
      baseEntry = entryByPresetId(manifest, requestedPresetId);
      recoveredFromRotatedResult = baseEntry !== null;
    }
    if (!baseEntry) {
      baseEntry = entryByResultKey(manifest, manifest.defaultResultKey);
      recoveredFromRotatedResult = baseEntry !== null;
    }
    if (!baseEntry) return { baseEntry: null, requestedInputs: null, entry: null, error: LOCAL_API_REQUIRED };
    const requestedInputs = cloneJson(baseEntry.normalizedInputs);
    try {
      INPUT_FIELDS.forEach((field) => {
        if (params.has(field.key)) requestedInputs[field.key] = parseInputValue(field, params.get(field.key));
      });
      if (params.has("evaluationYears")) {
        const evaluationYears = Number(params.get("evaluationYears"));
        if (!Number.isInteger(evaluationYears) || evaluationYears < 1 || evaluationYears > 10) {
          throw new Error("evaluationYears는 1–10 정수여야 합니다.");
        }
        const impliedWindow = evaluationYears * 252;
        if (params.has("evaluation_window_days") && Number(requestedInputs.evaluation_window_days) !== impliedWindow) {
          throw new Error("evaluationYears와 evaluation_window_days가 다릅니다.");
        }
        requestedInputs.evaluation_window_days = impliedWindow;
      }
      if (params.has("evaluation_window_days") || params.has("evaluationYears")) applyResearchInputDependencies(requestedInputs);
    } catch (error) {
      return {
        baseEntry,
        requestedInputs,
        entry: null,
        error: `${error.message} ${LOCAL_API_REQUIRED}`,
        recoveredFromRotatedResult,
      };
    }
    const entry = resolveExactEntry(manifest, requestedInputs);
    return {
      baseEntry,
      requestedInputs,
      entry,
      error: entry ? null : LOCAL_API_REQUIRED,
      recoveredFromRotatedResult,
    };
  }

  function searchForRequest(resultKey, normalizedInputs, presetId = null) {
    const params = new URLSearchParams();
    params.set("result", resultKey);
    if (presetId !== null) params.set("preset", presetId);
    INPUT_FIELDS.forEach((field) => {
      if (Object.prototype.hasOwnProperty.call(normalizedInputs, field.key)) {
        params.set(field.key, serializeInputValue(field, normalizedInputs[field.key]));
      }
    });
    if (integer(normalizedInputs.evaluation_window_days) && Number(normalizedInputs.evaluation_window_days) % 252 === 0) {
      params.set("evaluationYears", String(Number(normalizedInputs.evaluation_window_days) / 252));
    }
    return `?${params.toString()}`;
  }

  function policyDefinition(payload, policyId) {
    return payload.weightingPolicyRegistry.policies[policyId] || {};
  }

  function policyLabel(payload, policyId) {
    return policyDefinition(payload, policyId).label || policyId || "—";
  }

  function pairKey(row) {
    return `${row.factor}::${row.policy_id}`;
  }

  function rowReasonCodes(row) {
    return [...new Set([
      ...(Array.isArray(row.guardrail_breaches) ? row.guardrail_breaches : []),
      ...(Array.isArray(row.contribution_guardrail_breaches) ? row.contribution_guardrail_breaches : []),
      ...(Array.isArray(row.exclusion_reason_codes) ? row.exclusion_reason_codes : []),
    ].filter((value) => typeof value === "string" && value.trim()).map((value) => value.trim()))];
  }

  function rankingRow(factor, policyId) {
    return state.payload.factorPolicyRanking.find((row) => row.factor === factor && row.policy_id === policyId) || null;
  }

  function detailRankingRow() {
    return state.payload.factorPolicyRanking.find((row) => pairKey(row) === state.detailPairKey) || null;
  }

  function definitionFor(factor) {
    return state.payload.factorDefinitions.find((row) => row.factor === factor) || {};
  }

  function closeNumber(left, right, tolerance = 1e-9) {
    if (!finite(left) || !finite(right)) return false;
    const scale = Math.max(1, Math.abs(Number(left)), Math.abs(Number(right)));
    return Math.abs(Number(left) - Number(right)) <= tolerance * scale;
  }

  function validateTargetAllocation(payload) {
    const target = payload.currentResearchTarget;
    const config = payload.config;
    requireCondition(isRecord(target) && isRecord(config), "currentResearchTarget/config가 없습니다.");
    const maxWeight = Number(config.max_weight);
    requireCondition(finite(maxWeight) && maxWeight > 0 && maxWeight <= 1, "config.max_weight가 잘못되었습니다.");
    requireCondition(Array.isArray(target.weights), "currentResearchTarget.weights가 배열이 아닙니다.");
    requireCondition(integer(target.selectedSecurityCount) && Number(target.selectedSecurityCount) === target.weights.length, "currentResearchTarget 종목 수가 다릅니다.");
    requireCondition(integer(config.top_n) && Number(config.top_n) >= 1 && target.weights.length <= Number(config.top_n), "currentResearchTarget 종목 수가 Top-N을 초과합니다.");
    requireCondition(integer(target.eligibleSecurityCount) && Number(target.eligibleSecurityCount) >= target.weights.length, "currentResearchTarget 적격 종목 수가 잘못되었습니다.");

    const symbols = new Set();
    const weights = target.weights.map((row, index) => {
      const symbol = typeof row?.symbol === "string" ? row.symbol.trim().toUpperCase() : "";
      const weight = Number(row?.weight);
      requireCondition(
        isRecord(row)
          && row.rank === index + 1
          && symbol
          && !symbols.has(symbol)
          && finite(row.factorScore)
          && finite(weight)
          && weight > 0
          && weight <= maxWeight + 1e-12,
        "currentResearchTarget 보유 행이 잘못되었습니다.",
      );
      if (Object.prototype.hasOwnProperty.call(row, "maxWeight")) {
        requireCondition(closeNumber(row.maxWeight, maxWeight), "보유 행 maxWeight가 config와 다릅니다.");
      }
      symbols.add(symbol);
      return weight;
    });
    const cashWeight = Number(target.cashWeight);
    requireCondition(finite(cashWeight) && cashWeight >= 0 && cashWeight <= 1, "currentResearchTarget 현금 비중이 잘못되었습니다.");
    requireCondition(closeNumber(weights.reduce((sum, value) => sum + value, 0) + cashWeight, 1), "currentResearchTarget 비중과 현금의 합이 1이 아닙니다.");

    const concentration = target.concentration;
    requireCondition(isRecord(concentration), "currentResearchTarget concentration이 없습니다.");
    const invested = weights.reduce((sum, value) => sum + value, 0);
    const normalized = invested > 0 ? weights.map((value) => value / invested) : [];
    const hhi = normalized.reduce((sum, value) => sum + value * value, 0);
    const ordered = weights.slice().sort((left, right) => right - left);
    const expected = {
      investedWeight: invested,
      cashWeight,
      riskySleeveHhi: hhi,
      effectiveNames: hhi > 0 ? 1 / hhi : 0,
      top1Weight: ordered.slice(0, 1).reduce((sum, value) => sum + value, 0),
      top5Weight: ordered.slice(0, 5).reduce((sum, value) => sum + value, 0),
      maxWeight: ordered[0] || 0,
    };
    Object.entries(expected).forEach(([field, value]) => {
      requireCondition(closeNumber(concentration[field], value), `currentResearchTarget concentration.${field}가 잘못되었습니다.`);
    });
    return { target, maxWeight };
  }

  function expectedGuardrailProfile(researchInputs) {
    requireCondition(isRecord(researchInputs), "guardrailProfile researchInputs가 없습니다.");
    const thresholdFields = [
      "selectionMinSharpe",
      "selectionMaxDrawdown",
      "selectionMaxAnnualizedCostDrag",
      "selectionMinEffectiveNames",
      "selectionMaxTargetHhi",
      "selectionMaxTargetWeight",
      "selectionMaxAbsSecurityDayContribution",
      "selectionMaxSecurityAbsoluteContributionShare",
      "selectionMaxLeaveOneSecurityCagrDelta",
      "selectionExtremeEventPenaltyPoints",
    ];
    thresholdFields.forEach((field) => {
      requireCondition(finite(researchInputs[field]), `researchInputs.${field}가 잘못되었습니다.`);
    });
    requireCondition(
      ["warn", "penalize", "exclude"].includes(researchInputs.selectionExtremeEventAction),
      "researchInputs.selectionExtremeEventAction이 잘못되었습니다.",
    );
    return {
      id: ABSOLUTE_GUARDRAIL_VERSION,
      version: 1,
      policyNeutral: true,
      rules: [
        {
          id: "minimum_sharpe",
          metric: "sharpe",
          operator: ">=",
          threshold: researchInputs.selectionMinSharpe,
          unit: "ratio",
        },
        {
          id: "maximum_drawdown_magnitude",
          metric: "max_drawdown",
          operator: ">=",
          threshold: -Number(researchInputs.selectionMaxDrawdown),
          unit: "fraction",
        },
        {
          id: "maximum_annualized_cost_drag",
          metric: "annualized_cost_drag",
          operator: "<=",
          threshold: researchInputs.selectionMaxAnnualizedCostDrag,
          unit: "fraction_per_year",
        },
        {
          id: "minimum_historical_target_effective_names",
          metric: "min_target_effective_names",
          operator: ">=",
          threshold: researchInputs.selectionMinEffectiveNames,
          unit: "names",
        },
        {
          id: "minimum_current_target_effective_names",
          metric: "current_target_effective_names",
          operator: ">=",
          threshold: researchInputs.selectionMinEffectiveNames,
          unit: "names",
        },
        {
          id: "maximum_historical_target_hhi",
          metric: "max_target_hhi",
          operator: "<=",
          threshold: researchInputs.selectionMaxTargetHhi,
          unit: "fraction",
        },
        {
          id: "maximum_current_target_hhi",
          metric: "current_target_hhi",
          operator: "<=",
          threshold: researchInputs.selectionMaxTargetHhi,
          unit: "fraction",
        },
        {
          id: "maximum_historical_target_weight",
          metric: "max_target_weight",
          operator: "<=",
          threshold: researchInputs.selectionMaxTargetWeight,
          unit: "fraction",
        },
        {
          id: "maximum_current_target_weight",
          metric: "current_target_max_weight",
          operator: "<=",
          threshold: researchInputs.selectionMaxTargetWeight,
          unit: "fraction",
        },
        {
          id: "maximum_security_day_contribution",
          metric: "max_abs_security_day_contribution",
          operator: "<=",
          threshold: researchInputs.selectionMaxAbsSecurityDayContribution,
          unit: "portfolio_return_fraction",
        },
        {
          id: "maximum_security_absolute_contribution_share",
          metric: "max_security_absolute_contribution_share",
          operator: "<=",
          threshold: researchInputs.selectionMaxSecurityAbsoluteContributionShare,
          unit: "fraction",
        },
        {
          id: "maximum_leave_one_security_cagr_delta",
          metric: "max_abs_leave_one_security_cagr_delta",
          operator: "<=",
          threshold: researchInputs.selectionMaxLeaveOneSecurityCagrDelta,
          unit: "cagr_fraction",
        },
      ],
      requiredContracts: {
        completePolicyInputs: true,
        completeExecutionCoverage: true,
        currentTargetAvailable: true,
        contributionDiagnosticsComplete: true,
      },
      extremeEventAction: researchInputs.selectionExtremeEventAction,
      extremeEventPenaltyPoints: researchInputs.selectionExtremeEventPenaltyPoints,
    };
  }

  function validateGuardrailProfile(payload) {
    const profile = payload.selectionDecision?.guardrailProfile;
    requireCondition(isRecord(profile), "selectionDecision.guardrailProfile이 없습니다.");
    requireCondition(
      Array.isArray(profile.rules) && profile.rules.length === 12,
      "guardrailProfile은 정확히 12개 규칙이어야 합니다.",
    );
    requireCondition(
      sameJson(profile, expectedGuardrailProfile(payload.researchInputs)),
      "guardrailProfile이 researchInputs 기반 exact 계약과 다릅니다.",
    );
    return profile;
  }

  function concentrationGuardrailExpectations(row, researchInputs) {
    return {
      guardrail_historical_effective_names:
        Number(row.min_target_effective_names) >= Number(researchInputs.selectionMinEffectiveNames),
      guardrail_current_effective_names:
        Number(row.current_target_effective_names) >= Number(researchInputs.selectionMinEffectiveNames),
      guardrail_historical_target_hhi:
        Number(row.max_target_hhi) <= Number(researchInputs.selectionMaxTargetHhi),
      guardrail_current_target_hhi:
        Number(row.current_target_hhi) <= Number(researchInputs.selectionMaxTargetHhi),
      guardrail_historical_target_weight:
        Number(row.max_target_weight) <= Number(researchInputs.selectionMaxTargetWeight),
      guardrail_current_target_weight:
        Number(row.current_target_max_weight) <= Number(researchInputs.selectionMaxTargetWeight),
    };
  }

  function validateRankingConcentrationGuardrails(payload) {
    const metricDomains = {
      min_target_effective_names: (value) => value >= 0,
      current_target_effective_names: (value) => value >= 0,
      max_target_hhi: (value) => value >= 0 && value <= 1,
      current_target_hhi: (value) => value >= 0 && value <= 1,
      max_target_weight: (value) => value >= 0 && value <= 1,
      current_target_max_weight: (value) => value >= 0 && value <= 1,
    };
    payload.factorPolicyRanking.forEach((row, index) => {
      Object.entries(metricDomains).forEach(([field, validDomain]) => {
        const value = Number(row[field]);
        requireCondition(
          finite(row[field]) && validDomain(value),
          `factorPolicyRanking[${index}].${field}가 잘못되었습니다.`,
        );
      });
      Object.entries(concentrationGuardrailExpectations(row, payload.researchInputs)).forEach(
        ([field, expected]) => {
          requireCondition(
            row[field] === expected,
            `factorPolicyRanking[${index}].${field}가 집중도 임계값과 다릅니다.`,
          );
        },
      );
    });
  }

  function validateSelectedConcentrationGuardrails(payload, row, target) {
    const concentration = target.concentration;
    const metrics = {
      min_target_effective_names: Number(row.min_target_effective_names),
      current_target_effective_names: Number(row.current_target_effective_names),
      max_target_hhi: Number(row.max_target_hhi),
      current_target_hhi: Number(row.current_target_hhi),
      max_target_weight: Number(row.max_target_weight),
      current_target_max_weight: Number(row.current_target_max_weight),
    };
    Object.entries(metrics).forEach(([field, value]) => {
      requireCondition(finite(value), `선택 행 집중도 지표가 잘못되었습니다: ${field}`);
    });
    requireCondition(
      closeNumber(metrics.current_target_effective_names, concentration.effectiveNames)
        && closeNumber(metrics.current_target_hhi, concentration.riskySleeveHhi)
        && closeNumber(metrics.current_target_max_weight, concentration.maxWeight),
      "선택 행의 현재 집중도 지표가 currentResearchTarget과 다릅니다.",
    );
    const expected = concentrationGuardrailExpectations(row, payload.researchInputs);
    requireCondition(
      Object.values(expected).every(Boolean),
      "선택 조합이 역사상 최악값 또는 현재 집중도 절대 가드레일을 통과하지 못했습니다.",
    );
    requireCondition(
      row.absolute_guardrail_pass === true
        && row.selection_eligible === true
        && row.selection_status === "eligible"
        && row.selected === true,
      "선택 행이 pass/eligible/selected 계약을 충족하지 않습니다.",
    );
  }

  function validateGridAccounting(payload) {
    const accounting = payload.gridAccounting;
    const ranking = payload.factorPolicyRanking;
    requireCondition(isRecord(accounting), "gridAccounting이 없습니다.");
    requireCondition(Array.isArray(ranking), "factorPolicyRanking이 배열이 아닙니다.");
    const exactCounts = {
      independentFactorCount: EXPECTED_INDEPENDENT_FACTOR_COUNT,
      policyCount: EXPECTED_POLICY_COUNT,
      expectedIndependentPairCount: EXPECTED_INDEPENDENT_PAIR_COUNT,
      evaluatedIndependentPairCount: EXPECTED_INDEPENDENT_PAIR_COUNT,
      missingIndependentPairCount: 0,
      diagnosticAliasFactorCount: EXPECTED_ALIAS_FACTOR_COUNT,
      diagnosticAliasPairCount: EXPECTED_ALIAS_PAIR_COUNT,
    };
    Object.entries(exactCounts).forEach(([field, expected]) => {
      requireCondition(accounting[field] === expected, `gridAccounting.${field}가 ${expected}이 아닙니다.`);
    });
    requireCondition(
      accounting.availableIndependentPairCount + accounting.excludedIndependentPairCount
        === EXPECTED_INDEPENDENT_PAIR_COUNT,
      "gridAccounting available + excluded가 244와 다릅니다.",
    );
    requireCondition(
      ranking.length === EXPECTED_INDEPENDENT_PAIR_COUNT + EXPECTED_ALIAS_PAIR_COUNT,
      "factorPolicyRanking 전체 행 수가 256이 아닙니다.",
    );

    const pairs = new Set();
    ranking.forEach((row) => {
      requireCondition(
        isRecord(row) && typeof row.factor === "string" && typeof row.policy_id === "string",
        "factorPolicyRanking 식별자가 잘못되었습니다.",
      );
      const key = pairKey(row);
      requireCondition(!pairs.has(key), `중복 factor-policy 행입니다: ${key}`);
      pairs.add(key);
    });
    const aliasRows = ranking.filter((row) => row.comparison_status === "duplicate_alias");
    const independentRows = ranking.filter((row) => row.comparison_status !== "duplicate_alias");
    requireCondition(aliasRows.length === EXPECTED_ALIAS_PAIR_COUNT, "diagnostic alias 행 수가 12가 아닙니다.");
    requireCondition(
      new Set(aliasRows.map((row) => row.factor)).size === EXPECTED_ALIAS_FACTOR_COUNT,
      "diagnostic alias 팩터 수가 3이 아닙니다.",
    );
    requireCondition(independentRows.length === EXPECTED_INDEPENDENT_PAIR_COUNT, "독립 factor-policy 행 수가 244가 아닙니다.");
    requireCondition(
      new Set(independentRows.map((row) => row.factor)).size === EXPECTED_INDEPENDENT_FACTOR_COUNT,
      "독립 팩터 수가 61이 아닙니다.",
    );
    requireCondition(
      new Set(independentRows.map((row) => row.policy_id)).size === EXPECTED_POLICY_COUNT,
      "비중 정책 수가 4가 아닙니다.",
    );
    const policyIds = [...new Set(independentRows.map((row) => row.policy_id))].sort();
    const rowsByFactor = new Map();
    independentRows.forEach((row) => {
      if (!rowsByFactor.has(row.factor)) rowsByFactor.set(row.factor, []);
      rowsByFactor.get(row.factor).push(row);
    });
    rowsByFactor.forEach((rows, factor) => {
      requireCondition(
        sameJson(rows.map((row) => row.policy_id).sort(), policyIds),
        `독립 팩터의 4개 정책 grid가 불완전합니다: ${factor}`,
      );
    });
    const commonComparableFactorCount = [...rowsByFactor.values()].filter(
      (rows) => rows.every((row) => row.comparison_status === "available"),
    ).length;
    requireCondition(
      commonComparableFactorCount === accounting.commonComparableFactorCount,
      "commonComparableFactorCount가 ranking과 다릅니다.",
    );

    const availableRows = independentRows.filter((row) => row.comparison_status === "available");
    const excludedRows = independentRows.filter((row) => row.comparison_status !== "available");
    requireCondition(
      availableRows.length === accounting.availableIndependentPairCount,
      "availableIndependentPairCount가 ranking과 다릅니다.",
    );
    requireCondition(
      excludedRows.length === accounting.excludedIndependentPairCount,
      "excludedIndependentPairCount가 ranking과 다릅니다.",
    );
    const observedReasonCounts = {};
    excludedRows.forEach((row) => {
      requireCondition(
        Array.isArray(row.exclusion_reason_codes) && row.exclusion_reason_codes.length > 0,
        `제외 행에 exact reason code가 없습니다: ${pairKey(row)}`,
      );
      requireCondition(
        Array.isArray(row.exclusion_reasons) && row.exclusion_reasons.length > 0,
        `제외 행에 structured reason이 없습니다: ${pairKey(row)}`,
      );
      const structuredCodes = row.exclusion_reasons.map((reason) => reason?.code);
      requireCondition(
        sameJson([...new Set(structuredCodes)].sort(), [...new Set(row.exclusion_reason_codes)].sort()),
        `제외 행의 reason code와 structured reason이 다릅니다: ${pairKey(row)}`,
      );
      row.exclusion_reason_codes.forEach((code) => {
        requireCondition(typeof code === "string" && code, `빈 제외 reason code입니다: ${pairKey(row)}`);
        observedReasonCounts[code] = (observedReasonCounts[code] || 0) + 1;
      });
    });
    requireCondition(
      sameJson(observedReasonCounts, accounting.exclusionReasonCounts || {}),
      "gridAccounting.exclusionReasonCounts가 ranking exact reasons와 다릅니다.",
    );
    return accounting;
  }

  function modeLabel(mode) {
    return {
      live_market: "실제 시장 데이터",
      local_file: "검토된 로컬 데이터",
      demo: "합성 데모",
    }[mode] || mode || "미표기";
  }

  function evidenceLabel(value) {
    return {
      same_sample_descriptive_actual_market: "실제 시장 · 동일 표본 설명 연구",
      same_sample_descriptive: "동일 표본 설명 연구",
    }[value] || value || "미표기";
  }

  function formatDigestMap(value) {
    if (!isRecord(value)) return String(value || "—");
    const entries = Object.entries(value)
      .filter(([key, digest]) => key && typeof digest === "string" && digest)
      .map(([key, digest]) => `${key}:${digest.slice(0, 12)}`);
    return entries.length ? entries.join(" · ") : "—";
  }

  async function validateResult(entry, payload, summary = null, options = {}) {
    const apiResult = options.source === "local_api";
    requireCondition(isRecord(payload) && payload.schemaVersion === RESULT_SCHEMA_VERSION, "detail schemaVersion 4가 아닙니다.");
    validateIdentity(payload.resultIdentity, entry.resultKey, "detail", { requireCanonicalTransport: !apiResult });
    requireCondition(sameJson(payload.resultIdentity, entry.identity), apiResult
      ? "detail resultIdentity가 로컬 API 응답 identity와 다릅니다."
      : "detail resultIdentity가 manifest와 다릅니다.");
    requireCondition(payload.resultKey === undefined || payload.resultKey === entry.resultKey, "detail top-level resultKey가 다릅니다.");
    requireCondition(isRecord(payload.data) && payload.data.synthetic === false && payload.data.mode === "live_market", "결과는 실제 시장 비합성 실행이어야 합니다.");
    requireCondition(integer(payload.data.analyzedSecurityCount) && Number(payload.data.analyzedSecurityCount) >= 2700, "결과는 2,700개 이상 종목을 분석해야 합니다.");
    requireCondition(typeof payload.data.asOf === "string" && payload.data.asOf, "detail data.asOf가 없습니다.");
    requireCondition(
      isRecord(payload.data.inputSha256)
        && sameJson(Object.keys(payload.data.inputSha256).sort(), [...LIVE_INPUT_HASH_FIELDS].sort())
        && LIVE_INPUT_HASH_FIELDS.every(
          (field) => /^[0-9a-f]{64}$/.test(payload.data.inputSha256[field] || ""),
        ),
      "실제시장 provenance 입력 해시가 없습니다.",
    );
    requireCondition(Array.isArray(payload.priceSources) && payload.priceSources.length > 0, "priceSources가 비어 있습니다.");
    const priceSourceSymbols = new Set();
    payload.priceSources.forEach((row) => {
      const symbol = typeof row?.symbol === "string" ? row.symbol.trim().toUpperCase() : "";
      requireCondition(
        isRecord(row)
          && symbol
          && typeof row.price_source === "string"
          && row.price_source.trim()
          && !priceSourceSymbols.has(symbol),
        "priceSources 행 또는 종목 유일성 계약이 잘못되었습니다.",
      );
      priceSourceSymbols.add(symbol);
    });
    requireCondition(Array.isArray(payload.data.analyzedSymbols), "analyzedSymbols가 배열이 아닙니다.");
    const analyzedSymbols = payload.data.analyzedSymbols.map((value) => (
      typeof value === "string" ? value.trim().toUpperCase() : ""
    ));
    requireCondition(
      analyzedSymbols.length === Number(payload.data.analyzedSecurityCount)
        && analyzedSymbols.every((symbol, index) => (
          symbol
          && symbol === payload.data.analyzedSymbols[index]
          && priceSourceSymbols.has(symbol)
        ))
        && new Set(analyzedSymbols).size === analyzedSymbols.length,
      "analyzedSymbols 순서·유일성·priceSources coverage가 잘못되었습니다.",
    );
    const candidateSymbolsSha256 = await sha256Hex(
      new TextEncoder().encode(canonicalString(analyzedSymbols)),
    );
    requireCondition(Array.isArray(payload.sourceHealth) && payload.sourceHealth.length > 0, "sourceHealth가 비어 있습니다.");
    payload.sourceHealth.forEach((row) => {
      requireCondition(
        isRecord(row)
          && typeof row.source === "string"
          && row.source.trim()
          && typeof row.status === "string"
          && row.status.trim(),
        "sourceHealth 행의 source/status가 잘못되었습니다.",
      );
    });
    const [priceSourcesSha256, dataSourcesSha256] = await Promise.all([
      canonicalSha256(payload.priceSources),
      canonicalSha256(payload.sourceHealth),
    ]);
    requireCondition(
      priceSourcesSha256 === payload.data.inputSha256.priceSources,
      "priceSources RFC 8785 JCS SHA-256이 inputSha256.priceSources와 다릅니다.",
    );
    requireCondition(
      dataSourcesSha256 === payload.data.inputSha256.dataSources,
      "sourceHealth RFC 8785 JCS SHA-256이 inputSha256.dataSources와 다릅니다.",
    );
    const marketSnapshot = payload.resultIdentity?.keyParts?.marketSnapshot;
    const expectedMarketSnapshot = {
      sourceMode: payload.data.mode,
      sourceLabel: payload.data.sourceLabel,
      provider: payload.data.provider,
      priceBasis: payload.data.priceBasis,
      volumeBasis: payload.data.volumeBasis,
      rawCloseProxySymbolCount: payload.data.rawCloseProxySymbolCount,
      requestedThrough: payload.data.requestedThrough,
      dataAsOf: payload.data.asOf,
      inputSha256: payload.data.inputSha256,
      requestedCandidateCount: payload.data.requestedCandidateCount,
      providerReturnedCandidateCount: payload.data.providerReturnedCandidateCount,
      analyzedSecurityCount: payload.data.analyzedSecurityCount,
      candidateSymbolsSha256,
    };
    requireCondition(
      isRecord(marketSnapshot)
        && Object.entries(expectedMarketSnapshot).every(
          ([field, value]) => sameJson(marketSnapshot[field], value),
        ),
      "resultIdentity marketSnapshot이 detail data와 다릅니다.",
    );
    if (!apiResult) {
      requireCondition(isRecord(summary) && summary.schemaVersion === RESULT_SCHEMA_VERSION, "summary schemaVersion 4가 아닙니다.");
      validateIdentity(summary.resultIdentity, entry.resultKey, "summary");
      requireCondition(sameJson(summary.resultIdentity, entry.identity), "summary resultIdentity가 manifest와 다릅니다.");
      requireCondition(summary.resultKey === undefined || summary.resultKey === entry.resultKey, "summary top-level resultKey가 다릅니다.");
      requireCondition(summary.dataAsOf === payload.data.asOf && summary.dataMode === payload.data.mode && summary.synthetic === false, "summary/detail 데이터 기준이 다릅니다.");
      requireCondition(summary.analyzedSecurityCount === payload.data.analyzedSecurityCount, "summary/detail 분석 종목 수가 다릅니다.");
      requireCondition(summary.selectedFactor === payload.selectedFactor && summary.selectedWeightingPolicy === payload.selectedWeightingPolicy, "summary/detail 선택 조합이 다릅니다.");
    }

    const required = [
      "selectedFactor", "selectedWeightingPolicy", "selectedReason", "selectionDecision",
      "factorPolicyRanking", "policyDiagnostics", "weightingPolicyRegistry",
      "currentResearchTarget", "currentTransition", "selectionMethod", "performance",
      "factorDefinitions", "researchInputs", "researchScope", "config", "meta",
    ];
    required.forEach((key) => requireCondition(Object.prototype.hasOwnProperty.call(payload, key), `detail 필드가 없습니다: ${key}`));
    requireCondition(Array.isArray(payload.factorPolicyRanking) && payload.factorPolicyRanking.length > 0, "factorPolicyRanking이 비어 있습니다.");
    requireCondition(Array.isArray(payload.policyDiagnostics), "policyDiagnostics가 배열이 아닙니다.");
    requireCondition(isRecord(payload.weightingPolicyRegistry) && isRecord(payload.weightingPolicyRegistry.policies), "weightingPolicyRegistry가 없습니다.");
    requireCondition(isRecord(payload.weightingPolicyRegistry.policies[payload.selectedWeightingPolicy]), "선택 정책이 registry에 없습니다.");
    requireCondition(payload.selectionMethod.name === "joint_factor_policy_absolute_guardrails", "공동 팩터×정책 선택 계약이 아닙니다.");
    requireCondition(isRecord(payload.researchInputs) && payload.researchInputs.version === RESEARCH_INPUTS_VERSION, "researchInputs 버전 계약이 아닙니다.");
    Object.entries(RESEARCH_INPUT_PARITY).forEach(([publicKey, normalizedKey]) => {
      requireCondition(
        Object.prototype.hasOwnProperty.call(payload.researchInputs, publicKey)
          && Object.prototype.hasOwnProperty.call(entry.normalizedInputs, normalizedKey)
          && sameJson(payload.researchInputs[publicKey], entry.normalizedInputs[normalizedKey]),
        `researchInputs.${publicKey}가 manifest normalizedInputs와 다릅니다.`,
      );
    });
    requireCondition(
      integer(payload.researchInputs.evaluationYears)
        && Number(payload.researchInputs.evaluationYears) * 252 === Number(payload.researchInputs.evaluationWindowDays),
      "researchInputs 평가 연수와 거래일 창이 다릅니다.",
    );
    if (apiResult) {
      requireCondition(
        sameJson(payload.researchInputs, options.expectedResearchInputs),
        "로컬 API 결과 researchInputs가 요청과 다릅니다.",
      );
    }

    validateGuardrailProfile(payload);
    validateGridAccounting(payload);
    validateRankingConcentrationGuardrails(payload);
    const selectedRows = payload.factorPolicyRanking.filter((row) => row.factor === payload.selectedFactor && row.policy_id === payload.selectedWeightingPolicy);
    requireCondition(
      selectedRows.length === 1
        && selectedRows[0].selected === true
        && selectedRows[0].absolute_guardrail_pass === true
        && selectedRows[0].selection_eligible === true
        && selectedRows[0].selection_status === "eligible"
        && selectedRows[0].comparison_status === "available"
        && finite(selectedRows[0].selection_score),
      "선택 팩터×정책 행이 정확히 하나의 pass/eligible/selected available 행이 아닙니다.",
    );
    requireCondition(payload.factorPolicyRanking.filter((row) => row.selected === true).length === 1, "factorPolicyRanking에 선택 행이 하나가 아닙니다.");
    requireCondition(payload.meta.policyFactorRunCount === payload.factorPolicyRanking.length, "factorPolicyRanking 개수가 meta와 다릅니다.");

    const { target, maxWeight } = validateTargetAllocation(payload);
    requireCondition(isRecord(target) && target.factor === payload.selectedFactor && target.weightingPolicyId === payload.selectedWeightingPolicy, "currentResearchTarget이 선택 조합과 다릅니다.");
    requireCondition(target.asOf === payload.data.asOf && target.signalDate === payload.data.asOf, "currentResearchTarget 기준일이 다릅니다.");
    validateSelectedConcentrationGuardrails(payload, selectedRows[0], target);
    if (!apiResult) {
      requireCondition(sameJson(summary.currentResearchTarget, target), "summary/detail currentResearchTarget이 다릅니다.");
      requireCondition(sameJson(summary.weights, target.weights), "summary/detail weights가 다릅니다.");
      requireCondition(closeNumber(summary.cashWeight, target.cashWeight), "summary/detail cashWeight가 다릅니다.");
      requireCondition(closeNumber(summary.maxWeight, maxWeight), "summary/detail maxWeight가 다릅니다.");
      requireCondition(summary.portfolioSize === target.selectedSecurityCount, "summary/detail portfolioSize가 다릅니다.");
      requireCondition(sameJson(summary.concentration, target.concentration), "summary/detail concentration이 다릅니다.");
    }
    return selectedRows[0];
  }

  function initTheme() {
    const saved = localStorage.getItem("mfl-theme");
    const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    document.documentElement.dataset.theme = saved || preferred;
    $("#theme-toggle").addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("mfl-theme", next);
    });
  }

  function populateResultOptions(manifest) {
    const select = $("#input-result-key");
    select.innerHTML = manifest.entries.map((entry) => {
      const market = entry.identity.keyParts.marketSnapshot || {};
      const inputs = entry.normalizedInputs;
      const label = `${market.dataAsOf || inputs.end_date || "기준일 미표기"} · Top ${inputs.top_n ?? "—"} · ${String(entry.resultKey).slice(0, 10)}`;
      return `<option value="${entry.resultKey}">${escapeHtml(label)}</option>`;
    }).join("");
    const rebalanceValues = [...new Set([
      "W", "ME", "QE",
      ...manifest.entries.map((entry) => entry.normalizedInputs.rebalance_frequency).filter(Boolean),
    ])];
    $("#input-rebalance-frequency").innerHTML = rebalanceValues.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  }

  function fillForm(entry, normalizedInputs = entry.normalizedInputs, researchInputs = null) {
    $("#input-result-key").value = entry.resultKey;
    INPUT_FIELDS.forEach((field) => {
      const element = $(`#${field.id}`);
      if (element && Object.prototype.hasOwnProperty.call(normalizedInputs, field.key)) {
        element.value = serializeInputValue(field, normalizedInputs[field.key]);
      }
    });
    if (integer(researchInputs?.evaluationYears)) {
      $("#input-evaluation-years").value = String(researchInputs.evaluationYears);
    } else if (finite(normalizedInputs.evaluation_window_days)) {
      $("#input-evaluation-years").value = (Number(normalizedInputs.evaluation_window_days) / 252).toFixed(2).replace(/\.00$/, "");
    }
  }

  function readFormRequest() {
    const baseEntry = entryByResultKey(state.manifest, $("#input-result-key").value);
    if (!baseEntry) throw new Error(LOCAL_API_REQUIRED);
    const requestedInputs = cloneJson(baseEntry.normalizedInputs);
    INPUT_FIELDS.forEach((field) => {
      requestedInputs[field.key] = parseInputValue(field, $(`#${field.id}`).value);
    });
    const evaluationYears = Number($("#input-evaluation-years").value);
    if (!Number.isInteger(evaluationYears) || evaluationYears < 1 || evaluationYears > 10) {
      throw new Error("평가 기간(년)은 1–10 정수여야 합니다.");
    }
    if (Number(requestedInputs.evaluation_window_days) !== evaluationYears * 252) {
      throw new Error("평가 기간(년)과 거래일 창이 다릅니다.");
    }
    applyResearchInputDependencies(requestedInputs);
    return { baseEntry, requestedInputs, entry: resolveExactEntry(state.manifest, requestedInputs) };
  }

  function updateLocation(mode, resultKey, normalizedInputs) {
    const presetId = entryByResultKey(state.manifest, resultKey)?.presetId || null;
    const next = `${window.location.pathname}${searchForRequest(resultKey, normalizedInputs, presetId)}${window.location.hash}`;
    if (mode === "push") history.pushState({ resultKey }, "", next);
    if (mode === "replace") history.replaceState({ resultKey }, "", next);
  }

  function setInputStatus(message, tone = "ok") {
    const status = $("#input-status");
    status.textContent = message;
    status.dataset.tone = tone;
  }

  function setResultSource(source) {
    state.resultSource = source;
    const element = $("#result-source");
    if (!element) return;
    element.textContent = source === "local_api" ? "로컬 API 계산 결과" : (
      source === "static_grid" ? "정적 사전 계산 결과" : "결과 없음"
    );
    element.dataset.source = source || "none";
  }

  function showUnavailable(message, requestedInputs = null, baseEntry = null) {
    document.body.classList.add("result-unavailable");
    state.payload = null;
    state.summary = null;
    setResultSource(null);
    $("#result-key").textContent = "unsupported";
    setInputStatus(message, "error");
    if (baseEntry && requestedInputs) fillForm(baseEntry, requestedInputs);
    const loading = $("#loading-state");
    loading.textContent = message;
    loading.classList.add("error-state");
    loading.classList.remove("is-hidden");
  }

  function showLoading(message) {
    const loading = $("#loading-state");
    loading.textContent = message;
    loading.classList.remove("error-state", "is-hidden");
  }

  function showResult() {
    document.body.classList.remove("result-unavailable");
    $("#loading-state").classList.add("is-hidden");
  }

  function renderOverview() {
    const payload = state.payload;
    const data = payload.data;
    const selected = rankingRow(payload.selectedFactor, payload.selectedWeightingPolicy);
    const target = payload.currentResearchTarget;
    const concentration = target.concentration || {};
    const modeBadge = $("#data-mode-badge");
    modeBadge.textContent = modeLabel(data.mode);
    modeBadge.dataset.mode = data.mode;
    $("#asof-label").textContent = `실제 기준일 ${data.asOf}`;
    $("#source-label").textContent = `요청 종료 ${data.requestedThrough || "—"}`;
    $("#winner-factor").textContent = `${payload.selectedFactor} × ${policyLabel(payload, payload.selectedWeightingPolicy)}`;
    $("#decision-factor").textContent = payload.selectedFactor;
    $("#winner-score").textContent = fmtNumber(selected.selection_score, 1);
    $("#decision-policy").textContent = policyLabel(payload, payload.selectedWeightingPolicy);
    $("#winner-reason").textContent = payload.selectedReason;
    $("#policy-reason").textContent = `${payload.selectionMethod.version} · ${payload.selectionMethod.guardrailVersion} · 정책별 집계는 진단 전용`;
    const metrics = [
      ["CAGR", fmtPercent(selected.cagr)],
      ["Sharpe", fmtNumber(selected.sharpe)],
      ["Sortino", fmtNumber(selected.sortino)],
      ["Calmar", fmtNumber(selected.calmar)],
      ["MDD", fmtPercent(selected.max_drawdown)],
      ["회전율", fmtPercent(selected.annualized_turnover)],
    ];
    $("#winner-metrics").innerHTML = metrics.map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");

    $("#portfolio-status").textContent = target.status === "available" ? "Python 목표 산출" : "현금 대기";
    $("#portfolio-status").classList.toggle("unavailable", target.status !== "available");
    $("#target-timing").textContent = `${target.signalDate} 신호 · ${String(target.executionTiming || "—").replaceAll("_", " ")}`;
    $("#compact-holdings").innerHTML = target.weights.slice(0, 5).map((row) => `
      <li>
        <span class="holding-rank">${row.rank}</span>
        <span class="holding-name"><strong>${escapeHtml(row.symbol)}</strong><small>점수 ${fmtNumber(row.factorScore, 3)}</small></span>
        <strong class="holding-weight">${fmtPercent(row.weight, 2)}</strong>
      </li>`).join("") || '<li class="empty-row">Python 결과가 현금 100%를 지정했습니다.</li>';
    $("#compact-invested").textContent = fmtPercent(concentration.investedWeight);
    $("#compact-cash").textContent = fmtPercent(target.cashWeight);
    $("#compact-count").textContent = `${fmtCount(target.selectedSecurityCount)}개`;

    $("#requested-count").textContent = fmtCount(data.requestedCandidateCount);
    $("#returned-count").textContent = fmtCount(data.providerReturnedCandidateCount);
    $("#analyzed-count").textContent = fmtCount(data.analyzedSecurityCount);
    $("#eligible-count").textContent = fmtCount(data.latestEligibleSecurityCount);
    $("#factor-count").textContent = fmtCount(payload.meta.independentFactorCount);
    $("#factor-count-context").textContent = `전체 ${fmtCount(payload.meta.factorCount)}개 · alias ${fmtCount(payload.meta.aliasFactorCount)}개`;
    $("#policy-count").textContent = fmtCount(Object.keys(payload.weightingPolicyRegistry.policies).length);
    $("#footer-runtime").textContent = `Python ${fmtNumber(payload.meta.runtimeSeconds, 1)}초 · peak RSS ${fmtMoney(Number(payload.meta.maxRssBytes) / 1e6)}MB`;
  }

  function renderAllocation() {
    const payload = state.payload;
    const target = payload.currentResearchTarget;
    const concentration = target.concentration || {};
    const transition = payload.currentTransition || {};
    $("#allocation-factor-policy").textContent = `${target.factor} · ${policyLabel(payload, target.weightingPolicyId)}`;
    $("#allocation-total").textContent = "Python 검증";
    $("#allocation-note").textContent = `${target.signalDate} 마지막 관측 신호로 Python이 산출한 다음 세션 종가용 연구 목표입니다. ${transition.note || ""}`;
    const concentrationItems = [
      ["투자 비중", fmtPercent(concentration.investedWeight)],
      ["현금", fmtPercent(concentration.cashWeight)],
      ["유효 종목 수", fmtNumber(concentration.effectiveNames, 1)],
      ["상위 1종목", fmtPercent(concentration.top1Weight)],
      ["상위 5종목", fmtPercent(concentration.top5Weight)],
      ["위험자산 HHI", fmtNumber(concentration.riskySleeveHhi, 4)],
    ];
    $("#concentration-strip").innerHTML = concentrationItems.map(([label, value]) => `<article><span>${label}</span><strong>${value}</strong></article>`).join("");

    const displayMax = finite(concentration.maxWeight) && Number(concentration.maxWeight) > 0 ? Number(concentration.maxWeight) : 1;
    $("#allocation-bars").innerHTML = target.weights.map((row) => `
      <div class="allocation-row">
        <span class="rank">${row.rank}</span>
        <span class="symbol">${escapeHtml(row.symbol)}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${Math.max(0, Math.min(100, Number(row.weight) / displayMax * 100))}%"></span></span>
        <strong>${fmtPercent(row.weight, 2)}</strong>
      </div>`).join("") || '<p class="empty-row">Python 결과가 현금 100%를 지정했습니다.</p>';
    $("#allocation-table tbody").innerHTML = target.weights.map((row) => `
      <tr>
        <td><span class="rank-chip">${row.rank}</span></td>
        <td><strong>${escapeHtml(row.symbol)}</strong></td>
        <td>${escapeHtml(row.name || row.symbol)}</td>
        <td>${fmtNumber(row.factorScore, 4)}</td>
        <td>${fmtNumber(row.latestPrice, 2)}</td>
        <td>${fmtNumber(row.rawPolicyScore, 4)}</td>
        <td>${fmtPercent(row.trailingVolatility, 1)}</td>
        <td>${fmtMoney(row.trailingDollarVolume)}</td>
        <td>${fmtPercent(row.preCapWeight, 2)}</td>
        <td class="weight-cell">${fmtPercent(row.weight, 2)}${row.capBinding ? '<small> cap</small>' : ""}</td>
      </tr>`).join("");
    const definition = policyDefinition(payload, target.weightingPolicyId);
    const componentStatus = target.componentStatus || {};
    const contractItems = [
      ["정책 ID", target.weightingPolicyId],
      ["정책 버전", target.weightingPolicyVersion],
      ["구현 ID", definition.implementationId],
      ["상한", fmtPercent(payload.config.max_weight)],
      ["Top-N", fmtCount(payload.config.top_n)],
      ["동점 규칙", target.tieBreakPolicy],
      ["현재 추정 회전율", fmtPercent(transition.oneWayTurnover)],
      ["현재 추정 비용", fmtPercent(transition.modeledCostFraction, 3)],
      ...Object.entries(componentStatus).map(([key, value]) => [`구성 ${key}`, value]),
    ];
    $("#allocation-contract").innerHTML = contractItems.map(([label, value]) => `<div><dt>${label}</dt><dd>${escapeHtml(value ?? "—")}</dd></div>`).join("");
  }

  function renderPolicies() {
    const payload = state.payload;
    const selected = payload.selectedWeightingPolicy;
    const policies = Object.entries(payload.weightingPolicyRegistry.policies);
    const diagnostics = new Map(payload.policyDiagnostics.map((row) => [row.policy_id, row]));
    $("#policy-selected-badge").textContent = `선택 조합의 정책 · ${policyLabel(payload, selected)}`;
    $("#policy-cards").innerHTML = policies.map(([id, definition]) => `
      <article class="policy-card ${id === selected ? "is-selected" : ""}">
        <div class="policy-card-top"><span>v${escapeHtml(definition.version)}</span><b>${id === selected ? "선택 조합" : "정책 후보"}</b></div>
        <h3>${escapeHtml(definition.label || id)}</h3>
        <code>${escapeHtml(id)}</code>
        <p>${escapeHtml(definition.description || "설명 미표기")}</p>
        <dl>
          <div><dt>구현 ID</dt><dd>${escapeHtml(definition.implementationId || "—")}</dd></div>
          <div><dt>필요 입력</dt><dd>${fmtCount((definition.requiredSignalDateInputs || []).length)}개</dd></div>
          <div><dt>진단 조합</dt><dd>${fmtCount(diagnostics.get(id)?.pair_count ?? diagnostics.get(id)?.available_pair_count ?? diagnostics.get(id)?.paired_factor_count)}</dd></div>
        </dl>
      </article>`).join("");
    $("#policy-table tbody").innerHTML = policies.map(([id, definition]) => {
      const row = diagnostics.get(id) || {};
      return `
        <tr class="${id === selected ? "is-selected" : ""}">
          <td><strong>${escapeHtml(definition.label || id)}</strong><small>${escapeHtml(id)}</small></td>
          <td>${escapeHtml(definition.version || "—")}</td>
          <td>${escapeHtml(definition.implementationId || "—")}</td>
          <td>${escapeHtml(definition.formula || "—")}</td>
          <td>${fmtCount(row.pair_count ?? row.available_pair_count ?? row.paired_factor_count)}</td>
          <td>${fmtNumber(row.sharpe)}</td>
          <td>${fmtPercent(row.cagr)}</td>
          <td class="${signClass(row.max_drawdown)}">${fmtPercent(row.max_drawdown)}</td>
          <td>${fmtPercent(row.annualized_turnover)}</td>
          <td>${fmtPercent(row.annualized_cost_drag)}</td>
        </tr>`;
    }).join("");
  }

  function filteredPairs() {
    return state.payload.factorPolicyRanking.filter((row) => {
      const categoryMatch = state.category === "all" || row.category === state.category;
      const text = `${row.factor} ${row.policy_id}`.toLowerCase();
      return categoryMatch && text.includes(state.search.toLowerCase());
    });
  }

  function renderFactorFilters() {
    const categories = [...new Set(state.payload.factorPolicyRanking.map((row) => row.category).filter(Boolean))].sort();
    $("#category-filter").innerHTML = '<option value="all">전체</option>'
      + categories.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`).join("");
  }

  function renderFactorComparison() {
    const payload = state.payload;
    const rows = filteredPairs();
    const available = rows.filter((row) => row.selection_eligible === true && finite(row.selection_score));
    $("#ranking-chart").innerHTML = available.slice(0, 12).map((row) => `
      <button class="ranking-row ${pairKey(row) === state.detailPairKey ? "is-selected" : ""}" type="button" data-pair="${escapeHtml(pairKey(row))}">
        <span class="ranking-name">${escapeHtml(row.factor)}<small>${escapeHtml(policyLabel(payload, row.policy_id))}</small></span>
        <span class="bar-track"><span class="bar-fill" style="width:${Math.max(0, Math.min(100, Number(row.selection_score)))}%"></span></span>
        <strong>${fmtNumber(row.selection_score, 1)}</strong>
      </button>`).join("") || '<p class="empty-row">조건에 맞는 유효 팩터×정책 조합이 없습니다.</p>';
    $("#factor-table tbody").innerHTML = rows.map((row) => {
      const status = row.selection_status || row.comparison_status || "미표기";
      const statusReasons = rowReasonCodes(row);
      const coverage = `${fmtPercent(row.valuation_coverage_ratio)} · ${fmtCount(row.daily_risk_observations)}일`;
      return `
        <tr tabindex="0" data-pair="${escapeHtml(pairKey(row))}" class="${pairKey(row) === state.detailPairKey ? "is-selected" : ""}">
          <td>${finite(row.rank) ? row.rank : "—"}</td>
          <td><strong>${escapeHtml(row.factor)}</strong><small>${escapeHtml(row.category || "other")}</small></td>
          <td>${escapeHtml(policyLabel(payload, row.policy_id))}<small>${escapeHtml(row.policy_id)}</small></td>
          <td><span class="${row.selection_eligible ? "ok-text" : "muted"}">${escapeHtml(status)}</span>${statusReasons.length ? `<small>${escapeHtml([...new Set(statusReasons)].join(", "))}</small>` : ""}</td>
          <td class="score-cell">${fmtNumber(row.selection_score, 1)}</td>
          <td class="${signClass(row.cagr)}">${fmtPercent(row.cagr)}</td>
          <td>${fmtNumber(row.sharpe)}</td>
          <td>${fmtNumber(row.sortino)}</td>
          <td>${fmtNumber(row.calmar)}</td>
          <td class="${signClass(row.max_drawdown)}">${fmtPercent(row.max_drawdown)}</td>
          <td>${fmtPercent(row.annualized_turnover)}</td>
          <td>${fmtPercent(row.annualized_cost_drag)}</td>
          <td>${coverage}</td>
        </tr>`;
    }).join("");
    document.querySelectorAll("[data-pair]").forEach((element) => {
      const select = () => {
        state.detailPairKey = element.dataset.pair;
        renderFactorComparison();
        renderFactorDetail();
      };
      element.addEventListener("click", select);
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
    });
  }

  function svgPath(values, x, y) {
    let path = "";
    let active = false;
    values.forEach((value, index) => {
      if (!finite(value)) {
        active = false;
        return;
      }
      path += `${active ? "L" : "M"}${x(index).toFixed(2)},${y(Number(value)).toFixed(2)} `;
      active = true;
    });
    return path.trim();
  }

  function renderPerformanceChart(row) {
    const performance = state.payload.performance;
    if (row.policy_id !== performance.weightingPolicyId) {
      $("#performance-chart").innerHTML = '<p class="empty-row">이 조합의 성과 곡선은 현재 정적 detail에 포함되지 않았습니다. 브라우저가 다른 정책의 곡선을 추정하지 않습니다.</p>';
      return;
    }
    const factorValues = performance.factorCurves[row.factor] || [];
    const benchmarkValues = Array.isArray(performance.benchmarkCurve) ? performance.benchmarkCurve : [];
    const all = [...factorValues, ...benchmarkValues].filter(finite).map(Number);
    if (!all.length) {
      $("#performance-chart").innerHTML = '<p class="empty-row">Python payload에 표시할 성과 곡선이 없습니다.</p>';
      return;
    }
    const width = 900;
    const height = 350;
    const margin = { top: 24, right: 24, bottom: 40, left: 58 };
    const count = Math.max(factorValues.length, benchmarkValues.length, 2);
    let min = Math.min(...all);
    let max = Math.max(...all);
    if (min === max) { min -= 0.1; max += 0.1; }
    const padding = (max - min) * 0.08;
    min -= padding;
    max += padding;
    const x = (index) => margin.left + index / (count - 1) * (width - margin.left - margin.right);
    const y = (value) => margin.top + (max - value) / (max - min) * (height - margin.top - margin.bottom);
    const ticks = Array.from({ length: 5 }, (_, index) => min + (max - min) * index / 4);
    const grid = ticks.map((value) => `
      <line x1="${margin.left}" x2="${width - margin.right}" y1="${y(value)}" y2="${y(value)}" class="chart-grid-line" />
      <text x="${margin.left - 10}" y="${y(value) + 4}" text-anchor="end" class="chart-axis-label">${fmtNumber(value, 2)}</text>`).join("");
    const dates = performance.dates || [];
    $("#performance-chart").innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(row.factor)} 누적 성과">
        ${grid}
        <path d="${svgPath(benchmarkValues, x, y)}" class="chart-line-benchmark" />
        <path d="${svgPath(factorValues, x, y)}" class="chart-line-factor" />
        <text x="${margin.left}" y="${height - 10}" class="chart-axis-label">${escapeHtml(dates[0] || "")}</text>
        <text x="${width - margin.right}" y="${height - 10}" text-anchor="end" class="chart-axis-label">${escapeHtml(dates.at(-1) || "")}</text>
      </svg>
      <div class="chart-legend"><span class="legend-key">${escapeHtml(row.factor)} · ${escapeHtml(policyLabel(state.payload, row.policy_id))}</span><span class="legend-key benchmark">${escapeHtml(state.payload.data.benchmark)}</span></div>`;
  }

  function renderFactorDetail() {
    const row = detailRankingRow();
    if (!row) return;
    const definition = definitionFor(row.factor);
    $("#detail-title").textContent = `${row.factor} × ${policyLabel(state.payload, row.policy_id)}`;
    $("#factor-formula").textContent = definition.formula || definition.definition || "정의 미표기";
    $("#factor-description").textContent = definition.description || "설명 미표기";
    $("#factor-category").textContent = row.category || definition.category || "other";
    const metrics = [
      ["선택 점수", fmtNumber(row.selection_score, 1), "Python joint score"],
      ["기본 합성", fmtNumber(row.base_composite_score, 1), "절대 guardrail 전"],
      ["CAGR", fmtPercent(row.cagr), "비용 차감"],
      ["Sharpe", fmtNumber(row.sharpe), "exact daily risk"],
      ["Sortino", fmtNumber(row.sortino), "하방 위험"],
      ["Calmar", fmtNumber(row.calmar), "CAGR / |MDD|"],
      ["MDD", fmtPercent(row.max_drawdown), "최대 낙폭"],
      ["회전율", fmtPercent(row.annualized_turnover), "Python 연환산"],
      ["비용 drag", fmtPercent(row.annualized_cost_drag), "Python 연환산"],
    ];
    $("#factor-metrics").innerHTML = metrics.map(([label, value, context]) => `<article class="metric-card"><span>${label}</span><strong>${value}</strong><small>${context}</small></article>`).join("");
    const scoreWeights = state.payload.selectionMethod.weights || {};
    $("#component-bars").innerHTML = Object.entries(COMPONENT_LABELS).map(([key, label]) => {
      const score = row[`${key}_score`];
      const weight = Number(scoreWeights[key] || 0);
      return `
        <div class="component-row">
          <div class="component-label"><span>${label}</span><span>${fmtNumber(score, 1)} × ${fmtPercent(weight, 0)}</span></div>
          <span class="bar-track"><span class="bar-fill" style="width:${finite(score) ? Math.max(0, Math.min(100, Number(score))) : 0}%"></span></span>
        </div>`;
    }).join("");
    renderPerformanceChart(row);
    renderRiskDiagnostics();
  }

  function renderRiskDiagnostics() {
    const payload = state.payload;
    const row = detailRankingRow();
    if (!row) return;
    const isSelectedPair = row.selected === true
      && row.factor === payload.selectedFactor
      && row.policy_id === payload.selectedWeightingPolicy;
    const diagnostics = isSelectedPair ? (payload.contributionDiagnostics || {}) : {};
    const event = diagnostics.maxExactSingleSessionSecurityContribution || {};
    const profile = payload.selectionDecision?.guardrailProfile || {};
    const leaveOne = isSelectedPair && Array.isArray(diagnostics.topLeaveOneSecurity) ? diagnostics.topLeaveOneSecurity : [];
    const statusCounts = payload.factorPolicyRanking.reduce((counts, item) => {
      const status = item.selection_status || item.comparison_status || "unknown";
      counts[status] = (counts[status] || 0) + 1;
      return counts;
    }, {});
    const excludedCount = Object.entries(statusCounts)
      .filter(([status]) => status !== "eligible")
      .reduce((sum, [, count]) => sum + count, 0);
    $("#risk-status-badge").textContent = `${row.selection_status || "미표기"} · 제외 ${fmtCount(excludedCount)}개`;
    const riskMetrics = [
      ["단일 종목·세션 기여", fmtPercent(row.max_abs_security_day_contribution, 2), isSelectedPair ? `${event.symbol || "—"} · ${event.date || "날짜 미표기"}` : "현재 상세 조합 scalar"],
      ["종목 절대기여 점유율", fmtPercent(row.max_security_absolute_contribution_share, 2), isSelectedPair ? (diagnostics.largestAbsoluteContributionSecurity?.symbol || "—") : "현재 상세 조합 scalar"],
      ["Leave-one CAGR 변화", fmtPercent(row.max_abs_leave_one_security_cagr_delta, 2), isSelectedPair ? (diagnostics.maxLeaveOneSecurity?.symbol || "—") : "현재 상세 조합 scalar"],
      ["절대기여 HHI", fmtNumber(row.absolute_contribution_hhi, 4), isSelectedPair ? `${fmtCount(diagnostics.observedReturnCount)}개 관측수익 보존` : "현재 상세 조합 scalar"],
      ["극단 이벤트 제외", fmtCount(statusCounts.extreme_event_excluded || 0), `전체 ${fmtCount(payload.factorPolicyRanking.length)}개 행`],
      ["귀속 잔차 최대", fmtNumber(row.attribution_max_residual, 8), isSelectedPair ? (diagnostics.attributionMethod || "—") : (row.contribution_attribution_method || "—")],
    ];
    $("#risk-metrics").innerHTML = riskMetrics.map(([label, value, context]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${value}</strong><small>${escapeHtml(context)}</small></article>`).join("");

    $("#guardrail-profile-label").textContent = `${profile.id || "—"} · ${profile.policyNeutral ? "정책 중립" : "정책별"} · ${profile.extremeEventAction || "—"}`;
    $("#guardrail-rules-table tbody").innerHTML = (profile.rules || []).map((rule) => {
      const threshold = String(rule.unit || "").includes("fraction") ? fmtPercent(rule.threshold, 2) : fmtNumber(rule.threshold, 4);
      return `<tr><td><strong>${escapeHtml(rule.id)}</strong></td><td>${escapeHtml(rule.metric)}</td><td>${escapeHtml(rule.operator)} ${threshold}</td><td>${escapeHtml(rule.unit || "—")}</td></tr>`;
    }).join("");

    const breaches = [
      ...rowReasonCodes(row),
    ];
    const statusItems = [
      ["상세 조합", `${row.factor} × ${row.policy_id}`],
      ["선택 상태", row.selection_status || row.comparison_status || "—"],
      ["절대 가드레일", row.absolute_guardrail_pass === true ? "통과" : "미통과"],
      ["기여도 가드레일", row.contribution_guardrail_pass === true ? "통과" : "미통과"],
      ["위반·제외 사유", breaches.length ? [...new Set(breaches)].join(" · ") : "없음"],
      ["이벤트 처리", `${profile.extremeEventAction || "—"} · penalty ${fmtNumber(row.extreme_event_penalty_points, 1)}`],
      ["상태별 행 수", Object.entries(statusCounts).map(([status, count]) => `${status} ${count}`).join(" · ")],
    ];
    $("#guardrail-status").innerHTML = statusItems.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");

    $("#max-event-scope").textContent = isSelectedPair ? "선택 조합 관측 결과 · ticker/date 하드코딩 없음" : "선택 조합에서만 상세 이벤트 제공";
    $("#leave-one-scope").textContent = isSelectedPair ? "선택 조합 · 재최적화 없이 실현 기여 제거" : "현재 행은 scalar 민감도만 제공";
    const eventItems = isSelectedPair ? [
      ["종목 / 종료일", `${event.symbol || "—"} / ${event.date || "—"}`],
      ["관측 구간", `${event.intervalStart || "—"} → ${event.date || "—"} · ${fmtCount(event.returnIntervalSessions)}세션`],
      ["시작 비중", fmtPercent(event.startWeight, 2)],
      ["종목 수익", fmtPercent(event.securityReturn, 2)],
      ["포트폴리오 기여", fmtPercent(event.contribution, 2)],
      ["당일 포트폴리오 수익", fmtPercent(event.portfolioReturn, 2)],
      ["관측수익 보존", diagnostics.observedReturnsPreserved === true ? "예" : "아니오"],
    ] : [
      ["상세 범위", "이벤트 ticker/date와 leave-one 목록은 canonical selected pair에만 포함됩니다."],
      ["현재 행 단일 기여", fmtPercent(row.max_abs_security_day_contribution, 2)],
      ["현재 행 leave-one 변화", fmtPercent(row.max_abs_leave_one_security_cagr_delta, 2)],
    ];
    $("#max-event-contract").innerHTML = eventItems.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
    $("#leave-one-table tbody").innerHTML = leaveOne.map((item) => `
      <tr>
        <td><strong>${escapeHtml(item.symbol || "—")}</strong></td>
        <td>${fmtPercent(item.baseCagr, 2)}</td>
        <td>${fmtPercent(item.leaveOneCagr, 2)}</td>
        <td>${fmtPercent(item.absoluteCagrDelta, 2)}</td>
        <td>${escapeHtml(item.method || "—")}${item.reoptimized === false ? " · frozen" : ""}</td>
      </tr>`).join("") || `<tr><td colspan="5">${isSelectedPair ? "Python payload에 leave-one 진단이 없습니다." : "현재 행은 factorPolicyRanking의 leave-one scalar만 표시합니다."}</td></tr>`;
  }

  function renderDataScope() {
    const payload = state.payload;
    const data = payload.data;
    $("#flow-requested").textContent = fmtCount(data.requestedCandidateCount);
    $("#flow-returned").textContent = fmtCount(data.providerReturnedCandidateCount);
    $("#flow-analyzed").textContent = fmtCount(data.analyzedSecurityCount);
    $("#flow-eligible").textContent = fmtCount(data.latestEligibleSecurityCount);
    const priceSourceCounts = payload.priceSources.reduce((counts, row) => {
      const source = String(row.price_source || "unknown");
      counts[source] = (counts[source] || 0) + 1;
      return counts;
    }, {});
    const sourceStatusCounts = payload.sourceHealth.reduce((counts, row) => {
      const status = String(row.status || "unknown");
      counts[status] = (counts[status] || 0) + 1;
      return counts;
    }, {});
    const compactCounts = (counts) => Object.entries(counts)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, count]) => `${key}:${fmtCount(count)}`)
      .join(" · ");
    const items = [
      ["요청 종료일", data.requestedThrough || "—"],
      ["실제 기준일", data.asOf],
      ["관측 시작", data.startDate],
      ["거래일 수", fmtCount(data.observations)],
      ["제공자", data.provider || "—"],
      ["종목별 가격 출처", compactCounts(priceSourceCounts)],
      ["수집 상태", compactCounts(sourceStatusCounts)],
      ["가격 기준", data.priceBasis || "—"],
      ["거래량 기준", data.volumeBasis || "—"],
      ["입력 SHA-256", formatDigestMap(data.inputSha256)],
    ];
    $("#data-contract").innerHTML = items.map(([label, value]) => `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
    const limitations = payload.researchScope?.limitations || [];
    $("#limitations-list").innerHTML = limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    const notes = Array.isArray(data.notes) ? data.notes.join(" · ") : "";
    $("#data-note").textContent = `${modeLabel(data.mode)} · ${evidenceLabel(payload.researchScope?.evidenceStatus)}${notes ? ` · ${notes}` : ""}`;
  }

  function renderMethodology() {
    const payload = state.payload;
    const method = payload.selectionMethod;
    const accounting = payload.gridAccounting || {};
    $("#method-description").textContent = `${fmtCount(accounting.availableIndependentPairCount)}개 유효 독립 팩터×정책 조합을 하나의 Python 점수표에서 직접 비교했습니다. 정책별 집계는 선택에 사용하지 않는 진단 정보입니다.`;
    $("#method-decision").textContent = `${method.version} · ${method.guardrailVersion} · 신호 ${method.signalTiming} → 체결 ${method.executionTiming} → 첫 수익 ${method.returnExposureStarts} · 최소 ${fmtCount(method.minimumObservations)} 관측.`;
    $("#method-weights").innerHTML = Object.entries(method.weights || {}).map(([key, weight]) => `
      <div class="method-weight">
        <span>${COMPONENT_LABELS[key] || key}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${Number(weight) * 100}%"></span></span>
        <strong>${fmtPercent(weight, 0)}</strong>
      </div>`).join("");
  }

  function renderAll() {
    renderOverview();
    renderAllocation();
    renderPolicies();
    renderFactorFilters();
    renderFactorComparison();
    renderFactorDetail();
    renderDataScope();
    renderMethodology();
  }

  async function sha256Hex(bytes) {
    requireCondition(globalThis.crypto?.subtle, "브라우저 SHA-256 검증 기능을 사용할 수 없습니다.");
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
  }

  async function canonicalSha256(value) {
    return sha256Hex(new TextEncoder().encode(canonicalString(value)));
  }

  async function validateIdentityDigest(identity, label) {
    const canonical = typeof identity.canonicalKeyPartsJson === "string"
      ? identity.canonicalKeyPartsJson
      : canonicalString(identity.keyParts);
    const bytes = new TextEncoder().encode(canonical);
    requireCondition(await sha256Hex(bytes) === identity.resultKey, `${label} resultKey가 canonical keyParts SHA-256과 다릅니다.`);
  }

  async function fetchJson(url, label, reference) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${label} HTTP ${response.status}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (reference !== undefined) {
      requireCondition(isRecord(reference), `${label} artifact reference가 없습니다.`);
      requireCondition(bytes.byteLength === reference.bytes, `${label} byte count가 manifest와 다릅니다.`);
      requireCondition(await sha256Hex(bytes) === reference.sha256, `${label} SHA-256이 manifest와 다릅니다.`);
    }
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  }

  async function fetchLocalApiJson(path, options = {}) {
    const url = new URL(path, `${LOCAL_API_BASE_URL}/`).href;
    let response;
    try {
      response = await fetch(url, {
        cache: "no-store",
        method: options.method || "GET",
        headers: {
          Accept: "application/json",
          ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        ...(options.body === undefined ? {} : { body: canonicalString(options.body) }),
      });
    } catch (error) {
      throw new Error(`로컬 API(${LOCAL_API_BASE_URL})에 연결할 수 없습니다: ${error.message}`);
    }
    let body;
    try {
      const bytes = new Uint8Array(await response.arrayBuffer());
      body = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    } catch (error) {
      throw new Error(`로컬 API 응답 JSON이 잘못되었습니다: ${error.message}`);
    }
    if (!response.ok) {
      const detail = body?.error?.message || `HTTP ${response.status}`;
      throw new Error(`로컬 API가 실행을 거절했습니다: ${detail}`);
    }
    return { statusCode: response.status, body };
  }

  function waitForPoll() {
    return new Promise((resolve) => setTimeout(resolve, LOCAL_API_POLL_INTERVAL_MS));
  }

  async function resolveLocalApiResult(submission, token) {
    if (submission.statusCode === 200) return submission.body;
    requireCondition(
      submission.statusCode === 202
        && validSha256(submission.body?.resultKey)
        && typeof submission.body?.statusUrl === "string",
      "로컬 API 제출 응답 계약이 잘못되었습니다.",
    );
    let statusUrl = submission.body.statusUrl;
    while (token === state.loadToken) {
      const statusResponse = await fetchLocalApiJson(statusUrl);
      const status = statusResponse.body;
      requireCondition(status.resultKey === submission.body.resultKey, "로컬 API status resultKey가 제출 결과와 다릅니다.");
      if (status.status === "complete") {
        requireCondition(isRecord(status.result), "완료된 로컬 API status에 canonical 결과가 없습니다.");
        return status.result;
      }
      if (status.status === "failed") {
        throw new Error(`로컬 Python 분석 실패: ${status.error?.message || "원인 미표기"}`);
      }
      requireCondition(status.status === "queued" || status.status === "running", "로컬 API job status가 잘못되었습니다.");
      setInputStatus(`로컬 Python 분석 ${status.status} · ${submission.body.resultKey.slice(0, 12)}…`, "pending");
      await waitForPoll();
      statusUrl = status.statusUrl || statusUrl;
    }
    throw new Error("다른 결과 로드가 시작되어 로컬 API 표시를 취소했습니다.");
  }

  async function loadLocalApiResult(requestedInputs, baseEntry, options = {}) {
    const token = ++state.loadToken;
    const researchInputs = researchInputsFromNormalizedInputs(requestedInputs);
    if (options.historyMode) updateLocation(options.historyMode, baseEntry.resultKey, requestedInputs);
    showLoading("로컬 Python API에서 실제시장 2,700+ 전체 grid를 계산하는 중…");
    setInputStatus(`로컬 API(${LOCAL_API_BASE_URL})에 canonical 입력을 제출하는 중입니다.`, "pending");
    try {
      const submission = await fetchLocalApiJson("/api/runs", {
        method: "POST",
        body: researchInputs,
      });
      const payload = await resolveLocalApiResult(submission, token);
      if (token !== state.loadToken) return;
      const identity = payload.resultIdentity;
      const normalizedInputs = identity?.keyParts?.normalizedInputs;
      requireCondition(isRecord(identity) && isRecord(normalizedInputs), "로컬 API 결과 identity가 없습니다.");
      const entry = {
        resultKey: payload.resultKey,
        normalizedInputs,
        identity,
      };
      await validateIdentityDigest(identity, "local API detail");
      const selected = await validateResult(entry, payload, null, {
        source: "local_api",
        expectedResearchInputs: researchInputs,
      });
      state.entry = entry;
      state.payload = payload;
      state.summary = null;
      state.detailPairKey = pairKey(selected);
      state.category = "all";
      state.search = "";
      fillForm(baseEntry, normalizedInputs, payload.researchInputs);
      $("#result-key").textContent = payload.resultKey;
      setResultSource("local_api");
      updateLocation("replace", baseEntry.resultKey, normalizedInputs);
      renderAll();
      showResult();
      setInputStatus(`로컬 API가 새 Python 결과를 계산했습니다: ${payload.resultKey.slice(0, 12)}…`, "ok");
    } catch (error) {
      if (token !== state.loadToken) return;
      showUnavailable(`${error.message} ${LOCAL_API_REQUIRED}`, requestedInputs, baseEntry);
      console.error(error);
    }
  }

  async function loadEntry(entry, options = {}) {
    const token = ++state.loadToken;
    showLoading("manifest의 정확한 Python detail/summary를 불러오는 중…");
    const detailUrl = new URL(entry.detail.path, state.manifestUrl).href;
    const summaryUrl = new URL(entry.summary.path, state.manifestUrl).href;
    try {
      const [payload, summary] = await Promise.all([
        fetchJson(detailUrl, "detail", entry.detail),
        fetchJson(summaryUrl, "summary", entry.summary),
      ]);
      if (token !== state.loadToken) return;
      await validateIdentityDigest(entry.identity, "manifest/detail/summary");
      const selected = await validateResult(entry, payload, summary);
      state.entry = entry;
      state.payload = payload;
      state.summary = summary;
      state.detailPairKey = pairKey(selected);
      state.category = "all";
      state.search = "";
      fillForm(entry, entry.normalizedInputs, payload.researchInputs);
      $("#result-key").textContent = entry.resultKey;
      setResultSource("static_grid");
      renderAll();
      showResult();
      setInputStatus(`정확히 일치하는 사전 계산 결과를 열었습니다: ${entry.resultKey.slice(0, 12)}…`, "ok");
      if (options.historyMode) updateLocation(options.historyMode, entry.resultKey, entry.normalizedInputs);
    } catch (error) {
      if (token !== state.loadToken) return;
      showUnavailable(`결과를 표시할 수 없습니다: ${error.message}`, entry.normalizedInputs, entry);
      console.error(error);
    }
  }

  function bindControls() {
    if (state.controlsBound) return;
    state.controlsBound = true;
    $("#input-result-key").addEventListener("change", (event) => {
      const entry = entryByResultKey(state.manifest, event.target.value);
      if (entry) {
        fillForm(entry);
        setInputStatus("스냅샷 입력을 채웠습니다. 적용 버튼을 눌러 정확한 결과를 여세요.", "pending");
      }
    });
    $("#input-evaluation-years").addEventListener("change", (event) => {
      if (finite(event.target.value)) $("#input-evaluation-window-days").value = String(Math.round(Number(event.target.value) * 252));
    });
    $("#input-evaluation-window-days").addEventListener("change", (event) => {
      if (finite(event.target.value)) $("#input-evaluation-years").value = (Number(event.target.value) / 252).toFixed(2).replace(/\.00$/, "");
    });
    $("#research-input-form").addEventListener("submit", (event) => {
      event.preventDefault();
      try {
        const request = readFormRequest();
        if (!request.entry) {
          const apiRequest = localApiRequestFromStaticState(state.manifest, request.requestedInputs);
          loadLocalApiResult(apiRequest.requestedInputs, apiRequest.baseEntry, { historyMode: "push" });
          return;
        }
        loadEntry(request.entry, { historyMode: "push" });
      } catch (error) {
        showUnavailable(`${error.message} ${LOCAL_API_REQUIRED}`);
      }
    });
    $("#reset-default-inputs").addEventListener("click", () => {
      const entry = entryByResultKey(state.manifest, state.manifest.defaultResultKey);
      fillForm(entry);
      loadEntry(entry, { historyMode: "push" });
    });
    $("#category-filter").addEventListener("change", (event) => {
      state.category = event.target.value;
      renderFactorComparison();
    });
    $("#factor-search").addEventListener("input", (event) => {
      state.search = event.target.value.trim();
      renderFactorComparison();
    });
    window.addEventListener("popstate", () => loadFromLocation());
  }

  async function loadFromLocation(options = {}) {
    const request = requestFromSearch(state.manifest, window.location.search);
    if (!request.baseEntry) {
      showUnavailable(request.error);
      return;
    }
    if (!request.entry) {
      const apiRequest = localApiRequestFromStaticState(state.manifest, request.requestedInputs);
      await loadLocalApiResult(apiRequest.requestedInputs, apiRequest.baseEntry, { historyMode: "replace" });
      return;
    }
    await loadEntry(request.entry, {
      historyMode: options.replaceHistory || request.recoveredFromRotatedResult ? "replace" : null,
    });
  }

  async function load() {
    initTheme();
    showLoading("정적 grid manifest를 불러오는 중…");
    try {
      state.manifestUrl = new URL(MANIFEST_URL, window.location.href);
      state.manifest = validateManifest(await fetchJson(state.manifestUrl.href, "manifest"));
      populateResultOptions(state.manifest);
      bindControls();
      await loadFromLocation({ replaceHistory: !window.location.search });
    } catch (error) {
      showUnavailable(`정적 grid를 사용할 수 없습니다: ${error.message}`);
      console.error(error);
    }
  }

  if (typeof globalThis !== "undefined") {
    globalThis.__MFL_WEB_TESTS__ = {
      INPUT_FIELDS,
      LOCAL_API_REQUIRED,
      LOCAL_API_BASE_URL,
      canonicalString,
      validateManifest,
      resolveExactEntry,
      requestFromSearch,
      searchForRequest,
      researchInputsFromNormalizedInputs,
      localApiRequestFromStaticState,
      validateGridAccounting,
      validateResult,
      fetchJson,
      fetchLocalApiJson,
      resolveLocalApiResult,
      rowReasonCodes,
    };
  }

  if (hasDom) load();
})();
