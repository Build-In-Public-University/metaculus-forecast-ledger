from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .audit import audit_ledger, write_outcome_summary_csv
from .ledger import build_ledger, write_ledger, write_ledger_summary_csv, write_ledger_summary_md


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a read-only Metaculus forecast ledger.')
    parser.add_argument('--post-receipt', required=True, help='Path to a Metaculus POST receipt artifact')
    parser.add_argument('--pre-post', help='Path to the matching pre-POST forecast packet')
    parser.add_argument('--output', default='artifacts/ledger/metaculus_forecast_ledger.json')
    parser.add_argument('--summary-csv', default='artifacts/ledger/metaculus_forecast_ledger_summary.csv')
    parser.add_argument('--summary-md', default='artifacts/ledger/metaculus_forecast_ledger_summary.md')
    parser.add_argument('--outcomes', default='artifacts/ledger/outcomes.jsonl')
    parser.add_argument('--outcome-summary-csv', default='artifacts/ledger/outcome_summary.csv')
    parser.add_argument('--no-audit', action='store_true', help='Do not append resolution audit events')
    parser.add_argument('--no-fetch', action='store_true', help='Do not call Metaculus; build from receipt artifacts only')
    parser.add_argument('--token-env', default='METACULUS_TOKEN', help='Environment variable containing Metaculus token')
    args = parser.parse_args()

    token = os.environ.get(args.token_env)
    ledger = build_ledger(
        Path(args.post_receipt),
        Path(args.pre_post) if args.pre_post else None,
        token=token,
        fetch=not args.no_fetch,
    )
    out = write_ledger(ledger, args.output)
    csv_path = write_ledger_summary_csv(ledger, args.summary_csv)
    md_path = write_ledger_summary_md(ledger, args.summary_md)
    audit_result = {'events_appended': 0, 'discrepancies': 0}
    outcome_csv = None
    if not args.no_audit:
        audit_result = audit_ledger(ledger, args.outcomes)
        outcome_csv = write_outcome_summary_csv(args.outcomes, args.outcome_summary_csv)
    print(json.dumps({
        'output': str(out),
        'summary_csv': str(csv_path),
        'summary_md': str(md_path),
        'outcomes': args.outcomes if not args.no_audit else None,
        'outcome_summary_csv': str(outcome_csv) if outcome_csv else None,
        'audit': audit_result,
        'entry_count': ledger['entry_count'],
        'ledger_sha256': ledger['ledger_sha256'],
        'fetch': not args.no_fetch,
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
