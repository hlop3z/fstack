## Data Types

- **Structured**: relational, json, xml
- **Unstructured**: text, images, video, logs

## Auth

- **TS**: <https://github.com/authts/oidc-client-ts>
- **PY**: <https://github.com/authlib/authlib>
- **Go**: <https://github.com/coreos/go-oidc>
- **RS**: <https://github.com/ramosbugs/openidconnect-rs>

```
External Traffic
      ↓
Kong Gateway (auth, rate limit, API mgmt)[API product gateway built for business APIs]
      ↓
Envoy (service mesh layer inside cluster)[infrastructure proxy engine]
      ↓
Microservices
```
