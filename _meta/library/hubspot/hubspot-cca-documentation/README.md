# HubSpot Custom Code Actions (CCA) — Documentation

This folder contains reference documentation for **HubSpot Workflow Custom Code Actions**. Use it when building or debugging custom code actions in HubSpot workflows (Operations Hub Professional or Enterprise).

**Source:** [HubSpot Developers — Workflows | Custom Code Actions](https://developers.hubspot.com/docs/api-reference/automation-actions-v4-v4/custom-code-actions)

---

## Contents

| Document | Description |
|----------|-------------|
| [01-overview-and-requirements.md](./01-overview-and-requirements.md) | What CCA is, account requirements, runtime, example use cases, support |
| [02-supported-libraries.md](./02-supported-libraries.md) | Node.js and Python libraries available in the CCA runtime |
| [03-setup-and-configuration.md](./03-setup-and-configuration.md) | Adding a CCA to a workflow, configuration options, event object structure |
| [04-secrets-and-properties.md](./04-secrets-and-properties.md) | Secrets (env vars), HubSpot properties / input fields, limits |
| [05-data-outputs.md](./05-data-outputs.md) | Defining and returning outputs (callback/return), types, Edit records, date handling |
| [06-rate-limiting-testing-logging.md](./06-rate-limiting-testing-logging.md) | Rate limits, testing the action, and viewing logs |
| [07-execution-details-and-caveats.md](./07-execution-details-and-caveats.md) | Time/memory limits, retries, Node.js and Python caveats |
| [code-samples/](./code-samples/) | Reference JavaScript and Python samples (see also project root: `Workflow CCA sample.js`, `Workflow CCA sample.py`) |

---

## Quick reference

- **Entry point:** `exports.main(event, callback)` (Node.js) or `def main(event):` (Python).
- **Inputs:** Configure “Properties to include in code”; use `event.inputFields['propertyName']` (JS) or `event.get('inputFields').get('propertyName')` (Python).
- **Secrets:** Stored in workflow action; read via `process.env.SECRET_NAME` (JS) or `os.getenv('SECRET_NAME')` (Python).
- **Outputs:** `callback({ outputFields: { ... } })` (JS) or `return { "outputFields": { ... } }` (Python).
- **Limits:** 20s execution, 128 MB memory, string output ≤ 65,000 characters; total secret length &lt; 1000 characters.

For full details and caveats, see the documents above and the official HubSpot CCA page.
