import asyncio
import datetime
import json
import os
import random
import re
import string
import subprocess
import tempfile
import time
from queue import Queue

from autogpt.logs import logger, update_logger
from autogpt.main import run_auto_gpt

app = FastAPI()

# Join the current directory with .venv/bin/python
PYTHON = os.path.join(os.getcwd(), ".venv", "bin", "python")

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


class MessageQueue:
    def __init__(self):
        self.queue = Queue()

    def put(self, message):
        self.queue.put(message)

    def get(self):
        return self.queue.get()

def prepare_and_return_folder(content):
    content = re.sub(r'<@U[A-Z0-9]+>', '', content)
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d_%H-%M-%S")

    # Create a temporary directory with a unique name
    folder = tempfile.mkdtemp(prefix=date_str + "_", dir=os.path.join(os.getcwd(), 'auto_gpt_workspace'))

    ai_settings = f"""ai_name: AutoAskup
ai_role: an AI that achieves below goals.
ai_goals:
- {content}
- Terminate if above goal is achieved.
api_budget: 1"""

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


def run_auto_gpt_wrapper(folder=None, stream_log_call_back=None):
    print("RUNNING AUTO GPT")

    if stream_log_call_back:
        update_logger(log_callback_func=stream_log_call_back)

    logger.typewriter_log("DONE")

    run_auto_gpt(
            continuous=True,
            continuous_limit=None,
            ai_settings=os.path.join(folder, "ai_settings.yaml"),
            prompt_settings='prompt_settings.yaml',
            skip_reprompt=False,
            speak=False,
            debug=False,
            gpt3only=True,
            gpt4only=False,
            memory_type=None,
            browser_name=None,
            allow_downloads=False,
            skip_news=True,
            workspace_directory=folder,
            install_plugin_deps=False
        )


    logger.typing_logger("DONE")


@app.post("/auto_gpt")
async def run_autogpt_slack(request: Request, background_tasks: BackgroundTasks):
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
    folder = prepare_and_return_folder(data['order'])

    # Create a message queue
    message_queue = MessageQueue()

    def stream_log_call_back(title, content):
        print("STREAM LOG CALLBACK", title, content)
        message_queue.put({'type': 'log', 'content': title + content.strip()})

    update_logger(log_callback_func=stream_log_call_back)
    logger.typewriter_log("Running AutoGPT...")

    # Start the background task simulating a long-running process
    executor = ProcessPoolExecutor(max_workers=2)
    background_tasks.add_task(executor.submit(run_auto_gpt_wrapper))
    background_tasks.add_task(executor.submit(simple_function))

    print("OOO")

    async def event_stream():
        while True:
            print("Waiting for message")
            message = message_queue.get()
            print("MESSAGE", message)
            if message['content'].startswith('DONE'):
                break
            yield f"data: {json.dumps(message)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")



