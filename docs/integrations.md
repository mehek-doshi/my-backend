# Integrations

Every external system sits behind an interface in `app/integrations/base.py`. Check the current state with `GET /api/v1/admin/integrations`.

> **Honest status.** Nothing below has been run against a real Microsoft 365 tenant or a real Buddy system. The Graph and Teams clients are tested only against mocked HTTP transports.
> `mock` providers exist for tests/development and are refused when `ENVIRONMENT=production`.

| Integration | Interface | Implementations | Status |
|---|---|---|---|
| Microsoft Entra ID (sign-in) | `EntraValidator` | RS256 JWT validation against the tenant JWKS | Unit-tested with locally generated keys. **Not tested against a real tenant.** |
| Directory (hourly sync) | `DirectoryProvider` | `none`, `mock`, `graph` (`GET /users`) | Mocked-transport tests only. Updates names/title/team and deactivates disabled accounts; creates users only if `DIRECTORY_CREATE_USERS=true`. |
| Outlook (mail) | `MailProvider` | `none`, `mock`, `graph` (`POST /users/{sender}/sendMail`) | Mocked-transport tests only. |
| Teams | `TeamsProvider` | `none`, `mock`, `webhook` | Posts to a channel webhook (not to a person). Mocked-transport tests only. |
| SharePoint (every 5 min) | `SharePointProvider` | `none`, `mock`, `graph` (simple upload ≤ 4 MB, upload session above) | Mocked-transport tests only. Only **approved** artifacts are uploaded; failures are stored on the artifact and retried. |
| Buddy | `BuddyProvider` | `none`, `mock` | **Interface only. No real implementation exists**; the API contract of Buddy was not provided. |
| LLM | `LLMProvider` | `mock`, `openai_compatible` (`POST {base}/chat/completions`) | The HTTP client is tested against a mocked transport only. |
| Web search | `SearchProvider` | `none`, `mock` | No real search provider is implemented. |

## Entra ID setup (production sign-in)

1. Register an application; expose an API (audience `api://<client id>`), add the **app role** `TechRadar.Admin` (an old `TechRadar.Moderator` role, if you still have it, also maps to Admin), assign users/groups.
2. Set `AUTH_MODE=entra`, `ALLOW_DEV_AUTH=false`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` (optionally `ENTRA_AUDIENCE`), `ENVIRONMENT=production`.
3. The front end must obtain an access token for that API (MSAL) and send `Authorization: Bearer <token>`.

## Microsoft Graph application permissions (admin consent required)

| Feature | Permission |
|---|---|
| Directory sync | `User.Read.All` |
| Mail | `Mail.Send` (limit it to the sender mailbox with an Exchange application access policy) |
| SharePoint | `Sites.Selected` (preferred) or `Files.ReadWrite.All` |

Set `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` (a secret, keep it out of source control), `MAIL_SENDER`, `SHAREPOINT_DRIVE_ID`, `TEAMS_WEBHOOK_URL`, then switch the matching `*_PROVIDER` to `graph` / `webhook`.
If a required value is missing the provider falls back to `none`, the reason is shown in `/admin/integrations`, and the related job is recorded as `skipped` (not failed).

## Adding a real provider

Implement the Protocol in `base.py`, raise `NotConfigured` when settings are missing and `IntegrationError` on call failures, register it in `registry.py`, and add tests with a mocked transport.
