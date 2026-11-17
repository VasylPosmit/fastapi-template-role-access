"""Rehearse the role migration against a populated throwaway database.

Run from backend/:  uv run python scripts/rehearse_role_migration.py

Uses its own database (app_migration_rehearsal) in the same Postgres server as
DATABASE_URL; never touches the app or test databases. Proves the migration by
reading facts back, not by alembic's exit code.
"""

import logging
import os
import subprocess
import sys
import uuid
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rehearsal")
Snapshot = dict[str, Any]

REHEARSAL_DB = "app_migration_rehearsal"
BASELINE_REVISION = "fe56fa70289e"  # last revision before role access
# PR1 ships two revisions on top of BASELINE_REVISION, in this order:
# 1) schema: add user.role VARCHAR NOT NULL server_default 'member'
# 2) data: role = 'admin' where is_superuser (+ admin count == superuser count guard)
# PR2 adds 3) drop: remove user.is_superuser (downgrade restores it from role).
# Read from backend/app/alembic/versions/ so the script needs no edit when they land.


def role_revisions() -> tuple[str | None, str | None, str | None]:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    newer = [
        rev.revision
        for rev in scripts.iterate_revisions("heads", BASELINE_REVISION)
        if rev.revision != BASELINE_REVISION
    ]
    newer.reverse()  # oldest first
    padded = [*newer, None, None, None]
    return padded[0], padded[1], padded[2]


ROLE_SCHEMA_REVISION, ROLE_REVISION, DROP_SUPERUSER_REVISION = role_revisions()

# Representative population: every superuser/active combination, with items.
SEED_USERS = [
    # (email, is_superuser, is_active, item_count)
    ("admin.active@rehearsal.test", True, True, 2),
    ("admin.inactive@rehearsal.test", True, False, 1),
    ("member.active@rehearsal.test", False, True, 3),
    ("member.inactive@rehearsal.test", False, False, 1),
    ("member.no-items@rehearsal.test", False, True, 0),
]

server_url = make_url(str(settings.DATABASE_URL))
rehearsal_url = server_url.set(database=REHEARSAL_DB)


def admin_engine() -> Engine:
    return create_engine(
        server_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )


def alembic(*args: str) -> None:
    env = {
        **os.environ,
        "DATABASE_URL": rehearsal_url.render_as_string(hide_password=False),
    }
    subprocess.run(["alembic", *args], check=True, env=env)
    logger.info(f"  alembic {' '.join(args)}: ok")


def create_db() -> None:
    with admin_engine().connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{REHEARSAL_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{REHEARSAL_DB}"'))
    logger.info(f"created {REHEARSAL_DB}")


def drop_db() -> None:
    with admin_engine().connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{REHEARSAL_DB}" WITH (FORCE)'))
    logger.info(f"dropped {REHEARSAL_DB}")


def seed() -> None:
    # Raw SQL against the baseline schema: ORM models describe the *new* schema.
    with create_engine(rehearsal_url).begin() as conn:
        for email, is_superuser, is_active, item_count in SEED_USERS:
            user_id = uuid.uuid4()
            conn.execute(
                text(
                    'INSERT INTO "user" (id, email, is_active, is_superuser, '
                    "full_name, hashed_password, created_at) "
                    "VALUES (:id, :email, :active, :su, :name, 'not-a-real-hash', now())"
                ),
                {
                    "id": user_id,
                    "email": email,
                    "active": is_active,
                    "su": is_superuser,
                    "name": email,
                },
            )
            for n in range(item_count):
                conn.execute(
                    text(
                        "INSERT INTO item (id, title, owner_id, created_at) "
                        "VALUES (:id, :title, :owner, now())"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "title": f"{email} item {n}",
                        "owner": user_id,
                    },
                )
    logger.info(f"seeded {len(SEED_USERS)} users")


def has_column(conn: Connection, column: str) -> bool:
    return (
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'user' AND column_name = :column"
            ),
            {"column": column},
        ).first()
        is not None
    )


def snapshot() -> Snapshot:
    """Privilege-relevant facts, keyed by email, plus row counts."""
    with create_engine(rehearsal_url).connect() as conn:
        has_role = has_column(conn, "role")
        has_superuser = has_column(conn, "is_superuser")
        role_col = "u.role" if has_role else "NULL"
        su_col = "u.is_superuser" if has_superuser else "NULL"
        users = conn.execute(
            text(
                f"SELECT u.email, {su_col} AS is_superuser, u.is_active, "
                f"{role_col} AS role, count(i.id) AS items "
                'FROM "user" u LEFT JOIN item i ON i.owner_id = u.id '
                "GROUP BY u.email, 2, u.is_active, 4 ORDER BY u.email"
            )
        ).all()
    return {
        "has_role": has_role,
        "has_superuser": has_superuser,
        "users": {
            r.email: {
                "is_superuser": r.is_superuser,
                "is_active": r.is_active,
                "items": r.items,
                "role": r.role,
            }
            for r in users
        },
        "user_count": len(users),
        "item_count": sum(r.items for r in users),
    }


def compare(
    label: str,
    baseline: Snapshot,
    now: Snapshot,
    role_rule: str | None,
    expect_superuser: bool = True,
) -> bool:
    """Read-back check: pre-migration facts survive and role follows role_rule.

    role_rule: None = no role column; "member" = schema step only, everyone member;
    "backfill" = admin iff is_superuser, else member.
    expect_superuser: False once PR2's drop step has removed user.is_superuser.
    """
    expect_role = role_rule is not None
    errors = []
    if now["has_role"] != expect_role:
        errors.append(f"role column present={now['has_role']}, expected {expect_role}")
    if now["has_superuser"] != expect_superuser:
        errors.append(
            f"is_superuser present={now['has_superuser']}, expected {expect_superuser}"
        )
    for key in ("user_count", "item_count"):
        if baseline[key] != now[key]:
            errors.append(f"{key} {baseline[key]} -> {now[key]}")
    for email, before in baseline["users"].items():
        after = now["users"].get(email)
        if after is None:
            errors.append(f"{email} missing")
            continue
        facts = (
            ("is_superuser", "is_active", "items")
            if expect_superuser
            else ("is_active", "items")
        )
        for fact in facts:
            if before[fact] != after[fact]:
                errors.append(f"{email} {fact} {before[fact]} -> {after[fact]}")
        if expect_role:
            expected = (
                "admin"
                if role_rule == "backfill" and before["is_superuser"]
                else "member"
            )
            if after["role"] != expected:
                errors.append(f"{email} role={after['role']!r}, expected {expected!r}")
    if role_rule == "backfill":
        admins = sum(u["role"] == "admin" for u in now["users"].values())
        superusers = sum(u["is_superuser"] for u in baseline["users"].values())
        if admins != superusers:
            errors.append(
                f"admin count {admins} != pre-migration superuser count {superusers}"
            )
    for e in errors:
        logger.info(f"  ❌ {label}: {e}")
    logger.info(
        f"  {'✅' if not errors else '❌'} {label}: {now['user_count']} users, {now['item_count']} items"
    )
    return not errors


def main() -> int:
    logger.info(
        f"revisions: baseline={BASELINE_REVISION} schema={ROLE_SCHEMA_REVISION} "
        f"data={ROLE_REVISION} drop={DROP_SUPERUSER_REVISION}"
    )
    create_db()
    try:
        alembic("upgrade", BASELINE_REVISION)
        seed()
        baseline = snapshot()
        logger.info(
            f"baseline: {baseline['user_count']} users, {baseline['item_count']} items"
        )
        results = [
            compare("read-back at baseline", baseline, snapshot(), role_rule=None)
        ]
        if ROLE_SCHEMA_REVISION is None or ROLE_REVISION is None:
            logger.info("⏳ role revisions not set: skipping upgrade/downgrade/upgrade")
        else:
            alembic("upgrade", ROLE_SCHEMA_REVISION)
            results.append(
                compare("after schema step", baseline, snapshot(), role_rule="member")
            )
            alembic("upgrade", ROLE_REVISION)
            upgraded = snapshot()
            results.append(
                compare("after data step", baseline, upgraded, role_rule="backfill")
            )
            alembic("downgrade", ROLE_SCHEMA_REVISION)
            results.append(
                compare(
                    "after data-step downgrade",
                    baseline,
                    snapshot(),
                    role_rule="member",
                )
            )
            alembic("upgrade", ROLE_REVISION)
            alembic("downgrade", BASELINE_REVISION)
            results.append(
                compare("after downgrade", baseline, snapshot(), role_rule=None)
            )
            alembic("upgrade", ROLE_REVISION)
            reupgraded = snapshot()
            results.append(
                compare("after re-upgrade", baseline, reupgraded, role_rule="backfill")
            )
            same = reupgraded == upgraded
            logger.info(
                f"  {'✅' if same else '❌'} re-upgrade identical to first upgrade"
            )
            results.append(same)
            if DROP_SUPERUSER_REVISION is None:
                logger.info("⏳ no drop step yet (PR2): skipping is_superuser removal")
            else:
                results += rehearse_drop_step(baseline)
        return 0 if all(results) else 1
    finally:
        drop_db()


def rehearse_drop_step(baseline: Snapshot) -> list[bool]:
    """PR2: drop is_superuser, then prove downgrade rebuilds it from role."""
    assert DROP_SUPERUSER_REVISION and ROLE_REVISION
    alembic("upgrade", DROP_SUPERUSER_REVISION)
    dropped = compare(
        "after drop step",
        baseline,
        snapshot(),
        role_rule="backfill",
        expect_superuser=False,
    )
    alembic("downgrade", ROLE_REVISION)
    restored = compare(
        "after drop-step downgrade", baseline, snapshot(), role_rule="backfill"
    )
    alembic("upgrade", DROP_SUPERUSER_REVISION)
    return [dropped, restored]


if __name__ == "__main__":
    sys.exit(main())
