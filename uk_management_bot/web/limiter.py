"""
Shared rate limiter for web application
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

web_limiter = Limiter(key_func=get_remote_address)
