# Secrets and Properties (Inputs)

## Secrets

Secrets store sensitive values (e.g. [private app access token](https://developers.hubspot.com/apps/legacy-apps/private-apps/overview)) so they are not hard-coded. They are managed in the workflow action definition and exposed as **environment variables** in your code.

### Managing secrets in the UI

- **Add:** Click **Add secret**, then either choose an existing secret or create one (Secret name + Secret value), then Save.
- **Edit/delete:** Click **Manage secrets**.

The private app must have scopes for any data you access (e.g. `contacts`, `forms`).

### Limits

- **Total length** of all secret values for this action must **not exceed 1000 characters**.

### Test accounts

- Use **OAuth** or a **private app token**. Developer API keys do **not** work for test accounts and can produce: *"Authentication credentials not found. This API supports OAuth 2.0 authentication..."*

### Using secrets in code

Secrets are available as environment variables. The variable name is the **Secret name** you configured.

**JavaScript (Node.js):**

```javascript
const hubspotClient = new hubspot.Client({
  accessToken: process.env.SECRET_NAME
});
```

**Python:**

```python
import os
hubspot = HubSpot(access_token=os.getenv('SECRET_NAME'))
```

---

## Properties to include in code (input fields)

Instead of calling the HubSpot API for object properties, you can pass them from the workflow:

1. Under **Properties to include in code**, click **Select a property** and pick a property (or a previously formatted value from the workflow).
2. Set a **Property name** (Variable ID). This is the key you use in code.
3. Add more properties with **Add property** (each Variable ID must be unique; max **50** properties).

These appear on `event.inputFields` in your code.

### Referencing in code

**JavaScript:**

```javascript
const email = event.inputFields['email'];
```

**Python:**

```python
email = event.get('inputFields').get('email')
```

Use the **exact** Variable ID you configured (e.g. `'email'`). Missing or misspelled IDs will be `undefined` (JS) or return from `.get()` as `None` (Python).
