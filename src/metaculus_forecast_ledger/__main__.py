from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .ledger import build_ledger, write_ledger


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a read-only Metaculus forecast ledger.')
    parser.add_argument('--post-receipt', required=True, help='Path to a Metaculus POST receipt artifact')
    parser.add_argument('--pre-post', help='Path to the matching pre-POST forecast packet')
    parser.add_argument('--output', default='artifacts/ledger/metaculus_forecast_ledger.json')
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
    print(json.dumps({'output': str(out), 'entry_count': ledger['entry_count'], 'ledger_sha256': ledger['ledger_sha256'], 'fetch': not args.no_fetch}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
