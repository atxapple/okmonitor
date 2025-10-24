# OK Monitor SaaS - Architecture Specification

**Version:** 2.0.0 (Multi-Tenant SaaS)
**Status:** Foundation Document
**Last Updated:** 2025-10-23
**Repository:** okmonitor-saas (forked from okmonitor)

---

## Table of Contents

1. [System Overview](#system-overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Database Schema](#database-schema)
4. [Authentication & Security](#authentication--security)
5. [Multi-Tenancy & Data Isolation](#multi-tenancy--data-isolation)
6. [Device Management](#device-management)
7. [API Design](#api-design)
8. [Storage Architecture](#storage-architecture)
9. [WebSocket Real-Time Updates](#websocket-real-time-updates)
10. [Scalability & Performance](#scalability--performance)
11. [Migration Strategy](#migration-strategy)
12. [Development Roadmap](#development-roadmap)

---

## System Overview

### Product Vision

**OK Monitor SaaS** is a multi-tenant, cloud-based monitoring platform that allows individual users to monitor multiple cameras/devices with AI-powered anomaly detection. Each user has their own isolated account, can register multiple devices, and receives real-time alerts when anomalies are detected.

### Key Differences from Single-Tenant Version

| Aspect | Single-Tenant (okmonitor) | Multi-Tenant (okmonitor-saas) |
|--------|---------------------------|-------------------------------|
| **Users** | Single user per deployment | Multiple users per deployment |
| **Authentication** | None (URL access) | Login/password required |
| **Database** | File-based (JSON) | PostgreSQL |
| **Device Ownership** | Implicit (config file) | Explicit (pairing flow) |
| **Data Storage** | `/datalake/YYYY/MM/DD/` | `/datalake/{user_id}/YYYY/MM/DD/` |
| **Deployment** | One instance per user | One instance serves all users |
| **Configuration** | `.env` file | Database + per-user settings |

### Target Users

- **Primary:** Individuals managing 1-5 home/office cameras
- **Secondary:** Small businesses monitoring multiple locations
- **Scale:** 20-100 users initially, 1000+ users long-term

### Core Use Cases

1. **User Registration**: New user signs up with email/password
2. **Device Pairing**: User generates pairing code, enters on Raspberry Pi
3. **Multi-Camera Monitoring**: User switches between multiple cameras in UI
4. **Real-Time Alerts**: User receives WebSocket push notifications on anomalies
5. **Historical Review**: User browses past captures, filters by state/date

---

## High-Level Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         Users (Web Browser)                      │
│  https://okmonitor-saas.com/dashboard                           │
│  - Authentication (JWT in cookie)                               │
│  - Multi-device selector                                        │
│  - Real-time WebSocket updates                                  │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ HTTPS + WebSocket (wss://)
                 │
┌────────────────▼────────────────────────────────────────────────┐
│                    Cloud Server (Railway)                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FastAPI Application (Python)                            │  │
│  │  - Authentication middleware (JWT validation)            │  │
│  │  - Multi-tenancy query filters (user_id isolation)       │  │
│  │  - Device management API                                 │  │
│  │  - Capture ingestion + AI classification                 │  │
│  │  - WebSocket hub (per-user channels)                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  PostgreSQL Database                                      │  │
│  │  - Users (email, password_hash)                          │  │
│  │  - Devices (device_id, user_id, name)                    │  │
│  │  - Captures metadata (record_id, user_id, device_id)     │  │
│  │  - Pairing tokens (code, user_id, expires_at)            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Filesystem Storage (Railway Volume)                      │  │
│  │  /datalake/{user_id}/{YYYY}/{MM}/{DD}/{record_id}.jpeg   │  │
│  │  /config/{user_id}/normal_description.txt                │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ HTTPS API calls
                 │
┌────────────────▼────────────────────────────────────────────────┐
│              Raspberry Pi Devices (Edge)                         │
│  - Camera capture (OpenCV)                                      │
│  - Device ID + Pairing Token                                    │
│  - Sends JPEG + metadata to cloud                              │
│  - Auto-update from GitHub main branch                          │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Device Capture Flow
   ┌──────────┐
   │ Camera   │ captures image
   └────┬─────┘
        │
        ▼
   ┌──────────┐
   │ Device   │ POST /v1/captures
   │ (RPi)    │ {device_id, image_base64, pairing_token (if unclaimed)}
   └────┬─────┘
        │
        ▼
   ┌──────────┐
   │ Cloud    │ 1. Validate device ownership (device_id → user_id)
   │ Server   │ 2. AI classification (normal/abnormal)
   └────┬─────┘ 3. Store: DB metadata + filesystem image
        │      4. Publish WebSocket event to user's channel
        │
        ├──────────────────────┬──────────────────────┐
        ▼                      ▼                      ▼
   ┌──────────┐          ┌──────────┐          ┌──────────┐
   │PostgreSQL│          │Filesystem│          │WebSocket │
   │ INSERT   │          │ Write    │          │ Publish  │
   │ captures │          │ .jpeg    │          │ {event}  │
   └──────────┘          └──────────┘          └────┬─────┘
                                                     │
                                                     ▼
                                              ┌──────────┐
                                              │ User's   │
                                              │ Browser  │
                                              │ UI update│
                                              └──────────┘

2. User Authentication Flow
   ┌──────────┐
   │ Browser  │ POST /api/auth/login {email, password}
   └────┬─────┘
        │
        ▼
   ┌──────────┐
   │ Server   │ 1. Query users table
   └────┬─────┘ 2. Verify password (bcrypt)
        │      3. Generate JWT (user_id, email, exp)
        │      4. Set httpOnly cookie
        │
        ▼
   ┌──────────┐
   │ Browser  │ Future requests include JWT cookie
   └──────────┘ Server validates JWT → extracts user_id
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | FastAPI 0.117+ | High-performance async Python web framework |
| **Database** | PostgreSQL 15+ | Relational database for user data, metadata |
| **ORM** | SQLAlchemy 2.0+ | Database abstraction, migrations |
| **Authentication** | python-jose (JWT) | Token generation, validation |
| **Password Hashing** | passlib (bcrypt) | Secure password storage |
| **Image Processing** | OpenCV, Pillow | Thumbnail generation, image handling |
| **AI Classification** | OpenAI API / Gemini API | Anomaly detection |
| **Real-Time** | WebSocket (FastAPI) | Push notifications to users |
| **Storage** | Railway Volume (filesystem) | Image storage |
| **Deployment** | Railway | Cloud hosting, auto-deploy |
| **Device** | Raspberry Pi 5 + Python | Edge capture device |

---

## Database Schema

### Schema Design Principles

1. **User-centric**: All data tied to `user_id` for isolation
2. **Normalized**: Separate tables for users, devices, captures
3. **Indexed**: Fast queries on user_id, device_id, timestamps
4. **Soft deletes**: Keep deleted records for audit (deleted_at timestamp)
5. **UTC timestamps**: All times in UTC, convert to local in UI

### Entity Relationship Diagram

```
┌─────────────────┐
│     users       │
│─────────────────│
│ id (PK)         │───┐
│ email (UNIQUE)  │   │
│ password_hash   │   │
│ created_at      │   │
│ last_login_at   │   │
└─────────────────┘   │
                      │ 1:N
                      │
        ┌─────────────┴──────────────┐
        │                            │
        ▼                            ▼
┌─────────────────┐        ┌─────────────────┐
│    devices      │        │ pairing_tokens  │
│─────────────────│        │─────────────────│
│ id (PK)         │        │ id (PK)         │
│ user_id (FK)    │        │ user_id (FK)    │───┐
│ device_id       │───┐    │ code (6-digit)  │   │
│ name            │   │    │ created_at      │   │
│ created_at      │   │    │ expires_at      │   │
│ last_seen_at    │   │    │ used_at         │   │
│ deleted_at      │   │    └─────────────────┘   │
└─────────────────┘   │                          │
                      │ 1:N                      │
                      │                          │
                      ▼                          │
              ┌─────────────────┐                │
              │    captures     │                │
              │─────────────────│                │
              │ id (PK)         │                │
              │ record_id (UQ)  │                │
              │ user_id (FK)    │◀───────────────┘
              │ device_id (FK)  │
              │ captured_at     │
              │ ingested_at     │
              │ state           │ (normal/abnormal)
              │ confidence      │
              │ reason          │
              │ image_path      │
              │ thumbnail_path  │
              │ metadata_json   │
              └─────────────────┘
```

### Table Definitions

#### 1. users

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE,

    -- Indexes
    CONSTRAINT users_email_lower_unique UNIQUE (LOWER(email))
);

CREATE INDEX idx_users_email ON users(LOWER(email)) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_created_at ON users(created_at DESC);
```

**Fields:**
- `id`: Auto-increment primary key
- `email`: User's email (login username), case-insensitive unique
- `password_hash`: bcrypt hash of password (60 chars)
- `created_at`: Account creation timestamp
- `last_login_at`: Last successful login (for activity tracking)
- `deleted_at`: Soft delete timestamp (NULL = active)

#### 2. devices

```sql
CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE,

    -- Additional metadata
    ip_address VARCHAR(45),  -- IPv4 or IPv6
    hardware_info JSONB,     -- {model: "RPi5", os: "Bookworm", camera: "USB"}

    CONSTRAINT devices_user_device_unique UNIQUE (user_id, device_id)
);

CREATE INDEX idx_devices_user_id ON devices(user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_devices_device_id ON devices(device_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_devices_last_seen ON devices(last_seen_at DESC);
```

**Fields:**
- `id`: Auto-increment primary key
- `user_id`: Foreign key to users table
- `device_id`: Unique identifier from device (e.g., "rpi-living-room")
- `name`: User-friendly name (e.g., "Living Room Camera")
- `created_at`: When device was paired
- `last_seen_at`: Last API call from device (for online/offline status)
- `deleted_at`: Soft delete (user removed device)
- `ip_address`: Last known IP (for debugging)
- `hardware_info`: JSON metadata about device

#### 3. captures

```sql
CREATE TABLE captures (
    id SERIAL PRIMARY KEY,
    record_id VARCHAR(255) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,

    -- Timestamps
    captured_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ingested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Classification
    state VARCHAR(20) NOT NULL,  -- 'normal' or 'abnormal'
    confidence DECIMAL(5, 4),    -- 0.0000 to 1.0000
    reason TEXT,

    -- Storage paths (relative to datalake root)
    image_path VARCHAR(500),      -- user_123/2025/10/23/device_20251023_abc123.jpeg
    thumbnail_path VARCHAR(500),  -- user_123/2025/10/23/device_20251023_abc123_thumb.jpeg

    -- Metadata
    metadata_json JSONB,  -- {trigger_label, camera_source, timing_data, etc.}

    -- AI model info
    classifier_model VARCHAR(100),  -- "gpt-4o-mini", "gemini-2.5-flash"
    normal_description_snapshot TEXT,  -- Snapshot of normal description used

    CONSTRAINT captures_state_check CHECK (state IN ('normal', 'abnormal'))
);

CREATE INDEX idx_captures_user_id ON captures(user_id, captured_at DESC);
CREATE INDEX idx_captures_device_id ON captures(device_id, captured_at DESC);
CREATE INDEX idx_captures_record_id ON captures(record_id);
CREATE INDEX idx_captures_state ON captures(state, captured_at DESC);
CREATE INDEX idx_captures_captured_at ON captures(captured_at DESC);

-- Composite index for common query pattern
CREATE INDEX idx_captures_user_state_time ON captures(user_id, state, captured_at DESC);
```

**Fields:**
- `id`: Auto-increment primary key
- `record_id`: Unique identifier (format: `{device}_{timestamp}_{hash}`)
- `user_id`: Owner of this capture
- `device_id`: Which device captured this
- `captured_at`: When image was taken (device timestamp)
- `ingested_at`: When server received it
- `state`: Classification result
- `confidence`: AI confidence score (0.0-1.0)
- `reason`: AI explanation text
- `image_path`: Path to full image in filesystem
- `thumbnail_path`: Path to thumbnail
- `metadata_json`: Additional capture metadata
- `classifier_model`: Which AI model was used
- `normal_description_snapshot`: What "normal" definition was active

#### 4. pairing_tokens

```sql
CREATE TABLE pairing_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code VARCHAR(6) NOT NULL UNIQUE,  -- 6-digit numeric code
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL
);

CREATE INDEX idx_pairing_tokens_code ON pairing_tokens(code) WHERE used_at IS NULL;
CREATE INDEX idx_pairing_tokens_user_id ON pairing_tokens(user_id);
CREATE INDEX idx_pairing_tokens_expires_at ON pairing_tokens(expires_at);
```

**Fields:**
- `id`: Auto-increment primary key
- `user_id`: User who generated this token
- `code`: 6-digit pairing code (e.g., "483920")
- `created_at`: When token was generated
- `expires_at`: Token expiry (default: 15 minutes)
- `used_at`: When device successfully paired (NULL = unused)
- `device_id`: Which device used this token

#### 5. user_preferences (Future)

```sql
CREATE TABLE user_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,

    -- UI preferences
    default_device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
    capture_limit INTEGER DEFAULT 12,
    auto_refresh BOOLEAN DEFAULT TRUE,

    -- Notification preferences
    email_alerts_enabled BOOLEAN DEFAULT FALSE,
    alert_cooldown_minutes INTEGER DEFAULT 10,

    -- Preferences JSON (extensible)
    preferences_json JSONB,

    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_user_preferences_user_id ON user_preferences(user_id);
```

### Migration Strategy from File-Based

**Challenge:** Current okmonitor stores everything in files:
- Captures: `/datalake/YYYY/MM/DD/{record_id}.json`
- Config: `config/normal_description.txt`

**Solution:** Migration script that:

1. **Create default user** for existing data
   ```sql
   INSERT INTO users (email, password_hash)
   VALUES ('admin@localhost', '$2b$12$...')
   RETURNING id;  -- e.g., id=1
   ```

2. **Import devices** from existing captures
   ```python
   # Scan all record_ids, extract unique device_ids
   device_ids = set()
   for json_file in Path("/datalake").rglob("*.json"):
       data = json.loads(json_file.read_text())
       device_ids.add(data["metadata"]["device_id"])

   # Create device records
   for device_id in device_ids:
       INSERT INTO devices (user_id, device_id, name)
       VALUES (1, device_id, device_id)
   ```

3. **Import captures** metadata (images stay in place)
   ```python
   for json_file in Path("/datalake").rglob("*.json"):
       data = json.loads(json_file.read_text())

       # Move image to user-specific path
       old_path = json_file.parent / f"{data['record_id']}.jpeg"
       new_path = Path(f"/datalake/user_1/.../{data['record_id']}.jpeg")
       new_path.parent.mkdir(parents=True, exist_ok=True)
       shutil.move(old_path, new_path)

       # Insert into database
       INSERT INTO captures (record_id, user_id, device_id, ...)
       VALUES (data['record_id'], 1, device_id, ...)
   ```

4. **Verification**
   - Count: old files == new DB rows
   - Spot check: random sample matches
   - Test: UI shows all old captures

---

## Authentication & Security

### Authentication Flow

#### 1. User Registration

```
┌─────────┐
│ User    │ POST /api/auth/signup
│ Browser │ {email: "alice@example.com", password: "SecurePass123!"}
└────┬────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Server                                                      │
│                                                             │
│ 1. Validate email format (regex)                           │
│ 2. Check password strength (min 8 chars, mixed case, etc.) │
│ 3. Check email not already registered                      │
│    SELECT id FROM users WHERE email = 'alice@example.com'  │
│                                                             │
│ 4. Hash password with bcrypt (cost factor 12)              │
│    password_hash = bcrypt.hashpw(password, bcrypt.gensalt())│
│                                                             │
│ 5. Insert user record                                      │
│    INSERT INTO users (email, password_hash)                │
│    VALUES ('alice@example.com', '$2b$12$...')              │
│    RETURNING id;                                           │
│                                                             │
│ 6. Generate JWT token                                      │
│    payload = {user_id: 123, email: 'alice@...', exp: ...} │
│    token = jwt.encode(payload, SECRET_KEY)                 │
│                                                             │
│ 7. Set httpOnly cookie                                     │
│    Set-Cookie: auth_token={token}; HttpOnly; Secure; SameSite=Strict│
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────┐
│ Browser │ Redirects to /dashboard
└─────────┘ Future requests include auth_token cookie
```

#### 2. User Login

```
┌─────────┐
│ User    │ POST /api/auth/login
│ Browser │ {email: "alice@example.com", password: "SecurePass123!"}
└────┬────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Server                                                      │
│                                                             │
│ 1. Query user by email (case-insensitive)                  │
│    SELECT id, password_hash FROM users                     │
│    WHERE LOWER(email) = 'alice@example.com'                │
│    AND deleted_at IS NULL;                                 │
│                                                             │
│ 2. Verify password                                         │
│    if not bcrypt.checkpw(password, password_hash):         │
│        return 401 Unauthorized                             │
│                                                             │
│ 3. Update last login timestamp                             │
│    UPDATE users SET last_login_at = NOW()                  │
│    WHERE id = 123;                                         │
│                                                             │
│ 4. Generate JWT token                                      │
│    payload = {                                             │
│        user_id: 123,                                       │
│        email: 'alice@example.com',                         │
│        exp: datetime.utcnow() + timedelta(days=7)          │
│    }                                                       │
│    token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')│
│                                                             │
│ 5. Set httpOnly cookie                                     │
│    Set-Cookie: auth_token={token}; HttpOnly; Secure;       │
│               Max-Age=604800; SameSite=Strict              │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────┐
│ Browser │ Redirects to /dashboard
└─────────┘ Subsequent requests include auth_token cookie
```

#### 3. Authenticated API Requests

```
┌─────────┐
│ Browser │ GET /api/captures?limit=12
└────┬────┘ Cookie: auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Server - Authentication Middleware                         │
│                                                             │
│ 1. Extract token from cookie                               │
│    token = request.cookies.get("auth_token")               │
│                                                             │
│ 2. Decode & validate JWT                                   │
│    payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])│
│    - Verify signature (prevents tampering)                 │
│    - Check expiration (exp < now)                          │
│    - Validate structure (has user_id, email)               │
│                                                             │
│ 3. Load user context                                       │
│    user_id = payload["user_id"]                            │
│    request.state.user_id = user_id                         │
│    request.state.user_email = payload["email"]             │
│                                                             │
│ 4. Pass to route handler                                   │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Route Handler - Automatic User Context                     │
│                                                             │
│ @router.get("/api/captures")                               │
│ async def list_captures(request: Request, limit: int = 12):│
│     user_id = request.state.user_id  # Available!          │
│                                                             │
│     # Query only this user's captures                      │
│     SELECT * FROM captures                                 │
│     WHERE user_id = {user_id}                              │
│     ORDER BY captured_at DESC                              │
│     LIMIT {limit};                                         │
└─────────────────────────────────────────────────────────────┘
```

### Security Implementation Details

#### JWT Configuration

```python
# config/security.py
from datetime import timedelta

# JWT Settings
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")  # MUST be set in .env
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = timedelta(days=7)  # Tokens valid for 7 days

# Cookie Settings
COOKIE_NAME = "auth_token"
COOKIE_HTTPONLY = True  # Prevents JavaScript access (XSS protection)
COOKIE_SECURE = True    # HTTPS only
COOKIE_SAMESITE = "strict"  # CSRF protection
```

**Security Properties:**
- **httpOnly**: JavaScript cannot read token → XSS protection
- **Secure**: Only sent over HTTPS → MITM protection
- **SameSite**: Only sent to same origin → CSRF protection
- **Short-lived**: 7-day expiration → limited breach window

#### Password Requirements

```python
import re

def validate_password(password: str) -> tuple[bool, str]:
    """Validate password meets security requirements."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number"

    # Optional: special characters
    # if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
    #     return False, "Password must contain at least one special character"

    return True, "Password is valid"
```

#### Password Hashing

```python
import bcrypt

def hash_password(password: str) -> str:
    """Hash password using bcrypt with cost factor 12."""
    salt = bcrypt.gensalt(rounds=12)  # 2^12 iterations (secure, ~0.3s)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
```

**Why bcrypt?**
- Industry standard for password hashing
- Automatically salted (prevents rainbow tables)
- Slow by design (prevents brute force)
- Cost factor can be increased as hardware improves

#### Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/api/auth/login")
@limiter.limit("5 per minute")  # Max 5 login attempts per minute per IP
async def login(request: Request, credentials: LoginRequest):
    # ... login logic
    pass

@router.post("/api/auth/signup")
@limiter.limit("3 per hour")  # Max 3 signups per hour per IP
async def signup(request: Request, user_data: SignupRequest):
    # ... signup logic
    pass
```

**Rate Limits:**
- **Login**: 5 attempts/minute (prevents brute force)
- **Signup**: 3 attempts/hour (prevents spam accounts)
- **API calls**: 100 requests/minute per user (prevents abuse)

#### CSRF Protection

**Why needed:** Prevents malicious sites from making authenticated requests

**Solution:** SameSite cookie + CORS configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://okmonitor-saas.com"],  # Only your domain
    allow_credentials=True,  # Allow cookies
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

**Additional:** For state-changing operations (POST/PUT/DELETE), require CSRF token in header:

```python
# Generate CSRF token on login, store in cookie
csrf_token = secrets.token_urlsafe(32)
response.set_cookie("csrf_token", csrf_token, httponly=False)  # JS can read

# Validate on state-changing requests
@router.post("/api/captures/delete")
async def delete_capture(request: Request):
    csrf_from_cookie = request.cookies.get("csrf_token")
    csrf_from_header = request.headers.get("X-CSRF-Token")

    if not csrf_from_cookie or csrf_from_cookie != csrf_from_header:
        raise HTTPException(status_code=403, detail="CSRF token mismatch")
```

---

## Multi-Tenancy & Data Isolation

### Core Principle

**Every database query MUST filter by `user_id`** to ensure users can only access their own data.

### Isolation Layers

#### 1. Database Query Filtering

**Bad (Insecure):**
```python
# NEVER DO THIS - returns all users' captures!
captures = await db.query(Capture).order_by(Capture.captured_at.desc()).limit(12).all()
```

**Good (Secure):**
```python
# ALWAYS filter by user_id
user_id = request.state.user_id
captures = await db.query(Capture)\
    .filter(Capture.user_id == user_id)\
    .order_by(Capture.captured_at.desc())\
    .limit(12)\
    .all()
```

#### 2. ORM Model Base Class

**Automatic user_id filtering using SQLAlchemy:**

```python
# models/base.py
from sqlalchemy import Column, Integer
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import Session

class UserOwnedMixin:
    """Mixin for models that belong to a user."""

    @declared_attr
    def user_id(cls):
        return Column(Integer, nullable=False, index=True)

    @classmethod
    def query_for_user(cls, db: Session, user_id: int):
        """Return query filtered by user_id."""
        return db.query(cls).filter(cls.user_id == user_id)

# models/capture.py
class Capture(Base, UserOwnedMixin):
    __tablename__ = "captures"

    id = Column(Integer, primary_key=True)
    record_id = Column(String, unique=True, nullable=False)
    # user_id comes from UserOwnedMixin
    device_id = Column(Integer, ForeignKey("devices.id"))
    # ... other fields

# Usage in routes
@router.get("/api/captures")
async def list_captures(request: Request, db: Session = Depends(get_db)):
    user_id = request.state.user_id

    # Automatically filtered by user_id
    captures = Capture.query_for_user(db, user_id)\
        .order_by(Capture.captured_at.desc())\
        .limit(12)\
        .all()

    return captures
```

#### 3. Filesystem Isolation

**Directory Structure:**
```
/mnt/data/datalake/
├── user_1/
│   ├── 2025/10/23/
│   │   ├── device1_20251023_abc123.jpeg
│   │   └── device1_20251023_abc123_thumb.jpeg
│   └── 2025/10/24/
│       └── device2_20251024_def456.jpeg
├── user_2/
│   └── 2025/10/23/
│       └── device3_20251023_xyz789.jpeg
└── user_3/
    └── ...
```

**Path Construction:**
```python
def get_user_datalake_path(user_id: int, date: datetime) -> Path:
    """Get datalake path for user on specific date."""
    root = Path("/mnt/data/datalake")
    return root / f"user_{user_id}" / date.strftime("%Y/%m/%d")

def get_image_path(user_id: int, record_id: str, is_thumbnail: bool = False) -> Path:
    """Get full path to image file."""
    # Extract date from record_id (format: device_20251023_hash)
    # Assumes record_id contains date in format YYYYMMDD
    date_str = record_id.split("_")[1][:8]  # "20251023"
    date = datetime.strptime(date_str, "%Y%m%d")

    suffix = "_thumb" if is_thumbnail else ""
    filename = f"{record_id}{suffix}.jpeg"

    return get_user_datalake_path(user_id, date) / filename
```

**Serving Images:**
```python
@router.get("/api/captures/{record_id}/image")
async def serve_image(record_id: str, request: Request, db: Session = Depends(get_db)):
    user_id = request.state.user_id

    # 1. Verify user owns this capture
    capture = db.query(Capture).filter(
        Capture.record_id == record_id,
        Capture.user_id == user_id  # Critical: prevent access to other users' images
    ).first()

    if not capture:
        raise HTTPException(status_code=404, detail="Capture not found")

    # 2. Construct file path
    image_path = Path(capture.image_path)

    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")

    # 3. Serve file
    return FileResponse(image_path, media_type="image/jpeg")
```

#### 4. Configuration Isolation

**Per-User Config Directory:**
```
/mnt/data/config/
├── user_1/
│   ├── normal_description.txt
│   ├── similarity_cache.json
│   └── notifications.json
├── user_2/
│   ├── normal_description.txt
│   └── ...
└── user_3/
    └── ...
```

**Loading User Config:**
```python
def get_user_config_path(user_id: int, filename: str) -> Path:
    """Get path to user-specific config file."""
    root = Path("/mnt/data/config")
    return root / f"user_{user_id}" / filename

def load_user_normal_description(user_id: int) -> str:
    """Load user's normal description."""
    path = get_user_config_path(user_id, "normal_description.txt")

    if not path.exists():
        # Return default
        return "No anomalies detected."

    return path.read_text(encoding="utf-8")
```

### Preventing Data Leaks

#### Security Checklist

✅ **Every database query filters by user_id**
- Use ORM mixins to enforce this
- Never trust client-provided IDs without ownership verification

✅ **Filesystem paths include user_id**
- Images stored under `/datalake/user_{id}/`
- Direct path traversal impossible

✅ **Device ownership verified**
- Capture ingestion checks device belongs to user
- Reject captures from unauthorized devices

✅ **WebSocket channels isolated**
- Each user has separate channel: `user_{id}_captures`
- Users only subscribe to their own channel

✅ **API responses sanitized**
- Never include other users' data in error messages
- Generic "not found" instead of "belongs to another user"

#### Common Vulnerabilities & Mitigations

**1. IDOR (Insecure Direct Object Reference)**

❌ **Vulnerable:**
```python
@router.delete("/api/captures/{capture_id}")
async def delete_capture(capture_id: int, db: Session):
    # Anyone can delete any capture by guessing IDs!
    db.query(Capture).filter(Capture.id == capture_id).delete()
```

✅ **Secure:**
```python
@router.delete("/api/captures/{capture_id}")
async def delete_capture(capture_id: int, request: Request, db: Session):
    user_id = request.state.user_id

    # Verify ownership before delete
    capture = db.query(Capture).filter(
        Capture.id == capture_id,
        Capture.user_id == user_id
    ).first()

    if not capture:
        raise HTTPException(status_code=404, detail="Capture not found")

    db.delete(capture)
    db.commit()
```

**2. Path Traversal**

❌ **Vulnerable:**
```python
# User could request: /api/images/../../user_2/2025/10/23/secret.jpeg
image_path = Path(f"/datalake/{user_provided_path}")
```

✅ **Secure:**
```python
# Always construct paths programmatically, never from user input
image_path = get_image_path(user_id, record_id)

# Additional check
if not image_path.is_relative_to(f"/datalake/user_{user_id}"):
    raise HTTPException(status_code=403, detail="Access denied")
```

**3. SQL Injection**

❌ **Vulnerable:**
```python
# Direct SQL string concatenation
query = f"SELECT * FROM captures WHERE record_id = '{record_id}'"
```

✅ **Secure:**
```python
# Always use parameterized queries (ORM does this automatically)
capture = db.query(Capture).filter(Capture.record_id == record_id).first()
```

---

## Device Management

### Device Lifecycle

```
┌──────────────┐
│  UNCLAIMED   │  Device has device_id but not yet paired
│              │  (first boot, factory reset)
└──────┬───────┘
       │
       │ User generates pairing code
       │ Device sends code in capture request
       │
       ▼
┌──────────────┐
│   CLAIMED    │  Device linked to user_id
│              │  Can send captures
└──────┬───────┘
       │
       │ Device sends regular captures
       │ Updates last_seen_at
       │
       ▼
┌──────────────┐
│    ACTIVE    │  Device actively sending captures
│              │  Online status based on last_seen_at
└──────┬───────┘
       │
       │ User removes device
       │ Set deleted_at timestamp
       │
       ▼
┌──────────────┐
│   REMOVED    │  Soft deleted (can be restored)
│              │  No longer accepts captures
└──────────────┘
```

### Device Pairing Flow

#### User Side (Web UI)

```
┌─────────────────────────────────────────────────────────────┐
│ /dashboard/devices/pair                                     │
│                                                             │
│  Add New Device                                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                             │
│  1. Click "Generate Pairing Code"                           │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │              Pairing Code:  4 8 3 9 2 0            │   │
│  │                                                     │   │
│  │          Valid for 15 minutes                       │   │
│  │                                                     │   │
│  │  [QR Code]  ← Optional: encode URL with token      │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  2. On your Raspberry Pi device, run:                       │
│     sudo nano /opt/okmonitor/.env.device                    │
│                                                             │
│  3. Add this line:                                          │
│     PAIRING_CODE=483920                                     │
│                                                             │
│  4. Restart device:                                         │
│     sudo systemctl restart okmonitor-device                 │
│                                                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                             │
│  Status: ⏳ Waiting for device...                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Backend Flow:**

```python
@router.post("/api/devices/generate-pairing-code")
async def generate_pairing_code(request: Request, db: Session = Depends(get_db)):
    """Generate 6-digit pairing code valid for 15 minutes."""
    user_id = request.state.user_id

    # Generate random 6-digit code
    code = "".join(random.choices("0123456789", k=6))

    # Check for collision (very rare)
    existing = db.query(PairingToken).filter(
        PairingToken.code == code,
        PairingToken.used_at == None
    ).first()

    if existing:
        # Regenerate if collision
        return await generate_pairing_code(request, db)

    # Create token
    token = PairingToken(
        user_id=user_id,
        code=code,
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    db.add(token)
    db.commit()

    return {
        "code": code,
        "expires_at": token.expires_at.isoformat()
    }
```

#### Device Side (Raspberry Pi)

**Modified capture ingestion:**

```python
# device/main.py
def send_capture(frame: Frame, metadata: dict):
    """Send capture to cloud, including pairing code if unclaimed."""

    # Check if device has pairing code in config
    pairing_code = os.environ.get("PAIRING_CODE")

    payload = {
        "device_id": metadata["device_id"],
        "image_base64": base64.b64encode(frame.data).decode(),
        "metadata": metadata,
    }

    # Include pairing code if device is unclaimed
    if pairing_code:
        payload["pairing_code"] = pairing_code

    response = requests.post(f"{API_URL}/v1/captures", json=payload)

    if response.status_code == 200:
        data = response.json()

        # If device was just claimed, remove pairing code
        if data.get("device_claimed"):
            # Remove PAIRING_CODE from .env.device
            remove_pairing_code_from_env()
            logger.info("Device successfully paired!")
```

#### Server Side (Claim Device)

```python
@router.post("/v1/captures")
async def ingest_capture(
    request: CaptureRequest,
    db: Session = Depends(get_db)
):
    """Ingest capture from device, handle pairing if needed."""

    # Check if device exists and is claimed
    device = db.query(Device).filter(
        Device.device_id == request.device_id,
        Device.deleted_at == None
    ).first()

    # If device not claimed, check for pairing code
    if not device:
        if not request.pairing_code:
            raise HTTPException(
                status_code=403,
                detail="Device not claimed. Please provide pairing_code."
            )

        # Validate pairing code
        token = db.query(PairingToken).filter(
            PairingToken.code == request.pairing_code,
            PairingToken.used_at == None,
            PairingToken.expires_at > datetime.utcnow()
        ).first()

        if not token:
            raise HTTPException(
                status_code=403,
                detail="Invalid or expired pairing code"
            )

        # Claim device for user
        device = Device(
            user_id=token.user_id,
            device_id=request.device_id,
            name=f"Camera {request.device_id}",  # Default name
            last_seen_at=datetime.utcnow()
        )
        db.add(device)

        # Mark token as used
        token.used_at = datetime.utcnow()
        token.device_id = device.id

        db.commit()
        db.refresh(device)

        # Notify user via WebSocket
        await notify_device_paired(token.user_id, device)

        return {
            "state": "normal",
            "device_claimed": True,
            "device_name": device.name
        }

    # Device is claimed, proceed with normal capture processing
    user_id = device.user_id

    # ... rest of capture ingestion logic
```

### Device Management API

```python
@router.get("/api/devices")
async def list_devices(request: Request, db: Session = Depends(get_db)):
    """List user's devices."""
    user_id = request.state.user_id

    devices = db.query(Device).filter(
        Device.user_id == user_id,
        Device.deleted_at == None
    ).order_by(Device.created_at.desc()).all()

    return [
        {
            "id": d.id,
            "device_id": d.device_id,
            "name": d.name,
            "created_at": d.created_at.isoformat(),
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "is_online": is_device_online(d.last_seen_at),
            "ip_address": d.ip_address
        }
        for d in devices
    ]

def is_device_online(last_seen: datetime | None) -> bool:
    """Device is online if seen within last 5 minutes."""
    if not last_seen:
        return False
    return (datetime.utcnow() - last_seen).total_seconds() < 300

@router.put("/api/devices/{device_id}/name")
async def rename_device(
    device_id: int,
    new_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Rename a device."""
    user_id = request.state.user_id

    device = db.query(Device).filter(
        Device.id == device_id,
        Device.user_id == user_id
    ).first()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.name = new_name
    db.commit()

    return {"success": True, "name": new_name}

@router.delete("/api/devices/{device_id}")
async def remove_device(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Soft delete a device."""
    user_id = request.state.user_id

    device = db.query(Device).filter(
        Device.id == device_id,
        Device.user_id == user_id
    ).first()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Soft delete
    device.deleted_at = datetime.utcnow()
    db.commit()

    return {"success": True}
```

### Device Selector in UI

**Header Component:**

```html
<!-- In dashboard header -->
<div class="device-selector">
    <label for="device-select">Camera:</label>
    <select id="device-select">
        <option value="all">All Cameras</option>
        <!-- Populated dynamically -->
        <option value="123">Living Room (online)</option>
        <option value="456">Front Door (offline)</option>
    </select>
</div>

<script>
// Load user's devices
async function loadDevices() {
    const response = await fetch('/api/devices');
    const devices = await response.json();

    const select = document.getElementById('device-select');
    select.innerHTML = '<option value="all">All Cameras</option>';

    for (const device of devices) {
        const status = device.is_online ? '🟢' : '🔴';
        const option = document.createElement('option');
        option.value = device.id;
        option.textContent = `${status} ${device.name}`;
        select.appendChild(option);
    }
}

// When device selected, update captures list
document.getElementById('device-select').addEventListener('change', (e) => {
    const deviceId = e.target.value;
    loadCaptures(deviceId);  // Reload captures for selected device
});
</script>
```

**Captures API with Device Filter:**

```python
@router.get("/api/captures")
async def list_captures(
    request: Request,
    device_id: int | None = None,  # NEW: optional device filter
    limit: int = 12,
    db: Session = Depends(get_db)
):
    """List captures, optionally filtered by device."""
    user_id = request.state.user_id

    query = db.query(Capture).filter(Capture.user_id == user_id)

    # Filter by device if specified
    if device_id:
        # Verify user owns this device
        device = db.query(Device).filter(
            Device.id == device_id,
            Device.user_id == user_id
        ).first()

        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        query = query.filter(Capture.device_id == device_id)

    captures = query.order_by(Capture.captured_at.desc()).limit(limit).all()

    return [serialize_capture(c) for c in captures]
```

---

## API Design

### Endpoint Structure

```
Authentication
├── POST   /api/auth/signup          Create new user account
├── POST   /api/auth/login           Login with email/password
├── POST   /api/auth/logout          Logout (clear cookie)
└── GET    /api/auth/me              Get current user info

Device Management
├── GET    /api/devices              List user's devices
├── POST   /api/devices/generate-pairing-code   Generate 6-digit code
├── PUT    /api/devices/{id}/name    Rename device
├── DELETE /api/devices/{id}         Remove device (soft delete)
└── GET    /api/devices/{id}/status  Device online/offline status

Captures
├── POST   /v1/captures              Ingest capture from device
├── GET    /api/captures             List captures (filterable)
├── GET    /api/captures/{id}        Get single capture metadata
├── GET    /api/captures/{id}/image  Serve full image
├── GET    /api/captures/{id}/thumbnail  Serve thumbnail
└── DELETE /api/captures/{id}        Delete capture

Configuration
├── GET    /api/config/normal-description      Get user's normal description
├── PUT    /api/config/normal-description      Update normal description
└── GET    /api/config/preferences   Get user preferences

WebSocket
└── WS     /ws/captures?device_id={id}  Real-time capture notifications
```

### API Conventions

#### Request/Response Format

**Success Response:**
```json
{
  "data": {...},
  "meta": {
    "request_id": "abc-123",
    "timestamp": "2025-10-23T12:00:00Z"
  }
}
```

**Error Response:**
```json
{
  "error": {
    "code": "DEVICE_NOT_FOUND",
    "message": "Device with ID 123 not found",
    "details": {}
  },
  "meta": {
    "request_id": "abc-123",
    "timestamp": "2025-10-23T12:00:00Z"
  }
}
```

#### Authentication Header

**Cookie-based (Primary):**
```
Cookie: auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Bearer token (Alternative, for API clients):**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### Pagination

```
GET /api/captures?limit=20&offset=0&order=desc
```

**Response:**
```json
{
  "data": [...],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 156,
    "has_more": true
  }
}
```

#### Filtering

```
GET /api/captures?device_id=123&state=abnormal&from=2025-10-01&to=2025-10-23
```

---

## Storage Architecture

### Hybrid Storage Model

**Why Hybrid?**
- **PostgreSQL**: Fast queries, relationships, transactions
- **Filesystem**: Efficient image storage, CDN-friendly

### Directory Structure

```
/mnt/data/
├── datalake/                    # User images
│   ├── user_1/
│   │   ├── 2025/10/23/
│   │   │   ├── device1_20251023T120000_abc123.jpeg      # Full image
│   │   │   ├── device1_20251023T120000_abc123_thumb.jpeg # Thumbnail
│   │   │   └── device1_20251023T120500_def456.jpeg
│   │   └── 2025/10/24/
│   │       └── ...
│   ├── user_2/
│   │   └── 2025/10/23/
│   │       └── ...
│   └── user_N/
│       └── ...
│
├── config/                      # User configurations
│   ├── user_1/
│   │   ├── normal_description.txt
│   │   ├── similarity_cache.json
│   │   └── notifications.json
│   ├── user_2/
│   │   └── ...
│   └── server_config.json       # Global server config
│
└── backups/                     # Database backups
    ├── 2025-10-23_daily.sql.gz
    └── ...
```

### Storage Limits

**Per User:**
- **Images**: 10 GB (approximately 50,000 captures at 200 KB each)
- **Database**: 100 MB (metadata for millions of captures)

**Enforcement:**
```python
async def check_user_storage_quota(user_id: int, db: Session) -> bool:
    """Check if user has exceeded storage quota."""

    # Calculate total storage used
    user_path = Path(f"/mnt/data/datalake/user_{user_id}")

    if not user_path.exists():
        return True  # No storage used yet

    total_bytes = sum(
        f.stat().st_size
        for f in user_path.rglob("*.jpeg")
    )

    total_gb = total_bytes / (1024 ** 3)

    QUOTA_GB = 10

    if total_gb >= QUOTA_GB:
        logger.warning(f"User {user_id} exceeded storage quota: {total_gb:.2f} GB")
        return False

    return True

# In capture ingestion
if not await check_user_storage_quota(user_id, db):
    raise HTTPException(
        status_code=507,  # Insufficient Storage
        detail="Storage quota exceeded. Please delete old captures or upgrade plan."
    )
```

### Retention & Cleanup

**Automatic Cleanup (Optional Feature):**

```python
# Background task (runs daily at 3 AM)
async def cleanup_old_captures():
    """Delete captures older than retention period."""

    # Get all users
    users = db.query(User).filter(User.deleted_at == None).all()

    for user in users:
        # Get user's retention policy (default: 90 days)
        retention_days = 90  # TODO: make configurable per user

        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        # Find old captures
        old_captures = db.query(Capture).filter(
            Capture.user_id == user.id,
            Capture.captured_at < cutoff_date
        ).all()

        for capture in old_captures:
            # Delete files
            if capture.image_path:
                Path(capture.image_path).unlink(missing_ok=True)
            if capture.thumbnail_path:
                Path(capture.thumbnail_path).unlink(missing_ok=True)

            # Delete DB record
            db.delete(capture)

        db.commit()
        logger.info(f"Cleaned up {len(old_captures)} old captures for user {user.id}")
```

---

## WebSocket Real-Time Updates

### Architecture

**Per-User Channels:**
```
user_1_captures  → Only user 1's capture events
user_2_captures  → Only user 2's capture events
user_N_captures  → Only user N's capture events
```

### WebSocket Authentication

```python
@app.websocket("/ws/captures")
async def websocket_captures(
    websocket: WebSocket,
    device_id: int | None = None,
    db: Session = Depends(get_db)
):
    """WebSocket endpoint with JWT authentication."""

    # 1. Extract JWT from query parameter or cookie
    token = websocket.query_params.get("token") or websocket.cookies.get("auth_token")

    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    # 2. Validate JWT
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload["user_id"]
    except jwt.ExpiredSignatureError:
        await websocket.close(code=1008, reason="Token expired")
        return
    except jwt.InvalidTokenError:
        await websocket.close(code=1008, reason="Invalid token")
        return

    # 3. Accept connection
    await websocket.accept()

    # 4. Determine channel
    if device_id:
        # Verify user owns this device
        device = db.query(Device).filter(
            Device.id == device_id,
            Device.user_id == user_id
        ).first()

        if not device:
            await websocket.close(code=1008, reason="Device not found")
            return

        channel_key = f"user_{user_id}_device_{device_id}"
    else:
        # All devices for this user
        channel_key = f"user_{user_id}_all"

    # 5. Subscribe to channel
    queue = await capture_hub.subscribe(channel_key)
    logger.info(f"WebSocket connected: {channel_key}")

    try:
        await websocket.send_json({"event": "connected", "channel": channel_key})

        while True:
            message = await queue.get()

            if message == _QUEUE_SHUTDOWN:
                break

            try:
                data = json.loads(message) if isinstance(message, str) else message
                await websocket.send_json(data)
            except WebSocketDisconnect:
                break
            except Exception as exc:
                logger.warning(f"Failed to send WebSocket message: {exc}")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {channel_key}")
    finally:
        await capture_hub.unsubscribe(channel_key, queue)
```

### Publishing Events

```python
# In capture ingestion
async def publish_capture_event(user_id: int, device_id: int, capture_data: dict):
    """Publish capture event to user's WebSocket channels."""

    event_payload = {
        "event": "capture",
        "device_id": device_id,
        "record_id": capture_data["record_id"],
        "state": capture_data["state"],
        "captured_at": capture_data["captured_at"]
    }

    # Publish to user's "all devices" channel
    await capture_hub.publish(f"user_{user_id}_all", event_payload)

    # Also publish to device-specific channel
    await capture_hub.publish(f"user_{user_id}_device_{device_id}", event_payload)
```

---

## Scalability & Performance

### Database Optimization

**Connection Pooling:**
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,           # Keep 10 connections open
    max_overflow=20,        # Allow 20 additional connections under load
    pool_pre_ping=True,     # Verify connection before using
    pool_recycle=3600       # Recycle connections every hour
)
```

**Query Optimization:**
- All foreign keys indexed
- Composite index on `(user_id, captured_at DESC)` for fast queries
- EXPLAIN ANALYZE on slow queries

**Caching Strategy:**
```python
from functools import lru_cache
import redis

# Redis for session data and hot data
redis_client = redis.Redis(host='localhost', port=6379, db=0)

@lru_cache(maxsize=1000)
def get_user_normal_description(user_id: int) -> str:
    """Cached user normal description (in-memory)."""
    # Cache for 5 minutes in memory
    return load_user_normal_description(user_id)

async def get_user_devices_cached(user_id: int) -> list[Device]:
    """Cached device list (Redis)."""
    cache_key = f"devices:user_{user_id}"

    # Check cache
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Query database
    devices = db.query(Device).filter(
        Device.user_id == user_id,
        Device.deleted_at == None
    ).all()

    # Cache for 1 minute
    redis_client.setex(cache_key, 60, json.dumps([d.dict() for d in devices]))

    return devices
```

### Horizontal Scaling

**Stateless Design:**
- No session state stored in app memory
- JWT tokens enable any server to authenticate
- WebSocket connections can be on separate servers

**Load Balancing:**
```
           ┌─────────────┐
           │ Load        │
           │ Balancer    │
           │ (Railway)   │
           └──────┬──────┘
                  │
      ┌───────────┼───────────┐
      ▼           ▼           ▼
┌─────────┐ ┌─────────┐ ┌─────────┐
│ App     │ │ App     │ │ App     │
│ Server  │ │ Server  │ │ Server  │
│ (1)     │ │ (2)     │ │ (3)     │
└────┬────┘ └────┬────┘ └────┬────┘
     │           │           │
     └───────────┼───────────┘
                 ▼
          ┌─────────────┐
          │ PostgreSQL  │
          │ (shared)    │
          └─────────────┘
```

**Shared Filesystem:**
- Railway persistent volumes accessible by all instances
- Eventual consistency (writes take ~1s to propagate)

### Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| **API response time** | < 100ms | 95th percentile for GET requests |
| **Capture ingestion** | < 2s | Device POST to DB commit |
| **WebSocket latency** | < 500ms | Event publish to user receipt |
| **Database queries** | < 50ms | 99th percentile |
| **Image serving** | < 200ms | Thumbnail, from filesystem |
| **Page load** | < 1s | Dashboard with 12 captures |

---

## Migration Strategy

### Phase 1: Database Setup

1. **Create PostgreSQL database on Railway**
   ```bash
   railway postgres create
   ```

2. **Run migrations**
   ```bash
   alembic upgrade head
   ```

3. **Create default admin user**
   ```python
   python scripts/create_admin_user.py
   ```

### Phase 2: Data Migration

1. **Migrate existing captures**
   ```python
   python scripts/migrate_captures_to_db.py \
       --source /mnt/data/datalake \
       --admin-user-id 1
   ```

2. **Move images to user-specific paths**
   ```bash
   # Old: /datalake/2025/10/23/device_20251023_abc123.jpeg
   # New: /datalake/user_1/2025/10/23/device_20251023_abc123.jpeg
   ```

3. **Verify data integrity**
   ```bash
   python scripts/verify_migration.py
   ```

### Phase 3: Deployment

1. **Deploy new code to staging**
2. **Test authentication flow**
3. **Test device pairing**
4. **Test multi-user isolation**
5. **Deploy to production**

### Backward Compatibility

**Existing single-tenant deployments:**
- Stay on `okmonitor` repo (original)
- Continue receiving bug fixes
- Optional migration to okmonitor-saas

**No breaking changes to device code:**
- Devices can work with both single and multi-tenant servers
- Pairing code is optional (backward compatible)

---

## Development Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [x] Architecture document
- [ ] Database schema implementation
- [ ] Alembic migration setup
- [ ] User model + authentication
- [ ] JWT middleware

### Phase 2: Core Features (Weeks 3-4)
- [ ] Signup/login endpoints
- [ ] Multi-tenancy query filtering
- [ ] Device pairing flow
- [ ] User-specific datalake paths

### Phase 3: UI Updates (Weeks 5-6)
- [ ] Login/signup pages
- [ ] Device management page
- [ ] Device selector in header
- [ ] WebSocket authentication

### Phase 4: Testing & Security (Week 7)
- [ ] Security audit
- [ ] Data isolation tests
- [ ] Rate limiting
- [ ] Performance testing

### Phase 5: Migration & Deployment (Week 8)
- [ ] Migration scripts
- [ ] Staging deployment
- [ ] Production deployment
- [ ] Documentation

---

## Conclusion

This architecture provides a solid foundation for **okmonitor-saas** that:

✅ **Scales** to 1000+ users per deployment
✅ **Secures** user data with industry-standard practices
✅ **Isolates** users with multiple layers of protection
✅ **Maintains** backward compatibility with single-tenant version
✅ **Supports** future features (teams, billing, etc.)

The hybrid storage model (PostgreSQL + filesystem) provides the best of both worlds: fast queries and efficient image storage. The authentication system is secure and user-friendly. The multi-tenancy design ensures complete data isolation.

**Next Steps:** Begin Phase 1 implementation - database schema and authentication layer.

---

**Document Status:** ✅ Complete
**Review Status:** Pending stakeholder review
**Implementation Status:** Not started
