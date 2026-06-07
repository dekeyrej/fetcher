"""
Redis-based API server with SSE for real-time updates
This FastAPI application connects to a Redis instance to listen for updates on a specific channel.
It provides an endpoint to get the current state stored in Redis and another endpoint to stream updates via
Server-Sent Events (SSE).
It uses the `sse_starlette` library for handling SSE and `redis.asyncio` for asynchronous Redis operations.

kubectl rollout restart -n default deployment apiserver
"""
import asyncio
import orjson
import logging
import os

from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as aioredis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

UPDATE_CHANNEL = os.getenv('IN_CHANNEL', 'update')
user_pass      = os.getenv('USER_PASS', 'none:none')
host_port_db   = os.getenv('HOST_PORT_DB', 'redis.redis:6379/0')

redis_url = f"redis://{user_pass}@{host_port_db}"

sse_clients = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event to initialize Redis connection and start the listener.
    """
    app.state.redis = aioredis.from_url(redis_url, decode_responses=True)
    app.state.pubsub = app.state.redis.pubsub()
    
    await app.state.pubsub.subscribe(UPDATE_CHANNEL)

    # Fire off the listener loop as a non-blocking background task
    listener_task = asyncio.create_task(redis_listener(app.state.pubsub))
    print("FastAPI started: Redis async listener loop is running.")

    yield

    listener_task.cancel()  # Cancel the listener task when the app shuts down

    try:
        await listener_task  # Check if Redis is reachable
    except asyncio.CancelledError:
        print("Background listener task cancelled successfully.")

    # Cleanly close the connections
    await app.state.pubsub.disconnect()
    await app.state.redis.close()
    print("Cleanup complete.")

app = FastAPI(lifespan=lifespan)    

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],  # for local testing of webdisplay
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/key/Environment")
async def get_current_environment():
    logging.info(f"Fetching Redis key: Environment")
    weatherval = await app.state.redis.get(f"{UPDATE_CHANNEL}:Weather")
    aqival = await app.state.redis.get(f"{UPDATE_CHANNEL}:AQI")
    moonval = await app.state.redis.get(f"{UPDATE_CHANNEL}:Moon")
    val = {
        'AQI'    : orjson.loads(aqival or '{}'),
        'Moon'   : orjson.loads(moonval or '{}'),
        'Weather': orjson.loads(weatherval or '{}')
    }
    logging.debug(f"Value for key Environment: {val}")
    return JSONResponse(content=val)

@app.get("/key/{KV_KEY}")
async def get_current_state(KV_KEY: str):

    logging.info(f"Fetching Redis key: {UPDATE_CHANNEL}:{KV_KEY}")
    val = await app.state.redis.get(f"{UPDATE_CHANNEL}:{KV_KEY}")
    logging.debug(f"Value for key {UPDATE_CHANNEL}:{KV_KEY}: {val}")
    return JSONResponse(content=orjson.loads(val or '{}'))

async def broadcast(payload: dict):
    msg = orjson.dumps(payload).decode('utf-8')
    for q in list(sse_clients):
        await q.put(msg)

@app.put("/webcontrol/{command}")
async def send_webcontrol_command(command: str):
    valid_commands = {'pp', 'fwd', 'rew', 'out', 'reload'}
    if command not in valid_commands:
        return JSONResponse(status_code=400, content={"error": "Invalid command"})

    payload = {
        "type": "webcontrol",
        "command": command
    }

    await broadcast(payload)
    return JSONResponse(status_code=202, content={"status": "Command queued"})

@app.get("/events")
async def stream_events(request: Request):
    logging.info("Client connected for SSE updates")
    queue = asyncio.Queue()
    sse_clients.append(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await queue.get()
                yield {"event": "update", "data": msg}
        finally:
            sse_clients.remove(queue)

    return EventSourceResponse(event_generator())

@app.get("/ready")
async def readiness_probe():
    try:
        pong = await app.state.redis.ping()
        if pong:
            return JSONResponse(content={"status": "ready"})
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})

@app.get("/live")
async def liveness_probe():
    return JSONResponse(content={"status": "alive"})

async def redis_listener(pubsub):
    while True:
        try:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message['type'] == 'message':
                data = orjson.loads(message['data'])
                logging.info(f"Received message on '{UPDATE_CHANNEL}': {data.get('type', 'unknown')}")
                await broadcast(data)
        except asyncio.CancelledError:
            logging.info("Redis listener task cancelled.")
            raise
        except Exception as e:
            logging.error(f"Error in Redis listener: {e}")
            await asyncio.sleep(5)  # Wait before retrying on error

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apiserver:app", host="0.0.0.0", port=8000, reload=True)
