import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from utils.db_client import close_connection

# Import routes from routers inside api/routes/
from api.routes.companies import router as companies_router
from api.routes.reports import router as reports_router
from api.routes.proposals import router as proposals_router
from api.routes.tenders import router as tenders_router
from api.routes.bidforge import router as bidforge_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load/verify SAM entities database
    from api.routes.companies import import_sam_entities_csv
    import_sam_entities_csv()
    yield
    # Shutdown: close DB connection
    close_connection()

app = FastAPI(title="PPT-Agent Backend API", version="1.0", lifespan=lifespan)

# Enable CORS for frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(companies_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(proposals_router, prefix="/api")
app.include_router(tenders_router, prefix="/api")
app.include_router(bidforge_router, prefix="/api")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
