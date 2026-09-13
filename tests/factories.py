from __future__ import annotations

from email_workflow.domain.plan import ExtractionPayload


def make_extraction_payload(evidence_id: str = "evidence-0001") -> ExtractionPayload:
    def text(value: str = "") -> dict[str, object]:
        return {"value": value, "evidence_ids": [evidence_id] if value else []}

    def values(items: list[str] | None = None) -> dict[str, object]:
        return {
            "values": items or [],
            "evidence_ids": [evidence_id] if items else [],
        }

    return ExtractionPayload.model_validate(
        {
            "plan_name": text(),
            "project_name": text("Atlas"),
            "project_code": text("ATLAS"),
            "requirement_ids": values(["REQ-101"]),
            "test_type": text("功能"),
            "test_stage": text("system"),
            "test_round": text("第一轮"),
            "priority": text("P1"),
            "test_version": text("1.0"),
            "planned_start_date": text("2026-09-15"),
            "planned_end_date": text("2026-09-20"),
            "objective": text("验证通信主链路"),
            "scope": text("通信领域功能"),
            "environment": text("测试环境 A"),
            "risks": values(["网络抖动"]),
            "dependencies": values(["测试 SIM 卡"]),
            "notes": text(),
            "open_questions": [],
            "details": [
                {
                    "domain_key": text("通信测试"),
                    "owner_name": text("王芳"),
                    "owner_employee_id": text("001234567"),
                    "execution_start_date": text(),
                    "execution_end_date": text(),
                    "scope": text("验证入网与重连"),
                    "requirements": [
                        {"text": "设备断网后应自动重连", "evidence_ids": [evidence_id]}
                    ],
                    "test_cases": [
                        {
                            "title": text("断网重连"),
                            "objective": text("验证自动重连"),
                            "preconditions": values(["设备已入网"]),
                            "steps": [{"step_number": 1, "action": "断开并恢复网络"}],
                            "test_data": text(),
                            "expected_result": text("设备自动恢复连接"),
                            "priority": text("高"),
                            "evidence_ids": [evidence_id],
                            "provenance": "source",
                            "open_questions": [],
                        }
                    ],
                    "unresolved_fields": [],
                }
            ],
        }
    )
