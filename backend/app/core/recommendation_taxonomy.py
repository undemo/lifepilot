"""
Deprecated compatibility wrapper.

The canonical recommendation taxonomy lives in:
app.rules.recommendation_taxonomy

New code should import from app.rules.recommendation_taxonomy.
"""

from app.rules.recommendation_taxonomy import *  # noqa: F401,F403
