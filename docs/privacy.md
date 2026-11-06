# Privacy

Euro Info has no account, no analytics and no advertising. It connects only to:

| Connection | When | What is sent |
|---|---|---|
| News publishers (RSS feeds, article pages, images) | refresh, reading | ordinary web requests |
| Open-Meteo | refresh | city coordinates |
| Frankfurter (ECB rates) | refresh | nothing personal |
| api.github.com | once a day (can be turned off) | the app version in the user agent |
| Google Translate | only if you choose Google translation | headline and excerpt text |
| Ollama on your computer | AI features | stays on your computer |

The in-app reader keeps publishers' cookies so cookie choices are remembered; clear them by deleting the
`web` folder in your data folder. Your notes, saved stories, reading history and interest profile stay in:

- Linux: `~/.config/euro-info`, `~/.local/share/euro-info`, `~/.cache/euro-info`
- Windows: `%APPDATA%\Euro Info`, `%LOCALAPPDATA%\Euro Info`
