"""
Low-level runner for Claude Code CLI headless mode.

Authenticates with the user's Claude Max subscription via the
CLAUDE_CODE_OAUTH_TOKEN environment variable (created once with
`claude setup-token`, valid ~1 year). No per-token API billing —
each invocation consumes subscription quota instead, so callers
batch work into as few invocations as possible.

IMPORTANT: never pass `--bare` — bare mode skips OAuth token reads
and would silently drop subscription auth.
"""

import asyncio
import json
import logging
import os
import shutil
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Substrings the CLI emits when a subscription usage window is exhausted.
# Exhaustion is a hard stop until the 5-hour/weekly window resets — not a
# retryable 429 — so callers must stop cleanly instead of retrying.
_QUOTA_MARKERS = (
    "hit your session limit",
    "hit your weekly limit",
    "hit your usage limit",
    "usage limit reached",
    "limit reached",
)


class ClaudeQuotaExhausted(Exception):
    """Raised when the Claude subscription usage window is exhausted."""


class ClaudeCLIError(Exception):
    """Raised when the Claude CLI fails for a non-quota reason."""


def preflight() -> Tuple[bool, str]:
    """Check the CLI is installed and credentials are present.

    Costs no quota. Returns (ok, message).
    """
    if shutil.which("claude") is None:
        return False, (
            "Claude Code CLI not found on PATH. "
            "Install with: npm install -g @anthropic-ai/claude-code"
        )
    if not (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")):
        return False, (
            "No Claude credentials found. Run `claude setup-token` and set "
            "CLAUDE_CODE_OAUTH_TOKEN (Max subscription auth)."
        )
    return True, "Claude CLI and credentials available"


def _detect_quota_exhaustion(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _QUOTA_MARKERS)


async def _invoke(prompt: str, args: list, timeout: int) -> Dict[str, Any]:
    """Run the CLI once, returning the parsed top-level JSON envelope."""
    proc = await asyncio.create_subprocess_exec(
        "claude",
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ClaudeCLIError(f"Claude CLI timed out after {timeout}s")

    out_text = stdout.decode("utf-8", errors="replace")
    err_text = stderr.decode("utf-8", errors="replace")

    if _detect_quota_exhaustion(out_text) or _detect_quota_exhaustion(err_text):
        raise ClaudeQuotaExhausted(
            "Claude subscription usage window exhausted; stopping until it resets"
        )

    if proc.returncode != 0:
        raise ClaudeCLIError(
            f"Claude CLI exited {proc.returncode}: {err_text.strip()[:500] or out_text.strip()[:500]}"
        )

    try:
        return json.loads(out_text)
    except json.JSONDecodeError as e:
        raise ClaudeCLIError(f"Claude CLI returned non-JSON output: {e}; head={out_text[:300]!r}")


async def run_structured_prompt(
    prompt: str,
    schema: Dict[str, Any],
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    max_turns: int = 2,
) -> Dict[str, Any]:
    """Run one headless Claude prompt and return schema-conforming output.

    Uses `claude -p --output-format json --json-schema` so the CLI enforces
    the schema and returns the result in the envelope's `structured_output`
    field. Retries once on a malformed/missing structured_output, then
    raises ClaudeCLIError. ClaudeQuotaExhausted is never retried.
    """
    from crawler.config.settings import settings

    model = model or settings.claude_code_model
    timeout = timeout or settings.claude_cli_timeout

    args = [
        "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(schema),
        "--model", model,
        "--max-turns", str(max_turns),
    ]

    last_error: Optional[Exception] = None
    for attempt in (1, 2):
        try:
            envelope = await _invoke(prompt, args, timeout)
        except ClaudeQuotaExhausted:
            raise
        except ClaudeCLIError as e:
            last_error = e
            logger.warning(f"Claude CLI attempt {attempt} failed: {e}")
            continue

        structured = envelope.get("structured_output")
        if isinstance(structured, (dict, list)):
            return structured

        last_error = ClaudeCLIError(
            f"Claude CLI envelope missing structured_output "
            f"(is_error={envelope.get('is_error')}, subtype={envelope.get('subtype')})"
        )
        logger.warning(f"Claude CLI attempt {attempt}: {last_error}")

    raise last_error if last_error else ClaudeCLIError("Claude CLI failed with no diagnostic")
