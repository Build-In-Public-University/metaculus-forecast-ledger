import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from metaculus_forecast_ledger.audit import audit_ledger, write_outcome_summary_csv


def _entry(*, post_id=1, type_='binary', resolution=True, status='resolved', score: float | None = 42.5):
    return {
        'post_id': post_id,
        'question_id': post_id + 100,
        'type': type_,
        'status': status,
        'resolution_state': {
            'question_status': status,
            'resolution': resolution,
            'resolved': status == 'resolved',
            'actual_resolve_time': '2026-08-01T00:00:00Z',
        },
        'submitted_forecast_full': {'probability_yes': 0.67},
        'score': score,
        'score_note': 'baseline_score',
        'scoring_source': 'Metaculus baseline score (scoring/score_math.py)',
    }


def test_audit_appends_one_resolved_event_and_is_idempotent(tmp_path):
    path = tmp_path / 'outcomes.jsonl'
    ledger = {'entries': [_entry()]}

    first = audit_ledger(ledger, path, audited_at='2026-07-21T12:00:00+00:00')
    second = audit_ledger(ledger, path, audited_at='2026-07-21T12:05:00+00:00')

    assert first['events_appended'] == 1
    assert second['events_appended'] == 0
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]['post_id'] == 1
    assert rows[0]['resolution'] is True
    assert rows[0]['score'] == 42.5
    assert rows[0]['event_type'] == 'resolved'
    assert rows[0]['event_id']


def test_audit_keeps_open_questions_out_of_outcomes(tmp_path):
    path = tmp_path / 'outcomes.jsonl'
    result = audit_ledger({'entries': [_entry(status='open', score=None)]}, path)
    assert result['events_appended'] == 0
    assert not path.exists()


def test_audit_records_annulled_without_score(tmp_path):
    path = tmp_path / 'outcomes.jsonl'
    entry = _entry(status='annulled', score=None)
    entry['resolution_state']['resolution'] = None
    result = audit_ledger({'entries': [entry]}, path)
    assert result['events_appended'] == 1
    event = json.loads(path.read_text())
    assert event['event_type'] == 'annulled'
    assert event['score'] is None
    assert event['score_note'] == 'annulled_no_score'


def test_audit_records_resolution_discrepancy(tmp_path):
    path = tmp_path / 'outcomes.jsonl'
    audit_ledger({'entries': [_entry(resolution=True)]}, path)
    changed = _entry(resolution=False)
    result = audit_ledger({'entries': [changed]}, path)
    again = audit_ledger({'entries': [changed]}, path)
    assert result['events_appended'] == 1
    assert result['discrepancies'] == 1
    assert again == {'events_appended': 0, 'discrepancies': 0}
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[-1]['event_type'] == 'resolution_discrepancy'
    assert rows[-1]['previous_resolution'] is True
    assert rows[-1]['resolution'] is False


def test_write_outcome_summary_csv(tmp_path):
    outcomes = tmp_path / 'outcomes.jsonl'
    outcomes.write_text(json.dumps({
        'event_id': 'abc', 'post_id': 1, 'type': 'binary',
        'event_type': 'resolved', 'resolution': True, 'score': 42.5,
        'score_note': 'baseline_score', 'resolved_at': '2026-08-01T00:00:00Z',
    }) + '\n')
    output = tmp_path / 'summary.csv'
    write_outcome_summary_csv(outcomes, output)
    text = output.read_text()
    assert 'post_id,type,event_type,resolution,score,score_note,resolved_at' in text
    assert '1,binary,resolved,True,42.5,baseline_score' in text
