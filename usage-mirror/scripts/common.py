"""Shared helpers for usage-mirror: config, time zone, rates, small utilities.

Everything a person sets lives in a config file OUTSIDE the skill folder, so a skill update never overwrites it.
Default config path: ~/.config/usage-mirror/config.json. Override with the USAGE_MIRROR_CONFIG environment variable.
Standard library only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

VERSION = "1.0.0"

DEFAULT_CONFIG = Path.home() / ".config" / "usage-mirror" / "config.json"
DATA_ROOT = Path.home() / ".local" / "share" / "usage-mirror"

DEFAULTS = {
    "accounts": [],
    "output_dir": str(DATA_ROOT / "out"),
    "history_dir": str(DATA_ROOT / "history"),
    "rates_file": str(Path.home() / ".config" / "usage-mirror" / "rates.json"),
    "timezone": "UTC",
    "days": 45,
    "scan_days": 60,
    "live_meters": True,
    "live_reuse_seconds": 300,
    "user_agent": "usage-mirror/1.0.0",
}

PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6", "#e34948", "#008300"]


class ConfigError(Exception):
    pass


def config_path() -> Path:
    env = os.environ.get("USAGE_MIRROR_CONFIG")
    return Path(env).expanduser() if env else DEFAULT_CONFIG


def _expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(p))))


def detect_homes() -> list[Path]:
    """Claude Code config homes found next to the default one: ~/.claude and any ~/.claude* folder with a projects dir."""
    out = []
    for d in sorted(Path.home().glob(".claude*")):
        if d.is_dir() and (d / "projects").is_dir():
            out.append(d)
    return out


def load_config(path: Path | str | None = None, require_accounts: bool = True) -> dict:
    """Read the config file, fill defaults, expand paths. With no file, a single detected default account is used
    so a first run still works; with require_accounts and nothing found it raises ConfigError."""
    p = Path(path).expanduser() if path else config_path()
    raw: dict = {}
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ConfigError(f"config is not valid JSON: {p} ({e})")
    cfg = {**DEFAULTS, **{k: v for k, v in raw.items() if not k.startswith("_")}}
    accts = cfg.get("accounts") or []
    if not accts:
        homes = detect_homes()
        accts = [{"label": ("default" if h.name == ".claude" else h.name.lstrip(".")), "path": str(h)} for h in homes]
    out = []
    seen = set()
    for i, a in enumerate(accts):
        if not isinstance(a, dict) or not a.get("path"):
            raise ConfigError(f"accounts[{i}] needs a path")
        label = str(a.get("label") or _expand(a["path"]).name)
        if label in seen:
            raise ConfigError(f"duplicate account label: {label}")
        seen.add(label)
        out.append({"label": label, "color": a.get("color") or PALETTE[i % len(PALETTE)], "path": _expand(a["path"])})
    if require_accounts and not out:
        raise ConfigError("no accounts configured and no Claude Code home found; copy config.example.json to "
                          f"{DEFAULT_CONFIG} and edit it")
    cfg["accounts"] = out
    for k in ("output_dir", "history_dir", "rates_file"):
        cfg[k] = _expand(cfg[k])
    cfg["_path"] = p
    cfg["_exists"] = p.is_file()
    return cfg


# ---------- time zone ----------
class Clock:
    """Converts UTC instants to the configured local time. If the zone name cannot be resolved (Windows without the
    tzdata package, for example) it falls back to UTC and says so in .warning; the page shows that warning, because a
    silent fallback moves every day boundary."""

    def __init__(self, name: str):
        self.requested = name or "UTC"
        self.warning = ""
        self.effective = "UTC"
        self._tz = dt.timezone.utc
        if self.requested.upper() != "UTC":
            try:
                from zoneinfo import ZoneInfo
                self._tz = ZoneInfo(self.requested)
                self.effective = self.requested
            except Exception:
                self.warning = (f"time zone {self.requested!r} could not be loaded (on Windows run: pip install tzdata); "
                                "days and hours are shown in UTC")

    def local(self, t_utc: dt.datetime) -> dt.datetime:
        return t_utc.astimezone(self._tz).replace(tzinfo=None)

    def now_local(self) -> dt.datetime:
        return self.local(dt.datetime.now(dt.timezone.utc))


def parse_ts(s: str) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def iso_z(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ---------- rates ----------
def load_rates(path: Path) -> tuple[dict, str, str]:
    """(table, version, problem). A missing or broken file gives an empty table and a plain problem sentence; the page
    then shows tokens only and says dollars are off."""
    try:
        r = json.loads(Path(path).read_text(encoding="utf-8"))
        tbl = dict(r.get("usd_per_mtok") or {})
        ver = str(r.get("version") or "unversioned") + (" (as of " + str(r["as_of"]) + ")" if r.get("as_of") else "")
        return tbl, ver, "" if tbl else "the rates file has no usd_per_mtok table"
    except FileNotFoundError:
        return {}, "", f"rates file not found: {path}"
    except Exception as e:
        return {}, "", f"rates file unreadable: {e}"


def rate_for(model: str, tbl: dict) -> dict | None:
    """The exact model, else the longest listed prefix."""
    if model in tbl:
        return tbl[model]
    hits = [k for k in tbl if model.startswith(k)]
    return tbl[max(hits, key=len)] if hits else None


def price(rt: dict | None, inp: int, cw5: int, cw1: int, cr: int, out: int) -> float:
    if not rt:
        return 0.0
    return (inp * rt.get("in", 0) + cw5 * rt.get("write_5m", 0) + cw1 * rt.get("write_1h", 0)
            + cr * rt.get("read", 0) + out * rt.get("out", 0)) / 1e6


def say(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str, code: int = 1) -> "None":
    print("FAIL " + msg, file=sys.stderr)
    sys.exit(code)
