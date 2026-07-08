import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = "llama-3.3-70b-versatile"
TARGET_DB: str = os.getenv("TARGET_DB", "postgresql")
MAX_TOKENS: int = 2048
AGENT_TEMPERATURE: float = 0.0
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "outputs")

# Generalized DSN qualifiers to ignore when resolving copybooks/programs
IGNORE_DSN_QUALIFIERS_STR = os.getenv("IGNORE_DSN_QUALIFIERS", "AWS,M2,VSAM,KSDS,PS,CARDDEMO")
IGNORE_DSN_QUALIFIERS = [q.strip().upper() for q in IGNORE_DSN_QUALIFIERS_STR.split(",") if q.strip()]