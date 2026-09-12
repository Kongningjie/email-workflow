from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from email_workflow.core.logging import configure_logging

configure_logging("INFO")
app = FastAPI(title="Mock 测试管理平台", version="0.1.0")


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="mock-gateway")
