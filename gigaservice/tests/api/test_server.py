"""
Tests for the root server endpoints: GET / and GET /health.
"""


class TestRootEndpoint:
    def test_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_status_is_ok(self, client):
        assert client.get("/").json()["status"] == "ok"

    def test_service_name_present(self, client):
        assert "service" in client.get("/").json()

    def test_content_type_json(self, client):
        resp = client.get("/")
        assert "application/json" in resp.headers["content-type"]


class TestHealthEndpoint:
    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_healthy_is_true(self, client):
        assert client.get("/health").json()["healthy"] is True

    def test_content_type_json(self, client):
        resp = client.get("/health")
        assert "application/json" in resp.headers["content-type"]


class TestCORS:
    def test_cors_header_present(self, client):
        resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert "access-control-allow-origin" in resp.headers

    def test_cors_allows_all_origins(self, client):
        resp = client.get("/health", headers={"Origin": "https://example.com"})
        assert resp.headers.get("access-control-allow-origin") == "*"


class TestOpenAPISchema:
    def test_openapi_json_accessible(self, client):
        assert client.get("/openapi.json").status_code == 200

    def test_openapi_has_correct_title(self, client):
        schema = client.get("/openapi.json").json()
        assert schema["info"]["title"] == "GigaService"

    def test_docs_accessible(self, client):
        assert client.get("/docs").status_code == 200
