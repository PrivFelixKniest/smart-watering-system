from fastapi import FastAPI

from frontend.router import frontendRouter
from v1.router import v1Router

app = FastAPI()
app.include_router(frontendRouter)
app.include_router(v1Router)


