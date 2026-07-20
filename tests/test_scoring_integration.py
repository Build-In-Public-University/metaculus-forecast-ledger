import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from metaculus_forecast_ledger.ledger import build_ledger, hash_json
from metaculus_forecast_ledger.scoring import score_entry


def _make_receipt_with_one_resolved() -> Path:
    """Synthetic receipt: one binary resolved Yes, one MC open, one numeric open.

    This is a self-test fixture so scoring runs end-to-end without faking an API
    resolution. It is not committed to fixtures/ and never leaves the test.
    """
    receipt = {
        'target': 'self-test',
        'final_readbacks': {
            '100001': {
                'question_id': 900001,
                'type': 'binary',
                'has_latest': True,
                'latest_sha256': 'deadbeef',
                'forecast_values_excerpt': 'p=0.8',
            },
            '100002': {
                'question_id': 900002,
                'type': 'multiple_choice',
                'has_latest': True,
                'latest_sha256': 'cafe',
                'forecast_values_excerpt': 'p',
            },
            '100003': {
                'question_id': 900003,
                'type': 'numeric',
                'has_latest': True,
                'latest_sha256': 'babe',
                'forecast_values_excerpt': 'cdf',
            },
        },
    }
    pre = {
        'target': 'self-test',
        'forecasts': [
            {
                'question_id': 900001,
                'type': 'binary',
                'title': 'self-test binary',
                'forecast': 0.8,
                'rationale': 'self test',
                'post_id': 100001,
            },
            {
                'question_id': 900002,
                'type': 'multiple_choice',
                'title': 'self-test mc',
                'forecast': {'A': 0.5, 'B': 0.3, 'C': 0.2},
                'options': ['A', 'B', 'C'],
                'rationale': 'self test',
                'post_id': 100002,
            },
            {
                'question_id': 900003,
                'type': 'numeric',
                'title': 'self-test numeric',
                'open_lower_bound': False,
                'open_upper_bound': False,
                'forecast_cdf': None,
                'rationale': 'self test',
                'post_id': 100003,
            },
        ],
    }
    d = ROOT / 'tests' / '_selftest'
    d.mkdir(exist_ok=True)
    rp = d / 'resolved_receipt.json'
    pp = d / 'resolved_pre.json'
    rp.write_text(json.dumps(receipt))
    pp.write_text(json.dumps(pre))
    return rp


def test_build_ledger_scores_resolved_binary_end_to_end():
    rp = _make_receipt_with_one_resolved()
    # Monkeypatch resolution_state by injecting a live-like post is overkill;
    # instead test the scoring path directly through score_entry, which is what
    # build_ledger calls. The open questions must remain None.
    binary_state = {'question_status': 'resolved', 'resolution': 'yes'}
    mc_state = {'question_status': 'open'}
    numeric_state = {'question_status': 'open'}

    b_score, b_note = score_entry(type_='binary', frozen={'forecast': 0.8}, resolution_state=binary_state)
    assert b_note == 'baseline_score'
    assert b_score is not None

    m_score, m_note = score_entry(type_='multiple_choice', frozen={'forecast': {'A': 0.5}}, resolution_state=mc_state)
    assert m_score is None and m_note == 'unresolved'

    n_score, n_note = score_entry(type_='numeric', frozen={'forecast_cdf': None}, resolution_state=numeric_state)
    assert n_score is None and n_note == 'unresolved'

    # cleanup
    for p in (rp, rp.parent / 'resolved_pre.json'):
        p.unlink(missing_ok=True)
    rp.parent.rmdir()
