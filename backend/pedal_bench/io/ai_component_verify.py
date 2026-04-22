"""Verify a component photo against an expected BOM row.

Builder takes a photo of the part they're about to stuff. Claude compares
it against the BOM row's expected ``value`` + ``type`` and returns one of:

- ``match``    — photo clearly matches what the BOM says
- ``mismatch`` — photo is clearly a different component
- ``unsure``   — photo is unclear, cropped, out of focus, or otherwise
                 doesn't allow a confident call

The ``mismatch`` case is the valuable one: catching a swapped component
before it's soldered saves hours of debugging.

Contract:
    verify_component_photo(png_or_jpg_bytes, expected_value, expected_type,
                           optional_bom_context) -> VerifyResult

Raises only for programmer errors (bad inputs); network / API errors are
surfaced as ``VerifyResult(verdict="error", explanation=...)`` so the UI
can show them without crashing.
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 600

_VERDICT_VALUES = {"match", "mismatch", "unsure"}


@dataclass(frozen=True)
class VerifyResult:
    verdict: str  # match | mismatch | unsure | error
    explanation: str
    guess_value: str | None = None
    guess_type: str | None = None


_TOOL_SCHEMA = {
    "name": "report_verdict",
    "description": (
        "Report whether the component in the photo matches the expected "
        "BOM entry, with a short explanation and — if you can — a guess at "
        "what component is actually in the photo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": sorted(_VERDICT_VALUES),
                "description": (
                    "'match' if the photo clearly matches the expected "
                    "component. 'mismatch' if it's clearly different. "
                    "'unsure' if you can't tell."
                ),
            },
            "explanation": {
                "type": "string",
                "description": (
                    "One or two short sentences explaining the verdict. "
                    "Call out the specific visual evidence — color bands, "
                    "text markings, body shape, package style."
                ),
            },
            "guess_value": {
                "type": "string",
                "description": (
                    "If you can read the component's actual value (resistor "
                    "bands, capacitor marking, IC part number), report it. "
                    "Omit if unreadable."
                ),
            },
            "guess_type": {
                "type": "string",
                "description": (
                    "Short description of what the component actually "
                    "appears to be (e.g. 'ceramic capacitor', 'NPN "
                    "transistor', 'film resistor 1/4W'). Omit if unclear."
                ),
            },
        },
        "required": ["verdict", "explanation"],
    },
}


def verify_component_photo(
    image_bytes: bytes,
    image_media_type: str,
    expected_value: str,
    expected_type: str,
    expected_location: str | None = None,
    *,
    api_key: str | None = None,
) -> VerifyResult:
    if not image_bytes:
        return VerifyResult("error", "No image bytes provided.")
    effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not effective_key:
        return VerifyResult(
            "error",
            "No Anthropic API key — set one in Settings to enable component verification.",
        )
    if image_media_type not in {"image/jpeg", "image/png", "image/webp"}:
        return VerifyResult(
            "error", f"Unsupported image type: {image_media_type!r}"
        )

    try:
        resp = _call_claude(
            image_bytes, image_media_type,
            expected_value, expected_type, expected_location,
            api_key=effective_key,
        )
    except Exception as exc:
        log.info("verify_component_photo: API call failed: %s", exc)
        return VerifyResult("error", f"Vision API error: {type(exc).__name__}")

    return _parse_response(resp)


def _call_claude(
    image_bytes: bytes,
    image_media_type: str,
    expected_value: str,
    expected_type: str,
    expected_location: str | None,
    *,
    api_key: str,
):
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    where = f" (BOM location {expected_location})" if expected_location else ""
    user_text = (
        f"I'm about to stuff{where}. The BOM says this position is:\n"
        f"  value: {expected_value or '(unspecified)'}\n"
        f"  type:  {expected_type or '(unspecified)'}\n\n"
        "Look at the photo. Is the component in the photo actually this "
        "part? Be specific about the visual evidence:\n"
        "- For resistors: read the color bands if visible\n"
        "- For capacitors: read the marking (e.g. '104' = 100nF)\n"
        "- For ICs: read the part number printed on top\n"
        "- For transistors: read the body marking (e.g. '2N5088')\n\n"
        "If it clearly matches, say 'match'. If it's clearly a different "
        "component, say 'mismatch' and tell me what it actually is. If the "
        "photo is blurry, cropped, or otherwise too unclear to call, say "
        "'unsure'. Use the report_verdict tool — no free-form reply."
    )

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "report_verdict"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    )


def _parse_response(resp) -> VerifyResult:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and block.name == "report_verdict":
            data = block.input or {}
            verdict = data.get("verdict", "unsure")
            if verdict not in _VERDICT_VALUES:
                verdict = "unsure"
            explanation = str(data.get("explanation") or "").strip()
            if not explanation:
                explanation = "(no explanation provided)"
            # Cap absurd lengths.
            explanation = explanation[:600]
            guess_value = _trim(data.get("guess_value"))
            guess_type = _trim(data.get("guess_type"))
            return VerifyResult(verdict, explanation, guess_value, guess_type)

    return VerifyResult(
        "error",
        "Model did not return a tool_use response; try again.",
    )


def _trim(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s[:120]


__all__ = ["VerifyResult", "verify_component_photo"]
