from fastapi import APIRouter
from routes.usuarios import router as usuarios_router
from routes.livros import router as livros_router
from routes.emprestimos import router as emprestimos_router

main_router = APIRouter(prefix='/api')
main_router.include_router(usuarios_router)
main_router.include_router(livros_router)
main_router.include_router(emprestimos_router)
