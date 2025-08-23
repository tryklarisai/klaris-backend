import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from routers.tenants import router as tenant_router
from routers.auth import router as auth_router
from routers.connectors import router as connector_router, oauth_router
from routers.relationships import router as relationships_router
from routers.schemas import router as schema_router
from routers.chat import router as chat_router
from routers.bcl import router as bcl_router
from routers.usage import router as usage_router
import jwt

# Configure root logging (stdout handler) with level from env
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
try:
    level = getattr(logging, log_level)
except Exception:
    level = logging.INFO
logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("chat_graph").setLevel(level)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tenant_router)
app.include_router(auth_router)
app.include_router(connector_router)
app.include_router(oauth_router)  # Mount root-level Google OAuth endpoints
app.include_router(schema_router)
app.include_router(relationships_router)
app.include_router(chat_router)
app.include_router(bcl_router)
app.include_router(usage_router)

# --- Global auth middleware to protect APIs ---
JWT_SECRET = os.getenv("JWT_SECRET", "insecure-placeholder-change-in-env")
JWT_ALGORITHM = "HS256"

PUBLIC_PATH_PREFIXES = [
    "/api/health",
    "/api/v1/auth/login",
    "/api/v1/connectors/oauth",  # OAuth callbacks/flows
]

def _is_public_path(path: str) -> bool:
    for p in PUBLIC_PATH_PREFIXES:
        if path.startswith(p):
            return True
    return False

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Only guard API routes and allow public paths
    if path.startswith("/api/") and not _is_public_path(path):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except Exception:
            return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})
        # Make minimal context available to handlers if needed
        request.state.auth = {
            "user": payload.get("user"),
            "tenant": payload.get("tenant"),
            "sub": payload.get("sub"),
        }
    response = await call_next(request)
    return response

@app.get("/api/health")
def health():
    return {"status": "ok"}
