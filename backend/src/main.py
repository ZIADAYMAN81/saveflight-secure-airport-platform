import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .database import engine, Base, run_lightweight_migrations
from .middleware import limiter, SecurityHeadersMiddleware
from .metrics import metrics_response
from .auth_routes import router as auth_router
from .passenger_routes import router as passenger_router
from .booking_routes import router as booking_router
from .payment_routes import router as payment_router
from .staff_routes import router as staff_router
from .admin_routes import router as admin_router
from .seat_routes import router as seat_router
from .flight_status_routes import router as flight_status_router
from .analytics_routes import router as analytics_router

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
    yield


app = FastAPI(title="Save Flight", version="1.0.0", lifespan=lifespan)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again later."})


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(passenger_router)
app.include_router(booking_router)
app.include_router(payment_router)
app.include_router(staff_router)
app.include_router(admin_router)
app.include_router(seat_router)
app.include_router(flight_status_router)
app.include_router(analytics_router)


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    body, content_type = metrics_response()
    return Response(content=body, media_type=content_type)


# Optional single-service deployment mode: if a built frontend is baked into the
# image (see Dockerfile.railway), serve it from this same app. Registered last so
# it never shadows the API routes above. Absent locally/in docker-compose, where
# the frontend runs as its own container - this is a no-op.
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=os.path.join(_STATIC_DIR, "static")), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
