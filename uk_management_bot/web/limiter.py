"""Rate limiter for the standalone invite-registration web app.

Single-process app → in-memory storage is correct here (no Redis needed).
Only the key function is shared with the API limiter — imported from
``rate_limit_keys`` (side-effect-free) so this import does NOT construct the
API's Redis-backed limiter.
"""
from slowapi import Limiter

from uk_management_bot.api.rate_limit_keys import client_ip_key

web_limiter = Limiter(key_func=client_ip_key)
