"""Isolated ACL tests: SQLite + in-memory Qdrant; no user DB or Gemini calls.

Run ONLY this test file in its own pytest process. Modules for configuration,
embeddings, extraction and Gemini are replaced before importing the routers.
Existing Base, security, DocumentChunk and Conversation models are reused.
"""
import importlib.util
import io
from pathlib import Path
import runpy
import sys
import types
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


def stub(name, **values):
    module = types.ModuleType(name)
    module.__dict__.update(values)
    sys.modules[name] = module
    return module


settings = types.SimpleNamespace(jwt_secret_key="test-secret-" * 8, access_token_expire_minutes=30)
stub("app.core.config", get_settings=lambda: settings)
stub("app.services.embeddings", embed_query=lambda text: [1.0, 0.0],
     embed_passages=lambda texts: [[1.0, 0.0] for text in texts])
vector_stub = stub("app.services.vector_store", COLLECTION_NAME="acl_tests", ensure_collection=lambda: None)
stub("app.services.document_processing", extract_document=lambda *a, **k: ([], []),
     build_document_chunks=lambda units: [])
gemini_stub = stub("app.services.gemini", GeminiError=type("GeminiError", (Exception,), {}))
gemini_stub.generate_answer = lambda **kwargs: None
session_stub = stub("app.db.session", get_db=lambda: None)


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(type_, compiler, **kwargs):
    return "JSON"


from app.db.base import Base
from app.models.department import Department
from app.models.user import User
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.conversation import Conversation, ConversationTurn
from app.core.security import hash_password
from app.api import auth, documents, search, chat, conversations
from app.services.permissions import check_answer_access, sources_are_visible

PASSWORD = "Test-only-password-2026!"
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all([Department(id=1, code="HR", name="Human Resources"),
                    Department(id=2, code="IT", name="IT")])
        db.flush()
        db.add_all([
            User(id=1, email="admin@example.com", full_name="Admin", password_hash=PASSWORD_HASH, role="admin", is_active=True),
            User(id=2, email="hr@example.com", full_name="HR", password_hash=PASSWORD_HASH, role="employee", department_id=1, is_active=True),
            User(id=3, email="it@example.com", full_name="IT", password_hash=PASSWORD_HASH, role="employee", department_id=2, is_active=True),
            User(id=4, email="none@example.com", full_name="No department", password_hash=PASSWORD_HASH, role="employee", is_active=True),
        ])
        db.flush()
        for id_, scope, dept, state in [
            (1, "admin_only", None, "indexed"), (2, "company", None, "indexed"),
            (3, "department", 1, "indexed"), (4, "department", 2, "indexed"),
            (5, "department", 1, "uploaded"), (6, "admin_only", None, "indexed"),
        ]:
            db.add(Document(id=id_, original_name=f"doc{id_}.txt", stored_name=f"stored{id_}.txt",
                            file_size=10, status=state, uploaded_by=1, access_scope=scope, department_id=dept))
        db.flush()
        db.add_all([DocumentChunk(id=i, document_id=i, chunk_index=0, content=f"SECRET_DOC_{i}",
                                 start_char=0, end_char=12) for i in range(1, 7)])
        db.commit()

    vector = QdrantClient(":memory:")
    vector.create_collection("acl_tests", vectors_config=VectorParams(size=2, distance=Distance.COSINE))
    vector.upsert("acl_tests", [PointStruct(id=i, vector=[1.0, 0.0], payload={"document_id": i}) for i in range(1, 7)])
    spy = Mock(wraps=vector.query_points)
    monkeypatch.setattr(vector, "query_points", spy)
    monkeypatch.setattr(search, "ensure_collection", lambda: vector)
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path / "uploads")

    def get_test_db():
        with factory() as db:
            yield db

    app = FastAPI()
    app.dependency_overrides[session_stub.get_db] = get_test_db
    for router in [auth.router, documents.router, search.router, chat.router, conversations.router]:
        app.include_router(router)

    def fake_generate(question, sources):
        # Prefer the department source when available, otherwise a company source.
        chosen = next((s for s in sources if s["source_id"] == "C3"), sources[0])
        return types.SimpleNamespace(sufficient=True, answer=chosen["content"], source_ids=[chosen["source_id"]])

    monkeypatch.setattr(chat, "generate_answer", fake_generate)
    with TestClient(app) as client:
        yield types.SimpleNamespace(client=client, factory=factory, vector=vector, spy=spy, uploads=documents.UPLOAD_DIR)
    vector.close()
    engine.dispose()


def login(client, name):
    response = client.post("/auth/login", data={"username": f"{name}@example.com", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.mark.parametrize("name,expected", [
    ("admin", {1, 2, 3, 4, 5, 6}), ("hr", {2, 3, 5}),
    ("it", {2, 4}), ("none", {2}),
])
def test_document_listing(setup, name, expected):
    response = setup.client.get("/documents", headers=login(setup.client, name))
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == expected


@pytest.mark.parametrize("name,expected", [
    ("admin", {1, 2, 3, 4, 6}), ("hr", {2, 3}), ("it", {2, 4}), ("none", {2}),
])
def test_retrieval_filter_before_vector_search(setup, name, expected):
    response = setup.client.post("/search", headers=login(setup.client, name), json={"question": "test", "top_k": 10})
    assert response.status_code == 200, response.text
    assert {item["document_id"] for item in response.json()} == expected
    condition = setup.spy.call_args.kwargs["query_filter"].must[0]
    assert set(condition.match.any) == expected


def test_empty_access_does_not_call_qdrant_or_llm(setup, monkeypatch):
    with setup.factory() as db:
        document = db.get(Document, 2)
        document.access_scope = "admin_only"
        db.commit()
    generate = Mock()
    monkeypatch.setattr(chat, "generate_answer", generate)
    response = setup.client.post("/chat", headers=login(setup.client, "none"), json={"question": "test"})
    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert response.json()["sufficient"] is False
    setup.spy.assert_not_called()
    generate.assert_not_called()


def test_untrusted_qdrant_result_is_rechecked_in_sql(setup, monkeypatch):
    monkeypatch.setattr(setup.vector, "query_points", lambda **kwargs: types.SimpleNamespace(
        points=[types.SimpleNamespace(id=1, score=1.0)]))
    response = setup.client.post("/search", headers=login(setup.client, "hr"), json={"question": "test"})
    assert response.status_code == 200
    assert response.json() == []


def test_employee_cannot_get_other_department_chunks(setup):
    response = setup.client.get("/documents/4/chunks", headers=login(setup.client, "hr"))
    assert response.status_code == 404
    assert "SECRET_DOC_4" not in response.text


@pytest.mark.parametrize("method,path,body", [
    ("post", "/documents/2/process", None), ("post", "/documents/2/index", None),
    ("patch", "/documents/2/permissions", {"access_scope": "company"}),
    ("post", "/auth/departments", {"code": "OPS", "name": "Operations"}),
    ("post", "/auth/users", {"email": "new@example.com", "full_name": "New", "password": PASSWORD}),
    ("patch", "/auth/users/3", {"is_active": False}),
    ("get", "/auth/users", None),
])
def test_employee_admin_operations_forbidden(setup, method, path, body):
    response = setup.client.request(method, path, headers=login(setup.client, "hr"), json=body)
    assert response.status_code == 403, response.text


def test_employee_upload_forbidden(setup):
    response = setup.client.post("/documents", headers=login(setup.client, "hr"), files={"file": ("a.txt", b"hello")})
    assert response.status_code == 403
    assert not setup.uploads.exists()


def test_upload_defaults_private_and_accepts_explicit_department(setup):
    headers = login(setup.client, "admin")
    response = setup.client.post("/documents", headers=headers, files={"file": ("a.txt", b"hello")})
    assert response.status_code == 201, response.text
    assert response.json()["access_scope"] == "admin_only"
    assert response.json()["department_id"] is None
    response = setup.client.post("/documents", headers=headers,
        files={"file": ("b.txt", b"hello")}, data={"access_scope": "department", "department_id": "1"})
    assert response.status_code == 201, response.text
    assert response.json()["department_id"] == 1


@pytest.mark.parametrize("body", [
    {"access_scope": "department"}, {"access_scope": "department", "department_id": 999},
    {"access_scope": "company", "department_id": 1}, {"access_scope": "public"},
    {"access_scope": "company", "role": "admin"},
])
def test_invalid_document_permissions_rejected(setup, body):
    response = setup.client.patch("/documents/3/permissions", headers=login(setup.client, "admin"), json=body)
    assert response.status_code == 422


def test_acl_change_takes_effect_without_reindexing(setup):
    hr = login(setup.client, "hr")
    response = setup.client.patch("/documents/3/permissions", headers=login(setup.client, "admin"), json={"access_scope": "admin_only"})
    assert response.status_code == 200
    response = setup.client.post("/search", headers=hr, json={"question": "test"})
    assert {item["document_id"] for item in response.json()} == {2}
    # The vector remains stored; only SQL-derived access changed.
    assert setup.vector.count("acl_tests").count == 6


def test_history_redacts_answer_sources_question_and_title_after_revocation(setup):
    headers = login(setup.client, "hr")
    result = setup.client.post("/chat", headers=headers, json={"question": "SECRET_QUESTION"})
    assert result.status_code == 200, result.text
    assert result.json()["answer"] == "SECRET_DOC_3"
    id_ = result.json()["conversation_id"]
    assert setup.client.get(f"/conversations/{id_}/turns", headers=login(setup.client, "it")).status_code == 404
    assert setup.client.get(f"/conversations/{id_}/turns", headers=login(setup.client, "admin")).status_code == 404
    setup.client.patch("/documents/3/permissions", headers=login(setup.client, "admin"), json={"access_scope": "admin_only"})
    response = setup.client.get(f"/conversations/{id_}/turns", headers=headers)
    assert response.status_code == 200
    assert "SECRET_DOC_3" not in response.text
    assert "SECRET_QUESTION" not in response.text
    assert response.json()[0]["sources"] == []
    listing = setup.client.get("/conversations", headers=headers)
    assert "SECRET_QUESTION" not in listing.text
    # Stored data is preserved; only the unauthorized view is redacted.
    with setup.factory() as db:
        assert db.scalar(select(ConversationTurn.answer)) == "SECRET_DOC_3"


def test_gemini_only_receives_visible_sources(setup, monkeypatch):
    seen = []
    def generate(question, sources):
        seen.extend(sources)
        return types.SimpleNamespace(sufficient=True, answer="HR answer", source_ids=["C3"])
    monkeypatch.setattr(chat, "generate_answer", generate)
    response = setup.client.post("/chat", headers=login(setup.client, "hr"), json={"question": "test"})
    assert response.status_code == 200
    assert {source["source_id"] for source in seen} == {"C2", "C3"}


def test_user_management_password_and_live_department_change(setup):
    admin = login(setup.client, "admin")
    created = setup.client.post("/auth/users", headers=admin, json={
        "email": "NEW@EXAMPLE.COM", "full_name": " New employee ",
        "password": PASSWORD, "department_id": 1,
    })
    assert created.status_code == 201, created.text
    assert "password" not in created.text
    user_id = created.json()["id"]
    employee = login(setup.client, "new")
    changed = setup.client.patch(f"/auth/users/{user_id}", headers=admin, json={"department_id": 2})
    assert changed.status_code == 200
    response = setup.client.post("/search", headers=employee, json={"question": "test"})
    assert {item["document_id"] for item in response.json()} == {2, 4}
    setup.client.patch(f"/auth/users/{user_id}", headers=admin, json={"is_active": False})
    assert setup.client.get("/auth/me", headers=employee).status_code == 401
    with setup.factory() as db:
        assert db.get(User, user_id).password_hash != PASSWORD


def test_admin_cannot_be_disabled_by_this_endpoint(setup):
    response = setup.client.patch("/auth/users/1", headers=login(setup.client, "admin"), json={"is_active": False})
    assert response.status_code == 409


def test_null_active_flag_and_empty_user_update_rejected(setup):
    headers = login(setup.client, "admin")
    assert setup.client.patch("/auth/users/2", headers=headers, json={"is_active": None}).status_code == 422
    assert setup.client.patch("/auth/users/2", headers=headers, json={}).status_code == 422


def test_final_access_check_rejects_changed_department(setup):
    with setup.factory() as db:
        user = db.get(User, 2)
        user.department_id = 2
        db.commit()
        with pytest.raises(HTTPException) as error:
            check_answer_access(db, user, {3})
        assert error.value.status_code == 409


@pytest.mark.parametrize("sources", [None, {}, [{"document_id": True}], [{"content": "secret"}], [{"document_id": "3"}]])
def test_malformed_historical_sources_fail_closed(sources):
    assert sources_are_visible(sources, {3}) is False


def test_migration_generates_postgres_sql():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1] / "scripts" / "access_migration_template.py"
    spec = importlib.util.spec_from_file_location("access_template", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        module.upgrade()
    sql = output.getvalue()
    assert "DEFAULT 'admin_only' NOT NULL" in sql
    assert "CREATE TABLE departments" in sql
    assert "ck_documents_scope_department" in sql
    assert "DROP TABLE" not in sql


def test_migration_script_uses_existing_head_and_is_idempotent(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    import shutil
    backend = tmp_path / "backend"
    backend.mkdir()
    config = Config()
    config.config_file_name = str(backend / "alembic.ini")
    config.set_main_option("script_location", str(backend / "migrations"))
    command.init(config, str(backend / "migrations"))
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    # Persist an absolute path to avoid dependency on the fixture's working directory.
    ini = backend / "alembic.ini"
    content = ini.read_text().replace("script_location = ", "script_location = ", 1)
    import re
    ini.write_text(re.sub(r"^script_location\s*=.*$", f"script_location = {backend / 'migrations'}", content, flags=re.M))
    command.revision(Config(str(ini)), message="existing", rev_id="existing_head")
    shutil.copytree(Path(__file__).parents[1] / "scripts", backend / "scripts")
    monkeypatch.chdir(backend)
    script = backend / "scripts" / "create_access_migration.py"
    runpy.run_path(str(script), run_name="__main__")
    runpy.run_path(str(script), run_name="__main__")
    revisions = ScriptDirectory.from_config(Config(str(ini)))
    assert revisions.get_heads() == ["20261107_access_control"]
    assert revisions.get_revision("20261107_access_control").down_revision == "existing_head"
