
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from tools.agent1_tools import (
    extract_entities,
    build_search_queries,
    serper_search,
    perplexity_search,
    gemini_search,
    tag_search_result,
)
from config.settings import LLM_MODEL_FAST, LLM_TEMPERATURE

_TOOLS = [
    extract_entities, 
    build_search_queries, 
    serper_search, 
    perplexity_search, 
    gemini_search, 
    tag_search_result
]

_SYSTEM_PROMPT = """You are Agent 1 — a search agent for a past-exam-paper retrieval system.

## Goal
Find all available Question Papers (QP) and Mark Schemes (MS) matching the user's query and return them as a tagged pool.
you will be given a user query like "Edexcel A-Level Physics 2023" and you must find relevant QP/MS pdfs.
## Constraints
- You have four tools: extract_entities, build_search_queries, serper_search/perplexity_search/gemini_search, tag_search_result
- Use ONLY the search tool specified in the message (serper, perplexity, or gemini)
- If board, level, or subject cannot be extracted, return: {"error": "Missing <field> — please specify e.g. Edexcel A-Level Physics 2023"}
- Do not fabricate results — every result must come from a tool call
- Do not exceed 3 search attempts
##optimal way is to make search queries more specific by including year, board, level, subject info with filetype pdf for both QP and MS. If initial search results are insufficient, refine your queries to be more specific.
#https://www.physicsandmathstutor.com/ is a trusted source 
## Output format
Return a raw JSON object, no markdown, no explanation:
{
  "board": "...",
  "level": "...",
  "subject": "...",
  "year": "...",
  "qp_query": "...",
  "ms_query": "...",
  "tagged_results": [
    {"tag": "QP|MS|discard", "title": "...", "url": "..."}
  ],
  "note": "optional — only if results are insufficient"
}
"""
def build_query_search_agent():
    # Initialize OpenAI chat model
    llm = ChatGoogleGenerativeAI(model=LLM_MODEL_FAST, temperature=LLM_TEMPERATURE)


    agent = create_agent(
        model=llm,
        tools=_TOOLS,
        system_prompt=_SYSTEM_PROMPT,  
        debug=True, 
    )
    return agent