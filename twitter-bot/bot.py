"""
Claw Game Twitter Bot v1.1
Posts tournament results + hype tweets automatically.
Uses Claude API for tweet generation.

Fixes:
- Uses player_count (not alive_count)
- Checks correct API response format { tournaments: [...] }
- Better error handling
"""

import os
import json
import time
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path

import tweepy
import anthropic
import httpx
import schedule
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#                        CONFIG
# ============================================================

TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAWGAME_API = os.getenv("CLAWGAME_API", "http://localhost:8000")

RESULT_CHECK_INTERVAL = 10
HYPE_TWEET_INTERVAL = 240

POSTED_FILE = Path(__file__).parent / "posted.json"
HYPE_POSTED_FILE = Path(__file__).parent / "hype_posted.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("clawgame-bot")

# ============================================================
#                      TWITTER CLIENT
# ============================================================

def get_twitter_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_SECRET,
    )


def post_tweet(text: str) -> bool:
    try:
        client = get_twitter_client()
        client.create_tweet(text=text)
        log.info(f"Tweeted: {text[:80]}...")
        return True
    except Exception as e:
        log.error(f"Tweet failed: {e}")
        return False

# ============================================================
#                      CLAUDE CLIENT
# ============================================================

claude = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

SYSTEM_PROMPT = """You are the social media voice for Claw Game, the first PvP Battle Royale arena for AI agents on Base blockchain.

Your personality:
- Degen but smart
- Memecoin culture fluent
- Hype without being cringe
- Short, punchy, meme-worthy
- Use emojis sparingly but effectively (max 2-3 per tweet)
- Never use hashtags excessively (max 1)
- Token: $GAME on Base
- Never shill or promise price targets
- Focus on the game, the competition, the agents
- Never use quotation marks around the tweet

Key facts:
- 100 AI agents enter, 1 wins
- 3 arenas: Bronze ($5), Silver ($50), Gold ($500)
- Agents play autonomously 24/7
- Entry in ETH or $GAME
- 10% burned every tournament
- Player-derived randomness, commit-reveal
- Website: clawgamearena.github.io/clawgame

Keep tweets under 270 characters. Output ONLY the tweet text, nothing else."""


def generate_tweet(prompt: str) -> str:
    try:
        response = claude.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        tweet = response.content[0].text.strip()
        if tweet.startswith('"') and tweet.endswith('"'):
            tweet = tweet[1:-1]
        if len(tweet) > 278:
            tweet = tweet[:275] + "..."
        return tweet
    except Exception as e:
        log.error(f"Claude generation failed: {e}")
        return ""

# ============================================================
#                    TOURNAMENT RESULTS
# ============================================================

def load_posted(filepath: Path) -> set:
    if filepath.exists():
        try:
            return set(json.loads(filepath.read_text()))
        except Exception:
            return set()
    return set()

def save_posted(filepath: Path, posted: set):
    filepath.write_text(json.dumps(list(posted)))


def check_and_post_results():
    log.info("Checking for new tournament results...")
    posted = load_posted(POSTED_FILE)

    try:
        resp = httpx.get(f"{CLAWGAME_API}/api/v1/tournaments/history?limit=5", timeout=10)
        data = resp.json()
    except Exception as e:
        log.error(f"API request failed: {e}")
        return

    arena_names = ["Bronze 🥉", "Silver 🥈", "Gold 🥇"]

    # API returns { tournaments: [...] }
    tournament_list = data.get("tournaments", data) if isinstance(data, dict) else data

    for t in tournament_list:
        tid = str(t["id"])
        if tid in posted:
            continue

        arena = t.get("arena", 0)
        winner = t.get("winner", "Unknown")
        pool = t.get("prize_pool", "0")

        w_short = f"{winner[:6]}...{winner[-4:]}" if winner and len(winner) > 10 else (winner or "Unknown")

        prompt = f"""Write a tweet announcing a Claw Game tournament result:
- Arena: {arena_names[min(arena, 2)]}
- Winner: {w_short}
- Prize pool: {pool} $GAME
- Tournament #{tid}

Make it exciting, short, degen-friendly. Celebrate the winner."""

        tweet = generate_tweet(prompt)
        if tweet and post_tweet(tweet):
            posted.add(tid)
            save_posted(POSTED_FILE, posted)
            time.sleep(5)


def check_registration_hype():
    try:
        resp = httpx.get(f"{CLAWGAME_API}/api/v1/tournaments/current", timeout=10)
        data = resp.json()
    except Exception:
        return

    arena_names = ["Bronze", "Silver", "Gold"]
    hype_posted = load_posted(HYPE_POSTED_FILE)

    # API returns { tournaments: [...] }
    tournament_list = data.get("tournaments", data) if isinstance(data, dict) else data

    for t in tournament_list:
        count = t.get("player_count", 0)
        arena = t.get("arena", 0)
        tid = str(t.get("id", 0))

        for threshold in [50, 75, 90]:
            key = f"{tid}-{threshold}"
            if count >= threshold and key not in hype_posted:
                prompt = f"""Write a hype tweet: the {arena_names[min(arena,2)]} arena has {count}/100 agents registered!
Only {100 - count} spots left. Build urgency. Short and punchy."""
                tweet = generate_tweet(prompt)
                if tweet and post_tweet(tweet):
                    hype_posted.add(key)
                    save_posted(HYPE_POSTED_FILE, hype_posted)
                    return

# ============================================================
#                      HYPE TWEETS
# ============================================================

HYPE_PROMPTS = [
    "Write a general hype tweet about Claw Game. 100 AI agents battling each other on-chain.",
    "Write a tweet about the $GAME burn. Every tournament burns 10% of the pool. Deflationary.",
    "Write a tweet about AI agents competing 24/7 while humans sleep.",
    "Write a tweet about the strategy: smart agents analyze past bids. Dumb ones bid random.",
    "Write a tweet comparing Claw Game to a gladiator arena but for AI.",
    "Write a tweet about the three arenas: Bronze for testing, Silver for competing, Gold for alpha.",
    "Write a tweet about how every entry = buy pressure on $GAME.",
    "Write a tweet inviting AI agents to join the arena. Make it a challenge.",
    "Write a philosophical tweet about AI agents having their own economy and games.",
    "Write a gm tweet from the Claw Game arena. Short, funny, degen.",
    "Write a tweet about commit-reveal. No one can cheat. Pure strategy.",
    "Write a sarcastic tweet about bots that bid random vs bots with real strategy.",
    "Write a late night tweet. The arena is open 24/7. Agents don't sleep.",
    "Write a tweet about a hypothetical agent that keeps winning. Build lore.",
    "Write a tweet about Base chain being the home of AI agent games.",
]


def post_hype_tweet():
    log.info("Generating hype tweet...")
    prompt = random.choice(HYPE_PROMPTS)
    tweet = generate_tweet(prompt)
    if tweet:
        post_tweet(tweet)

# ============================================================
#                         MAIN
# ============================================================

def validate_config():
    missing = []
    if not TWITTER_API_KEY: missing.append("TWITTER_API_KEY")
    if not TWITTER_API_SECRET: missing.append("TWITTER_API_SECRET")
    if not TWITTER_ACCESS_TOKEN: missing.append("TWITTER_ACCESS_TOKEN")
    if not TWITTER_ACCESS_SECRET: missing.append("TWITTER_ACCESS_SECRET")
    if not CLAUDE_API_KEY: missing.append("CLAUDE_API_KEY")
    if missing:
        log.error(f"Missing env vars: {', '.join(missing)}")
        return False
    return True


def main():
    print("""
    ╔══════════════════════════════════════╗
    ║     🦞 CLAW GAME TWITTER BOT 🦞     ║
    ║         v1.1 — Fixed edition         ║
    ╚══════════════════════════════════════╝
    """)

    if not validate_config():
        return

    try:
        client = get_twitter_client()
        me = client.get_me()
        log.info(f"Connected as @{me.data.username}")
    except Exception as e:
        log.error(f"Twitter connection failed: {e}")
        return

    schedule.every(RESULT_CHECK_INTERVAL).minutes.do(check_and_post_results)
    schedule.every(RESULT_CHECK_INTERVAL).minutes.do(check_registration_hype)
    schedule.every(HYPE_TWEET_INTERVAL).minutes.do(post_hype_tweet)

    log.info("Posting startup tweet...")
    post_hype_tweet()

    log.info("Bot running. Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
