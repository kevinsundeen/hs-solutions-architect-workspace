# Custom Code Action — Code Samples

Reference implementations for HubSpot workflow custom code actions.

| File | Language | Notes |
|------|-----------|--------|
| [sample.js](./sample.js) | Node.js | Uses `@hubspot/api-client`, secrets, `inputFields`, `callback` with `outputFields`. |
| [sample.py](./sample.py) | Python | Same flow using HubSpot Python client, `os.getenv`, and `return { "outputFields": ... }`. |

## Prerequisites in the workflow

For both samples:

1. **Secret:** Add a secret (e.g. private app access token) with the name you use in code (e.g. `SECRET_NAME`). The app must have scopes for the data you read (e.g. `contacts`).
2. **Properties to include in code:** Add at least one property and set its Variable ID to `email` (or match the key you use in code).
3. **Data outputs:** Add outputs named `email` and `phone`, type string.

## Event payload reference

Both samples expect `event` in this shape:

```json
{
  "origin": { "portalId": 1, "actionDefinitionId": 2 },
  "object": { "objectType": "CONTACT", "objectId": 4 },
  "inputFields": { "email": "contact@example.com" },
  "callbackId": "ap-123-456-7-8"
}
```

See [03-setup-and-configuration.md](../03-setup-and-configuration.md) and [04-secrets-and-properties.md](../04-secrets-and-properties.md) for full details.
