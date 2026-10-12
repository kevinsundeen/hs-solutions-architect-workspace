# Custom Code Actions — Overview and Requirements

## What are Custom Code Actions?

**Custom code actions** let you write and run **JavaScript** or **Python** (beta) inside HubSpot workflows. They run as a **Custom code** workflow action and extend what you can do in automation (inside and outside HubSpot).

- **JavaScript** runs on the [Node.js runtime](https://docs.aws.amazon.com/lambda/latest/dg/lambda-nodejs.html).
- **Python** runs on the [Python runtime](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html).

Execution is handled by HubSpot via **AWS Lambda** (serverless).

---

## Account requirements

- **Operations Hub** — **Professional** or **Enterprise**.
- Custom code actions are not available on other tiers.

---

## Example use cases

From [HubSpot's Programmable Automation Use Cases Library](https://www.hubspot.com/data-hub-use-cases):

- Weighted lead rotation with custom weights  
- Formatting international phone numbers  
- Archiving or deleting contacts  
- Deduplicating contacts  
- Completing all tasks for a closed deal  

Use the use-case library for more examples and patterns.

---

## Support and troubleshooting

- **Product / setup issues:** [HubSpot support](https://knowledge.hubspot.com/help-and-resources/get-help-with-hubspot).
- **Code / implementation issues:** [HubSpot Developer Forum](https://community.hubspot.com/t5/HubSpot-Developers/ct-p/developers) — search and post there for help with your code.
