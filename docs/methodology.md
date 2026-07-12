# Momentum Factor Lab methodology

## 연구 질문

같은 실제 시장 입력, eligibility, 평가기간, 리밸런싱, 비용 조건에서 어떤 모멘텀 팩터와 비중 정책의 조합이 가장 견고한 후행 결과를 보였는지 비교합니다. 결과는 동일 표본의 설명적 연구이며 미래 수익이나 실제 주문을 뜻하지 않습니다.

## 데이터와 기준일

- 기본 후보군은 현재 상장 미국 개별주 2,700개 이상입니다.
- 라이브 실행은 후보 전체를 요청하며 내부에서 200개로 자르지 않습니다.
- 팩터 수익률은 adjusted close를 사용합니다.
- 거래대금은 provider raw close × raw share volume을 사용하고 필요한 proxy 수를 공개합니다.
- `data.asOf`는 마지막 실제 가격 관측일입니다. 요청 종료일이나 생성일로 덮어쓰지 않습니다.
- 실제시장 수집 실패는 demo나 정적 이전 결과로 대체하지 않습니다.

시장 스냅샷 v2는 adjusted prices, raw closes, share volumes, dollar volumes와 요청
universe 메타데이터, 종목별 가격 공급자(`priceSources`)·수집 source
health(`dataSources`)를 별도 저장합니다. 모든 파일 SHA-256과 행렬·ordered symbol·canonical
record SHA-256을 함께 기록하며, 검증된 snapshot replay는 모든 hash, universe 순서,
후보 수와 actual as-of가 일치할 때만 허용합니다. 따라서 같은 스냅샷에서 파생한 rolling
preset도 refresh universe의 종목명과 원래의 Yahoo/Nasdaq/Stooq/FDR provenance를 잃지
않습니다.

## Eligibility

각 신호일 `t`에 다음 후행 조건을 만족하는 종목만 후보가 됩니다.

- 유효한 양수 adjusted close와 최소 가격
- 최소 관측 히스토리
- 최근 가격·거래량 결측률 한도
- 최근 품질 창의 절대 일수익률 한도
- 후행 거래대금과 최소 유효 관측일

미래 사건을 과거에 역적용하지 않습니다. 큰 실제 수익은 기존 보유 sleeve의 관측수익에서 삭제하지 않고, 관측된 날의 종가 신호부터 후행 품질 창이 끝날 때까지만 신규 target eligibility에 영향을 줍니다.

## 팩터 카탈로그와 grid 완전성

총 64개 팩터 중 compatibility alias 3개는 독립 선택에서 제외합니다.

- `acceleration` → `accel_3m_vs_6m`
- `short_acceleration` → `accel_1m_vs_3m`
- `relative_strength_6m` → `mom_6m`

독립 팩터 61개와 정책 4개의 Cartesian product 244개를 먼저 생성합니다. 각 기대 조합은 정확히 한 행이어야 하며 누락은 데이터 부족이 아니라 구현 오류입니다. 각 독립 행은 `available` 또는 구조화된 `excluded` 사유를 가져야 합니다. alias 12개 행은 별도 진단 회계로 유지합니다.

## 시점·회계 계약

1. Signal: close `t`
2. Execution: next available session close `t+1`
3. First market exposure return: close `t+1` → close `t+2`

보유는 종목별 share sleeve와 cash sleeve로 유지합니다. 중간 quote gap이 있으면 그 날짜의 종목수익을 0으로 발명하지 않습니다. 다음 완전 valuation일의 관측 구간 수익이 이전 완전 NAV 이후 변화를 catch up 합니다. Terminal quote가 없으면 ending NAV와 이에 의존하는 CAGR·Calmar는 unavailable입니다.

```text
one_way_turnover = 0.5 × (
  Σ |target_stock - drifted_pretrade_stock|
  + |target_cash - drifted_pretrade_cash|
)
```

```text
modeled_cost = one_way_turnover
             × (transaction_cost_bps + slippage_bps) / 10000
```

비용은 체결일에 한 번만 차감합니다. 첫 신호 전 cash warm-up은 팩터 성과 관측치가 아닙니다.

## 비중 정책

### `equal_weight`

Top-N에 같은 raw score를 주고 종목 상한을 적용합니다.

### `capped_linear_rank`

동점 인식 선형 rank strength를 사용합니다. 같은 팩터 점수는 같은 강도를 받습니다.

### `capped_vol_adjusted_rank`

```text
raw_i = tie_aware_rank_strength_i
      / clipped_trailing_annualized_volatility_i
```

기본 후행 창은 63거래일, 최소 42관측, 변동성 floor 10%, cap 100%입니다.

### `score_liquidity_rank`

```text
raw_i = floor
      + 0.60 × factor_score_percentile_i
      + 0.40 × trailing_raw_dollar_volume_percentile_i
```

규모·현재 시가총액·부분 market-cap fallback을 사용하지 않습니다.

### Top-N 경계 동점

팩터 점수가 Top-N 경계를 가로질러 동률이면 trailing raw-dollar-volume 내림차순, symbol 오름차순으로 멤버십을 결정합니다. 필요한 거래대금이 없으면 target을 unavailable로 둡니다.

## 팩터–정책 공동 선택

정책을 먼저 고른 뒤 팩터를 고르는 계층 선택을 사용하지 않습니다.

1. 244개 기대 독립 조합을 전부 계산합니다.
2. 정책 입력, 현재 target, valuation, exact daily-risk, 체결 coverage를 평가합니다.
3. 유효 조합 전체를 하나의 모집단으로 합칩니다.
4. Sortino, Calmar, MDD, CAGR, Sharpe, stability를 한 번만 robust percentile로 변환합니다.
5. 절대 가드레일과 extreme-event 규칙을 조합별로 적용합니다.
6. `selection_score`와 결정론 tie-break로 `(factor, policy)` 한 쌍을 직접 선택합니다.

정책별 중앙 성과는 `policyDiagnostics`에만 기록하며 선택·순위 의미가 없습니다. `equal_weight`는 동등한 후보일 뿐 허용선 기준이 아닙니다.

## 절대·버전형 가드레일

가드레일 profile은 version과 다음 rule metadata를 갖습니다.

- rule ID
- 대상 metric
- operator
- threshold
- unit

기본 규칙은 최소 Sharpe, 최대 drawdown magnitude, 최대 연율 비용 drag, 최소 effective names, 최대 HHI·종목 비중, 완전한 입력·체결·현재 target·기여도 진단, 최대 종목/일 기여도, 최대 종목 절대기여 점유율, 최대 leave-one CAGR 변화를 포함합니다.

표준 가드레일 위반은 선택에서 제외합니다. 극단사건 규칙은 `warn`, `penalize`, `exclude` 중 versioned action을 사용합니다. 관측수익 자체는 어느 action에서도 제거하지 않습니다. 절대 임계값과 action은 Python의 `--selection-*` 기본값이면서 공개 `ResearchInputs` v1의 canonical per-request 필드입니다. 요청별 값은 정규화 입력과 selection hash에 포함되므로 변경 시 별도 result key로 전체 grid를 다시 계산합니다.

## 종목별 기여도와 민감도

각 valuation interval의 exact contribution은 기존 share sleeve 회계에서 계산합니다.

```text
security contribution_i
  = pretrade_sleeve_value_i / previous_complete_nav
  - previous_complete_weight_i
```

현금과 비용 contribution을 더하면 net portfolio return과 일치해야 합니다. 단일 세션 event와 multi-session quote-gap recovery event를 구분합니다.

기간 종목 집중도는 다음으로 계산합니다.

```text
security_absolute_contribution_share_i
  = Σ_t |contribution_i,t|
  / Σ_j Σ_t |contribution_j,t|
```

Leave-one sensitivity는 실제 경로·비용을 동결한 realized-contribution deletion입니다. 종목을 제거한 뒤 신호·순위·비중을 재최적화한 반사실 결과가 아닙니다.

## 현재 연구 목표

`currentResearchTarget`은 마지막 실제 입력일 점수를 선택된 정책의 역사 kernel에 넣은 다음 세션 목표입니다. `backtestHeldPortfolio`는 마지막 체결 이후 as-of까지 drift된 연구 보유입니다.

`currentTransition`은 마지막 관측 종가 기준 두 상태 사이의 indicative turnover/cost입니다. 다음 종가 전의 실제 pre-trade drift와 비용은 아직 알 수 없으므로 `actualNextClosePretradeDriftKnown=false`입니다.

## Schema v4와 identity

Canonical payload는 다음을 포함합니다.

- `resultIdentity`와 top-level `resultKey`
- `researchInputs`
- `factorPolicyRanking`
- `gridAccounting`
- `policyDiagnostics`
- `weightingPolicyRegistry`
- `contributionDiagnostics`
- `currentResearchTarget`, `backtestHeldPortfolio`, `currentTransition`
- 데이터 funnel, source health, input hashes, runtime, peak RSS

이전 `factorRanking`, `policyFactorMetrics`, `weightingPolicyComparison`, `modelPortfolio` 중복 필드는 허용하지 않습니다.

브라우저는 Python-selected 행과 Python target을 표시할 뿐 winner, weight, turnover, cost를 다시 계산하지 않습니다.

## 정적 grid와 arbitrary inputs

정적 Pages는 `grid/v1/manifest.json`에 등록된 sparse, content-addressed 실제시장 결과만 제공합니다. `keyParts`는 Python과 JavaScript가 공유하는 RFC 8785 JCS로 canonicalize하며, manifest와 detail/summary의 전체 identity, canonical bytes, artifact bytes, SHA-256을 검증합니다. 같은 JSON 구조라도 공백이나 다른 숫자 표기를 사용한 비정규 identity transport는 거절합니다. 2,700개 미만 또는 synthetic 결과는 게시할 수 없습니다.

전체 입력 tuple과 정확히 맞지 않는 URL 상태는 정적 결과로 대체하지 않습니다. 가장 가까운 preset을 사용하지 않고, 별도의 loopback Python API에 canonical `ResearchInputs`를 제출해 canonical engine을 실행합니다. 브라우저는 `202` status를 polling하고 완료 결과의 actual 2,700+·identity·61×4 grid·exact exclusion reasons를 검증한 뒤에만 표시합니다. 동적 API result key는 manifest preset으로 가장하지 않으며, URL은 최신 default base와 반환된 공개 입력을 보존해 reload/share 시 같은 최신 조건을 다시 실행합니다.

정기 publication은 설정에 선언된 모든 `static_grid_presets`를 한 번의 검증된 최신 actual-market 스냅샷에서 다시 계산합니다. 현재 preset은 최신 Top‑20, 최신 Top‑30, 직전 7개 완료 세션의 Top‑20입니다. 각 preset은 동일 Python engine과 독립 identity/cache key를 사용하고, writer는 완성된 bounded manifest를 원자적으로 교체한 뒤 참조되지 않는 content-addressed artifact와 비활성 alias를 제거합니다.

## 캐시 무효화

시장 cache는 TTL/refresh, 실제 as-of, 반환 종목, component bytes/hash를 검증합니다. 분석 cache key는 연구 입력, 시장 내용, 유니버스, 팩터, 정책, 선택·가드레일, 엔진 source digest를 포함합니다. 같은 날짜의 공급자 보정도 matrix hash가 바뀌면 다른 result key가 됩니다.

## 연구 한계

- 동일 표본에서 다수 조합을 비교하는 선택 편향
- 현재 상장 종목 기반 survivorship 한계
- 역사적 구성종목·상장폐지·ticker history의 불완전성
- quote gap 내부 일별 수익률을 추정하지 않음
- 무료 제공자의 adjustment·symbol mapping·지연 차이
- walk-forward/OOS/embargo와 완전한 PIT universe는 현 범위 밖임

이 한계는 결과에 명시하며, 현재 구현이 이를 해결했다고 주장하지 않습니다.
