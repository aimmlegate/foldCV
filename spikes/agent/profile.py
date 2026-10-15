"""Per-process assistant controls over the existing native login profile."""

from __future__ import annotations

import json
from pathlib import Path

from resume_api.cli.experimental_profile import ExperimentalCliProfile


TOKEN_ENV = "FOLDCV_AGENT_MCP_CAPABILITY"
TOOLS = ("get_resume_context", "check_resume", "read_public_page")


class AgentProofProfile(ExperimentalCliProfile):
    def config(self, operation: Path, *, url: str | None = None,
               allow_web: bool = True) -> list[str]:
        values = [
            'approvals_reviewer="user"',
            'web_search="live"' if allow_web else 'web_search="disabled"',
            'features.guardian_approval=false',
            'features.daemon_auto_start=false',
            'features.multi_agent=false',
            'features.multi_agent_v2=false',
            'model_auto_compact_token_limit=1000000',
            'model_reasoning_effort="medium"',
            'model_reasoning_summary="none"',
        ]
        if url is not None:
            tools = TOOLS if allow_web else TOOLS[:2]
            values.append('mcp_servers={foldcv={url=' + json.dumps(url)
                          + ',bearer_token_env_var="' + TOKEN_ENV
                          + '",required=true,enabled=true,enabled_tools='
                          + json.dumps(tools) + ',default_tools_approval_mode="approve"'
                          + ',startup_timeout_sec=10,tool_timeout_sec=20}}')
        return [*super().config(operation),
                *(part for value in values for part in ("--config", value))]
