"""
Bootstrap runner for PyCharm remote debugging inside Docker containers.

Mode:
- DEBUGPY_WAIT_FOR_CLIENT=1: block startup until IDE debug server is reachable.
- DEBUGPY_WAIT_FOR_CLIENT=0: start app immediately and retry background attach.
"""

from __future__ import annotations

import argparse
import os
import runpy
import socket
import sys
import threading
import time
from typing import Optional


def _to_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _can_connect(host: str, port: int, timeout_s: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _resolve_path_mappings() -> list[tuple[str, str]]:
    project_root = os.getenv("PYCHARM_PROJECT_ROOT", "").strip()
    source_subdir = os.getenv("PYCHARM_SOURCE_SUBDIR", "").strip()

    local_root = os.getenv("PYCHARM_LOCAL_ROOT", "").strip()
    if not local_root and project_root and source_subdir:
        local_root = os.path.join(project_root, source_subdir)

    remote_root = os.getenv("PYCHARM_REMOTE_ROOT", "").strip()

    local_shared_root = os.getenv("PYCHARM_LOCAL_SHARED_ROOT", "").strip()
    if not local_shared_root and project_root:
        local_shared_root = os.path.join(project_root, "src_shared")

    remote_shared_root = os.getenv("PYCHARM_REMOTE_SHARED_ROOT", "").strip()

    mappings: list[tuple[str, str]] = []
    if local_root and remote_root:
        mappings.append((os.path.normpath(local_root), os.path.normpath(remote_root)))
    if local_shared_root and remote_shared_root:
        mappings.append(
            (
                os.path.normpath(local_shared_root),
                os.path.normpath(remote_shared_root),
            )
        )
    return mappings


def _apply_path_mappings() -> None:
    mappings = _resolve_path_mappings()
    if not mappings:
        return

    try:
        from pydevd_file_utils import setup_client_server_paths  # type: ignore

        setup_client_server_paths(mappings)
        print(
            f"[pycharm-debug] path mappings active: {mappings}",
            file=sys.stderr,
            flush=True,
        )
    except Exception as exc:
        print(
            f"[pycharm-debug] path mappings setup failed: {exc}",
            file=sys.stderr,
            flush=True,
        )


def _wait_server(host: str, port: int, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _can_connect(host, port):
            return True
        time.sleep(0.25)
    return False


def _attach(host: str, port: int, suspend: bool, redirect_output: bool) -> None:
    import pydevd_pycharm

    _apply_path_mappings()
    pydevd_pycharm.settrace(
        host,
        port=port,
        stdout_to_server=redirect_output,
        stderr_to_server=redirect_output,
        suspend=suspend,
        patch_multiprocessing=True,
    )
    print(
        f"[pycharm-debug] attached to {host}:{port} (suspend={suspend})",
        file=sys.stderr,
        flush=True,
    )


def _background_attach(
    *,
    host: str,
    port: int,
    retry_seconds: float,
    redirect_output: bool,
) -> None:
    while True:
        try:
            if _can_connect(host, port):
                _attach(
                    host=host,
                    port=port,
                    suspend=False,
                    redirect_output=redirect_output,
                )
                return
        except Exception as exc:
            print(
                f"[pycharm-debug] retry attach failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
        time.sleep(retry_seconds)


def _run_target(module: Optional[str], script: Optional[str]) -> None:
    if module:
        runpy.run_module(module, run_name="__main__")
        return
    if script:
        runpy.run_path(script, run_name="__main__")
        return
    raise RuntimeError("Either --module or --script must be provided")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", default=None)
    parser.add_argument("--script", default=None)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    host = os.getenv("PYCHARM_DEBUG_HOST", "host.docker.internal")
    wait_for_client = _to_bool(os.getenv("DEBUGPY_WAIT_FOR_CLIENT"), default=False)
    attach_timeout_s = float(os.getenv("PYCHARM_ATTACH_TIMEOUT_SECONDS", "180"))
    retry_seconds = float(os.getenv("PYCHARM_RETRY_SECONDS", "2"))
    redirect_output = _to_bool(os.getenv("PYCHARM_REDIRECT_OUTPUT"), default=True)

    if wait_for_client:
        print(
            f"[pycharm-debug] waiting for IDE debug server at {host}:{args.port}",
            file=sys.stderr,
            flush=True,
        )
        if not _wait_server(host, args.port, attach_timeout_s):
            print(
                f"[pycharm-debug] timeout waiting for {host}:{args.port}",
                file=sys.stderr,
                flush=True,
            )
            return 2
        try:
            _attach(
                host=host,
                port=args.port,
                suspend=True,
                redirect_output=redirect_output,
            )
        except Exception as exc:
            print(
                f"[pycharm-debug] attach failed in wait mode: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return 3
    else:
        thread = threading.Thread(
            target=_background_attach,
            kwargs={
                "host": host,
                "port": args.port,
                "retry_seconds": retry_seconds,
                "redirect_output": redirect_output,
            },
            daemon=True,
        )
        thread.start()
        print(
            f"[pycharm-debug] app started; background attach loop for {host}:{args.port}",
            file=sys.stderr,
            flush=True,
        )

    _run_target(args.module, args.script)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
