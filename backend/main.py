from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.tenants import router as tenant_router
from routers.auth import router as auth_router
from routers.connectors import router as connector_router, oauth_router
from routers.relationships import router as relationships_router
from routers.business_context import router as business_context_router
from routers.schemas import router as schema_router

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
app.include_router(business_context_router)

@app.get("/api/health")
def health():
    return {"status": "ok"}
