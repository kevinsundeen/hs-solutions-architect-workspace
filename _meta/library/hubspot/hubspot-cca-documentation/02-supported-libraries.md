# Supported Libraries

Only the libraries listed below are available inside the custom code action runtime. Use them via `require()` (Node.js) or `import` (Python) as described.

---

## Node.js

Load libraries with `require()` at the top of your code.

| Library | Version |
|---------|---------|
| `@hubspot/api-client` | ^10 |
| `async` | ^3.2.0 |
| `aws-sdk` | ^2.744.0 |
| `axios` | ^1.2.0 |
| `lodash` | ^4.17.20 |
| `mongoose` | ^6.8.0 |
| `mysql` | ^2.18.1 |
| `redis` | ^4.5.1 |
| `request` | ^2.88.2 |
| `bluebird` | ^3.7.2 |
| `random-number-csprng` | ^1.0.2 |
| `googleapis` | ^67.0.0 |

**Note:** The v4 Associations API is supported in **@hubspot/api-client** version **9.0.0+** (and in version 8 of the Node.js HubSpot client).

---

## Python

Load libraries with an **import** at the top of your code. Prefer:

`from [libraryname] import [item]`  

Example: `from redis.client import redis`.

| Library | Version |
|---------|---------|
| `requests` | 2.28.2 |
| HubSpot API client | ^8 |
| `google-api-python-client` | 2.74.0 |
| `mysql-connector-python` | 8.0.32 |
| `redis` | 4.4.2 |
| `nltk` | 3.8.1 |

Standard library modules can be used with normal `import`, e.g. `import os`.
