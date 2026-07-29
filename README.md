# Momentum Factor Lab

미국 개별주 2,700개 이상을 대상으로 64개 모멘텀 팩터를 같은 조건과 같은 고정 비중 방법으로 비교하는 연구 도구입니다. 계산의 canonical source는 Python이며, 정적 웹은 사전 계산된 결과를 선택하고 표시합니다. 공개 preset에 없는 입력은 loopback Python API 또는 명시적으로 설정된 공통 control API가 같은 엔진으로 다시 실행합니다.

이 프로젝트가 내놓는 비중은 마지막 실제 입력일 신호로 만든 **다음 세션 종가용 연구 목표**입니다. 실제 체결 또는 개인화된 투자 권고가 아닙니다.

데이터 모드는 `live_market`, `local_file`, `demo`로 명시적으로 구분하며 서로를 fallback으로 사용하지 않습니다.

## 핵심 계약

- 데이터 기준일은 시스템 날짜가 아니라 가격 패널의 마지막 실제 관측일입니다.
- 실제시장 실행은 패키지 후보군 전체를 요청합니다. `max_price_symbols`가 없는 정적 배포는 분석 종목 2,700개 미만이면 실패합니다.
- 실제시장 수집 실패를 demo나 기존 정적 결과로 대체하지 않습니다.
- 200종목 demo는 테스트 전용이며 실제시장 grid에 게시할 수 없습니다.
- 64개 팩터를 계산하고 compatibility alias 3개를 뺀 61개 독립 팩터를 선택 후보로 사용합니다.
- 독립 팩터 61개를 하나의 고정 비중 방법으로 각각 한 번만 실행하고, 같은 모집단에서 최고 팩터를 선택합니다.
- 팩터 선택 단계에서 비중 정책을 최적화하지 않습니다. Top-N·비중 상한·기간·비용·필터·가드레일이 바뀌면 64개 팩터 전체를 Python으로 다시 계산합니다.
- 신호·체결·수익 시점은 `t 종가 → t+1 종가 체결 → t+1~t+2 첫 시장수익`입니다.
- 역사 백테스트와 현재 목표는 동일한 target-weight kernel을 사용합니다.
- 현금을 포함한 one-way turnover와 비용을 동일한 회계식으로 계산합니다.
- quote gap을 0% 수익으로 채우지 않습니다. 종목별 share sleeve를 유지하고 valuation이 가능한 관측 구간에서만 수익을 확정합니다.
- 비용, 현금, turnover, quote gap, 데이터 provenance를 결과에 보존합니다.

## 고정 비중 방법

`score_liquidity_rank` 하나만 사용합니다.

```text
raw_i = 0.05
      + 0.70 × factor_score_percentile_i
      + 0.30 × trailing_raw_dollar_volume_percentile_i
```

두 입력은 편입 후보 안에서 동점을 보존하는 percentile rank로 변환합니다. 시가총액은 이 고정 방법에 사용하지 않으며, 외부 접근 실패를 현재값 역복사나 제3자 proxy로 대체하지 않습니다. 필요한 후행 거래대금이 없으면 해당 포트폴리오는 현금 100%로 실패-폐쇄됩니다.

종목당 최대 비중을 적용하고, 상한 때문에 수용하지 못한 예산은 현금으로 남깁니다. Top-N 경계 동점은 신호일까지의 후행 거래대금 내림차순, symbol 오름차순으로 결정합니다.

## 최고 팩터 선택과 절대 가드레일

고정 방법으로 계산 가능한 독립 팩터들의 net Sortino, Calmar, MDD, CAGR, Sharpe, subperiod stability를 동일 모집단에서 robust percentile로 변환합니다. 다음 절대 기준을 각 팩터에 적용합니다.

- 최소 Sharpe
- 최대 drawdown magnitude
- 최대 연율 비용 drag
- 최소 effective names
- 최대 target HHI와 종목 비중
- 정책 입력·체결·현재 target·기여도 진단 완전성
- 최대 단일 종목·단일 세션 절대 기여도
- 최대 종목별 전체 절대 기여도 점유율
- 최대 leave-one-security CAGR 변화

가드레일에는 version, rule ID, 연산자, 단위, 임계값이 포함됩니다. 극단사건 관측수익은 백테스트에서 삭제하지 않습니다. 사용자는 `--selection-min-sharpe`, `--selection-max-target-hhi`, `--selection-max-abs-security-day-contribution`, `--selection-max-security-absolute-contribution-share`, `--selection-max-leave-one-security-cagr-delta`, `--selection-extreme-event-action` 등 `--selection-*` 실행 인자로 절대 한도와 조치를 설정할 수 있습니다. 이 값들은 정규화 입력과 selection hash에 포함되며, 변경하면 별도 result key로 전체 grid를 다시 계산합니다.

종목 기여도는 전체 `date × security × candidate` cube를 저장하지 않고 share-sleeve 회계 안에서 스트리밍으로 누적합니다. leave-one 결과는 재최적화가 아니라 실제 거래 경로를 고정한 realized-contribution deletion입니다.

## 설치

```bash
uv sync --extra live --extra dev
```

## 실제시장 전체 실행

```bash
uv run python -m momentum_factor_lab.cli run \
  --live \
  --start-date 2016-01-01 \
  --universe-profile large_liquid \
  --universe-source-mode packaged \
  --min-avg-dollar-volume 5000000 \
  --max-price-symbols none \
  --refresh-market-data \
  --export-input-snapshot \
  --output-dir outputs/daily-dashboard \
  --site-dir outputs/daily-dashboard/site \
  --json
```

`--end-date`를 생략하면 요청 종료일은 실행일입니다. 결과의 `data.asOf`는 제공자가 실제로 반환한 마지막 완료 세션입니다.
일반 `run` 명령은 공개 `docs`의 3-preset grid를 단일 결과로 축소할 수 없도록
`--site-dir docs`를 거절합니다. 공개 grid 갱신은 전체 preset을 다시 만드는
`scheduled-dashboard` 또는 완전한 검토 artifact 집합을 받는 `build-static-grid`만 사용합니다.

## 연구 입력

웹과 Python 실행 경로가 공유하는 `ResearchInputs` v2는 다음을 포함합니다.

- 리밸런싱 주기
- 평가 창(거래일, 252–2,520일)
- Top-N, 최대 종목 비중
- 거래비용, 슬리피지
- 최소 가격·히스토리·평균 거래대금·평균 거래량
- 유동성 lookback과 최소 관측일
- 가격·거래량 결측률
- 최대 일간 절대 수익률 조건
- 최소 Sharpe, 최대 MDD·비용 drag, 최소 유효 종목 수, 최대 HHI·종목 비중
- 최대 종목·단일 세션 기여도, 최대 종목 절대기여 점유율, 최대 leave-one CAGR 변화
- 극단사건 `warn`/`penalize`/`exclude` 조치와 최대 감점

절대 선택 가드레일은 `ResearchInputs` v2의 canonical per-request 필드입니다. Python 실행의 `--selection-*` 기본값과 동일하며, 웹/API 요청이 값을 바꾸면 정규화 입력·selection hash·result key가 함께 바뀌고 전체 grid를 새로 계산합니다.

입력이 바뀌면 전체 팩터 랭킹, 최고 팩터, 각 팩터의 성과와 포트폴리오, turnover, 비용, 종목·점수·비중·현금이 Python에서 다시 계산됩니다. 화면의 ‘사용자 선택 팩터’ 변경은 이미 계산된 같은 실행 안에서 비교 대상을 바꾸며, Python 최고 팩터를 덮어쓰지 않습니다.

## 정적 Pages와 로컬 API

정적 Pages는 임의 계산 환경이 아닙니다. 지원되는 실제시장 결과만 다음 sparse manifest에 등록합니다.

```text
docs/data/grid/v1/manifest.json
docs/data/grid/v1/results/<resultKey>.json
docs/data/grid/v1/summaries/<resultKey>.json
```

브라우저는 manifest에서 전체 입력 tuple이 정확히 같은 entry만 정적 결과로 엽니다. 부분 일치나 최근접 preset은 없습니다. 공개 Pages의 미지원 입력은 배포된 공통 control API가 GitHub Actions/Python worker에 전달합니다. loopback 또는 파일 기반 로컬 미리보기에서는 `127.0.0.1:8765` 로컬 API를 사용합니다. 두 경로 모두 actual-market 2,700+·61개 독립 팩터 회계·고정 비중 방법·identity를 다시 검증한 뒤에만 화면을 바꾸며, 실행이나 계약 검증이 실패하면 현재 검증 결과를 유지합니다.

여러 사전 계산 결과를 하나의 bounded grid로 만들 수 있습니다.

```bash
uv run python -m momentum_factor_lab.cli build-static-grid \
  --artifact result-a.json summary-a.json \
  --preset-id latest-top20 \
  --artifact result-b.json summary-b.json \
  --preset-id latest-top30 \
  --default-result-key <sha256> \
  --site-dir docs
```

정기 실행은 `.github/momentum-dashboard-config.json`의 `static_grid_presets` 전체를 처리합니다. 최신 기본 Top‑20, 최신 Top‑30, 직전 7개 완료 세션 시점 Top‑20을 한 번 수집·검증한 actual-market 스냅샷에서 각각 다시 계산하고, 세 결과를 한 manifest로 원자적으로 교체합니다. 입력·시장 내용·엔진이 그대로인 경우에만 identity가 맞는 분석 cache를 재사용하며, 새 manifest에 없는 content-addressed 파일과 비활성 alias는 제거합니다.
스냅샷 v2는 네 가격·거래량 행렬뿐 아니라 요청 universe 메타데이터, 종목별 가격
source와 수집 source health도 파일 hash로 봉인해 replay합니다. 따라서 두 번째 이후
preset에서도 refresh universe의 종목명과 공급자 provenance가 사라지거나 일반적인
snapshot label로 대체되지 않습니다.

### 정기 갱신·watchdog 상태

`Daily Momentum Dashboard`는 미국 정규장 완료 이후 06:30 KST에 실행합니다.
08:30·10:30·12:30 KST watchdog은 공개 데이터 기준일과 성공 생성 시각을 확인해,
이미 최신인 경우 실제로 건너뛰고 stale 또는 최근 실패 상태일 때만 본 실행을 다시
요청합니다. watchdog이 queue한 dispatch는 시작 시점에도 schedule 의미로 최신
dashboard/status 원격 쌍을 다시 확인해 경합으로 생기는 중복 게시를 막습니다. 사람이
실행하는 수동 dispatch의 `watchdog_origin` 기본값은 `false`이며 이 중복 방지와
무관하게 항상 실행합니다. 분석 cache hit으로 immutable 결과의 `generatedAtUtc`가
유지되는 경우에는, 정확히 같은 result/data/generated identity에 결합된
`available.attemptedAtUtc`를 성공 게시 시각으로 사용합니다.

고정 절대 가드레일을 통과한 팩터가 하나도 없으면 임의 팩터를 선택하거나 임계값을
완화하지 않습니다. 이는 실행 오류가 아니라 fail-closed 분석 결과이므로 workflow는
`docs/data/automation-status.json`에 `degraded`(기존 검증 결과가 없으면
`unavailable`)와 `no_eligible_factor`를 기록하고 정상 종료합니다. 공개 dashboard와
3-preset grid는 마지막 검증 결과를 그대로 유지하며, watchdog은 이 상태를 최근 실패로
보고 다음 제한된 재시도 시점에 다시 실행합니다.

공개 source health에는 로컬 cache 경로를 싣지 않습니다. 생성된 `docs`는 커밋 전에
provider credential 형식과 민감한 JSON 필드를 스캔하며, 탐지된 실제 값은 로그에
출력하거나 push-protection 우회 대상으로 처리하지 않고 게시를 중단합니다. 원격
control run도 immutable artifact와 sidecar를 같은 scanner로 통과한 뒤에만
커밋합니다.

임의 입력은 loopback 전용 로컬 API에서 실행합니다.

```bash
uv run python -m momentum_factor_lab.cli serve-local-api \
  --live \
  --start-date 2016-01-01 \
  --min-avg-dollar-volume 5000000 \
  --host 127.0.0.1 \
  --port 8765
```

API 계약:

- `GET /api/capabilities`
- `POST /api/runs`
- `GET /api/runs/<resultKey>`

cache hit은 canonical schema-v5 결과를 반환하고, 새 장기 실행은 `202`와 status URL을 반환합니다. API도 실제시장·2,700개 이상만 허용하며 demo/static 결과로 대체하지 않습니다.
브라우저 Origin은 프로젝트 Pages(`https://sonchanggi.github.io`)와 loopback만 기본
허용합니다. 다른 검토된 HTTPS origin은 반복 가능한 `--allowed-origin`으로 명시하며,
그 밖의 Origin은 preflight와 본 요청 모두 시장 로드 전에 403으로 차단됩니다.

로컬 정적 viewer에서 임의 입력을 실행하려면 위 loopback API를 먼저 시작합니다. 공개 Pages는 loopback을 호출하지 않습니다. API 결과 URL은 manifest에 없는 동적 result key를 정적 preset처럼 가장하지 않습니다. URL의 base result는 최신 default preset으로 유지하고 공개 입력 전체를 기록하므로, 새로고침·공유 시 같은 최신 조건을 다시 실행할 수 있습니다.
각 정적 entry의 안정적인 `presetId`도 URL에 기록하므로 일일 갱신으로 content-addressed
result key가 교체·정리된 뒤에도 같은 rolling preset과 공개 입력을 새 manifest에서 복원합니다.

## 공통 원격 control API

정적 grid와 loopback API는 그대로 유지합니다. 공개 Pages는
`https://quant-control-api.onrender.com`을 `quant-run-api-base`로 사용하고,
로컬 미리보기는 loopback API를 우선합니다.

```text
GET  /v1/projects/momentum/capabilities
POST /v1/projects/momentum/runs
GET  /v1/runs/<runId>
GET  /v1/runs/<runId>/result
```

원격 요청은 `momentum/v2`의 26개 입력을 전부 보내며 평가 창은
`evaluationWindowDays` 정수로 전달합니다. 부분 입력, 알 수 없는 입력,
fallback을 거절합니다. API가 만든 `configHash`와 worker가 같은 RFC 8785 입력으로
계산한 hash가 다르면 Python을 실행하지 않습니다.

API 프로세스는 장기 분석을 직접 실행하지 않습니다.
`.github/workflows/controlled-analysis.yml`이 기존 `ResearchInputs.apply()`와
기존 Python 계산 경로를 사용하고, 공개 기본 alias를 덮어쓰지 않는 immutable
artifact를 게시합니다. 브라우저는 run/schema/config/data/code/artifact identity와
정확한 byte SHA-256을 모두 확인한 뒤에만 화면 결과를 바꿉니다. 대기·실패·취소·불일치
상태에서는 기존 검증 결과를 계속 표시합니다.

worker callback에는 다음 저장소 secret이 필요합니다.

- `QUANT_CONTROL_API_BASE_URL`
- `QUANT_CONTROL_WORKER_CALLBACK_TOKEN`

세션 액세스 토큰은 브라우저 탭 메모리에서만 사용하며 Web Storage나 URL에 저장하지
않습니다. meta가 비어 있으면 기존 정적 preset/loopback 동작만 사용합니다.

## 캐시와 result identity

시장 수집 캐시와 분석 결과 캐시를 분리합니다.

- 시장 캐시: provider 요청, 종목, TTL, refresh, 실제 as-of, component byte 수와 SHA-256
- 분석 캐시: 정규화 연구 입력, 실제 데이터 hash, as-of, 유니버스 hash, 팩터 hash, 정책 hash/version, 선택·가드레일 hash, 엔진 hash

같은 `asOf`라도 공급자 데이터 한 셀이 바뀌면 시장 component hash와 `resultKey`가 바뀝니다. cache 파일 내부 identity가 파일명과 다르면 재사용하지 않습니다.

정적 full/summary/manifest와 Quant 소비자는 동일한 다음 객체를 사용합니다.

```json
{
  "identityVersion": "momentum-result-identity-v1",
  "resultKey": "<sha256(canonical keyParts)>",
  "keyParts": {"canonicalJsonVersion": "rfc8785-jcs-v1"},
  "canonicalKeyPartsJson": "<RFC 8785 JCS bytes decoded as UTF-8>"
}
```

정적 transport는 `canonicalKeyPartsJson`을 함께 싣습니다. Python publisher와 브라우저·Quant 소비자가 모두 RFC 8785 JCS 표현을 독립적으로 다시 만들고, 문자열의 byte equality와 SHA-256을 확인합니다. 공백 추가나 다른 숫자 표기처럼 같은 JSON 구조의 비정규 표현은 양쪽 artifact가 서로 일치하더라도 거절합니다.

## 산출물

- `outputs/.../momentum_factor_results_*.json`: canonical schema-v5 결과
- `outputs/.../input/*.csv.gz`: 선택적 실제 입력 패널
- `outputs/.../input/market_data_manifest.json`: 파일·행렬 SHA-256, 실제 as-of, 후보 수, read contract
- `docs/data/grid/v1/manifest.json`: 지원 입력과 content-addressed 결과 목록
- `docs/data/dashboard.json`, `docs/data/summary.json`: default entry의 byte-identical migration alias
- `docs/data/automation-status.json`: 최근 정기 분석·게시 상태와 last-good 보존 여부
- `docs/index.html`, `docs/assets/*`: 정적 viewer

schema-v5에는 다음이 포함됩니다.

- 요청→제공자 반환→분석→최신 적격 funnel
- 61개 독립 팩터의 완전성 및 정확한 제외 사유 회계
- compatibility alias 3개를 포함한 64개 팩터 행
- 고정 방법의 component score, 절대 가드레일, penalty, selection score, rank
- `bestFactor`, `factorRanking`: 동일 입력으로 Python이 고른 최고 팩터와 선택 이유
- 종목별 기여도·집중도·leave-one sensitivity
- `bestFactorPortfolio`, `factorPortfolios`: 최고 팩터 및 모든 팩터의 Python 포트폴리오
- 마지막 백테스트 보유, 현금, turnover, 비용
- 입력·유니버스·팩터·정책·선택·엔진 identity

## Demo와 로컬 파일

Demo는 테스트 전용입니다.

```bash
uv run python -m momentum_factor_lab.cli run --demo --demo-symbol-count 200
```

이 명령과 `--max-price-symbols`로 제한한 live smoke는 `docs/data`를 건드리지 않고 `output-dir/site`의 격리 preview에만 씁니다. 전체 실제시장 실행이라도 분석 종목이 2,700개 미만이면 공개 alias를 쓰기 전에 실패합니다.

`build-site`도 기본적으로 `outputs/site-preview`에만 씁니다. `docs`의 default alias와 content-addressed grid를 분리해서 덮어쓰는 경로는 거절하며, 공개용 재구성은 검증된 detail/summary를 함께 받는 `build-static-grid`만 사용합니다.

검토한 조정가격 CSV도 연구 실행에 사용할 수 있지만 actual-market static grid에는 게시할 수 없으며 동일하게 격리 preview만 만듭니다.

```bash
uv run python -m momentum_factor_lab.cli run \
  --prices adjusted_prices.csv \
  --volumes share_volumes.csv \
  --market-caps point_in_time_market_caps.csv \
  --volume-basis split_adjusted
```

## 검증

```bash
uv run pytest -q
uv run ruff check momentum_factor_lab tests scripts
uv run python -m compileall -q momentum_factor_lab tests
MFL_TEST_PAYLOAD=docs/data/grid/v1/latest.json node scripts/test_web_contract.mjs
node scripts/test_web_control_api_contract.mjs
git diff --check
```

## 연구 한계

- 현재 상장 종목 중심 입력은 역사적 구성종목·상장폐지·ticker reuse를 완전히 복원하지 못합니다.
- 동일 후행 표본에서 다수 조합을 비교하므로 선택 편향이 있습니다.
- quote gap 내부의 일별 수익률은 추정하지 않습니다.
- 무료 제공자의 adjustment, symbol mapping, 지연, rate limit 차이가 남을 수 있습니다.
- walk-forward/OOS/embargo와 완전한 PIT universe는 이번 도구의 범위 밖이며 위 한계를 제거했다고 주장하지 않습니다.

모든 결과는 연구용이며 투자·세무·법률 조언이 아닙니다.
