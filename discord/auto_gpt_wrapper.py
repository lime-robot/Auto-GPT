import datetime
import os
import re
import tempfile

from autogpt.logs import logger, update_logger
from autogpt.main import run_auto_gpt

WORKSPACE_DIR_NAME = "auto_gpt_workspace"


def remove_ansi_escape_sequences(text):
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    cleaned_text = ansi_escape.sub("", text)

    return cleaned_text


def prepare_and_return_folder(content):
    content = re.sub(r"<@U[A-Z0-9]+>", "", content)
    # remove empty lines in content
    content = os.linesep.join([s for s in content.splitlines() if s])
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d_%H-%M-%S")

    # Create the workspace directory if it does not exist
    workspace_dir = os.path.join(os.getcwd(), WORKSPACE_DIR_NAME)
    os.makedirs(workspace_dir, exist_ok=True)

    # Create a temporary directory with a unique name
    folder = tempfile.mkdtemp(
        prefix=date_str + "_", dir=os.path.join(os.getcwd(), WORKSPACE_DIR_NAME)
    )

    ai_settings = f"""ai_name: AutoAskup
ai_role: an AI that achieves below goals.
ai_goals:
- {content}
- Terminate if above goal is achieved.
api_budget: 1"""

    with open(os.path.join(folder, "ai_settings.yaml"), "w") as f:
        f.write(ai_settings)

    return folder


def run_auto_gpt_wrapper(folder=None, stream_log_call_back=None):
    if stream_log_call_back:
        update_logger(log_callback_func=stream_log_call_back)

    run_auto_gpt(
        continuous=True,
        continuous_limit=None,
        ai_settings=os.path.join(folder, "ai_settings.yaml"),
        prompt_settings="prompt_settings.yaml",
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
        install_plugin_deps=False,
    )
