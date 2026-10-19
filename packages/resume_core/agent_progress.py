"""Bound explicitly public provider summaries without exposing raw reasoning."""

import hashlib
import time


class PublicProgress:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.items = set()
        self.text = {}
        self.sent = {}
        self.last_at = 0
        self.count = 0

    def accept(self, method, params, emit):
        if not isinstance(params, dict):
            return
        item = params.get("item", {})
        if not isinstance(item, dict):
            item = {}
        if method == "item/started" and item.get("type") == "reasoning":
            identifier = item.get("id")
            if isinstance(identifier, str) and len(self.items) < 32:
                self.items.add(identifier)
        elif method == "item/reasoning/summaryTextDelta":
            identifier, index, delta = params.get("itemId"), params.get("summaryIndex"), params.get("delta")
            if not isinstance(identifier, str) or identifier not in self.items or type(index) is not int or not 0 <= index < 16 or not isinstance(delta, str):
                return
            key = (identifier, index)
            if key not in self.text and len(self.text) >= 64:
                return
            self.text[key] = (self.text.get(key, "") + delta)[:1200]
            self.publish(key, emit)
        elif method == "item/completed" and item.get("type") == "reasoning" and isinstance(item.get("id"), str) and item["id"] in self.items:
            identifier = item["id"]
            summary = item.get("summary", [])
            if isinstance(summary, list):
                for index, part in enumerate(summary[:16]):
                    value = part if isinstance(part, str) else part.get("text") if isinstance(part, dict) and part.get("type") == "summary_text" else None
                    key = (identifier, index)
                    if isinstance(value, str) and (key in self.text or len(self.text) < 64):
                        self.text[key] = value[:1200]
            for key in list(self.text):
                if key[0] == identifier:
                    self.publish(key, emit, final=True)

    def publish(self, key, emit, *, final=False):
        value = self.text[key].strip()
        now = self.clock()
        if (not value or self.sent.get(key) == value or self.count >= 24
                or not final and self.count > 0 and now - self.last_at < 1):
            return
        self.sent[key], self.last_at = value, now
        self.count += 1
        identifier = "summary_" + hashlib.sha256(f"{key[0]}:{key[1]}".encode()).hexdigest()[:24]
        emit("activity.updated", {"itemId": identifier, "kind": "summary", "text": value})
