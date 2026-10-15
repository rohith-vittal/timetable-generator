from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import faculty, admin, metadata, auth

app = FastAPI(
    title="Automated Timetable Generation API",
    description="Conflict-free scheduling system based on Constraint Programming (CP-SAT/CSP), supporting Day, Week, and Year scopes with strict 1:1 faculty-subject allocation.",
    version="1.0.0",
)

# Enable CORS for modern frontend frameworks (Next.js, Vite, React)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import HTMLResponse, FileResponse
import os

# Register route modules
app.include_router(auth.router)
app.include_router(faculty.router)
app.include_router(admin.router)
app.include_router(metadata.router)

INDEX_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "index.html")

@app.get("/", response_class=HTMLResponse, tags=["Web UI"])
def serve_ui():
    """Serves the interactive Faculty & Admin Timetable Web Application."""
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Automated Timetable Generation API</h1><p>Visit <a href='/docs'>/docs</a> for Swagger UI.</p>")

@app.get("/api/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "Automated Timetable Generation Engine",
        "version": "1.0.0",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json"
    }
