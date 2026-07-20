import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from metaculus_forecast_ledger.scoring import (
    baseline_score_binary,
    baseline_score_continuous,
    baseline_score_multiple_choice,
    is_resolved,
    score_entry,
)


def test_binary_baseline_formula():
    # perfect forecast on Yes -> ~ +99.9
    s = baseline_score_binary(0.999, outcome_yes=True)
    assert s == 100.0 * math.log(0.999 * 2) / math.log(2)
    # 50/50 -> 0
    assert abs(baseline_score_binary(0.5, outcome_yes=True)) < 1e-9
    # wrong side, confident -> negative
    assert baseline_score_binary(0.999, outcome_yes=False) < 0


def test_multiple_choice_baseline_formula():
    # 3 options, perfect on resolved -> 100*ln(1)/ln(3)=0? no: p=1 => p*N=N => ln(N)/ln(N)=1 => 100
    probs = {'a': 1 / 3, 'b': 1 / 3, 'c': 1 / 3}
    assert abs(baseline_score_multiple_choice(probs, 'a')) < 1e-9  # uniform => 0
    perfect = {'a': 0.999, 'b': 0.0005, 'c': 0.0005}
    s = baseline_score_multiple_choice(perfect, 'a')
    expected = 100.0 * math.log(0.999 * 3) / math.log(3)
    assert abs(s - expected) < 1e-9


def test_continuous_baseline_formula():
    # 11 cdf points => 10 pmf bins, closed bounds
    cdf = [i / 10 for i in range(11)]
    # middle bucket 5, closed bounds: baseline = (1 - 0.05*0)/(10-2) = 0.125
    # uniform pmf[5]=0.1 => 100*ln(0.1/0.125)/2
    score = baseline_score_continuous(cdf, 5, open_bounds_count=0)
    assert abs(score - 100.0 * math.log(0.1 / 0.125) / 2.0) < 1e-9
    # tail bucket, p=0.1, baseline=0.05 => 100*ln(2)/2
    s = baseline_score_continuous(cdf, 0, open_bounds_count=0)
    assert abs(s - 100.0 * math.log(0.1 / 0.05) / 2.0) < 1e-9


def test_is_resolved_variants():
    assert is_resolved({'question_status': 'resolved'})
    assert is_resolved({'resolved': True})
    assert is_resolved({'resolution': 'yes'})
    assert not is_resolved({'question_status': 'open'})
    assert not is_resolved({})


def test_score_entry_unresolved_returns_none():
    state = {'question_status': 'open'}
    score, note = score_entry(type_='binary', frozen={'forecast': 0.67}, resolution_state=state)
    assert score is None and note == 'unresolved'


def test_score_entry_binary_resolved():
    state = {'question_status': 'resolved', 'resolution': 'yes'}
    score, note = score_entry(type_='binary', frozen={'forecast': 0.67}, resolution_state=state)
    assert note == 'baseline_score'
    assert score == baseline_score_binary(0.67, outcome_yes=True)


def test_score_entry_continuous_requires_full_cdf():
    state = {'question_status': 'resolved', 'resolution': 69.0}
    # fixture-style frozen only has cdf head/tail, no full list
    frozen = {'open_lower_bound': True, 'open_upper_bound': False, 'forecast_cdf_head': None}
    score, note = score_entry(type_='numeric', frozen=frozen, resolution_state=state, latest=None)
    assert score is None and note.startswith('continuous CDF unavailable')


def test_score_entry_continuous_with_full_cdf():
    state = {'question_status': 'resolved', 'resolution': 0.69}
    cdf = [i / 100 for i in range(101)]
    frozen = {'open_lower_bound': True, 'open_upper_bound': False}
    latest = {'continuous_cdf': cdf}
    score, note = score_entry(type_='numeric', frozen=frozen, resolution_state=state, latest=latest)
    assert note == 'baseline_score'
    assert score is not None
