# Architecture diagrams

Both diagrams are Mermaid; they render on GitHub, in VS Code (Markdown Preview Mermaid) and at https://mermaid.live.

## Version 1 - LLM is everything

```mermaid
flowchart LR
    P([Player]) -->|natural-language message| UI[Streamlit chat UI<br/>app_v1.py]
    UI -->|system prompt with room + SECRET solutions<br/>+ full chat history + new message| LLM[(Gemini API<br/>Game Master)]
    LLM -->|narrative reply<br/>+ [[ESCAPED]] marker| UI
    UI -->|strip marker, show reply| P
    UI --- MEM[/st.session_state.history<br/>only memory = chat transcript/]
```

State, rules, solutions and win detection all live inside the LLM's context. Nothing is enforced outside the model.

## Version 2 - Python owns the truth, LLM narrates

```mermaid
flowchart TB
    P([Player]) -->|message| UI[Streamlit UI<br/>app_v2.py]
    UI --> TT[take_turn<br/>engine.py]

    subgraph Untrusted["LLM (untrusted, no secrets)"]
        IP[Intent parser<br/>text -> JSON action + noun phrases]
        NR[Narrator<br/>facts -> prose]
    end

    TT -->|1. player text| IP
    IP -->|raw JSON| SAN[sanitize_intent<br/>whitelist actions, Python resolves names,<br/>Python extracts digits, META filter]
    TT -.->|LLM down / invalid| RP[rule_parse<br/>keyword fallback]
    SAN --> VAL
    RP --> VAL

    subgraph Trusted["Python (trusted)"]
        CFG[(game_config.json<br/>objects, items, locks, solutions, hints)]
        ST[(Game state<br/>visible_objects, item_status,<br/>inventory, unlocked, revealed_secrets, escaped)]
        VAL[Game.apply<br/>action validation + inventory checks]
        LK[leaks<br/>output filter]
        CFG --> VAL
        VAL <--> ST
    end

    VAL -->|2. facts: success/failure decided by Python| TT
    TT -->|3. facts only| NR
    NR -->|prose| LK
    LK -->|clean prose, else plain facts| UI
    UI -->|reply + sidebar inventory| P
```

Key property: the player's text never reaches the state. Only a validated intent does, and only `Game.apply` mutates state.
