"""실제 DB 연결 없이 DATA CSV와 고정된 BE seed를 대조한다."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from data_contract import ROOT, compare_seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--seed-dir', type=Path, default=ROOT.parent / 'BE/src/main/resources/db/migration')
    parser.add_argument('--json', type=Path, help='검증 보고서 저장 경로 (기존 파일은 덮어쓰지 않음)')
    args = parser.parse_args()
    try:
        report = compare_seed(args.data_dir, args.seed_dir)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.json:
            with args.json.open('x', encoding='utf-8') as stream:
                stream.write(text + '\n')
        print(text)
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(f'검증 실패: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
