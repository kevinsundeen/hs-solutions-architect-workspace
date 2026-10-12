# Data Outputs

Data outputs let you pass values from your custom code to **later workflow actions** (e.g. **Edit records**) without a separate API call to write properties.

---

## Defining outputs in the UI

1. Under **Data outputs**, click **Add output**.
2. Choose **Data type** (e.g. number, string, boolean, datetime, enum, date, phone number).
3. Enter the **Name** for the output (must match the key you use in code).
4. Add more outputs with **Add output** as needed.

Outputs you return in code must be **declared here** with matching names and types; otherwise they cannot be used in later actions.

---

## Returning outputs in code

### JavaScript (Node.js)

Use the **callback** and pass an object with an `outputFields` object. Call `callback` from within `exports.main`.

```javascript
callback({
  outputFields: {
    email: email,
    phone: phone
  }
});
```

Data is not sent to the workflow until the event loop drains; code after `callback()` can still run.

### Python

Return a dict with an `"outputFields"` key from `main(event)`:

```python
return {
  "outputFields": {
    "email": email,
    "phone": phone
  }
}
```

---

## Output rules and limits

- **String length:** Each string output is limited to **65,000 characters**. Larger values cause an `OUTPUT_VALUES_TOO_LARGE` error.
- **Edit records:** When mapping CCA outputs to properties, follow [compatible source and target properties](https://knowledge.hubspot.com/workflows/compatible-source-and-target-properties-for-copying-property-values-in-workflows) for copying values.

### Date and datetime properties

- **Datetime property:** Output must be in **UNIX time in milliseconds**.
- **Date-only property:** Output must be in **UNIX time in milliseconds** with the time set to **midnight UTC**.

Example (JavaScript) for a date at midnight UTC:

```javascript
currentDate.setUTCHours(0, 0, 0, 0);
// then use the timestamp in milliseconds for the output
```

Use the same numeric (milliseconds) value in your `outputFields` when updating date/datetime properties via Edit records.
