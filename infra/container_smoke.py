"""Verify the actual production Nginx/API/DB surface and Docker isolation."""

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit


def verify(base, docker, compose, *, check_btmh_job=False):
    target = urlsplit(base)
    if target.scheme not in ("http", "https") or target.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Security smoke only accepts a loopback HTTP(S) test target")
    checks = []

    def command(*arguments):
        return subprocess.check_output(
            [docker, *arguments], text=True, encoding="utf-8", errors="replace"
        ).strip()

    def request(path, **kwargs):
        # The fixed loopback target was checked above; paths below are code-owned constants.
        return urllib.request.urlopen(urllib.request.Request(base + path, **kwargs), timeout=10)  # noqa: S310

    def not_found(path):
        try:
            request(path)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404, (path, exc.code)
            return
        raise AssertionError(f"Expected 404: {path}")

    assert json.load(request("/api/v1/health/ready"))["status"] == "ready"
    assert json.load(request("/api/v1/health/live"))["status"] == "ok"
    checks.append("Nginx proxies API liveness/readiness")
    response = request("/")
    for header in (
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ):
        assert response.headers.get(header), header
    assert "unsafe-inline" not in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    checks.append("Production CSP and browser security headers")
    for path in (
        "/.env",
        "/.env?raw",
        "/.git/config",
        "/assets/missing.js.map",
        "/api/v1/ingest",
        "/api/v1/openapi.json",
        "/api/v1/docs",
    ):
        not_found(path)
    checks.append("Hidden files, source maps, mutation/admin/docs routes are unavailable")
    latest = json.load(request("/api/v1/quotes/latest?product_id=sjc-bar-1l-hcm"))
    assert latest["data_status"] == "missing" and latest["data"] is None
    exported = request("/api/v1/prices/export.csv?product_id=sjc-bar-1l-hcm&from=2026-11-04&to=2026-11-05")
    assert "text/csv" in exported.headers["Content-Type"]
    checks.append("Empty production database never supplies fabricated quotes; CSV export works")
    payload = json.dumps(
        {
            "quantity": "1",
            "entry_ask": "140000000",
            "world_reference_now": "120000000",
            "world_change_pct": "0",
            "future_premium_pct": "10",
            "future_spread": "3000000",
        }
    ).encode()
    calculation = json.load(
        request("/api/v1/simulations/scenario", data=payload, headers={"Content-Type": "application/json"})
    )
    assert calculation["data"]["net_pnl_vnd"] == "-11000000.0"
    assert calculation["data"]["label"] == "SCENARIO, NOT OBSERVED PRICE"
    checks.append("Decimal scenario calculation works through production proxy")
    identifiers = command(*compose, "ps", "-a", "-q").split()
    assert identifiers, "No Compose containers found"
    services, networks = {}, {}
    for identifier in identifiers:
        info = json.loads(command("inspect", identifier))[0]
        service = info["Config"]["Labels"]["com.docker.compose.service"]
        services[service] = info
        assert info["Config"]["User"].split(":")[0] not in ("", "0", "root"), service
        host = info["HostConfig"]
        assert not host["Privileged"] and host["ReadonlyRootfs"], service
        assert "ALL" in host["CapDrop"] and "no-new-privileges:true" in host["SecurityOpt"], service
        assert host["Memory"] > 0 and host["PidsLimit"] > 0 and host["NanoCpus"] > 0, service
        assert host["NetworkMode"] != "host" and host["PidMode"] != "host", service
        assert not any("docker.sock" in mount["Destination"] for mount in info["Mounts"]), service
        if service in ("db", "api", "worker", "migrate"):
            assert not host["PortBindings"], service
        if service == "migrate":
            assert info["State"]["Status"] == "exited" and info["State"]["ExitCode"] == 0
        else:
            assert info["State"]["Health"]["Status"] == "healthy", service
        for network in info["NetworkSettings"]["Networks"]:
            if network not in networks:
                networks[network] = json.loads(command("network", "inspect", network))[0]
    assert set(services) == {"db", "api", "worker", "migrate", "frontend"}
    assert all(networks[name]["Internal"] for name in services["db"]["NetworkSettings"]["Networks"])
    assert all(networks[name]["Internal"] for name in services["api"]["NetworkSettings"]["Networks"])
    assert not set(services["db"]["NetworkSettings"]["Networks"]) & set(
        services["frontend"]["NetworkSettings"]["Networks"]
    )
    bindings = services["frontend"]["HostConfig"]["PortBindings"]
    assert all(item["HostIp"] == "127.0.0.1" for items in bindings.values() for item in items)
    checks.append("Non-root, read-only, cap-drop, no-new-privileges and resource limits on every service")
    checks.append("Database/API ports private; frontend loopback-only; database/API networks internal")
    checks.append("Migration completed and every long-running service is healthy")
    command(*compose, "exec", "-T", "frontend", "nginx", "-t")
    role = command(
        *compose,
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "from app.db import engine; from sqlalchemy import text; c=engine.connect(); "
        "print(c.execute(text('SELECT current_user')).scalar())",
    )
    assert role == "gold_reader", role
    denied = command(
        *compose,
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "from app.db import engine\nfrom sqlalchemy import text\nfrom sqlalchemy.exc import DBAPIError\n"
        "try:\n with engine.begin() as c: c.execute(text('DELETE FROM data_sources WHERE 1=0'))\n"
        "except DBAPIError: print('write_denied')\nelse: raise SystemExit('API role can write')",
    )
    assert denied == "write_denied", denied
    checks.append("Nginx configuration valid under runtime user; API authenticates as read-only gold_reader")
    if check_btmh_job:
        # Only exercise the disabled job in a dedicated gate project, never on an enabled source.
        worker = services["worker"]
        project = worker["Config"]["Labels"]["com.docker.compose.project"]
        assert project.startswith("gold-") and project.endswith("-gate"), project
        job = subprocess.run(
            [docker, *compose, "exec", "-T", "-e", "VANG_TODAY_ENABLED=false", "worker", "python", "-m",
             "app.jobs.collect_daily", "--source", "btmh"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        output = json.loads(job.stdout)
        assert output["provider_id"] == "vang-today", output
        assert job.returncode == 2 and output.get("error_code") == "source_disabled", output
        latest = json.load(request("/api/v1/quotes/latest?product_id=vang-today-sjl1l10"))
        assert latest["data"] is None and latest["data_status"] == "missing"
        checks.append("Legacy domestic schedule selects Vàng.Today; disabled feed writes no quotes")
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--project-name")
    parser.add_argument("--env-file")
    parser.add_argument("--compose-file", action="append", default=[])
    parser.add_argument("--report", type=Path)
    parser.add_argument("--check-btmh-job", action="store_true")
    args = parser.parse_args()
    compose = ["compose"]
    if args.project_name:
        compose += ["--project-name", args.project_name]
    if args.env_file:
        compose += ["--env-file", args.env_file]
    for file in args.compose_file:
        compose += ["-f", file]
    result = {"checked_at": datetime.now(UTC).isoformat(), "base_url": args.base_url, "passed": False}
    try:
        result["checks"] = verify(args.base_url, args.docker, compose, check_btmh_job=args.check_btmh_job)
        result["passed"] = True
        print(f"Container security smoke: {len(result['checks'])} checks passed")
    finally:
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
