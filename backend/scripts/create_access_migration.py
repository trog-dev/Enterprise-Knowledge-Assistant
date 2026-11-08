"""Run from backend; creates a migration attached to YOUR current Alembic head."""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def main():
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    revision = "20261107_access_control"

    if any(item.revision == revision for item in scripts.walk_revisions()):
        print("Access migration already exists. Next: python -m alembic upgrade head")
        return

    heads = scripts.get_heads()
    if len(heads) != 1:
        raise SystemExit("Expected one Alembic head. Run: python -m alembic heads")

    destination = Path(scripts.versions) / f"{revision}_access_control.py"
    template = (Path(__file__).parent / "access_migration_template.py").read_text(
        encoding="utf-8"
    )
    content = template.replace('"__CURRENT_HEAD__"', repr(heads[0]))
    # Never overwrite an existing migration.
    with destination.open("x", encoding="utf-8") as output:
        output.write(content)
    print(f"Created migration: {destination}")
    print(f"Parent revision: {heads[0]}")
    print("Review the migration, then run: python -m alembic upgrade head")


if __name__ == "__main__":
    main()
