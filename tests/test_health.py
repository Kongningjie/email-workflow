from pathlib import Path

from fastapi.testclient import TestClient

from email_workflow.core.config import Settings
from email_workflow.core.errors import AppError
from email_workflow.main import create_app
from mock_gateway.main import app as gateway_app


def test_main_health_has_request_id(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        config_dir=Path("config"),
        data_dir=tmp_path,
        frontend_dist_dir=tmp_path / "frontend",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health", headers={"X-Request-Id": "test-request"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "email-workflow"}
    assert response.headers["X-Request-Id"] == "test-request"


def test_gateway_health() -> None:
    with TestClient(gateway_app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "mock-gateway"


def test_safe_error_envelope_contains_request_id(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        config_dir=Path("config"),
        data_dir=tmp_path,
        frontend_dist_dir=tmp_path / "frontend",
    )
    test_app = create_app(settings)

    @test_app.get("/test-error")
    async def raise_safe_error() -> None:
        raise AppError(code="test_error", message="安全错误消息", status_code=409)

    with TestClient(test_app) as client:
        response = client.get("/test-error", headers={"X-Request-Id": "error-request"})
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "test_error",
            "message": "安全错误消息",
            "field": None,
            "request_id": "error-request",
        }
    }


def test_spa_fallback_does_not_hide_unknown_api_route(tmp_path: Path) -> None:
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text(
        "<!doctype html><title>测试计划前端</title>", encoding="utf-8"
    )
    settings = Settings(
        app_env="test",
        config_dir=Path("config"),
        data_dir=tmp_path / "data",
        frontend_dist_dir=frontend_dir,
    )
    with TestClient(create_app(settings)) as client:
        page_response = client.get("/plans")
        api_response = client.get("/api/v1/missing", headers={"X-Request-Id": "missing-request"})
    assert page_response.status_code == 200
    assert "测试计划前端" in page_response.text
    assert api_response.status_code == 404
    assert api_response.json()["error"] == {
        "code": "not_found",
        "message": "资源不存在",
        "field": None,
        "request_id": "missing-request",
    }
