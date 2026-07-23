# Product and interface design

## 첫 화면의 질문

사용자는 별도 설정 없이 다음을 먼저 확인할 수 있어야 합니다.

- 공개 결과가 검증됐는가?
- 데이터 기준일과 공통 평가 종료일은 언제인가?
- 같은 입력에서 Python이 선정한 최고 팩터는 무엇인가?
- 최고 팩터의 상대 선택 점수와 선택 포트폴리오 상태는 무엇인가?
- 선택 팩터·최고 팩터·시장 지수의 누적 성과는 어떻게 달랐는가?

## 정보 순서

1. 페이지 정체성, 공개 상태, 데이터 기준일
2. 최고 팩터, 신호 상태, 비교 팩터, 포트폴리오 요약
3. 선택 팩터·최고 팩터·시장 지수의 핵심 성과 차트
4. 공개 결과·보유 이력 기준일·비교 팩터 선택
5. 접힌 Python 분석 조건
6. 접힌 팩터 랭킹·선정 근거·방법론
7. 접힌 종목·보유 이력·가드레일·데이터 운영 상세
8. 연구용 고지 한 번

DOM 순서는 모바일에서도 유지하며 CSS로 의미 순서를 뒤집지 않습니다.

## 계산 소유권

- Python JSON이 최고 팩터, 순위, 비중, 현금, 성과, 비용의 유일한 source입니다.
- 브라우저는 manifest entry 선택, URL 직렬화, 표시와 탐색만 수행합니다.
- JavaScript에 팩터 공식, 선택 점수, 포트폴리오 비중 계산을 복제하지 않습니다.
- 사용자 선택 팩터는 비교 대상이며 `bestFactor`를 바꾸지 않습니다.
- summary/detail/manifest는 동일한 전체 `resultIdentity`를 요구합니다.
- 계약 검증 실패 시 이전 숫자를 남기지 않고 fail-closed 처리합니다.

## 입력 상태와 URL

- 최초 로드에서 query를 정규화하고 exact manifest entry를 찾습니다.
- 분석 입력 변경은 `history.pushState`, canonical normalization은 `replaceState`를 사용합니다.
- `popstate`로 이전 exact tuple을 복원합니다.
- 부분 일치나 가장 가까운 preset을 분석 결과로 사용하지 않습니다.
- 미지원 tuple이면 이전 결과를 숨기고 loopback Python API에 canonical 입력을 제출합니다.
- 정적 preset과 로컬 API 결과를 result key 옆에 구분합니다.

차트의 강조 계열, hover 날짜, 고정 날짜는 프레젠테이션 상태입니다. 이 상태는 URL, 분석 입력, 최고 팩터, 공식 성과 카드, 포트폴리오를 변경하지 않습니다.

## 정적 grid 상태

정적 viewer가 허용하는 detail 결과는 다음 조건을 모두 만족합니다.

- `schemaVersion: 5`
- 실제시장, non-synthetic
- 분석 종목 2,700개 이상
- 독립 팩터 61개가 모두 평가됨
- 하나의 고정 비중 정책 `score_liquidity_rank`
- bounded `grid/v1` manifest entry
- detail/summary 전체 identity parity
- 파일 bytes와 SHA-256 parity
- 전체 normalized input tuple exact match

Hub용 요약은 detail schema와 별도의 `quant-research-summary` contract v4입니다. detail schema 번호와 함께 올리지 않습니다.

정기 생성기는 최신 Top-20·최신 Top-30·직전 7개 완료 세션 Top-20 preset을 하나의 검증된 actual-market 스냅샷에서 다시 계산합니다.

## 선택과 비중 표현

- Python 최고 팩터는 `bestFactor`, 근거는 `bestFactorReason`과 `factorRanking`으로 표시합니다.
- 사용자 비교 선택은 공식 최고 팩터와 별도 상태로 표시합니다.
- `aria-pressed`는 사용자가 현재 비교 중인 팩터 또는 고정한 차트 계열을 뜻합니다.
- 공식 최고 팩터는 별도 `Python 최고` 배지와 선 스타일로 구분합니다.
- 모든 팩터에 같은 `score_liquidity_rank` 정책을 적용합니다.
- 정책 비중은 팩터 점수 percentile 70% + 후행 raw dollar-volume percentile 30%입니다.
- 시가총액은 비중 계산에 사용하지 않으며 호환 필드의 비중은 0%입니다.
- 최고 팩터 포트폴리오는 `bestFactorPortfolio`, 비교 팩터는 `factorPortfolios[factor]`에서 읽습니다.
- 사용할 수 없는 포트폴리오는 숫자를 추정하지 않고 fail-closed 상태를 표시합니다.

## 핵심 성과 차트

- 원본은 `performance.dates`, `performance.factorCurves`, `performance.benchmarkCurves`입니다.
- 선택 팩터와 최고 팩터가 같으면 하나의 계열로 합칩니다.
- 결측 구간은 잇거나 0%로 채우지 않습니다.
- hover/focus는 계열 또는 날짜의 임시 preview입니다.
- click/tap은 계열 또는 날짜를 고정합니다.
- `ArrowLeft`, `ArrowRight`, `Home`, `End`로 관측일을 이동합니다.
- 날짜 입력은 휴장일이나 누락일을 가장 가까운 실제 관측일로 맞춥니다.
- 정확값 카드는 선택일, 계열명, 평가 시작 대비 누적 수익률, 관측 상태를 표시합니다.
- 비활성 계열은 사라지지 않고 약해지며 선 종류와 이름을 함께 사용합니다.
- 차트 선택일은 보유 이력 기준일과 별개입니다.

## 시각 언어와 접근성

- 결과와 핵심 차트를 긴 설정·방법론보다 먼저 둡니다.
- 반복 설명, 공급자 상세, result key, 실행 명령은 접힌 영역으로 이동합니다.
- 공통 프로젝트 메뉴 순서와 `quant-research-theme` 키를 사용합니다.
- 주요 버튼·입력·내비게이션은 최소 `44×44px`입니다.
- 핵심 상태·차트 metadata는 최소 `12px`입니다.
- 390px에서 문서 전체 가로 overflow를 만들지 않습니다.
- 내비게이션, 차트 canvas, 표만 자체 가로 스크롤할 수 있습니다.
- loading, unavailable, contract error는 assistive technology에 노출합니다.
- `prefers-reduced-motion`에서 비필수 전환과 smooth scroll을 제거합니다.
- light/dark/mobile 모두 같은 의미 대비를 유지합니다.

## 데이터 모드 언어

- `live_market`: 실제 시장 데이터
- `local_file`: 검토된 로컬 연구 데이터
- `demo`: 합성 테스트 데이터

Demo와 local file은 실제시장 정적 grid에 들어갈 수 없습니다. 수집 실패 시 기존 holdings를 새 결과처럼 노출하지 않습니다.

## 연구 경계

- 결과는 연구·의사결정 보조용이며 실행 가이드가 아닙니다.
- 브라우저 what-if 계산을 canonical 결과처럼 보여주지 않습니다.
- 같은 표본 선택 편향과 survivorship/PIT 한계를 숨기지 않습니다.
- 현 범위 밖인 walk-forward/OOS/embargo를 구현한 것처럼 표현하지 않습니다.

## Acceptance checklist

- 결과·기준일·핵심 성과 차트가 분석 설정보다 먼저 보임
- 모든 공개 분석 입력이 URL round-trip 됨
- exact manifest tuple만 결과를 표시함
- detail/summary/manifest identity mismatch가 fail-closed 됨
- schema v5, 독립 팩터 61개, alias 3개, 고정 70/30 정책이 유지됨
- `bestFactorPortfolio`와 `factorPortfolios[bestFactor]`가 같음
- 계열 preview/pin과 날짜 preview/pin이 구분됨
- 정확값 카드가 원본 curve의 같은 날짜 값과 일치함
- 선택/최고 팩터가 같을 때 중복 계열이 없음
- 차트 탐색이 URL·분석 입력·공식 결과를 변경하지 않음
- 결측 관측을 보간하지 않음
- 공통 내비게이션·테마 migration·skip link가 동작함
- 390px 문서 overflow가 없고 주요 조작이 44px 이상임
- 라이트·다크·키보드·touch·unavailable 상태를 검증함
- 브라우저 source에 winner·ticker·date·결과 값 하드코딩이 없음
- 정적 자료는 actual-market 2,700+이며 demo가 아님
