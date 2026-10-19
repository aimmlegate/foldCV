"""Resolve catalog intents from durable proof without repeating project writes."""

import hashlib
import os
import re

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.storage import StorageFailure
from packages.resume_core.storage import private_file


def reconcile_action(projects, key, command):
    with projects.state_lock:
        return _reconcile_action(projects, key, command)


def _reconcile_action(projects, key, command):
    project = command["projectId"]
    try:
        result = dict(command["result"])
        if command["commitKind"] == "workspace":
            workspace, checksum = projects.storage.read_committed(project, synchronize=True)
            proof = next((item for item in workspace.mutation_replay if item.client_mutation_id == command["proofId"]), None)
            if proof is not None and proof.request_sha256 == command["payloadSha256"]:
                result["projectRevision"] = workspace.project_revision
            elif proof is None and checksum == command["beforeSha256"]:
                result = {"durable": False, "error": {"code": "AGENT_SAVE_FAILED"}}
            else:
                raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
        else:
            if not re.fullmatch(r"[a-f0-9]{64}\.(docx|foldcv)", command["fileName"]):
                raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
            target = projects.storage._directory(project) / "renders" / command["fileName"]
            if not target.exists():
                result = {"durable": False, "error": {"code": "AGENT_SAVE_FAILED"}}
            else:
                private_file(target)
                with target.open("rb") as stream:
                    if hashlib.sha256(stream.read()).hexdigest() != result["sha256"]:
                        raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
                    os.fsync(stream.fileno())
                descriptor = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        completed = {name: value for name, value in command.items() if name != "receiptReserve"}
        completed.update(status="completed" if result.get("durable") else "failed", result=result)
        if command["commitKind"] == "workspace" and projects.loaded:
            projects.adopt_committed(project, workspace, checksum)
        projects.catalog.record_action(key, completed)
        if not any(item.get("status") == "applying" and item["projectId"] == project for item in projects.catalog.actions().values()):
            projects.catalog_recovery_fences.discard(project)
        return result
    except (AgentFailure, ProjectStoreFailure, StorageFailure, OSError, ValueError, KeyError):
        projects.catalog_recovery_fences.add(project)
        raise AgentFailure("AGENT_OUTCOME_UNKNOWN") from None


def recover_actions(projects):
    with projects.state_lock:
        _recover_actions(projects)


def _recover_actions(projects):
    commands = projects.catalog.actions(synchronize=True)
    projects.catalog_recovery_fences.clear()
    projects.catalog_recovery_fences.update(command["projectId"] for command in commands.values() if command.get("status") == "applying")
    for key, command in commands.items():
        if command.get("status") == "applying":
            try:
                reconcile_action(projects, key, command)
            except AgentFailure:
                pass
