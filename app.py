# Streamlit page for Crewline: page 1 views a run (timeline, totals per agent, final report),
# page 2 approves or denies risky actions that a running harness is waiting on.
# Start with: streamlit run app.py   (and set APPROVAL_MODE = "streamlit" in config to use page 2)
import json
from collections import defaultdict

import pandas as pd
import streamlit as st

from harness import config, state

# Brand: page title and logo from brand/BRAND.md; theme comes from .streamlit/config.toml.
st.set_page_config(page_title="Crewline", page_icon=str(config.ROOT / "brand" / "logo.svg"), layout="wide")
STATUS_WORDS = {"ok": "🟢 OK", "retry": "🟡 RETRY", "rejected": "🟡 REJECTED", "error": "🔴 ERROR",
                "denied": "🔴 DENIED", "blocked": "🔴 BLOCKED", "injection": "🟣 INJECTION", "approval": "🔵 APPROVAL"}


# Page 1: pick a trace file and show what happened.
def runs_page() -> None:
    st.title("Crewline: runs")
    traces = sorted(config.RUNS_DIR.glob("*.jsonl"), reverse=True)
    if not traces:
        st.info("No runs yet. Get the demo data (docs/GUIDE.md, part 2), then run: python run.py --task myrepo")
        return
    path = st.selectbox("Run", traces, format_func=lambda p: p.stem)
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    start = events[0]["ts"]

    # Final report first. The trace cuts long text, so the full report comes from SQLite.
    st.subheader(f"Final status: {events[-1]['status']}")
    row = state.connect().execute("SELECT report FROM runs WHERE run_id = ?", (path.stem,)).fetchone()
    if row and row[0]:
        report = json.loads(row[0])
        st.dataframe(pd.DataFrame(report["findings"]), width="stretch")
        for item in report["missing"]:
            st.warning(f"MISSING {item}")
        for note in report["notes"]:
            st.info(f"NOTE {note}")
    else:
        st.caption("Full report not in this machine's runs.db (committed example traces have no database).")

    # Totals per agent from the model calls.
    totals = defaultdict(lambda: {"steps": 0, "tokens": 0, "est_cost_usd": 0.0, "model_seconds": 0.0})
    for e in events:
        if e["event_type"] == "llm_step":
            t = totals[e["agent"]]
            t["steps"] += 1
            t["tokens"] += e["input_tokens"] + e["output_tokens"]
            t["est_cost_usd"] += e["est_cost_usd"]
            t["model_seconds"] += e["seconds"]
    st.subheader("Totals per agent")
    st.caption("Cost is estimated at paid prices; the free tier costs $0.")
    st.dataframe(pd.DataFrame(totals).T, width="stretch")

    # Timeline: one row per event, status as a word plus colour dot.
    st.subheader("Timeline")
    st.dataframe(pd.DataFrame([{
        "t (s)": round(e["ts"] - start, 2), "status": STATUS_WORDS.get(e["status"], e["status"]),
        "agent": e["agent"], "event": e["event_type"], "tool": e["tool"] or "",
        "args": json.dumps(e["tool_args"]) if e["tool_args"] else "", "output": (e["output"] or "")[:200],
    } for e in events]), width="stretch", hide_index=True)


# Page 2: approvals waiting in SQLite. The harness polls the row and continues on a decision.
def approvals_page() -> None:
    st.title("Crewline: approvals")
    if config.APPROVAL_MODE != "streamlit":
        st.warning('APPROVAL_MODE in harness/config.py is "terminal", so the harness asks in the terminal instead.')
    db = state.connect()
    pending = db.execute("SELECT id, run_id, agent, action FROM approvals WHERE status = 'pending'").fetchall()
    if not pending:
        st.success("Nothing waiting for approval.")
    for approval_id, run_id, agent, action in pending:
        st.markdown(f"**🔵 APPROVAL NEEDED** · `{run_id}` · agent **{agent}** wants to: `{action}`")
        col1, col2 = st.columns(2)
        # Each button writes the decision; the waiting harness picks it up within half a second.
        for col, label, decision in ((col1, "Approve", "approved"), (col2, "Deny", "denied")):
            if col.button(label, key=f"{decision}-{approval_id}"):
                db.execute("UPDATE approvals SET status = ? WHERE id = ?", (decision, approval_id))
                db.commit()
                st.rerun()
    st.subheader("History")
    st.dataframe(pd.DataFrame(db.execute("SELECT id, run_id, agent, action, status FROM approvals ORDER BY id DESC").fetchall(),
                              columns=["id", "run", "agent", "action", "status"]), width="stretch", hide_index=True)
    if st.button("Refresh"):
        st.rerun()


# Sidebar switches between the two pages.
page = st.sidebar.radio("Page", ["Runs", "Approvals"])
runs_page() if page == "Runs" else approvals_page()
