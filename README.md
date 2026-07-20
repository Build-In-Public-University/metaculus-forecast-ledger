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

`score` is intentionally not implemented yet. Different Metaculus types require different scoring logic and resolution extraction. False precision is how dashboards become weather vanes.

## Verification

```bash
python3 -m pytest tests -q
```

Expected at initial publication:

```text
3 passed
```
