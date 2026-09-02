"""End-to-End Test Script for GridGuard AI Hackathon Demo Scenario.

Verifies complete pipeline execution:
Feeder lookup -> ML Forecast -> Stress Risk -> Optimization Recommendation ->
Counterfactual Simulation -> Operator Action Dispatch -> AI Copilot Explanation -> Final Outcome.
"""

import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.demo_service import demo_service
from app.services.feeder_service import get_feeder_by_id


def run_demo_test() -> None:
    """Execute end-to-end hackathon demo scenario verification."""
    print("==================================================")
    print("GRIDGUARD AI — END-TO-END DEMO SCENARIO TEST")
    print("==================================================")

    # 1. Verify Feeder F07 existence
    feeder = get_feeder_by_id("F07")
    assert feeder is not None, "Feeder F07 must exist!"
    print(f"[✓] Feeder F07 Specs: Capacity={feeder.capacity} MW | Load={feeder.current_load} MW | Voltage={feeder.voltage} p.u.")

    # 2. Run Demo Scenario Service
    demo = demo_service.run_demo_scenario("F07")
    print(f"\n[✓] Scenario Name: {demo.scenario}")
    print(f"[✓] Forecast Peak (ML): {demo.outcome.before_load_mw:.1f} MW (source: '{demo.forecast.source}')")
    print(f"[✓] Risk Score: {demo.risk.score:.0f}/100 ({demo.risk.level.value}) | TTO: {demo.risk.time_to_overload} min")
    print(f"[✓] Recommended Actions: {demo.recommendation.actions}")
    print(f"[✓] Simulation Reduction: {demo.simulation.total_reduction} MW -> Simulated Load: {demo.simulation.simulated_load} MW")
    if demo.dispatch:
        print(f"[✓] Operator Dispatch Status: {demo.dispatch.status} (Actions: {[a.action_type for a in demo.dispatch.actions]})")
    print(f"[✓] AI Copilot Source: '{demo.copilot.source}'")
    print(f"[✓] Operational Outcome: {demo.outcome.status_message}")

    # 3. Verify Logical Consistency
    out = demo.outcome
    if out.overload_before and not out.overload_after:
        assert out.overload_avoided is True, "Overload must be avoided if peak > capacity and simulated <= capacity!"
        assert out.status_message == "OVERLOAD_PREVENTED"
    elif not out.overload_before:
        assert out.overload_avoided is False, "Do not claim overload prevented if no overload was detected initially!"
        assert out.status_message == "NO_OVERLOAD_DETECTED"

    print("\n==================================================")
    print("ALL END-TO-END DEMO SCENARIO ASSERTS PASSED PERFECTLY!")
    print("==================================================")


if __name__ == "__main__":
    run_demo_test()
