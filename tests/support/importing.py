"""Offline tool turns; source extraction uses the real parser without a worker."""

from packages.resume_core.extraction.parser import extract
from packages.resume_core.models.importing import ImportContent, ImportContentFinish, ImportRead
from resume_api.agent.runtime import RuntimeResult, ScriptedAgentRuntime
from resume_api.importer.session import ImportSession


def importer(monkeypatch, script=None, **runtime_options):
    sessions = {}
    async def start(session):
        sessions[session.url] = session
    async def inline_extract(data, name, pasted, _files):
        return extract(data, name, pasted)
    monkeypatch.setattr(ImportSession, "start", start)
    monkeypatch.setattr("resume_api.rich_projects.run_extract", inline_extract)
    async def turn(value, cancel, emit):
        session = sessions[value.url]
        if script:
            return await script(session, value, cancel)
        await complete(session)
        return RuntimeResult(state="completed")
    return ScriptedAgentRuntime(turn, **runtime_options), sessions


async def read_source(session):
    items, offset = [], 0
    while offset is not None:
        page = await session.dispatcher.call("read_import", ImportRead(offset=offset))
        assert "error" not in page, page
        end = page["nextOffset"]
        selected = session.coordinator.paragraphs[offset:end]
        assert all(p.text in page["text"] for p in selected)
        items.extend({"ref": p.ref, "text": p.text} for p in selected)
        offset = page["nextOffset"]
    return items, session.coordinator.load().sequence


async def complete(session, *, facts=True, finish=True):
    items, _sequence = await read_source(session)
    sections = [{"category": "identity", "refs": [items[0]["ref"]]},
        {"category": "experience", "refs": [item["ref"] for item in items[1:9]]},
        {"category": "skills", "refs": [item["ref"] for item in items[9:]]}]
    digest = ([{"text": "Север: backend, 2021 — настоящее время. Python, PostgreSQL. "
        "Команда сократила обработку на 30%; личный вклад отдельно не указан.",
        "refs": [item["ref"] for item in items[1:6]]},
        {"text": "Запад: CRM, Java/MySQL, 2017–2020. Восток: PHP, отчёты, 2008–2009.",
        "refs": [item["ref"] for item in items[6:9]]}] if facts else [])
    reply = await session.dispatcher.call("save_import", ImportContent.model_validate({
        "facts": digest, "sections": sections,
        "profile": {"name": "Ирина Примерова", "title": "backend-разработчик", "refs": [items[0]["ref"]]}}))
    assert reply.get("durable") and not reply["completed"], reply
    if finish:
        reply = await session.dispatcher.call("finish_import", ImportContentFinish())
        assert reply.get("readyForPublication") and not reply["completed"], reply
    return reply
