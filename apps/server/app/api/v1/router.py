from fastapi import APIRouter

from app.api.v1.articles import router as articles_router
from app.api.v1.search import router as search_router
from app.api.v1.tags import router as tags_router


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(articles_router)
api_router.include_router(tags_router)
api_router.include_router(search_router)
