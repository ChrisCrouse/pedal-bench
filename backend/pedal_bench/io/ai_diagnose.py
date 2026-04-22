"""AI-assisted pedal diagnosis.

Takes a symptom ("no sound", "weak output", "distorted at low gain"), a
set of measured IC pin voltages, and optionally the project's cached
wiring-diagram image, and asks Claude to reason about the fault.

This is the "voltage-tree debugging" feature, AI-first: rather than
hand-authoring decision trees for each pedal, we let Sonnet read the
schematic image and reason from first principles. For well-known pedals
this produces meaningfully correct advice; for obscure designs it at
least produces coherent *probe-next* suggestions the builder can follow.

Contract:
    diagnose(symptom, supply, selected_ic, readings, wiring_image=None,
             project_name=None) -> DiagnosisResult

Never raises — all failures become DiagnosisResult(confidence="error",...).

Cost envelope (Sonnet 4.6):
    With wiring image:       ~$0.02–0.05 per call
    Text-only:               ~$0.005–0.015 per call
    Prompt caching reused across calls in the same session: ~70-90% savings.
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1400


@dataclass(frozen=True)
class PinReading:
    pin: int
    name: str
    expected_v: float | None
    tolerance_v: float | None
    measured_v: float | None  # None if user hasn't measured yet


@dataclass(frozen=True)
class DiagnosisResult:
    primary_suspect: str
    reasoning: str
    next_probe: str
    confidence: str                        # high | medium | low | error
    alternative_suspects: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)


_TOOL_SCHEMA = {
    "name": "report_diagnosis",
    "description": (
        "Report your diagnosis of the pedal fault based on the symptom, "
        "measured voltages, and schematic (if provided). Always call this "
        "tool — never reply in plain text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "primary_suspect": {
                "type": "string",
                "description": (
                    "The single most likely cause of the reported symptom. "
                    "Be specific — name the component designator when "
                    "possible (e.g., 'C5 backwards', 'Q2 emitter open')."
                ),
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "One or two paragraphs explaining why this is the "
                    "primary suspect. Cite specific voltage readings and "
                    "what they tell you about signal flow."
                ),
            },
            "next_probe": {
                "type": "string",
                "description": (
                    "Concrete next step: what to measure or check, and "
                    "what reading would confirm vs. rule out the suspect."
                ),
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": (
                    "Your confidence in the primary suspect. 'low' is fine "
                    "and honest when the readings are ambiguous."
                ),
            },
            "alternative_suspects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Other plausible causes to keep in mind.",
            },
            "caveats": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Honest limitations: missing readings, unreadable "
                    "schematic, unknown pedal topology, etc."
                ),
            },
        },
        "required": ["primary_suspect", "reasoning", "next_probe", "confidence"],
    },
}


def diagnose(
    symptom: str,
    supply_vcc_v: float,
    supply_vref_v: float,
    selected_ic: str | None,
    readings: list[PinReading],
    wiring_image: tuple[bytes, str] | None = None,
    project_name: str | None = None,
    bom_highlights: list[str] | None = None,
) -> DiagnosisResult:
    """Ask Claude to reason about the fault and return structured advice."""
    symptom = (symptom or "").strip()
    if not symptom:
        return DiagnosisResult(
            primary_suspect="(no symptom given)",
            reasoning="",
            next_probe="Describe what's wrong with the pedal first.",
            confidence="error",
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return DiagnosisResult(
            primary_suspect="(no API key)",
            reasoning="",
            next_probe="Add ANTHROPIC_API_KEY to backend/.env.",
            confidence="error",
        )

    try:
        resp = _call_claude(
            symptom=symptom,
            supply_vcc_v=supply_vcc_v,
            supply_vref_v=supply_vref_v,
            selected_ic=selected_ic,
            readings=readings,
            wiring_image=wiring_image,
            project_name=project_name,
            bom_highlights=bom_highlights or [],
        )
    except Exception as exc:
        log.info("diagnose: API call failed: %s", exc)
        return DiagnosisResult(
            primary_suspect="(API error)",
            reasoning=f"{type(exc).__name__}: {exc}",
            next_probe="Check your API key, usage limit, and network.",
            confidence="error",
        )

    return _parse_response(resp)


def _call_claude(
    *,
    symptom: str,
    supply_vcc_v: float,
    supply_vref_v: float,
    selected_ic: str | None,
    readings: list[PinReading],
    wiring_image: tuple[bytes, str] | None,
    project_name: str | None,
    bom_highlights: list[str],
):
    import anthropic

    client = anthropic.Anthropic()

    system = (
        "You are a DIY guitar pedal debugging assistant. You reason about "
        "analog circuits from first principles: signal flow, bias points, "
        "op-amp behavior, transistor saturation, coupling-cap polarity. "
        "You are decisive when readings clearly indicate a fault, and "
        "honestly uncertain when they don't. Never invent component "
        "designators you can't see; if the schematic is absent, refer to "
        "stages functionally ('the gain stage', 'the output coupling "
        "capacitor'). Always call the report_diagnosis tool — never "
        "reply in plain text."
    )

    lines: list[str] = []
    if project_name:
        lines.append(f"Pedal: {project_name}")
    lines.append(f"Power supply: V+ = {supply_vcc_v} V, VREF = {supply_vref_v} V")
    lines.append("")
    lines.append(f"Reported symptom: {symptom}")
    lines.append("")

    if selected_ic:
        lines.append(f"Relevant IC: {selected_ic}")

    if readings:
        lines.append("Measured pin voltages:")
        for r in readings:
            expected_str = (
                f"expected {r.expected_v:.2f} V (±{r.tolerance_v or 0:.2f})"
                if r.expected_v is not None
                else "no target"
            )
            measured_str = (
                f"measured {r.measured_v:.2f} V"
                if r.measured_v is not None
                else "not measured"
            )
            lines.append(f"  pin {r.pin} ({r.name}): {measured_str}; {expected_str}")
    else:
        lines.append("(No pin readings provided.)")

    if bom_highlights:
        lines.append("")
        lines.append("Relevant BOM rows (polarity-sensitive or unusual values):")
        for b in bom_highlights[:30]:
            lines.append(f"  - {b}")

    lines.append("")
    lines.append(
        "Based on the symptom + readings (+ schematic if provided), give me "
        "your best single primary suspect, the reasoning chain, and the "
        "next thing to probe. Use the report_diagnosis tool."
    )

    user_content: list[dict] = []
    if wiring_image is not None:
        image_bytes, media_type = wiring_image
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        user_content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
                # Cache the schematic so repeat calls within a session are cheap.
                "cache_control": {"type": "ephemeral"},
            }
        )
    user_content.append({"type": "text", "text": "\n".join(lines)})

    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "report_diagnosis"},
        messages=[{"role": "user", "content": user_content}],
    )


def _parse_response(resp) -> DiagnosisResult:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and block.name == "report_diagnosis":
            data = block.input or {}
            primary = str(data.get("primary_suspect") or "(no suspect returned)")[:500]
            reasoning = str(data.get("reasoning") or "")[:3000]
            next_probe = str(data.get("next_probe") or "")[:800]
            conf = data.get("confidence") or "low"
            if conf not in {"high", "medium", "low"}:
                conf = "low"
            alts_raw = data.get("alternative_suspects") or []
            caveats_raw = data.get("caveats") or []
            alts = [str(a)[:200] for a in alts_raw if a][:6]
            caveats = [str(c)[:200] for c in caveats_raw if c][:6]
            return DiagnosisResult(
                primary_suspect=primary,
                reasoning=reasoning,
                next_probe=next_probe,
                confidence=conf,
                alternative_suspects=alts,
                caveats=caveats,
            )

    return DiagnosisResult(
        primary_suspect="(no tool response)",
        reasoning="",
        next_probe="Try again; the model didn't return a structured reply.",
        confidence="error",
    )


__all__ = ["PinReading", "DiagnosisResult", "diagnose"]
