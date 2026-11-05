"""Run after Compose starts. Verifies the real Nginx/API surface, not a mock server."""
import json
import subprocess
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"


def request(path):
    return urllib.request.urlopen(BASE + path, timeout=10)


def main():
    assert request("/api/v1/health/ready").status == 200
    response = request("/")
    for header in ("Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"):
        assert response.headers.get(header), header
    assert "unsafe-inline" not in response.headers["Content-Security-Policy"]
    for path in ("/.env", "/.env?raw", "/.git/config", "/src/main.ts", "/api/v1/ingest"):
        try:
            result = request(path)
            # SPA fallback can return index for a path, but must never disclose source/config.
            assert path == "/src/main.ts" and b'<!doctype html>' in result.read().lower()
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    latest = json.load(request("/api/v1/quotes/latest?product_id=sjc-bar-1l-hcm"))
    assert latest["data_status"] == "missing" and latest["data"] is None
    exported = request("/api/v1/prices/export.csv?product_id=sjc-bar-1l-hcm&from=2026-11-04&to=2026-11-05")
    assert "text/csv" in exported.headers["Content-Type"]
    identifiers = subprocess.check_output(["docker", "compose", "ps", "-q"], text=True).split()  # noqa: S603,S607
    for identifier in identifiers:
        info = json.loads(subprocess.check_output(["docker", "inspect", identifier], text=True))[0]  # noqa: S603,S607
        assert info["Config"]["User"] not in ("", "0", "root")
        assert not info["HostConfig"]["Privileged"]
        assert info["HostConfig"]["ReadonlyRootfs"]
        service = info["Config"]["Labels"]["com.docker.compose.service"]
        if service in ("db", "api", "worker"):
            assert not info["HostConfig"]["PortBindings"]
    print("Container health, CSP, hidden files, missing data, CSV and isolation checks passed")


if __name__ == "__main__":
    main()
