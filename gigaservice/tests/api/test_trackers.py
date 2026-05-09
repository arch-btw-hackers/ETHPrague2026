"""
API contract tests for /trackers CRUD endpoints.
"""
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# conftest.py mock_swarm patches api.packages / api.sensors but not
# api.trackers — add tracker-specific patches here via a dedicated fixture.
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_trackers(monkeypatch):
    """In-memory Swarm + index for tracker endpoints."""
    store: dict[str, dict] = {}
    counter = [0]
    index: dict[str, dict] = {}

    async def _upload(data: dict) -> str:
        counter[0] += 1
        h = format(counter[0], "064x")
        store[h] = data
        return h

    async def _download(ref: str) -> dict:
        if ref not in store:
            raise Exception(f"ref {ref} not found")
        return store[ref]

    async def _get_entry(key: str):
        return index.get(key)

    async def _set_entry(key: str, **fields):
        index.setdefault(key, {}).update(fields)

    async def _read_index():
        return dict(index)

    async def _delete_entry(key: str):
        index.pop(key, None)

    monkeypatch.setattr("api.trackers.upload_json", _upload)
    monkeypatch.setattr("api.trackers.download_json", _download)
    monkeypatch.setattr("api.trackers.get_device_entry", _get_entry)
    monkeypatch.setattr("api.trackers.set_device_entry", _set_entry)
    monkeypatch.setattr("api.trackers._read_index", _read_index)
    monkeypatch.setattr("api.trackers.delete_device_entry", _delete_entry)

    return {"store": store, "index": index}


@pytest.fixture()
def tracker_payload():
    return {
        "tracker_id": "trk-001",
        "name": "Warehouse Alpha",
        "description": "Cold chain tracker",
        "owner": "logistics-team",
    }


# ---------------------------------------------------------------------------
# POST /trackers/
# ---------------------------------------------------------------------------

class TestCreateTracker:
    def test_returns_201(self, client, mock_trackers, tracker_payload):
        resp = client.post("/trackers/", json=tracker_payload)
        assert resp.status_code == 201

    def test_response_shape(self, client, mock_trackers, tracker_payload):
        body = client.post("/trackers/", json=tracker_payload).json()
        assert body["tracker_id"] == tracker_payload["tracker_id"]
        assert body["name"] == tracker_payload["name"]
        assert body["description"] == tracker_payload["description"]
        assert body["owner"] == tracker_payload["owner"]
        assert "meta_hash" in body

    def test_meta_stored_in_swarm(self, client, mock_trackers, tracker_payload):
        resp = client.post("/trackers/", json=tracker_payload)
        h = resp.json()["meta_hash"]
        assert mock_trackers["store"][h]["name"] == tracker_payload["name"]

    def test_duplicate_returns_409(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        resp = client.post("/trackers/", json=tracker_payload)
        assert resp.status_code == 409

    def test_defaults_for_optional_fields(self, client, mock_trackers):
        resp = client.post("/trackers/", json={"tracker_id": "trk-min", "name": "Minimal"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["description"] == ""
        assert body["owner"] == ""

    def test_missing_tracker_id_returns_422(self, client, mock_trackers):
        resp = client.post("/trackers/", json={"name": "X"})
        assert resp.status_code == 422

    def test_missing_name_returns_422(self, client, mock_trackers):
        resp = client.post("/trackers/", json={"tracker_id": "trk-x"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /trackers/
# ---------------------------------------------------------------------------

class TestListTrackers:
    def test_empty_list(self, client, mock_trackers):
        resp = client.get("/trackers/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_created_tracker(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        body = client.get("/trackers/").json()
        assert len(body) == 1
        assert body[0]["tracker_id"] == tracker_payload["tracker_id"]

    def test_returns_multiple_trackers(self, client, mock_trackers):
        for i in range(3):
            client.post("/trackers/", json={"tracker_id": f"trk-{i}", "name": f"Tracker {i}"})
        body = client.get("/trackers/").json()
        assert len(body) == 3

    def test_list_response_shape(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        item = client.get("/trackers/").json()[0]
        for key in ("tracker_id", "name", "description", "owner", "meta_hash"):
            assert key in item


# ---------------------------------------------------------------------------
# GET /trackers/{tracker_id}
# ---------------------------------------------------------------------------

class TestGetTracker:
    def test_returns_200_after_create(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        resp = client.get(f"/trackers/{tracker_payload['tracker_id']}")
        assert resp.status_code == 200

    def test_response_contains_correct_data(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        body = client.get(f"/trackers/{tracker_payload['tracker_id']}").json()
        assert body["name"] == tracker_payload["name"]
        assert body["owner"] == tracker_payload["owner"]

    def test_unknown_tracker_returns_404(self, client, mock_trackers):
        resp = client.get("/trackers/ghost")
        assert resp.status_code == 404

    def test_404_detail_mentions_tracker_id(self, client, mock_trackers):
        body = client.get("/trackers/ghost").json()
        assert "ghost" in body["detail"]


# ---------------------------------------------------------------------------
# PUT /trackers/{tracker_id}
# ---------------------------------------------------------------------------

class TestUpdateTracker:
    def test_returns_200(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        resp = client.put(f"/trackers/{tracker_payload['tracker_id']}", json={"name": "Updated"})
        assert resp.status_code == 200

    def test_name_updated(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        body = client.put(f"/trackers/{tracker_payload['tracker_id']}", json={"name": "New Name"}).json()
        assert body["name"] == "New Name"

    def test_description_updated(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        body = client.put(f"/trackers/{tracker_payload['tracker_id']}", json={"description": "New desc"}).json()
        assert body["description"] == "New desc"

    def test_owner_updated(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        body = client.put(f"/trackers/{tracker_payload['tracker_id']}", json={"owner": "new-owner"}).json()
        assert body["owner"] == "new-owner"

    def test_partial_update_preserves_other_fields(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        body = client.put(f"/trackers/{tracker_payload['tracker_id']}", json={"name": "Changed"}).json()
        # description and owner should be unchanged
        assert body["description"] == tracker_payload["description"]
        assert body["owner"] == tracker_payload["owner"]

    def test_empty_update_preserves_all_fields(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        body = client.put(f"/trackers/{tracker_payload['tracker_id']}", json={}).json()
        assert body["name"] == tracker_payload["name"]

    def test_update_returns_new_meta_hash(self, client, mock_trackers, tracker_payload):
        resp1 = client.post("/trackers/", json=tracker_payload)
        old_hash = resp1.json()["meta_hash"]
        resp2 = client.put(f"/trackers/{tracker_payload['tracker_id']}", json={"name": "Changed"})
        assert resp2.json()["meta_hash"] != old_hash

    def test_unknown_tracker_returns_404(self, client, mock_trackers):
        resp = client.put("/trackers/ghost", json={"name": "X"})
        assert resp.status_code == 404

    def test_get_reflects_updated_data(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        client.put(f"/trackers/{tracker_payload['tracker_id']}", json={"name": "Post-Update"})
        body = client.get(f"/trackers/{tracker_payload['tracker_id']}").json()
        assert body["name"] == "Post-Update"


# ---------------------------------------------------------------------------
# DELETE /trackers/{tracker_id}
# ---------------------------------------------------------------------------

class TestDeleteTracker:
    def test_returns_204(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        resp = client.delete(f"/trackers/{tracker_payload['tracker_id']}")
        assert resp.status_code == 204

    def test_get_returns_404_after_delete(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        client.delete(f"/trackers/{tracker_payload['tracker_id']}")
        assert client.get(f"/trackers/{tracker_payload['tracker_id']}").status_code == 404

    def test_list_empty_after_delete(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        client.delete(f"/trackers/{tracker_payload['tracker_id']}")
        assert client.get("/trackers/").json() == []

    def test_unknown_tracker_returns_404(self, client, mock_trackers):
        resp = client.delete("/trackers/ghost")
        assert resp.status_code == 404

    def test_delete_only_removes_target(self, client, mock_trackers):
        client.post("/trackers/", json={"tracker_id": "trk-a", "name": "A"})
        client.post("/trackers/", json={"tracker_id": "trk-b", "name": "B"})
        client.delete("/trackers/trk-a")
        remaining = client.get("/trackers/").json()
        assert len(remaining) == 1
        assert remaining[0]["tracker_id"] == "trk-b"

    def test_recreate_after_delete(self, client, mock_trackers, tracker_payload):
        client.post("/trackers/", json=tracker_payload)
        client.delete(f"/trackers/{tracker_payload['tracker_id']}")
        # Should be possible to re-register the same tracker_id
        resp = client.post("/trackers/", json=tracker_payload)
        assert resp.status_code == 201
