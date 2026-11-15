# The Locked Library: AI Escape Room

Two versions of an LLM-driven escape room (Python, Streamlit, Google Gemini free tier).

| File | Purpose |
|---|---|
| `app_v1.py` | Version 1: Gemini is the whole game (prompt-only) |
| `app_v2.py` | Version 2: structured state + validation, LLM as parser/narrator |
| `engine.py` | Game state, action validation, intent sanitising, leak filter |
| `game_config.json` | Room, items, locks, solutions, hints |
| `llm_client.py` | Gemini wrapper |
| `test_engine.py` | 13 offline tests for Version 2 |
| `architecture.md` | Architecture diagrams (Mermaid) for both versions |
| `test_cases.md` | Version 1 vs Version 2 test cases |
| `report.md` | Short report |

## Run

```
pip install -r requirements.txt
export GEMINI_API_KEY=your_key      # https://aistudio.google.com/apikey
streamlit run app_v1.py
streamlit run app_v2.py             # also playable with no key (keyword parser)
python -m unittest test_engine -v
```

The default model is `gemini-2.0-flash`; change it in the sidebar or with `GEMINI_MODEL` if Google retires it.

## Walkthrough (spoilers)

examine desk -> take note -> examine bookshelf -> examine books (3-8-5) -> try 385 on drawer -> take key -> move the painting -> use key on safe -> take paper (7392) -> try 7392 on door.
