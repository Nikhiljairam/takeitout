# Talk It Out — a voice journal (Streamlit + OpenRouter)

Record or type quick voice-note-style journal entries throughout the day,
then let an LLM (via [OpenRouter](https://openrouter.ai)) turn them into a
daily recap (mood, themes, follow-up question), a weekly narrative, gentle
"how you're doing" insights, and answers to free-form questions about your
own journal.

This is a Streamlit re-build of an original single-file HTML prototype,
swapped to use **OpenRouter** for the LLM calls so you can bring your own
key and pick whichever model you like.

## Features

- 🎤 Voice entries (recorded in-browser, transcribed with free Google
  speech recognition) or ⌨️ typed entries
- 📞 A short guided "daily check-in" Q&A mode
- 📅 Day view with an AI-generated recap (mood, themes, action items)
- 📆 Week view + an AI "week in review" narrative
- 🗓️ 30-day mood grid and recurring-theme tags
- 💭 "How you're doing" — a 14-day pattern read + a song suggestion + gentle nudges
- 🔎 "Ask your journal" — Q&A over the last 30 days of entries
- 🔥 Streak tracking, and a plain-text export of everything you've logged

## Project layout

```
talk-it-out/
├── app.py                          # Streamlit UI + page logic
├── llm.py                          # OpenRouter API wrapper
├── storage.py                      # SQLite persistence (entries, recaps, profile)
├── speech.py                       # Speech-to-text for recorded clips
├── requirements.txt
├── .streamlit/
│   └── secrets.toml.example        # copy to secrets.toml locally
└── data/                           # SQLite DB lives here (gitignored)
```

## 1. Run it locally

```bash
git clone https://github.com/<your-username>/talk-it-out.git
cd talk-it-out
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then edit .streamlit/secrets.toml and paste in your real OpenRouter key

streamlit run app.py
```

Get an OpenRouter API key at **https://openrouter.ai/keys** (sign up, then
"Create Key"). OpenRouter gives you access to Claude, GPT, Gemini, Llama,
and many other models through one key/endpoint, and lets you cap spend per key.

## 2. Push this to your own GitHub repo

From inside this folder:

```bash
git init
git add .
git commit -m "Initial commit: Talk It Out voice journal"
git branch -M main

# create an empty repo on GitHub first (via the website, or `gh repo create`),
# then point this local repo at it:
git remote add origin https://github.com/<your-username>/talk-it-out.git
git push -u origin main
```

If you have the GitHub CLI (`gh`) installed and authenticated, you can
create the remote repo in one step instead:

```bash
gh repo create talk-it-out --public --source=. --remote=origin --push
```

> **Important:** `secrets.toml` and the `data/` folder are in `.gitignore`
> on purpose — never commit your real API key or your journal database to
> a public repo.

## 3. Deploy on Streamlit Community Cloud

1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. Click **New app**, pick your `talk-it-out` repo, branch `main`, and
   set the main file path to `app.py`.
3. Before (or right after) deploying, open **Advanced settings → Secrets**
   (or, once deployed: **Manage app → Settings → Secrets**) and paste:

   ```toml
   OPENROUTER_API_KEY = "sk-or-v1-...your real key..."
   OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"
   ```

4. Save, and the app will redeploy with your key available as
   `st.secrets["OPENROUTER_API_KEY"]`.

You can change the model any time — either by editing the
`OPENROUTER_MODEL` secret, or per-session from the sidebar's "OpenRouter
model id" field in the running app. Any valid OpenRouter model id works,
e.g. `anthropic/claude-3.5-sonnet`, `openai/gpt-4o-mini`,
`google/gemini-flash-1.5`, `meta-llama/llama-3.1-70b-instruct`.

## Notes & limitations

- **Persistence:** entries are stored in a local SQLite file
  (`data/talk_it_out.db`). On Streamlit Community Cloud the filesystem is
  ephemeral — it resets when the app redeploys or wakes from a long sleep.
  Fine for casual personal use; if you want entries to survive indefinitely,
  swap `storage.py` for a hosted DB (Turso, Supabase, a Google Sheet, etc.)
  or mount a persistent volume if you self-host.
- **Speech-to-text:** uses the free Google Web Speech recognizer via the
  `SpeechRecognition` package — no extra API key needed, but accuracy on
  long or noisy recordings will be rougher than a paid STT service. Swap
  `speech.py` for Whisper/Deepgram/AssemblyAI if you want better accuracy.
- **Single user:** this app has no login system — it's built for one
  person's personal use per deployment, matching the original prototype.
- **Not medical advice:** the "How you're doing" panel is a reflection
  aid based only on what you've written, not a diagnosis.
