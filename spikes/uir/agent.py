"""Deterministic UIR presentation proof over the real bound tool transport."""

import asyncio
import json
import threading

import httpx

from resume_api.agent.runtime import RuntimeResult


class UIRAgent:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event(); self.release.set()
        self.turns = []
        self.tools = []

    async def __call__(self, value, cancel, emit):
        context = json.loads(value.prompt.partition("\n")[2])
        message = context["message"].lower()
        self.turns.append({"model": value.model, "message": context["message"], "scope": context["scope"],
            "allowEdits": context["allowEdits"], "allowWeb": context["allowWeb"]})
        count = 0
        async with httpx.AsyncClient(timeout=30, headers={"Authorization": "Bearer " + value.token,
                "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}) as client:
            async def call(name, arguments):
                nonlocal count
                count += 1
                event = {"callId": "uir_" + str(count), "name": name, "error": None}
                emit("tool.started", event)
                response = await client.post(value.url, json={"jsonrpc": "2.0", "id": count,
                    "method": "tools/call", "params": {"name": name, "arguments": arguments}})
                response.raise_for_status()
                result = json.loads(response.json()["result"]["content"][0]["text"])
                self.tools.append({"name": name, "error": result.get("error")})
                emit("tool.failed" if result.get("error") else "tool.completed", {**event, "error": result.get("error")})
                return result

            selected = context["scope"].get("selection")
            outline = json.loads(context["outline"]["content"])
            block_id = selected["anchor"]["blockId"] if selected else next(
                (b["id"] for b in outline["blocks"] if b["id"] == "profile"),
                next(b["id"] for b in outline["blocks"] if b["type"] == "paragraph"))
            cell = selected["anchor"]["cellId"] if selected else None
            read = await call("get_resume_context", {"query": {"kind": "document", "ids": [cell or block_id]}})
            if read.get("error"):
                return RuntimeResult(error=read["error"]["code"], text="Не удалось прочитать фрагмент.", tool_calls=count)
            self.entered.set()
            if "hold" in message or "стоп" in message:
                self.release.clear()
                while not self.release.is_set():
                    if cancel.is_set():
                        return RuntimeResult(state="cancelled", error="AGENT_CANCELLED", tool_calls=count)
                    await asyncio.sleep(.02)
            if "ошибка" in message:
                return RuntimeResult(error="AGENT_PROCESS_FAILED", text="Не удалось завершить задачу. Повторите её явно.", tool_calls=count)
            source = await call("read_public_page", {"url": "https://example.com/uir-synthetic-source"}) if context["allowWeb"] else None
            source_ids = [source["source"]["id"]] if source and not source.get("error") else []
            snapshot = read["snapshot"]["id"]
            await call("publish_findings", {"request": {"findings": [{"severity": "info", "message": "Проверьте ясность формулировки.",
                "targets": [{"snapshotId": snapshot, "blockId": block_id, "cellId": cell, "recordId": None,
                    "fieldKey": None, "start": None, "end": None}], "sourceIds": source_ids}]}})
            edited = False
            if context["allowEdits"] and "измени" in message:
                start = selected["anchor"]["offset"] if selected else 0
                end = selected["head"]["offset"] if selected else 9
                prepared = await call("prepare_edit_batch", {"request": {"key": "uir_presentation_edit", "snapshotIds": [snapshot],
                    "operations": [{"kind": "replace_text", "target": {"snapshotId": snapshot, "blockId": block_id,
                        "cellId": cell, "field": "content", "start": min(start, end), "end": max(start, end)}, "content": [{"text": "UIR07"}]}]}})
                if not prepared.get("error") and prepared.get("batchId"):
                    receipt = await call("apply_edit_batch", {"request": {"batchId": prepared["batchId"]}})
                    edited = receipt.get("durable", False)
                    await call("get_resume_context", {"query": {"kind": "document", "ids": [cell or block_id]}})
            await call("check_resume", {})
            text = ("Изменения сохранены. Одна отмена в истории редактора." if edited else "Проверка завершена без изменения резюме.")
            if source_ids: text += " Источник: " + source_ids[0]
            emit("message.delta", {"text": text})
            return RuntimeResult(state="completed", text=text, tool_calls=count)
