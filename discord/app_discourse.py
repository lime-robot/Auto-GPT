import os

import requests
from auto_gpt_wrapper import (
    prepare_and_return_folder,
    remove_ansi_escape_sequences,
    run_auto_gpt_wrapper,
)
from fastapi import BackgroundTasks, FastAPI, Request

app = FastAPI()

# Replace with your Discourse API details
discourse_api_key = os.environ["DISCOURSE_API_KEY"]
discourse_api_username = "discobot"
discourse_url = "http://ec2-35-89-115-28.us-west-2.compute.amazonaws.com:4200"


@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    post = data.get("post", None)
    if not post:
        return {"error": "No post data"}

    if post["username"] == discourse_api_username:
        print("Bot post, ignoring")
        return {"message": "Bot post, ignoring"}

    post_title = post["topic_title"]
    post_content = post["raw"]

    order = f"{post_title} {post_content} Write in MD format"

    # Now create a new post in the same topic

    def post_thread(title, content):
        post_data = {
            "reply_to_post_number": post["id"],
            "raw": f"## {title}\n\n{content}",
            "topic_id": post["topic_id"],
        }

        new_post_response = requests.post(
            f"{discourse_url}/posts.json",
            data=post_data,
            headers={
                "Api-Key": discourse_api_key,
                "Api-Username": discourse_api_username,
            },
            timeout=10,
        )

        print(new_post_response.text)

    result_dir = prepare_and_return_folder(order)
    background_tasks.add_task(
        run_auto_gpt_wrapper, folder=result_dir, stream_log_call_back=post_thread
    )

    return {"message": "OK"}


# This would allow you to run it directly using `uvicorn script_name:app`
if __name__ == "__main__":
    # Now create a new post in the same topic
    post_data = {
        "reply_to_post_number": 8,
        "raw": "Echo: 123 Echo 123 Echo 123 Echo 123",
    }

    new_post_response = requests.post(
        f"{discourse_url}/posts.json",
        data=post_data,
        headers={"Api-Key": discourse_api_key, "Api-Username": discourse_api_username},
        timeout=10,
    )

    print(new_post_response.text)
    print(discourse_api_key, discourse_api_username)
