from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

import os
import random
import string
import datetime
import time
import re
import json
import subprocess

from firebase_util import verify_id_token

app = FastAPI()
PYTHON = '/Users/hunkim/Documents/work/chatgpt/07-auto-gpt/stream_rest_api/.venv/bin/python'

# CORS
origins = [
    "http://localhost:1024",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def prepare(content):
    content = re.sub(r'<@U[A-Z0-9]+>', '', content)
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d_%H-%M-%S")
    length = 5
    random_str = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))
    folder_name = date_str + "_" + random_str
    folder = os.path.join(os.getcwd(), 'auto_gpt_workspace', folder_name)
    os.makedirs(folder, exist_ok=True)
    ai_settings = f"""ai_name: AutoAskup
ai_role: an AI that achieves below goals.
ai_goals:
- {content}
- Terminate if above goal is achieved.
api_budget: 3"""
    with open(os.path.join(folder, "ai_settings.yaml"), "w") as f:
        f.write(ai_settings)
    return folder


def format_output(bytes):
    text = bytes.decode()
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    text = text.replace('ansicode', '\n')  # Replace ansicode with new line (\n)
    text = text.strip()
    index = text.find('THOUGHTS')
    if index != -1:
        return text[index:]
    if "Thinking..." in text:
        return
    if text.startswith(('REASONING', 'PLAN', '- ', 'CRITICISM', 'SPEAK', 'NEXT ACTION', 'SYSTEM', 'Goals')):
        return text
    # return text

@app.post("/auto_gpt")
async def run_autogpt_slack(request: Request):
    # Get id_token from request header Authorization
    id_token = request.headers.get("authorization", {})

    if not id_token:
        raise HTTPException(status_code=401, detail="No Authorization header")
    try:
        if id_token.startswith('Bearer '):
            id_token = id_token[7:]

        decoded_token = verify_id_token(id_token)
        if not decoded_token:
            raise HTTPException(status_code=401, detail="Invalid Authorization header")
    except Exception as e:
        print(("Error: ", e))
        raise HTTPException(status_code=401, detail=f"Invalid Authorization header: {e}")

    body = await request.body()
    data = json.loads(body)

    main_dir = os.path.dirname(os.getcwd())
    sub_dir = "stream_rest_api"

    print(main_dir)
    folder = prepare(data['order'])
    process = subprocess.Popen(
        [PYTHON, os.path.join(main_dir, sub_dir, 'api.py'), os.path.join(main_dir, folder)],
        cwd=main_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )



    async def stream():
        started_loop = False
        while True:
            output = process.stdout.readline()
            if (not output) and process.poll() is not None:
                break
            if output:
                print(output.decode().strip())
                output = format_output(output)
                if output is None:
                    continue
                if output.startswith('THOUGHTS'):
                    started_loop = True
                    yield f"data: {json.dumps({'type': 'thinking'})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'log', 'content': output.strip()})}\n\n"
                if not started_loop:
                    continue

        # Send files as part of the stream
        for fname in os.listdir(folder):
            if fname not in ['ai_settings.yaml', 'auto-gpt.json', 'file_logger.txt']:
                with open(os.path.join(folder, fname), 'r') as f:
                    content = f.read()
                    yield f"data: {json.dumps({'type': 'result', 'title': fname, 'content': content})}\n\n"


        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/plain")


@app.get("/")
async def index():
    return 'AutoAskUp'

# nohup uvicorn app:app --host 0.0.0.0 --port 30207 --reload &
