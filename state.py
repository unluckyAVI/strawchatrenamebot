"""
State manager with MongoDB persistence.
Thumbnail is stored as base64 in MongoDB so it survives server restarts.
"""

from __future__ import annotations
import os
import base64
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
        self.thumbnail: Optional[str] = None        # local path to thumb file
        self.thumbnail_b64: Optional[str] = None    # base64 encoded thumb
        self.rename_override: Optional[str] = None
        self.awaiting_thumbnail: bool = False
        self.awaiting_rename: bool = False
        self.custom_meta: dict = {}
        self.metadata_enabled: bool = True  # backward compat


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
                        state.custom_meta = doc.get("custom_meta", {})
                        # Restore thumbnail from base64 if available
                        thumb_b64 = doc.get("thumbnail_b64", None)
                        if thumb_b64:
                            state.thumbnail_b64 = thumb_b64
                            # Write to disk for use
                            thumb_path = os.path.join(
                                Config.THUMB_DIR, f"thumb_{chat_id}.jpg"
                            )
                            try:
                                with open(thumb_path, "wb") as f:
                                    f.write(base64.b64decode(thumb_b64))
                                state.thumbnail = thumb_path
                                print(f"[STATE] Restored thumbnail for {chat_id}")
                            except Exception as e:
                                print(f"[STATE] Failed to restore thumbnail: {e}")
                except Exception as e:
                    print(f"[STATE] Load failed: {e}")
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
                    "thumbnail_b64": state.thumbnail_b64,
                    "custom_meta": state.custom_meta,
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
        """Save thumbnail path AND encode to base64 for MongoDB."""
        state = self.get(chat_id)
        state.thumbnail = path
        # Encode to base64 for persistent storage
        try:
            with open(path, "rb") as f:
                state.thumbnail_b64 = base64.b64encode(f.read()).decode()
            print(f"[STATE] Thumbnail saved to MongoDB for {chat_id}")
        except Exception as e:
            print(f"[STATE] Failed to encode thumbnail: {e}")
        self._save(chat_id)

    def clear_thumbnail(self, chat_id: int):
        state = self.get(chat_id)
        state.thumbnail = None
        state.thumbnail_b64 = None
        self._save(chat_id)

    def set_rename_override(self, chat_id: int, name: str):
        self.get(chat_id).rename_override = name

    def consume_rename_override(self, chat_id: int) -> Optional[str]:
        state = self.get(chat_id)
        val = state.rename_override
        state.rename_override = None
        return val


# Singleton
state_manager = StateManager()
