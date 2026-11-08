from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from database import fechar_conexoes
from router import main_router


@asynccontextmanager
async def lifespan(app):
    yield
    fechar_conexoes()


app = FastAPI(title='biblioteca plural', lifespan=lifespan)
app.include_router(main_router)
STATIC = Path(__file__).parent / 'static'


@app.exception_handler(Exception)
async def falha_servico(request: Request, exc: Exception):
    return JSONResponse(status_code=503, content={'detail': 'não foi possível acessar o serviço. verifique as conexões e a preparação dos bancos.'})


@app.get('/', include_in_schema=False)
def interface():
    return FileResponse(STATIC / 'index.html')


app.mount('/static', StaticFiles(directory=STATIC), name='static')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host='0.0.0.0', port=8000, reload=True)
