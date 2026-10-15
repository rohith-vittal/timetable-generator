import os
import sys
import uvicorn

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        
    print("Starting Automated Timetable Generation API Server...")
    print("Web Interface available at: http://localhost:8000")
    print("Interactive Swagger Documentation at: http://localhost:8000/docs")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, app_dir=current_dir)

