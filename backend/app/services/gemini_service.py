"""Gemini explanation service for GridGuard AI Copilot.

DISCLAIMER: This service translates structured deterministic feeder intelligence
into natural-language operational explanations using Google Gemini (or a deterministic
fallback when Gemini is unavailable). It NEVER computes risk scores, load values,
or action feasibility.
"""

import json
import logging
from typing import Optional

from google import genai

from app.schemas.copilot import CopilotExplanationSource, CopilotResponse
from app.schemas.feeder import FeederIntelligenceResponse
from app.utils.config import get_gemini_api_key

logger = logging.getLogger(__name__)

# System prompt constraining Gemini to strictly adhere to provided structured data
SYSTEM_PROMPT = """You are GridGuard AI, an expert electrical grid operations copilot.
Your job is to convert structured feeder metrics, load forecasts, risk assessments, and recommended mitigation actions into a concise, professional, operator-ready explanation.

CRITICAL CONSTRAINTS:
1. Base your response ONLY on the provided JSON data.
2. DO NOT invent, calculate, or hallucinate measurements, risk scores, forecast numbers, or actions.
3. DO NOT change the risk score, risk level, or recommendation status.
4. Keep all explanations operational, concise, and professional.
5. Output ONLY valid JSON matching this exact structure:
{
  "summary": "<concise operational summary>",
  "risk_explanation": "<explanation of risk score and key contributors>",
  "recommended_action_explanation": "<explanation of recommended actions>",
  "expected_outcome": "<explanation of expected load and status after action>",
  "operator_message": "<actionable directive for grid operator>"
}"""


def generate_deterministic_fallback(intelligence: FeederIntelligenceResponse) -> CopilotResponse:
    """Generate a programmatic explanation fallback directly from structured intelligence data when Gemini is unavailable."""
    feeder_id = intelligence.feeder_id
    cap = intelligence.current.capacity
    risk = intelligence.risk
    rec = intelligence.recommendation
    contribs = [c.name for c in intelligence.contributors]

    # 1. Summary
    if risk.score > 30:
        tto_str = f" within {int(risk.time_to_overload)} minutes" if risk.time_to_overload else ""
        summary = (
            f"Feeder {feeder_id} is operating under {risk.level} risk (score: {int(risk.score)}/100) "
            f"and is predicted to exceed its {cap:.0f} MW capacity{tto_str}."
        )
    else:
        summary = (
            f"Feeder {feeder_id} is operating safely within normal parameters under {risk.level} risk "
            f"(score: {int(risk.score)}/100)."
        )

    # 2. Risk Explanation
    if contribs:
        contrib_text = ", ".join(contribs)
        risk_explanation = (
            f"Risk score is {int(risk.score)} ({risk.level}). The main contributors are: {contrib_text}."
        )
    else:
        risk_explanation = f"Risk score is {int(risk.score)} ({risk.level}). No active risk contributors identified."

    # 3. Recommended Action Explanation
    if rec.actions:
        actions_text = " and ".join(rec.actions)
        rec_explanation = f"Recommended actions are {actions_text} to mitigate predicted overload."
    else:
        rec_explanation = "No intervention required as the feeder load is within safe capacity limits."

    # 4. Expected Outcome
    if rec.status == "OVERLOAD_AVOIDED":
        expected_outcome = (
            f"Expected load after recommended actions is {rec.expected_load_after:.0f} MW, "
            f"so the overload is avoided (reduced from {rec.predicted_load:.0f} MW peak)."
        )
    elif rec.status == "SAFE":
        expected_outcome = (
            f"Expected load is {rec.predicted_after:.0f} MW, remaining safely below capacity."
        )
    else:
        expected_outcome = (
            f"Expected load after action is {rec.predicted_after:.0f} MW. Flexibility is insufficient to fully clear overload."
        )

    # 5. Operator Message
    if risk.time_to_overload:
        operator_msg = f"Act within the {int(risk.time_to_overload)}-minute overload window to authorize mitigation."
    elif risk.score > 30:
        operator_msg = f"Monitor feeder {feeder_id} closely and prepare for load control operations."
    else:
        operator_msg = f"System normal for feeder {feeder_id}. Continue standard grid monitoring."

    return CopilotResponse(
        feeder_id=feeder_id,
        summary=summary,
        risk_explanation=risk_explanation,
        recommended_action_explanation=rec_explanation,
        expected_outcome=expected_outcome,
        operator_message=operator_msg,
        source=CopilotExplanationSource.DETERMINISTIC_FALLBACK,
    )


def generate_copilot_explanation(intelligence: FeederIntelligenceResponse) -> CopilotResponse:
    """Generate a Copilot operational explanation for feeder intelligence.

    Uses Google Gemini SDK (gemini-2.5-flash) if API key is present; falls back to
    deterministic code if key is missing or API call fails.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        logger.info("GEMINI_API_KEY not found. Using deterministic fallback.")
        return generate_deterministic_fallback(intelligence)

    try:
        client = genai.Client(api_key=api_key)
        prompt_content = f"{SYSTEM_PROMPT}\n\nStructured Feeder Data:\n{intelligence.model_dump_json()}"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_content,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        res_text = response.text

        # Parse JSON output
        data = json.loads(res_text)
        return CopilotResponse(
            feeder_id=intelligence.feeder_id,
            summary=data.get("summary", ""),
            risk_explanation=data.get("risk_explanation", ""),
            recommended_action_explanation=data.get("recommended_action_explanation", ""),
            expected_outcome=data.get("expected_outcome", ""),
            operator_message=data.get("operator_message", ""),
            source=CopilotExplanationSource.GEMINI,
        )
    except Exception as err:
        logger.warning(f"Gemini API call error ({err}). Falling back to deterministic explanation.")
        return generate_deterministic_fallback(intelligence)
