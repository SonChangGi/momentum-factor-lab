# Product and interface design

## 첫 화면의 질문

사용자는 첫 화면에서 다음을 바로 확인할 수 있어야 합니다.

- 실제 데이터 기준일과 requested-through는 언제인가?
- 요청·제공자 반환·분석·최신 적격 종목은 각각 몇 개인가?
- 어떤 연구 입력 tuple을 보고 있는가?
- 어떤 팩터–정책 조합이 직접 선택됐고 이유는 무엇인가?
- 성과·turnover·비용·극단사건 의존성은 어떠한가?
- 현재 다음 세션 연구 목표의 종목·점수·비중·현금은 무엇인가?

## 정보 순서

1. 실제시장/demo/local badge, 실제 as-of, result identity
2. 연구 입력 controls와 지원 snapshot selector
3. 선택된 factor-policy와 선택 이유
4. requested → returned → analyzed → eligible funnel
5. 현재 전체 target holdings, 점수, 비중, 현금, 집중도
6. net performance, turnover, cost, contribution diagnostics
7. 전체 joint factor-policy ranking
8. 선택 의미가 없는 policy diagnostics
9. factor definitions, provenance, 한계

DOM 순서는 모바일에서도 유지하며 CSS로 의미 순서를 뒤집지 않습니다.

## 계산 소유권

- Python JSON이 winner, rank, weight, cash, turnover, cost의 유일한 source입니다.
- 브라우저는 manifest entry 선택, URL 직렬화, 표시·필터만 수행합니다.
- JavaScript에 정책 공식, 팩터 composite, 비중 계산을 복제하지 않습니다.
- policy label, version, description, formula는 Python registry에서 읽습니다.
- summary/detail/manifest/Quant는 동일한 전체 `resultIdentity`를 요구합니다.

## 입력 상태와 URL

- 최초 로드에서 query를 정규화하고 exact manifest entry를 찾습니다.
- 입력 변경은 `history.pushState`, canonical normalization은 `replaceState`를 사용합니다.
- `popstate`로 이전 exact tuple을 복원합니다.
- URL에는 `resultKey`와 모든 공개 연구 입력을 보존합니다.
- 부분 일치나 가장 가까운 preset을 사용하지 않습니다.
- 미지원 tuple이면 이전 결과를 숨기고 loopback Python API에 canonical 입력을 제출합니다.
- API의 queued/running/failed/complete 상태를 표시하고 완료된 actual 2,700+·61×4 결과만 검증 후 렌더링합니다.
- 정적 preset과 로컬 API 결과를 resultKey 옆에 명확히 구분합니다.
- 동적 API resultKey는 manifest key로 쓰지 않습니다. URL base는 최신 default preset, query는 반환된 공개 입력을 사용해 reload/share 시 같은 최신 조건을 다시 실행합니다.

## 정적 grid 상태

정적 viewer가 허용하는 결과는 다음 조건을 모두 만족합니다.

정기 생성기는 설정된 최신 Top‑20·최신 Top‑30·직전 7개 완료 세션 Top‑20 preset을 하나의 검증된 actual-market 스냅샷에서 모두 다시 계산합니다. 단일 default만 게시하거나 이전 preset 파일을 우연히 보존하는 방식은 허용하지 않습니다.

- `schemaVersion: 4`
- 실제시장, non-synthetic
- 분석 종목 2,700개 이상
- bounded `grid/v1` manifest entry
- detail/summary 전체 identity parity
- 파일 bytes와 SHA-256 parity
- 전체 normalized input tuple exact match

지원되는 sparse tuple만 control에서 선택할 수 있습니다. 새로운 Python 결과가 manifest에 등록되기 전에는 지원 상태로 보이지 않습니다.

## 선택 표현

- “정책을 먼저 선택”하는 시각 계층을 사용하지 않습니다.
- 선택 카드는 하나의 `(factor, policy)` 조합과 joint selection score를 보여줍니다.
- `equal_weight`는 기준선이 아니라 peer 후보로 표시합니다.
- 정책별 median 표에는 “진단 전용, 선택에 사용하지 않음”을 명시합니다.
- 제외된 조합은 exact reason code와 guardrail breach를 표시합니다.
- 극단사건 action이 warning/penalty/exclusion 중 무엇이었는지 보여줍니다.

## 현재 목표 표현

- `currentResearchTarget`만 현재 target의 canonical 객체로 사용합니다.
- 별도의 이름으로 같은 객체를 복제하지 않습니다.
- `backtestHeldPortfolio`와 target을 분리합니다.
- `currentTransition`은 마지막 관측 종가 기준 indicative 값이라고 표시합니다.
- 실제 다음 종가 drift는 미래 관측 전 unknown임을 유지합니다.
- unavailable target은 현금 100%, 보유 0개로 fail-closed 표시합니다.

## 시각 언어

- 차분한 연구 도구 톤의 off-white/charcoal 기반과 제한된 accent
- 숫자는 tabular numerals
- 표는 카드 내부 horizontal scroll을 사용하고 page overflow를 만들지 않음
- 선택 상태는 색상만이 아니라 배경·텍스트·아이콘을 함께 사용
- loading, unsupported, contract error를 assistive technology에 노출
- `prefers-reduced-motion`에서 비필수 transition 제거
- light/dark/mobile 모두 같은 의미 대비 유지

## 데이터 모드 언어

- `live_market`: 실제 시장 데이터
- `local_file`: 검토된 로컬 연구 데이터
- `demo`: 합성 테스트 데이터

Demo와 local file은 실제시장 정적 grid에 들어갈 수 없습니다. 수집 실패 시 기존 실제 holdings를 fallback으로 노출하지 않습니다.

## 연구 경계

- 현재 목표는 연구 결과이며 실행 가이드가 아닙니다.
- 브라우저 what-if 계산을 canonical 결과처럼 보여주지 않습니다.
- 같은 표본 선택 편향과 survivorship/PIT 한계를 숨기지 않습니다.
- 현 범위 밖인 walk-forward/OOS/embargo를 구현한 것처럼 표현하지 않습니다.

## Acceptance checklist

- 실제 as-of와 2,700+ 분석 funnel이 첫 화면에 보임
- 모든 공개 입력이 URL round-trip 됨
- exact manifest tuple만 결과를 표시함
- full/summary/manifest identity mismatch가 fail-closed 됨
- 244개 독립 조합의 `available + excluded = expected`, missing 0
- alias 12개가 독립 회계와 분리됨
- 선택된 joint row가 정확히 하나이며 rank 1
- 정책 median은 diagnostic-only
- 절대 guardrail rule metadata와 breach가 보임
- 종목별 기여도, 최대 event, leave-one sensitivity가 보임
- current target holdings/weights/cash가 Python payload와 같음
- 브라우저 source에 winner·ticker·date·정책 결과 하드코딩이 없음
- stale Momentum fallback holdings가 없음
- unsupported tuple은 local API에 canonical request를 제출하고 상태를 표시함
- guardrail·action·penalty를 포함한 모든 공개 입력이 API request와 URL을 round-trip 함
- API 결과의 2,700+·244 independent pairs·12 aliases·exact reason counts가 fail-closed 검증됨
- 표·controls가 page-level overflow를 만들지 않음
- 정적 자료는 actual-market 2,700+이며 demo가 아님
