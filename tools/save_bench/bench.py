"""In-process benchmark of one V7 text edit through the /v2 edit route (default) or the in-memory repository directly.

Usage: python -I bench.py <checkout-root> [--api v2|repository] [--edits 3] [--out results.txt] [--records 720 --coverage 1774]
Uses only the synthetic fixture under a new temporary store. No user data, no network, no providers.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def text_length(block):
    from packages.resume_core.rich_mutations import inline_text
    return sum(len(inline_text(span).encode('utf-16-le')) // 2 for span in block.content)


def rss_mb():
    return int(subprocess.run(['ps', '-o', 'rss=', '-p', str(os.getpid())], capture_output=True, text=True).stdout) / 1024


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    parser.add_argument('--api', choices=['v2', 'repository'], default='v2',
        help='the /v2 routes, or the in-memory repository directly')
    parser.add_argument('--edits', type=int, default=3)
    parser.add_argument('--out', default=None)
    parser.add_argument('--records', type=int, default=720)
    parser.add_argument('--coverage', type=int, default=1774)
    parser.add_argument('--dump-wires', default=None, help='directory for the response of edit 0')
    parser.add_argument('--rss', action='store_true', help='report resident memory before and after the edits')
    args = parser.parse_args()
    sys.path[:0] = [args.root, args.root + '/services/api/src']
    import gc
    import fixture
    from packages.resume_core.templates.compiler import canonical
    from tests.templates.test_template_preparation import command
    workspace, sources = fixture.build(args.root, records=args.records, coverage=args.coverage)
    sizes = fixture.sizes(workspace)
    store = Path(tempfile.mkdtemp(prefix='foldcv-spc-', dir='/private/tmp'))
    mode = os.environ.get('SPC_GC', '')
    out = [f'fixture {json.dumps(sizes)}', f'checkout {args.root}', f'python {sys.version.split()[0]}', f'api {args.api}']
    if args.api == 'repository':
        from packages.resume_core.project_repository import ProjectRepository
        from packages.resume_core.template_api import TemplateProjectResponseV1
        from packages.resume_core.template_preparation import prepare_edit
        from packages.resume_core.templates.presentation import project_presentation, snapshot_identity
        repo = ProjectRepository(store / 'data')
        repo.create(workspace, blobs=[('sources', key, raw, hashlib.sha256(raw).hexdigest()) for key, raw in sources.items()])
        project = workspace.project_id

        def run_edit(preparation):
            def build(current):
                response = TemplateProjectResponseV1(schemaVersion=1, workspace=current, snapshot=snapshot_identity(current),
                    presentation=project_presentation(current), durability='durable', savedProjectRevision=current.project_revision,
                    savedDocumentRevision=current.document_revision, saveError=None, generation=None, identity=None)
                prepared = prepare_edit(response, preparation)
                return prepared.preview.workspace, {'created_ids': prepared.created_ids}
            return repo.mutate(project, base_revision=repo.read(project).project_revision,
                client_mutation_id=preparation.client_mutation_id, request_sha256=hashlib.sha256(canonical(preparation)).hexdigest(),
                action_id=preparation.capture.action_id, kind='edit', build=build)
        current = lambda: repo.read(project)
        close = lambda: None
    else:
        from tests.projects.support import v2_client
        client, project = v2_client(store, workspace, sources)
        run_edit, current, close = client.edit, client.current, client.close
    if mode == 'freeze':
        gc.collect(); gc.freeze(); gc.set_threshold(50000, 20, 20)
    elif mode == 'off':
        gc.disable()
    out.append(f'gc {mode or "default"} {gc.get_threshold()}')
    start_rss = rss_mb()
    totals = []
    try:
        for index in range(args.edits):
            value = current()
            blocks = value.project.document.regions[2].blocks
            block = blocks[(index * 7) % len(blocks)]
            point = text_length(block)
            preparation = command(value, start=point, end=point, text='x', target={'kind': 'literal'})
            preparation.operations[0].range.block_id = block.id
            preparation.operations[0].range.before_revision = block.revision
            preparation.client_mutation_id = f'edit-{index}'
            preparation.capture.action_id = f'action-{index}'
            preparation.capture.action_token = index + 1
            started = time.perf_counter()
            run_edit(preparation)
            totals.append({'edit': round((time.perf_counter() - started) * 1000)})
            out.append(f'##### edit {index}: ' + json.dumps(totals[-1]))
            if args.dump_wires and index == 0:
                from resume_api.projects.service import response_for_workspace
                folder = Path(args.dump_wires)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'response.json').write_text(response_for_workspace(current()).model_dump_json(by_alias=True))
        if args.rss:
            gc.collect()
            out.append(f'##### rss MB: start {start_rss:.0f}, after {args.edits} edits {rss_mb():.0f}, growth {rss_mb() - start_rss:.0f}')
        out.append('##### per-edit totals (ms): ' + json.dumps(totals))
        text = '\n'.join(out)
        print(text)
        if args.out:
            Path(args.out).write_text(text)
    finally:
        close()
        shutil.rmtree(store, ignore_errors=True)


if __name__ == '__main__':
    main()
