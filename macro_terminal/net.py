"""HTTP with timeout and retries. The only place that touches the network (besides yfinance)."""
from __future__ import annotations

import time
from pathlib import Path

import requests

from . import config


class FetchError(RuntimeError):
    pass


def get(url: str, *, params: dict | None = None, timeout: float = config.HTTP_TIMEOUT_S,
        tries: int = config.HTTP_TRIES) -> requests.Response:
    last = None
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers={"User-Agent": config.USER_AGENT})
            if r.status_code == 404:
                raise FetchError(f"404 not found: {url}")
            r.raise_for_status()
            return r
        except FetchError:
            raise
        except Exception as e:  # noqa: BLE001  network errors, 5xx, timeouts
            last = e
            time.sleep(2 * (attempt + 1))
    raise FetchError(f"{url}: {last}")


def get_json(url: str, **kw):
    return get(url, **kw).json()


def download(url: str, dest: Path, max_age_days: float | None = None) -> Path:
    """Download to dest unless a fresh enough copy exists. Writes atomically."""
    if dest.exists() and max_age_days is not None:
        age_days = (time.time() - dest.stat().st_mtime) / 86400
        if age_days <= max_age_days:
            return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = get(url, timeout=300)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    return dest
