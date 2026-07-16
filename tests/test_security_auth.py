import pytest
import secrets
from unittest.mock import patch
from fastapi.testclient import TestClient

def test_token_comparison_uses_compare_digest():
    """Verify that the auth middleware uses secrets.compare_digest."""
    import server.main as main_module
    import inspect
    source = inspect.getsource(main_module.sidecar_token_auth)
    assert "compare_digest" in source, "Token comparison should use secrets.compare_digest"

def test_shutdown_requires_auth():
    """Verify /shutdown is not in unauthenticated_paths."""
    import server.main as main_module
    import inspect
    source = inspect.getsource(main_module.sidecar_token_auth)
    # /shutdown should NOT be in the unauthenticated_paths set
    assert '"/shutdown"' not in source.split('unauthenticated_paths')[1].split('}')[0], \
        "/shutdown should require authentication"
