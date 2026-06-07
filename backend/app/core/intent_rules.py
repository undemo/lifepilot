"""
Deprecated compatibility wrapper.

The canonical intent rules live in:
app.rules.intent_rules

New code should import from app.rules.intent_rules.
"""

from app.rules.intent_rules import *  # noqa: F401,F403
