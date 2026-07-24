# -*- coding: utf-8 -*-
"""Explainable scoring contracts for candidate split paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ScoringCriterion:
    """One independent, weighted criterion in a scoring profile."""

    criterion_id: str
    label: str
    description: str
    weight: float
    direction: Literal["minimize", "maximize"]
    is_enabled: bool = True


@dataclass(frozen=True, slots=True)
class CandidateScore:
    """An explainable score assigned to one candidate for one criterion."""

    candidate_id: str
    criterion: ScoringCriterion
    raw_value: float
    normalized_value: float
    weighted_value: float
    rationale: str
    evidence_feature_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """All criterion scores and the final score for one candidate path."""

    candidate_id: str
    scoring_profile_id: str
    scores: tuple[CandidateScore, ...]
    total_score: float
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PathRanking:
    """A deterministic, explainable ordering of scored candidate paths."""

    ranking_id: str
    geometry_id: str
    scoring_profile_id: str
    scoring_model_version: str
    criteria: tuple[ScoringCriterion, ...]
    ordered_breakdowns: tuple[ScoreBreakdown, ...]
    tie_breaker_rule: str
