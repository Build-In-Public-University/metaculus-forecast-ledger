from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .scoring import score_entry

API_BASE_URL = 'https://www.metaculus.com/api'
USER_AGENT = 'metaculus-forecast-ledger/0.1 (+https://github.com/Build-In-Public-University/metaculus-forecast-ledger)'


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_post(post_id: int, token: str | None = None) -> dict[str, Any]:
    headers = {'Accept': 'application/json', 'User-Agent': USER_AGENT}
    if token:
        headers['Authorization'] = f'Token {token}'
    url = f'{API_BASE_URL}/posts/{post_id}/'
    request = urllib.request.Request(url, headers=headers, method='GET')
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def extract_latest_forecast(post: dict[str, Any]) -> dict[str, Any] | None:
    question = post.get('question') or {}
    my_forecasts = question.get('my_forecasts') or {}
    latest = my_forecasts.get('latest')
    return latest if isinstance(latest, dict) else None


def extract_resolution_state(post: dict[str, Any]) -> dict[str, Any]:
    question = post.get('question') or {}
    keys = [
        'actual_resolve_time',
        'actual_resolution_time',
        'resolution',
        'resolution_set_time',
        'resolved',
        'scheduled_resolve_time',
        'status',
        'cp_reveal_time',
    ]
    state = {key: question.get(key) for key in keys if key in question}
    state['post_status'] = post.get('status')
    state['question_status'] = question.get('status')
    return state


def _forecast_from_pre_packet(pre_packet: dict[str, Any], question_id: int) -> dict[str, Any] | None:
    for forecast in pre_packet.get('forecasts', []):
        if forecast.get('question_id') == question_id:
            return forecast
    return None


def _receipt_entries(post_receipt: dict[str, Any]) -> list[dict[str, Any]]:
    final = post_receipt.get('final_readbacks', {})
    entries = []
    for post_id_text, readback in sorted(final.items(), key=lambda item: int(item[0])):
        entries.append(
            {
                'post_id': int(post_id_text),
                'question_id': readback.get('question_id'),
                'type': readback.get('type'),
                'latest_sha256_at_receipt': readback.get('latest_sha256'),
                'forecast_values_excerpt_at_receipt': readback.get('forecast_values_excerpt'),
                'receipt_has_latest': readback.get('has_latest'),
            }
        )
    return entries


def build_ledger(
    post_receipt_path: str | Path,
    pre_post_path: str | Path | None = None,
    *,
    token: str | None = None,
    fetch: bool = True,
) -> dict[str, Any]:
    post_receipt = load_json(post_receipt_path)
    pre_packet = load_json(pre_post_path) if pre_post_path else {}
    rows = []
    for entry in _receipt_entries(post_receipt):
        frozen = _forecast_from_pre_packet(pre_packet, entry['question_id']) or {}
        live_post = fetch_post(entry['post_id'], token=token) if fetch else None
        latest = extract_latest_forecast(live_post) if live_post else None
        resolution_state = extract_resolution_state(live_post) if live_post else {}
        row = {
            'post_id': entry['post_id'],
            'question_id': entry['question_id'],
            'type': entry['type'],
            'title': frozen.get('title'),
            'target': post_receipt.get('target'),
            'source_post_receipt_sha256': hash_json(post_receipt),
            'source_pre_post_sha256': hash_json(pre_packet) if pre_packet else None,
            'submitted_forecast_summary': _public_forecast_summary(frozen),
            'rationale_sha256': hash_json(frozen.get('rationale')) if frozen.get('rationale') else None,
            'receipt_has_latest': entry['receipt_has_latest'],
            'latest_sha256_at_receipt': entry['latest_sha256_at_receipt'],
            'live_fetch_attempted': fetch,
            'live_my_forecast_latest_sha256': hash_json(latest) if latest else None,
            'live_my_forecast_has_latest': bool(latest),
            'resolution_state': resolution_state,
            'status': _ledger_status(resolution_state),
            **_score_fields(entry['type'], frozen, resolution_state, latest),
        }
        rows.append(row)
    ledger = {
        'artifact': 'metaculus_forecast_ledger',
        'created_at_utc': now_utc(),
        'scope': 'read-only ledger for submitted Metaculus forecasts',
        'network_policy': 'GET-only; this project contains no Metaculus POST endpoint calls',
        'source_receipt_path': str(post_receipt_path),
        'source_pre_post_path': str(pre_post_path) if pre_post_path else None,
        'entry_count': len(rows),
        'entries': rows,
    }
    ledger['ledger_sha256'] = hash_json(ledger['entries'])
    return ledger


def _public_forecast_summary(forecast: dict[str, Any]) -> Any:
    if not forecast:
        return None
    if forecast.get('type') == 'numeric':
        return {
            'forecast_summary': forecast.get('forecast_summary'),
            'forecast_cdf_sha256': forecast.get('forecast_cdf_sha256'),
            'forecast_cdf_count': forecast.get('forecast_cdf_count'),
            'forecast_cdf_head': forecast.get('forecast_cdf_head'),
            'forecast_cdf_tail': forecast.get('forecast_cdf_tail'),
        }
    return forecast.get('forecast')


def _score_fields(type_: str, frozen: dict[str, Any], resolution_state: dict[str, Any], latest: dict[str, Any] | None) -> dict[str, Any]:
    score, note = score_entry(type_=type_, frozen=frozen, resolution_state=resolution_state, latest=latest)
    return {'score': score, 'score_note': note, 'scoring_source': 'Metaculus baseline score (scoring/score_math.py)'}


def _ledger_status(resolution_state: dict[str, Any]) -> str:
    question_status = resolution_state.get('question_status')
    if question_status in {'resolved', 'annulled'}:
        return question_status
    if resolution_state.get('resolution') is not None or resolution_state.get('resolved') is True:
        return 'resolved'
    if question_status in {'closed'}:
        return 'closed_unresolved'
    return question_status or 'unknown'


def write_ledger(ledger: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + '\n')
    return path


def env_token() -> str | None:
    return os.environ.get('METACULUS_TOKEN')
