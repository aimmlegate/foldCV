# T00B CLI experiment

Run from the repository root with Python 3.13 (the existing `.venv`). No new
dependencies are needed. This is a process experiment, not a production adapter.

```sh
.venv/bin/python -m unittest discover -s tests/cli_spike -v
.venv/bin/python -m unittest discover -s skills/format-resume/tests -v
```

The offline suite copies `tests/cli_spike/fake_cli.py` into a fresh temporary
directory, gives it an executable Python shebang, and supplies synthetic scripts.
It never invokes the real Codex binary or accesses an account. On macOS, allow
signals to the test's own process groups and `/bin/ps` process metadata. The
restricted agent sandbox initially denied these operations; run the full suite
in a normal terminal or with the execution tool's approved escalation.

The installed binary was outside PATH. Use an explicit path:

```sh
.venv/bin/python -m spikes.cli.runner probe --executable /Users/fostral/.codex/plugins/.plugin-appserver/codex-cli/bin/codex
.venv/bin/python -m spikes.cli.runner metadata --executable /Users/fostral/.codex/plugins/.plugin-appserver/codex-cli/bin/codex
```

`probe` checks version, exec options and native login status. `metadata` uses
`initialize`, `initialized`, `account/read` with `refreshToken=false`, and
`model/list`. Neither creates a thread or starts generation. CLI-owned native
credentials stay in the default home. Account identifiers and raw diagnostics
are discarded. Inherited API keys, access tokens, custom provider endpoints,
CODEX_HOME, proxy variables and launch overrides are not passed to the child.

The opt-in synthetic command is:

```sh
.venv/bin/python -m spikes.cli.runner live --executable /Users/fostral/.codex/plugins/.plugin-appserver/codex-cli/bin/codex
```

It currently exits 1 with `CLI_PROFILE_UNSAFE`, before generation. The real
`0.162.0-alpha.2` profile is deliberately closed. Do not change its readiness
flag just to run the canary. First establish all gaps in
[the findings](../../docs/gui/cli-spike.md), review the evidence, then test an
eligible profile. The distinct `-fixture` version is only an offline protocol.
No real CLI version is approved for generation by this spike.

The intended live action selects only catalog-advertised `gpt-6-luna`, prepares
fictional text with a random canary, and permits one generation start with a
60-second acceptance deadline. There is no retry, repair loop or model fallback.
The initial experiment allowance remains three total generation starts, including
manual retries. None were used. Internal inference counts and hard token caps
are not known. A future live profile also needs a canary audit; this command
alone is not a retention test.

`Runner.generate` uses argv, stdin, an operation-local schema, bounded JSONL and
strict final validation. It returns content in memory; `Result.metadata()` and
`Runner.last_metadata` exclude content. It accepts at most 8 KiB input, 256 KiB
combined process output, 64 KiB per event, and a 400-character summary. Limits
apply to this fixed spike schema, not arbitrary JSON Schema.

Each operation owns a random marked directory under
`experiments/gui-cli-spike/operations`. Startup reaps only correctly marked,
unlocked directories without surviving workers. It preserves symlinks, unrelated
files, active operations and quarantined cleanup failures. Crash survivors are
preserved until their group exits; startup does not kill arbitrary old PIDs.
Corrupt or unreadable `.worker` records are quarantined with `.cleanup-blocked`;
startup cannot treat them as proof that the worker exited.
The runner writes an unverified spawning marker before launching a child. If it
crashes before recording the PID, the next startup quarantines that directory.
Malformed ownership markers are left untouched while cleanup continues for
independent directories.

```sh
.venv/bin/python -m spikes.cli.runner cleanup
```

Normal cleanup follows TERM, then KILL of the operation's process group. A macOS
fallback inspects only numeric PID/group pairs and signals members of that group.
It reinspects the group after signaling and quarantines the operation if a live
member remains or process inspection fails.
The acceptance deadline includes probes; process/file cleanup can add bounded
process grace time. Escaped process groups, PID reuse races, filesystem stalls,
Windows and Linux are not certified by these macOS tests. If tree cleanup cannot
be established, the operation fails and its marked directory is quarantined;
inspect those synthetic artifacts manually before removing them.

The adapter was independently written using the small T3 pattern cited in
`docs/gui/cli-integration.md`. No upstream implementation was copied or ported
verbatim. No extra service, provider API, GUI or document renderer is included.
