from __future__ import annotations

import os

# Set test env vars before any prism imports
os.environ.setdefault("PRISM_ENV", "dev")
os.environ.setdefault("PRISM_DATABASE_URL", "mysql+aiomysql://prism:prism@localhost:3306/prism_test")
os.environ.setdefault("PRISM_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault(
    "PRISM_TOKEN_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
)
os.environ.setdefault("PRISM_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
