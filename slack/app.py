import os
import random
import string
import datetime
import time
import re
import json
import subprocess
from collections import defaultdict
import signal

import openai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler
from tenacity import retry, stop_after_attempt, wait_random_exponential, RetryError

from api import init_task

app = FastAPI()

thread_ts2pids = defaultdict(list)

def format_stdout(stdout):
    text = stdout.decode()
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    text = text.strip()
    index = text.find('THOUGHTS')
    if index != -1:
        return text[index:]
    if "Thinking..." in text:
        return
    prefixes = ('REASONING', 'PLAN', '- ', 'CRITICISM', 'SPEAK', 'NEXT ACTION', 'SYSTEM', '$ SPENT', 'BROWSING')
    if text.startswith(prefixes):
        return text

def process_user_message(user_message):
    # Remove @AutoAskUp from message
    mention_pattern = r'^<@U[A-Z0-9]+>'
    user_message = re.sub(mention_pattern, '', user_message).strip()
    # Extract options from message
    options = {
        'debug': False,
        'gpt3_only': True,
        'api_budget': 1,
    }
    if user_message.startswith('?'):
        options['debug'] = True
        user_message = user_message.replace('?', '').strip()
    if user_message.startswith('!'):
        options['gpt3_only'] = False
        user_message = user_message.replace('!', '').strip()
    if user_message.startswith('%'):
        options['gpt3_only'] = True
        user_message = user_message.replace('%', '').strip()

    match = re.search(r'\$(\d+(\.\d+)?)\s*$', user_message)
    if match:
        options['api_budget'] = min(5, float(match.group(1)))
        user_message = user_message[:user_message.rfind(match.group(0))].strip()

    return user_message, options

@retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(6))
def upload_files(client, channel, thread_ts, fname, file):
    upload_text_file = client.files_upload(
        channels=channel,
        thread_ts=thread_ts,
        title=fname,
        file=file,
    )
    return upload_text_file

def run_autogpt_slack(client, user_message, options, channel, thread_ts, openai_api_key=None):
    ai_settings, workspace = init_task(user_message, options, openai_api_key)
    
    # Run autogpt
    main_dir = os.path.dirname(os.getcwd())
    process = subprocess.Popen(
        ["python", os.path.join(main_dir, 'slack', 'api.py'), os.path.join(main_dir, workspace), str(options['gpt3_only'])],
        cwd=main_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    ai_settings_message = f"AutoGPT launched with settings:\n{ai_settings.replace('api_budget: ', 'api_budget: $')}"
    print(ai_settings_message)
    client.chat_postMessage(
        channel=channel,
        text=ai_settings_message,
        thread_ts=thread_ts
    )
    
    # add to pid
    thread_ts2pids[thread_ts].append(process.pid)
    print('thread_ts2pids', thread_ts2pids)

    # Read stdout and send messages to slack
    started_loop = False
    messages = []
    dollars_spent = 0
    while True:
        stdout = process.stdout.readline()
        if (not stdout) and process.poll() is not None:
            break
        if not stdout:
            continue
        output = format_stdout(stdout)
        if output is None:
            continue
        print(output)
        if output.startswith('$ SPENT'):
            dollars_spent = output.split('$ SPENT:')[1].strip()
        if not options['debug']:
            if output.startswith('SPEAK'):
                output = output[6:].strip()
                client.chat_postMessage(
                    channel=channel,
                    text=output,
                    thread_ts=thread_ts
                )
            elif output.startswith('BROWSING'):
                client.chat_postMessage(
                    channel=channel,
                    text=output,
                    thread_ts=thread_ts
                )
            continue
        if output.startswith('THOUGHTS'):
            started_loop = True
        if not started_loop:
            continue
        messages.append(output)
        if started_loop and output.startswith(('$ SPENT')):
            client.chat_postMessage(
                channel=channel,
                text="\n".join(messages),
                thread_ts=thread_ts
            )
            messages = []
        rc = process.poll()
    if len(messages) > 0:
        # Send remaining messages to slack
        client.chat_postMessage(
            channel=channel,
            text="\n".join(messages),
            thread_ts=thread_ts
        )
        messages = []

    # Print stderr
    for line in process.stderr:
        print(line.decode().strip())

    # Upload files to slack
    for root, dirs, fnames in os.walk(workspace):
        for fname in fnames:
            # Construct the full file path
            file = os.path.join(root, fname)
            if fname not in ['ai_settings.yaml', 'auto-gpt.json', 'file_logger.txt']:
                file = os.path.join(root, fname)
                try:
                    upload_files(client, channel, thread_ts, fname, file)
                except RetryError as e:
                    print(f"Error uploading file {file} to channel:{channel} / thread_ts:{thread_ts}")

    # Send $ spent message to slack
    client.chat_postMessage(
        channel=channel,
        text=f"Total Spent: ${round(float(dollars_spent), 2)}",
        thread_ts=thread_ts
    )

    # Delete from pid
    if process.pid in thread_ts2pids[thread_ts]:
        thread_ts2pids[thread_ts].remove(process.pid)
        if len(thread_ts2pids[thread_ts]) == 0:
            del thread_ts2pids[thread_ts]


@app.post("/")
async def slack_events(request: Request, background_tasks: BackgroundTasks):

    # Get the request body and headers
    body = await request.body()
    headers = request.headers
    print('BODY', body)
    print('HEADER', headers)
    data = json.loads(body)

    if data.get("type") == "url_verification":
        # Respond with the challenge value if the event is a challenge
        challenge = data.get("challenge")
        return {"challenge": challenge}

    # Load secrets
    app_id = data['api_app_id']
    with open('secrets.json', 'r') as f:
        secrets = json.load(f)[app_id]
    
    # Prepare slack client
    client = WebClient(token=secrets["SLACK_BOT_TOKEN"])
    rate_limit_handler = RateLimitErrorRetryHandler(max_retry_count=1)
    client.retry_handlers.append(rate_limit_handler)

    # Avoid replay attacks
    if abs(time.time() - int(headers.get('X-Slack-Request-Timestamp'))) > 60 * 5:
        raise HTTPException(status_code=401, detail="Invalid timestamp")

    # Verify signature
    signature_verifier = SignatureVerifier(signing_secret=secrets["SLACK_SIGNING_SECRET"])
    if not signature_verifier.is_valid(
            body=body,
            timestamp=headers.get("X-Slack-Request-Timestamp"),
            signature=headers.get("X-Slack-Signature")):
        raise HTTPException(status_code=401, detail="Invalid signature")

    user_message, options = process_user_message(data['event']['text'])
    event = data['event']  
    thread_ts = event['thread_ts'] if 'thread_ts' in event else event['ts']
    
    if user_message.lower() == 'stop':
        # If stop command, kill process
        if thread_ts not in thread_ts2pids:
            client.chat_postMessage(
                channel=event['channel'],
                text="AutoGPT is not launched yet.",
                thread_ts=thread_ts
            )
            return JSONResponse(content="Main process is not running yet.")
        for pid in thread_ts2pids[thread_ts]:
            os.kill(pid, signal.SIGTERM)
        del thread_ts2pids[thread_ts]
        print('thread_ts2pids', thread_ts2pids)
        client.chat_postMessage(
            channel=event['channel'],
            text="AutoGPT stopped.",
            thread_ts=thread_ts
        )
        return JSONResponse(content="AutoGPT stopped.")
    
    background_tasks.add_task(run_autogpt_slack, client, user_message, options, event['channel'], thread_ts, secrets['OPENAI_API_KEY'])
    start_message = "Preparing to launch AutoGPT..."
    if options['debug']:
        start_message += " (in DEBUG MODE)"
    if options['gpt3_only']:
        start_message += " (with GPT3.5)"
    else:
        start_message += " (with GPT4)"
    client.chat_postMessage(
        channel=event['channel'],
        text=start_message,
        thread_ts=thread_ts
    )
    return JSONResponse(content="Launched AutoGPT.")

@app.get("/")
async def index():
    return 'AutoAskUp'

# nohup uvicorn app:app --host 0.0.0.0 --port 30207 &