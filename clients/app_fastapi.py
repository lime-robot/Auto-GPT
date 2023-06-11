import asyncio
import datetime
import json
import os
import re

import subprocess
import uuid
from collections import defaultdict

from fastapi import Depends, FastAPI, HTTPException, WebSocket, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from slack.api import init_task

AUTO_ASKUP_API_KEY = os.environ["AUTO_ASKUP_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

app = FastAPI()

task_result_dir_status = {}

thread_ts2pids = defaultdict(list)


def format_stdout(stdout):
    text = stdout.decode()
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    text = ansi_escape.sub("", text)
    text = text.strip()
    index = text.find("THOUGHTS")
    if index != -1:
        return text[index:]
    if "Thinking..." in text:
        return
    prefixes = (
        "REASONING",
        "PLAN",
        "- ",
        "CRITICISM",
        "SPEAK",
        "NEXT ACTION",
        "SYSTEM",
        "$ SPENT",
        "BROWSING",
    )
    if text.startswith(prefixes):
        return text


def get_token_header(
    apikey: str = Depends(APIKeyHeader(name="Authorization", auto_error=True))
):
    if apikey != AUTO_ASKUP_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return apikey


class Item(BaseModel):
    prompt: str


@app.post("/autoaskup")
async def autoaskup(item: Item, apikey: str = Depends(get_token_header)):
    # Get the request body in JSON format
    if not item.prompt:
        # 400 Bad Request
        raise HTTPException(
            status_code=400, detail="{prompt: your prompt} is required."
        )

    options = {
        "debug": False,
        "gpt3_only": True,
        "api_budget": 1,
    }
    ai_settings, workspace = init_task(item.prompt, options, OPENAI_API_KEY)

    if not os.path.exists(workspace):
        raise HTTPException(status_code=500, detail="Failed to create a workspace.")

    task_id = str(uuid.uuid4())
    task_result_dir_status[task_id] = (ai_settings, options, workspace)

    return {
        "message": f"Task {task_id} initialized",
        "task_id": task_id,
        "workspace": workspace,
        "ai_settings": ai_settings,
    }


@app.websocket("/autoaskup/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await websocket.accept()
    websocket.send_text("Websocket connection established.")

    if task_id not in task_result_dir_status or not task_result_dir_status[task_id]:
        await websocket.send_text("Task not initialized. Please initialize task first.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    ai_settings, options, workspace = task_result_dir_status[task_id]
    # Check the result directory exists
    if not os.path.exists(workspace):
        await websocket.send_text(
            "Task/path not initialized Please initialize task first."
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Run autogpt
    main_dir = os.path.dirname(os.getcwd())
    process = subprocess.Popen(
        [
            os.path.join(main_dir, "clients", ".venv", "bin", "python3"),
            os.path.join(main_dir, "slack", "api.py"),
            os.path.join(main_dir, workspace),
            str(options["gpt3_only"]),
        ],
        cwd=main_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    ai_settings_message = f"AutoGPT launched with settings:\n{ai_settings.replace('api_budget: ', 'api_budget: $')}"
    await websocket.send_text(ai_settings_message)

    # add to pid
    thread_ts2pids[task_id].append(process.pid)
    print("thread_ts2pids", thread_ts2pids)

    # Read stdout and send messages to slack
    started_loop = False
    messages = []
    dollars_spent = 0
    while True:
        stdout = process.stdout.readline()
        print(stdout)

        if (not stdout) and process.poll() is not None:
            break
        if not stdout:
            continue
        output = format_stdout(stdout)
        if output is None:
            continue

        await websocket.send_text(output)
        if output.startswith("$ SPENT"):
            dollars_spent = output.split("$ SPENT:")[1].strip()

        if output.startswith("THOUGHTS"):
            started_loop = True
        if not started_loop:
            continue
        messages.append(output)
        if started_loop and output.startswith(("$ SPENT")):
            await websocket.send_text("\n".join(messages))
            messages = []
        rc = process.poll()
    if len(messages) > 0:
        # Send remaining messages to slack
        await websocket.send_text("\n".join(messages))
        messages = []

    # Print stderr
    for line in process.stderr:
        print(line.decode().strip())

    # Upload files to slack
    for root, dirs, fnames in os.walk(workspace):
        for fname in fnames:
            # Construct the full file path
            file = os.path.join(root, fname)
            if fname not in ["ai_settings.yaml", "auto-gpt.json", "file_logger.txt"]:
                file = os.path.join(root, fname)
                # Send file content to websocket
                await websocket.send_text(f"Uploading {fname}...")
                with open(file, "rb") as f:
                    await websocket.send_bytes(f.read())

    # Send $ spent message to slack
    await websocket.send_text(f"Total Spent: ${round(float(dollars_spent), 2)}")
    # Close websocket
    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)

    # Delete from pid
    if process.pid in thread_ts2pids[task_id]:
        thread_ts2pids[task_id].remove(process.pid)
        if len(thread_ts2pids[task_id]) == 0:
            del thread_ts2pids[task_id]
