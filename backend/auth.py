# File: backend/auth.py
"""
Authentication and Authorization Module
Supports API Key and JWT authentication with rate limiting
"""

import os
import time
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from enum import Enum
from functools import wraps
from collections import defaultdict

from fastapi import HTTPException, Security, Depends, Request, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt

# ==========================================
# CONFIGURATION
# ==========================================

# Load from environment
API_KEY_SECRET = os.getenv("API_KEY_SECRET", secrets.token_hex(32))
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

# Auth mode: "disabled", "api_key", "jwt", "both"
AUTH_MODE = os.getenv("AUTH_MODE", "api_key").lower()

# Default API keys (comma-separated in env)
# Format: key1:role1,key2:role2
# Roles: admin, trader, readonly
DEFAULT_API_KEYS = os.getenv("API_KEYS", "")


class UserRole(str, Enum):
    ADMIN = "admin"      # Full access
    TRADER = "trader"    # Can trade, no admin functions
    READONLY = "readonly"  # View only


class AuthUser(BaseModel):
    """Authenticated user info"""
    user_id: str
    role: UserRole
    api_key_hash: Optional[str] = None
    

# ==========================================
# API KEY STORE
# ==========================================

class APIKeyStore:
    """
    In-memory API key store.
    In production, use database or secrets manager.
    """
    
    def __init__(self):
        self._keys: Dict[str, Tuple[str, UserRole]] = {}  # hash -> (user_id, role)
        self._load_default_keys()
    
    def _load_default_keys(self):
        """Load API keys from environment."""
        if not DEFAULT_API_KEYS:
            # Generate a default admin key if none provided
            default_key = os.getenv("BOT_API_KEY", "")
            if default_key:
                self.add_key(default_key, "default_admin", UserRole.ADMIN)
            return
        
        for entry in DEFAULT_API_KEYS.split(","):
            entry = entry.strip()
            if ":" in entry:
                key, role_str = entry.split(":", 1)
                role = UserRole(role_str.lower()) if role_str.lower() in [r.value for r in UserRole] else UserRole.READONLY
                self.add_key(key.strip(), f"user_{len(self._keys)}", role)
            else:
                self.add_key(entry, f"user_{len(self._keys)}", UserRole.TRADER)
    
    def _hash_key(self, api_key: str) -> str:
        """Hash API key for storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def add_key(self, api_key: str, user_id: str, role: UserRole):
        """Add or update an API key."""
        key_hash = self._hash_key(api_key)
        self._keys[key_hash] = (user_id, role)
    
    def validate_key(self, api_key: str) -> Optional[AuthUser]:
        """Validate API key and return user info."""
        key_hash = self._hash_key(api_key)
        if key_hash in self._keys:
            user_id, role = self._keys[key_hash]
            return AuthUser(user_id=user_id, role=role, api_key_hash=key_hash)
        return None
    
    def revoke_key(self, api_key: str) -> bool:
        """Revoke an API key."""
        key_hash = self._hash_key(api_key)
        if key_hash in self._keys:
            del self._keys[key_hash]
            return True
        return False


# Global API key store
api_key_store = APIKeyStore()


# ==========================================
# RATE LIMITER
# ==========================================

class RateLimiter:
    """
    Token bucket rate limiter per API key/IP.
    """
    
    def __init__(self):
        # Rate limits per role (requests per minute)
        self.limits: Dict[UserRole, int] = {
            UserRole.ADMIN: 300,
            UserRole.TRADER: 120,
            UserRole.READONLY: 60,
        }
        self.default_limit = 30  # For unauthenticated (if allowed)
        
        # Buckets: {identifier: {"tokens": float, "last_update": float}}
        self._buckets: Dict[str, Dict] = defaultdict(lambda: {"tokens": 0, "last_update": time.time()})
        self._lock_time: Dict[str, float] = {}  # Lockout timestamps
    
    def _get_bucket(self, identifier: str, limit: int) -> Dict:
        """Get or create a bucket for identifier."""
        bucket = self._buckets[identifier]
        now = time.time()
        
        # Refill tokens based on time passed
        time_passed = now - bucket["last_update"]
        tokens_to_add = time_passed * (limit / 60.0)  # tokens per second
        bucket["tokens"] = min(limit, bucket["tokens"] + tokens_to_add)
        bucket["last_update"] = now
        
        return bucket
    
    def check_rate_limit(self, identifier: str, role: Optional[UserRole] = None) -> Tuple[bool, Dict]:
        """
        Check if request is within rate limit.
        Returns (allowed, info_dict).
        """
        # Check if locked out
        if identifier in self._lock_time:
            if time.time() < self._lock_time[identifier]:
                remaining = int(self._lock_time[identifier] - time.time())
                return False, {"locked": True, "retry_after": remaining}
            else:
                del self._lock_time[identifier]
        
        limit = self.limits.get(role, self.default_limit) if role else self.default_limit
        bucket = self._get_bucket(identifier, limit)
        
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True, {
                "limit": limit,
                "remaining": int(bucket["tokens"]),
                "reset_in": int(60 - (time.time() - bucket["last_update"]) % 60)
            }
        
        # Rate limited - lock for a short period
        self._lock_time[identifier] = time.time() + 10  # 10 second lockout
        return False, {"limit": limit, "remaining": 0, "retry_after": 10}
    
    def get_identifier(self, request: Request, user: Optional[AuthUser] = None) -> str:
        """Get rate limit identifier from request."""
        if user and user.api_key_hash:
            return f"key:{user.api_key_hash[:16]}"
        # Fall back to IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        return f"ip:{request.client.host if request.client else 'unknown'}"


# Global rate limiter
rate_limiter = RateLimiter()


# ==========================================
# SECURITY SCHEMES
# ==========================================

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


# ==========================================
# JWT UTILITIES
# ==========================================

def create_jwt_token(user_id: str, role: UserRole, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT token."""
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=JWT_EXPIRY_HOURS))
    payload = {
        "sub": user_id,
        "role": role.value,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> Optional[AuthUser]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return AuthUser(
            user_id=payload["sub"],
            role=UserRole(payload["role"]),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        return None


# ==========================================
# DEPENDENCY FUNCTIONS
# ==========================================

async def get_api_key(api_key: str = Security(api_key_header)) -> Optional[str]:
    """Extract API key from header."""
    return api_key


async def get_bearer_token(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)
) -> Optional[str]:
    """Extract Bearer token from header."""
    if credentials:
        return credentials.credentials
    return None


async def get_current_user(
    request: Request,
    api_key: Optional[str] = Depends(get_api_key),
    token: Optional[str] = Depends(get_bearer_token),
) -> Optional[AuthUser]:
    """
    Get current authenticated user from API key or JWT.
    Returns None if auth is disabled or no valid credentials.
    """
    if AUTH_MODE == "disabled":
        # Return a default admin user when auth is disabled
        return AuthUser(user_id="anonymous", role=UserRole.ADMIN)
    
    user = None
    
    # Try API key first
    if api_key and AUTH_MODE in ("api_key", "both"):
        user = api_key_store.validate_key(api_key)
    
    # Try JWT token
    if not user and token and AUTH_MODE in ("jwt", "both"):
        user = decode_jwt_token(token)
    
    return user


async def require_auth(
    request: Request,
    user: Optional[AuthUser] = Depends(get_current_user),
) -> AuthUser:
    """Require authentication - raises 401 if not authenticated."""
    if AUTH_MODE == "disabled":
        return AuthUser(user_id="anonymous", role=UserRole.ADMIN)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication",
            headers={"WWW-Authenticate": "Bearer, ApiKey"},
        )
    
    # Check rate limit
    identifier = rate_limiter.get_identifier(request, user)
    allowed, info = rate_limiter.check_rate_limit(identifier, user.role)
    
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {info.get('retry_after', 10)} seconds",
            headers={"Retry-After": str(info.get("retry_after", 10))},
        )
    
    return user


async def require_role(required_roles: list[UserRole]):
    """Factory for role-based access control."""
    async def check_role(user: AuthUser = Depends(require_auth)) -> AuthUser:
        if user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {[r.value for r in required_roles]}",
            )
        return user
    return check_role


# ==========================================
# PRE-BUILT DEPENDENCIES
# ==========================================

async def require_admin(user: AuthUser = Depends(require_auth)) -> AuthUser:
    """Require admin role."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_trader(user: AuthUser = Depends(require_auth)) -> AuthUser:
    """Require trader or admin role."""
    if user.role not in (UserRole.ADMIN, UserRole.TRADER):
        raise HTTPException(status_code=403, detail="Trader access required")
    return user


async def optional_auth(
    request: Request,
    user: Optional[AuthUser] = Depends(get_current_user),
) -> Optional[AuthUser]:
    """Optional authentication - for read-only endpoints."""
    if AUTH_MODE == "disabled":
        return AuthUser(user_id="anonymous", role=UserRole.ADMIN)
    
    # Still check rate limit for unauthenticated users
    if not user:
        identifier = rate_limiter.get_identifier(request)
        allowed, info = rate_limiter.check_rate_limit(identifier)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry after {info.get('retry_after', 10)} seconds",
            )
    
    return user


# ==========================================
# AUTH ENDPOINTS (for JWT login)
# ==========================================

class LoginRequest(BaseModel):
    api_key: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


def create_auth_router():
    """Create auth router with login endpoint."""
    from fastapi import APIRouter
    
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    
    @router.post("/login", response_model=TokenResponse)
    async def login(req: LoginRequest):
        """Exchange API key for JWT token."""
        user = api_key_store.validate_key(req.api_key)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        token = create_jwt_token(user.user_id, user.role)
        return TokenResponse(
            access_token=token,
            expires_in=JWT_EXPIRY_HOURS * 3600,
            role=user.role.value,
        )
    
    @router.get("/me")
    async def get_me(user: AuthUser = Depends(require_auth)):
        """Get current user info."""
        return {
            "user_id": user.user_id,
            "role": user.role.value,
        }
    
    @router.get("/status")
    async def auth_status():
        """Get auth configuration status (public)."""
        return {
            "auth_mode": AUTH_MODE,
            "auth_enabled": AUTH_MODE != "disabled",
            "jwt_enabled": AUTH_MODE in ("jwt", "both"),
            "api_key_enabled": AUTH_MODE in ("api_key", "both"),
        }
    
    return router


# Export auth router
auth_router = create_auth_router()
