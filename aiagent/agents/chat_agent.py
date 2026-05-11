from openai import OpenAI

from aiagent.env_utils import get_openai_api_key


def create_client() -> OpenAI:
    api_key = get_openai_api_key()
    return OpenAI(api_key=api_key)


def run_cli_chat() -> None:
    client = create_client()

    print("=== ChainGuardian CLI Chat ===")
    print("Type 'exit' or 'quit' to leave the chat.\n")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful AI assistant specialized in blockchain security "
                "and anomaly detection. Behave like a research assistant that "
                "helps the user step-by-step, asking brief clarifying questions "
                "only when absolutely necessary."
            ),
        }
    ]

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("AI: Bye~")
            break

        messages.append({"role": "user", "content": user_input})

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
            )
        except Exception as e:
            print(f"[Error] OpenAI API call failed: {e}")
            continue

        msg_obj = response.choices[0].message
        assistant_reply = msg_obj.content

        print(f"AI: {assistant_reply}\n")

        messages.append({"role": "assistant", "content": assistant_reply})
