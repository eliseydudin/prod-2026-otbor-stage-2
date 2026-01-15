from fastapi import FastAPI

app = FastAPI()


@app.get("/ping")
async def healthcheck():
    return {"status": "ok"}
