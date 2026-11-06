"""Terminal output: `euro-info --headlines` prints weather, rates and the latest stories."""
from __future__ import annotations

from datetime import datetime

from . import feeds


def main(limit: int = 25) -> int:
    weather = feeds.get_weather()
    news = feeds.get_news()
    print("EURO INFO", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"))
    print()
    for city, data in weather.items():
        if "error" in data:
            print(f"  {city:<10} unavailable")
        else:
            print(f"  {city:<10} {data['temperature']:>5.1f}°C  {data['description']}")
    rates = feeds.get_exchange_rates().get("rates", {})
    if rates:
        print("  EUR       ", "  ".join(f"{code} {value:.3f}" for code, value in rates.items()))
    print()
    for index, article in enumerate(news[:limit], 1):
        print(f"{index:>2}. {article['title']}")
        print(f"    {article['source']} · {article.get('time', '')}")
        print(f"    {article['link']}")
    print(f"\n{len(news)} stories from {len(feeds.NEWS_SOURCES)} sources.")
    return 0
