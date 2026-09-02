"""Default editable objective: equivalent to the frozen linear combination."""


def combine_actor_objective(actor_loss, bc_loss, bc_weight):
    """Return actor_loss + bc_weight * bc_loss without casting the inputs."""

    return actor_loss + bc_weight * bc_loss
