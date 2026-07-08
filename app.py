import datetime as dt

import streamlit as st

import storage
from llm import call_llm, safe_parse_json, LLMError
from speech import transcribe_audio_bytes, TranscriptionError

st.set_page_config(page_title="Talk It Out — a voice journal", page_icon="🎙️", layout="centered")
storage.init_db()

KIND_META = {
    "moment": {"icon": "🕐", "label": "point-in-time"},
    "eod": {"icon": "🌙", "label": "end of day"},
    "call": {"icon": "📞", "label": "phone check-in"},
}
MOOD_COLOR_HINT = "🟢 great · 🟡 okay · 🟠 rough · 🔴 heavy"


def today_str():
    return dt.date.today().isoformat()


def yesterday_str():
    return (dt.date.today() - dt.timedelta(days=1)).isoformat()


def now_time_str():
    return dt.datetime.now().strftime("%H:%M")


# ---------------------------------------------------------------------------
# Welcome / profile
# ---------------------------------------------------------------------------
profile = storage.get_profile()
if "profile" not in st.session_state:
    st.session_state.profile = profile

if not st.session_state.profile:
    st.markdown("## 🎙️ Talk It Out")
    st.caption("A voice journal that listens, recaps your day, and reflects patterns back to you.")
    with st.form("setup_form"):
        name = st.text_input("What should we call you?")
        submitted = st.form_submit_button("Start journaling")
        if submitted:
            if name.strip():
                storage.save_profile(name.strip())
                st.session_state.profile = {"name": name.strip(), "phone": ""}
                st.rerun()
            else:
                st.warning("Enter a name to continue.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"### Hey, {st.session_state.profile['name']} 👋")
    if st.button("Switch profile"):
        storage.clear_profile()
        st.session_state.profile = None
        st.rerun()

    st.divider()
    st.markdown("**Model**")
    st.session_state.model_override = st.text_input(
        "OpenRouter model id",
        value=st.session_state.get("model_override", "anthropic/claude-3.5-sonnet"),
        help="Any OpenRouter model id, e.g. anthropic/claude-3.5-sonnet, "
        "openai/gpt-4o-mini, google/gemini-flash-1.5",
    )
    st.caption("Requires OPENROUTER_API_KEY set in Secrets.")

    st.divider()
    all_entries = storage.get_entries()

    def has_entry(ds):
        return any(e["date"] == ds for e in all_entries)

    cursor = dt.date.today()
    if not has_entry(today_str()):
        cursor -= dt.timedelta(days=1)
    streak = 0
    while has_entry(cursor.isoformat()):
        streak += 1
        cursor -= dt.timedelta(days=1)
    st.markdown(f"🔥 **{streak} day{'s' if streak != 1 else ''} streak**")

    if all_entries:
        lines = [f"[{e['date']} {e['time']}] ({KIND_META[e['kind']]['label']}) {e['text']}" for e in all_entries]
        st.download_button(
            "Export all entries (.txt)",
            data="\n\n".join(lines),
            file_name="talk-it-out-entries.txt",
            mime="text/plain",
        )

st.title("🎙️ Talk It Out")
st.caption("A voice journal — record or type what's going on, and let it recap the day for you.")

tabs = st.tabs(["📝 Log", "📅 Day", "📆 Week", "🗓️ Month & themes", "💭 How you're doing", "🔎 Ask your journal"])

# ---------------------------------------------------------------------------
# TAB: Log an entry
# ---------------------------------------------------------------------------
with tabs[0]:
    st.subheader("Log a moment")
    mode = st.radio("How do you want to capture this?", ["🎤 Voice", "⌨️ Type"], horizontal=True)

    transcript = st.session_state.get("draft_text", "")

    if mode == "🎤 Voice":
        audio = st.audio_input("Record your entry")
        if audio is not None:
            if st.button("Transcribe recording"):
                with st.spinner("Transcribing…"):
                    try:
                        transcript = transcribe_audio_bytes(audio.getvalue())
                        st.session_state.draft_text = transcript
                        st.success("Transcribed — edit below if anything came out wrong.")
                    except TranscriptionError as e:
                        st.error(str(e))

    draft = st.text_area(
        "Entry text",
        value=st.session_state.get("draft_text", transcript),
        height=140,
        key="draft_text_area",
        placeholder="Speak or type what's on your mind…",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        entry_date = st.date_input("Date", value=dt.date.today())
    with col2:
        entry_time = st.text_input("Time", value=now_time_str())
    with col3:
        kind = st.selectbox(
            "Kind",
            options=list(KIND_META.keys()),
            format_func=lambda k: f"{KIND_META[k]['icon']} {KIND_META[k]['label']}",
        )

    if st.button("💾 Save entry", type="primary"):
        text = draft.strip()
        if not text:
            st.warning("Nothing to save yet.")
        else:
            storage.add_entry(entry_date.isoformat(), entry_time, kind, text)
            st.session_state.draft_text = ""
            st.success("Saved.")
            st.rerun()

    st.divider()
    st.subheader("📞 Daily check-in (guided Q&A)")
    st.caption("A few quick questions about your day, compiled into one entry.")

    if "call_active" not in st.session_state:
        st.session_state.call_active = False
        st.session_state.call_exchanges = []
        st.session_state.call_question = None

    OPENING_QUESTION = "Hey! What are you up to right now?"

    if not st.session_state.call_active:
        if st.button("Start check-in"):
            st.session_state.call_active = True
            st.session_state.call_exchanges = []
            st.session_state.call_question = OPENING_QUESTION
            st.rerun()
    else:
        for ex in st.session_state.call_exchanges:
            st.chat_message("assistant").write(ex["q"])
            st.chat_message("user").write(ex["a"])
        if st.session_state.call_question:
            st.chat_message("assistant").write(st.session_state.call_question)

        answer = st.text_input("Your answer", key="call_answer")
        c1, c2 = st.columns(2)
        with c1:
            submit_clicked = st.button("Submit answer")
        with c2:
            end_clicked = st.button("End check-in")

        def compile_and_save_checkin():
            if st.session_state.call_exchanges:
                text = "\n\n".join(f"Q: {ex['q']}\nA: {ex['a']}" for ex in st.session_state.call_exchanges)
                storage.add_entry(today_str(), now_time_str(), "call", text)

        if end_clicked:
            compile_and_save_checkin()
            st.session_state.call_active = False
            st.session_state.call_question = None
            st.success("Check-in saved.")
            st.rerun()

        if submit_clicked and answer.strip():
            st.session_state.call_exchanges.append({"q": st.session_state.call_question, "a": answer.strip()})
            st.session_state.call_question = None

            if len(st.session_state.call_exchanges) >= 4:
                compile_and_save_checkin()
                st.session_state.call_active = False
                st.success("Sounds like a full day — check-in saved!")
                st.rerun()
            else:
                convo = "\n\n".join(f"Q: {ex['q']}\nA: {ex['a']}" for ex in st.session_state.call_exchanges)
                prompt = (
                    "You are a warm, casual friend checking in on someone during a quick voice call "
                    "about their day. So far:\n" + convo +
                    "\n\nAsk ONE short, natural next question to learn about whichever of these is not "
                    "yet covered: what they are currently doing, what has happened in their day so far, "
                    "and what their plan is for the rest of the day. Keep it brief and casual like a real "
                    "phone call, not a survey. If those are already reasonably covered, wrap up warmly "
                    "instead of asking another question.\n\nRespond with ONLY valid JSON, no markdown "
                    'fences: {"question":"next short question, or null if wrapping up","closing":"a '
                    'short warm sign-off line, empty string unless question is null"}'
                )
                try:
                    with st.spinner("…"):
                        text = call_llm(prompt, max_tokens=300)
                    parsed = safe_parse_json(text)
                    if parsed and parsed.get("question"):
                        st.session_state.call_question = parsed["question"]
                    else:
                        compile_and_save_checkin()
                        st.session_state.call_active = False
                        st.success(parsed.get("closing") if parsed else "Thanks for sharing — talk soon!")
                except LLMError as e:
                    compile_and_save_checkin()
                    st.session_state.call_active = False
                    st.error(str(e))
            st.rerun()

# ---------------------------------------------------------------------------
# TAB: Day view + recap
# ---------------------------------------------------------------------------
with tabs[1]:
    view_choice = st.radio("View", ["Today", "Yesterday"], horizontal=True)
    view_date = today_str() if view_choice == "Today" else yesterday_str()

    entries = storage.get_entries(date=view_date)
    st.subheader(f"{view_choice}'s entries")
    if not entries:
        st.info("Nothing logged yet.")
    else:
        for e in entries:
            km = KIND_META[e["kind"]]
            with st.container(border=True):
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"**{km['icon']} {e['time']}** — {e['text']}")
                if c2.button("Delete", key=f"del_{e['id']}"):
                    storage.delete_entry(e["id"])
                    st.rerun()

        if st.button("✨ Generate recap for this day"):
            transcript = "\n".join(f"{e['time']} ({KIND_META[e['kind']]['label']}): {e['text']}" for e in entries)
            prompt = (
                "Here are voice journal entries from one day, timestamped (some may be in Hindi, "
                "English, or a mix of both):\n" + transcript +
                "\n\nReturn ONLY valid JSON, no markdown fences, in exactly this shape: "
                '{"mood":"one or two word mood label, in English","moodEmoji":"a single emoji",'
                '"recap":"2-3 warm second-person sentences in English reflecting on the day",'
                '"actionItems":["short items mentioned that sound like tasks or reminders, empty '
                'array if none"],"followUpQuestion":"one gentle open question to sit with tomorrow",'
                '"themes":["1-3 short lowercase one or two word topic tags in English, e.g. work, '
                'sleep, family"]}'
            )
            try:
                with st.spinner("Listening back and writing your recap…"):
                    text = call_llm(prompt, max_tokens=800)
                parsed = safe_parse_json(text)
                if parsed:
                    storage.save_recap(view_date, parsed)
                    st.rerun()
                else:
                    st.error("Couldn't parse a recap that time — try again.")
            except LLMError as e:
                st.error(str(e))

    recap = storage.get_recap(view_date)
    if recap:
        with st.container(border=True):
            st.markdown(f"### {recap.get('moodEmoji', '')} {recap.get('mood', '')}")
            st.write(recap.get("recap", ""))
            if recap.get("actionItems"):
                st.markdown("**Mentioned:** " + " · ".join(recap["actionItems"]))
            if recap.get("followUpQuestion"):
                st.caption(f"💬 {recap['followUpQuestion']}")
            if recap.get("themes"):
                st.markdown(" ".join(f"`#{t}`" for t in recap["themes"]))

    st.divider()
    st.subheader("On this day")
    found_any = False
    for days_ago in (7, 30):
        d = (dt.date.today() - dt.timedelta(days=days_ago)).isoformat()
        past_entries = storage.get_entries(date=d)
        if past_entries:
            found_any = True
            st.markdown(f"**{days_ago} days ago, you said:**")
            st.info(f'"{past_entries[0]["text"]}"')
    if not found_any:
        st.caption("Nothing from 7 or 30 days ago yet.")

# ---------------------------------------------------------------------------
# TAB: Week
# ---------------------------------------------------------------------------
with tabs[2]:
    st.subheader("This week")
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cols = st.columns(7)
    week_dates = [(monday + dt.timedelta(days=i)).isoformat() for i in range(7)]
    for i, ds in enumerate(week_dates):
        r = storage.get_recap(ds)
        with cols[i]:
            st.caption(labels[i])
            st.markdown(f"<div style='text-align:center;font-size:26px'>{r['moodEmoji'] if r else '·'}</div>", unsafe_allow_html=True)

    selected = st.selectbox("View a day's recap", options=week_dates, index=today.weekday())
    r = storage.get_recap(selected)
    if r:
        with st.container(border=True):
            st.markdown(f"**{selected} — {r.get('moodEmoji','')} {r.get('mood','')}**")
            st.write(r.get("recap", ""))
    else:
        st.caption("No recap generated for that day yet.")

    st.divider()
    if st.button("🧵 Weave this week into a narrative"):
        recap_texts = []
        for ds in week_dates:
            r = storage.get_recap(ds)
            if r:
                recap_texts.append(f"{ds}: {r.get('recap','')}")
        if not recap_texts:
            st.info("No daily recaps yet this week — generate a few daily recaps first.")
        else:
            prompt = (
                "Here are daily recap notes from one person's week:\n" + "\n".join(recap_texts) +
                '\n\nWrite a short, warm "week in review" narrative (4-6 sentences, second person, '
                "plain prose, no headers or bullet points) that notices any pattern across the days."
            )
            try:
                with st.spinner("Weaving the week together…"):
                    text = call_llm(prompt, max_tokens=500)
                st.success("")
                st.write(text)
            except LLMError as e:
                st.error(str(e))

# ---------------------------------------------------------------------------
# TAB: Month grid + themes
# ---------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Last 30 days")
    all_recaps = storage.all_recaps()
    dates_logged = storage.all_dates_with_entries()
    days = [(dt.date.today() - dt.timedelta(days=i)) for i in range(29, -1, -1)]
    row = st.columns(10)
    for idx, d in enumerate(days):
        ds = d.isoformat()
        r = all_recaps.get(ds)
        label = r["moodEmoji"] if r else ("•" if ds in dates_logged else "")
        with row[idx % 10]:
            st.markdown(
                f"<div title='{ds}' style='text-align:center;border:1px solid #444;border-radius:6px;"
                f"padding:6px 0;margin-bottom:4px;font-size:15px'>{label}</div>",
                unsafe_allow_html=True,
            )
        if idx % 10 == 9 and idx != len(days) - 1:
            row = st.columns(10)

    st.divider()
    st.subheader("Recurring themes")
    counts = {}
    for r in all_recaps.values():
        for t in r.get("themes", []):
            key = t.lower()
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        st.caption("Themes show up here once you've generated a few daily recaps.")
    else:
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:8]
        st.markdown(" ".join(f"`#{k} · {v}`" for k, v in top))

# ---------------------------------------------------------------------------
# TAB: Insights ("How you're doing")
# ---------------------------------------------------------------------------
with tabs[4]:
    st.subheader("How you're doing")
    st.caption(
        "Reads back through your last 14 days of entries — a feeling check, a song for right "
        "now, and a couple of gentle nudges. Reflections, not a diagnosis."
    )
    if st.button("Get insights"):
        cutoff = (dt.date.today() - dt.timedelta(days=14)).isoformat()
        relevant = storage.get_entries(since=cutoff)
        if len(relevant) < 3:
            st.info("Log a few more entries (at least 3 in the last two weeks) to get a meaningful read.")
        else:
            history_text = "\n".join(
                f"{e['date']} {e['time']} ({KIND_META[e['kind']]['label']}): {e['text']}" for e in relevant
            )
            prompt = (
                "Here is a personal voice journal from the last 14 days (entries may be in Hindi, "
                "English, or a mix):\n" + history_text +
                "\n\nBased only on what is explicitly said in these entries, respond with ONLY valid "
                'JSON, no markdown fences, in exactly this shape:\n{"currentFeeling":"2-3 sentences '
                "in English, second person, warm and grounded, describing how the person seems to be "
                "doing lately based on patterns in what they actually said. Do not use clinical or "
                'mental-health diagnostic labels.","song":{"title":"a real existing song title",'
                '"artist":"the real artist name","reason":"one sentence connecting it to their recent '
                'mood or something they mentioned"},"suggestions":["2-4 short, gentle lifestyle or '
                "habit suggestions (sleep, movement, breaks, connecting with people, etc) that each "
                "tie back to something specific mentioned in the entries, phrased as gentle "
                'suggestions not prescriptions"]}'
            )
            try:
                with st.spinner("Reading back through the last two weeks…"):
                    text = call_llm(prompt, max_tokens=700)
                parsed = safe_parse_json(text)
                if parsed:
                    if parsed.get("currentFeeling"):
                        st.markdown("**Right now, it seems like…**")
                        st.write(parsed["currentFeeling"])
                    song = parsed.get("song")
                    if song and song.get("title"):
                        st.markdown(f"🎵 **{song['title']}** — {song.get('artist','')}")
                        st.caption(song.get("reason", ""))
                    if parsed.get("suggestions"):
                        st.markdown("**Worth trying**")
                        for s in parsed["suggestions"]:
                            st.markdown(f"- {s}")
                    st.caption(
                        "Generated from patterns in your own entries — not professional advice. If "
                        "something feels heavier than a nudge can fix, a real conversation with "
                        "someone you trust (or a professional) is worth more than an app."
                    )
                else:
                    st.error("Couldn't parse a read that time — try again.")
            except LLMError as e:
                st.error(str(e))

# ---------------------------------------------------------------------------
# TAB: Ask your journal
# ---------------------------------------------------------------------------
with tabs[5]:
    st.subheader("Ask your journal")
    st.caption("Ask about patterns across the last 30 days of entries.")
    q = st.text_input("e.g. What's been stressing me out lately?")
    if st.button("Ask") and q.strip():
        cutoff = (dt.date.today() - dt.timedelta(days=30)).isoformat()
        relevant = storage.get_entries(since=cutoff)
        if not relevant:
            st.info("Not enough entries in the last 30 days to answer from yet.")
        else:
            history_text = "\n".join(
                f"{e['date']} {e['time']} ({KIND_META[e['kind']]['label']}): {e['text']}" for e in relevant
            )
            prompt = (
                "Here is a personal voice journal from the last 30 days (entries may be in Hindi, "
                "English, or a mix of both):\n" + history_text +
                "\n\nAnswer this question about the journal in English, second person, 3-5 sentences, "
                "referencing specific days where useful. If the journal genuinely does not contain "
                f"enough to answer, say so honestly rather than guessing.\n\nQuestion: {q}"
            )
            try:
                with st.spinner("Reading back through your journal…"):
                    text = call_llm(prompt, max_tokens=500)
                st.write(text)
            except LLMError as e:
                st.error(str(e))
