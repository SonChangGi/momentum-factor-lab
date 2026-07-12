# Momentum Factor Lab

미국 개별주 2,700개 이상을 대상으로 모멘텀 팩터와 비중 정책을 같은 조건에서 전수 비교하는 연구 도구입니다. 계산의 canonical source는 Python이며, 정적 웹은 사전 계산된 결과를 선택하고 표시만 합니다.

이 프로젝트가 내놓는 비중은 마지막 실제 입력일 신호로 만든 **다음 세션 종가용 연구 목표**입니다. 실제 체결 또는 개인화된 투자 권고가 아닙니다.

데이터 모드는 `live_market`, `local_file`, `demo`로 명시적으로 구분하며 서로를 fallback으로 사용하지 않습니다.

## 핵심 계약

- 데이터 기준일은 시스템 날짜가 아니라 가격 패널의 마지막 실제 관측일입니다.
- 실제시장 실행은 패키지 후보군 전체를 요청합니다. `max_price_symbols`가 없는 정적 배포는 분석 종목 2,700개 미만이면 실패합니다.
- 실제시장 수집 실패를 demo나 기존 정적 결과로 대체하지 않습니다.
- 200종목 demo는 테스트 전용이며 실제시장 grid에 게시할 수 없습니다.
- 64개 팩터를 계산하고 compatibility alias 3개를 뺀 61개 독립 팩터를 선택 후보로 사용합니다.
- 네 정책을 모두 실행해 `61 × 4 = 244`개 독립 팩터–정책 조합을 먼저 만듭니다.
- 정책을 먼저 고르지 않습니다. 모든 유효 조합을 하나의 모집단에서 한 번만 점수화해 `(factor, policy)` 한 쌍을 직접 선택합니다.
- `equal_weight`도 다른 정책과 동등한 후보이며 다른 정책의 허용선을 정하지 않습니다.
- 정책별 중앙값은 선택에 쓰지 않는 진단 자료입니다.
- 신호·체결·수익 시점은 `t 종가 → t+1 종가 체결 → t+1~t+2 첫 시장수익`입니다.
- 역사 백테스트와 현재 목표는 동일한 target-weight kernel을 사용합니다.
- 현금을 포함한 one-way turnover와 비용을 동일한 회계식으로 계산합니다.
- quote gap을 0% 수익으로 채우지 않습니다. 종목별 share sleeve를 유지하고 valuation이 가능한 관측 구간에서만 수익을 확정합니다.
- 비용, 현금, turnover, quote gap, 데이터 provenance를 결과에 보존합니다.

## 비중 정책

1. `equal_weight`
   - Top-N 동일가중

2. `capped_linear_rank`
   - 동점 인식 선형 순위 강도

3. `capped_vol_adjusted_rank`
   - 순위 강도를 신호일까지의 후행 연율 변동성으로 조정

4. `score_liquidity_rank`
   - 팩터 점수 percentile 60% + 후행 raw-dollar-volume percentile 40% + floor
   - 규모 또는 현재 시가총액을 사용하지 않습니다.

모든 정책은 종목별 최대 비중을 적용하고, 수용하지 못한 예산은 현금으로 남깁니다. Top-N 경계 동점은 신호일까지의 후행 거래대금 내림차순, symbol 오름차순으로 결정합니다. 필요한 tie-break 입력이 없으면 임의 종목을 고르지 않고 해당 target을 unavailable로 둡니다.

## 공동 선택과 절대 가드레일

유효한 244개 독립 조합의 net Sortino, Calmar, MDD, CAGR, Sharpe, subperiod stability를 동일 모집단에서 robust percentile로 변환합니다. 다음 정책 중립 절대 기준을 각 조합에 적용합니다.

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

웹과 로컬 API가 공유하는 `ResearchInputs` v1은 다음을 포함합니다.

- 리밸런싱 주기
- 최근 평가 연수와 대응 거래일 창
- Top-N, 최대 종목 비중
- 거래비용, 슬리피지
- 최소 가격·히스토리·평균 거래대금·평균 거래량
- 유동성 lookback과 최소 관측일
- 가격·거래량 결측률
- 최대 일간 절대 수익률 조건
- 최소 Sharpe, 최대 MDD·비용 drag, 최소 유효 종목 수, 최대 HHI·종목 비중
- 최대 종목·단일 세션 기여도, 최대 종목 절대기여 점유율, 최대 leave-one CAGR 변화
- 극단사건 `warn`/`penalize`/`exclude` 조치와 최대 감점

절대 선택 가드레일은 `ResearchInputs` v1의 canonical per-request 필드입니다. Python 실행의 `--selection-*` 기본값과 동일하며, 웹/API 요청이 값을 바꾸면 정규화 입력·selection hash·result key가 함께 바뀌고 전체 grid를 새로 계산합니다.

입력이 바뀌면 전체 팩터–정책 grid, 선택 조합, 성과, turnover, 비용, 현재 종목·점수·비중·현금이 Python에서 다시 계산됩니다.

## 정적 Pages와 로컬 API

정적 Pages는 임의 계산 환경이 아닙니다. 지원되는 실제시장 결과만 다음 sparse manifest에 등록합니다.

```text
docs/data/grid/v1/manifest.json
docs/data/grid/v1/results/<resultKey>.json
docs/data/grid/v1/summaries/<resultKey>.json
```

브라우저는 manifest에서 전체 입력 tuple이 정확히 같은 entry만 정적 결과로 엽니다. 부분 일치나 최근접 preset은 없습니다. 미지원 입력은 기본 `127.0.0.1:8765` loopback Python API에 canonical `ResearchInputs`를 POST하고 완료 상태를 polling한 뒤, actual-market 2,700+·61×4 회계·identity를 다시 검증해 같은 화면에 로컬 API 결과로 구분 표시합니다. API가 실행 중이지 않거나 계약 검증에 실패하면 이전 결과를 숨기고 fail-closed 오류를 표시합니다.

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

cache hit은 canonical schema-v4 결과를 반환하고, 새 장기 실행은 `202`와 status URL을 반환합니다. API도 실제시장·2,700개 이상만 허용하며 demo/static 결과로 대체하지 않습니다.
브라우저 Origin은 프로젝트 Pages(`https://sonchanggi.github.io`)와 loopback만 기본
허용합니다. 다른 검토된 HTTPS origin은 반복 가능한 `--allowed-origin`으로 명시하며,
그 밖의 Origin은 preflight와 본 요청 모두 시장 로드 전에 403으로 차단됩니다.

정적 viewer에서 임의 입력을 실행하려면 위 loopback API를 먼저 시작합니다. API 결과 URL은 manifest에 없는 동적 result key를 정적 preset처럼 가장하지 않습니다. URL의 base result는 최신 default preset으로 유지하고 공개 입력 전체를 기록하므로, 새로고침·공유 시 같은 최신 조건을 API에서 다시 실행합니다.
각 정적 entry의 안정적인 `presetId`도 URL에 기록하므로 일일 갱신으로 content-addressed
result key가 교체·정리된 뒤에도 같은 rolling preset과 공개 입력을 새 manifest에서 복원합니다.

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

- `outputs/.../momentum_factor_results_*.json`: canonical schema-v4 결과
- `outputs/.../input/*.csv.gz`: 선택적 실제 입력 패널
- `outputs/.../input/market_data_manifest.json`: 파일·행렬 SHA-256, 실제 as-of, 후보 수, read contract
- `docs/data/grid/v1/manifest.json`: 지원 입력과 content-addressed 결과 목록
- `docs/data/dashboard.json`, `docs/data/summary.json`: default entry의 byte-identical migration alias
- `docs/index.html`, `docs/assets/*`: 정적 viewer

schema-v4에는 다음이 포함됩니다.

- 요청→제공자 반환→분석→최신 적격 funnel
- 244개 독립 조합의 완전성 및 정확한 제외 사유 회계
- alias 12개 진단 행을 포함한 256개 전체 factor-policy 행
- 공동 component score, 절대 가드레일, penalty, selection score, rank
- 선택된 팩터·정책과 선택 이유
- 종목별 기여도·집중도·leave-one sensitivity
- 현재 연구 목표, 마지막 백테스트 보유, 현금, turnover, 비용
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
  --volume-basis split_adjusted
```

## 검증

```bash
uv run pytest -q
uv run ruff check momentum_factor_lab tests scripts
uv run python -m compileall -q momentum_factor_lab tests
node scripts/test_web_contract.mjs
git diff --check
```

## 연구 한계

- 현재 상장 종목 중심 입력은 역사적 구성종목·상장폐지·ticker reuse를 완전히 복원하지 못합니다.
- 동일 후행 표본에서 다수 조합을 비교하므로 선택 편향이 있습니다.
- quote gap 내부의 일별 수익률은 추정하지 않습니다.
- 무료 제공자의 adjustment, symbol mapping, 지연, rate limit 차이가 남을 수 있습니다.
- walk-forward/OOS/embargo와 완전한 PIT universe는 이번 도구의 범위 밖이며 위 한계를 제거했다고 주장하지 않습니다.

모든 결과는 연구용이며 투자·세무·법률 조언이 아닙니다.
