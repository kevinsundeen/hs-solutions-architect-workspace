# HubSpot API Reference & Documentation

## Official Documentation Links

### Core APIs
- **REST API:** https://developers.hubspot.com/docs/api/overview
- **GraphQL API:** https://developers.hubspot.com/docs/api/graphql
- **Webhooks:** https://developers.hubspot.com/docs/api/webhooks

### Custom Code Actions (CCA)
- **Main Documentation:** https://developers.hubspot.com/docs/api-reference/automation-actions-v4-v4/custom-code-actions
- **Use Cases Library:** https://www.hubspot.com/data-hub-use-cases
- **Developer Forum:** https://community.hubspot.com/t5/HubSpot-Developers/ct-p/developers

### Workflows
- **Workflow API:** https://developers.hubspot.com/docs/api-reference/automation-actions-v4-v4/workflows
- **Custom Code Actions:** See `_meta/hubspot-cca-documentation/` for detailed CCA reference
- **v4 Flows API — tested constraints & examples:** See `_meta/hubspot-workflow-api.md` (reverse-engineered from sandbox, June 2026)

## Common Patterns

### Custom Code Actions (CCA)

**Entry Point:**
- JavaScript: `exports.main(event, callback)`
- Python: `def main(event):`

**Accessing Input Properties:**
- JavaScript: `event.inputFields['propertyName']`
- Python: `event.get('inputFields').get('propertyName')`

**Secrets/Environment Variables:**
- JavaScript: `process.env.SECRET_NAME`
- Python: `os.getenv('SECRET_NAME')`

**Outputs:**
- JavaScript: `callback({ outputFields: { ... } })`
- Python: `return { "outputFields": { ... } }`

**Limits:**
- Execution time: 20 seconds
- Memory: 128 MB
- String output: ≤ 65,000 characters
- Total secret length: < 1000 characters

### Rate Limits
- **Private Apps:** 100 requests per 10 seconds per app
- **OAuth Apps:** Varies by tier
- **Bulk Operations:** Use batch endpoints when possible

### Common Use Cases
- Mapping Salesforce User IDs to HubSpot users
- Formatting international phone numbers
- Weighted lead rotation
- Data transformation and validation
- Custom notifications and alerts

## Detailed CCA Documentation

For comprehensive Custom Code Actions documentation, see:
- `_meta/hubspot-cca-documentation/README.md` - Overview and quick reference
- `_meta/hubspot-cca-documentation/01-overview-and-requirements.md` - Requirements and use cases
- `_meta/hubspot-cca-documentation/02-supported-libraries.md` - Available libraries
- `_meta/hubspot-cca-documentation/03-setup-and-configuration.md` - Setup guide
- `_meta/hubspot-cca-documentation/04-secrets-and-properties.md` - Configuration
- `_meta/hubspot-cca-documentation/05-data-outputs.md` - Output handling
- `_meta/hubspot-cca-documentation/06-rate-limiting-testing-logging.md` - Testing and debugging
- `_meta/hubspot-cca-documentation/07-execution-details-and-caveats.md` - Limitations and gotchas
- `_meta/hubspot-cca-documentation/code-samples/` - Reference code examples

## Best Practices

1. **Always test in a test workflow** before deploying to production
2. **Handle errors gracefully** - CCA failures can break workflows
3. **Use batch operations** when processing multiple records
4. **Respect rate limits** - implement retry logic with exponential backoff
5. **Log important operations** - use console.log/print for debugging
6. **Keep code simple** - 20s execution limit means complex operations may timeout
7. **Validate inputs** - check for null/undefined values before processing

## Common Gotchas

- User-type properties require HubSpot user objects, not raw IDs
- Date handling varies between JavaScript and Python
- String concatenation can hit 65k character limit
- Secrets are shared across all workflow actions in an account
- Custom code actions run in isolated Lambda environments
