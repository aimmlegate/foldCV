"""Resolve the proven agent-only profile through the existing native connection."""

import json
from urllib.parse import urlsplit

from packages.resume_core.assistant_store import AgentFailure
from resume_api.agent.host_profile import AgentProofProfile, TOKEN_ENV


class AgentProfile(AgentProofProfile):
    @classmethod
    def from_connection(cls, connection):
        current = getattr(connection, "experimental_profile", None)
        if current is None or getattr(connection, "executable", None) != current.executable:
            raise AgentFailure("AGENT_RUNTIME_UNSUPPORTED")
        return cls(current.root, current.executable)

    def arguments(self, operation, *, url, tools, allow_web):
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None
                or parsed.path != "/mcp" or parsed.query or parsed.fragment
                or parsed.username is not None or parsed.password is not None):
            raise AgentFailure("AGENT_RUNTIME_UNSUPPORTED")
        config = 'mcp_servers={foldcv={url=' + json.dumps(url) + ',bearer_token_env_var="' + TOKEN_ENV
        config += '",required=true,enabled=true,enabled_tools=' + json.dumps(list(tools))
        config += ',default_tools_approval_mode="approve",startup_timeout_sec=10,tool_timeout_sec=20}}'
        return ("app-server", "--strict-config", "--listen", "stdio://",
            *self.config(operation, allow_web=allow_web), "--config", config)
