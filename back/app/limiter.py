import os
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address

load_dotenv()

is_enabled = os.environ.get("RATE_LIMIT_ENABLED", "").lower() == "true"
limiter = Limiter(key_func=get_remote_address, enabled=is_enabled)
