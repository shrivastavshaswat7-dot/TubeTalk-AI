from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/")
def root():
    return {"message": "TubeTalk AI Backend is running"}


@router.get("/health")
def health():
    return {"status": "healthy", "application": "TubeTalk AI"}
