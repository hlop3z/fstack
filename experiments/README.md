Build a complete, working **docker-compose-based local development setup** that integrates:

- **Zitadel (OIDC Identity Provider)**
- **Kong Gateway (API Gateway)**
- A simple **sample backend API service (e.g., Node.js or Python FastAPI)**

## Kong:

- DB-less mode (no database required)

### Requirements:

1. The system must be fully runnable with:

   ```bash
   docker-compose up
   ```

2. Zitadel must be configured as an **OIDC provider** with:
   - A pre-created application (client_id + client_secret)
   - Authorization Code flow enabled
   - Correct redirect URIs for Kong or test client
3. Kong must be configured to:
   - Use the **OIDC plugin (or JWT validation if simpler)**
   - Trust Zitadel as the identity provider
   - Protect the sample API route (`/api/*`)
4. Provide a **sample API service**:
   - Exposes `/api/hello`
   - Returns JSON `{ "message": "hello world" }`
5. Include:
   - Full `docker-compose.yml`
   - Kong configuration (declarative config or DB-less mode)
   - Zitadel setup instructions (or bootstrap config if possible)
   - Environment variables for all secrets
6. Authentication flow must work like:
   - User logs in via Zitadel
   - Receives access token (JWT)
   - Calls Kong with `Authorization: Bearer <token>`
   - Kong validates token with Zitadel issuer
   - Request is forwarded to backend API
7. Include:
   - Step-by-step run instructions
   - Example `curl` request with token flow
   - Troubleshooting section (common OIDC misconfig issues)

### Constraints:

- Must work locally (no cloud dependencies required)
- Prefer minimal setup complexity
- Use official Docker images where possible
- Avoid enterprise-only Kong features unless necessary

### Output format:

- Project folder structure first
- Then full file contents
- Then setup instructions
- Then authentication flow explanation

---
