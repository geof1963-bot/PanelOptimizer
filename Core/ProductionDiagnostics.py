# -*- coding: utf-8 -*-
"""Crash-resilient production diagnostics for risky OCC and Mesh operations."""

from __future__ import annotations

import os
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DIRECTORY = _ROOT / "RealTests" / "Diagnostics"
_LOG_PATH: Path | None = None
_RUN_STARTED = 0.0
_CURRENT_STAGE = "idle"
_CURRENT_ITEM = "none"


def start_run(label: str = "Split Panel") -> Path:
    """Start a durable diagnostic log and return its path."""
    global _LOG_PATH, _RUN_STARTED
    directory = Path(os.environ.get(
        "PANELOPTIMIZER_DIAGNOSTICS",
        str(_DEFAULT_DIRECTORY),
    ))
    directory.mkdir(parents=True, exist_ok=True)
    _LOG_PATH = directory / "split_panel_v600.log"
    _RUN_STARTED = time.perf_counter()
    _write(f"START {label}")
    return _LOG_PATH


def finish_run(status: str) -> None:
    """Flush a terminal run marker."""
    _write(f"FINISH status={status}")


def diagnostics_directory() -> Path:
    """Return the active artifact directory."""
    return _LOG_PATH.parent if _LOG_PATH is not None else _DEFAULT_DIRECTORY


def save_shape_artifact(name: str, shape: object) -> Path | None:
    """Persist one B-rep diagnostic without mutating its source."""
    path = diagnostics_directory() / f"{name}.brep"
    try:
        shape.exportBrep(str(path))
        _write(f"ARTIFACT name={name} path={path}")
        return path
    except Exception as error:
        _write(
            f"ARTIFACT_FAIL name={name} "
            f"type={type(error).__name__} message={error}"
        )
        return None


def save_mesh_artifact(name: str, mesh: object) -> Path | None:
    """Persist one transient mesh as an STL diagnostic."""
    path = diagnostics_directory() / f"{name}.stl"
    try:
        mesh.write(str(path))
        _write(f"ARTIFACT name={name} path={path}")
        return path
    except Exception as error:
        _write(
            f"ARTIFACT_FAIL name={name} "
            f"type={type(error).__name__} message={error}"
        )
        return None


def current_context() -> tuple[str, str]:
    """Return the last durable stage and item markers."""
    return _CURRENT_STAGE, _CURRENT_ITEM


def shape_facts(shape: object) -> str:
    """Return bounded topology facts without raising."""
    try:
        return (
            f"faces={len(shape.Faces)} edges={len(shape.Edges)} "
            f"solids={len(shape.Solids)}"
        )
    except Exception as error:
        return f"shape_facts_unavailable={type(error).__name__}:{error}"


def log_event(stage: str, item: str, message: str) -> None:
    """Write and flush one diagnostic event."""
    global _CURRENT_STAGE, _CURRENT_ITEM
    _CURRENT_STAGE, _CURRENT_ITEM = str(stage), str(item)
    _write(f"stage={stage} item={item} {message}")


def log_exception(error: BaseException) -> None:
    """Persist the complete Python traceback with current context."""
    _write(
        f"EXCEPTION stage={_CURRENT_STAGE} item={_CURRENT_ITEM} "
        f"type={type(error).__name__} message={error}\n"
        + "".join(traceback.format_exception(
            type(error), error, error.__traceback__
        )).rstrip()
    )


@contextmanager
def operation(stage: str, item: str, name: str, shape: object | None = None):
    """Log a risky operation before and after execution."""
    started = time.perf_counter()
    facts = shape_facts(shape) if shape is not None else "shape=none"
    log_event(stage, item, f"BEGIN operation={name} {facts}")
    try:
        yield
    except BaseException as error:
        duration = time.perf_counter() - started
        log_event(
            stage, item,
            f"FAIL operation={name} duration={duration:.6f}s",
        )
        log_exception(error)
        raise
    duration = time.perf_counter() - started
    log_event(
        stage, item,
        f"OK operation={name} duration={duration:.6f}s",
    )


def _memory_mb() -> float | None:
    """Return memory only when a proven cheap provider is available."""
    return None


def _write(message: str) -> None:
    if _LOG_PATH is None:
        return
    elapsed = time.perf_counter() - _RUN_STARTED
    memory = _memory_mb()
    prefix = f"{elapsed:012.6f}s memory_mb="
    prefix += f"{memory:.3f}" if memory is not None else "unavailable"
    with _LOG_PATH.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(prefix + " " + message.rstrip() + "\n")
        stream.flush()
