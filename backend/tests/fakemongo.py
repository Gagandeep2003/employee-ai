"""A small in-memory async Mongo substitute for tests, supporting the subset of
query/update operators this codebase actually uses ($gt/$gte/$lt/$in/$ne/$nin/$or/
$regex/$exists, $set/$inc). Not a full Mongo emulation -- just enough to exercise
real route logic without needing a live database.
"""
import re
import copy
import types


def _get(doc, key):
    return doc.get(key)


def _match_value(doc_val, cond):
    if isinstance(cond, dict) and any(k.startswith("$") for k in cond.keys()):
        for op, val in cond.items():
            if op == "$gt" and not (doc_val is not None and doc_val > val):
                return False
            if op == "$gte" and not (doc_val is not None and doc_val >= val):
                return False
            if op == "$lt" and not (doc_val is not None and doc_val < val):
                return False
            if op == "$lte" and not (doc_val is not None and doc_val <= val):
                return False
            if op == "$in" and doc_val not in val:
                return False
            if op == "$nin" and doc_val in val:
                return False
            if op == "$ne" and doc_val == val:
                return False
            if op == "$exists" and (doc_val is not None) != bool(val):
                return False
            if op == "$regex":
                flags = re.IGNORECASE if cond.get("$options") == "i" else 0
                if not doc_val or not re.search(val, doc_val, flags):
                    return False
        return True
    return doc_val == cond


def _match(doc, query):
    for k, v in query.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
            continue
        if not _match_value(_get(doc, k), v):
            return False
    return True


def _apply_update(doc, update):
    if "$set" in update:
        doc.update(update["$set"])
    if "$inc" in update:
        for k, v in update["$inc"].items():
            doc[k] = doc.get(k, 0) + v
    if "$unset" in update:
        for k in update["$unset"]:
            doc.pop(k, None)


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key, direction=1):
        if isinstance(key, list):
            for k, d in reversed(key):
                self._docs.sort(key=lambda x: (x.get(k) is None, x.get(k)), reverse=(d == -1))
        else:
            self._docs.sort(key=lambda x: (x.get(key) is None, x.get(key)), reverse=(direction == -1))
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    async def to_list(self, n=None):
        return copy.deepcopy(self._docs[:n] if n else self._docs)

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        for d in self._docs:
            yield copy.deepcopy(d)


def _project(doc, projection):
    if not projection:
        return copy.deepcopy(doc)
    include = {k for k, v in projection.items() if v}
    exclude = {k for k, v in projection.items() if not v}
    if include - {"_id"}:
        return {k: v for k, v in doc.items() if k in include}
    return {k: v for k, v in doc.items() if k not in exclude}


class FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query=None, projection=None, sort=None):
        query = query or {}
        candidates = [d for d in self.docs if _match(d, query)]
        if sort:
            for k, direction in reversed(sort):
                candidates.sort(key=lambda x: (x.get(k) is None, x.get(k)), reverse=(direction == -1))
        if not candidates:
            return None
        return _project(candidates[0], projection)

    def find(self, query=None, projection=None):
        query = query or {}
        matched = [_project(d, projection) for d in self.docs if _match(d, query)]
        return FakeCursor(matched)

    async def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))
        return types.SimpleNamespace(inserted_id=doc.get("id") or doc.get("_id") or len(self.docs))

    async def insert_many(self, docs):
        for d in docs:
            self.docs.append(copy.deepcopy(d))
        return types.SimpleNamespace(inserted_ids=list(range(len(docs))))

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                _apply_update(d, update)
                return types.SimpleNamespace(modified_count=1, matched_count=1)
        if upsert:
            new_doc = {}
            for k, v in query.items():
                if not k.startswith("$"):
                    new_doc[k] = v
            _apply_update(new_doc, update)
            self.docs.append(new_doc)
            return types.SimpleNamespace(modified_count=0, matched_count=0, upserted_id=1)
        return types.SimpleNamespace(modified_count=0, matched_count=0)

    async def update_many(self, query, update):
        count = 0
        for d in self.docs:
            if _match(d, query):
                _apply_update(d, update)
                count += 1
        return types.SimpleNamespace(modified_count=count)

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                del self.docs[i]
                return types.SimpleNamespace(deleted_count=1)
        return types.SimpleNamespace(deleted_count=0)

    async def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, query)]
        return types.SimpleNamespace(deleted_count=before - len(self.docs))

    async def count_documents(self, query=None):
        query = query or {}
        return sum(1 for d in self.docs if _match(d, query))

    async def create_index(self, *a, **kw):
        return "fake_index"


class FakeDB:
    """Mimics motor's db[collection_name] attribute/subscript access, creating
    collections lazily on first access -- same as real Mongo."""
    def __init__(self):
        self._collections = {}

    def __getattr__(self, name):
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]

    def __getitem__(self, name):
        return getattr(self, name)

    async def command(self, *a, **kw):
        return {"ok": 1}
