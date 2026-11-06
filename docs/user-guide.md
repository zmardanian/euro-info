# Euro Info user guide

## What's new in 4.0

- **Briefing** (Ctrl+1) is the home page: developing stories ranked by importance. Each card groups every
  report about one event; hover the score for the reasons. **Write AI briefing** turns the top stories into a
  sectioned, cited briefing.
- **Latest news** (Ctrl+2) shows one card per story; **All reports** opens the others.
- **Regions** (Europe · United States · Global) follow what a story is about. **Topics**: Politics, Economy,
  Technology, Security. **Focus** hides sport, celebrity, lifestyle and local US stories.
- **Trending** subjects sit under the weather strip; click one to filter, click again to clear.
- **Ask AI**: type a question in the search box and press Ask AI (Ctrl+Enter). The local model answers from
  the loaded stories and your library, with numbered citations.
- **New** badges mark stories since your last visit; saved searches notify you about new matches.
- **J / K** move between stories. Settings → **For you** ranks stories near your interests (private).

## Start

Open **Euro Info** from the application menu or run `euro-info`. Opening it again brings the existing
window to the front. The window shows the last downloaded stories at once and refreshes in the background.

## The window

- **Sidebar:** your four views (All stories, Saved for later, Research library, Recently opened), reader
  tools, location focus, sources, and the local AI status at the bottom.
- **Header:** search, saved searches, and buttons for refresh, display options and settings.
- **Strip:** weather for six capitals and the daily ECB reference rates (not live trading quotes).
- **Chips:** All, Europe, Romania, Economy, International, Technology, and Unread only. Region and sort
  order sit on the right; Technology adds a topic selector (Linux, AI, Biotech, Breakthroughs).

Click a card (or press Enter) to read it. On a card, **☆** saves it, **✦** asks the local AI for a brief,
and **⋯** offers notes and tags, read/unread, translation of the full page, opening in your browser, and
copying the link. **Why featured** on the lead story explains its ranking. A report count such as
"4 reports · 2 families" opens the coverage timeline; it is not a count of independent confirmations.

## Search

| Type | Finds |
|---|---|
| `"energy policy"` | the exact phrase |
| `energy -oil` | energy, but not oil |
| `source:"Deutsche Welle"` | one publisher |
| `tag:energy` | your research tag |
| `is:unread` `is:read` `is:saved` `is:noted` | your reading state |

Terms combine with AND, and the operators are the same in every language. **+** saves the current search;
**−** removes the selected one.

## Research library

Add notes and comma-separated tags from **⋯ → Notes and tags** or inside the reader. **Research library**
lists every story with notes or tags, even after it leaves the feeds. **Recently opened** lists the last
500 stories you opened. **File → Export current view** writes Markdown or CSV; **File → Backup reading
list** writes a JSON backup you can import on another computer (existing notes win on conflicts, tags merge).

## Local AI

Euro Info uses [Ollama](https://ollama.com) on your computer. The sidebar button shows its state:

- **Local AI · qwen3.5:9b**: ready. Click for settings and diagnostics.
- **Local AI is off**: click to start it. Euro Info starts your `ollama.service` user service when you
  have one (keeping its GPU settings), otherwise `ollama serve`. With the default setting it stops Ollama
  again when you close Euro Info, but only if Euro Info started it.
- **No AI model installed**: click to download `qwen3.5:9b` (about 6.6 GB) with a progress bar.
- **Ollama not installed**: click to open the download page.

**AI brief** on a card analyses the RSS excerpt plus related coverage from the loaded feeds. Inside the
reader, **AI brief** uses the text of the opened page instead. Each brief separates reported facts,
assessment, a qualified judgment and developments to watch; numbers like [2] open the cited report.
**Investigative connections** shows the evidence map given to the model: leads to check, not proof.
The window shows which model wrote the brief. An identical brief reopens from storage for 48 hours;
**Retry** writes a new one. AI can be wrong; read the cited reporting before relying on it.

**Settings** chooses the model (Automatic picks the best installed one), the analysis profile
(Efficient, Balanced, Deeper), and how long the model stays in GPU memory.

## Languages and translation

Choose the interface language under **View → Language**. AI briefs follow it. The first time you pick a
language other than English, Euro Info asks how to translate headlines:

- **Local AI (private):** translated on your computer, a few headlines at a time.
- **Google (sends headlines online):** fast, but the headline text goes to Google.
- **Keep original:** headlines stay in their original language.

Change this later in **Settings → Headline translation**. **⋯ → Translate full story** opens the publisher
page through Google Translate, only when you click it.

## Display

**View** (the Aa button) switches between Standard, Warm paper and Soft night, compact and roomy layouts,
larger headlines, and article images. Images are off by default to save bandwidth and memory.

## Keyboard

| Keys | Action |
|---|---|
| F5 | Refresh |
| Ctrl+K or / | Search |
| Esc | Clear search |
| Ctrl+1 … Ctrl+4 | All, Saved, Research library, Recently opened |
| Enter | Read the focused story |
| S | Save the focused story |
| Ctrl+, | Settings |
| Ctrl+Shift+E | Export current view |
| Ctrl+ / Ctrl− | Text size in the reader and AI brief |

## Updates

Euro Info checks GitHub once a day and shows a banner when a new version is out (turn this off in
Settings; **Help → Check for updates** checks on demand). To update, install the new download the same
way; your data stays.

## Troubleshooting

**Tools → Diagnostics** lists each source's last result, the local AI state and the installed models, and
can open the log folder. The log is `~/.cache/euro-info/euro-info.log`; Ollama output started by Euro Info
goes to `~/.cache/euro-info/ollama-server.log`. If a source is down, its last stories stay visible for up
to a day.
