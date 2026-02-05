import os
from dotenv import load_dotenv

# ЭТО ДОЛЖНО БЫТЬ САМЫМ ПЕРВЫМ
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.routers import auth, payment, liveness, bot

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Cafeteria")

@app.on_event("startup")
async def startup_event():
    bot.start_bot()

app.include_router(auth.router, prefix="/api")
app.include_router(liveness.router, prefix="/api")
app.include_router(payment.router, prefix="/api")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="static", html=True), name="root")
