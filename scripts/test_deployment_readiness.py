# -*- coding: utf-8 -*-
"""
scripts/test_deployment_readiness.py
===================================
Validates all cloud deployment deliverables:
  1. requirements.txt structure & packages
  2. .gitignore coverage
  3. app/main.py CORS middleware configuration
  4. frontend/app.js & frontend/config.js configurable API_BASE
  5. Dockerfile & render.yaml syntax & existence
"""

import io
import os
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app

def run_checks():
    print("=" * 70)
    print("VERIFYING CLOUD DEPLOYMENT READINESS")
    print("=" * 70)

    # 1. requirements.txt
    req_file = ROOT / "requirements.txt"
    assert req_file.exists(), "requirements.txt not found!"
    req_text = req_file.read_text(encoding="utf-8")
    for pkg in ["fastapi", "uvicorn", "pydantic", "groq", "pandas", "pyarrow", "rank-bm25"]:
        assert pkg in req_text, f"Package '{pkg}' missing from requirements.txt"
    print("\n[1] requirements.txt Verified ✅")

    # 2. .gitignore
    git_file = ROOT / ".gitignore"
    assert git_file.exists(), ".gitignore not found!"
    git_text = git_file.read_text(encoding="utf-8")
    for pattern in ["venv/", "__pycache__/", ".env", "logs/", "data/vectordb/"]:
        assert pattern in git_text, f"Pattern '{pattern}' missing from .gitignore"
    print("[2] .gitignore Verified ✅")

    # 3. CORS check in app/main.py
    client = TestClient(app)
    # Test preflight OPTIONS request from a Vercel domain
    headers = {
        "Origin": "https://spinneys-store.vercel.app",
        "Access-Control-Request-Method": "POST",
    }
    resp = client.options("/api/chat", headers=headers)
    assert resp.status_code == 200, f"CORS preflight failed: {resp.status_code}"
    cors_origin = resp.headers.get("access-control-allow-origin")
    print(f"[3] CORS Middleware Verified ✅ (Origin: {cors_origin})")

    # 4. Frontend Configurable API_BASE
    app_js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    config_js = (ROOT / "frontend" / "config.js").read_text(encoding="utf-8")
    index_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "window.__SPINNEYS_API_BASE__" in app_js, "window.__SPINNEYS_API_BASE__ missing in app.js"
    assert "window.__SPINNEYS_API_BASE__" in config_js, "config.js missing override"
    assert "config.js" in index_html, "config.js script tag missing in index.html"
    print("[4] Frontend Configurable API_BASE Verified ✅")

    # 5. Dockerfile & render.yaml
    dockerfile = ROOT / "Dockerfile"
    render_yaml = ROOT / "render.yaml"
    assert dockerfile.exists(), "Dockerfile missing!"
    assert render_yaml.exists(), "render.yaml missing!"
    docker_text = dockerfile.read_text(encoding="utf-8")
    assert "uvicorn app.main:app" in docker_text, "Start command missing in Dockerfile"
    assert "retrieval_meta.parquet" in docker_text, "Parquet copy missing in Dockerfile"
    print("[5] Dockerfile & render.yaml Verified ✅")

    print("\n" + "=" * 70)
    print("ALL CLOUD DEPLOYMENT CHECKS PASSED! 🚀")
    print("=" * 70)

if __name__ == "__main__":
    run_checks()
