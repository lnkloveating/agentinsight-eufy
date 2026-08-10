from fastapi import APIRouter, status

from app.api.dependencies import BriefClarificationServiceDependency
from app.schemas.brief_clarification import (
    BriefClarificationAnswer,
    BriefClarificationSession,
    BriefClarificationStart,
)

router = APIRouter()


@router.post(
    "",
    response_model=BriefClarificationSession,
    status_code=status.HTTP_201_CREATED,
    summary="开始 Research Brief 多轮追问",
    description=(
        "在正式项目创建前保存模糊研究问题，调用所选模型生成动态追问；"
        "后端不会自动补齐隐私、家庭事件或干预授权。"
    ),
)
async def start_clarification(
    payload: BriefClarificationStart,
    service: BriefClarificationServiceDependency,
) -> BriefClarificationSession:
    return await service.start(payload)


@router.get(
    "/{session_id}",
    response_model=BriefClarificationSession,
    summary="读取 Research Brief 追问会话",
)
async def get_clarification(
    session_id: str,
    service: BriefClarificationServiceDependency,
) -> BriefClarificationSession:
    return await service.get(session_id)


@router.post(
    "/{session_id}/messages",
    response_model=BriefClarificationSession,
    summary="回答下一轮 Research Brief 追问",
    description=(
        "保存用户回答，调用模型提取明确字段并生成下一批问题。"
        "仅当完整 ResearchBrief 通过确定性校验后才返回 ready_for_confirmation。"
    ),
)
async def answer_clarification(
    session_id: str,
    payload: BriefClarificationAnswer,
    service: BriefClarificationServiceDependency,
) -> BriefClarificationSession:
    return await service.answer(session_id, payload)
