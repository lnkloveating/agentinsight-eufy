"""不调用模型的资料路由信号提取与分类规则。"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from app.schemas.evidence import EvidenceClaimType
from app.schemas.source_routing import (
    SourceRouteTarget,
    SourceRoutingSuggestedBy,
    SourceRoutingSuggestion,
)


class SourceRoutingInput(BaseModel):
    source_asset_id: str
    content_hash: str
    display_name: str
    source_url: str | None
    media_type: str
    media_category: str
    authorization_basis: str
    purpose: str
    fragment_hashes: list[str] = Field(default_factory=list)
    excerpts: list[str] = Field(default_factory=list)

    def stable_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeterministicRoutingResult:
    suggestions: list[SourceRoutingSuggestion]
    signals: list[str]


@dataclass
class _RouteScore:
    weights: list[float]
    claim_types: set[EvidenceClaimType]
    signals: set[str]


class DeterministicSourceRouter:
    """根据来源、路径、用途和原文特征生成可解释的多标签建议。"""

    _retail_domains = {
        "amazon.com",
        "bestbuy.com",
        "walmart.com",
        "target.com",
        "costco.com",
        "homedepot.com",
        "lowes.com",
    }
    _review_domains = {"reddit.com", "youtube.com", "youtu.be"}

    def classify(self, source: SourceRoutingInput) -> DeterministicRoutingResult:
        routes: defaultdict[SourceRouteTarget, _RouteScore] = defaultdict(
            lambda: _RouteScore([], set(), set())
        )
        combined = "\n".join([source.display_name, source.purpose, *source.excerpts]).lower()
        url = urlsplit(source.source_url or "")
        domain = (url.hostname or "").lower().removeprefix("www.")
        path = url.path.lower()

        def add(
            route: SourceRouteTarget,
            weight: float,
            signal: str,
            *claim_types: EvidenceClaimType,
        ) -> None:
            score = routes[route]
            score.weights.append(weight)
            score.signals.add(signal)
            score.claim_types.update(claim_types)

        if self._matches_domain(domain, self._retail_domains):
            add(
                SourceRouteTarget.PRICE_CHANNEL,
                0.96,
                f"retail_domain:{domain}",
                EvidenceClaimType.PRICE_OBSERVATION,
                EvidenceClaimType.CHANNEL_AVAILABILITY,
                EvidenceClaimType.SELLER_INFORMATION,
                EvidenceClaimType.PROMOTION,
            )
        if self._matches_domain(domain, self._review_domains):
            add(
                SourceRouteTarget.USER_REVIEW,
                0.72,
                f"review_domain:{domain}",
                EvidenceClaimType.USER_OPINION,
            )
            if domain in {"youtube.com", "youtu.be"}:
                add(
                    SourceRouteTarget.MEDIA_REVIEW,
                    0.88,
                    f"media_domain:{domain}",
                    EvidenceClaimType.USER_OPINION,
                )
        if re.search(r"/(products?|shop)/", path) and not self._matches_domain(
            domain, self._retail_domains
        ):
            add(
                SourceRouteTarget.OFFICIAL_PRODUCT,
                0.72,
                "product_path",
                EvidenceClaimType.VENDOR_CLAIM,
                EvidenceClaimType.PRODUCT_IDENTITY,
                EvidenceClaimType.CAPABILITY,
                EvidenceClaimType.SPECIFICATION,
                EvidenceClaimType.COMPATIBILITY,
                EvidenceClaimType.LIMITATION,
            )

        self._classify_purpose(combined, add)
        self._classify_content(combined, add)
        if source.media_category in {"video", "audio"}:
            add(
                SourceRouteTarget.MEDIA_REVIEW,
                0.48,
                f"media_category:{source.media_category}",
                EvidenceClaimType.USER_OPINION,
            )
        if source.authorization_basis == "enterprise_authorized" and self._contains_any(
            combined, ("internal", "内部", "confidential", "保密")
        ):
            add(
                SourceRouteTarget.ENTERPRISE_INTERNAL,
                0.96,
                "enterprise_internal_authorization",
                EvidenceClaimType.FACT,
            )

        suggestions = [
            SourceRoutingSuggestion(
                route=route,
                claim_types=sorted(score.claim_types, key=str),
                confidence=round(self._combined_confidence(score.weights), 4),
                reason="；".join(sorted(score.signals)),
                signals=sorted(score.signals),
                suggested_by=SourceRoutingSuggestedBy.RULE,
            )
            for route, score in routes.items()
            if score.claim_types and self._combined_confidence(score.weights) >= 0.4
        ]
        suggestions.sort(key=lambda item: (-item.confidence, item.route.value))
        signals = sorted({signal for item in suggestions for signal in item.signals})
        return DeterministicRoutingResult(suggestions=suggestions, signals=signals)

    @staticmethod
    def _classify_purpose(combined: str, emit: Callable[..., None]) -> None:
        if DeterministicSourceRouter._contains_any(
            combined, ("official", "官网", "官方产品", "产品规格")
        ):
            emit(
                SourceRouteTarget.OFFICIAL_PRODUCT,
                0.82,
                "purpose:official_product",
                EvidenceClaimType.VENDOR_CLAIM,
                EvidenceClaimType.PRODUCT_IDENTITY,
                EvidenceClaimType.CAPABILITY,
                EvidenceClaimType.SPECIFICATION,
            )
        if DeterministicSourceRouter._contains_any(
            combined, ("price", "pricing", "retail", "价格", "渠道", "商品页")
        ):
            emit(
                SourceRouteTarget.PRICE_CHANNEL,
                0.82,
                "purpose:price_channel",
                EvidenceClaimType.PRICE_OBSERVATION,
                EvidenceClaimType.CHANNEL_AVAILABILITY,
            )
        if DeterministicSourceRouter._contains_any(
            combined, ("review", "用户评价", "用户评论", "测评")
        ):
            emit(
                SourceRouteTarget.USER_REVIEW,
                0.78,
                "purpose:user_review",
                EvidenceClaimType.USER_OPINION,
            )
        if DeterministicSourceRouter._contains_any(
            combined, ("interview", "用户访谈", "用户研究", "痛点")
        ):
            emit(
                SourceRouteTarget.USER_RESEARCH,
                0.8,
                "purpose:user_research",
                EvidenceClaimType.USER_OPINION,
            )
        if DeterministicSourceRouter._contains_any(
            combined, ("market report", "行业报告", "市场报告", "market research")
        ):
            emit(
                SourceRouteTarget.MARKET_RESEARCH,
                0.84,
                "purpose:market_research",
                EvidenceClaimType.MARKET_FACT,
            )

    @staticmethod
    def _classify_content(combined: str, emit: Callable[..., None]) -> None:
        if re.search(r"(?:\$|€|£|¥)\s?\d|\b(?:usd|aud|eur|gbp|cny)\b", combined):
            emit(
                SourceRouteTarget.PRICE_CHANNEL,
                0.62,
                "content:currency_price",
                EvidenceClaimType.PRICE_OBSERVATION,
            )
        if DeterministicSourceRouter._contains_any(
            combined, ("in stock", "out of stock", "add to cart", "库存", "加入购物车")
        ):
            emit(
                SourceRouteTarget.PRICE_CHANNEL,
                0.5,
                "content:availability",
                EvidenceClaimType.CHANNEL_AVAILABILITY,
            )
        if DeterministicSourceRouter._contains_any(
            combined, ("coupon", "discount", "save ", "优惠券", "折扣", "促销")
        ):
            emit(
                SourceRouteTarget.PRICE_CHANNEL,
                0.48,
                "content:promotion",
                EvidenceClaimType.PROMOTION,
            )
        if DeterministicSourceRouter._contains_any(
            combined, ("rating", "stars", "verified purchase", "评分", "用户评论")
        ):
            emit(
                SourceRouteTarget.USER_REVIEW,
                0.58,
                "content:user_review",
                EvidenceClaimType.USER_OPINION,
            )
        if DeterministicSourceRouter._contains_any(
            combined,
            ("specification", "compatibility", "firmware", "规格", "兼容", "固件"),
        ):
            emit(
                SourceRouteTarget.TECHNICAL_DOCUMENT,
                0.62,
                "content:technical_terms",
                EvidenceClaimType.SPECIFICATION,
                EvidenceClaimType.COMPATIBILITY,
                EvidenceClaimType.TECHNICAL_FACT,
            )

    @staticmethod
    def _combined_confidence(weights: list[float]) -> float:
        remaining = 1.0
        for weight in weights:
            remaining *= 1 - weight
        return min(0.99, 1 - remaining)

    @staticmethod
    def _matches_domain(domain: str, candidates: set[str]) -> bool:
        return any(domain == item or domain.endswith(f".{item}") for item in candidates)

    @staticmethod
    def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
        return any(term in text for term in terms)
