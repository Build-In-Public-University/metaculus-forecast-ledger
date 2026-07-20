"""Metaculus baseline-score functions.

Implements the Baseline score from Metaculus' official scoring code:

    https://github.com/Metaculus/metaculus/blob/main/scoring/score_math.py

The Baseline score compares a forecast to a naive "chance" prior:
  - binary:         uniform 50%
  - multiple_choice: uniform 1/N across available options
  - continuous:     5% in each open tail, uniform over the closed middle

Formula reference (`evaluate_forecasts_baseline_accuracy`):

  categorical (binary / multiple_choice):
      score = 100 * ln(p * N) / ln(N)
      where N = options available at forecast time, p = predicted prob of outcome

  continuous:
      pmf[i] = cdf[i+1] - cdf[i]
      if resolution bucket is a tail (0 or last): baseline = 0.05
      else: baseline = (1 - 0.05 * open_bounds_count) / (len(pmf) - 2)
      score = 100 * ln(pmf[bucket] / baseline) / 2

Scores are resolution-dependent. Unresolved questions return None.

This module is pure and contains no network calls.
"""

from __future__ import annotations

import math
from typing import Any

SOURCE_URL = 'https://github.com/Metaculus/metaculus/blob/main/scoring/score_math.py'


def baseline_score_binary(p_yes: float, outcome_yes: bool) -> float:
    """Baseline score for a binary question.

    N = 2; p = predicted probability of the actual outcome.
    """
    if not (0.0 < p_yes < 1.0):
        raise ValueError('p_yes must be strictly inside (0, 1)')
    p = p_yes if outcome_yes else (1.0 - p_yes)
    n = 2
    return 100.0 * math.log(p * n) / math.log(n)


def baseline_score_multiple_choice(probs: dict[str, float], resolution_option: str) -> float:
    """Baseline score for a multiple-choice question.

    N = number of available options; p = predicted prob of the resolved option.
    """
    if resolution_option not in probs:
        raise ValueError(f'resolution_option {resolution_option!r} not in forecast options')
    if not probs:
        raise ValueError('empty option probabilities')
    n = len(probs)
    p = probs[resolution_option]
    if not (0.0 < p < 1.0):
        raise ValueError('option probability must be strictly inside (0, 1)')
    return 100.0 * math.log(p * n) / math.log(n)


def baseline_score_continuous(
    cdf: list[float],
    resolution_bucket: int,
    open_bounds_count: int,
) -> float:
    """Baseline score for a continuous (numeric/date/discrete) question.

    `cdf` is the monotone CDF over `continuous_range`; length M.
    `resolution_bucket` is the PMF bin index containing the resolved value
    (0 = below lower bound, len(pmf)-1 = above upper bound).
    `open_bounds_count` is the number of open bounds (0, 1, or 2).
    """
    if len(cdf) < 2:
        raise ValueError('cdf must have at least 2 points')
    pmf = [b - a for a, b in zip(cdf, cdf[1:])]
    last = len(pmf) - 1
    if not (0 <= resolution_bucket <= last):
        raise ValueError('resolution_bucket out of pmf range')
    p = pmf[resolution_bucket]
    if p <= 0.0:
        raise ValueError('pmf[resolution_bucket] must be > 0')
    if resolution_bucket in (0, last):
        baseline = 0.05
    else:
        baseline = (1.0 - 0.05 * open_bounds_count) / (len(pmf) - 2)
    if baseline <= 0.0:
        raise ValueError('invalid baseline for continuous score')
    return 100.0 * math.log(p / baseline) / 2.0


def is_resolved(resolution_state: dict[str, Any]) -> bool:
    if resolution_state.get('question_status') in {'resolved', 'annulled'}:
        return True
    if resolution_state.get('resolved') is True:
        return True
    return resolution_state.get('resolution') is not None


def score_entry(
    *,
    type_: str,
    frozen: dict[str, Any],
    resolution_state: dict[str, Any],
    latest: dict[str, Any] | None = None,
) -> tuple[float | None, str]:
    """Resolve a baseline score for one ledger entry.

    Returns (score, note). score is None when not scorable yet.
    """
    if not is_resolved(resolution_state):
        return None, 'unresolved'

    resolution = resolution_state.get('resolution')

    if type_ == 'binary':
        forecast = frozen.get('forecast')
        if not isinstance(forecast, (int, float)):
            return None, 'binary forecast missing in source'
        outcome_yes = resolution in (True, 'yes', 'Yes', 'YES')
        try:
            return baseline_score_binary(float(forecast), outcome_yes), 'baseline_score'
        except ValueError as exc:
            return None, f'binary score error: {exc}'

    if type_ == 'multiple_choice':
        probs = frozen.get('forecast')
        options = frozen.get('options')
        if not isinstance(probs, dict) or not options:
            return None, 'multiple_choice forecast/options missing in source'
        if not isinstance(resolution, str) or resolution not in probs:
            return None, f'resolution option {resolution!r} not in forecast options'
        try:
            return baseline_score_multiple_choice(probs, resolution), 'baseline_score'
        except ValueError as exc:
            return None, f'multiple_choice score error: {exc}'

    if type_ == 'numeric':
        cdf = latest.get('continuous_cdf') if latest else None
        if not cdf and 'forecast_cdf' in frozen:
            cdf = frozen.get('forecast_cdf')
        if not cdf:
            return None, 'continuous CDF unavailable in source; full CDF required'
        open_bounds_count = 0
        if frozen.get('open_lower_bound'):
            open_bounds_count += 1
        if frozen.get('open_upper_bound'):
            open_bounds_count += 1
        bucket = _continuous_resolution_bucket(cdf, resolution)
        if bucket is None:
            return None, 'continuous resolution outside range and no tail mapping'
        try:
            return baseline_score_continuous(cdf, bucket, open_bounds_count), 'baseline_score'
        except ValueError as exc:
            return None, f'continuous score error: {exc}'

    return None, f'unsupported type {type_!r} for scoring'


def _continuous_resolution_bucket(cdf: list[float], resolution: Any) -> int | None:
    """Map a resolved numeric value to a PMF bucket index, or None if unmappable."""
    try:
        value = float(resolution)
    except (TypeError, ValueError):
        return None
    if value <= cdf[0]:
        return 0
    if value >= cdf[-1]:
        return len(cdf) - 2
    for i in range(len(cdf) - 1):
        if cdf[i] <= value < cdf[i + 1]:
            return i
    return None


def extract_resolution(post: dict[str, Any]) -> dict[str, Any]:
    """Normalize the live Metaculus post resolution fields into score_entry inputs.

    Returns a dict with:
      resolved (bool): whether the question has resolved
      type (str|None): resolved forecast type if present
      resolution (Any): the normalized resolution value
                        binary -> bool (True=Yes)
                        multiple_choice -> option label string
                        numeric/date/discrete -> float value
      note (str): why resolution could not be extracted, if applicable

    This only reads fields; it never calls the network.
    """
    question = post.get('question') or {}
    if question.get('status') != 'resolved':
        return {'resolved': False, 'type': None, 'resolution': None, 'note': 'question not resolved'}

    type_ = question.get('type')
    raw = question.get('resolution')
    if raw is None:
        return {'resolved': True, 'type': type_, 'resolution': None, 'note': 'resolution field missing'}

    if type_ == 'binary':
        if isinstance(raw, bool):
            outcome = raw
        else:
            outcome = str(raw).strip().lower() in ('yes', 'true', '1')
        return {'resolved': True, 'type': type_, 'resolution': outcome, 'note': 'ok'}

    if type_ == 'multiple_choice':
        if not isinstance(raw, str):
            return {'resolved': True, 'type': type_, 'resolution': None, 'note': 'mc resolution not a string'}
        return {'resolved': True, 'type': type_, 'resolution': raw, 'note': 'ok'}

    if type_ in ('numeric', 'date', 'discrete'):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return {'resolved': True, 'type': type_, 'resolution': None, 'note': 'continuous resolution not numeric'}
        return {'resolved': True, 'type': type_, 'resolution': value, 'note': 'ok'}

    return {'resolved': True, 'type': type_, 'resolution': None, 'note': f'unsupported resolved type {type_!r}'}


def score_post(post: dict[str, Any], frozen: dict[str, Any], latest: dict[str, Any] | None = None) -> tuple[float | None, str]:
    """One-call scoring for a live Metaculus post.

    Combines extract_resolution with score_entry so a resolved live post flows
    straight to a baseline score. Returns (score, note).
    """
    extracted = extract_resolution(post)
    if not extracted['resolved']:
        return None, 'unresolved'
    if extracted['note'] != 'ok':
        return None, extracted['note']
    type_ = extracted['type'] or frozen.get('type')
    if not isinstance(type_, str):
        return None, 'resolved post missing type'
    if latest is None:
        question = post.get('question') or {}
        latest = (question.get('my_forecasts') or {}).get('latest')
    resolution_state = {
        'question_status': 'resolved',
        'resolution': extracted['resolution'],
        'resolved': True,
    }
    return score_entry(type_=type_, frozen=frozen, resolution_state=resolution_state, latest=latest)
