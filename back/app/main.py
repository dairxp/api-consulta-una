from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # 1. Importar el middleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.routers.consulta import router
from app.routers.benchmark import router as benchmark_router
from app.limiter import limiter

import os
from dotenv import load_dotenv

load_dotenv() # Carga las variables de entorno del archivo .env

environment = os.environ.get("ENVIRONMENT")

if environment == "production":
    app = FastAPI(
        title="API Consulta Padrón UNAP",
        version="1.0.0",
        docs_url=None,  # Desactiva Swagger UI en producción
        redoc_url=None  # Desactiva ReDoc en producción
    )
else:
    app = FastAPI(
        title="API Consulta Padrón UNAP",
        version="1.0.0"
    )

from slowapi.middleware import SlowAPIMiddleware

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
print(f"Limiter is enabled: {limiter.enabled}")

# Permitimos el frontend configurado en el .env, o localhost por defecto
frontend_url_env = os.environ.get("FRONTEND_URL", "")
origenes_permitidos = [orig.strip() for orig in frontend_url_env.split(",") if orig.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos, # Solo acepta peticiones de esta lista
    allow_credentials=True,
    allow_methods=["*"],               # Permite todos los métodos (GET, POST, etc)
    allow_headers=["*"],               # Permite todos los encabezados
)

app.include_router(router)
app.include_router(benchmark_router)

@app.get("/")
def root():
    return {
        "mensaje": "Consulta Electoral UNAP - by DairXP"
    }
