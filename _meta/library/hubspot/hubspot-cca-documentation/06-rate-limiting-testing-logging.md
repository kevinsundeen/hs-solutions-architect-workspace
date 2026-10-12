# Rate Limiting, Testing, and Logging

## Rate limiting

You can limit how often the custom code action runs. The limit applies to **this action** and to **all actions that follow it** in the workflow.

### Configuring rate limit

1. In the workflow editor, click the **custom code action**.
2. At the bottom, open **Configure rate limit**.
3. Turn **Turn on rate limiting** on.
4. Set **Action executions** (max runs per period) and **Time frame** (Seconds, Minutes, or Hours).

When the limit is hit, the action does not run. In the [workflow action logs](https://knowledge.hubspot.com/workflows/understand-your-workflow-details-page#action-logs) you’ll see:

*This action has been paused to stay within the configured rate limit. It will resume on [date and time].*

---

## Testing the action

Test the custom code action before turning the workflow on. The test runs **only** this action (no other workflow steps). You pick a record and run the code; then you see outputs and logs.

**Important:** The test runs against a **real** record. Any changes your code makes (API calls, etc.) **will apply** to that record. Use a dedicated test record to avoid affecting live data.

### How to test

1. Click the **custom code action** in the workflow.
2. At the bottom, expand **Test action**.
3. In **Object**, choose the **record** to run against.
4. If the action uses formatted property values from the workflow, enter **test value(s)** for them.
5. Click **Test**, then confirm in the dialog.
6. Review:
   - **Status** — success or failure.
   - **Data outputs** — values for each defined output. If the code returns an output that isn’t declared in Data outputs, an alert is shown; add that output in the UI to use it later.
   - **Logs** — e.g. memory and runtime.
7. Click **Save** when done.

---

## Logging

After the workflow is on, logs from the custom code action appear in the workflow’s **action logs**. Use them to debug behavior in production.

See: [Understand your workflow details page — Action logs](https://knowledge.hubspot.com/workflows/understand-your-workflow-details-page#action-logs).
