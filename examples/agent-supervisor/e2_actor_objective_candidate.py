"""Deterministic E2 fixture that adds one bounded BC term."""


def combine_actor_objective(actor_loss, bc_loss, bc_weight):
    return actor_loss + bc_weight * bc_loss + 0.1 * bc_loss
