"""Tests for the credentials API route.

Covers:
  - GET /api/credentials — credential status check
  - PUT /api/credentials — update/set credential
  - DELETE /api/credentials/{key} — clear credential
  - Edge cases: unknown key, empty values
"""
import os
from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


class TestCredentialsAPI:
    """Test the /api/credentials endpoints."""

    # --- GET ---

    def test_get_credentials_status(self):
        response = client.get("/api/credentials")
        assert response.status_code == 200
        data = response.json()
        assert "credentials" in data
        creds = data["credentials"]
        # Should have all expected keys
        assert "LLM_API_KEY" in creds
        assert "SEMANTIC_SCHOLAR_API_KEY" in creds
        assert "GOOGLE_SCHOLAR_COOKIE" in creds
        # Each key should have 'configured' and 'preview'
        for key, val in creds.items():
            assert "configured" in val
            assert "preview" in val
            # preview should never be plaintext
            assert isinstance(val["preview"], str)
            if val["configured"] and val["preview"]:
                assert val["preview"].endswith("****")

    def test_get_credentials_configured(self):
        # Temporarily set a key
        os.environ["LLM_API_KEY"] = "sk-test123456"
        try:
            response = client.get("/api/credentials")
            data = response.json()
            assert data["credentials"]["LLM_API_KEY"]["configured"] is True
            assert data["credentials"]["LLM_API_KEY"]["preview"] == "sk-t****"
        finally:
            del os.environ["LLM_API_KEY"]

    def test_get_credentials_not_configured(self):
        # Ensure key is not set
        os.environ.pop("LLM_API_KEY", None)
        response = client.get("/api/credentials")
        data = response.json()
        assert data["credentials"]["LLM_API_KEY"]["configured"] is False

    # --- PUT ---

    def test_put_credential_valid(self):
        response = client.put("/api/credentials", json={
            "key": "LLM_API_KEY",
            "value": "sk-test-new-key",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["key"] == "LLM_API_KEY"

    def test_put_credential_unknown_key(self):
        response = client.put("/api/credentials", json={
            "key": "INVALID_KEY",
            "value": "some-value",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Unknown credential" in data["message"]

    def test_put_credential_empty_value(self):
        response = client.put("/api/credentials", json={
            "key": "LLM_API_KEY",
            "value": "",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"

    # --- DELETE ---

    def test_delete_credential_valid(self):
        # First set a key, then delete it
        client.put("/api/credentials", json={
            "key": "SEMANTIC_SCHOLAR_API_KEY",
            "value": "test-key",
        })
        response = client.delete("/api/credentials/SEMANTIC_SCHOLAR_API_KEY")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cleared"
        assert data["key"] == "SEMANTIC_SCHOLAR_API_KEY"

    def test_delete_credential_unknown_key(self):
        response = client.delete("/api/credentials/INVALID_KEY")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Unknown credential" in data["message"]

    def test_delete_credential_nonexistent(self):
        response = client.delete("/api/credentials/LLM_API_KEY")
        assert response.status_code == 200
