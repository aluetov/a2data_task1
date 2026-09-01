from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from app.config import get_settings
from app.db.db import create_database_engine, create_session_factory
from app.redis import create_redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = create_database_engine(settings)

    app.state.settings = settings
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = create_redis(settings)

    try:
        yield
    finally:
        await engine.dispose()
        await app.state.redis.aclose()

app = FastAPI(lifespan=lifespan)



@app.get("/")
async def read_root():
    return {"message": "Hello, World!"}


@app.post("/check")
async def check():
    pass


@app.get("/health")
async def health_check():
    return {"status": "healthy"}