from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ledger import hash_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _resolved_event(entry: dict[str, Any], audited_at: str) -> dict[str, Any] | None:
    status = entry.get('status')
    if status not in {'resolved', 'annulled'}:
        return None
    state = entry.get('resolution_state') or {}
    event_type = 'annulled' if status == 'annulled' else 'resolved'
    resolution = state.get('resolution')
    score = None if event_type == 'annulled' else entry.get('score')
    score_note = 'annulled_no_score' if event_type == 'annulled' else entry.get('score_note')
    forecast_hash = hash_json(entry.get('submitted_forecast_full')) if entry.get('submitted_forecast_full') is not None else None
    identity = {
        'post_id': entry.get('post_id'),
        'question_id': entry.get('question_id'),
        'event_type': event_type,
        'resolution': resolution,
        'forecast_hash': forecast_hash,
    }
    return {
        'event_id': hash_json(identity),
        'event_type': event_type,
        'post_id': entry.get('post_id'),
        'question_id': entry.get('question_id'),
        'type': entry.get('type'),
        'resolution': resolution,
        'resolved_at': state.get('actual_resolve_time') or state.get('actual_resolution_time'),
        'forecast_hash': forecast_hash,
        'score': score,
        'score_note': score_note,
        'scoring_source': entry.get('scoring_source'),
        'audited_at': audited_at,
    }


def audit_ledger(
    ledger: dict[str, Any],
    outcomes_path: str | Path,
    *,
    audited_at: str | None = None,
) -> dict[str, int]:
    """Append resolution events from a ledger without duplicating prior events."""
    path = Path(outcomes_path)
    audited_at = audited_at or _now()
    existing = _read_events(path)
    known_ids = {event.get('event_id') for event in existing}
    latest_resolution: dict[Any, dict[str, Any]] = {}
    for event in existing:
        if event.get('event_type') in {'resolved', 'annulled', 'resolution_discrepancy'}:
            latest_resolution[event.get('post_id')] = event

    appended = []
    discrepancies = 0
    for entry in ledger.get('entries', []):
        event = _resolved_event(entry, audited_at)
        if event is None:
            continue
        previous = latest_resolution.get(event['post_id'])
        if previous and previous.get('resolution') == event.get('resolution'):
            continue
        if previous and previous.get('resolution') != event.get('resolution'):
            discrepancy = {
                **event,
                'event_type': 'resolution_discrepancy',
                'previous_event_id': previous.get('event_id'),
                'previous_resolution': previous.get('resolution'),
            }
            discrepancy_identity = {
                'event_id': event['event_id'],
                'previous_event_id': discrepancy['previous_event_id'],
            }
            discrepancy['event_id'] = hash_json(discrepancy_identity)
            event = discrepancy
        if event['event_id'] not in known_ids:
            appended.append(event)
            known_ids.add(event['event_id'])
            latest_resolution[event['post_id']] = event
            if event.get('event_type') == 'resolution_discrepancy':
                discrepancies += 1

    if appended:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as fh:
            for event in appended:
                fh.write(json.dumps(event, sort_keys=True) + '\n')
    return {'events_appended': len(appended), 'discrepancies': discrepancies}


SUMMARY_COLUMNS = ['post_id', 'type', 'event_type', 'resolution', 'score', 'score_note', 'resolved_at']


def write_outcome_summary_csv(outcomes_path: str | Path, output_path: str | Path) -> Path:
    """Write a compact human-readable projection of the append-only outcomes."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for event in _read_events(Path(outcomes_path)):
            writer.writerow({key: event.get(key) for key in SUMMARY_COLUMNS})
    return path
