from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_workflow.infrastructure.models import TestPlan, TestPlanVersion
from email_workflow.infrastructure.plan_repository import PlanRepository


@dataclass(frozen=True, slots=True)
class PlanSnapshot:
    plan: TestPlan
    version: TestPlanVersion


class PlanQueryService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list_plans(self) -> list[TestPlan]:
        async with self.session_factory() as session:
            return await PlanRepository(session).list_all()

    async def get(self, plan_id: uuid.UUID) -> PlanSnapshot | None:
        async with self.session_factory() as session:
            repository = PlanRepository(session)
            plan = await repository.get(plan_id)
            if plan is None:
                return None
            version = await repository.version(plan_id, plan.current_version)
            if version is None:
                raise RuntimeError("计划当前版本不存在")
            return PlanSnapshot(plan=plan, version=version)

    async def versions(self, plan_id: uuid.UUID) -> list[TestPlanVersion] | None:
        async with self.session_factory() as session:
            repository = PlanRepository(session)
            if await repository.get(plan_id) is None:
                return None
            return await repository.versions(plan_id)

    async def version(self, plan_id: uuid.UUID, version_number: int) -> TestPlanVersion | None:
        async with self.session_factory() as session:
            return await PlanRepository(session).version(plan_id, version_number)
