import asyncio
import datetime
import os
import re
import tempfile

import discord
from autogpt.logs import logger, update_logger
from autogpt.main import run_auto_gpt
from discord.ext import commands

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="!", intents=intents)


whitelist = [1071691298374959124, 987566840257589298]


def remove_ansi_escape_sequences(text):
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    cleaned_text = ansi_escape.sub("", text)

    return cleaned_text


def prepare_and_return_folder(content):
    content = re.sub(r"<@U[A-Z0-9]+>", "", content)
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d_%H-%M-%S")

    # Create a temporary directory with a unique name
    folder = tempfile.mkdtemp(
        prefix=date_str + "_", dir=os.path.join(os.getcwd(), "auto_gpt_workspace")
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


@client.event
async def on_ready():
    print("Logged in as {0.user}".format(client))


@client.event
async def on_message(message):
    if message.guild is None:
        print("Not a guild message", message)
        return

    loop = asyncio.get_event_loop()

    print(f"Got message from {message.guild.id}", type(message.guild.id))
    mention = discord.utils.get(message.mentions, id=client.user.id)
    if mention:
        if message.guild.id not in whitelist:
            print("Not allowed to talk in this server")
            await message.channel.send(
                f"Sorry, I am not allowed to talk in this server({message.guild.id}). Ask the server owner or hunkim+askup@gmail.com to add me to the whitelist."
            )
            return

        text = message.content.replace(f"<@{client.user.id}>", "").strip()
        result_dir = prepare_and_return_folder(text)
        await message.channel.send(f"Running AutoGPT with the following goal: {text}")

        def stream_log_call_back(title, content):
            content = remove_ansi_escape_sequences(content)
            title = remove_ansi_escape_sequences(title)
            loop.call_soon_threadsafe(
                asyncio.create_task,
                message.channel.send(f"{title} {content}"),
            )

        # run_auto_gpt_wrapper(folder=result_dir, stream_log_call_back=stream_log_call_back)
        loop.run_in_executor(
            None, run_auto_gpt_wrapper, result_dir, stream_log_call_back
        )


client.run(TOKEN)
