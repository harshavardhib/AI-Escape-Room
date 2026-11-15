"""Version 2 - Reliable AI Escape Room.

Python owns state, rules and solutions (engine.py + game_config.json).
The LLM only (1) classifies the player's message and (2) narrates engine facts.
Without an API key the game still works, using a keyword parser and plain-text facts.

Run:  streamlit run app_v2.py
"""
import json
import os

import streamlit as st

from engine import Game, take_turn
from llm_client import DEFAULT_MODEL, LLM

st.set_page_config(page_title="The Locked Library (v2)", page_icon="🔐")
st.title("🔐 The Locked Library")
st.caption("Version 2: structured game state, validated actions, LLM as narrator.")


def new_game():
    st.session_state.game = Game("game_config.json")
    st.session_state.messages = [("assistant", st.session_state.game.cfg["intro"])]
    st.session_state.last_turn = None


if "game" not in st.session_state:
    new_game()
game: Game = st.session_state.game

with st.sidebar:
    api_key = st.text_input("Gemini API key (optional)", type="password",
                            value=os.getenv("GEMINI_API_KEY", ""))
    model = st.text_input("Model", value=os.getenv("GEMINI_MODEL", DEFAULT_MODEL))
    if st.button("Restart game"):
        new_game()
        st.rerun()
    st.markdown("---")
    st.markdown("**How to play:** " + game.cfg["help"])
    st.subheader("Inventory")
    names = game.inventory_names()
    st.write(", ".join(names) if names else "_empty_")
    st.subheader("Unlocked")
    st.write(", ".join(game.state["unlocked"]) if game.state["unlocked"] else "_nothing yet_")
    if st.checkbox("Show debug panel"):
        st.json(game.state)
        st.write("Last intent:")
        st.json(st.session_state.last_turn)

for role, text in st.session_state.messages:
    with st.chat_message(role):
        st.write(text)

if game.state["escaped"]:
    st.success("🎉 You escaped the library! Press Restart to play again.")
elif prompt := st.chat_input("What do you do?"):
    llm = None
    if api_key:
        try:
            llm = LLM(api_key, model)
        except Exception as e:
            st.warning(f"LLM unavailable ({e}); using the built-in parser.")
    out = take_turn(game, prompt, llm)
    st.session_state.messages += [("user", prompt), ("assistant", out["reply"])]
    st.session_state.last_turn = {"intent": out["intent"], "narrated_by_llm": out["narrated"]}
    st.rerun()
