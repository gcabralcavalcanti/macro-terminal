"""Thin, defensive wrapper around the Claude API.

- JSON answers constrained by a JSON Schema (structured outputs) and validated again locally,
  including constraints the API does not enforce (item counts, string lengths).
- Every accepted answer is recorded under recordings/. The same request is never paid twice,
  and without an API key the recordings replay (demo mode).
- Call cap per run, timeout, SDK retries (network/429/5xx), one retry when our own checks fail,
  one JSON log line per call with tokens and cost.
- The key comes from ANTHROPIC_API_KEY (environment or .env). It is never printed or logged.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import jsonschema

from . import config


class BudgetExceeded(RuntimeError):
    pass


class NoRecording(RuntimeError):
    pass


def load_key(root: Path = config.ROOT) -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    env_file = root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ANTHROPIC_API_KEY" and value.strip():
                return value.strip().strip('"')
    if os.name == "nt":  # variable set in Windows after this terminal was opened
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                return winreg.QueryValueEx(k, "ANTHROPIC_API_KEY")[0] or None
        except OSError:
            return None
    return None


def request_key(request: dict) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


class LLM:
    """mode: 'auto' (live if a key exists, else demo), 'live' or 'demo'."""

    def __init__(self, mode: str = "auto", client=None, recordings: Path = config.RECORDINGS,
                 log_dir: Path = config.LOGS, max_calls: int = config.MAX_CALLS_PER_RUN):
        key = None if mode == "demo" else load_key()
        if mode == "live" and not key and client is None:
            raise RuntimeError("Live mode needs ANTHROPIC_API_KEY (environment or .env).")
        self.mode = "live" if (key or client is not None) and mode != "demo" else "demo"
        self.recordings = recordings
        self.log_path = log_dir / f"run-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        self.max_calls = max_calls
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self._client = client
        if self._client is None and self.mode == "live":
            import anthropic
            self._client = anthropic.Anthropic(api_key=key, timeout=config.TIMEOUT_S, max_retries=config.SDK_RETRIES)

    # ------------------------------------------------------------------ public
    def ask(self, task: str, system: str, prompt: str, api_schema: dict, strict_schema: dict,
            check: Callable[[dict], list[str]] | None = None) -> tuple[dict, dict]:
        """Return (answer, meta). The answer matches strict_schema and passes check."""
        request = {"model": config.MODEL, "system": system, "prompt": prompt, "schema": api_schema,
                   "max_tokens": config.MAX_TOKENS}
        key = request_key(request)
        path = self.recordings / f"{task}-{key}.json"
        if path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
            self._log(task, key, "recording", 0, 0, [])
            return rec["answer"], {"mode": "recorded", "request": key, "recorded_at": rec["recorded_at"],
                                   "input_tokens": rec.get("input_tokens"), "output_tokens": rec.get("output_tokens")}
        if self.mode == "demo":
            raise NoRecording(f"No recorded answer for {task} ({key}).")

        problems: list[str] = []
        user = prompt
        for attempt in range(config.SCHEMA_RETRIES + 1):
            answer, usage = self._call(system, user, api_schema)
            problems = self.problems(answer, strict_schema, check)
            self._log(task, key, "api", usage[0], usage[1], problems, attempt)
            if not problems:
                self.recordings.mkdir(parents=True, exist_ok=True)
                rec = {"task": task, "model": config.MODEL, "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "input_tokens": self.tokens_in, "output_tokens": self.tokens_out,
                       "request": {"system": system, "prompt": prompt}, "answer": answer}
                path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
                return answer, {"mode": "live", "request": key, "recorded_at": rec["recorded_at"],
                                "input_tokens": self.tokens_in, "output_tokens": self.tokens_out, "attempts": attempt + 1}
            user = (prompt + "\n\nYour previous answer was rejected by the checker:\n- " + "\n- ".join(problems)
                    + "\nAnswer again, fixing these points.")
        raise ValueError(f"{task}: answer failed checks after retries: {problems}")

    def cost_usd(self, tin: int | None = None, tout: int | None = None) -> float:
        p_in, p_out = config.PRICE_PER_MTOK.get(config.MODEL, (0.0, 0.0))
        tin = self.tokens_in if tin is None else tin
        tout = self.tokens_out if tout is None else tout
        return ((tin or 0) * p_in + (tout or 0) * p_out) / 1e6

    @staticmethod
    def problems(answer: dict, schema: dict, check) -> list[str]:
        if "_error" in answer:
            return [answer["_error"]]
        try:
            jsonschema.validate(answer, schema)
        except jsonschema.ValidationError as e:
            return [f"schema: {e.message}"]
        return check(answer) if check else []

    # ----------------------------------------------------------------- private
    def _call(self, system: str, user: str, schema: dict):
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"Call cap reached ({self.max_calls} per run).")
        self.calls += 1
        response = self._client.messages.create(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
        self.tokens_in += response.usage.input_tokens
        self.tokens_out += response.usage.output_tokens
        usage = (response.usage.input_tokens, response.usage.output_tokens)
        if response.stop_reason == "refusal":
            return {"_error": "refusal"}, usage
        if response.stop_reason == "max_tokens":
            return {"_error": "answer cut at max_tokens"}, usage
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text), usage
        except json.JSONDecodeError:
            return {"_error": "invalid JSON"}, usage

    def _log(self, task, key, source, tin, tout, problems, attempt=0):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "task": task, "request": key,
                "source": source, "attempt": attempt, "model": config.MODEL, "input_tokens": tin,
                "output_tokens": tout, "cost_usd": round(self.cost_usd(tin, tout), 6), "problems": problems}
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
