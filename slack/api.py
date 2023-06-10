import datetime
import json
import os
import random
import string
import sys

import openai

main_dir = os.getcwd()
sys.path.append(main_dir)


def init_task(user_message, options, openai_api_key):
    # Make workspace folder and write ai_settings.yaml in it
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d_%H-%M-%S")
    length = 5
    random_str = "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(length)
    )
    workspace_name = date_str + "_" + random_str
    workspace = os.path.join(os.getcwd(), "auto_gpt_workspace", workspace_name)
    os.makedirs(workspace, exist_ok=True)
    ai_settings = user_message2ai_settings(
        user_message, options["api_budget"], openai_api_key=openai_api_key
    )
    with open(os.path.join(workspace, "ai_settings.yaml"), "w") as f:
        f.write(ai_settings)

    return ai_settings, workspace


def user_message2ai_settings(
    user_message, api_budget=1, infer=False, openai_api_key=None
):
    if infer:
        prompt = f"""
An AI bot will handle given request. Provide name, role and goals for the AI assistant in JSON format with following keys:
- "ai_name": AI names
- "ai_role": AI role, starting with 'an AI that'
- "ai_goals": List of 1~4 necessary sequential goals for the AI.
Simplify ai_goals as much as possible.

Request:
```
Write dummy text to 'dummy_text.txt' file
```
Response:
{{
    "ai_name": "DummyTextBot",
    "ai_role": "an AI that writes dummy text to 'dummy_text.txt' file.",
    "ai_goals": [
        "Generate dummy text.",
        "Write dummy text to 'dummy_text.txt' file."
    ]
}}
Request:
```
Decide whether to buy or sell Tesla stock, and write a report on the decision in markdown format in Korean.
```
Response:
{{
    "ai_name": "TeslaStockBot",
    "ai_role": "an AI that decides whether to buy or sell Tesla stock, and writes a report on the decision in markdown format in Korean.",
    "ai_goals": [
        "Research financial data of Tesla stock.",
        "Research recent news about Tesla.",
        "Based on research, make a decision whether to buy or sell Tesla stock.",
        "Write a report on the decision in markdown format in Korean."
    ]
}}
Request:
```
{user_message}
```
Response:
"""
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            api_key=openai_api_key,
        )
        data = json.loads(response.choices[0]["message"]["content"])
        ai_goals_str = "\n".join(["- " + goal for goal in data["ai_goals"]])
        ai_settings = f"""
ai_name: {data['ai_name']}
ai_role: {data['ai_role']}
ai_goals:
{ai_goals_str}
- Make sure to write a report
api_budget: {api_budget}
"""
    else:
        user_messages = user_message.split("\n")
        user_messages = [
            user_message.replace('"', '\\"') for user_message in user_messages
        ]
        goals = [
            f'- "{user_message}"'
            for user_message in user_messages
            if user_message != ""
        ]
        goals = "\n".join(goals)
        ai_settings = f"""ai_name: AutoAskUp
ai_role: an AI that achieves below GOALS.
ai_goals:
{goals}
- Make sure to write a report
api_budget: {api_budget}"""
    return ai_settings


if __name__ == "__main__":
    print(sys.argv)
    print(os.getcwd())
    _, folder, gpt3only = sys.argv
    from autogpt.main import run_auto_gpt

    run_auto_gpt(
        continuous=True,
        continuous_limit=None,
        ai_settings=os.path.join(folder, "ai_settings.yaml"),
        prompt_settings="prompt_settings.yaml",
        skip_reprompt=False,
        speak=False,
        debug=False,
        gpt3only=eval(gpt3only),
        gpt4only=False,
        memory_type=None,
        browser_name=None,
        allow_downloads=False,
        skip_news=True,
        workspace_directory=folder,
        install_plugin_deps=False,
    )
