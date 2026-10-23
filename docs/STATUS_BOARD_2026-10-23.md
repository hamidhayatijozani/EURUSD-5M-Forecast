# EURUSD-5M-Forecast — Status Board (2026-10-23)

Snapshot for operational cleanup. Not a claim of edge, profitability, or production broker readiness.

## Live / main health

| Gate | Status | Evidence |
|------|--------|----------|
| `research-tests` on main | PASS | recent push runs green |
| `live-minute-research` (schedule) | PASS | e.g. [run 39955282656](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/39955282656) |
| `ClaimLab EURUSD market probe` | PASS | e.g. [run 39939645247](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/39939645247) |
| `market-research` | PASS | scheduled success |
| SSRF / arbitrary outbound URL sink | No CodeQL-style hotspot found in current Python search | — |

Main is operationally healthy for scheduled research loops. Live evidence persistence continues via `[skip ci]` evidence commits.

## Open pull requests (12) — triage

| PR | Title | Last update | Recommended action |
|----|-------|-------------|--------------------|
| [#54](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/54) | Forward-only virtual paper account + risk diagnostics | 2026-10-17 | **Priority review/merge candidate** (paper-only, safety tests, isolated CI) |
| [#53](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/53) | Preregister single-model EUR/USD M5 edge test | 2026-10-15 | Keep open only if still active research; else close as superseded |
| [#52](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/52) | Port evidence-gated trader ranking / FX research | 2026-10-15 | Review scope vs current main; rebase or close |
| [#51](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/51) | Coinversa Hyperliquid risk context | 2026-10-15 | Optional sidecar — low priority |
| [#50](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/50) | Coinversa crypto-risk context sidecar | 2026-10-15 | Duplicate theme with #51 — consolidate or close one |
| [#42](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/42) | Read-only OANDA EURUSD live data adapter | 2026-10-13 | Keep if OANDA secrets still planned; else close |
| [#39](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/39) | ClaimLab Web evidence-ledger interface | 2026-10-12 | Stale — rebase or close |
| [#37](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/37) | P0: Harden evidence settlement + system E2E | 2026-10-12 | **P0 infrastructure** — rebase on main, re-run CI, then merge or supersede |
| [#35](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/35) | Research audit: multi-source input availability | 2026-10-12 | Stale research audit — close if issue #36 closed supersedes |
| [#33](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/33) | Same-sample original vs inverse direction evaluator | 2026-10-12 | Align with issue #32 protocol or close |
| [#31](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/31) | Preregistered cross-repository feature experiment | 2026-10-12 | Stale — close unless actively used |
| [#3](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/3) | Connect closed candles to ClaimLab live ledger | 2026-10-06 | Very stale — close or fully rebase |

## Open research issues (selected)

| Issue | State | Note |
|-------|-------|------|
| [#36](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/issues/36) P0 live auditable prediction | **Closed** | Do not treat TEST_CI as LIVE_EXECUTION |
| [#34](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/issues/34) Multi-source minute-ahead + PST | Open | Research protocol |
| [#32](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/issues/32) Original vs inverse 90% forward target | Open | Explicitly not a performance claim |

## Recommended sequence (minimal risk)

1. **Merge or close #54** (paper account) after exact-head CI review — additive measurement layer only.
2. **Rebase #37** on current `main` and re-run E2E evidence contracts; merge if still the missing settlement hardening.
3. **Close or mark draft** PRs older than ~10 days with no rebase (#3, #31, #33, #35, #39) unless an owner claims them within 48h.
4. **Consolidate** Coinversa sidecars (#50/#51) into one PR or drop both.
5. Keep scheduled live loops running; do not treat green schedules as predictive edge.

## Explicit non-claims

- No guaranteed profitability or 90% hit rate.
- No live broker execution readiness.
- Scheduled workflow success ≠ settled, audited edge.
- Closing stale PRs is hygiene, not rejection of underlying research ideas.

## Links

- Repo: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast
- Open PRs: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pulls
- Actions: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions
