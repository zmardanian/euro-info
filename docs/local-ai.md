# Local AI

Euro Info's AI features run on your own computer through [Ollama](https://ollama.com). No article text or
question is sent to an online AI service.

## Setup
1. Install Ollama (Windows installer, or the Linux script from ollama.com).
2. Start Euro Info. The AI button at the bottom of the sidebar shows the state and fixes problems in one click:
   start Ollama, install the recommended model `qwen3.5:9b` (about 6.6 GB), or open the download page.

On Linux, Euro Info starts your `ollama.service` user service when you have one (keeping its GPU settings),
otherwise `ollama serve`, and by default stops it when you close the app if Euro Info started it.

## Models
**Automatic** picks the best installed general chat model: official Qwen3.5 first, then Qwen3, Qwen2.5, Gemma 3,
Llama 3 and Mistral. Variants with their own system prompts (for coding or app building) are used only when
nothing else is installed. Choose a model yourself in **Settings → Local AI model**. "Thinking" mode is off: it is
too slow for reading.

| Profile | Context | Answer length | Use |
|---|---|---|---|
| Efficient | 4K tokens | ~1,000 | older or smaller GPUs |
| Balanced (default) | 6K | ~1,400 | 8 GB GPUs with a 9B model |
| Deeper | 12K | ~2,000 | more sources, slower |

## Features
- **AI brief** on a story: facts, connections and perspectives, a qualified judgment, and what would change it.
- **Ask AI**: a question answered from the most relevant loaded reports and your library, with citations.
- **Write AI briefing**: Europe, United States, Economy and markets, Technology and What to watch, each cited.
- **Translation** (optional): headlines translated privately by the local model.

Numbers like **[2]** open the cited report. Identical analyses reopen from storage for 48 hours. The model
loads while you type a question ending in "?", so answers start sooner.

## Speed
Measured with qwen3.5:9b on an 8 GB AMD GPU: an Ask answer took about 21 s from a cold start (13 s to the first
words, mostly model loading); a 12-story briefing took 16 s with the model already loaded.

## Limits
Analyses use RSS excerpts unless you open the article and press AI brief in the reader. AI can be wrong: read
the cited reporting before relying on a conclusion.
