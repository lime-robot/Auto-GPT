import sys
import os
from autogpt.logs import update_logger, logger

main_dir = os.getcwd()
sys.path.append(main_dir)

def log_callback_func(title, content):
    print("CALLBACK", title, content)


if __name__ == "__main__":
    print(sys.argv)
    print(os.getcwd())

    logger.typewriter_log("Starting AutoGPT")

    update_logger(log_callback_func)
    logger.typewriter_log("Logger Updated")

    _, folder = sys.argv
    from autogpt.main import run_auto_gpt

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
