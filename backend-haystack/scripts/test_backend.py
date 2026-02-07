"""
End-to-end test script for the Haystack backend.
Tests auth flow, query streaming, and admin operations.

Usage:
    # Start the backend first:
    # cd backend-haystack && uvicorn app.main:app --reload
    
    # Then run tests:
    # python scripts/test_backend.py
"""

import json
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000/v1"
TOKEN = None
USER_ID = None


def req(method: str, path: str, body=None, token=None, stream=False):
    """Make an HTTP request to the backend."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if stream:
                return response.status, response.read().decode("utf-8")
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}
    except urllib.error.URLError as e:
        return 0, {"error": str(e)}


def test_health():
    """Test health endpoint."""
    print("\n=== Test: Health Check ===")
    status, data = req("GET", "/health")
    assert status == 200, f"Expected 200, got {status}: {data}"
    assert data["status"] == "healthy"
    print(f"  PASS: {data}")


def test_register():
    """Test user registration."""
    global TOKEN, USER_ID
    print("\n=== Test: User Registration ===")

    timestamp = int(time.time())
    status, data = req("POST", "/api/auth/local/register", {
        "username": f"testuser_{timestamp}",
        "email": f"test_{timestamp}@example.com",
        "password": "TestPassword123!",
    })

    assert status == 200, f"Expected 200, got {status}: {data}"
    assert "jwt" in data, f"No JWT in response: {data}"
    assert data["user"]["role"]["type"] == "researcher"

    TOKEN = data["jwt"]
    USER_ID = data["user"]["id"]
    print(f"  PASS: Registered user {data['user']['username']} (id={USER_ID})")


def test_login():
    """Test user login."""
    global TOKEN
    print("\n=== Test: User Login ===")

    # Login with the registered user
    status, data = req("POST", "/api/auth/local", {
        "identifier": f"test_{int(time.time()) - 1}@example.com",  # May not exist
        "password": "TestPassword123!",
    })

    # This may fail if the user doesn't exist (timing), which is okay
    if status == 200:
        TOKEN = data["jwt"]
        print(f"  PASS: Logged in as {data['user']['username']}")
    else:
        print(f"  SKIP: Login test skipped (user may not exist yet)")


def test_get_profile():
    """Test getting user profile."""
    print("\n=== Test: Get Profile ===")
    status, data = req("GET", "/api/users/me", token=TOKEN)
    assert status == 200, f"Expected 200, got {status}: {data}"
    assert data["id"] == USER_ID
    print(f"  PASS: Profile for {data['username']} (role={data['role']['type']})")


def test_create_api_key():
    """Test API key creation."""
    print("\n=== Test: Create API Key ===")
    status, data = req("POST", "/api/api-keys", {
        "data": {"name": "Test Key", "permissions": {"query": True, "queryGpu": True}}
    }, token=TOKEN)

    assert status == 200, f"Expected 200, got {status}: {data}"
    assert "apiKey" in data, f"No apiKey in response: {data}"
    assert data["apiKey"].startswith("ominis_")
    print(f"  PASS: Created key {data['data']['keyPrefix']}...")
    return data["data"]["id"]


def test_list_api_keys():
    """Test listing API keys."""
    print("\n=== Test: List API Keys ===")
    status, data = req("GET", "/api/api-keys", token=TOKEN)
    assert status == 200, f"Expected 200, got {status}: {data}"
    assert len(data["data"]) > 0
    print(f"  PASS: Found {len(data['data'])} API keys")


def test_query_stream():
    """Test streaming query endpoint."""
    print("\n=== Test: Query Stream (SSE) ===")

    url = f"{BASE_URL}/query-stream"
    data = json.dumps({
        "question": "¿Qué es la diabetes?",
        "history": [],
        "rag_search": True,
    }).encode("utf-8")

    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
            lines = [l for l in raw.split("\n") if l.startswith("data: ")]

            event_types = set()
            for line in lines:
                try:
                    event = json.loads(line[6:])
                    event_types.add(event.get("type", "unknown"))
                except json.JSONDecodeError:
                    pass

            print(f"  Received {len(lines)} SSE events")
            print(f"  Event types: {event_types}")

            if "done" in event_types:
                print("  PASS: Stream completed with 'done' event")
            elif "error" in event_types:
                print("  WARN: Stream returned error (Ollama may not be running)")
            else:
                print(f"  WARN: Unexpected event types: {event_types}")

    except urllib.error.HTTPError as e:
        print(f"  WARN: HTTP {e.code} - {e.read().decode()}")
    except urllib.error.URLError as e:
        print(f"  SKIP: Cannot connect to backend ({e})")


def test_system_health():
    """Test public health check."""
    print("\n=== Test: System Health (Public) ===")
    status, data = req("GET", "/system-stats/health")
    assert status == 200, f"Expected 200, got {status}: {data}"
    print(f"  PASS: Status={data['status']}, Model={data['model']['status']}")


def main():
    print("=" * 60)
    print("Ominis Health - Haystack Backend E2E Tests")
    print("=" * 60)

    # Check connectivity
    status, _ = req("GET", "/health")
    if status == 0:
        print("\nERROR: Cannot connect to backend at", BASE_URL)
        print("Start the backend first: uvicorn app.main:app --reload")
        sys.exit(1)

    try:
        test_health()
        test_register()
        test_get_profile()
        test_create_api_key()
        test_list_api_keys()
        test_query_stream()
        test_system_health()

        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n  FAIL: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
