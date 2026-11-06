# Changelog

All notable changes to Euro Info, newest first.

## 4.0.0

Euro Info now follows all of Europe plus the US politics, economy and technology that matter worldwide, ranks
stories by how important they are, and runs on Windows as well as Linux. Your settings, saved stories, notes
and history carry over.

### All of Europe, plus the US news that matters
- 92 checked sources (was 41): EU institutions and pan-European desks, national desks in 23 European
  countries including Ukraine, Moldova's neighbours, the Baltics and the Balkans, US politics and economy,
  global markets and technology. Romania stays with six sources.
- English feeds and feeds in your interface language are on by default; your earlier choices are kept.
- New region switch (Europe · United States · Global) that follows what a story is about, not only where the
  publisher is based.
- New topics: Politics, Economy, Technology and Security, recognised in eight languages.

### Smarter
- **Briefing**, the new home page: developing stories ranked by importance, each grouping every report about
  the same event with its sources, countries, topic and an importance score you can hover for the reasons.
- **Importance ranking** everywhere: how many independent publishers and countries cover a story, its
  subject, key institutions and people, and freshness. Sport, celebrity, lifestyle and local crime, and US
  stories without wider relevance, rank lower; **Focus** hides them.
- **Latest news** shows one card per developing story, with its other reports one click away.
- **Trending**: subjects whose share of coverage is rising, compared with earlier refreshes; click one to
  filter. A publisher mentioning its own country does not count as a trend.
- **For you** (optional, on this computer only): stories close to what you read, save and annotate rank a
  little higher, and "Why featured" says so.
- **New** badges for stories that arrived since your last visit.
- **Saved-search alerts**: a desktop notification and a count when new stories match a saved search.
- J and K move between stories.

### Local AI
- **Ask the news**: type a question in the search box and press Ask AI (Ctrl+Enter). Euro Info finds the
  most relevant loaded reports and your library (BM25 ranking) and the local model answers with citations.
- **Write AI briefing**: a sectioned briefing (Europe, United States, Economy and markets, Technology, What to
  watch) written from the top developing stories, each point cited.
- Shorter, clearer instructions for the model with the same evidence rules, so small local models follow
  them better and start answering sooner.
- Context sizes suit an 8 GB GPU with a 9B model (Efficient 4K, Balanced 6K, Deeper 12K tokens).
- The model loads while you are still typing a question that ends with "?", so the answer starts sooner.

### Faster
- Story analysis takes 82 ms for 720 stories (one pass over the words instead of hundreds of patterns),
  runs off the interface thread, and is cached, so a refresh only analyses new stories.
- The Briefing page redraws in about 7 ms and reuses its cards; filters switch in about 14 ms.
- Feed validators are kept between sessions: after a restart most feeds answer "not modified".
- Only the sources you selected are downloaded; download workers keep their connections open.
- Weather and rates: the capital of your focus country comes first (Brussels and Washington added).

### Windows
- A Windows installer (per-user, no administrator rights) and a portable zip, built and self-tested
  automatically on Windows.
- Settings and data live in `%APPDATA%\Euro Info` and `%LOCALAPPDATA%\Euro Info`; Euro Info finds and starts
  Ollama for Windows.

### For developers
- New modules: `core/sources.py` (catalogue), `core/intel.py` (topics, regions, entities, importance,
  stories, trends, interest profile), `core/retrieval.py` (search for Ask).
- `euro-info --self-test REPORT` builds the window headless, refreshes once, checks Qt WebEngine and writes
  a JSON report; both release builds run it on the packaged app.
- GitHub Actions builds Linux (Ubuntu 22.04, for compatibility with older distributions) and Windows on
  every release branch and tag, and publishes the release for tags. Tests also run on Windows.
- 163 tests.

## 3.0.0

A rebuild of 2.3.0 for speed, privacy and a cleaner reading experience. Your settings, saved stories,
notes, tags and reading history carry over automatically.

### Faster
- Drawing the page takes 76 ms instead of 290 ms, and 20 ms when cards can be reused; starring a story
  takes under 1 ms instead of rebuilding the page; searching takes 10 ms instead of 213 ms (386 stories,
  measured offline on the same computer).
- Story topics and technology tags are computed once per story instead of on every redraw.
- Built cards are reused when you switch filters, views or pages; saving, marking read and translations
  update only the affected card.
- The embedded browser loads the first time you open a story, not at startup: the window is ready in
  half the time, and the same test uses 194 MB of memory instead of 489 MB.
- Weather for all six cities comes from one request instead of six.
- The release is an unpacked app folder with an installer, so the app no longer unpacks 270 MB to /tmp on
  every launch.

### Cleaner design
- One design system for the Standard, Warm paper and Soft night themes, with a new icon set.
- Calmer story cards: icon actions, rounded thumbnails, no grey placeholder boxes when images are off.
- A tidier header: search, saved searches and display options in one place; filter chips; a status bar.
- The sidebar now holds all four views (All, Saved, Research library, Recently opened) with shortcuts
  Ctrl+1 to Ctrl+4.
- Times ("32m ago") and dates follow the interface language.
- The in-app reader remembers publisher cookie choices between articles.

### Local AI
- The model is detected automatically, including Qwen3.5 (qwen3.5:9b preferred). Coding and app-building
  variants are only used when nothing else is installed.
- Euro Info starts your own `ollama.service` (systemd user service) when it exists, keeping your GPU tuning,
  and can stop it again on exit if it started it.
- A status button in the sidebar shows the model in use and offers a one-click fix: start Ollama, install
  qwen3.5:9b with a progress bar, or open the Ollama download page.
- The analysis window shows which model wrote it; exports include the model name.

### Privacy
- Headline translation is a choice: keep the original language, translate privately with local AI, or use
  Google (sends headlines online). Nothing is sent to Google unless you choose it.
- A once-a-day check for new versions on GitHub, which can be turned off in Settings.

### Fixes
- Markdown export of the current view crashed (code from another function had been pasted into it).
- Story topics were sometimes decided by the publisher's name: "France 24 Europe" contains "euro", so
  unrelated stories were filed under Economy.
- PySide6 was missing from the requirements, so a fresh source setup could not start.
- Duplicate phrasebook and term-table entries were removed.
- The 1.2.0 checksum file listed a wrong path; checksums now use plain file names.
- Bundled font libraries are left out, which removes the flood of fontconfig warnings.
- The Plasma widget runs the installed app (`euro-info --widget-json`) instead of needing a developer
  Python setup.
- Errors that were silently ignored are now written to ~/.cache/euro-info/euro-info.log.

### For developers
- The 4,188-line app.py is now the `euroinfo` package: `core/` (feeds, images, AI, translation,
  research library, updates) and `ui/` (window, cards, dialogs, reader, analysis, background jobs).
- One version number in `euroinfo/__init__.py`; one settings file in ~/.config/euro-info/settings.conf
  (migrated once from ~/.config/EuroInfo/EuroInfo.conf).
- Lint and 128 tests run on every push through GitHub Actions; tests never touch your real data.
- `euro-info --headlines` replaces the old terminal script.

## 2.3.0

This release upgrades the AI article resume from a same-story summarizer to a bounded, local investigative reader. It does not retrain or replace the Ollama model.

#### What changed

- Same-event report retrieval now considers RSS excerpt terms as well as headline overlap, helping include reports with different headlines but shared details.
- Article analysis searches the already loaded feed for a small number of recent reports sharing named actors, institutions and economic, geopolitical or military/security frames.
- Wider-context reports are clearly marked as separate events. Source numbering, source families and reported wire attributions remain visible; these items are never treated as corroboration for the focal event.
- The prompt asks the model to trace concrete connections, state who benefits or bears costs, assess leverage and strategic dependency, examine documented public/private role overlaps as apparent conflicts, give the strongest counterpoint, and distinguish direct evidence from structural inference. It now explicitly separates strategic parallels from causal links, so unrelated events cannot be presented as influencing one another without evidence.
- Conclusions are expected to take a clear position and give separate confidence for reported facts and wider interpretation. Generic lists of missing information should not replace analysis.
- Context and source material remain bounded by the chosen Efficient/Balanced/Deep profile.

#### Evidence limits

Context selection runs locally over articles already loaded by the app; it does not search the whole internet. Entity/frame matches are investigative leads, not proof of coordination or causation. A relative's public role in a commercial discussion can raise an appearance-of-conflict question, but does not prove personal investment, benefit, influence or corruption. The EU-China and Nord Stream reports illustrate a strategic parallel around European economic and security interests, not evidence that the events are connected. Read the cited publisher report for full context, especially when the app only has an RSS excerpt.

#### Validation

The full test suite covers excerpt-based related-report retrieval, cross-story candidate selection, wire-source deduplication, evidence labels, bounded context and analytical prompt requirements. The local 8B model was run on a loaded EU-China trade story with a same-day Reuters report on Jared Kushner and Nord Stream to check whether both direct reporting and structural interpretation appear in the resume.

## 2.2.0

Euro Info now assembles a bounded evidence map alongside the article material sent to the local Ollama model. This release focuses on better synthesis across reports, not a change to the model's neural weights.

#### What changed

- Added an **Investigative connections** view showing publisher-time sequence, repeated headline anchors, publisher-family spread and keyword-based frame signals.
- Added prompts that ask the local model to compare report details, chronology, named actors, attribution and source dependence; consider relevant political, economic, geopolitical, military/security or technical perspectives; and weigh a leading explanation against a plausible alternative.
- Required conclusions to distinguish source-backed facts from inference, calibrate confidence and identify two concrete developments or checks that would change the view. Each citation must support the detail beside it; the model labels single-source claims and cannot treat publication dates as event dates.
- Added science-stage checks for preprints, peer review, replication, lab/animal work, clinical trials and clinical use.
- Reserved context room for the map and bounded the combined source evidence by the selected analysis profile.
- Versioned the analysis cache so older generated reports are not reused with the new prompt.

#### Evidence limits

Shared terms are candidate reading leads, not verified entities, causal links, contradictions or independent confirmation. Publication time is not necessarily event time. Frame labels are keyword signals. Missing coverage describes the loaded sample and says nothing conclusive about unreported events. The local model and article evidence can still be wrong or incomplete; open cited sources for verification.

#### Validation

The full local test suite covers map generation, bounded evidence assembly, profile limits, prompt safeguards, UI integration and the existing news/source features. The app uses the locally installed Ollama model, normally `qwen3:8b`; this release does not download a model or send articles to a hosted AI service.

## 2.1.0

#### Technology with Linux priority

A Technology tab combines specialist feeds with technology stories from the existing desks. Linux gets a priority boost in Recommended ordering and the technology Location focus order, while publisher and event variety keep other important stories visible. Topic filters cover Linux, AI, biotech and breakthroughs. Explicit Newest, Oldest and Publisher sorts remain available.

Added: Phoronix, LWN, OMG! Ubuntu!, Ars Technica, MIT Technology Review, Nature Biotechnology, Nature AI, Science News, Heise, Fedora Magazine and kernel.org release announcements. Project publications and research/commentary are labelled separately from newsrooms. Specialist feeds are enabled once on upgrade; later deselections are respected.

#### Source selection and coverage

Coverage & sources opens a local report of all enabled feeds or the current view, with geography, languages, country keyword mentions, assessment frames, technology topics, missing matches, stale/undated reports, feed errors, cached fallback and source access context. Copy/export are available. Country keywords and publisher base countries are descriptive signals, not a complete event census. The source manager supports specialist selection and shows expertise, publication kind and subscription context.

On 2026-10-08 the live audit found all 41 feeds responding: 397 articles, 100 Romanian-language, 287 English-language and 10 German-language. The sample contained 43 Linux, 27 AI, 15 biotech and 19 breakthrough/science matches; overlapping topics are counted separately. The catalogue remains concentrated in Romanian, English and some German reporting, with many publisher bases in the US/UK. Missing country matches identify investigation priorities, not proof that a country had no relevant events.

#### Evidence and original reporting

Publisher editions are counted as families. Shared agency mentions and identical substantive excerpts are flagged as observable dependence. Agency attribution does not prove the entire report is a syndicated copy; an unflagged report is not certified independent. These dependencies reduce the evidence-diversity ranking benefit. Original author attribution is preserved where supplied by the feed.

Each analysis source is labelled headline only, RSS excerpt or publisher-page extract. Extracted pages can be incomplete; neither RSS nor an extracted page is represented as a verified complete article. AI prompts distinguish first-party announcements, research and independently verified benefits, and distinguish laboratory/animal results, trials and deployment when the supplied sources support those stages. Tech analyses assess the actual technical change before applying relevant political/economic/geopolitical/military frames.

#### Events, freshness and ranking

Event matches are limited to a 72-hour publication window, with an anchor check to reduce transitive topic drift. The coverage timeline includes source excerpts, publisher families, attribution, freshness and update/correction mentions. These are feed signals, not independent verification that every correction has been collected. Tracking parameters are ignored for duplicate detection while case-sensitive article paths are preserved.

Recommended ranking combines freshness, location relevance, public-impact keyword signals, usable excerpts, update signals and observed evidence diversity. It limits repeated publishers/events in the leading results and explains the featured story through Why featured. It is not a reliability rating. Collection gives each responding feed a turn and remains capped at 10 items/feed and 420 total; 12 fetch workers and existing AI/image resource limits remain in place.

#### Validation and limits

Unit and widget regressions cover topic/geographic separation, Linux priority, specialist source migration, shared agencies, duplicate excerpts, publisher families, temporal grouping, source limits, translation and export workflows. Live feeds and local Ollama are checked separately. AI can still misinterpret excerpts and infer unsupported implications; source labels and citations make its basis inspectable. The app does not circumvent subscriptions, certify outlet credibility, retrieve every article on the web, or treat absent coverage as negative evidence.

## 2.0.1

Compact layout is now the default and is remembered between launches. Toggle Compact for the larger layout; Aa+ independently enlarges reading headlines. AI analysis reading size remains independent.

The featured story is part of the scrolling news grid. It uses a smaller image, removes repeated teaser information in compact mode, and retains explicit Read and AI actions. Smaller toolbar buttons, a narrower sidebar, tighter outer margins, and readable 18px story headlines reserve more room for news. Paper and night themes remain available.

At 1540 × 960, the original fixed lead layout provided a 208px news viewport. A prototype with fonts reduced to one-third provided 329px but reduced the lead headline to 10px. The revised layout provides 571px, with a 21px lead headline; the lead card decreases from 254px to 151px. Structural density is preferable to extremely small type. Measurements use the same cached articles and isolated settings.

## 2.0.0

#### What makes this a major release

The app now supports a persistent research workflow, reusable local analysis, and user control of resources, alongside the existing multilingual news dashboard.

##### Research and reading

- Local notes and tags, edited from the story's **⋯** menu, the lead story's **✎** button, or the article reader. Editing notes does not start the web engine.
- Read/unread controls and an unread-only filter; a check beside the publisher identifies opened/read stories.
- **Tools → Recently opened** keeps the last 500 opened stories available after they leave the current feeds. Incidental history is bounded to 5,000 records; research notes are retained.
- A research library for articles with notes or tags, independent of the current source selection.
- Saved searches; phrases, exclusions, publisher/tag filters, and read/saved/note predicates.
- Sorting by location focus, publication date in either direction, or publisher.
- Export the current view as Markdown or CSV, including notes, tags and publisher URLs. CSV fields are protected against spreadsheet formula execution.
- JSON library backup/import. Imports are validated before application and merge with saved items, preserving existing local notes on conflicts.

##### Local AI

- Reopen an identical completed analysis from the local cache without invoking Ollama. Evidence, output language and model/profile settings form the cache key; answers expire after 48 hours, with at most 100 retained.
- Retry explicitly bypasses the cache.
- Choose an installed model and Efficient/Balanced/Deeper analysis profiles. Balanced retains the prior 4,096-token context and 1,000-token output limit. Deeper uses 8,192/1,600; Efficient uses 3,072/850.
- Choose whether to release model memory after analysis or keep it warm for 2, 10 or 30 minutes.
- The publisher reader's **AI brief** action extracts article text already loaded on screen, adds relevant feed coverage, and budgets the excerpts by profile. RSS-only analysis remains available directly from story cards.
- Source provenance is visible. Page extraction can be incomplete; direct feed analyses use headlines/excerpts. AI output is an assessment of supplied evidence, not independent fact verification.
- Copy and export analyses with their source titles and URLs.
- Missing required sections or an unfinished answer at the final output cap are reported as errors and are not cached as successful analyses.

##### Reliability and efficiency

- One GUI instance per login; a second launch activates the existing reader.
- Publisher ETag/Last-Modified validators allow unchanged feeds to reuse parsed articles on HTTP 304.
- A feed outage can reuse that feed's last successful in-session data for up to 24 hours, with errors recorded in diagnostics; complete feed failure remains visibly stale.
- Feed/model diagnostics run off the GUI thread and show source failures, response time, article count, installed models and reported GPU model memory.
- Automatic refresh can be disabled or set to 5/15/30/60 minutes.
- Notes/history use transactional SQLite with WAL and separate short-lived connections. Existing saved-story JSON and existing interface preferences remain compatible.
- Existing bounded thumbnails, dedicated worker pools, coverage-map reuse, batched streaming updates and dialog cleanup are retained.
- Publisher titles are displayed as plain text, and model markup is escaped before rendering. No additional pip dependency was introduced.

#### Verification

- 51 regression tests covering persistence, concurrent writes, cache expiration/invalidation, imports, exports, search, notes without a browser, resource settings, feed validators/outages, AI errors/cancellation/completion and rendering.
- 42 combinations of seven languages, three themes and two dashboard widths.
- Full research workflow: notes/read state/search/watchlist, backup merge, CSV export, diagnostics and reset.
- Real web-engine extraction against a controlled local publisher page.
- Built AppImage and desktop launcher verification, plus real local analysis and cache-reopen checks.

#### Data locations

- Saved items: `~/.local/share/euro-info/saved-stories.json` (existing format).
- Notes, read state, saved searches and analyses: `~/.local/share/euro-info/research.sqlite3`.
- Settings: `~/.config/EuroInfo/EuroInfo.conf`.
- Feed/image snapshot and Ollama launch logs: `~/.cache/euro-info/`.

The release does not claim every possible future optimization is exhausted. Its functionality and resource bounds are explicit and tested.

#### Measured release checks

A fresh local two-source Romanian analysis completed in 17.5 seconds; reopening the identical evidence/language/settings took 4.4 ms and created no model job. Repeated dashboard renders averaged 52.1 ms in an eight-render check, with coverage clustering performed once. These are local measurements, not universal guarantees.

The installed AppImage passed single-instance verification: the second launch exited successfully and left one main window. The desktop launcher and installed SHA256 were validated.

Final visual regression check: masthead type remains stable through all themes and reading-size changes. Reopening the app preserves a maximized window.

## 1.6.0

- Applied 50 reading, navigation, article-reader and AI presentation improvements; see UI-IMPROVEMENTS-1.6.0.md.
- Larger editorial headlines and body text, unclipped story titles, excerpts and responsive controls.
- Redesigned AI reader with formatted sections and bullets, citations, sources, text zoom, copy, retry and generation status.
- Reduced streaming repaint frequency and repeated coverage calculation; cancelled closed analysis streams.
- Added safe rich-text renderer regression tests and retained local-model error handling.
- Released closed modal readers and embedded web pages; began rich-text rendering only after first token arrival.

### All 50 interface improvements

These are implemented changes, not a proposed feature list. Implementation is in `app.py`; translated controls are in `i18n.py`. Newsreader remains the bundled editorial serif.

#### Typography and reading

1. Set a larger application body font and a consistent Qt font baseline.
2. Increase normal story headlines from 16 to 21 pixels.
3. Increase the main lead headline from 23 to 30 pixels.
4. Increase article reader headings from 22 to 28 pixels.
5. Increase AI dialog story headings from 15 to 27 pixels.
6. Enlarge the small source, timestamp, category and weather text.
7. Enlarge section headings from 16 to 21 pixels.
8. Remove fixed maximum heights that cut off story headlines.
9. Remove fixed maximum heights that cut off lead descriptions.
10. Add short article excerpts to normal story cards.
11. End excerpt truncation at word boundaries and show an ellipsis.
12. Increase story card internal margins to 14 pixels.
13. Increase spacing between card content rows from 3 to 8 pixels.
14. Widen the navigation sidebar from 218 to 258 pixels.
15. Increase contrast of sidebar hints and section labels.

#### Navigation and story controls

16. Give display and action controls their own row below the masthead.
17. Reflow that control row into two rows on narrow windows.
18. Give search its own full-width row instead of squeezing it beside filters.
19. Use one article column earlier on narrow windows, and earlier still with enlarged text.
20. Remove the leftover second-column stretch when switching to one column.
21. Add visible focus borders to buttons and selectors.
22. Make story cards focusable with a visible focus border and an accessible title.
23. Open focused story cards with Enter or Space.
24. Replace the passive article hint with an explicit Read button.
25. Move translation and save controls out of the attribution row into the action row.
26. Increase save buttons to 38 × 36 pixels and add an accessible label.
27. Increase translation buttons to 42 × 36 pixels and add an accessible label.
28. Replace the tiny AI icon button with a larger, localized AI brief action.
29. Localize report and publisher counts on coverage buttons.
30. Localize coverage dialog titles and reading instructions.
31. Add a clear button to source search.
32. Show a live selected-source count in the source chooser.
33. Increase source chooser row padding for easier selection.
34. Wrap empty-state instructions so they remain readable in narrow windows.
35. Widen scrollbars from 9 to 13 pixels for easier targeting.

#### Article reader

36. Increase the article reader to a 1000 × 800 default window.
37. Open publisher articles at 115% zoom.
38. Add bounded article zoom controls.
39. Disable Back and Forward when no matching navigation history exists.
40. Show publisher loading progress and remove it when loading finishes.
41. Wrap publisher and publication-time metadata.

#### AI analysis reader

42. Increase the AI reader from 650 × 430 to 940 × 800, with a usable minimum size.
43. Use an 18-pixel analysis body by default, with persistent size controls and keyboard zoom.
44. Render numbered Markdown sections as distinct large headings.
45. Render facts, assessment frames and developments as genuine bullet lists; request this structure from the model while retaining a developed critical judgment.
46. Add an expandable source panel with publisher attribution and clickable numbered evidence.
47. Add Copy analysis, enabled when an answer completes.
48. Add Retry, enabled after success or failure.
49. Show generation state, elapsed time, completion or failure and an indeterminate activity bar.
50. Apply warm-paper and night colors to dialogs, analysis surfaces and source lists, using readable citation colors in the AI reader.

#### Optimization pass

- Batch rich-text streaming updates at most four times per second instead of changing the document for every token.
- Skip unchanged document updates.
- Preserve the reader's scroll position when they scroll away from the bottom during generation.
- Reuse a single cached coverage map while article identities and original headlines are unchanged; refresh automatically invalidates it.
- Suspend story-grid painting while rebuilding and restore it even for empty views or exceptions.
- Cancel a closed analysis at the next received stream event, releasing the response connection; an already blocked network read remains subject to its existing timeout.
- Escape model HTML and link only valid evidence numbers; no Markdown renderer dependency was added.
- Delete closed modal readers and their embedded web pages after use, instead of retaining them under the main window.
- Start the rich-text render timer only after the first token arrives.
- Guide article analyses toward 300–420 words with a developed critical judgment, reducing output-cap continuations without dropping a required section.
- Recognize both parenthesized and Markdown numbered final sections to avoid redundant continuation at the output cap.
- Retain dedicated worker pools, lazy thumbnails, bounded article pages and the existing model/context limits.

#### Verification

The existing regression suite and new renderer tests cover source HTML escaping, evidence validation, sections, real lists and incomplete streamed markup. Release checks also cover real local generation and wide/narrow layouts. Theme and language checks use isolated temporary settings, preserving the user's preferences.

Final verification: 31 regression tests; 42 language/theme/window-width combinations passed. In an eight-render check, coverage was calculated once; first render took 53.2 ms and subsequent renders averaged 48.8 ms. These are local measurements, not a universal speed guarantee. A real installed Romanian analysis completed with all four sections.

The final length-guided local Romanian article analysis completed in 16.9 seconds with all four sections and no error (one source, 240 words). Model timing and output length vary by article, evidence and hardware.

The final installed AppImage also completed a two-source Romanian article analysis in 18.2 seconds, with all four sections and no continuation delay.

## 1.5.1

- Launch Ollama with the system library environment, without AppImage or PyInstaller library overrides.
- Use disk-based compiler temporary storage when the app launches Ollama, respecting any user-specified TMPDIR.
- Retain Ollama startup logs for diagnosing model-loading failures and show the actual server error in article analysis.
- Treat interrupted or failed response streams as failures instead of silently accepting incomplete text.
- Fixed a missing worker attribute that could crash continuation of a truncated article analysis.
- Corrected continuation instructions for daily briefs and article analyses.
- Verified recovery from the /tmp quota exhaustion caused by abandoned Euro Info extraction directories.

## 1.5.0

- Added a per-story AI analysis action to every article card.
- Prevented exact duplicate lead headlines from appearing twice in the first view while retaining all source reports in the coverage timeline.
- Moved the per-story AI action below each headline so it does not crowd publisher and time metadata.
- Search the loaded news feeds for related reports and prefer coverage from distinct publishers.
- Stream local AI output as it is generated and isolate image, refresh, translation and analysis worker pools so image requests cannot delay an AI response.
- Keep the local model available for 10 minutes between reading requests to avoid reloads during a session.
- Ask the local model for a cited assessment using relevant political, economic, geopolitical and security/military frames, a qualified analyst judgment and developments to watch; detect output cutoffs and request only a missing final section.
- Require the AI response to use the selected interface language, including its headings and analysis.
- Strengthened daily briefs with a cited editorial assessment while retaining uncertainty and source independence checks.
- Added Standard, Warm Paper and Soft Night display palettes, saved between launches, plus larger headline text.
- Added the screen-optimized Newsreader typeface for editorial headlines and headings, bundled with its SIL Open Font License.

## 1.4.0

- Added Standard, Warm Paper and Soft Night display palettes, saved between launches.
- Added a Larger Headlines control for the lead and story list.
- Added the screen-optimized Newsreader typeface for editorial headlines and headings, bundled with its SIL Open Font License.
- Updated article reader headings to use the same type system.

## 1.3.1

- Added the screen-optimized Newsreader typeface for story headlines and editorial headings, with its SIL Open Font License included in the package.
- Increased headline size and strengthened the hierarchy between headlines and supporting information.

## 1.3.0

- Group likely related headlines into a transparent story coverage timeline.
- Open each report directly from the timeline to compare publisher coverage.
- Build daily briefs from representative coverage across clustered events.
- Add numbered, clickable evidence citations to local AI summaries and briefs.
- Instruct the local model to distinguish reporting from uncertainty and avoid treating duplicate coverage as independent confirmation.

## 1.2.7

- Show the last saved headlines, weather and rates immediately while fresh data loads.
- Keep the last good news and dashboard values when a refresh is temporarily offline.
- Debounce search rendering so rapid typing no longer rebuilds every story card per keystroke.
- Batch translation-cache writes into one atomic disk update per batch.
- Translate only stories in the current view and continue after an in-flight refresh completes.
- Re-render the feed when the region selector changes.
- Back off failed article images for 15 minutes, invalidate undecodable cached images, and close streamed responses.
- Expire old thumbnails and cap the local image cache at 256 MiB.
- Keep supported Chromium locale packs only in the AppImage and cache appimagetool between builds.

## 1.2.6

- Run local AI summaries in a background worker so model startup does not freeze the interface.
- Start the local Ollama server on demand when it is not already running.
- Prefer the installed Qwen3 8B model, with Qwen 2.5 Coder 7B as a fallback.
- Bound the model context and output length for more predictable memory use and response time.
- Include all 12 selected stories in daily briefs and guard against instructions embedded in article text.

## 1.2.5

- Fixed a runaway headline-translation retry loop that could repeatedly rebuild the UI when a translation was missing.
- Each article/language pair is translated at most once per selection; failed translations leave the original headline visible.
- Added tests that verify failed translations are not requeued.
- Article images are off by default and can be enabled from the reader sidebar.

## 1.2.4

- Decode publisher images in background workers at card thumbnail resolution instead of decoding full-size images on the UI thread.
- Reject exceptionally large source images and reduce image worker concurrency from six to two.
- Limit local AI briefs to six feed excerpts and unload Qwen 2.5 Coder 7B when a request completes.

## 1.2.3

- Added optional country-aware article ordering. Direct location mentions rank highest, local publishers follow, and remaining stories keep their feed order. Location never filters or removes a headline.
- Added privacy-preserving automatic focus from the system locale and manual country selection. No precise location is collected or shared.
- Added sidebar reader tools: local Ollama daily brief, copy visible headlines with publisher links, and reset filters.
- Updated the local AI summary feature to use qwen2.5-coder:7b and request answer-only output.

## 1.2.2

- ===============

- Reworked the front page into a compact editorial dashboard with a formal
-   masthead, restrained paper-and-brass styling and a framed lead story.
- Reclaimed vertical space by combining city weather and reference rates into
-   a responsive information strip.
- Added daily European Central Bank reference rates for EUR against USD, GBP,
-   RON, CHF and PLN through the Frankfurter API. The interface identifies these
-   as daily reference rates, not live trading prices.
- Kept exchange-rate failures independent of news and weather refreshes.

## 1.2.1

- Open original publisher pages in the built-in Chromium reader with in-app back, forward and reload controls.
- Bundle Qt WebEngine and its required Qt modules in the Linux AppImage.
- Keep publisher links within the app and reject non-web URL schemes.
- Expanded to 30 curated live feeds (10 Romanian, 10 European, 10 world).
- Added region filtering, persistent source selection, and balanced feed caps.
- Added French, German, Italian, Romanian, Polish and Spanish interface options.
- Added background, cached headline/excerpt translation and in-app full-story translation.
- Added responsive one/two-column layout and paged story loading.
- Limited image downloads to visible stories and retained workers safely through completion.

## 1.2.0

- Expanded to 30 curated live feeds (10 Romanian, 10 European, 10 world).
- Added region filtering, persistent source selection, and balanced feed caps.
- Added French, German, Italian, Romanian, Polish and Spanish interface options.
- Added background, cached headline/excerpt translation and full-story browser translation.
- Added responsive one/two-column layout and paged story loading.
- Limited image downloads to visible stories and retained workers safely through completion.
