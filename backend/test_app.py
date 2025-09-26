# backend/test_app.py
from fastapi import FastAPI
import time

app = FastAPI()

@app.get("/")
async def read_root():
    print(f"[{time.time()}] Request received in test_app!")
    return {"message": "Hello from Test App"}
