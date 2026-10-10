"""Keep source bytes, source text, and stable source units for later views."""

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from extract import extract


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_units(source):
    units = []
    for page in source['pages']:
        paragraphs = re.split(r'\n\s*\n', page['text'])
        for paragraph in paragraphs:
            # Keep wrapped lines together, but separate distinct bullet claims.
            for part in re.split(r'\n(?=\s*[-•]\s)', paragraph):
                text = part.strip()
                if text:
                    units.append({'id': f'u{len(units) + 1:04d}', 'page': page['page'], 'text': text})
    return units


def prepare(input_path, folder, as_of):
    folder.mkdir(parents=True, exist_ok=True)
    archive_path = folder / 'archive.json'
    if archive_path.exists():
        raise ValueError('Archive already exists; create a new version instead of overwriting it')
    snapshot = folder / ('original' + input_path.suffix.lower())
    if snapshot.exists() and digest(snapshot) != digest(input_path):
        raise ValueError('Existing source snapshot differs')
    shutil.copyfile(input_path, snapshot)
    source = extract(snapshot)
    source['file'] = input_path.name
    (folder / 'source.json').write_text(json.dumps(source, ensure_ascii=False, indent=2))
    archive = {'schema_version': 2, 'as_of': as_of, 'source_snapshot': snapshot.name,
               'source': source, 'units': source_units(source), 'classifications': {},
               'jobs': [], 'global_technologies': []}
    archive_path.write_text(json.dumps(archive, ensure_ascii=False, indent=2))
    readable = '\n\n'.join(f"[{u['id']} | page {u['page']}]\n{u['text']}" for u in archive['units'])
    (folder / 'units.txt').write_text(readable)
    return len(archive['units'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--as-of', required=True)
    args = parser.parse_args()
    print(f'Preserved {prepare(args.input, args.folder, args.as_of)} source units.')
