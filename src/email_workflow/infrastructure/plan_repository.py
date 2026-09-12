from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from email_workflow.infrastructure.models import TestPlan, TestPlanVersion


class PlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_source_email(self, source_email_id: uuid.UUID) -> TestPlan | None:
        statement = select(TestPlan).where(TestPlan.source_email_id == source_email_id)
        return cast(TestPlan | None, await self.session.scalar(statement))

    async def get(self, plan_id: uuid.UUID) -> TestPlan | None:
        return await self.session.get(TestPlan, plan_id)

    async def list_all(self) -> list[TestPlan]:
        statement = select(TestPlan).order_by(TestPlan.updated_at.desc(), TestPlan.id)
        return list((await self.session.scalars(statement)).all())

    async def version(self, plan_id: uuid.UUID, version_number: int) -> TestPlanVersion | None:
        statement = select(TestPlanVersion).where(
            TestPlanVersion.test_plan_id == plan_id,
            TestPlanVersion.version_number == version_number,
        )
        return cast(TestPlanVersion | None, await self.session.scalar(statement))

    async def versions(self, plan_id: uuid.UUID) -> list[TestPlanVersion]:
        statement = (
            select(TestPlanVersion)
            .where(TestPlanVersion.test_plan_id == plan_id)
            .order_by(TestPlanVersion.version_number.desc())
        )
        return list((await self.session.scalars(statement)).all())

    def add(self, plan: TestPlan, version: TestPlanVersion) -> None:
        self.session.add_all((plan, version))
