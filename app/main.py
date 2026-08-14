from fastapi import FastAPI

from frontend.router import frontend_router
from v1.router import v1_router

app = FastAPI()
app.include_router(frontend_router)
app.include_router(v1_router)
