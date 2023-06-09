import asyncio
import os
import uuid

from auto_gpt_wrapper import (
    prepare_and_return_folder,
    remove_ansi_escape_sequences,
    run_auto_gpt_wrapper,
)
from fastapi import FastAPI, HTTPException, Request, WebSocket, Depends
from fastapi.security import HTTPAuthorizationCredentials


app = FastAPI()

task_result_dir_status = {}


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(fastapi.security)):
    if credentials.scheme != "Bearer" or credentials.credentials != "mysecretkey":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication credentials",
        )
    return credentials


@app.post("/autoaskup")
async def autoaskup(request: Request):
    # Get the request body in JSON format
    body = await request.json()
    prompt = body.get("prompt", None)

    if not prompt:
        # 400 Bad Request
        raise HTTPException(
            status_code=400, detail="{prompt: your prompt} is required."
        )

    task_id = str(uuid.uuid4())
    result_dir = prepare_and_return_folder(prompt)

    if not os.path.exists(result_dir):
        raise HTTPException(status_code=500, detail="Failed to create a workspace.")

    task_result_dir_status[task_id] = result_dir

    return {
        "message": f"Task {task_id} initialized",
        "task_id": task_id,
        "result_dir": result_dir,
    }


@app.websocket("/autoaskup/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await websocket.accept()
    websocket.send_text("Websocket connection established.")

    if task_id not in task_result_dir_status or not task_result_dir_status[task_id]:
        await websocket.send_text("Task not initialized. Please initialize task first.")
        return

    result_dir = task_result_dir_status[task_id]
    # Check the result directory exists
    if not os.path.exists(result_dir):
        await websocket.send_text(
            "Task/path not initialized Please initialize task first."
        )
        return

    loop = asyncio.get_event_loop()

    def stream_log_call_back(title, content):
        content = remove_ansi_escape_sequences(content)
        title = remove_ansi_escape_sequences(title)

        loop.call_soon_threadsafe(
            asyncio.create_task,
            websocket.send_text(f"{title} {content}"),
        )

    # run_auto_gpt_wrapper(folder=result_dir, stream_log_call_back=stream_log_call_back)
    await loop.run_in_executor(
        None, run_auto_gpt_wrapper, result_dir, stream_log_call_back
    )
    print("Task completed.")
