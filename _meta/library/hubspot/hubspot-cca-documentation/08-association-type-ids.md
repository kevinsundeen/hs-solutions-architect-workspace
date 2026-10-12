# HubSpot CRM Association Type IDs (Reference)

This file documents HubSpot's **HUBSPOT_DEFINED association type IDs** for standard CRM objects, for use with the v4 associations API (including the [Create Default](https://developers.hubspot.com/docs/api-reference/crm-associations-v4/basic/put-crm-v4-objects-fromObjectType-fromObjectId-associations-default-toObjectType-toObjectId) endpoint).

> Note: For many workflows, you can use the v4 **default association** endpoint without specifying an explicit association type ID. These IDs are most useful when you need fine‑grained control over association directions or non‑default types.

## Subscription ↔ Company (example POC)

- **Type ID `297`** — Subscription to company  
- **Type ID `298`** — Company to subscription

For an entitlements POC, we treat each HubSpot **subscription** record as an entitlement and associate it to the owning **company**. In most cases we can rely on the v4 **default association** endpoint between `subscription` and `company`, but if we ever need to specify association specs manually, use the IDs above.

## Selected association type IDs by object

The full list below is copied from HubSpot's association reference for quick lookup.

### Company to object

- `450` — Company to company  
- `14` — Child to parent company  
- `13` — Parent to child company  
- `280` — Company to contact  
- `2` — Company to primary contact  
- `930` — Company to billing contact  
- `342` — Company to deal  
- `6` — Primary company to deal  
- `340` — Company to ticket  
- `25` — Primary company to ticket  
- `181` — Company to call  
- `185` — Company to email  
- `611` — Company to lead  
- `187` — Company to meeting  
- `189` — Company to note  
- `191` — Company to task  
- `88` — Company to communication (SMS, WhatsApp, or LinkedIn message)  
- `460` — Company to postal mail  
- `180` — Company to invoice  
- `935` — Company to order  
- `510` — Primary company to order  
- `390` — Company to payment  
- `472` — Company to payment link  
- `72` — Company to quote  
- `1335` — Billing company to quote  
- `298` — Company to subscription  
- `909` — Company to appointment  
- `939` — Company to course  
- `885` — Company to listing  
- `793` — Company to service  
- `929` — Company to feedback submission  
- `1237` — Company to project  

### Subscription to object

- `295` — Subscription to contact  
- `297` — Subscription to company  
- `299` — Subscription to deal  
- `1121` — Subscription to ticket  
- `623` — Subscription to invoice  
- `301` — Subscription to line item  
- `303` — Subscription to quote  
- `478` — Subscription to payment link  
- `515` — Subscription to order  
- `1174` — Subscription to feedback submission  

---

The source for these IDs is HubSpot's developer documentation for v4 associations:  
- [Create Default association](https://developers.hubspot.com/docs/api-reference/crm-associations-v4/basic/put-crm-v4-objects-fromObjectType-fromObjectId-associations-default-toObjectType-toObjectId)  
- Associations guide and related pages linked from that document.

