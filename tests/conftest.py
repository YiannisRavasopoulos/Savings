import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.main import create_app

PASSWORD = "correct horse battery"


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def app(data_dir):
    return create_app(env={"APP_DATA_DIR": str(data_dir)}, run_backups=False)


@pytest.fixture
def conn(app):
    c = db.connect(app.state.cfg.db_path)
    yield c
    c.close()


def make_user(conn, username, password=PASSWORD, status="active", display_name=None, seed=True):
    """Create a user directly in the database (as the admin app would) and return its id."""
    with conn:
        cur = conn.execute(
            "INSERT INTO users (username, display_name, password_hash, status) VALUES (?, ?, ?, ?)",
            (username, display_name or username.title(), auth.hash_password(password), status))
        if seed:
            db.seed_user(conn, cur.lastrowid)
    return cur.lastrowid


def browser(app) -> TestClient:
    """A client that behaves like a browser on our own pages (sends a same-site Origin)."""
    return TestClient(app, headers={"Origin": "http://testserver"})


def login(client, username, password=PASSWORD):
    r = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return client


@pytest.fixture
def uid(conn):
    return make_user(conn, "alice")


@pytest.fixture
def client(app, uid):
    return login(browser(app), "alice")


def category_id(conn, name, user_id=None):
    if user_id is None:
        user_id = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]
    return conn.execute("SELECT id FROM categories WHERE name = ? AND user_id = ?", (name, user_id)).fetchone()[0]


def add_budget(conn, category_id, cents, effective_from, user_id=None):
    """A budget entry for a category, owned by `user_id` (default: the category's owner)."""
    if user_id is None:
        user_id = conn.execute("SELECT user_id FROM categories WHERE id = ?", (category_id,)).fetchone()[0]
    conn.execute("INSERT INTO category_budgets (category_id, user_id, monthly_budget_cents, effective_from) "
                 "VALUES (?, ?, ?, ?)", (category_id, user_id, cents, effective_from))
