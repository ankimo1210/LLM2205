def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_root_contains_app_shell(client):
    resp = client.get("/")
    body = resp.text
    assert 'id="app"' in body
    assert 'id="msg-input"' in body
    assert 'id="send-btn"' in body
    assert '/static/app.js' in body
    assert '/static/styles.css' in body


def test_static_css(client):
    resp = client.get("/static/styles.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]


def test_static_js(client):
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
