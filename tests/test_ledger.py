import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from metaculus_forecast_ledger.ledger import build_ledger, hash_json, write_ledger


def test_build_ledger_from_receipts_without_network():
    ledger = build_ledger(
        ROOT / 'fixtures/metaculus_cup_practice_post_receipt.json',
        ROOT / 'fixtures/metaculus_cup_practice_pre_post_forecast_packet.json',
        fetch=False,
    )
    assert ledger['network_policy'].startswith('GET-only')
    assert ledger['entry_count'] == 3
    assert {row['post_id'] for row in ledger['entries']} == {43491, 44676, 44551}
    assert {row['type'] for row in ledger['entries']} == {'binary', 'multiple_choice', 'numeric'}
    assert all(row['receipt_has_latest'] is True for row in ledger['entries'])
    assert all(row['live_fetch_attempted'] is False for row in ledger['entries'])
    assert all(row['score'] is None for row in ledger['entries'])
    # current Cup questions are still open -> unresolved, not faked
    assert all(row['score_note'] == 'unresolved' for row in ledger['entries'])
    assert all(row['scoring_source'].startswith('Metaculus baseline') for row in ledger['entries'])
    numeric = next(row for row in ledger['entries'] if row['type'] == 'numeric')
    assert numeric['submitted_forecast_summary']['forecast_cdf_count'] == 201
    assert numeric['submitted_forecast_summary']['forecast_cdf_sha256']


def test_write_ledger_round_trips(tmp_path):
    ledger = build_ledger(
        ROOT / 'fixtures/metaculus_cup_practice_post_receipt.json',
        ROOT / 'fixtures/metaculus_cup_practice_pre_post_forecast_packet.json',
        fetch=False,
    )
    out = write_ledger(ledger, tmp_path / 'ledger.json')
    loaded = json.loads(out.read_text())
    assert loaded['ledger_sha256'] == hash_json(loaded['entries'])
    assert loaded['entry_count'] == 3


def test_no_post_endpoint_literals_in_source():
    source = ''.join(p.read_text() for p in (ROOT / 'src').rglob('*.py'))
    assert '/questions/forecast/' not in source
    assert '/comments/create/' not in source
    assert "method='POST'" not in source
    assert 'method="POST"' not in source
