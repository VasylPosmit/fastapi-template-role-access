"""Role access scenarios (Admin / Manager / Member), exercised through the API only.

Each test is named after its scenario ID from the verification catalogue.
Every test depends on the autouse `role_api` fixture: until the role-access backend lands,
they all fail with "ROLE API NOT LANDED" instead of an obscure error.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_email, random_lower_string

USERS = f"{settings.API_V1_STR}/users"
METRICS = f"{settings.API_V1_STR}/metrics/"

Headers = dict[str, str]


@pytest.fixture(scope="module", autouse=True)
def role_api(client: TestClient, superuser_token_headers: Headers) -> None:
    me = client.get(f"{USERS}/me", headers=superuser_token_headers).json()
    if "role" not in me or "permissions" not in me:
        pytest.fail("ROLE API NOT LANDED: GET /users/me has no 'role'/'permissions'")


@pytest.fixture
def make_user(
    client: TestClient, superuser_token_headers: Headers
) -> Callable[[str], tuple[str, Headers]]:
    """Create a user with `role` via the admin API; return (user_id, auth headers)."""

    def _make(role: str) -> tuple[str, Headers]:
        email, password = random_email(), random_lower_string()
        r = client.post(
            f"{USERS}/",
            headers=superuser_token_headers,
            json={"email": email, "password": password},
        )
        assert r.status_code == 200, r.text
        user_id = r.json()["id"]
        r = client.patch(
            f"{USERS}/{user_id}", headers=superuser_token_headers, json={"role": role}
        )
        assert r.status_code == 200 and r.json()["role"] == role, r.text
        return user_id, user_authentication_headers(
            client=client, email=email, password=password
        )

    return _make


def read_user(client: TestClient, admin: Headers, user_id: str) -> dict[str, object]:
    r = client.get(f"{USERS}/{user_id}", headers=admin)
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_access_01_admin_manages_users_and_access(
    client: TestClient,
    superuser_token_headers: Headers,
    make_user: Callable[..., tuple[str, Headers]],
) -> None:
    admin = superuser_token_headers
    user_id, _ = make_user("member")

    r = client.patch(f"{USERS}/{user_id}", headers=admin, json={"role": "manager"})
    assert r.status_code == 200
    r = client.patch(f"{USERS}/{user_id}", headers=admin, json={"is_active": False})
    assert r.status_code == 200
    stored = read_user(client, admin, user_id)
    assert stored["role"] == "manager" and stored["is_active"] is False

    assert client.delete(f"{USERS}/{user_id}", headers=admin).status_code == 200
    assert client.get(f"{USERS}/{user_id}", headers=admin).status_code == 404


def test_access_02_manager_views_users_and_metrics(
    client: TestClient, make_user: Callable[..., tuple[str, Headers]]
) -> None:
    target_id, _ = make_user("member")
    _, manager = make_user("manager")

    assert client.get(f"{USERS}/", headers=manager).status_code == 200
    assert client.get(f"{USERS}/{target_id}", headers=manager).status_code == 200
    assert client.get(METRICS, headers=manager).status_code == 200


def test_access_03_manager_cannot_change_access(
    client: TestClient,
    superuser_token_headers: Headers,
    make_user: Callable[..., tuple[str, Headers]],
) -> None:
    target_id, _ = make_user("member")
    _, manager = make_user("manager")
    before = read_user(client, superuser_token_headers, target_id)

    attempts = [
        client.patch(f"{USERS}/{target_id}", headers=manager, json={"role": "admin"}),
        client.patch(
            f"{USERS}/{target_id}", headers=manager, json={"is_active": False}
        ),
        client.delete(f"{USERS}/{target_id}", headers=manager),
        client.post(
            f"{USERS}/",
            headers=manager,
            json={"email": random_email(), "password": random_lower_string()},
        ),
    ]
    assert [r.status_code for r in attempts] == [403, 403, 403, 403]
    assert read_user(client, superuser_token_headers, target_id) == before


def test_access_04_member_own_profile_only(
    client: TestClient,
    superuser_token_headers: Headers,
    make_user: Callable[..., tuple[str, Headers]],
) -> None:
    member_id, member = make_user("member")

    assert client.get(f"{USERS}/me", headers=member).status_code == 200
    r = client.patch(f"{USERS}/me", headers=member, json={"full_name": "Renamed"})
    assert r.status_code == 200 and r.json()["full_name"] == "Renamed"

    # Privilege fields on /me are silently ignored, never applied.
    r = client.patch(
        f"{USERS}/me", headers=member, json={"role": "admin", "is_active": False}
    )
    assert r.status_code == 200
    stored = read_user(client, superuser_token_headers, member_id)
    assert stored["role"] == "member" and stored["is_active"] is True

    assert client.get(f"{USERS}/", headers=member).status_code == 403
    assert client.get(METRICS, headers=member).status_code == 403


def test_access_05_last_active_admin_is_protected(
    client: TestClient, superuser_token_headers: Headers
) -> None:
    admin = superuser_token_headers
    users = client.get(f"{USERS}/", headers=admin, params={"limit": 10_000}).json()
    active_admins = [
        u for u in users["data"] if u["role"] == "admin" and u["is_active"]
    ]
    assert len(active_admins) == 1, (
        "precondition: the first superuser is the only active admin"
    )
    admin_id = active_admins[0]["id"]

    demote = client.patch(
        f"{USERS}/{admin_id}", headers=admin, json={"role": "manager"}
    )
    deactivate = client.patch(
        f"{USERS}/{admin_id}", headers=admin, json={"is_active": False}
    )
    delete = client.delete(f"{USERS}/{admin_id}", headers=admin)
    # Only the last admin can target itself; the last-admin guard (409) runs first.
    assert (demote.status_code, deactivate.status_code) == (409, 409)
    assert delete.status_code == 403  # template rule: admins can't delete themselves

    stored = read_user(client, admin, admin_id)
    assert stored["role"] == "admin" and stored["is_active"] is True


def test_access_06_unauthenticated_is_401_not_403(client: TestClient) -> None:
    assert client.get(f"{USERS}/me").status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.get(f"{USERS}/me", headers=bad).status_code == 401


@pytest.mark.parametrize("role", ["admin", "manager", "member"])
def test_access_07_me_exposes_role_permissions(
    client: TestClient, make_user: Callable[..., tuple[str, Headers]], role: str
) -> None:
    _, headers = make_user(role)
    me = client.get(f"{USERS}/me", headers=headers).json()
    perms = set(me["permissions"])
    assert me["role"] == role
    if role == "admin":
        assert {
            "users:read",
            "users:write",
            "users:assign_role",
            "metrics:read",
        } <= perms
    elif role == "manager":
        assert {"users:read", "metrics:read"} <= perms
        assert not perms & {"users:write", "users:assign_role"}
    else:
        assert not perms & {
            "users:read",
            "users:write",
            "users:assign_role",
            "metrics:read",
        }


def test_session_01_demotion_applies_to_existing_token(
    client: TestClient,
    superuser_token_headers: Headers,
    make_user: Callable[..., tuple[str, Headers]],
) -> None:
    user_id, old_token = make_user("admin")
    assert client.get(f"{USERS}/", headers=old_token).status_code == 200

    r = client.patch(
        f"{USERS}/{user_id}", headers=superuser_token_headers, json={"role": "member"}
    )
    assert r.status_code == 200
    assert client.get(f"{USERS}/", headers=old_token).status_code == 403


def test_session_02_deactivation_applies_to_existing_token(
    client: TestClient,
    superuser_token_headers: Headers,
    make_user: Callable[..., tuple[str, Headers]],
) -> None:
    user_id, old_token = make_user("manager")
    assert client.get(f"{USERS}/me", headers=old_token).status_code == 200

    r = client.patch(
        f"{USERS}/{user_id}", headers=superuser_token_headers, json={"is_active": False}
    )
    assert r.status_code == 200
    assert client.get(f"{USERS}/me", headers=old_token).status_code == 401
