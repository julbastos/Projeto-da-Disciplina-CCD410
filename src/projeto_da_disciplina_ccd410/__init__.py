def main() -> None:
    import sys
    from pathlib import Path
    import uvicorn
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    uvicorn.run('app:app', host='0.0.0.0', port=8000)
