# Euro Info Plasma widget

A KDE Plasma 6 widget with the latest stories, topic filters, search and weather. It runs the installed
app (`euro-info --widget-json`), so it needs no Python setup of its own.

`install.sh` from the Euro Info release installs or upgrades the widget. Add it from **Add Widgets…**
(search for "Euro Info"). Try it in a window with:

```sh
plasmawindowed com.alexpetre.euroinfo
```

The bridge (`package/contents/code/bridge.sh`) looks for the app in this order: `EURO_INFO_BIN`,
`euro-info` on PATH, `~/.local/bin/euro-info`, then a source checkout named in
`~/.config/euro-info/widget-source` (for development).
