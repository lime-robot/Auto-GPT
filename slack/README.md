# Slack Bot for Auto GPT

**Tested on Linux**

1. Create Slack Bot.
2. Add `secrets.json` to slack folder. Keys are App ID from App Credentials.
    ```json
    {
        "A058~~": {
            "WORKSPACE_NAME": "Test1",
            "OPENAI_API_KEY": "sk-~~",
            "SLACK_SIGNING_SECRET": "~~",
            "SLACK_BOT_TOKEN": "xoxb-~~"
        },
        "A05B~~": {
            "WORKSPACE_NAME": "Test2",
            "OPENAI_API_KEY": "sk-~~",
            "SLACK_SIGNING_SECRET": "~~",
            "SLACK_BOT_TOKEN": "xoxb-~~"
        }
    }
    ```
3. Install wkhtmltopdf
    ```
    apt-get update
    apt-get install wkhtmltopdf
    ```
4. Install Chrome
    ```
    wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    dpkg -i google-chrome-stable_current_amd64.deb
    ```
5. Install Auto GPT requirements at **Auto-GPT(parent) directory**.
    ```
    pip install -r requirements.txt
    ```
6. Install requirements at **slack directory**
    ```
    pip install -r requirements.txt
    ```
7. Run server
    ```
    nohup uvicorn app:app --host 0.0.0.0 --port 30052 --reload &
    ```