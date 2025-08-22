import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.tenants import router as tenant_router
from routers.auth import router as auth_router
from routers.connectors import router as connector_router, oauth_router
from routers.relationships import router as relationships_router
from routers.schemas import router as schema_router
from routers.chat import router as chat_router
from routers.bcl import router as bcl_router

# Configure root logging (stdout handler) with level from env
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
try:
    level = getattr(logging, log_level)
except Exception:
    level = logging.INFO
logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

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

@app.get("/api/health")
def health():
    return {"status": "ok"}
