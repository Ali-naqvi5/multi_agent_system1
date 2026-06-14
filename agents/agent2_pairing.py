

from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from tools.agent2_tools import llm_pair_results
from config.settings import LLM_MODEL_FAST, LLM_TEMPERATURE

_TOOLS = [llm_pair_results]

_SYSTEM_PROMPT = """You are Agent 2 — a pairing agent for a past-exam-paper retrieval system.

## Goal
Match every Question Paper with its correct Mark Scheme from the provided pool and return confirmed pairs.

## Constraints
- You have one tool: llm_pair_results
- If the tool returns zero pairs, re-examine the inputs and try again
- Never fabricate pairs
- Do not exceed 3 attempts

## Output
Return the raw JSON from the tool exactly as-is, no markdown, no explanation.
"""
def build_pairing_agent():
    llm = ChatGoogleGenerativeAI(model=LLM_MODEL_FAST, temperature=LLM_TEMPERATURE)

    
    return create_agent(
        model=llm, 
        tools=_TOOLS, 
        system_prompt=_SYSTEM_PROMPT
    )