"""Local AI through Ollama: discovery, model choice, service start and streaming chat.

Nothing leaves the computer: every request goes to the local Ollama server.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable, Iterator

import requests

from .. import logs, paths

log = logs.get("ai")

RECOMMENDED_MODEL = "qwen3.5:9b"
RECOMMENDED_MODEL_SIZE = "6.6 GB"
DOWNLOAD_PAGE = "https://ollama.com/download"
# Preferred chat models, best first. A prefix ending in ":" matches only the
# official tags of that family (qwen3.5:9b), so custom variants such as
# qwen3.5-apps with their own system prompts are only used as a last resort.
PREFERRED_PREFIXES = ("qwen3.5:", "qwen3:", "qwen2.5:", "gemma3:", "llama3.1:", "llama3.2:", "mistral:",
                      "qwen3.5", "qwen3", "qwen2.5")
_NOT_CHAT = re.compile(r"embed|bge|nomic|minilm|rerank|whisper|clip|vision-only", re.I)

_started_process: subprocess.Popen | None = None
_started_service = False
_start_lock = threading.Lock()


def base_url() -> str:
    """Honour OLLAMA_HOST like the ollama CLI does."""
    host = os.environ.get("OLLAMA_HOST", "").strip() or "127.0.0.1:11434"
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    if host.startswith("http://0.0.0.0"):
        host = host.replace("0.0.0.0", "127.0.0.1", 1)
    return host.rstrip("/")


def clean_environment() -> dict[str, str]:
    """Environment for child processes without the bundle's library overrides.

    The packaged app sets LD_LIBRARY_PATH and Qt paths for itself; passing them
    to systemctl or ollama would make those programs load the wrong libraries.
    """
    environment = os.environ.copy()
    if getattr(sys, "frozen", False) or "_PYI_ARCHIVE_FILE" in environment or "APPDIR" in environment:
        original = environment.pop("LD_LIBRARY_PATH_ORIG", None)
        if original:
            environment["LD_LIBRARY_PATH"] = original
        else:
            environment.pop("LD_LIBRARY_PATH", None)
        for key in list(environment):
            if key.startswith("_PYI") or key in {"APPDIR", "APPIMAGE", "OPENSSL_MODULES", "QT_PLUGIN_PATH",
                                                 "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "SSL_CERT_FILE"}:
                environment.pop(key, None)
    # AMD's GPU compiler writes temporary files while loading models; keep them
    # on disk instead of the RAM-backed /tmp. An explicit TMPDIR is respected.
    if not IS_WINDOWS and not environment.get("TMPDIR"):
        temporary = paths.ensure(paths.cache_dir() / "ollama-tmp")
        environment["TMPDIR"] = str(temporary)
    return environment


def is_chat_model(name: str) -> bool:
    return bool(name) and not _NOT_CHAT.search(name)


def choose_model(installed: list[str], requested: str = "auto") -> str | None:
    """The model to use: the requested one if installed, else the best available chat model."""
    if requested and requested != "auto":
        return requested if requested in installed else None
    # Specialised variants (coding, app-building prompts) sort after general ones.
    candidates = sorted((name for name in installed if is_chat_model(name)),
                        key=lambda name: (bool(re.search(r"coder|-apps|code", name)), name))
    for prefix in PREFERRED_PREFIXES:
        for name in candidates:
            if name.startswith(prefix):
                return name
    return candidates[0] if candidates else None


@dataclass
class Status:
    """What the app can tell the reader about local AI, in one place."""
    state: str = "checking"  # ready, stopped, no-model, missing, error
    models: list[str] = field(default_factory=list)
    model: str | None = None
    running: list[dict] = field(default_factory=list)
    detail: str = ""
    can_start: bool = False


IS_WINDOWS = sys.platform.startswith("win")


def installed_binary() -> str | None:
    candidates = [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama"), Path.home() / ".local/bin/ollama"]
    if IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        candidates = [Path(local, "Programs", "Ollama", "ollama.exe"),
                      Path(os.environ.get("ProgramFiles", "C:/Program Files"), "Ollama", "ollama.exe")]
    return shutil.which("ollama") or next((str(path) for path in candidates if path.is_file()), None)


def user_service_exists() -> bool:
    if IS_WINDOWS or not shutil.which("systemctl"):
        return False
    try:
        result = subprocess.run(["systemctl", "--user", "list-unit-files", "ollama.service", "--no-legend"],
                                capture_output=True, text=True, timeout=5, env=clean_environment())
    except (OSError, subprocess.SubprocessError):
        return False
    return "ollama.service" in result.stdout


def list_models(http: requests.Session | None = None, timeout=(1.0, 3.0)) -> list[str]:
    http = http or requests.Session()
    response = http.get(f"{base_url()}/api/tags", timeout=timeout)
    response.raise_for_status()
    return [item["name"] for item in response.json().get("models", []) if item.get("name")]


def status(requested: str = "auto") -> Status:
    """Probe Ollama without starting anything."""
    with requests.Session() as http:
        try:
            models = list_models(http, timeout=(0.8, 2.0))
        except requests.RequestException:
            binary = installed_binary()
            if not binary:
                return Status("missing", detail="Ollama is not installed.")
            return Status("stopped", detail="Ollama is installed but not running.", can_start=True)
        except (ValueError, KeyError, TypeError) as exc:
            return Status("error", detail=f"Unexpected Ollama response: {exc}")
        try:
            running = http.get(f"{base_url()}/api/ps", timeout=(0.8, 2.0)).json().get("models", [])
        except (requests.RequestException, ValueError, AttributeError):
            running = []
    model = choose_model(models, requested)
    if model:
        return Status("ready", models, model, running)
    if requested != "auto" and models:
        return Status("no-model", models, None, running, f"Selected model is not installed: {requested}")
    return Status("no-model", models, None, running, "No chat model is installed.")


def wait_until_ready(seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + seconds
    with requests.Session() as http:
        while time.monotonic() < deadline:
            try:
                list_models(http, timeout=(0.5, 1.5))
                return True
            except (requests.RequestException, ValueError):
                time.sleep(0.25)
    return False


def start_service() -> str:
    """Start Ollama and wait for it. Prefers the user's own systemd service.

    Returns how it was started ("running", "systemd" or "process"); raises
    RuntimeError when Ollama cannot be started.
    """
    global _started_process, _started_service
    with _start_lock:
        if wait_until_ready(0.3):
            return "running"
        environment = clean_environment()
        if user_service_exists():
            result = subprocess.run(["systemctl", "--user", "start", "ollama.service"],
                                    capture_output=True, text=True, timeout=20, env=environment)
            if result.returncode == 0 and wait_until_ready(20):
                _started_service = True
                log.info("Started the user's ollama.service")
                return "systemd"
            log.warning("systemctl --user start ollama failed: %s", result.stderr.strip())
        binary = installed_binary()
        if not binary:
            raise RuntimeError("Ollama is not installed.")
        log_path = paths.ensure(paths.cache_dir()) / "ollama-server.log"
        if log_path.exists() and log_path.stat().st_size > 2 * 1024 * 1024:
            log_path.replace(log_path.with_suffix(".previous.log"))
        detach = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                  if IS_WINDOWS else {"start_new_session": True})
        with log_path.open("ab") as output:
            _started_process = subprocess.Popen([binary, "serve"], env=environment, stdin=subprocess.DEVNULL,
                                                stdout=output, stderr=output, **detach)
        if wait_until_ready(15):
            log.info("Started ollama serve (pid %s)", _started_process.pid)
            return "process"
        raise RuntimeError("Ollama could not be started. See ~/.cache/euro-info/ollama-server.log.")


def started_by_app() -> bool:
    return _started_service or (_started_process is not None and _started_process.poll() is None)


def stop_if_started() -> None:
    """Stop Ollama only when this app started it, leaving the user's own sessions alone."""
    global _started_process, _started_service
    if _started_service:
        try:
            subprocess.run(["systemctl", "--user", "stop", "ollama.service"], timeout=10,
                           capture_output=True, env=clean_environment())
            log.info("Stopped ollama.service started by Euro Info")
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("Could not stop ollama.service: %s", exc)
        _started_service = False
    if _started_process is not None and _started_process.poll() is None:
        _started_process.terminate()
        try:
            _started_process.wait(5)
        except subprocess.TimeoutExpired:
            _started_process.kill()
        log.info("Stopped ollama serve started by Euro Info")
    _started_process = None


def warm_up(model: str, keep_alive: str = "10m") -> None:
    """Load the model into memory ahead of a request, so the first words arrive sooner."""
    try:
        requests.post(f"{base_url()}/api/generate", json={"model": model, "keep_alive": keep_alive},
                      timeout=(1.5, 120)).close()
    except requests.RequestException as exc:
        log.debug("Warm-up skipped: %s", exc)


def ensure_running() -> list[str]:
    """Installed model names, starting Ollama first when needed."""
    try:
        return list_models()
    except requests.RequestException:
        start_service()
        return list_models()


def pull_model(name: str, progress: Callable[[str, float], None] | None = None,
               cancelled: Callable[[], bool] = lambda: False) -> None:
    """Download a model through Ollama, reporting (status, fraction 0..1)."""
    ensure_running()
    with requests.post(f"{base_url()}/api/pull", json={"model": name, "stream": True},
                       stream=True, timeout=(5, 600)) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if cancelled():
                raise RuntimeError("Download cancelled.")
            if not line:
                continue
            event = json.loads(line)
            if event.get("error"):
                raise RuntimeError(event["error"])
            total, done = event.get("total") or 0, event.get("completed") or 0
            if progress:
                progress(str(event.get("status", "")), done / total if total else -1.0)
            if event.get("status") == "success":
                return


def chat_stream(http: requests.Session, model: str, messages: list[dict], options: dict,
                keep_alive: str = "10m", response_format: dict | str | None = None,
                timeout=(5, 180)) -> Iterator[dict]:
    """Yield Ollama chat events. Thinking is off: it is too slow for reading sessions."""
    payload = {"model": model, "messages": messages, "stream": True, "think": False,
               "keep_alive": keep_alive, "options": options}
    if response_format is not None:
        payload["format"] = response_format
    response = http.post(f"{base_url()}/api/chat", json=payload, timeout=timeout, stream=True)
    try:
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", response.reason)
            except ValueError:
                detail = response.reason
            raise RuntimeError(f"Ollama HTTP {response.status_code}: {detail}")
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                event = json.loads(line)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("Ollama returned an invalid response stream.") from exc
            if event.get("error"):
                raise RuntimeError(f"Ollama: {event['error']}")
            yield event
    finally:
        response.close()


def chat(model: str, messages: list[dict], options: dict, keep_alive: str = "10m",
         response_format: dict | str | None = None, timeout=(5, 180)) -> str:
    with requests.Session() as http:
        parts = []
        for event in chat_stream(http, model, messages, options, keep_alive, response_format, timeout):
            parts.append(event.get("message", {}).get("content", ""))
            if event.get("done"):
                break
        return "".join(parts)
