# HubSpot Workflow API — v4 Flows Reference

*Source: reverse-engineered from live portal exports + sandbox testing. June 2026.*
*Authoritative export: `<Client>/work/<build-folder>/workflow_exports/`*

---

## Core Endpoints

```
POST   /automation/v4/flows              # Create
GET    /automation/v4/flows              # List all
GET    /automation/v4/flows/{flowId}     # Get one
PUT    /automation/v4/flows/{flowId}     # Full replace (requires revisionId)
DELETE /automation/v4/flows/{flowId}     # Permanent delete
POST   /automation/v4/flows/batch/read   # Batch fetch by IDs
```

Auth header: `Authorization: Bearer <private_app_token>`  
Required scope: `automation`

---

## Top-Level Workflow Fields

| Field | Type | Notes |
|---|---|---|
| `name` | string | Display name in HubSpot UI |
| `type` | string | `"CONTACT_FLOW"` for contact workflows |
| `flowType` | string | Always `"WORKFLOW"` |
| `objectTypeId` | string | `"0-1"` contacts, `"0-2"` companies, `"0-3"` deals |
| `isEnabled` | boolean | `false` to create disabled (recommended for new deploys) |
| `startActionId` | **string** | ID of the first action — **must be a string, not int** |
| `nextAvailableActionId` | **string** | Next available action slot — **must be a string, not int** |
| `actions` | array | Flat list of action objects (see below) |
| `enrollmentCriteria` | object | Trigger configuration |
| `timeWindows` | array | Usually `[]` |
| `blockedDates` | array | Usually `[]` |
| `suppressionListIds` | array | Usually `[]` |
| `canEnrollFromSalesforce` | boolean | Usually `false` |
| `revisionId` | integer | Required for PUT. Get from GET response. |

> **Critical:** `startActionId` and `nextAvailableActionId` are strings (`"1"`, `"36"`), not integers.
> Passing integers causes: `Cannot construct instance of ApiActionId: no int/Int-argument constructor/factory method to deserialize from Number value (1)`

---

## enrollmentCriteria

The v4 API only reliably accepts `"MANUAL"` for enrollment type when creating workflows via API. Set the actual trigger (form submission, property change, etc.) in the HubSpot UI after creation.

```json
"enrollmentCriteria": {
  "shouldReEnroll": true,
  "type": "MANUAL"
}
```

---

## Action Types

### SINGLE_CONNECTION — Property Set (`actionTypeId: "0-5"`)

Used to write a value to a contact property.

```json
{
  "actionId": "3",
  "type": "SINGLE_CONNECTION",
  "actionTypeId": "0-5",
  "actionTypeVersion": 0,
  "connection": {
    "edgeType": "STANDARD",
    "nextActionId": "4"
  },
  "fields": {
    "property_name": "lead_source",
    "value": {
      "staticValue": "Paid (Search)",
      "type": "STATIC_VALUE"
    }
  }
}
```

#### Value types for `fields.value`:

**Static string:**
```json
{ "staticValue": "some value", "type": "STATIC_VALUE" }
```

**Contact property token (e.g. copy utm_source to utm_source_first):**
```json
{ "staticValue": "{{ contact.utm_source }}", "type": "STATIC_VALUE" }
```

**Code action output:**
```json
{
  "actionId": "1",
  "dataKey": "resolved_lead_source",
  "type": "FIELD_DATA"
}
```
Where `"1"` is the actionId of the CUSTOM_CODE action that produced the output.

**Timestamp (execution time):**
```json
{ "timestampType": "EXECUTION_TIME", "type": "TIMESTAMP" }
```

**Clear a field (empty string):**
```json
{ "staticValue": "", "type": "STATIC_VALUE" }
```

---

### SINGLE_CONNECTION — Delay (`actionTypeId: "0-1"`)

```json
{
  "actionId": "19",
  "type": "SINGLE_CONNECTION",
  "actionTypeId": "0-1",
  "actionTypeVersion": 0,
  "fields": {
    "delta": "1",
    "time_unit": "MINUTES"
  }
}
```
`time_unit` options: `"MINUTES"`, `"HOURS"`, `"DAYS"`, `"WEEKS"`

---

### LIST_BRANCH — Conditional branch

Evaluates a filter condition. Matching contacts go to `listBranches[0].connection`; non-matching go to `defaultBranch`.

```json
{
  "actionId": "2",
  "type": "LIST_BRANCH",
  "listBranches": [
    {
      "filterBranch": { ... },
      "branchName": "first-touch, new lead",
      "connection": {
        "edgeType": "STANDARD",
        "nextActionId": "11"
      }
    }
  ],
  "defaultBranch": {
    "edgeType": "STANDARD",
    "nextActionId": "10"
  }
}
```

Multiple match branches are supported in `listBranches[]`. Omit `defaultBranch` to terminate the workflow when no branch matches.

---

## Filter / Branch Structure

The `filterBranch` block inside `listBranches`:

```json
{
  "filterBranches": [
    {
      "filterBranches": [],
      "filters": [
        {
          "property": "utm_source",
          "operation": {
            "operator": "IS_KNOWN",
            "includeObjectsWithNoValueSet": false,
            "operationType": "ALL_PROPERTY"
          },
          "filterType": "PROPERTY"
        }
      ],
      "filterBranchType": "AND",
      "filterBranchOperator": "AND"
    }
  ],
  "filters": [],
  "filterBranchType": "OR",
  "filterBranchOperator": "OR"
}
```

The outer `OR` block wraps inner `AND` blocks. This mirrors the HubSpot UI's "any of the following / all of the following" structure.

### Property operators

| Operator | `operationType` | Use |
|---|---|---|
| `IS_KNOWN` | `ALL_PROPERTY` | Property has a value |
| `IS_UNKNOWN` | `ALL_PROPERTY` | Property is empty / not set |
| `EQUAL` | `STRING` | Exact match |
| `CONTAINS_ALL` | `ENUMERATION` | Value is in list |
| `NOT_EQUAL` | `STRING` | Does not match |

For `IS_KNOWN` / `IS_UNKNOWN`:
- `includeObjectsWithNoValueSet`: `false` for IS_KNOWN, `true` for IS_UNKNOWN

For `CONTAINS_ALL` with enum values:
```json
{
  "property": "lead_source",
  "operation": {
    "operator": "CONTAINS_ALL",
    "includeObjectsWithNoValueSet": false,
    "values": ["Paid (Display)", "Paid (Social)"],
    "operationType": "ENUMERATION"
  },
  "filterType": "PROPERTY"
}
```

---

## Connection / Edge Types

| `edgeType` | Use |
|---|---|
| `STANDARD` | Sequential flow to next action |
| `GOTO` | Jump (non-sequential — e.g. two branches merging back to same action) |

Use `GOTO` when multiple paths converge on the same downstream action and you need to avoid duplicate-step visual noise in the UI.

---

## Terminal Actions (End of Workflow)

Omit the `connection` key entirely on the last action:

```json
{
  "actionId": "35",
  "type": "SINGLE_CONNECTION",
  "actionTypeId": "0-5",
  "actionTypeVersion": 0,
  "fields": {
    "property_name": "utm_term",
    "value": { "staticValue": "", "type": "STATIC_VALUE" }
  }
}
```

---

## CUSTOM_CODE Action

Code actions are not deployable via the POST /flows API — they must be created/pasted manually in the HubSpot UI. The v4 API will reject a payload containing a `CUSTOM_CODE` action type on creation.

When cloning an existing workflow that contains a code action, the clone inherits it. This is the intended path for deploying code-action workflows at scale:
1. Build and verify the code action manually in sandbox
2. Use the clone endpoint or GET + PUT pattern to replicate to other workflows
3. Do not attempt to POST a new workflow with CUSTOM_CODE in the payload

---

## Update (PUT) Requirements

1. `GET /automation/v4/flows/{id}` to get current state + `revisionId`
2. Remove from payload before PUT: `id`, `createdAt`, `updatedAt`, `dataSources`, `crmObjectCreationStatus`
3. Include `revisionId` in PUT payload (must match current)
4. PUT replaces the entire workflow — include ALL actions, not just changes

---

## Property Token Format

Contact property values in `STATIC_VALUE` strings:
```
{{ contact.utm_source }}
{{ contact.utm_source_first }}
{{ contact.utm_source_last__c }}
```

Code action output values:
```
{{ action_outputs.action_output_1.resolved_lead_source }}
```
Where `1` is the `actionId` of the CUSTOM_CODE action.

---

## Known Error Messages

| Error | Cause | Fix |
|---|---|---|
| `Cannot construct instance of ApiActionId: no int/Int-argument constructor/factory method to deserialize from Number value (1)` | `startActionId` or `nextAvailableActionId` is an integer | Change to string: `"1"`, `"36"` |
| `Invalid request to flow creation` / `FLOW_CREATION_BAD_REQUEST` | Various; see below | See constraints table |
| `revisionId mismatch` | PUT with stale revisionId | Re-fetch with GET before PUT |
| `startActionId not found` | `startActionId` references an actionId not in the actions array | Verify first action's `actionId` matches `startActionId` |

---

## Verified Constraints (tested June 2026, re-tested + corrected July 2026)

| Constraint | Behavior |
|---|---|
| `LIST_BRANCH` — fresh POST | **Works**, corrected July 2026. The June note that fresh POST "always fails" was wrong or specific to a payload shape at the time — see the convergence rule below, which was the actual cause of most `FLOW_CREATION_BAD_REQUEST` failures during the July opt-in build. `enrollmentCriteria.type: "EVENT_BASED"` + `LIST_BRANCH` actions POST successfully together (tested repeatedly, a real portal, July 2026). |
| **Action convergence — the real rule** | When two or more edges land on the same downstream `actionId`, the **first** in-edge may be `STANDARD`; every subsequent in-edge to that same target **must** be `edgeType: "GOTO"`. This applies to `connection` on `SINGLE_CONNECTION` actions AND to `listBranches[].connection` / `defaultBranch` — but a `LIST_BRANCH`'s own arm/default edges must stay `STANDARD` (see next row), so route the *extra* convergent edges through GOTO on the SINGLE_CONNECTION side instead. Violating this is the most common cause of `FLOW_CREATION_BAD_REQUEST` with no other clue in the error body. |
| Two `LIST_BRANCH` arms (or arm + `defaultBranch`) targeting the same `nextActionId` | **Still forbidden**, confirmed again July 2026. If two cohorts should reach the same next step, merge them into one arm as an `OR` of `AND` filter-branches (see Filter/Branch structure) rather than two arms with the same target. |
| `defaultBranch` targeting another `LIST_BRANCH` action directly | **Forbidden** (400). Route through an intermediate `SINGLE_CONNECTION` relay action first, even a no-op property set, then into the next branch. |
| `IS_UNKNOWN` operator in a `LIST_BRANCH` filter | **Rejected** (400), confirmed July 2026. Use the inverted form instead: branch on `IS_KNOWN` matching → "already set, skip"; `defaultBranch` → the "was empty" action. |
| `defaultBranch.edgeType` | Must be `"STANDARD"`. `"GOTO"` in `defaultBranch` → 400. |
| `edgeType: "GOTO"` on SINGLE_CONNECTION | Allowed, and is the documented way to converge edges — see convergence rule above. |
| `listBranches[].connection.edgeType` | Must stay `"STANDARD"` even when the arm's target is also reached another way — put the GOTO on the other (non-branch) edge into that target. |
| `CUSTOM_CODE` action type | Can be cloned. Cannot be created from scratch via POST (likely — not re-tested July 2026). Paste code manually in UI. |
| `STATIC_VALUE` with `{{ contact.property_name }}` token | Works, including copying one property's value into a *different* property (verified for string/enum in July 2026 build; datetime→datetime token copy accepted by the API but not confirmed to render correctly — verify with a live contact). |
| `OBJECT_PROPERTY` value type | Works. Shape: `{"type": "OBJECT_PROPERTY", "propertyName": "<enrolled-object prop>"}`. **Use this, not a `STATIC_VALUE` token, for enumeration targets on create-record actions:** the API accepts `{{ enrolled_object.x }}` but the editor validates the literal token against the option list and shows "Invalid option chosen for property" (a real portal flow, Oct 2026). |
| `enrollmentCriteria.type` | `"MANUAL"` and `"EVENT_BASED"` both verified via API (July 2026: `EVENT_BASED` with `eventTypeId: "4-655002"` = contact property-change, `operator: "HAS_COMPLETED"`, filter `property: "hs_name"` / `operation.value: "<property to watch>"` — this is the shape used by every property-change-triggered workflow built in this portal). Multiple `eventFilterBranches` entries OR together (verified — a workflow can watch two different properties for the same enrollment). |
| Static-list "add contact" action | POST with `actionTypeId: "0-13"`, `fields: {"list_id": "<id>", "operation": "ADD"}`. On read-back the API normalizes this to the canonical action `actionTypeId: "0-63809083"`, `fields: {"listId": "<id>", "targetObject": "{{ enrolled_object }}"}` — expect the ID/field-name change when verifying via GET, it's the same action. |
| Blacklist / dynamic country-based list | Build via `POST /crm/v3/lists/` with `processingType: "DYNAMIC"` and a top-level `filterBranch` (same `OR`-of-`AND` shape as workflow filters) — no code action or HubDB needed for a simple enum-membership list. |
| Branch filter: "member of this list" | `filterType: "IN_LIST"` — **not** `"LIST_MEMBERSHIP"`, `"LIST"`, or `"OBJECT_LIST_MEMBERSHIP"` (all rejected; found the correct name from the 400 error body, which lists every valid `filterType`). Full shape: `{"filterType": "IN_LIST", "listId": "<id>", "operator": "IN_LIST"}` — `operator` is **required**; omitting it 400s with "Some required fields were not set: [operator]". Negation: `operator: "NOT_IN_LIST"` (only `IN_LIST`/`NOT_IN_LIST` are valid — confirmed via the 400 body). Use this instead of embedding a country (or any enum) array directly in multiple workflows' branch filters — put the array in one list, reference the list by ID everywhere. Verified July 2026: refactoring workflows from inline `IS_ANY_OF`/`IS_NONE_OF` arrays to `IN_LIST`/`NOT_IN_LIST` against shared lists produced byte-identical branch outcomes (confirmed by adversarial trace), and centralizes the source-of-truth so a later data change means "update the lists," not "find and update the array in every workflow." |
| List name collisions | `POST /crm/v3/lists/` 400s with "list names already exist" if you re-POST an existing name — check first with `POST /crm/v3/lists/search {"query": "<name-prefix>", "count": ...}` (the plain `GET /crm/v3/lists/` list-all endpoint does not reliably return newly created lists for a same-session idempotency check — search does). |

### Workaround for LIST_BRANCH workflows (superseded, see above)

The June 2026 note below described a clone-based workaround on the theory that fresh
LIST_BRANCH POSTs always failed. That premise was disproven in July 2026 — fresh POST
works once the convergence/defaultBranch/IS_UNKNOWN rules above are followed. The
clone approach still works and remains useful for porting an existing complex workflow
(e.g. one with a `CUSTOM_CODE` action) wholesale:

1. **Find or create a workflow** in the HubSpot UI that has at least one IF/THEN branch
2. **Export it**: `GET /automation/v4/flows/{id}` → save to JSON
3. **Strip read-only fields** before POST: `id`, `revisionId`, `createdAt`, `updatedAt`, `insertedAt`, `portalId`, `migrationStatus`, `dataSources`, `crmObjectCreationStatus`, `customProperties`
4. **Replace name and actions** in the stripped payload
5. **POST** the modified payload — succeeds because the workflow type/context is inherited from a real workflow

This is the approach used by `workflow_deployer.py --clone` in this repo. For a workflow
built entirely from `SINGLE_CONNECTION` + `LIST_BRANCH` actions (no code actions), a fresh
POST is simpler and does not require an existing template — see
`<Client>/work/<build-folder>/build/builder.py` for a from-scratch
multi-branch, multi-workflow build using this pattern, including a small
`Flow._auto_goto()` helper that automatically applies the convergence rule.

---

## Minimal Working Example

```python
import requests

workflow = {
    "name": "[OPS] My Workflow",
    "type": "CONTACT_FLOW",
    "flowType": "WORKFLOW",
    "objectTypeId": "0-1",
    "isEnabled": False,
    "startActionId": "1",                  # string, not int
    "nextAvailableActionId": "3",          # string, not int
    "enrollmentCriteria": {
        "shouldReEnroll": False,
        "type": "MANUAL",
    },
    "actions": [
        {
            "actionId": "1",
            "type": "SINGLE_CONNECTION",
            "actionTypeId": "0-5",
            "actionTypeVersion": 0,
            "connection": {"edgeType": "STANDARD", "nextActionId": "2"},
            "fields": {
                "property_name": "lead_source",
                "value": {"staticValue": "Paid (Search)", "type": "STATIC_VALUE"}
            }
        },
        {
            "actionId": "2",
            "type": "SINGLE_CONNECTION",
            "actionTypeId": "0-5",
            "actionTypeVersion": 0,
            # No connection = terminal action
            "fields": {
                "property_name": "lead_source_channel",
                "value": {"staticValue": "Paid", "type": "STATIC_VALUE"}
            }
        }
    ],
    "timeWindows": [],
    "blockedDates": [],
    "suppressionListIds": [],
    "canEnrollFromSalesforce": False,
}

resp = requests.post(
    "https://api.hubapi.com/automation/v4/flows",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json=workflow,
)
print(resp.status_code, resp.json())
```
