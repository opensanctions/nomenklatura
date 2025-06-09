def penalize(score: float, penalty: float) -> float:
    """
    Apply a penalty to a score.

    Args:
        score (float): The original score.
        penalty (float): The penalty to apply.

    Returns:
        float: The penalized score.
    """
    detract = 1 - penalty
    return score * detract
