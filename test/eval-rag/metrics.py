def est_pertinent(chunk, q):
    """Check if at least 2 criteria match in the chunk content."""
    txt = (chunk.get("contenu", "") + " " + chunk.get("source", "")).lower()
    return sum(1 for c in q["criteres"] if c.lower() in txt) >= 2


def mrr_at_k(flags, k):
    """Mean Reciprocal Rank @ K — returns 1/rank of first hit or 0."""
    for i, ok in enumerate(flags[:k]):
        if ok:
            return 1.0 / (i + 1)
    return 0.0


def recall_at_k(flags, k):
    """Recall @ K — proportion of relevant results in top K."""
    tot = sum(flags)
    return sum(flags[:k]) / tot if tot else 0.0
