# Full Stack FastAPI Template

## Role-based access (Ender Turing test task)

Adds Admin / Manager / Member access levels on top of the existing template.

**Time spent:** about 1 hour (15:00–16:04), plus a final review pass.

**Run and test:** unchanged, see [development.md](./development.md). One extra, optional command rehearses the migration on a throwaway database (upgrade, downgrade, re-upgrade, with a read-back check after each step):

```bash
cd backend && uv run python scripts/rehearse_role_migration.py
```

**Try all three roles locally.** With `FASTAPI_ENV=development` (the default `.env`), `scripts/prestart.sh` seeds:

| Account | Role | Password |
| --- | --- | --- |
| `admin@example.com` (`FIRST_SUPERUSER`) | Admin | `FIRST_SUPERUSER_PASSWORD` |
| `manager@example.com` | Manager | same |
| `member@example.com` | Member | same |

Never deploy with `FASTAPI_ENV=development`: it also seeds these accounts (and already enables the template's unauthenticated `/private` routes).

**Where access rules live.** [`backend/app/core/permissions.py`](./backend/app/core/permissions.py): `ROLE_PERMISSIONS` maps each role to its permissions. Endpoints declare `require_permission(Permission.X)`; the frontend reads the same set from `GET /users/me` → `permissions`.

| | Admin | Manager | Member |
| --- | :-: | :-: | :-: |
| Own profile, password, own items | yes | yes | yes |
| List and view users (`users:read`) | yes | yes | no |
| Create, edit, deactivate, delete users (`users:write`) | yes | no | no |
| Change a user's role (`users:assign_role`) | yes | no | no |
| Metrics stub (`metrics:read`) | yes | yes | no |
| Other users' items (`items:read_any`, `items:write_any`) | yes | no | no |
| Test email, recovery-email preview (`email:test`) | yes | no | no |

**Assumptions**

- Migration maps `is_superuser = true` to Admin and everyone else to Member; nobody becomes Manager by migration. The upgrade aborts if the result disagrees with `is_superuser`.
- `is_superuser` stays for now, kept equal to `role == admin` on every write, so the previous code version still works against the migrated database. It is dropped in a follow-up change.
- Role and active status are read from the database on every request (never from the token), so changes apply to existing sessions on their next request.
- 401 means the session is no longer valid (bad token, deleted or deactivated user) and logs the user out; 403 means not allowed and keeps the session.
- At least one active admin must remain (409). Users cannot change their own role or deactivate themselves (403). Admins cannot delete themselves (as in the template).
- Signup always creates a Member; role fields sent to `/users/me` or signup are ignored.
- Admin keeps seeing all users' items, as superusers did. Manager sees only their own items.
- Old app instances are stopped before the migration runs. An old instance that keeps writing users afterwards would not set `role`.

**AI conversations:** raw exports in [`ai-conversations/`](./ai-conversations/).

[![Test Docker Compose](../../actions/workflows/test-docker-compose.yml/badge.svg)](../../actions/workflows/test-docker-compose.yml)
[![Test Backend](../../actions/workflows/test-backend.yml/badge.svg)](../../actions/workflows/test-backend.yml)

## Technology Stack and Features

- ⚡ [**FastAPI**](https://fastapi.tiangolo.com) for the Python backend API.
  - 🧰 [SQLModel](https://sqlmodel.tiangolo.com) for the Python SQL database interactions (ORM).
  - 🔍 [Pydantic](https://docs.pydantic.dev), used by FastAPI, for the data validation and settings management.
  - 💾 [PostgreSQL](https://www.postgresql.org) as the SQL database.
- 🚀 [React](https://react.dev) for the frontend.
  - 🧩 Built into the backend application and served by FastAPI on the same domain as the API.
  - 💃 Using TypeScript, hooks, [Vite](https://vitejs.dev), and other parts of a modern frontend stack.
  - 🎨 [Tailwind CSS](https://tailwindcss.com) and [shadcn/ui](https://ui.shadcn.com) for the frontend components.
  - 🤖 An automatically generated frontend client.
  - 🧪 [Playwright](https://playwright.dev) for end-to-end testing.
  - 🦇 Dark mode support.
- ☁️ [FastAPI Cloud](https://fastapicloud.com) for deployment.
- 🐋 [Docker Compose](https://www.docker.com) for local services and self-hosted deployment.
  - 📞 [Traefik](https://traefik.io) as a reverse proxy with automatic HTTPS.
- 🔒 Secure password hashing by default.
- 🔑 JWT (JSON Web Token) authentication.
- 📫 Email-based password recovery.
- ✉️ [React Email](https://react.email) for email templates.
- 📬 [Mailpit](https://mailpit.axllent.org) for local email testing during development.
- ✅ Tests with [Pytest](https://pytest.org).
- 🏭 CI (continuous integration) and CD (continuous deployment) based on GitHub Actions.

### Dashboard Login

![Dashboard login screenshot](img/login.png)

### Dashboard - Admin

![Admin dashboard screenshot](img/dashboard.png)

### Dashboard - Items

![Items dashboard screenshot](img/dashboard-items.png)

### Dashboard - Dark Mode

![Dark mode dashboard screenshot](img/dashboard-dark.png)

### React Email Templates

![Email templates screenshot](img/react-email.png)

### Mailpit - Local Email Testing

![Mailpit screenshot](img/mailpit.png)

### Interactive API Documentation

![API docs](img/docs.png)

## How to Use It

Click the **Use this template** button at the top of this page to create a new repository.

## Backend Development

Backend docs: [backend/README.md](./backend/README.md).

## Frontend Development

Frontend docs: [frontend/README.md](./frontend/README.md).

## Deployment

FastAPI Cloud deployment: [deployment.md](./deployment.md).

Self-hosted deployment with Docker Compose: [deployment-docker-compose.md](./deployment-docker-compose.md).

## Development

General development docs: [development.md](./development.md).

This includes the local FastAPI and Vite workflow, Docker Compose services, `.env` configuration, and more.

## Release Notes

Check the file [release-notes.md](./release-notes.md).

## License

The Full Stack FastAPI Template is licensed under the terms of the MIT license.
