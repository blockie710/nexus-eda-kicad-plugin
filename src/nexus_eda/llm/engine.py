# SPDX-License-Identifier: Apache-2.0
"""LLM engine wrapper around llama-cpp-python.

Reads model defaults from ``models/manifest.yaml`` so that quantization
(Q4_K_M), temperature (0.1), top_p (0.9), and max_tokens (4096) stay in
sync with the project's Phase 1 manifest.

If ``llama-cpp-python`` is not installed (e.g. KiCad's bundled Python lacks
the C++ bindings), the engine degrades gracefully: :func:`load_model` and
:func:`generate` are still importable, but raise :class:`LLMError` at call
time so callers can decide whether to fall back to stubs or the llama-cpp server
HTTP endpoint at ``http://localhost:8000``.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "LLMConfig",
    "LLMEngine",
    "LLMError",
    "generate",
    "load_model",
]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class LLMError(RuntimeError):
    """Raised when the LLM engine is unavailable or generation fails."""


# --------------------------------------------------------------------------- #
# Path / config helpers
# --------------------------------------------------------------------------- #
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # repo root
_MANIFEST_PATH = _PROJECT_ROOT / "models" / "manifest.yaml"


@dataclass
class LLMConfig:
    """Generation parameters, resolved from the manifest with overrides."""

    model_id: str
    model_path: str | None = None
    quant: str = "Q4_K_M"
    temperature: float = 0.1
    top_p: float = 0.9
    max_tokens: int = 4096
    context_k: int = 128
    api_url: str = "http://localhost:8000"
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_manifest(
        cls, manifest_path: str | os.PathLike | None = None
    ) -> LLMConfig:
        """Load runtime defaults and the primary model entry from manifest."""
        path = Path(manifest_path) if manifest_path else _MANIFEST_PATH
        if not path.exists():
            raise LLMError(f"Manifest not found: {path}")

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        runtime = data.get("runtime", {})
        models = data.get("models", {})

        primary_key = next(
            (k for k, v in models.items() if v.get("primary")), None
        )
        if primary_key is None:
            raise LLMError("No primary model marked in manifest")
        model_entry = models[primary_key]

        return cls(
            model_id=model_entry["model_id"],
            quant=model_entry.get("quant", runtime.get("quantization", "Q4_K_M")),
            temperature=runtime.get("temperature", 0.1),
            top_p=runtime.get("top_p", 0.9),
            max_tokens=runtime.get("max_tokens", 4096),
            context_k=model_entry.get("context_k", runtime.get("context_k", 128)),
            api_url=runtime.get("api", "http://localhost:8000"),
        )


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class LLMEngine:
    """Thin wrapper around ``llama_cpp.Llama`` with streaming support.

    Usage::

        engine = load_model()
        for chunk in engine.generate_stream("Hello"): ...
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._model: Any = None
        self._lock = threading.Lock()

    # -- model loading ------------------------------------------------------- #
    def load(self) -> LLMEngine:
        """Lazy-load the underlying llama.cpp model.

        Looks for the model on disk via the ``NEXUS_LLM_MODEL_PATH`` env var.
        If the binding is unavailable or the model file is missing, the
        engine is still constructed but :meth:`generate` / generate_stream
        will raise :class:`LLMError` at call time.
        """
        if self._model is not None:
            return self

        try:
            from llama_cpp import Llama  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise LLMError(
                "llama-cpp-python is not installed in this environment. "
                "Install with: pip install llama-cpp-python[server]"
            ) from exc

        model_path = os.environ.get("NEXUS_LLM_MODEL_PATH") or self.config.model_path
        if not model_path or not Path(model_path).exists():
            raise LLMError(
                f"Model file not found for {self.config.model_id} "
                "(Q4_K_M). Set NEXUS_LLM_MODEL_PATH or config.model_path."
            )

        self._model = Llama(
            model_path=model_path,
            n_ctx=self.config.context_k * 1024,
            n_gpu_layers=-1,  # offload all layers to GPU when available
            verbose=False,
        )
        return self

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    # -- generation ---------------------------------------------------------- #
    def generate(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stream_callback: Any | None = None,
    ) -> str:
        """Generate text. If *stream_callback* is given, each token chunk is
        passed to it as it arrives (streaming). Returns the full completion."""
        if self._model is None:
            raise LLMError("Model not loaded. Call engine.load() first.")

        kwargs: dict[str, Any] = {
            "temperature": temperature if temperature is not None else self.config.temperature,
            "top_p": top_p if top_p is not None else self.config.top_p,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "stream": stream_callback is not None,
        }

        with self._lock:
            output: str = ""
            try:
                for chunk in self._model(prompt, **kwargs):
                    delta = chunk["choices"][0].get("delta", {}).get("content", "") or ""
                    if delta:
                        output += delta
                        if stream_callback is not None:
                            stream_callback(delta)
            except Exception as exc:
                raise LLMError(f"Generation failed: {exc}") from exc

        return output

    def generate_stream(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        callback: Any | None = None,
    ) -> str:
        """Explicit streaming alias for :meth:`generate`."""
        return self.generate(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream_callback=callback,
        )


# --------------------------------------------------------------------------- #
# Convenience functions (module-level)
# --------------------------------------------------------------------------- #
_engine: LLMEngine | None = None
_engine_lock = threading.Lock()


def load_model(
    model_path: str | None = None,
    config: LLMConfig | None = None,
) -> LLMEngine:
    """Load (or return a cached) :class:`LLMEngine`.

    Parameters
    ----------
    model_path:
        Override path to the ``.gguf`` / ``.bin`` quantized model file.
        If omitted, reads ``NEXUS_LLM_MODEL_PATH`` or the manifest primary entry.
    config:
        Pre-built :class:`LLMConfig`. If omitted, resolved from the manifest.
    """
    global _engine
    if config is None:
        config = LLMConfig.from_manifest()
    if model_path:
        config.model_path = model_path

    engine = LLMEngine(config=config)
    engine.load()

    with _engine_lock:
        _engine = engine
    return engine


def generate(
    prompt: str,
    *,
    engine: LLMEngine | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
    stream_callback: Any | None = None,
) -> str:
    """Generate text using a cached or provided engine.

    If no *engine* is supplied and none has been loaded yet, one is lazily
    created from the manifest. Raises :class:`LLMError` if the binding or
    model file is unavailable.
    """
    if engine is None:
        global _engine
        with _engine_lock:
            if _engine is None:
                _engine = LLMEngine(LLMConfig.from_manifest())
            engine = _engine

    if not engine.is_loaded:
        engine.load()

    return engine.generate(
        prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stream_callback=stream_callback,
    )
