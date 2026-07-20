import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from metaculus_forecast_ledger.scoring import (
    baseline_score_binary,
    baseline_score_continuous,
    extract_resolution,
    score_post,
)
from metaculus_forecast_ledger.ledger import (
    build_ledger,
    write_ledger_summary_csv,
    write_ledger_summary_md,
)


def _resolved_binary_post(p_yes: float, outcome_yes: bool) -> dict:
    return {
        'question': {
            'type': 'binary',
            'status': 'resolved',
            'resolution': outcome_yes,
            'my_forecasts': {'latest': {'probability_yes': p_yes}},
        }
    }


def _resolved_mc_post(probs: dict[str, float], resolution: str) -> dict:
    return {
        'question': {
            'type': 'multiple_choice',
            'status': 'resolved',
            'resolution': resolution,
            'my_forecasts': {'latest': {'probability_yes_per_category': probs}},
        }
    }


def _resolved_numeric_post(cdf: list[float], value: float, open_lower: bool, open_upper: bool) -> dict:
    return {
        'question': {
            'type': 'numeric',
            'status': 'resolved',
            'resolution': value,
            'my_forecasts': {'latest': {'continuous_cdf': cdf, 'open_lower_bound': open_lower, 'open_upper_bound': open_upper}},
        }
    }


def test_extract_resolution_binary():
    post = _resolved_binary_post(0.8, True)
    ext = extract_resolution(post)
    assert ext['resolved'] is True
    assert ext['type'] == 'binary'
    assert ext['resolution'] is True
    # string 'yes' also maps to True
    post2 = {'question': {'type': 'binary', 'status': 'resolved', 'resolution': 'yes'}}
    assert extract_resolution(post2)['resolution'] is True
    # open question reports not resolved
    open_post = {'question': {'type': 'binary', 'status': 'open'}}
    assert extract_resolution(open_post)['resolved'] is False


def test_score_post_binary_resolved():
    post = _resolved_binary_post(0.8, True)
    frozen = {'type': 'binary', 'forecast': 0.8}
    score, note = score_post(post, frozen)
    assert note == 'baseline_score'
    assert score == baseline_score_binary(0.8, outcome_yes=True)


def test_score_post_mc_resolved():
    probs = {'A': 0.5, 'B': 0.3, 'C': 0.2}
    post = _resolved_mc_post(probs, 'A')
    frozen = {'type': 'multiple_choice', 'forecast': probs, 'options': list(probs)}
    score, note = score_post(post, frozen)
    assert note == 'baseline_score'
    # A resolved, p=0.5, N=3 => 100*ln(0.5*3)/ln(3)
    import math
    assert abs(score - 100.0 * math.log(0.5 * 3) / math.log(3)) < 1e-9


def test_score_post_numeric_resolved_with_full_cdf():
    cdf = [i / 100 for i in range(101)]
    post = _resolved_numeric_post(cdf, 0.69, open_lower=True, open_upper=False)
    # need full forecast_cdf in frozen; score_post reads from latest only
    frozen = {'type': 'numeric', 'open_lower_bound': True, 'open_upper_bound': False}
    score, note = score_post(post, frozen)
    assert note == 'baseline_score'
    assert score is not None
    # same as scoring the bucket directly
    import math
    value = 0.69
    bucket = None
    for i in range(len(cdf) - 1):
        if cdf[i] <= value < cdf[i + 1]:
            bucket = i
            break
    assert bucket is not None, 'test value must fall inside the cdf range'
    pmf = [b - a for a, b in zip(cdf, cdf[1:])]
    baseline = (1 - 0.05 * 1) / (len(pmf) - 2)
    expected = 100.0 * math.log(pmf[bucket] / baseline) / 2.0
    assert abs(score - expected) < 1e-9


def test_score_post_open_returns_unresolved():
    post = {'question': {'type': 'binary', 'status': 'open'}}
    frozen = {'type': 'binary', 'forecast': 0.5}
    score, note = score_post(post, frozen)
    assert score is None and note == 'unresolved'


def test_summary_exports(tmp_path):
    ledger = build_ledger(
        ROOT / 'fixtures/metaculus_cup_practice_post_receipt.json',
        ROOT / 'fixtures/metaculus_cup_practice_pre_post_forecast_packet.json',
        fetch=False,
    )
    csv_path = write_ledger_summary_csv(ledger, tmp_path / 'summary.csv')
    md_path = write_ledger_summary_md(ledger, tmp_path / 'summary.md')
    csv_text = csv_path.read_text()
    assert csv_text.startswith('post_id,type,status,forecast_excerpt,score,score_note')
    rows = list(csv.DictReader(csv_text.splitlines()))
    assert len(rows) == 3
    assert all(r['score'] == '' for r in rows)  # open => no score
    md_text = md_path.read_text()
    assert '| post_id | type | status | forecast | score | note |' in md_text
    assert md_text.count('|') >= 3 * 6  # header + 3 rows-ish
