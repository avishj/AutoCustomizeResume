"""Content selector: decides which optional items to include.

Uses LLM to score optional resume items against the JD and
pick the best set. Reorders skills to front-load relevant ones.
Never rewords or modifies any text.
"""
