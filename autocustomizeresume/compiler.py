"""LaTeX compiler: invokes tectonic and enforces 1-page limit.

Compiles .tex to PDF via tectonic, checks page count, and retries
by dropping lowest-scored optional items if the result exceeds 1 page.
"""
