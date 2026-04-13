"""
ROADAI Database — MongoDB Atlas (Async)
=======================================
Migration from SQLite to MongoDB for Cloud Deployment (Render + Atlas).
Uses 'motor' for high-performance async I/O.
"""
import os
import asyncio
import json
import logging
import ssl
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ServerSelectionTimeoutError
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Environment configuration
MONGODB_URL = os.environ.get("MONGODB_URL", "mongodb://localhost:27017/roadai")
DB_NAME = os.environ.get("MONGODB_DB", "roadai")
TIMEOUT_MS = int(os.environ.get("MONGODB_TIMEOUT_MS", 30000))
TLS_VERIFY = os.environ.get("MONGODB_TLS_VERIFY", "true").lower() == "true"
FORCE_TLS12 = os.environ.get("MONGODB_FORCE_TLS12", "false").lower() == "true"

# Global state
_client: AsyncIOMotorClient = None
_mode: str = "undecided"  # "cloud" or "rescue"
_fallback_file = Path("config/fallback_db.json")

# ── Fallback implementation (Rescue Mode) ───────────────────────

class FallbackCursor:
    def __init__(self, data):
        self._data = data
    def sort(self, *args, **kwargs): return self
    def limit(self, *args, **kwargs): return self
    async def to_list(self, length=100): return self._data[:length]
    def __aiter__(self):
        async def _iter():
            for item in self._data: yield item
        return _iter()

class FallbackCollection:
    def __init__(self, db_name, coll_name):
        self.coll_name = coll_name
        self.db = _FallbackDBInstance

    def _load(self):
        if not _fallback_file.exists(): return []
        try:
            data = json.loads(_fallback_file.read_text())
            return data.get(self.coll_name, [])
        except: return []

    def _save(self, items):
        data = {}
        if _fallback_file.exists():
            try: data = json.loads(_fallback_file.read_text())
            except: pass
        data[self.coll_name] = items
        _fallback_file.write_text(json.dumps(data, indent=2))

    async def find_one(self, query):
        items = self._load()
        for i in items:
            match = True
            for k, v in query.items():
                if i.get(k) != v: match = False; break
            if match: return i
        return None

    async def insert_one(self, doc):
        items = self._load()
        if "_id" not in doc: doc["_id"] = str(len(items) + 1)
        items.append(doc)
        self._save(items)
        return doc

    async def insert_many(self, docs):
        items = self._load()
        for doc in docs:
            if "_id" not in doc: doc["_id"] = str(len(items) + 1)
            items.append(doc)
        self._save(items)

    async def count_documents(self, query):
        return len(self._load())

    async def replace_one(self, query, replacement):
        items = self._load()
        for idx, i in enumerate(items):
            match = True
            for k, v in query.items():
                if i.get(k) != v: match = False; break
            if match:
                items[idx] = replacement
                break
        self._save(items)

    def find(self, query=None):
        return FallbackCursor(self._load())
    
    def aggregate(self, pipeline):
        # Very basic mock for severity distribution
        return FallbackCursor([])

class FallbackDatabase:
    def __getattr__(self, name):
        return FallbackCollection(DB_NAME, name)

_FallbackDBInstance = FallbackDatabase()

# ── Connection Management ───────────────────────────────────────

def init_db():
    """Initializer (Sync wrapper if needed, but client is lazy)"""
    global _client, _mode
    if _client is None:
        logger.info(f"🔌 Initializing MongoDB Atlas: {DB_NAME}...")
        _client = AsyncIOMotorClient(
            MONGODB_URL, 
            serverSelectionTimeoutMS=TIMEOUT_MS,
            connectTimeoutMS=TIMEOUT_MS,
            tlsAllowInvalidCertificates=not TLS_VERIFY
        )
    return _client

async def get_db():
    """FastAPI Dependency equivalent for MongoDB with Rescue Mode fallback"""
    global _client, _mode
    if _client is None:
        init_db()
    
    if _mode == "rescue":
        return _FallbackDBInstance
        
    if _mode == "undecided":
        try:
            # Quick check if server is reachable (with timeout)
            logger.info(f"⏱️  Checking Atlas connectivity (Timeout: {TIMEOUT_MS/1000}s)...")
            # We use an explicit asyncio timeout to ensure we don't hang if the driver hangs
            await asyncio.wait_for(_client.admin.command('ismaster'), timeout=(TIMEOUT_MS/1000) + 1)
            _mode = "cloud"
            logger.info("✅ Connected to MongoDB Atlas (Cloud Mode)")
        except (asyncio.TimeoutError, Exception) as e:
            _mode = "rescue"
            logger.warning(f"⚠️ FALLBACK: MongoDB unreachable or too slow ({type(e).__name__}). Entering Rescue Mode (Local JSON).")
            return _FallbackDBInstance

    return _client[DB_NAME]

async def close_db():
    global _client
    if _client:
        _client.close()
        _client = None

# ── Helper for ObjectIDs and JSON ───────────────────────────────

def doc_to_dict(doc) -> dict:
    """Recursively convert MongoDB docs (with _id) to clean dicts."""
    if doc is None: return {}
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc

def docs_to_list(docs) -> list:
    return [doc_to_dict(d) for d in docs]
