# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-06-26
- Primary product surfaces: static GitHub Pages dashboard (`docs/index.html`), generated dashboard assets (`docs/assets/dashboard.js`, `docs/assets/styles.css`), Python generator (`momentum_factor_lab/dashboard.py`).
- Evidence reviewed: `docs/index.html`, `docs/assets/dashboard.js`, `docs/assets/styles.css`, `docs/data/dashboard.json`, `momentum_factor_lab/dashboard.py`, prior repo memory that CSS output and embedded `CSS_CONTENT` must stay synchronized.

## Brand
- Personality: dark, analytical, high-signal research cockpit; serious but not black-box or overly dim.
- Trust signals: visible data 기준일, run timestamp, provider, fail-closed/tradability gate language, clear research-only disclaimers.
- Avoid: low-contrast near-black layering, decorative glow that competes with numbers, implying browser scenarios are saved trading instructions.

## Product goals
- Goals: let users compare momentum factors, inspect current best factor vs selected factor, test browser-side scenario assumptions, and audit daily weights by basis date.
- Non-goals: broker execution, personalized investment advice, hidden persistence of browser inputs, changing GitHub Actions run configuration from the static page.
- Success signals: defaults match the current best factor and requested inputs; max-weight/cost/rebalance changes visibly affect scenario weights and backtest view; empty/fallback states explain why data is missing.

## Personas and jobs
- Primary personas: quant researcher, investment decision-support reviewer, project owner checking daily static output.
- User jobs: identify the strongest recent momentum factor, review selected-factor holdings/weights, test sensitivity to caps/costs/rebalance cadence, understand whether current output is research-only or tradable.
- Key contexts of use: desktop research review, mobile quick freshness check, public GitHub Pages read-only access.

## Information architecture
- Primary navigation: hero/status, manual update, analysis/backtest controls, summary cards, diagnostics, visual charts, current output, selected-factor daily weight analysis, tables/disclaimers.
- Core routes/screens: single-page static dashboard.
- Content hierarchy: trust/freshness first, controls second, charts before detailed tables, disclaimers always visible in copy.

## Design principles
- Principle 1: Dark cockpit, readable numbers. Keep the dark identity while lifting surfaces, text, chart axes, and input contrast.
- Principle 2: Every scenario assumption must be visible next to the affected result.
- Tradeoffs: browser scenarios are responsive sensitivity views, not regenerated live backend runs; copy must state this clearly.

## Visual language
- Color: navy/slate dark background, brighter card surfaces, cyan/blue analytical accents, green/amber/rose only for semantic status.
- Typography: system sans stack; heavy labels for metrics; tabular-feeling numeric tables.
- Spacing/layout rhythm: grouped controls, roomy cards, compact tables with scroll wrappers.
- Shape/radius/elevation: rounded panels with restrained shadows; avoid excessive glow.
- Motion: minimal hover/focus feedback only.
- Imagery/iconography: no decorative imagery required; charts and tables carry the product.

## Components
- Existing components to reuse: hero, status card, manual update card, controls, summary cards, panels, viz cards, bar/line charts, tables, badges, empty states.
- New/changed components: grouped backtest-control panel, preset chips, live scenario summary, daily selected-factor weights table.
- Variants and states: loading/updating status, missing snapshot fallback, research-only gate, selected/best chart rows, responsive single-column controls.
- Token/component ownership: `momentum_factor_lab/dashboard.py` owns generated HTML/CSS/JS; `docs/assets/*` must match generated outputs.

## Accessibility
- Target standard: WCAG AA contrast intent for text and key chart labels.
- Keyboard/focus behavior: visible focus outlines on links, buttons, selects, and inputs.
- Contrast/readability: no near-black-on-black cards; muted text must remain readable on dark surfaces.
- Screen-reader semantics: preserve section labels, table headers, live regions, and status messages.
- Reduced motion and sensory considerations: no required animation; avoid flashing or noisy effects.

## Responsive behavior
- Supported breakpoints/devices: desktop, tablet, mobile GitHub Pages browsing.
- Layout adaptations: control groups collapse from two columns to one; tables stay horizontally scrollable; chart rows become stacked on small screens.
- Touch/hover differences: preset chips and buttons need large enough tap targets; hover is enhancement only.

## Interaction states
- Loading: run-status shows busy text while JSON or control changes render.
- Empty: panels explain missing score/weight/backtest snapshots without substituting unrelated factors silently.
- Error: JSON fetch failure appears in run-status.
- Success: summary/status cards show data 기준일, provider, run time, and selected scenario state.
- Disabled: run selector disabled when only one run exists.
- Offline/slow network, if applicable: static page requires only local JSON assets after initial load; manual update links out to GitHub Actions.

## Content voice
- Tone: concise Korean research-operational copy; direct about limitations.
- Terminology: 기준일, 선택 팩터, 현재 기준 최고 팩터, 연구용 신호, 시나리오 비중, 리밸런싱, 거래 비용.
- Microcopy rules: explain whether a value is backend-generated, browser-recomputed, or fallback; never present scenario output as a saved trading order.

## Implementation constraints
- Framework/styling system: no frontend framework; vanilla JS, static HTML/CSS, generated by Python.
- Design-token constraints: keep CSS variables and final dark readability override in sync between source template and generated CSS.
- Performance constraints: keep payload size bounded; avoid adding large historical datasets for browser-only interactions.
- Compatibility constraints: no new dependency for UI behavior; preserve static GitHub Pages boundary.
- Test/screenshot expectations: run dashboard unit/static tests and capture local screenshot/visual verdict evidence when feasible.

## Open questions
- [ ] Whether future payloads should export deeper historical per-factor score/weight data for fully faithful browser-side custom backtests / owner: product / impact: accuracy vs payload size.
