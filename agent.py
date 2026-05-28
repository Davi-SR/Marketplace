import os
import uuid
import json
from pathlib import Path
from sqlalchemy import create_engine
from agno.agent import Agent
from agno.tools.sql import SQLTools
from agno.models.openai import OpenAIChat
from agno.db.sqlite import SqliteDb
from dotenv import load_dotenv

BACK_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BACK_DIR / ".env")

db_url = os.getenv("DB_URL")
api_key = os.getenv("OPENAI_API_KEY")

if not db_url or db_url.strip() == "":
    db_url = "duckdb:///banco_odontogroup.db"
elif not db_url.startswith("duckdb://"):
    formatted_url = db_url.replace("\\", "/")
    db_url = f"duckdb:///{formatted_url}"

engine = create_engine(db_url, connect_args={'read_only': True})
agent_db = SqliteDb(db_file=str(BACK_DIR / "aibi_storage.db"))

PROMPTS_DIR = BACK_DIR / "prompts"

with open(PROMPTS_DIR / "knowledge.JSON", "r", encoding="utf-8") as f:
    db_context = f.read()

with open(PROMPTS_DIR / "prompt.md", "r", encoding="utf-8") as f:
    instructions_prompt = f.read()

def get_agent(session_id: str = None):
    if session_id is None:
        session_id = f"Conversa_{uuid.uuid4().hex[:8]}"
    
    return Agent(
        tools=[SQLTools(db_engine=engine)], 
        db=agent_db,
        session_id=session_id,
        model=OpenAIChat(id="gpt-4o-2024-08-06", api_key=api_key),
        instructions=[
            instructions_prompt,
            "\n### TODO O CONTEXTO SOBRE O BANCO DE DADOS (knowledge.JSON):",
            db_context
        ],
        markdown=True,
        add_history_to_context=True,
    )
agent = get_agent()

if __name__ == "__main__":
    agent.print_response("Olá! Quem é você?")