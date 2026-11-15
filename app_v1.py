"""Version 1 - Interactive AI Escape Room (the LLM is the whole game).

Run:  streamlit run app_v1.py
Needs a free Gemini API key (https://aistudio.google.com/apikey) in GEMINI_API_KEY
or pasted into the sidebar.
"""
import os

import streamlit as st

from llm_client import DEFAULT_MODEL, chat

ESCAPE_MARKER = "[[ESCAPED]]"

SYSTEM_PROMPT = f"""You are the Game Master of a text escape-room game. Stay in character at all times.

SETTING: The player wakes up locked in an old library. The room has exactly these objects:
a desk, a bookshelf, a painting, a locked drawer, and a door with a four-digit keypad.

SECRET GAME DESIGN (never reveal it directly; let the player discover it):
- Desk: a handwritten note lies on it: "The red books know my drawer's number. Read them from left to right."
- Bookshelf: three red books stand out. Their spines carry handwritten numbers 3, 8, 5 (left to right).
- Drawer: opens with the three-digit code 385. Inside is a small brass key.
- Painting: the frame swings away from the wall and hides a small steel wall safe with a keyhole.
- Wall safe: opens with the brass key. Inside is a slip of paper reading 7392.
- Door: opens with the four-digit code 7392. That is the escape.

RULES:
- Describe what the player sees and respond to their actions in 2-4 vivid sentences.
- Reveal clues only when the player examines the right object. Do not hand out solutions.
- Keep track of what the player has found and collected during the conversation.
- Do not invent extra objects, keys or shortcuts.
- When the player enters 7392 on the door, narrate the escape and end your message with the exact marker {ESCAPE_MARKER}.
"""

INTRO = ("You wake on a cold wooden floor. The air smells of dust and old paper. You are locked "
         "inside a library: a heavy oak desk with a drawer, a tall bookshelf, a large framed "
         "painting, and a sturdy door with a four-digit keypad. Somewhere in this room is the way out.")
INSTRUCTIONS = ("Type what you want to do in plain language, for example *\"examine the bookshelf\"*, "
                "*\"take the note\"*, or *\"try 123 on the drawer\"*. Use **Restart** in the sidebar to start over.")

st.set_page_config(page_title="The Locked Library (v1)", page_icon="🔐")
st.title("🔐 The Locked Library")
st.caption("Version 1: the LLM is Game Master, rule keeper and memory.")


def new_game():
    st.session_state.history = []      # list of (role, text) sent to the LLM
    st.session_state.escaped = False


if "history" not in st.session_state:
    new_game()

with st.sidebar:
    api_key = st.text_input("Gemini API key", type="password", value=os.getenv("GEMINI_API_KEY", ""))
    model = DEFAULT_MODEL
st.caption(f"Gemini model: {model}")
    if st.button("Restart game"):
        new_game()
        st.rerun()
    st.markdown("---")
    st.markdown(INSTRUCTIONS)

with st.chat_message("assistant"):
    st.write(INTRO)
for role, text in st.session_state.history:
    with st.chat_message("assistant" if role == "model" else "user"):
        st.write(text)

if st.session_state.escaped:
    st.success("🎉 You escaped the library! Press Restart to play again.")
elif prompt := st.chat_input("What do you do?"):
    if not api_key:
        st.error("Please add your Gemini API key in the sidebar.")
        st.stop()
    with st.chat_message("user"):
        st.write(prompt)
    # The intro is part of the conversation the model should know about.
    history = [("user", "Begin the game."), ("model", INTRO)] + st.session_state.history
    try:
        reply = chat(api_key, model, SYSTEM_PROMPT, history, prompt)
    except Exception as e:  # network / quota / key errors
        st.error(f"The Game Master could not answer: {e}")
        st.stop()
    escaped = ESCAPE_MARKER in reply
    reply = reply.replace(ESCAPE_MARKER, "").strip()
    st.session_state.history += [("user", prompt), ("model", reply)]
    st.session_state.escaped = escaped
    st.rerun()
