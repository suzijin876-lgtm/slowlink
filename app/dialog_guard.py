def should_keep_existing_dialog_cache(
    old_count: int,
    new_count: int,
    min_keep_ratio: float = 0.85,
    min_old_count: int = 50,
) -> bool:
    """Return True when a refreshed dialog list looks like a partial fetch."""
    try:
        old_count = int(old_count or 0)
        new_count = int(new_count or 0)
        min_keep_ratio = float(min_keep_ratio or 0.85)
        min_old_count = int(min_old_count or 50)
    except Exception:
        return False
    if old_count < min_old_count:
        return False
    if new_count <= 0:
        return True
    return new_count < old_count * min_keep_ratio
