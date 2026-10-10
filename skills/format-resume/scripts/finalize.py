"""Build evidence and estimates from an archive without rewriting candidate text."""

import argparse
import json
from pathlib import Path

from archive import digest
from policy import estimate


def finalize(view, archive, archive_path):
    view['schema_version'] = 2
    view['archive_sha256'] = digest(archive_path)
    view['evidence'] = {u['id']: {'page': u['page'], 'quote': u['text']} for u in archive['units']}
    for item in view['focus']:
        item['duration'], item['estimate'] = estimate(item['label']['text'], archive)
    return view


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('view', type=Path)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    view = finalize(json.loads(args.view.read_text()), json.loads(args.archive.read_text()), args.archive)
    args.view.write_text(json.dumps(view, ensure_ascii=False, indent=2))
    print('Updated evidence, archive binding, and derived focus experience.')
