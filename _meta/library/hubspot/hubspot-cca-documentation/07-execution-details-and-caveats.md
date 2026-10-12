# Execution Details and Caveats

## Limitations

Custom code actions must:

| Limit | Value |
|-------|--------|
| **Execution time** | Finish within **20 seconds**. |
| **Memory** | Use no more than **128 MB**. |
| **Test accounts** | Use **OAuth** or a **private app token** (developer API keys are not supported). |

Exceeding time or memory results in an error.

---

## Retries

When your code calls the HubSpot API (or other APIs), you must respect [HubSpot’s API rate limits](https://developers.hubspot.com/developer-tooling/platform/usage-guidelines).

To have HubSpot **retry** the action on rate limiting or certain server errors:

- **Node.js:** In the `catch` block, **re-throw** the error (e.g. `throw err;`).
- **Python:** In the `except` block, **re-raise** the error (e.g. `raise`).

If the failure is due to rate limiting (429) or 5XX from **axios** or **@hubspot/api-client**, HubSpot will retry for **up to three days**, starting one minute after failure, with increasing delays (up to eight hours between attempts).

---

## Node.js caveats

### Random numbers

- **`Math.random()`** can produce the **same** values across executions when many contacts enroll at once, because the runtime may seed it with the same time and state is cleared each run.
- Prefer the **random-number-csprng** (1.0.2) library for cryptographically secure pseudo-random numbers.

### Variable re-use

- Variables declared **outside** `exports.main` may be **reused** across executions (to save memory).
- Put any logic or data that must be **unique per execution** **inside** `exports.main`.

---

## Python caveats

### Variable re-use

- Same idea as Node.js: variables **outside** `def main(event)` can be reused across runs.
- **Read-only:** You can use them as-is.
- **Mutable:** If you need to change a global, declare it with `global` inside `main` before using it.

Example:

```python
a = 1
def main(event):
  global a
  a += 1
```

---

## Summary

- Stay under 20s and 128 MB; use OAuth/private app for test accounts.
- Re-throw (JS) or re-raise (Python) rate limit/5XX errors if you want retries.
- In Node.js, avoid `Math.random()` for per-execution randomness; use `random-number-csprng`.
- Keep execution-specific logic and state inside `main` / `exports.main`; be careful with globals in Python.
