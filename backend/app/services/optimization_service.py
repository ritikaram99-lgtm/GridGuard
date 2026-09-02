"""Optimization engine evaluating candidate actions for feeder peak load reduction.

Determines the optimal feasible combination of flexible resources to achieve
required load reduction while minimizing cost, disruption, and excess reduction.
"""

from dataclasses import dataclass
from itertools import combinations
from typing import Optional
from app.schemas.recommendation import ActionDetail
from app.services.flexibility_service import FlexibleResource


@dataclass
class CandidateCombination:
    """Class representing a evaluated combination of resource actions."""

    actions: list[ActionDetail]
    total_reduction: float
    total_cost: float
    total_disruption: float
    action_names: list[str]


def calculate_required_reduction(predicted_load: float, capacity: float) -> float:
    """Calculate required load reduction in MW.

    Formula: required_reduction = max(predicted_load - capacity, 0)
    """
    return max(predicted_load - capacity, 0.0)


def generate_candidate_combinations(resources: list[FlexibleResource]) -> list[CandidateCombination]:
    """Generate all non-empty candidate combinations of available flexible resources."""
    candidate_list: list[CandidateCombination] = []

    for r in range(1, len(resources) + 1):
        for resource_group in combinations(resources, r):
            details: list[ActionDetail] = []
            tot_reduction = 0.0
            tot_cost = 0.0
            tot_disruption = 0.0
            names: list[str] = []

            for res in resource_group:
                reduction = res.max_reduction
                cost = reduction * res.cost_per_mw
                disruption = reduction * res.disruption_per_mw

                details.append(
                    ActionDetail(
                        action_type=res.action_type,
                        load_reduction=reduction,
                        cost=cost,
                        disruption=disruption,
                    )
                )
                tot_reduction += reduction
                tot_cost += cost
                tot_disruption += disruption
                names.append(res.action_type)

            candidate_list.append(
                CandidateCombination(
                    actions=details,
                    total_reduction=tot_reduction,
                    total_cost=tot_cost,
                    total_disruption=tot_disruption,
                    action_names=names,
                )
            )

    return candidate_list


def select_best_action(
    resources: list[FlexibleResource], required_reduction: float
) -> Optional[CandidateCombination]:
    """Select the optimal feasible combination of resources to satisfy required_reduction.

    Selection Criteria:
    1. Feasibility: total_reduction >= required_reduction
    2. Primary Objective: Minimum total_cost
    3. Secondary Objective: Minimum total_disruption
    4. Tertiary Objective: Minimum excess load reduction (total_reduction - required_reduction)

    Returns None if no combination can satisfy required_reduction.
    """
    if required_reduction <= 0:
        return CandidateCombination(
            actions=[],
            total_reduction=0.0,
            total_cost=0.0,
            total_disruption=0.0,
            action_names=[],
        )

    all_candidates = generate_candidate_combinations(resources)

    # Filter feasible combinations
    feasible_candidates = [
        c for c in all_candidates if c.total_reduction >= required_reduction
    ]

    if not feasible_candidates:
        return None

    # Deterministic multi-criteria sort
    feasible_candidates.sort(
        key=lambda c: (
            c.total_cost,
            c.total_disruption,
            c.total_reduction - required_reduction,
        )
    )

    return feasible_candidates[0]
