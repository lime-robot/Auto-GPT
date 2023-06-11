import requests
import os

import os
import re

import subprocess

from slack.api import init_task

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

def create_article(api_key, article_data):
    url = 'http://localhost:3000/api/articles'
    headers = {
        'Content-Type': 'application/json',
        'api-key': api_key
    }
    data = {"article": article_data}

    response = requests.post(url, json=data, headers=headers)
    print(response.status_code)

    if response.status_code != 201:
        raise Exception(f'API call failed with status code {response.status_code} and message {response.json()}')

    return response.status_code, response.json()


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



def autoaskup(prompt):
    options = {
        "debug": False,
        "gpt3_only": True,
        "api_budget": 1,
    }
    ai_settings, workspace = init_task(prompt, options, OPENAI_API_KEY)

    if not os.path.exists(workspace):
        raise FileNotFoundError(f"Workspace {workspace} not found")

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

        print(output)
        if output.startswith("$ SPENT"):
            dollars_spent = output.split("$ SPENT:")[1].strip()

        if output.startswith("THOUGHTS"):
            started_loop = True
        if not started_loop:
            continue
        messages.append(output)
        if started_loop and output.startswith(("$ SPENT")):
            print("\n".join(messages))
            messages = []
        rc = process.poll()

    if len(messages) > 0:
        # Send remaining messages to slack
        print("\n".join(messages))
        messages = []

    # Print stderr
    for line in process.stderr:
        print(line.decode().strip())

    md_content = results_to_md(workspace)
    md_content += "\nDollars spent: $" + dollars_spent + "\n"
    return md_content

def results_to_md(workspace):
    md_content = ""
     # Upload files to slack
    for root, dirs, fnames in os.walk(workspace):
        for fname in fnames:
            # Construct the full file path
            file = os.path.join(root, fname)
            # If it's md file, make the content as string and return it
            if file.endswith(".md"):
                with open(file, "r") as f:
                    md_content += f.read()
    return md_content

if __name__ == '__main__':
    title = "Sould I buy, sell, or hold Tesla stock?"
    # md_content = autoaskup(title)
    md_content = results_to_md("/home/ubuntu/Auto-GPT/clients/auto_gpt_workspace/2023-06-11_08-27-49_KFmnW")

    print("MO content\n", md_content)
        
    # Usage example:
    article_data = {
        "title": title,
        "body_markdown": md_content,
        "published": True,
        "series": "string",
        "tags": "autogpt",
        "organization_id": 0
    }

    api_key = os.environ['FOREM_API_KEY']
    status_code, response_json = create_article(api_key, article_data)

    print(status_code)
    print(response_json)