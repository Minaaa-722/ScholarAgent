"""Tests for the credentials API route with keyring-backed storage.

Storage priority:
  1. System keyring (primary) — encrypted, no plaintext file
  2. Process environment variables (explicit, set by user)
  3. .env file (fallback) — lowest priority, documented plaintext risk

All tests mock keyring to avoid depending on real system credential manager.
"""
import os
from unittest.mock import patch
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

CREDENTIAL_KEYS = ["LLM_API_KEY", "SEMANTIC_SCHOLAR_API_KEY", "GOOGLE_SCHOLAR_COOKIE"]


class TestCredentialsAPI:
    """Test the /api/credentials endpoints with keyring-backed storage."""

    # ------------------------------------------------------------------
    # GET /api/credentials — status & preview (never plaintext)
    # ------------------------------------------------------------------

    @patch("keyring.get_password", return_value=None)
    def test_get_credentials_all_not_configured(self, mock_keyring):
        """No key in keyring or environ → all shown as not configured."""
        for key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

        response = client.get("/api/credentials")
        assert response.status_code == 200
        data = response.json()
        assert "credentials" in data

        for key in CREDENTIAL_KEYS:
            info = data["credentials"][key]
            assert info["configured"] is False
            assert info["preview"] == ""

    @patch("keyring.get_password", side_effect=lambda s, k: "sk-real-key-from-keyring" if k == "LLM_API_KEY" else None)
    def test_get_credentials_from_keyring(self, mock_keyring):
        """Key stored in keyring → shown as configured with masked preview."""
        for key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

        response = client.get("/api/credentials")
        data = response.json()
        cred = data["credentials"]["LLM_API_KEY"]

        assert cred["configured"] is True
        assert cred["preview"] == "sk-r****"
        # Verify we actually read from keyring
        mock_keyring.assert_any_call("ScholarAgent", "LLM_API_KEY")

    @patch("keyring.get_password", return_value=None)
    def test_get_credentials_from_environ_fallback(self, mock_keyring):
        """Key not in keyring but in os.environ → shown as configured (fallback)."""
        os.environ["LLM_API_KEY"] = "sk-env-key-12345"

        try:
            response = client.get("/api/credentials")
            data = response.json()
            cred = data["credentials"]["LLM_API_KEY"]

            assert cred["configured"] is True
            assert cred["preview"] == "sk-e****"
        finally:
            del os.environ["LLM_API_KEY"]

    @patch("keyring.get_password", return_value=None)
    def test_get_credentials_preview_never_plaintext(self, mock_keyring):
        """Preview never shows the full key — only first 4 chars + '****'."""
        os.environ["LLM_API_KEY"] = "sk-this-is-a-very-long-secret-key-12345"

        try:
            response = client.get("/api/credentials")
            data = response.json()
            preview = data["credentials"]["LLM_API_KEY"]["preview"]

            # Should be masked
            assert "sk-t" in preview  # first 4 chars
            assert "****" in preview  # masked suffix
            # Should NOT contain the full key
            assert "very-long-secret" not in preview
        finally:
            del os.environ["LLM_API_KEY"]

    @patch("keyring.get_password", return_value=None)
    def test_get_credentials_short_key_preview(self, mock_keyring):
        """Key shorter than 4 chars → preview shows as much as possible + '****'."""
        os.environ["LLM_API_KEY"] = "ab"

        try:
            response = client.get("/api/credentials")
            data = response.json()
            preview = data["credentials"]["LLM_API_KEY"]["preview"]
            assert preview == "ab****"
        finally:
            del os.environ["LLM_API_KEY"]

    # ------------------------------------------------------------------
    # PUT /api/credentials — update/set credential
    # ------------------------------------------------------------------

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value=None)
    def test_put_credential_writes_to_keyring(self, mock_get, mock_set):
        """PUT writes the credential to keyring and sets os.environ."""
        for key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

        response = client.put("/api/credentials", json={
            "key": "LLM_API_KEY",
            "value": "sk-new-key-98765",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["key"] == "LLM_API_KEY"

        # Verify written to keyring
        mock_set.assert_called_with("ScholarAgent", "LLM_API_KEY", "sk-new-key-98765")
        # Verify set in os.environ
        assert os.environ.get("LLM_API_KEY") == "sk-new-key-98765"

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value=None)
    def test_put_credential_unknown_key(self, mock_get, mock_set):
        """PUT with an unknown key returns an error."""
        response = client.put("/api/credentials", json={
            "key": "INVALID_KEY",
            "value": "some-value",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Unknown credential" in data["message"]
        # Should NOT have called keyring for unknown key
        mock_set.assert_not_called()

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value=None)
    def test_put_credential_empty_value(self, mock_get, mock_set):
        """PUT with empty value stores the empty string (allowed)."""
        for key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

        response = client.put("/api/credentials", json={
            "key": "LLM_API_KEY",
            "value": "",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        # Empty value is stored as-is
        mock_set.assert_called_with("ScholarAgent", "LLM_API_KEY", "")

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value=None)
    def test_put_credential_updates_llm_instance(self, mock_get_keyring, mock_set_keyring):
        """PUT LLM_API_KEY should update the runtime LLM instance's api_key."""
        for key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

        # Replace app.state.llm with a mock to verify set_api_key is called
        mock_llm = MagicMock()
        mock_llm.api_key = "sk-old"
        app.state.llm = mock_llm

        response = client.put("/api/credentials", json={
            "key": "LLM_API_KEY",
            "value": "sk-updated-key",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"

        # Verify the endpoint called set_api_key on the LLM instance
        mock_llm.set_api_key.assert_called_once_with("sk-updated-key")

    # ------------------------------------------------------------------
    # DELETE /api/credentials/{key} — clear credential
    # ------------------------------------------------------------------

    @patch("keyring.delete_password")
    @patch("keyring.get_password", return_value="some-key")
    def test_delete_credential_clears_keyring_and_environ(self, mock_get, mock_del):
        """DELETE removes credential from keyring and os.environ."""
        os.environ["LLM_API_KEY"] = "sk-to-delete"

        try:
            response = client.delete("/api/credentials/LLM_API_KEY")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "cleared"
            assert data["key"] == "LLM_API_KEY"

            # Verify removed from keyring
            mock_del.assert_called_with("ScholarAgent", "LLM_API_KEY")
            # Verify removed from os.environ
            assert os.environ.get("LLM_API_KEY") is None
        finally:
            os.environ.pop("LLM_API_KEY", None)

    @patch("keyring.delete_password")
    @patch("keyring.get_password", return_value=None)
    def test_delete_credential_unknown_key(self, mock_get, mock_del):
        """DELETE with an unknown key returns an error."""
        response = client.delete("/api/credentials/INVALID_KEY")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Unknown credential" in data["message"]
        mock_del.assert_not_called()

    @patch("keyring.delete_password")
    @patch("keyring.get_password", return_value=None)
    def test_delete_credential_nonexistent_is_idempotent(self, mock_get, mock_del):
        """DELETE on a key that exists in CREDENTIAL_KEYS but not in storage succeeds."""
        for key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

        response = client.delete("/api/credentials/LLM_API_KEY")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cleared"
        assert data["key"] == "LLM_API_KEY"
        # delete_password may raise if key doesn't exist; handler should catch it
        mock_del.assert_called_with("ScholarAgent", "LLM_API_KEY")

    # ------------------------------------------------------------------
    # Priority: keyring > process env > .env
    # ------------------------------------------------------------------

    @patch("api.routes.credentials._read_from_dotenv", return_value="from-dotenv")
    @patch("keyring.get_password", return_value=None)
    def test_priority_process_env_over_dotenv(self, mock_keyring, mock_dotenv):
        """Process env var takes priority over .env when keyring is empty."""
        os.environ["LLM_API_KEY"] = "from-process-env"
        try:
            response = client.get("/api/credentials")
            data = response.json()
            cred = data["credentials"]["LLM_API_KEY"]
            assert cred["configured"] is True
            assert cred["preview"] == "from****"
        finally:
            del os.environ["LLM_API_KEY"]

    @patch("api.routes.credentials._read_from_dotenv", return_value="from-dotenv")
    @patch("keyring.get_password", side_effect=lambda s, k: "from-keyring")
    def test_priority_keyring_over_dotenv(self, mock_keyring, mock_dotenv):
        """Keyring takes priority over .env when both are configured."""
        for key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

        response = client.get("/api/credentials")
        data = response.json()
        cred = data["credentials"]["LLM_API_KEY"]
        assert cred["configured"] is True
        assert cred["preview"] == "from****"
        mock_keyring.assert_any_call("ScholarAgent", "LLM_API_KEY")

    @patch("api.routes.credentials._read_from_dotenv", return_value="from-dotenv")
    @patch("keyring.get_password", side_effect=lambda s, k: "from-keyring")
    def test_priority_keyring_over_process_env(self, mock_keyring, mock_dotenv):
        """Keyring takes priority over process env when both are set."""
        os.environ["LLM_API_KEY"] = "from-process-env"
        try:
            response = client.get("/api/credentials")
            data = response.json()
            cred = data["credentials"]["LLM_API_KEY"]
            assert cred["configured"] is True
            assert cred["preview"] == "from****"
            mock_keyring.assert_any_call("ScholarAgent", "LLM_API_KEY")
        finally:
            del os.environ["LLM_API_KEY"]

    # ------------------------------------------------------------------
    # GET /api/credentials/init-status — first-run detection
    # ------------------------------------------------------------------

    @patch("api.routes.credentials._read_from_dotenv", return_value=None)
    @patch("keyring.get_password", return_value=None)
    def test_init_status_needs_initialization(self, mock_keyring, mock_dotenv):
        """No credentials in keyring, env, or .env → needs_initialization=true."""
        for key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

        response = client.get("/api/credentials/init-status")
        assert response.status_code == 200
        data = response.json()
        assert data["needs_initialization"] is True

    @patch("api.routes.credentials._read_from_dotenv", return_value="from-dotenv")
    @patch("keyring.get_password", return_value=None)
    def test_init_status_configured_via_dotenv(self, mock_keyring, mock_dotenv):
        """LLM_API_KEY in .env → needs_initialization=false."""
        for key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

        response = client.get("/api/credentials/init-status")
        assert response.status_code == 200
        data = response.json()
        assert data["needs_initialization"] is False

    @patch("api.routes.credentials._read_from_dotenv", return_value=None)
    @patch("keyring.get_password", side_effect=lambda s, k: "sk-from-keyring")
    def test_init_status_configured_via_keyring(self, mock_keyring, mock_dotenv):
        """LLM_API_KEY in keyring → needs_initialization=false."""
        for key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

        response = client.get("/api/credentials/init-status")
        assert response.status_code == 200
        data = response.json()
        assert data["needs_initialization"] is False

    @patch("api.routes.credentials._read_from_dotenv", return_value=None)
    @patch("keyring.get_password", return_value=None)
    def test_init_status_configured_via_process_env(self, mock_keyring, mock_dotenv):
        """LLM_API_KEY in process env → needs_initialization=false."""
        os.environ["LLM_API_KEY"] = "sk-from-process-env"
        try:
            response = client.get("/api/credentials/init-status")
            assert response.status_code == 200
            data = response.json()
            assert data["needs_initialization"] is False
        finally:
            del os.environ["LLM_API_KEY"]