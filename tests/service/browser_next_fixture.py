"""API-served built recovery entry with controlled creation replies only."""

import asyncio
from pathlib import Path
import socket
import sys
import json
import hashlib
from dataclasses import replace

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from resume_api.app import create_app
from tests.recovery.generation_fixtures import CreationProvider, frozen_now
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.gui_rewriting import GuiRewriteProposal
from packages.resume_core.gui_reconciliation import GuiReconcileProposal
from packages.resume_core.gui_drafting import GuiDraftProposal
from packages.resume_core.gui_normalization import GuiSemanticProposal
from packages.resume_core.models.recovery import GuiLeadershipFact
from resume_api.providers.content import ContentFailure
from resume_api.gui_rendering import GuiDocxRenderer
from packages.resume_core.rendering.docx_errors import failure
from resume_api.connection import Metadata, Quota, ConnectionFailure


class ControlledProvider(CreationProvider):
    def __init__(self, root, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root = root

    def generate(self, request, files, cancel):
        if (self.root / 'multiple-examples').exists() and request.result_type is GuiSemanticProposal:
            payload = json.loads(request.text)
            expected = hashlib.sha256((ROOT/'tests/fixtures/recovery/E2.txt').read_bytes()).hexdigest()
            self.example = 'E2' if payload['input']['sources'][0]['byteSha256'] == expected else 'E1'
        path = self.root/'model-requests.json'
        records = json.loads(path.read_text()) if path.exists() else []
        records.append({'model':request.policy.model,'kind':json.loads(request.text)['task']});path.write_text(json.dumps(records))
        if request.result_type is GuiRewriteProposal:
            (self.root / "rewrite-started").touch()
            while (self.root / "hold-rewrite").exists():
                if cancel.wait(.01):
                    raise ContentFailure("CANCELLED", logical_attempts=1)
        if request.result_type is GuiReconcileProposal:
            (self.root / 'analysis-started').touch()
            while (self.root / 'hold-analysis').exists():
                if cancel.wait(.01):
                    (self.root / 'analysis-released').touch()
                    raise ContentFailure('CANCELLED', logical_attempts=1)
            if (self.root / 'fail-analysis').exists(): raise ContentFailure('QUOTA_EXHAUSTED', logical_attempts=1)
            (self.root / 'analysis-released').touch()
        response = super().generate(request, files, cancel)
        if (self.root / 'related-example').exists() and request.result_type is GuiDraftProposal:
            reply = response.value.model_copy(deep=True)
            fact = next(fact for fact in self.normalized.facts if isinstance(fact, GuiLeadershipFact))
            for field in reply.fields:
                if field.field_id == 'profile/text' or field.field_id.endswith('/tasks') and field.field_id.startswith('job:'+fact.job_id+'/'):
                    field.text, field.fact_ids = 'Обучила двух новых разработчиков.', [fact.id]
            return replace(response, value=reply)
        if (self.root / 'related-example').exists() and request.result_type is GuiReconcileProposal:
            payload = json.loads(request.text)['input']
            fact = next((item for item in payload['facts'] if item['kind']=='leadership'), None)
            if fact and any('трёх' in field.get('text','') for field in payload['changedFields']):
                fact = GuiLeadershipFact.model_validate(fact);fact.value.action = 'Обучила трёх новых разработчиков'
                fact.value.team_size.number = 3
                reply = response.value.model_copy(deep=True);reply.facts = [fact]
                for field in reply.field_facts:
                    if field.field_id.endswith('/tasks'): field.fact_ids = [fact.id]
                raw = reply.model_dump(mode='json',by_alias=True)
                raw['annotations'] = [{'id':'related-profile-conflict','type':'conflicting','code':'trainee_conflict',
                    'anchor':{'kind':'field','fieldId':'profile/text','range':None},'factIds':[fact.id],
                    'reason':'В опыте изменилось число обученных разработчиков.','updateSuggestionId':'related-profile-update'}]
                raw['suggestions'] = [{'id':'related-profile-update','factIds':[fact.id],
                    'replacements':[{'fieldId':'profile/text','range':None,'text':'Обучила трёх новых разработчиков.'}],
                    'reason':'Обновить прежнее упоминание в профиле.'}]
                return replace(response, value=GuiReconcileProposal.model_validate(raw))
        return response


class ControlledRenderer(GuiDocxRenderer):
    def __init__(self, root):
        self.root, self.calls = root, 0

    async def render(self, document, anchors, files):
        self.calls += 1
        (self.root / "render-count.json").write_text(json.dumps({"count": self.calls}))
        if (self.root / "hold-export").exists():
            (self.root / "export-started").touch()
            while (self.root / "hold-export").exists():
                await asyncio.sleep(.01)
        if (self.root / "fail-export").exists():
            raise failure("DOCX_BLOCK_PAGE_BUDGET", "candidate.summary", anchors)
        return await super().render(document, anchors, files)


class ControlledConnection:
    def __init__(self, root):
        self.root = root
    def inspect(self, _files, cancel, *, full=True):
        path = self.root/'connection-actions.json'
        actions = json.loads(path.read_text()) if path.exists() else []
        actions.append('status' if full else 'discover');path.write_text(json.dumps(actions))
        while (self.root/'hold-connection').exists():
            if cancel.wait(.01):raise ConnectionFailure('METADATA_FAILED')
        case = (self.root/'connection-case').read_text() if (self.root/'connection-case').exists() else 'connected'
        if case == 'login_required':raise ConnectionFailure('LOGIN_REQUIRED')
        if case == 'cli_missing':raise ConnectionFailure('CLI_MISSING')
        quota = Quota('exhausted',100) if case == 'quota_exhausted' else Quota() if case == 'unknown_limits' else Quota('available',25)
        return Metadata('synthetic-cli',('fixture-model-a','fixture-model-b'),'plus',quota)
    def login(self, _files, _cancel):
        (self.root/'native-login-called').touch()
        raise ConnectionFailure('LOGIN_REQUIRED')


def retain_evidence(root, store, example):
    for id, workspace in store.workspaces.items():
        if workspace.project is None:
            continue
        evidence = root / "evidence" / id
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "workspace.json").write_text(workspace.model_dump_json(by_alias=True, indent=2) + "\n")
        for (pid, source_id), content in store.originals.items():
            if pid == id:
                (evidence / (source_id + ".txt")).write_bytes(content)
        for snapshot in workspace.project.renders:
            content = store.artifacts.get((id, snapshot.id))
            if content is not None:
                (evidence / (snapshot.id + ".docx")).write_bytes(content)
        (evidence / "test-evidence.json").write_text(json.dumps({
            "controlledProvidersOnly": True, "nativeInference": False,
            "frozenClock": "2026-10-11T12:00:00+00:00", "example": example,
        }, indent=2) + "\n")


async def main():
    root, dist = Path(sys.argv[1]), Path(sys.argv[2])
    example = sys.argv[3] if len(sys.argv) > 3 else "E1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = create_app(origin=origin, secret="synthetic-next-secret-0123456789",
            temp_root=root / "operations", data_root=root / "FoldCV", dist=dist,
            gui_provider=ControlledProvider(root, example.split("-")[0], remove_focus=example.endswith("-focus")),
            gui_renderer=ControlledRenderer(root), gui_clock=frozen_now, connection_adapter=ControlledConnection(root))
        store = app.app.state.gui_projects
        if (root / 'pause-analysis').exists():
            store.rules.load()
            store.preferences.save_analysis(False)
        save = store.storage.save
        def controlled_save(workspace, originals, artifacts):
            if (root / "fail-user-saves").exists() and workspace.project and workspace.project.document.profile.text.origin == "user":
                raise ProjectStoreFailure("PROJECT_SAVE_FAILED")
            save(workspace, originals, artifacts)
        store.storage.save = controlled_save
        cleanup = store.storage.cleanup_deleted
        def controlled_cleanup(id):
            if (root/'fail-project-cleanup').exists():
                from packages.resume_core.storage import locked_root
                with locked_root(store.storage.root,'.projects.lock'):
                    registry=store.storage._registry();entry=next(item for item in registry.entries if item.project_id==id)
                    entry.cleanup_status='failed';store.storage._write_registry(registry);return entry
            return cleanup(id)
        store.storage.cleanup_deleted=controlled_cleanup
        run = store._run
        async def run_retained(*args):
            await run(*args)
            retain_evidence(root, store, example)
        store._run = run_retained
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
            proxy_headers=False, access_log=False, log_level="critical", timeout_graceful_shutdown=2))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("Controlled entry server failed")
            await asyncio.sleep(0.01)
        print(origin, flush=True)
        await task


if __name__ == "__main__":
    asyncio.run(main())
