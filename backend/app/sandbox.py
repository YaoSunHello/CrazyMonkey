"""Where agent-written code runs.

Two executors behind one interface:

- `DaytonaExecutor` — a disposable cloud sandbox, destroyed after the run.
  This is the one to use. The agent's code never touches this machine, and the
  verifier stays on the host where the agent cannot reach it.
- `LocalExecutor` — a subprocess in a temporary directory. It exists so the
  loop can be developed and demonstrated without a Daytona key, and it must be
  turned on deliberately: running model-written code on your own machine is a
  real risk, not a detail.

The Daytona specifics below are not guesses; they are the shape that already
works in dimknaf/agent-arena, including the reasons for each one.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.trace import Trace

# `python:latest` is rejected by snapshot creation — image refs need a real tag.
SANDBOX_IMAGE = "python:3.11-bookworm"
WORKDIR = "/work"
DATADIR = "/data"


@dataclass
class RunOutput:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class Executor(Protocol):
    """What the agent's tools need, and nothing more."""

    async def start(self) -> None: ...
    async def put(self, path: str, content: bytes) -> None: ...
    async def get(self, path: str) -> bytes: ...
    async def run_python(self, path: str, timeout: int = 300) -> RunOutput: ...
    async def remove(self, path: str) -> None: ...
    async def close(self) -> None: ...


class LocalExecutor:
    """Runs agent code in a subprocess, in a temporary directory.

    DEVELOPMENT ONLY. There is no isolation here: the code can read your files
    and reach the network. Enabled only via `allow_local_execution=True`, so it
    can never be reached by accident.
    """

    def __init__(self, trace: Trace, data_dir: Path, *, allow_local_execution: bool = False):
        if not allow_local_execution:
            raise RuntimeError(
                "LocalExecutor runs model-written code on this machine with no isolation. "
                "Pass allow_local_execution=True to accept that, or set DAYTONA_API_KEY "
                "to use a disposable sandbox instead."
            )
        self.trace = trace
        self.data_dir = data_dir
        self._root: Path | None = None

    async def start(self) -> None:
        self._root = Path(tempfile.mkdtemp(prefix="footing-work-"))
        self.trace.tool(
            "sandbox",
            f"local subprocess · {self._root}",
            status="ok",
            kind="local",
        )
        kit = (Path(__file__).parent / "kit" / "statement_kit.py").read_bytes()
        (self._root / "kit.py").write_bytes(kit)
        self.trace.out(
            "No isolation: agent code runs as you, on this machine.", stream="stderr"
        )

    def _resolve(self, path: str) -> Path:
        """Map a sandbox path onto the temp workspace, refusing to escape it."""
        assert self._root is not None
        if path.startswith(DATADIR):
            return self.data_dir / path[len(DATADIR) :].lstrip("/")
        relative = path[len(WORKDIR) :].lstrip("/") if path.startswith(WORKDIR) else path
        target = (self._root / relative).resolve()
        if not str(target).startswith(str(self._root.resolve())):
            raise ValueError(f"path escapes the workspace: {path}")
        return target

    async def put(self, path: str, content: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    async def get(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    async def run_python(self, path: str, timeout: int = 300) -> RunOutput:
        target = self._resolve(path)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(target),
            cwd=str(self._root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "FOOTING_DATA": str(self.data_dir), "PYTHONIOENCODING": "utf-8"},
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            return RunOutput(-1, "", f"timed out after {timeout}s")
        return RunOutput(
            process.returncode or 0,
            stdout.decode("utf-8", "replace"),
            stderr.decode("utf-8", "replace"),
        )

    async def remove(self, path: str) -> None:
        target = self._resolve(path)
        if target.exists():
            target.unlink()

    async def close(self) -> None:
        self.trace.tool("sandbox", "workspace kept for inspection", status="ok")


class DaytonaExecutor:
    """A disposable Daytona sandbox.

    Every non-obvious call here is deliberate:

    - `process.exec` defaults to a 10-second timeout, which silently kills a
      real run. Everything goes through `create_session` +
      `execute_session_command(run_async=True)` + `get_session_command_logs_async`.
    - `auto_stop_interval=0`, or the sandbox stops after 15 minutes idle.
    - Both stdout and stderr callbacks are wired; progress arrives on stderr.
    - Callbacks only append. Blocking inside one disconnects the stream.
    - `< /dev/null` on the command: a process that reads piped stdin otherwise
      waits forever, with nothing on screen to say so.
    """

    def __init__(self, trace: Trace, data_dir: Path, *, api_key: str, target: str = "eu"):
        self.trace = trace
        self.data_dir = data_dir
        self.api_key = api_key
        self.target = target
        self._daytona = None
        self._sandbox = None
        self._session = "footing"

    async def start(self) -> None:
        from daytona import (
            AsyncDaytona,
            CreateSandboxFromImageParams,
            DaytonaConfig,
        )

        self.trace.tool("sandbox", f"creating · {SANDBOX_IMAGE}", status="running")
        self._daytona = AsyncDaytona(DaytonaConfig(api_key=self.api_key, target=self.target))
        self._sandbox = await self._daytona.create(
            CreateSandboxFromImageParams(
                image=SANDBOX_IMAGE,
                auto_stop_interval=0,
                ttl_minutes=30,
            ),
            timeout=300,
        )
        await self._sandbox.process.create_session(self._session)
        await self._exec(f"mkdir -p {WORKDIR} {DATADIR}")

        uploaded = 0
        for path in sorted(self.data_dir.rglob("*")):
            if path.is_file():
                relative = path.relative_to(self.data_dir).as_posix()
                await self._sandbox.fs.upload_file(path.read_bytes(), f"{DATADIR}/{relative}")
                uploaded += 1

        kit = (Path(__file__).parent / "kit" / "statement_kit.py").read_bytes()
        await self._sandbox.fs.upload_file(kit, f"{WORKDIR}/kit.py")
        self.trace.tool("sandbox", "installing pdfplumber", status="running")
        await self._exec("pip install --quiet pdfplumber", timeout=300)
        self.trace.tool(
            "sandbox",
            f"ready · {self._sandbox.id} · {uploaded} data files · kit + pdfplumber",
            status="ok",
            kind="daytona",
            sandbox_id=self._sandbox.id,
        )

    async def _exec(self, command: str, timeout: int = 300) -> RunOutput:
        from daytona import SessionExecuteRequest

        response = await self._sandbox.process.execute_session_command(
            self._session,
            SessionExecuteRequest(command=f"{command} < /dev/null", run_async=True),
        )
        command_id = getattr(response, "cmd_id", None) or getattr(response, "id", None)
        if command_id is None:
            return RunOutput(-1, "", "no command id returned by Daytona")

        out: list[str] = []
        err: list[str] = []

        def on_stdout(chunk: str) -> None:   # must not block
            out.append(chunk)
            self.trace.out(chunk, stream="stdout")

        def on_stderr(chunk: str) -> None:   # must not block
            err.append(chunk)
            self.trace.out(chunk, stream="stderr")

        try:
            await asyncio.wait_for(
                self._sandbox.process.get_session_command_logs_async(
                    self._session, command_id, on_stdout, on_stderr
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return RunOutput(-1, "".join(out), f"timed out after {timeout}s")

        info = await self._sandbox.process.get_session_command(self._session, command_id)
        return RunOutput(getattr(info, "exit_code", None) or 0, "".join(out), "".join(err))

    async def put(self, path: str, content: bytes) -> None:
        await self._sandbox.fs.upload_file(content, path)

    async def get(self, path: str) -> bytes:
        return await self._sandbox.fs.download_file(path)

    async def run_python(self, path: str, timeout: int = 300) -> RunOutput:
        return await self._exec(f"cd {WORKDIR} && python3 {path} 2>&1", timeout=timeout)

    async def remove(self, path: str) -> None:
        """Clear an attempt's output before the next one.

        Without this, an attempt that writes nothing leaves the previous
        attempt's file in place, the verifier passes it a second time, and the
        failure never surfaces.
        """
        await self._exec(f"rm -f {path}", timeout=30)

    async def close(self) -> None:
        if self._sandbox is not None:
            try:
                await self._daytona.delete(self._sandbox)
                self.trace.tool("sandbox", "destroyed", status="ok")
            except Exception as exc:  # noqa: BLE001 — teardown must never mask a result
                self.trace.tool("sandbox", f"could not delete: {exc}", status="fail")
        if self._daytona is not None:
            await self._daytona.close()


def build_executor(trace: Trace, data_dir: Path, *, allow_local: bool = False) -> Executor:
    """Prefer a real sandbox; fall back to local only when explicitly allowed."""
    key = os.environ.get("DAYTONA_API_KEY", "").strip()
    if key:
        return DaytonaExecutor(
            trace, data_dir, api_key=key, target=os.environ.get("DAYTONA_TARGET", "eu")
        )
    return LocalExecutor(trace, data_dir, allow_local_execution=allow_local)
