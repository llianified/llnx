"""Tiny JSON helpers over urllib, so no HTTP library is needed."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request


def get_json(url: str, timeout: int = 15, headers: dict | None = None) -> dict:
    h = {"User-Agent": "bot-trading/0.2", "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post_json(url: str, payload: dict, timeout: int = 20,
              headers: dict | None = None) -> dict:
    h = {"User-Agent": "bot-trading/0.2", "Accept": "application/json",
         "Content-Type": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())
