"""Persistent, per-user demo request state; never stores credentials."""
from contextlib import closing
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from uuid import UUID

from catalog import apartment


class DraftConflict(ValueError):
    pass


class DraftStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS drafts (owner TEXT PRIMARY KEY, state TEXT NOT NULL)")
        except sqlite3.Error as exc:
            raise OSError("Could not initialize draft storage") from exc

    @staticmethod
    def owner(user_id):
        return hashlib.sha256(f"kinshore-demo:{user_id}".encode()).hexdigest()

    @staticmethod
    def validate(state):
        try:
            keys = ("draft_id", "checkin", "checkout", "guests", "step", "category_id", "submission_key")
            clean = {key: state[key] for key in keys}
            if "nightly_cents" in state:
                if type(state["nightly_cents"]) is not int or state["nightly_cents"] < 0:
                    raise ValueError
                clean["nightly_cents"] = state["nightly_cents"]
            if clean["step"] == "submitted_demo":
                clean["reference"] = state["reference"]
                if not isinstance(clean["reference"], str) or not clean["reference"]:
                    raise ValueError
            elif clean["step"] != "review_demo":
                raise ValueError
            if not re.fullmatch(r"[0-9a-f]{8}", clean["draft_id"]):
                raise ValueError
            if str(UUID(clean["submission_key"])) != clean["submission_key"]:
                raise ValueError
            if not apartment(clean["category_id"]) or type(clean["guests"]) is not int or not 1 <= clean["guests"] <= 6:
                raise ValueError
            for key in ("arrival_editable", "with_pet", "by_car"):
                if key in state:
                    if type(state[key]) is not bool:
                        raise ValueError
                    clean[key] = state[key]
            if "children" in state:
                if type(state["children"]) is not int or not 0 <= state["children"] < clean["guests"]:
                    raise ValueError
                clean["children"] = state["children"]
            start, end = date.fromisoformat(clean["checkin"]), date.fromisoformat(clean["checkout"])
            if not 1 <= (end - start).days <= 90:
                raise ValueError
            return clean
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ValueError("Invalid saved draft") from None

    def load(self, user_id):
        try:
            with closing(sqlite3.connect(self.path)) as db:
                row = db.execute("SELECT state FROM drafts WHERE owner = ?", (self.owner(user_id),)).fetchone()
            return self.validate(json.loads(row[0])) if row else None
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise OSError("Could not read saved draft") from exc

    def save(self, user_id, state):
        state = self.validate(state)
        try:
            with closing(sqlite3.connect(self.path)) as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT state FROM drafts WHERE owner = ?", (self.owner(user_id),)).fetchone()
                if row:
                    old = self.validate(json.loads(row[0]))
                    if old["step"] == "review_demo" and old["submission_key"] != state["submission_key"]:
                        raise DraftConflict("An unfinished request already exists")
                db.execute("INSERT OR REPLACE INTO drafts (owner, state) VALUES (?, ?)",
                           (self.owner(user_id), json.dumps(state)))
                db.commit()
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise OSError("Could not save draft") from exc

    def discard(self, user_id, draft_id):
        try:
            with closing(sqlite3.connect(self.path)) as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT state FROM drafts WHERE owner = ?", (self.owner(user_id),)).fetchone()
                old = self.validate(json.loads(row[0])) if row else None
                if not old or old["step"] != "review_demo" or old["draft_id"] != draft_id:
                    return False
                db.execute("DELETE FROM drafts WHERE owner = ?", (self.owner(user_id),))
                db.commit()
                return True
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise OSError("Could not discard draft") from exc
