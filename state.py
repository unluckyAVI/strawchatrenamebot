"""
State manager with MongoDB persistence.
Stores per-chat: format, thumbnail, rename override, custom metadata, awaiting states.
"""

from __future__ import annotations
from typing import Optional
from config import Config

try:
    from pymongo import MongoClient
    _mongo_client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
    _mongo_client.server_info()
    _db = _mongo_client["straWchat_bot"]
    _col = _db["user_states"]
    MONGO_AVAILABLE = True
    print("[STATE] MongoDB connected successfully ✅")
except Exception as e:
    MONGO_AVAILABLE = False
    print(f"[STATE] MongoDB unavailable, using in-memory store ⚠️ ({e})")


class ChatState:
    def __init__(self):
        self.fmt: str = Config.DEFAULT_FORMAT
        self.thumbnail: Optional[str] = None
        self.rename_override: Optional[str] = None
        self.awaiting_thumbnail: bool = False
        self.awaiting_rename: bool = False
        self.custom_meta: dict = {}   # customizable metadata fields
        self.metadata_enabled: bool = True   # on/off toggle for metadata embedding


class StateManager:
    def __init__(self):
        self._cache: dict[int, ChatState] = {}

    def get(self, chat_id: int) -> ChatState:
        if chat_id not in self._cache:
            state = ChatState()
            if MONGO_AVAILABLE:
                try:
                    doc = _col.find_one({"_id": chat_id})
                    if doc:
                        state.fmt = doc.get("fmt", Config.DEFAULT_FORMAT)
                        state.thumbnail = doc.get("thumbnail", None)
                        state.custom_meta = doc.get("custom_meta", {})
                        state.metadata_enabled = doc.get("metadata_enabled", True)
                except Exception:
                    pass
            self._cache[chat_id] = state
        return self._cache[chat_id]

    def _save(self, chat_id: int):
        if not MONGO_AVAILABLE:
            return
        state = self._cache.get(chat_id)
        if not state:
            return
        try:
            _col.update_one(
                {"_id": chat_id},
                {"$set": {
                    "fmt": state.fmt,
                    "thumbnail": state.thumbnail,
                    "custom_meta": state.custom_meta,
                    "metadata_enabled": state.metadata_enabled,
                }},
                upsert=True,
            )
        except Exception as e:
            print(f"[STATE] MongoDB save failed: {e}")

    def reset_format(self, chat_id: int):
        self.get(chat_id).fmt = Config.DEFAULT_FORMAT
        self._save(chat_id)

    def set_format(self, chat_id: int, fmt: str):
        self.get(chat_id).fmt = fmt
        self._save(chat_id)

    def set_thumbnail(self, chat_id: int, path: str):
        self.get(chat_id).thumbnail = path
        self._save(chat_id)

    def clear_thumbnail(self, chat_id: int):
        self.get(chat_id).thumbnail = None
        self._save(chat_id)

    def set_rename_override(self, chat_id: int, name: str):
        self.get(chat_id).rename_override = name

    def set_metadata_enabled(self, chat_id: int, enabled: bool):
        self.get(chat_id).metadata_enabled = enabled
        self._save(chat_id)

    def consume_rename_override(self, chat_id: int) -> Optional[str]:
        state = self.get(chat_id)
        val = state.rename_override
        state.rename_override = None
        return val


# Singleton
state_manager = StateManager()
