"""Validation for bounded, resumable Modal Candidate segments."""

from __future__ import annotations


def validate_candidate_segment(
    *,
    resume_step: int,
    max_steps: int,
    val_check_interval: int,
    save_interval: int,
) -> None:
    """Reject schedules that RLinf would fail only after an expensive rollout."""

    if resume_step < 0:
        raise ValueError("resume_step must be non-negative")
    if max_steps <= resume_step:
        raise ValueError("max_steps must be greater than the resumed step")
    if save_interval <= 0:
        raise ValueError("save_interval must be positive for a resumable segment")
    if val_check_interval == 0 or val_check_interval < -1:
        raise ValueError("val_check_interval must be -1 or a positive integer")
    if val_check_interval > 0 and save_interval % val_check_interval != 0:
        raise ValueError(
            "RLinf requires save_interval to be divisible by val_check_interval"
        )
    if max_steps % save_interval != 0:
        raise ValueError("the segment endpoint must produce a checkpoint")
    if val_check_interval > 0 and max_steps % val_check_interval != 0:
        raise ValueError("an evaluation segment must evaluate at its endpoint")
