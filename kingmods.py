import os
import json
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

KINGMODS_URL = "https://www.kingmods.net/en/fs25/new-mods"
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]
DATA_FILE = "sent_mods.json"
BASE_URL = "https://www.kingmods.net"


class ModParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.mods = []
        self.current = None
        self.in_link = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        # Start of a mod link
        if tag == "a":
            href = attrs.get("href", "")

            if "/fs25/mods/" in href:
                self.current = {
                    "url": urljoin(BASE_URL, href),
                    "name": "",
                    "image": ""
                }
                self.in_link = True
                return

        # Image inside the mod link
        if tag == "img" and self.current:
            image = (
                attrs.get("src")
                or attrs.get("data-src")
                or attrs.get("data-lazy-src")
                or ""
            )

            # Some sites use srcset instead
            if not image:
                srcset = attrs.get("srcset", "")
                if srcset:
                    image = srcset.split(",")[0].strip().split(" ")[0]

            if image:
                self.current["image"] = urljoin(BASE_URL, image)

    def handle_data(self, data):
        if self.current and self.in_link:
            text = " ".join(data.split())

            if text:
                self.current["name"] += " " + text

    def handle_endtag(self, tag):
        if tag == "a" and self.current:
            name = " ".join(self.current["name"].split())

            if name:
                self.current["name"] = name

                if self.current not in self.mods:
                    self.mods.append(self.current)

            self.current = None
            self.in_link = False


def load_sent():
    if not os.path.exists(DATA_FILE):
        return set()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_sent(sent):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent), f, ensure_ascii=False, indent=2)


def get_page():
    request = urllib.request.Request(
        KINGMODS_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def send_discord(mod):
    embed = {
        "title": "🆕 New FS25 Mod",
        "description": f"**{mod['name']}**",
        "url": mod["url"],
        "color": 3066993,
        "footer": {
            "text": "KingMods • Farming Simulator 25"
        }
    }

    # Add mod image if found
    if mod.get("image"):
        embed["image"] = {
            "url": mod["image"]
        }

    payload = {
        "username": "KingMods",
        "embeds": [embed]
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        DISCORD_WEBHOOK,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "KingMods Discord Bot"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def main():
    print("Checking KingMods...")

    html = get_page()

    parser = ModParser()
    parser.feed(html)

    mods = parser.mods[:120]

    print(f"Found {len(mods)} mods.")

    for mod in mods:
        print(
            f"MOD: {mod['name']} | "
            f"IMAGE: {mod['image'] or 'NONE'}"
        )

    sent = load_sent()

    # First run: remember existing mods without sending them
    if not sent:
        for mod in mods:
            sent.add(mod["url"])

        save_sent(sent)
        print("Initial database created.")
        return

    new_mods = []

    for mod in reversed(mods):
        if mod["url"] not in sent:
            new_mods.append(mod)

    print(f"New mods: {len(new_mods)}")

    for mod in new_mods:
        try:
            send_discord(mod)
            sent.add(mod["url"])
            print(f"Sent: {mod['name']}")
        except Exception as e:
            print(f"Discord error: {e}")

    if len(sent) > 2000:
        sent = set(list(sent)[-1500:])

    save_sent(sent)


if __name__ == "__main__":
    main()
