"""CT05 M7e live proof: a strict template import of a synthetic source through the real Codex CLI in an isolated store.

Every model dispatch (one `codex exec` run) is charged to the D091 ledger before its process starts. Once the
allowance is spent no further dispatch starts. The store is a new isolated root; the CLI profile is the existing
FoldCV sign-in, used in place and never copied.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'services/api/src')]
LEDGER = ROOT / 'docs/gui/handoffs/CONFIGURABLE-TEMPLATES/native-attempts.json'
PROFILE = Path.home() / 'Library/Application Support/FoldCV/cli-experiment'


def now():
    return datetime.now(timezone.utc).isoformat()


class Allowance:
    """The D091 ledger: a dispatch is recorded and charged before it starts, whatever its outcome."""

    def __init__(self, path, run):
        self.path, self.run, self.lock = path, run, threading.Lock()

    def _write(self, ledger):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
        os.replace(temporary, self.path)

    def charge(self, model):
        with self.lock:
            ledger = json.loads(self.path.read_text())
            if ledger['spent'] >= ledger['cap']:
                return None
            identifier = 'CT-%02d' % (len(ledger['attempts']) + 1)
            ledger['attempts'].append({'id': identifier, 'run': self.run, 'model': model, 'status': 'dispatched',
                'startedAt': now(), 'finishedAt': None, 'elapsedSeconds': None, 'code': None})
            ledger['spent'] += 1
            self._write(ledger)
            return identifier

    def settle(self, identifier, status, code, elapsed):
        with self.lock:
            ledger = json.loads(self.path.read_text())
            record = next(item for item in ledger['attempts'] if item['id'] == identifier)
            record.update(status=status, code=code, finishedAt=now(), elapsedSeconds=round(elapsed, 2))
            self._write(ledger)


def guard_dispatch(allowance, evidence):
    from resume_api.providers.codex_cli import CodexCliProvider
    from resume_api.providers.content import ContentFailure
    original = CodexCliProvider._run

    def run(provider, files, args, deadline, cancel, **kwargs):
        if not args or args[0] != 'exec' or '--help' in args:
            return original(provider, files, args, deadline, cancel, **kwargs)
        model = args[args.index('--model') + 1] if '--model' in args else None
        identifier = allowance.charge(model)
        if identifier is None:
            raise ContentFailure('LIVE_ALLOWANCE_SPENT')
        started = time.monotonic()
        try:
            result = original(provider, files, args, deadline, cancel, **kwargs)
        except Exception as error:
            allowance.settle(identifier, 'failed', getattr(error, 'code', type(error).__name__), time.monotonic() - started)
            raise
        allowance.settle(identifier, 'completed', None, time.monotonic() - started)
        (evidence / (identifier + '.stdout')).write_bytes(result[0])
        return result

    CodexCliProvider._run = run


async def main(args):
    import uvicorn
    from packages.resume_core.storage import atomic_write
    from packages.resume_core.templates.store import TemplateStore
    from resume_api.app import create_app
    from resume_api.cli.experimental_profile import installed_profile
    from tests.templates.employment_fixtures import employment_package
    root = args.root.resolve()
    if root.parent != Path('/private/tmp') or not root.name.startswith('foldcv-ct05-live-') or root.exists():
        raise SystemExit('A new /private/tmp/foldcv-ct05-live-* root is required')
    root.mkdir(mode=0o700)
    data, evidence = root / 'data', root / 'evidence'
    data.mkdir(mode=0o700); evidence.mkdir(mode=0o700)
    # The store selects the user's chosen model explicitly; nothing is picked by this tool.
    atomic_write(data / 'preferences.json', json.dumps({'schemaVersion': 1, 'selectedModel': args.model,
        'automaticAnalysis': False, 'theme': 'system'}).encode())
    guard_dispatch(Allowance(LEDGER, root.name), evidence)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen(128)
        origin = 'http://127.0.0.1:' + str(listener.getsockname()[1]); secret = secrets.token_urlsafe(32)
        app = create_app(origin=origin, secret=secret, temp_root=root / 'operations', dist=args.dist.resolve(),
            experimental_profile=installed_profile(PROFILE), data_root=data, background_enabled=True,
            template_import_call_cap=args.call_cap)
        TemplateStore(app.app.state.rich_projects.storage.root).activate(employment_package())

        @app.app.get('/v1/ct05/live')
        async def live():
            return {'ledger': json.loads(LEDGER.read_text()), 'callCap': args.call_cap, 'model': args.model}
        app.app.router.routes.insert(0, app.app.router.routes.pop())
        launch = root / 'launch.json'
        atomic_write(launch, json.dumps({'url': origin + '/#secret=' + secret, 'pid': os.getpid()}).encode()); launch.chmod(0o600)
        print(json.dumps({'origin': origin, 'pid': os.getpid(), 'root': str(root)}), flush=True)
        await uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', access_log=False, server_header=False, log_level='warning',
            timeout_graceful_shutdown=2)).serve(sockets=[listener])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--call-cap', type=int, required=True)
    asyncio.run(main(parser.parse_args()))
