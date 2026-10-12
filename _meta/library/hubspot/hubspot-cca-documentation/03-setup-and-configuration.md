# Setup and Configuration

## Adding a custom code action to a workflow

1. In HubSpot: **Automation** → **Workflows**.
2. Open a workflow (or create one).
3. Click the **+** (plus) to add an action.
4. In the left panel, search for **Custom code** and select it.

---

## Configuring the custom code action

After adding the action, configure:

| Setting | Description |
|--------|--------------|
| **Language** | Default is **Node.js**. In the Python beta, choose **Python** from the Language dropdown. |
| **Description** | Shown on the workflow action card. |
| **Secret** | Optional. Add a secret (e.g. private app token) for API calls. See [04-secrets-and-properties.md](./04-secrets-and-properties.md). |
| **Properties to include in code** | Map workflow data (properties or formatted values) to variable names used in code. Up to **50 properties**; each Variable ID must be unique. See [04-secrets-and-properties.md](./04-secrets-and-properties.md). |
| **Code** | Your JavaScript or Python. |
| **Data outputs** | Define name and type for each output so later actions (e.g. Edit records) can use them. See [05-data-outputs.md](./05-data-outputs.md). |

**Note:** The code editor does **not** show lint errors when using Python.

---

## Execution contract

- **Node.js:** The `exports.main(event, callback)` function is invoked when the action runs. Call `callback(...)` to return data to the workflow.
- **Python:** The `def main(event):` function is invoked. Return a dict with `outputFields` to send data back.
- **Event:** The `event` argument holds the workflow execution context (see below).

---

## Event object structure

`event` contains at least:

```json
{
  "origin": {
    "portalId": 1,
    "actionDefinitionId": 2
  },
  "object": {
    "objectType": "CONTACT",
    "objectId": 4
  },
  "inputFields": {
  },
  "callbackId": "ap-123-456-7-8"
}
```

| Field | Description |
|-------|-------------|
| `origin.portalId` | Your HubSpot portal ID. |
| `origin.actionDefinitionId` | This custom action’s definition ID. |
| `object.objectType` | CRM object type enrolled in the workflow (e.g. `CONTACT`). |
| `object.objectId` | ID of the enrolled CRM object. |
| `inputFields` | Key-value map of properties you added under “Properties to include in code.” Keys are the **Variable ID** you gave each property. |
| `callbackId` | Unique ID for this execution. |

You use `event.object.objectId` and `event.object.objectType` for API calls, and `event.inputFields` for workflow inputs (see [04-secrets-and-properties.md](./04-secrets-and-properties.md)).
