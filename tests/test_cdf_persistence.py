import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from metaculus_forecast_ledger.ledger import (
    _full_submitted_forecast,
    build_ledger,
    score_from_artifact,
)


def _resolved_post(type_, resolution, latest):
    return {
        'question': {
            'type': type_,
            'status': 'resolved',
            'resolution': resolution,
            'my_forecasts': {'latest': latest},
        }
    }


def test_full_submitted_forecast_numeric_captures_cdf():
    # Live Metaculus shape uses `forecast_values` for the CDF.
    cdf = [i / 100 for i in range(101)]
    latest = {'forecast_values': cdf, 'open_lower_bound': True, 'open_upper_bound': False}
    full = _full_submitted_forecast('numeric', {}, latest)
    assert full is not None
    assert full['continuous_cdf'] == cdf
    assert full['open_lower_bound'] is True
    assert full['open_upper_bound'] is False


def test_full_submitted_forecast_numeric_offline_fallback_to_forecast_cdf():
    # Pre-post packet shape uses `forecast_cdf` when live is absent.
    cdf = [i / 100 for i in range(101)]
    frozen = {'forecast_cdf': cdf, 'open_lower_bound': False, 'open_upper_bound': True}
    full = _full_submitted_forecast('numeric', frozen, None)
    assert full is not None
    assert full['continuous_cdf'] == cdf
    assert full['open_lower_bound'] is False
    assert full['open_upper_bound'] is True


def test_score_from_artifact_numeric_offline_resolved():
    cdf = [i / 100 for i in range(101)]
    full = {'continuous_cdf': cdf, 'open_lower_bound': True, 'open_upper_bound': False}
    entry = {
        'type': 'numeric',
        'submitted_forecast_full': full,
        'resolution_state': {'question_status': 'resolved', 'resolved': True, 'resolution': 0.69},
    }
    score, note = score_from_artifact(entry)
    assert note == 'baseline_score'
    assert score is not None
    value = 0.69
    bucket = None
    for i in range(len(cdf) - 1):
        if cdf[i] <= value < cdf[i + 1]:
            bucket = i
            break
    assert bucket is not None
    pmf = [b - a for a, b in zip(cdf, cdf[1:])]
    baseline = (1 - 0.05 * 1) / (len(pmf) - 2)
    expected = 100.0 * math.log(pmf[bucket] / baseline) / 2.0
    assert abs(score - expected) < 1e-9


def test_score_from_artifact_numeric_offline_unresolved():
    full = {'continuous_cdf': [i / 100 for i in range(101)], 'open_lower_bound': True, 'open_upper_bound': False}
    entry = {'type': 'numeric', 'submitted_forecast_full': full, 'resolution_state': {'question_status': 'open'}}
    score, note = score_from_artifact(entry)
    assert score is None and note == 'unresolved'


def test_score_from_artifact_uses_live_resolution_when_post_provided():
    cdf = [i / 100 for i in range(101)]
    full = {'continuous_cdf': cdf, 'open_lower_bound': False, 'open_upper_bound': False}
    entry = {'type': 'numeric', 'submitted_forecast_full': full, 'resolution_state': {}}
    post = _resolved_post('numeric', 0.69, {'continuous_cdf': cdf, 'open_lower_bound': False, 'open_upper_bound': False})
    score, note = score_from_artifact(entry, post=post)
    assert note == 'baseline_score'
    assert score is not None


def test_build_ledger_persists_full_forecast_offline():
    ledger = build_ledger(
        ROOT / 'fixtures/metaculus_cup_practice_post_receipt.json',
        ROOT / 'fixtures/metaculus_cup_practice_pre_post_forecast_packet.json',
        fetch=False,
    )
    entries = {e['post_id']: e for e in ledger['entries']}
    assert entries[43491]['submitted_forecast_full'] == {'probability_yes': 0.67}
    mc_full = entries[44676]['submitted_forecast_full']
    assert mc_full['probability_yes_per_category']['Henry McMaster'] == 0.08
    # Numeric full CDF not available offline (fixture redacts it) -> None.
    # That is honest: an offline build cannot score it without the live CDF.
    assert entries[44551]['submitted_forecast_full'] is None


def test_build_ledger_scores_resolved_numeric_from_persisted_cdf(monkeypatch):
    # Simulate a resolved live post where the live CDF was captured at build
    # time; after resolution, scoring must NOT re-fetch Metaculus.
    cdf = [i / 100 for i in range(101)]

    def fake_fetch(post_id, token=None):
        return {
            'question': {
                'type': 'numeric',
                'status': 'resolved',
                'resolution': 0.69,
                'my_forecasts': {
                    'latest': {'forecast_values': cdf, 'open_lower_bound': True, 'open_upper_bound': False}
                },
            }
        }

    monkeypatch.setattr('metaculus_forecast_ledger.ledger.fetch_post', fake_fetch)
    ledger = build_ledger(
        ROOT / 'fixtures/metaculus_cup_practice_post_receipt.json',
        ROOT / 'fixtures/metaculus_cup_practice_pre_post_forecast_packet.json',
        token='dummy',
        fetch=True,
    )
    entry = next(e for e in ledger['entries'] if e['type'] == 'numeric')
    assert entry['submitted_forecast_full'] is not None
    assert entry['submitted_forecast_full']['continuous_cdf'] == cdf
    assert entry['score'] is not None
    assert entry['score_note'] == 'baseline_score'
    # Independent expected value
    value = 0.69
    bucket = None
    for i in range(len(cdf) - 1):
        if cdf[i] <= value < cdf[i + 1]:
            bucket = i
            break
    assert bucket is not None
    pmf = [b - a for a, b in zip(cdf, cdf[1:])]
    baseline = (1 - 0.05 * 1) / (len(pmf) - 2)
    expected = 100.0 * math.log(pmf[bucket] / baseline) / 2.0
    assert abs(entry['score'] - expected) < 1e-9
