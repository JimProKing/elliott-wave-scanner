#!/usr/bin/env python3
"""Render API로 웹 서비스 생성/배포 (RENDER_API_KEY 필요)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = "https://api.render.com/v1"
REPO = "https://github.com/JimProKing/elliott-wave-scanner"
SERVICE_NAME = "elliott-focused-viewer"
ROOT_DIR = "focused_viewer"


def _api(method: str, path: str, payload: dict | None = None) -> dict:
    key = os.environ.get("RENDER_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "RENDER_API_KEY 환경변수가 필요합니다.\n"
            "Render 대시보드 → Account Settings → API Keys 에서 발급 후:\n"
            "  set RENDER_API_KEY=rnd_xxxx\n"
            "  python deploy_render.py"
        )

    data = None
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Render API 오류 {e.code}: {err}") from e


def _find_owner_id() -> str:
    owners = _api("GET", "/owners?limit=20")
    if not owners:
        raise SystemExit("Render workspace를 찾을 수 없습니다.")
    return owners[0]["owner"]["id"]


def _find_existing_service(owner_id: str) -> dict | None:
    services = _api("GET", f"/services?ownerId={owner_id}&limit=50")
    for item in services:
        svc = item.get("service", {})
        if svc.get("name") == SERVICE_NAME or svc.get("slug") == SERVICE_NAME:
            return svc
    return None


def create_service(owner_id: str) -> dict:
    payload = {
        "type": "web_service",
        "name": SERVICE_NAME,
        "ownerId": owner_id,
        "repo": REPO,
        "branch": "main",
        "rootDir": ROOT_DIR,
        "autoDeploy": "yes",
        "serviceDetails": {
            "env": "python",
            "envSpecificDetails": {
                "buildCommand": "pip install -r requirements-web.txt",
                "startCommand": "gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180",
            },
            "healthCheckPath": "/api/status",
            "plan": "free",
            "region": "oregon",
        },
        "envVars": [
            {"key": "PYTHON_VERSION", "value": "3.11"},
            {"key": "WEB_DEPLOY", "value": "1"},
            {"key": "MPLBACKEND", "value": "Agg"},
            {"key": "BINANCE_API_BASE", "value": "https://data-api.binance.vision"},
            {"key": "DISABLE_SCAN", "value": "0"},
        ],
    }
    return _api("POST", "/services", payload)


def trigger_deploy(service_id: str) -> dict:
    return _api("POST", f"/services/{service_id}/deploys", {"clearCache": "do_not_clear"})


def main() -> int:
    print("Render 배포 시작...")
    owner_id = _find_owner_id()
    print(f"Workspace ID: {owner_id}")

    existing = _find_existing_service(owner_id)
    if existing:
        service_id = existing["id"]
        print(f"기존 서비스 발견: {existing.get('name')} ({service_id})")
        print(f"URL: {existing.get('serviceDetails', {}).get('url', '배포 후 생성')}")
        result = trigger_deploy(service_id)
        deploy_id = result.get("id", "unknown")
        print(f"재배포 트리거 완료: deploy {deploy_id}")
        print(f"대시보드: {existing.get('dashboardUrl')}")
        return 0

    result = create_service(owner_id)
    service = result.get("service", result)
    url = service.get("serviceDetails", {}).get("url")
    dashboard = service.get("dashboardUrl")
    deploy_id = result.get("deployId")
    print("서비스 생성 완료!")
    if url:
        print(f"URL: {url}")
    if dashboard:
        print(f"대시보드: {dashboard}")
    if deploy_id:
        print(f"Deploy ID: {deploy_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())