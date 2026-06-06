# JWT Authentication System — DPA QA Manager

## Overview

ระบบ Authentication ที่ปรับปรุงจาก Plain-text session เป็น JWT (JSON Web Token) พร้อม Register page ออกแบบตาม Cal.com Design System

---

## Architecture

```
Frontend (React)                Backend (FastAPI)
─────────────────               ─────────────────────────
LoginPage.jsx      ──POST──▶   /api/auth/login
RegisterPage.jsx   ──POST──▶   /api/auth/register
apiFetch()         ──Bearer──▶  All protected /api/* routes
App.jsx (401 hook) ◀──401────  Auto-logout on expired token
```

---

## Files Changed / Created

### Backend

| File | Type | Description |
|------|------|-------------|
| `backend/requirements.txt` | Modified | เพิ่ม `python-jose[cryptography]` และ `passlib[bcrypt]` |
| `backend/services/auth_service.py` | **New** | JWT encode/decode, bcrypt hash/verify, plain-text fallback |
| `backend/routers/auth.py` | **New** | Login และ Register endpoints |
| `backend/models/schemas.py` | Modified | เพิ่ม `RegisterRequest`, `TokenResponse` |
| `backend/main.py` | Modified | Register `auth_router` |
| `backend/routers/product_request.py` | Modified | ลบ `POST /api/login` เก่าออก |

### Frontend

| File | Type | Description |
|------|------|-------------|
| `frontend/src/api.js` | **New** | JWT helper: `getToken`, `setToken`, `clearAuth`, `apiFetch` |
| `frontend/src/LoginPage.jsx` | Modified | เรียก `/api/auth/login`, store JWT, เพิ่มลิงก์ Register |
| `frontend/src/RegisterPage.jsx` | **New** | Register form (Cal.com design) |
| `frontend/src/App.jsx` | Modified | JWT-aware session restore, authMode toggle, clearAuth on logout |
| `frontend/src/CreateReport.jsx` | Modified | แทน `fetch()` ด้วย `apiFetch()`, รับ `user` prop, ส่ง `userId` ผ่าน wizard |

---

## API Endpoints

### `POST /api/auth/login`

**Request:**
```json
{ "userId": "10455", "password": "yourpassword" }
```

**Response (200):**
```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "user": {
    "userId": "10455",
    "fullName": "John Doe",
    "role": "user"
  }
}
```

**Error (401):**
```json
{ "detail": "Invalid Employee ID or password" }
```

---

### `POST /api/auth/register`

**Request:**
```json
{
  "userId": "10455",
  "fullName": "John Doe",
  "password": "securepass",
  "role": "user"
}
```

**Response (200):**
```json
{ "status": "success", "message": "Account created successfully" }
```

**Error (409):**
```json
{ "detail": "Employee ID already registered" }
```

---

## JWT Token

| Property | Value |
|----------|-------|
| Algorithm | HS256 |
| Expiry | 8 hours |
| Secret Key | `JWT_SECRET_KEY` env var (fallback: hardcoded dev key) |
| Payload | `{ sub, name, role, exp }` |

> **Production:** ต้องตั้ง `JWT_SECRET_KEY` ใน `.env` ให้เป็น random string ที่ปลอดภัย

---

## Password Migration (Plain-text → bcrypt)

ผู้ใช้เก่าที่เคย register ก่อนระบบนี้ (password เก็บเป็น plain-text) จะถูก upgrade อัตโนมัติ:

```
Login ครั้งแรกหลัง upgrade
  1. ตรวจ bcrypt verify → ล้มเหลว (ไม่ใช่ bcrypt hash)
  2. fallback plain-text compare → สำเร็จ
  3. UPDATE users SET password_hash = bcrypt(password)
  4. ออก JWT ตามปกติ
```

ต่อไปทุก login จะใช้ bcrypt verify ปกติ

---

## Frontend Token Flow

```
LocalStorage
  dpa_token  = JWT access token
  dpa_user   = { userId, fullName, role }

Session restore (App.jsx):
  if (dpa_token && dpa_user) → ถือว่า logged in (ไม่ verify expiry client-side)

Auto-logout (apiFetch):
  response.status === 401 → clearAuth() + window.location.reload()
```

### `apiFetch(url, options)` — api.js

ทำหน้าที่เหมือน `fetch()` ปกติ แต่:
- ใส่ `Authorization: Bearer <token>` ทุก request อัตโนมัติ
- ถ้าได้ 401 กลับมา → ล้าง session + reload ทันที

```js
// ใช้แทน fetch() ทุกที่
const res = await apiFetch('/api/product-requests');
```

---

## Database — users table

```sql
CREATE TABLE users (
  user_id       VARCHAR PRIMARY KEY,   -- Employee ID (e.g. "10455")
  full_name     VARCHAR NOT NULL,
  role          VARCHAR DEFAULT 'user', -- 'user' | 'admin'
  password_hash VARCHAR NOT NULL,       -- bcrypt hash
  is_active     BOOLEAN DEFAULT TRUE
);
```

---

## Register Page — UI Spec (Cal.com Design)

- **Font:** Cal Sans (headings), Inter (body/inputs)
- **Colors:** `#242424` (primary), `#898989` (secondary), `#ffffff` (surface)
- **Shadow:** `rgba(19,19,22,0.7) 0px 1px 5px -4px, rgba(34,42,53,0.08) 0px 0px 0px 1px, rgba(34,42,53,0.05) 0px 4px 8px 0px`
- **Fields:** Employee ID, Full Name, Password, Confirm Password, Role (radio card)
- **Validation:** Client-side ก่อน submit (Employee ID format: 4-6 digits, password min 6 chars, confirm match)
- **Success state:** แสดง checkmark + ปุ่ม "Go to Sign In →"

---

## Environment Variables

เพิ่มใน `.env` หรือ environment:

```env
JWT_SECRET_KEY=<random-256-bit-string>
```

Generate ด้วย Python:
```python
import secrets
print(secrets.token_hex(32))
```

---

## Security Notes

- Password เก็บเป็น bcrypt hash (cost factor 12 default)
- JWT ไม่มี refresh token — หมดอายุใน 8 ชั่วโมง ต้อง login ใหม่
- Secret key ต้อง rotate ถ้า compromise — token เก่าทั้งหมดจะ invalid ทันที
- ยังไม่มี rate limiting บน login endpoint — ควรเพิ่มในอนาคต (production)
- Routes `/api/product-requests`, `/api/generate-report` ฯลฯ ยังไม่ได้บังคับ JWT dependency ที่ backend — ป้องกันผ่าน frontend `apiFetch` เท่านั้น ถ้าต้องการ enforce ที่ backend ให้เพิ่ม `Depends(get_current_user)` ใน `routers/product_request.py`
