import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = "llama-3.3-70b-versatile"
TARGET_DB: str = os.getenv("TARGET_DB", "postgresql")
MAX_TOKENS: int = 2048
AGENT_TEMPERATURE: float = 0.0
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "outputs")