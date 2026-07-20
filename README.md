# Metaculus Forecast Ledger

Read-only forecast ledger for Metaculus practice submissions.

This repo exists because a forecast without an outcome log is just an API call with better posture.

## Scope

- Ingests public-safe Metaculus forecast receipt artifacts.
- Optionally performs authenticated `GET /api/posts/{post_id}/` readbacks.
- Writes a ledger with submitted forecast summaries, latest-forecast proof hashes, resolution state, and scoring placeholders.
- Contains no Metaculus forecast/comment POST endpoint calls.

## Current seed ledger

Seed source:

```text
fixtures/metaculus_cup_practice_post_receipt.json
fixtures/metaculus_cup_practice_pre_post_forecast_packet.json
```

Submitted practice questions tracked:

```text
43491 / 43498 — Bosnia High Representative — binary — 67% Yes
44676 / 44835 — SC GOP Senate nominee — multiple_choice
44551 / 44705 — Farage Clacton vote share — numeric CDF
```

## Quickstart

Offline/from receipts only:

```bash
python3 -m pytest tests -q
python3 scripts/update_metaculus_forecast_ledger.py \
  --post-receipt fixtures/metaculus_cup_practice_post_receipt.json \
  --pre-post fixtures/metaculus_cup_practice_pre_post_forecast_packet.json \
  --no-fetch
```

Live read-only update:

```bash
export METACULUS_TOKEN=...
python3 scripts/update_metaculus_forecast_ledger.py \
  --post-receipt fixtures/metaculus_cup_practice_post_receipt.json \
  --pre-post fixtures/metaculus_cup_practice_pre_post_forecast_packet.json \
  --output artifacts/ledger/metaculus_forecast_ledger.json
```

The live mode only performs GET requests. If that changes, the tests should fail and the maintainer should feel faintly accused.

## Ledger fields

Each entry records:

```text
post_id
question_id
type
title
target
submitted_forecast_summary
rationale_sha256
receipt_has_latest
latest_sha256_at_receipt
live_my_forecast_has_latest
live_my_forecast_latest_sha256
resolution_state
status
score
score_note
```

`score` is filled when a question is resolved, using Metaculus' published **Baseline score** from `scoring/score_math.py`:

- binary: `100 * ln(p·2) / ln(2)`
- multiple_choice: `100 * ln(p·N) / ln(N)` where N = available options
- continuous: `100 * ln(pmf[bucket] / baseline) / 2`, baseline `0.05` in each open tail, `(1 − 0.05·open_bounds)/(len(pmf)−2)` over the closed middle

Unresolved questions keep `score = null` with `score_note = "unresolved"`. The ledger does not invent scores for open questions. That would defeat the entire point.

Source: https://github.com/Metaculus/metaculus/blob/main/scoring/score_math.py

Continuous scoring needs the full CDF. The pinned Cup fixture redacts the numeric CDF, so a fully-scored numeric entry requires the live forecast distribution (`my_forecasts.latest.continuous_cdf`) at resolution time.

## Resolution scoring pipeline

The ledger scores resolved questions automatically via `score_post(post, frozen)`:

1. `extract_resolution(post)` normalizes the live post's `question.resolution` field into the shape `score_entry` consumes:
   - binary → `bool` (True = Yes)
   - multiple_choice → option label string
   - numeric/date/discrete → float value
2. `score_entry(...)` computes the Metaculus Baseline score (see above).

When you run the updater against a resolved live post, the `score` column fills from the post itself — no manual step. Open questions stay `score = null` with `score_note = "unresolved"`.

## Persisted forecast distributions

The ledger stores the **complete** submitted distribution in each entry (`submitted_forecast_full`), not just a hash:

- binary → `probability_yes`
- multiple_choice → `probability_yes_per_category`
- numeric/date/discrete → the full `continuous_cdf` (201-point list)

This is captured at build time from the live `my_forecasts.latest` (`forecast_values` key on Metaculus). Scoring then runs from the persisted distribution via `score_from_artifact`, so a resolved question can be scored **without re-fetching Metaculus** — even if the original forecast is later pruned or superseded. The CDF is your own forecast; persisting it is evidence retention, not a leak.

Offline builds (`--no-fetch`) can still score binary/MC from the pre-post packet. Numeric requires the live CDF, which the fixture redacts; an offline numeric entry honestly reports `submitted_forecast_full: null` rather than inventing a distribution.

## Summary export

The CLI also writes human-readable summaries next to the JSON ledger:

```text
artifacts/ledger/metaculus_forecast_ledger_summary.csv
artifacts/ledger/metaculus_forecast_ledger_summary.md
```

Both are generated read-only from the ledger artifact. No network calls.

## Verification

```bash
python3 -m pytest tests -q
```

Expected:

```text
25 passed
```
