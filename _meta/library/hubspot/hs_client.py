"""
Reusable HubSpot v3/v4 client for migration loaders.

Built for a client migration but deliberately client-agnostic — the pieces the
repo was missing are here rather than inline in one script: note creation *with pinning*, a
preflight validator, retry-after handling, and an upsert that copes with non-unique key
properties.

Stdlib only. No SDK — the SDK re-encodes and hides response bodies, and both matter here.

Key design point: HubSpot's `batch/upsert` requires a UNIQUE idProperty. Probed 2026-08-18:
    POST /crm/v3/objects/contacts/batch/upsert  idProperty=customer_number (non-unique)
    -> 400 "Unable to perform update/upsert by non-unique 0-1 property"
So `upsert_records()` takes a `unique` flag and falls back to search-then-create/patch when the
key property cannot be made unique. That path is slower and not race-safe; it is correct for a
single-threaded migration and is what this codebase needs.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.hubapi.com"
TIMEOUT = 120
BATCH_SIZE = 100
MAX_RETRIES = 5


class HubSpotError(RuntimeError):
    def __init__(self, status, body, url):
        self.status, self.body, self.url = status, body, url
        super().__init__(f"HTTP {status} on {url}: {str(body)[:500]}")


class HS:
    def __init__(self, token: str, label: str = "hubspot", dry_run: bool = True):
        self.token = token
        self.label = label
        self.dry_run = dry_run
        self.calls = 0
        self.errors: list[dict] = []

    # ── transport ─────────────────────────────────────────────────────────────────────────

    def request(self, method: str, path: str, body=None, params: dict | None = None):
        url = BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

        for attempt in range(1, MAX_RETRIES + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    self.calls += 1
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                raw = e.read().decode(errors="replace")
                # 429 and 5xx are retryable; everything else is a real error.
                if e.code == 429 or 500 <= e.code < 600:
                    wait = float(e.headers.get("Retry-After") or 0) or min(2 ** attempt, 30)
                    if attempt < MAX_RETRIES:
                        time.sleep(wait)
                        continue
                raise HubSpotError(e.code, raw, url) from None
            except Exception as e:
                if attempt < MAX_RETRIES:
                    time.sleep(min(2 ** attempt, 30))
                    continue
                raise HubSpotError(0, str(e), url) from None
        raise HubSpotError(0, "retries exhausted", url)

    # ── preflight ─────────────────────────────────────────────────────────────────────────

    def properties(self, object_type: str) -> dict[str, dict]:
        res = self.request("GET", f"/crm/v3/properties/{object_type}")
        return {p["name"]: p for p in res.get("results", [])}

    def association_labels(self, from_obj: str, to_obj: str) -> list[dict]:
        try:
            return self.request(
                "GET", f"/crm/v4/associations/{from_obj}/{to_obj}/labels").get("results", [])
        except HubSpotError:
            return []

    def preflight(self, required_props: dict[str, list[str]],
                  required_assocs: list[tuple[str, str]]) -> list[str]:
        """
        Verify every target property and association type exists BEFORE the first write.
        Returns a list of problem strings; empty means clear to load.
        """
        problems = []
        for obj, names in required_props.items():
            try:
                have = self.properties(obj)
            except HubSpotError as e:
                problems.append(f"{obj}: cannot read properties ({e.status})")
                continue
            for n in names:
                if n not in have:
                    problems.append(f"{obj}.{n} — property does not exist")
        for a, b in required_assocs:
            if not self.association_labels(a, b):
                problems.append(f"association {a} -> {b} — no association type defined")
        return problems

    # ── read ──────────────────────────────────────────────────────────────────────────────

    def search_by_property(self, object_type: str, prop: str, value: str,
                           extra_props: list[str] | None = None) -> dict | None:
        """First record whose `prop` equals `value`, or None."""
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": prop, "operator": "EQ", "value": str(value)}]}],
            "properties": [prop] + (extra_props or []),
            "limit": 2,
        }
        res = self.request("POST", f"/crm/v3/objects/{object_type}/search", body)
        results = res.get("results") or []
        return results[0] if results else None

    def batch_read_by_property(self, object_type: str, prop: str,
                               values: list[str]) -> dict[str, str]:
        """{key_value: record_id} for a unique idProperty. Missing keys are simply absent."""
        found: dict[str, str] = {}
        for chunk in _chunks([v for v in values if v], BATCH_SIZE):
            body = {"idProperty": prop, "properties": [prop],
                    "inputs": [{"id": str(v)} for v in chunk]}
            try:
                res = self.request("POST", f"/crm/v3/objects/{object_type}/batch/read", body)
            except HubSpotError as e:
                if e.status == 404:      # none of the chunk exists yet
                    continue
                raise
            for r in res.get("results", []):
                k = (r.get("properties") or {}).get(prop)
                if k:
                    found[str(k)] = r["id"]
        return found

    # ── write ─────────────────────────────────────────────────────────────────────────────

    def upsert_records(self, object_type: str, key_prop: str, records: list[dict],
                       unique: bool) -> dict[str, str]:
        """
        records: [{key_prop: <key>, ...other properties...}]
        Returns {key_value: hubspot_id}. In dry-run, returns synthetic ids and writes nothing.
        """
        keyed = {}
        for r in records:
            k = str(r.get(key_prop) or "").strip()
            if k:
                keyed[k] = r                      # last one wins; callers pre-dedupe

        if self.dry_run:
            return {k: f"DRYRUN-{object_type}-{i}" for i, k in enumerate(keyed, 1)}

        if unique:
            return self._batch_upsert(object_type, key_prop, keyed)
        return self._search_then_write(object_type, key_prop, keyed)

    def _batch_upsert(self, object_type: str, key_prop: str, keyed: dict) -> dict[str, str]:
        out = {}
        for chunk in _chunks(list(keyed.items()), BATCH_SIZE):
            body = {"inputs": [{"idProperty": key_prop, "id": k, "properties": _stringify(p)}
                               for k, p in chunk]}
            try:
                res = self.request(
                    "POST", f"/crm/v3/objects/{object_type}/batch/upsert", body)
            except HubSpotError as e:
                if len(chunk) == 1:
                    self.errors.append({"object": object_type, "op": "batch/upsert",
                                        "status": e.status, "body": str(e.body)[:600],
                                        "keys": [k for k, _ in chunk]})
                    continue
                # One bad record fails the whole batch. Retry each record on its own so only
                # the bad one is lost (CB051 — a unique key makes a single reject likelier).
                for k, props in chunk:
                    out.update(self._batch_upsert(object_type, key_prop, {k: props}))
                continue
            for r in res.get("results", []):
                k = (r.get("properties") or {}).get(key_prop)
                if k:
                    out[str(k)] = r["id"]
        return out

    def _search_then_write(self, object_type: str, key_prop: str, keyed: dict) -> dict[str, str]:
        """Non-unique key property: search, then PATCH or POST. One record at a time."""
        out = {}
        for k, props in keyed.items():
            try:
                existing = self.search_by_property(object_type, key_prop, k)
                if existing:
                    self.request("PATCH", f"/crm/v3/objects/{object_type}/{existing['id']}",
                                 {"properties": _stringify(props)})
                    out[k] = existing["id"]
                else:
                    res = self.request("POST", f"/crm/v3/objects/{object_type}",
                                       {"properties": _stringify(props)})
                    out[k] = res["id"]
            except HubSpotError as e:
                self.errors.append({"object": object_type, "op": "search-then-write",
                                    "status": e.status, "body": str(e.body)[:600], "key": k})
        return out

    def associate(self, from_obj: str, from_id: str, to_obj: str, to_id: str,
                  type_id: int | None = None) -> bool:
        if self.dry_run:
            return True
        try:
            if type_id is None:
                # v4 default association for the pair.
                self.request("PUT", f"/crm/v4/objects/{from_obj}/{from_id}/associations/default/"
                                    f"{to_obj}/{to_id}")
            else:
                self.request("PUT", f"/crm/v4/objects/{from_obj}/{from_id}/associations/"
                                    f"{to_obj}/{to_id}",
                             [{"associationCategory": "HUBSPOT_DEFINED",
                               "associationTypeId": type_id}])
            return True
        except HubSpotError as e:
            self.errors.append({"op": "associate", "from": f"{from_obj}:{from_id}",
                                "to": f"{to_obj}:{to_id}", "status": e.status,
                                "body": str(e.body)[:400]})
            return False

    def associate_batch(self, from_obj: str, to_obj: str, pairs: list[tuple[str, str]],
                        type_id: int | None = None) -> int:
        """
        Batch-create associations, 100 per call, via the v4 batch endpoint instead of one
        PUT per pair. At migration scale (thousands of tickets x 3 associations each) this is
        the difference between a few dozen calls and several thousand.
        """
        if self.dry_run:
            return len(pairs)
        made = 0
        # Verified 2026-08-18 against a sandbox: the untyped ("default") batch endpoint is
        # .../batch/associate/default, NOT .../batch/create/default (404s). The labeled endpoint
        # is .../batch/create (no /default suffix; .../batch/associate 404s for that one).
        # Asymmetric naming — confirmed live, not inferred from memory.
        path = (f"/crm/v4/associations/{from_obj}/{to_obj}/batch/associate/default" if type_id is None
                else f"/crm/v4/associations/{from_obj}/{to_obj}/batch/create")
        for chunk in _chunks(pairs, BATCH_SIZE):
            inputs = [{"from": {"id": f}, "to": {"id": t}} if type_id is None else
                      {"from": {"id": f}, "to": {"id": t},
                       "types": [{"associationCategory": "HUBSPOT_DEFINED",
                                  "associationTypeId": type_id}]}
                     for f, t in chunk]
            try:
                self.request("POST", path, {"inputs": inputs})
                # The v4 batch response returns two result rows per pair (the association is
                # bidirectional) — count input pairs, not result rows, so this reflects pairs
                # actually associated.
                made += len(chunk)
            except HubSpotError as e:
                self.errors.append({"op": "associate_batch", "from_obj": from_obj,
                                    "to_obj": to_obj, "status": e.status,
                                    "body": str(e.body)[:400], "count": len(chunk)})
        return made

    # ── notes ─────────────────────────────────────────────────────────────────────────────

    # Ticket <- Note association type id. 228 is the HubSpot-defined note_to_ticket type.
    NOTE_TO_TICKET = 228

    def create_note_on_ticket(self, ticket_id: str, body_html: str, timestamp_ms: int,
                              pin: bool = True) -> str | None:
        """
        Create a note, associate it to the ticket, and optionally PIN it.

        Notes cannot be upserted — there is no idProperty on an engagement. The caller MUST
        track creation in its own state file or a re-run duplicates every note.
        """
        if self.dry_run:
            return f"DRYRUN-note-{ticket_id}"
        try:
            res = self.request("POST", "/crm/v3/objects/notes", {
                "properties": {"hs_note_body": body_html, "hs_timestamp": str(timestamp_ms)},
                "associations": [{
                    "to": {"id": ticket_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED",
                               "associationTypeId": self.NOTE_TO_TICKET}],
                }],
            })
            note_id = res["id"]
        except HubSpotError as e:
            self.errors.append({"op": "create_note", "ticket": ticket_id,
                                "status": e.status, "body": str(e.body)[:600]})
            return None

        if pin:
            # Pinning is a property on the PARENT record, not on the note.
            try:
                self.request("PATCH", f"/crm/v3/objects/tickets/{ticket_id}",
                             {"properties": {"hs_pinned_engagement_id": note_id}})
            except HubSpotError as e:
                self.errors.append({"op": "pin_note", "ticket": ticket_id, "note": note_id,
                                    "status": e.status, "body": str(e.body)[:400]})
        return note_id

    def batch_create_notes(self, items: list[dict], pin: bool = True) -> dict[str, str]:
        """Bulk version of create_note_on_ticket. `items` = [{ticket_id, body_html, timestamp_ms}].

        Returns {ticket_id: note_id}.

        Why this exists: the per-note path above costs 2 sequential round trips per ticket
        (create + pin) and is not batchable by the caller, which made notes ~62% of a full
        migration's wall clock. Measured 2026-09-01: notes/batch/create with the association
        INLINE does work and creates the association (verified by reading it back), so 100 notes
        cost one call instead of 100, and the pins collapse into one tickets/batch/update.

        Still no upsert path — engagements have no idProperty — so the caller MUST keep tracking
        which tickets already have a note or a re-run duplicates them.
        """
        out: dict[str, str] = {}
        if not items:
            return out
        if self.dry_run:
            return {i["ticket_id"]: f"DRYRUN-note-{i['ticket_id']}" for i in items}

        for chunk in _chunks(items, BATCH_SIZE):
            inputs = [{
                "properties": {"hs_note_body": i["body_html"],
                               "hs_timestamp": str(i["timestamp_ms"])},
                "associations": [{
                    "to": {"id": i["ticket_id"]},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED",
                               "associationTypeId": self.NOTE_TO_TICKET}],
                }],
            } for i in chunk]
            try:
                res = self.request("POST", "/crm/v3/objects/notes/batch/create",
                                   {"inputs": inputs})
            except HubSpotError as e:
                self.errors.append({"op": "batch_create_notes", "count": len(chunk),
                                    "status": e.status, "body": str(e.body)[:600]})
                continue
            # Results do NOT come back in input order (measured 2026-09-28), and a note has no
            # key property to match on. Read back which ticket each new note is associated to —
            # the association was set inline from the correct ticket_id, so it is the truth.
            note_ids = [r["id"] for r in res.get("results", [])]
            wanted = {str(i["ticket_id"]) for i in chunk}
            try:
                rb = self.request("POST", "/crm/v4/associations/notes/tickets/batch/read",
                                  {"inputs": [{"id": n} for n in note_ids]})
            except HubSpotError as e:
                self.errors.append({"op": "batch_create_notes/readback", "count": len(note_ids),
                                    "status": e.status, "body": str(e.body)[:600]})
                continue
            for row in rb.get("results", []):
                nid = str((row.get("from") or {}).get("id"))
                for to in row.get("to") or []:
                    tid = str(to.get("toObjectId"))
                    if tid in wanted:
                        out[tid] = nid

        if pin and out:
            for chunk in _chunks(list(out.items()), BATCH_SIZE):
                try:
                    self.request("POST", "/crm/v3/objects/tickets/batch/update",
                                 {"inputs": [{"id": tid,
                                              "properties": {"hs_pinned_engagement_id": nid}}
                                             for tid, nid in chunk]})
                except HubSpotError as e:
                    self.errors.append({"op": "batch_pin_notes", "count": len(chunk),
                                        "status": e.status, "body": str(e.body)[:600]})
        return out

    def batch_create_with_associations(self, object_type: str,
                                       records: list[tuple[dict, list[dict]]],
                                       key_prop: str | None = None) -> list[str]:
        """Create records with their associations IN THE CREATE CALL. Returns ids, in order.

        batch/create does NOT return results in input order (measured 2026-09-28: 6 of 9
        tickets came back shuffled, so claims and notes were attached to the wrong cases).
        Pass `key_prop` — a property every record carries with a distinct value — and results
        are matched back by that value. Without it, positional order is assumed, which is only
        safe for single-record chunks.

        `records` = [(properties, [{"to_object_id":..., "type_id":..., "category":...}, ...])]

        WHY NOT batch/upsert — measured 2026-09-01, and it is a silent-data-loss trap:
        `tickets/batch/upsert` ACCEPTS an `associations` block, returns HTTP 2xx, and does NOT
        create the association. Reading the association back is the only way to notice. So
        anything that needs an association to exist AT CREATION TIME (e.g. a HubSpot workflow
        that reads the associated contact to name the record, and does not re-enroll) has to go
        through batch/CREATE and give up upsert idempotency. The caller decides which it needs.
        """
        ids: list[str] = []
        if not records:
            return ids
        if self.dry_run:
            return [f"DRYRUN-{object_type}-{n}" for n in range(len(records))]

        for chunk in _chunks(records, BATCH_SIZE):
            inputs = []
            for props, assocs in chunk:
                item = {"properties": _stringify(props)}
                if assocs:
                    item["associations"] = [{
                        "to": {"id": str(a["to_object_id"])},
                        "types": [{"associationCategory": a.get("category", "HUBSPOT_DEFINED"),
                                   "associationTypeId": a["type_id"]}],
                    } for a in assocs]
                inputs.append(item)
            try:
                res = self.request("POST", f"/crm/v3/objects/{object_type}/batch/create",
                                   {"inputs": inputs})
            except HubSpotError as e:
                self.errors.append({"op": "batch_create_with_associations",
                                    "object": object_type, "count": len(chunk),
                                    "status": e.status, "body": str(e.body)[:600]})
                ids += [None] * len(chunk)
                continue
            results = res.get("results", [])
            if key_prop:
                by_key = {str((r.get("properties") or {}).get(key_prop)): r["id"] for r in results}
                ids += [by_key.get(str(props.get(key_prop))) for props, _a in chunk]
            elif len(chunk) == 1:
                ids += [r["id"] for r in results]
            else:
                raise ValueError("batch_create_with_associations: key_prop is required for "
                                 "multi-record chunks — HubSpot does not preserve input order")
        return ids


# ── helpers ───────────────────────────────────────────────────────────────────────────────────

def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _stringify(props: dict) -> dict:
    """HubSpot wants strings. Drop Nones and empties rather than sending nulls."""
    out = {}
    for k, v in props.items():
        if v is None or v == "":
            continue
        out[k] = v if isinstance(v, str) else ("true" if v is True else
                                               "false" if v is False else str(v))
    return out
