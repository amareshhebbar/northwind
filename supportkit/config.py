from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(os.environ.get("SUPPORT_ROOT", Path(__file__).resolve().parent.parent))

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^${}]*))?\}")


def load_dotenv(path: Optional[Path] = None) -> None:
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def expand(value: Any) -> Any:
    if isinstance(value, str):

        def sub(m: "re.Match[str]") -> str:
            return os.environ.get(m.group(1)) or (m.group(2) if m.group(2) is not None else "")

        previous = None
        while previous != value:
            previous = value
            value = _VAR.sub(sub, value)
        return value
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand(v) for v in value]
    return value


def coerce(value: Any) -> Any:
    if isinstance(value, str):
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        if re.fullmatch(r"-?\d+\.\d+", value):
            return float(value)
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
    if isinstance(value, dict):
        return {k: coerce(v) for k, v in value.items()}
    if isinstance(value, list):
        return [coerce(v) for v in value]
    return value


class Platform:
    def __init__(self, raw: Dict[str, Any], versions: Dict[str, Any]):
        self.raw = raw
        self.platform = raw.get("platform", {})
        self.llm = raw.get("llm", {})
        self.stores = raw.get("stores", {})
        self.services: Dict[str, Dict[str, Any]] = raw.get("services", {})
        self.versions: Dict[str, Any] = versions.get("versions", {})
        self.version_order: List[str] = list(self.versions.keys())
        self.host = self.platform.get("host", "127.0.0.1")

    def service(self, name: str) -> Dict[str, Any]:
        if name not in self.services:
            raise KeyError(f"unknown service '{name}'; known: {', '.join(self.services)}")
        cfg = dict(self.services[name])
        cfg["name"] = name
        merged_llm = dict(self.llm.get("roles", {}))
        merged_llm.update(cfg.get("llm") or {})
        cfg["llm"] = merged_llm
        return cfg

    def url(self, name: str) -> str:
        return f"http://{self.host}:{self.services[name]['port']}"

    def version(self, name: str) -> Dict[str, Any]:
        if name not in self.versions:
            raise KeyError(f"unknown version '{name}'; known: {', '.join(self.version_order)}")
        cfg = dict(self.versions[name])
        cfg["name"] = name
        return cfg

    def active_version(self, service: Optional[str] = None) -> str:
        env_forced = os.environ.get("SUPPORT_VERSION")
        if env_forced:
            return env_forced
        if service:
            f = ROOT / ".state" / "versions" / service
            if f.exists():
                return f.read_text().strip()
        g = ROOT / ".active_version"
        if g.exists():
            return g.read_text().strip()
        return str(self.platform.get("default_version", "v1"))


_cache: Dict[str, Platform] = {}


def load_platform(force: bool = False) -> Platform:
    if "p" in _cache and not force:
        return _cache["p"]
    load_dotenv()
    raw = coerce(expand(yaml.safe_load((ROOT / "platform.yml").read_text(encoding="utf-8"))))
    versions = coerce(expand(yaml.safe_load((ROOT / "versions.yml").read_text(encoding="utf-8"))))
    _cache["p"] = Platform(raw, versions)
    return _cache["p"]
