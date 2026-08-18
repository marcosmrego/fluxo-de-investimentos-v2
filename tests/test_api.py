import base64
import importlib

from fastapi.testclient import TestClient


def _basic(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _load_app(monkeypatch):
    monkeypatch.setenv("DASHBOARD_USERNAME", "investidor")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "segredo-de-teste")
    import dashboard.main as main
    return importlib.reload(main)


def test_financial_api_requires_authentication(monkeypatch):
    main = _load_app(monkeypatch)
    with TestClient(main.app) as client:
        response = client.get("/api/status")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_invalid_credentials_are_rejected(monkeypatch):
    main = _load_app(monkeypatch)
    with TestClient(main.app) as client:
        response = client.get("/", headers=_basic("investidor", "incorreta"))

    assert response.status_code == 401


def test_valid_credentials_allow_dashboard(monkeypatch):
    main = _load_app(monkeypatch)
    with TestClient(main.app) as client:
        response = client.get(
            "/", headers=_basic("investidor", "segredo-de-teste")
        )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_health_is_public_and_does_not_expose_database_errors(monkeypatch):
    main = _load_app(monkeypatch)

    class UnavailableEngine:
        def connect(self):
            raise RuntimeError("secret database hostname")

    monkeypatch.setattr(main, "engine", UnavailableEngine())
    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
    assert "www-authenticate" not in response.headers


def test_startup_rejects_missing_auth_secret(monkeypatch):
    monkeypatch.setenv("DASHBOARD_USERNAME", "investidor")
    # Empty environment value must win over a developer's local .env file.
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    import dashboard.main as main

    try:
        importlib.reload(main)
    except RuntimeError as exc:
        assert "DASHBOARD_PASSWORD" in str(exc)
    else:
        raise AssertionError("app accepted a missing dashboard password")


def test_thesis_inventory_endpoint_returns_real_portfolio_coverage(monkeypatch):
    main = _load_app(monkeypatch)
    expected = {
        "positions": [{"ticker": "CMIN3", "thesis_origin": "TESE_CONTEMPORANEA"}],
        "coverage": {"open_positions": 1, "inventoried_positions": 1},
    }
    monkeypatch.setattr(main, "load_position_thesis_inventory", lambda: expected)

    with TestClient(main.app) as client:
        response = client.get(
            "/api/teses/inventario",
            headers=_basic("investidor", "segredo-de-teste"),
        )

    assert response.status_code == 200
    assert response.json() == expected


def test_publish_thesis_endpoint_validates_and_persists_review(monkeypatch):
    main = _load_app(monkeypatch)
    captured = {}

    def fake_publish(ticker, payload):
        captured.update({"ticker": ticker, "payload": payload})
        return {"ticker": ticker, "status": "PUBLICADA", "versao": 1}

    monkeypatch.setattr(main, "publish_position_thesis", fake_publish)
    payload = {
        "origin": "TESE_ATUAL_RECONSTRUIDA",
        "summary": "Tese revisada manualmente com informacao suficiente para acompanhar.",
        "horizon": "longo prazo",
        "risks": ["Risco material"],
        "review_triggers": ["Mudanca dos fundamentos"],
    }

    with TestClient(main.app) as client:
        response = client.post(
            "/api/teses/BBAS3/publicar",
            json=payload,
            headers=_basic("investidor", "segredo-de-teste"),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "PUBLICADA"
    assert captured["ticker"] == "BBAS3"
    assert captured["payload"]["origin"] == "TESE_ATUAL_RECONSTRUIDA"
