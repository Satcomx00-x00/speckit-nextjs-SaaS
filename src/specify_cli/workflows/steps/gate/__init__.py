"""Gate step — human review gate."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from specify_cli.workflows.base import StepBase, StepContext, StepResult, StepStatus
from specify_cli.workflows.expressions import evaluate_expression

CHECK_TIMEOUT_SECONDS = 300


class GateStep(StepBase):
    """Interactive review gate.

    When running in an interactive terminal, prompts the user to choose
    an option (e.g. approve / reject).  Falls back to ``PAUSED`` when
    stdin is not a TTY (CI, piped input) so the run can be resumed
    later with ``specify workflow resume``.

    An optional ``check:`` shell command runs BEFORE the human is
    prompted.  A non-zero exit blocks the gate (``on_check_fail:
    block``, the default) so approval cannot even be offered while the
    machine-verifiable pre-condition is unmet — or downgrades to a
    warning shown alongside the prompt (``on_check_fail: warn``).

    The user's choice is stored in ``output.choice``.  ``on_reject``
    controls abort / skip behaviour.
    """

    type_key = "gate"

    def execute(self, config: dict[str, Any], context: StepContext) -> StepResult:
        message = config.get("message", "Review required.")
        if isinstance(message, str) and "{{" in message:
            message = evaluate_expression(message, context)

        options = config.get("options", ["approve", "reject"])
        on_reject = config.get("on_reject", "abort")

        show_file = config.get("show_file")
        if show_file and isinstance(show_file, str) and "{{" in show_file:
            show_file = evaluate_expression(show_file, context)

        output = {
            "message": message,
            "options": options,
            "on_reject": on_reject,
            "show_file": show_file,
            "choice": None,
        }

        # Machine-verifiable pre-condition: runs before the human sees
        # the gate, in CI and interactive runs alike.
        check_cmd = config.get("check")
        if check_cmd:
            if isinstance(check_cmd, str) and "{{" in check_cmd:
                check_cmd = evaluate_expression(check_cmd, context)
            check_cmd = str(check_cmd)
            on_check_fail = config.get("on_check_fail", "block")
            check_result = self._run_check(check_cmd)
            output["check"] = check_result
            if check_result["exit_code"] != 0:
                if on_check_fail == "block":
                    return StepResult(
                        status=StepStatus.FAILED,
                        output=output,
                        error=(
                            f"Gate {config.get('id', '?')!r} pre-condition failed "
                            f"(exit {check_result['exit_code']}): {check_cmd}"
                        ),
                    )
                # on_check_fail == "warn": surface it, let the human decide
                print(
                    f"  ⚠ Gate pre-condition failed (exit "
                    f"{check_result['exit_code']}): {check_cmd}"
                )
                if check_result["output_tail"]:
                    print(f"    {check_result['output_tail']}")

        # Non-interactive: pause for later resume
        if not sys.stdin.isatty():
            return StepResult(status=StepStatus.PAUSED, output=output)

        # Interactive: prompt the user
        choice = self._prompt(message, options)
        output["choice"] = choice

        if choice in ("reject", "abort"):
            if on_reject == "abort":
                output["aborted"] = True
                return StepResult(
                    status=StepStatus.FAILED,
                    output=output,
                    error=f"Gate rejected by user at step {config.get('id', '?')!r}",
                )
            if on_reject == "retry":
                # Pause so the next resume re-executes this gate
                return StepResult(status=StepStatus.PAUSED, output=output)
            # on_reject == "skip" → completed, downstream steps decide
            return StepResult(status=StepStatus.COMPLETED, output=output)

        return StepResult(status=StepStatus.COMPLETED, output=output)

    @staticmethod
    def _run_check(check_cmd: str) -> dict[str, Any]:
        """Run the gate's pre-condition shell command, capturing a short tail."""
        try:
            proc = subprocess.run(
                check_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=CHECK_TIMEOUT_SECONDS,
            )
            combined = (proc.stdout or "") + (proc.stderr or "")
            tail = combined.strip().splitlines()[-5:]
            return {
                "run": check_cmd,
                "exit_code": proc.returncode,
                "output_tail": "\n    ".join(tail),
            }
        except subprocess.TimeoutExpired:
            return {
                "run": check_cmd,
                "exit_code": -1,
                "output_tail": f"timed out after {CHECK_TIMEOUT_SECONDS}s",
            }
        except Exception as exc:  # noqa: BLE001 — report, don't crash the gate
            return {"run": check_cmd, "exit_code": -1, "output_tail": str(exc)}

    @staticmethod
    def _prompt(message: str, options: list[str]) -> str:
        """Display gate message and prompt for a choice."""
        print("\n  ┌─ Gate ─────────────────────────────────────")
        print(f"  │ {message}")
        print("  │")
        for i, opt in enumerate(options, 1):
            print(f"  │  [{i}] {opt}")
        print("  └────────────────────────────────────────────")

        while True:
            try:
                raw = input(f"  Choose [1-{len(options)}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return options[-1]  # default to last (usually reject)
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return options[int(raw) - 1]
            # Also accept the option name directly
            if raw.lower() in [o.lower() for o in options]:
                return next(o for o in options if o.lower() == raw.lower())
            print(f"  Invalid choice. Enter 1-{len(options)} or an option name.")

    def validate(self, config: dict[str, Any]) -> list[str]:
        errors = super().validate(config)
        if "message" not in config:
            errors.append(
                f"Gate step {config.get('id', '?')!r} is missing 'message' field."
            )
        options = config.get("options", ["approve", "reject"])
        if not isinstance(options, list) or not options:
            errors.append(
                f"Gate step {config.get('id', '?')!r}: 'options' must be a non-empty list."
            )
        elif not all(isinstance(o, str) for o in options):
            errors.append(
                f"Gate step {config.get('id', '?')!r}: all options must be strings."
            )
        on_reject = config.get("on_reject", "abort")
        if on_reject not in ("abort", "skip", "retry"):
            errors.append(
                f"Gate step {config.get('id', '?')!r}: 'on_reject' must be "
                f"'abort', 'skip', or 'retry'."
            )
        if on_reject in ("abort", "retry") and isinstance(options, list):
            reject_choices = {"reject", "abort"}
            if not any(o.lower() in reject_choices for o in options):
                errors.append(
                    f"Gate step {config.get('id', '?')!r}: on_reject={on_reject!r} "
                    f"but options has no 'reject' or 'abort' choice."
                )
        check_cmd = config.get("check")
        if check_cmd is not None and not isinstance(check_cmd, str):
            errors.append(
                f"Gate step {config.get('id', '?')!r}: 'check' must be a string "
                f"shell command."
            )
        on_check_fail = config.get("on_check_fail", "block")
        if on_check_fail not in ("block", "warn"):
            errors.append(
                f"Gate step {config.get('id', '?')!r}: 'on_check_fail' must be "
                f"'block' or 'warn'."
            )
        return errors
