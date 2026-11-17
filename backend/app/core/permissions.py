"""Access model: roles, permissions, and the table that maps one to the other.

`ROLE_PERMISSIONS` is the single place to change an access rule. The backend
checks it through `require_permission` (app/api/deps.py) and the frontend
receives the same set via `GET /users/me` -> `permissions`.

Rules that depend on *which* record is touched (own profile, own items, the
last active admin) are not permissions; they live next to the endpoint.
"""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


class Permission(StrEnum):
    USERS_READ = "users:read"  # list users, read any user by id
    USERS_WRITE = "users:write"  # create, update (incl. is_active), delete users
    USERS_ASSIGN_ROLE = "users:assign_role"  # set a role other than member
    METRICS_READ = "metrics:read"
    ITEMS_READ_ANY = "items:read_any"  # read items owned by other users
    ITEMS_WRITE_ANY = "items:write_any"  # update/delete items owned by other users
    EMAIL_TEST = "email:test"  # test email, password-recovery HTML preview


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.MANAGER: frozenset({Permission.USERS_READ, Permission.METRICS_READ}),
    Role.MEMBER: frozenset(),
}


def has_permission(role: Role | str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(Role(role), frozenset())
