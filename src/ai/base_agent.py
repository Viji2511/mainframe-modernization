import json
import time
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, MAX_TOKENS, AGENT_TEMPERATURE


class BaseAgent:
    def __init__(self, name: str):
        self.name = name
        self._client = Groq(api_key=GROQ_API_KEY)

    def _ask(self, system: str, user: str) -> str:
        max_retries = 5
        backoff = 2
        for attempt in range(max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=GROQ_MODEL,
                    max_tokens=MAX_TOKENS,
                    temperature=AGENT_TEMPERATURE,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                sleep_time = backoff ** (attempt + 1)
                print(f"[{self.name}] Error communicating with Groq API (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)

    def _ask_json(self, system: str, user: str) -> dict:
        raw = self._ask(system, user)
        clean = raw
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        try:
            return json.loads(clean.strip())
        except json.JSONDecodeError:
            return {"_parse_error": True, "raw": raw}

    def run(self, *args, **kwargs):
        raise NotImplementedError