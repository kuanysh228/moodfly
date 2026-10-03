import asyncio
import contextlib
import json
import os
import re
import threading

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .hub import Hub
from .paths import FRONTEND

hub: Hub | None = None
NAME_RE = re.compile(r"^[\w\- ]{2,20}$")


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    global hub
    hub = Hub()
    thread = threading.Thread(target=hub.run_forever, name="brains", daemon=True)
    thread.start()
    yield
    hub.stop()


app = FastAPI(title="MoodFly", lifespan=lifespan)


@app.middleware("http")
async def no_stale_frontend(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/brain.bin")
def brain_bin() -> Response:
    return Response(hub.brain_binary(), media_type="application/octet-stream")


class Client:
    def __init__(self, socket: WebSocket, loop: asyncio.AbstractEventLoop):
        self.socket = socket
        self.loop = loop
        self.queue: asyncio.Queue = asyncio.Queue()
        self.user: dict | None = None
        self.session = None

    def push(self, msg: dict) -> None:
        self.loop.call_soon_threadsafe(self.queue.put_nowait, msg)

    def me(self) -> dict:
        pet = hub.db.pet_of(self.user["id"]) if self.user else None
        return {
            "type": "me",
            "user": {"id": self.user["id"], "nick": self.user["nick"]} if self.user else None,
            "token": self.user["token"] if self.user else None,
            "pet": hub.pet_public(pet) if pet else None,
        }

    def watch(self, key: str | None) -> None:
        hub.unwatch(self.session)
        self.session = hub.watch(key, self.user)

    async def handle(self, cmd: dict) -> None:
        kind = cmd.get("type")
        if kind == "auth":
            self.user = hub.db.user_by_token(str(cmd.get("token", "")))
            self.push(self.me())
        elif kind == "register":
            nick = str(cmd.get("nick", "")).strip()
            if not NAME_RE.match(nick):
                self.push({"type": "error", "text": "Ник: 2–20 букв, цифр, пробелов или дефисов"})
                return
            user = hub.db.register(nick)
            if not user:
                self.push({"type": "error", "text": "Такой ник уже занят"})
                return
            self.user = user
            self.push(self.me())
        elif kind == "create_pet" and self.user:
            name = str(cmd.get("name", "")).strip()
            if not NAME_RE.match(name):
                self.push({"type": "error", "text": "Имя питомца: 2–20 символов"})
            elif hub.db.pet_of(self.user["id"]):
                self.push({"type": "error", "text": "У вас уже есть питомец"})
            else:
                self.push({"type": "notice", "text": f"Рождается {name}… проводим медосмотр мозга"})
                await asyncio.to_thread(hub.create_pet, self.user, name)
                self.push(self.me())
        elif kind == "watch":
            self.watch(cmd.get("channel"))
        elif kind == "allocate" and self.user:
            hub.allocate(self.user, str(cmd.get("stat")))
            self.push(self.me())
            hub.broadcast({"type": "pets", "pets": hub.pets_public()})
        elif kind == "challenge" and self.user:
            key, err = hub.challenge(self.user, int(cmd.get("pet_id", 0)))
            if err:
                self.push({"type": "error", "text": err})
            else:
                self.push({"type": "battle_started", "channel": key})
        elif kind == "room" and self.session and self.session.kind == "pet":
            inner = cmd.get("cmd") or {}
            if isinstance(inner, dict):
                room = self.session.obj
                is_owner = bool(self.user) and room.pet["owner_id"] == self.user["id"]
                if inner.get("type") == "say":
                    inner["who"] = self.user["nick"] if self.user else "гость"
                room.submit(inner, is_owner)


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await socket.accept()
    client = Client(socket, asyncio.get_running_loop())
    hub.clients.add(client)
    await socket.send_text(json.dumps(hub.hello(), ensure_ascii=False))
    client.push({"type": "pets", "pets": hub.pets_public()})
    client.push({"type": "battles", "battles": hub.battles_public()})

    async def receive() -> None:
        while True:
            msg = await socket.receive_text()
            try:
                cmd = json.loads(msg)
            except json.JSONDecodeError:
                continue
            if isinstance(cmd, dict):
                await client.handle(cmd)

    async def send() -> None:
        last = None
        while True:
            while not client.queue.empty():
                await socket.send_text(json.dumps(client.queue.get_nowait(), ensure_ascii=False))
            s = client.session
            if s is not None and s.frame is not None and (s.key, s.frame_id) != last:
                last = (s.key, s.frame_id)
                frame, bins = s.frame, s.bins
                await socket.send_text(json.dumps(frame, ensure_ascii=False))
                for b in bins:
                    await socket.send_bytes(b)
            await asyncio.sleep(0.01)

    tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        hub.clients.discard(client)
        hub.unwatch(client.session)


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")


def main() -> None:
    host = os.environ.get("MOODFLY_HOST", "127.0.0.1")
    port = int(os.environ.get("MOODFLY_PORT", "8000"))
    print(f"MoodFly: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
