"""已确认竞品候选来源接入用例。"""

from app.application.competitor_source_onboarding.processing_dispatcher import (
    CompetitorSourceProcessingDispatcher,
)
from app.application.competitor_source_onboarding.service import (
    CompetitorSourceOnboardingService,
)

__all__ = [
    "CompetitorSourceOnboardingService",
    "CompetitorSourceProcessingDispatcher",
]
