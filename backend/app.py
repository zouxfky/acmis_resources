from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.db import init_db
from backend.features.admin import router as admin_router
from backend.features.auth import router as auth_router
from backend.features.runtime_monitor import RuntimeMonitorService
from backend.features.workspace import router as workspace_router


app = FastAPI(title="ACMIS API")
runtime_monitor = RuntimeMonitorService()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:4173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(workspace_router)
app.include_router(admin_router)


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    runtime_monitor.start()


@app.on_event("shutdown")
def shutdown_event() -> None:
    runtime_monitor.stop()
