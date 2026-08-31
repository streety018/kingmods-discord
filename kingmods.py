import os
import json
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

KINGMODS_URL = "https://www.kingmods.net/en/fs25/new-mods"
BASE_URL = "https://www.kingmods.net"
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]
DATA_FILE = "sent_mods.json"

# Mod mora biti mlađi od 2 dana da bi bio poslat.
MAX_AGE_DAYS = 2


class ModParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.mods = []
        self.current = None
        self.in_link = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            href = attrs.get("href", "")

            if "/fs25/mods/" in href:
                self.current = {
                    "url": urljoin(BASE_URL, href),
                    "name": "",
                    "image": "",
                    "time_text": ""
                }
                self.in_link = True
                return

        if tag == "img" and self.current:
            image = (
                attrs.get("src")
                or attrs.get("data-src")
                or attrs.get("data-lazy-src")
                or ""
            )

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
            text = " ".join(self.current["name"].split())

            # KingMods timestamps
            time_match = re.search(
                r"(just now|"
                r"\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago|"
                r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})$",
                text,
                re.IGNORECASE
            )

            # If there is no timestamp, this is probably a
            # recommended/unrelated old mod somewhere else.
            if time_match:
                self.current["time_text"] = time_match.group(1)

                # Remove timestamp from name
                text = text[:time_match.start()].strip()

                # Remove download/view count at the end.
                text = re.sub(r"\s+\d[\d\s]*$", "", text).strip()

                self.current["name"] = text

                if self.current["name"]:
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


def get_page(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/130 Safari/537.36"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def parse_age(time_text):
    text = time_text.lower().strip()

    if text == "just now":
        return 0

    match = re.match(
        r"(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago",
        text
    )

    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if "minute" in unit:
        return value / 1440

    if "hour" in unit:
        return value / 24

    if "day" in unit:
        return value

    if "week" in unit:
        return value * 7

    if "month" in unit:
        return value * 30

    if "year" in unit:
        return value * 365

    return None


def get_mod_details(mod):
    try:
        html = get_page(mod["url"])

        # ---------------------------------------------------------
        # PUBLISHED BY
        # ---------------------------------------------------------
        publisher = "Unknown"

        publisher_patterns = [
            r'"publisher"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"',
            r'"publishedBy"\s*:\s*"([^"]+)"',
            r'"publisher"\s*:\s*"([^"]+)"',
            r'Published\s+by\s*</[^>]+>\s*<[^>]+>\s*([^<]+)',
            r'Published\s+by\s*:\s*([^<\r\n]+)',
            r'Published\s+by\s+([^<\r\n]+)',
        ]

        for pattern in publisher_patterns:
            match = re.search(
                pattern,
                html,
                re.IGNORECASE
            )

            if match:
                found_publisher = re.sub(
                    r"\s+",
                    " ",
                    match.group(1)
                ).strip()

                if found_publisher:
                    publisher = found_publisher
                    break

        # ---------------------------------------------------------
        # VERSION
        # ---------------------------------------------------------
        version = "Unknown"

        version_match = re.search(
            r'\bV(\d+(?:\.\d+)+)\b',
            html,
            re.IGNORECASE
        )

        if version_match:
            version = "V" + version_match.group(1)

        # ---------------------------------------------------------
        # IMAGE
        # ---------------------------------------------------------
        image = mod.get("image", "")

        if not image:
            image_patterns = [
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image'
            ]

            for pattern in image_patterns:
                match = re.search(
                    pattern,
                    html,
                    re.IGNORECASE
                )

                if match:
                    image = urljoin(
                        BASE_URL,
                        match.group(1)
                    )
                    break

        # ---------------------------------------------------------
        # DETERMINE NEW / UPDATED
        # ---------------------------------------------------------
        is_update = bool(
            re.search(
                r"\bUpdated\b",
                mod["name"],
                re.IGNORECASE
            )
        )

        # Remove "Updated" from actual title.
        clean_name = re.sub(
            r"^\s*Updated\s+",
            "",
            mod["name"],
            flags=re.IGNORECASE
        ).strip()

        return {
            "name": clean_name,
            "url": mod["url"],
            "image": image,
            "author": publisher,
            "version": version,
            "is_update": is_update
        }

    except Exception as e:
        print(f"Details error for {mod['url']}: {e}")

        return {
            "name": mod["name"],
            "url": mod["url"],
            "image": mod.get("image", ""),
            "author": "Unknown",
            "version": "Unknown",
            "is_update": bool(
                re.search(
                    r"\bUpdated\b",
                    mod["name"],
                    re.IGNORECASE
                )
            )
        }


def send_discord(mod):
    if mod["is_update"]:
        title = "🔄 UPDATED MOD"
        color = 15105570
    else:
        title = "🆕 NEW MOD"
        color = 3066993

    description = (
        f"**{mod['name']}**\n\n"
        f"👤 **Published by:** {mod['author']}\n"
        f"🔢 **Version:** {mod['version']}"
    )

    embed = {
        "title": title,
        "description": description,
        "url": mod["url"],
        "color": color,
        "footer": {
            "text": "KingMods • Farming Simulator 25"
        }
    }

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

    html = get_page(KINGMODS_URL)

    parser = ModParser()
    parser.feed(html)

    print(
        f"Found {len(parser.mods)} valid timestamped entries."
    )

    valid_mods = []

    for mod in parser.mods:
        age = parse_age(mod["time_text"])

        if age is None:
            continue

        if age <= MAX_AGE_DAYS:
            valid_mods.append(mod)
        else:
            print(
                f"IGNORED OLD MOD: {mod['name']} "
                f"({mod['time_text']})"
            )

    print(f"Fresh entries: {len(valid_mods)}")

    sent = load_sent()

    # First run:
    # remember currently visible fresh mods without sending them.
    if not sent:
        for mod in valid_mods:
            sent.add(mod["url"])

        save_sent(sent)

        print("Initial database created.")
        return

    new_mods = []

    for mod in reversed(valid_mods):
        if mod["url"] not in sent:
            new_mods.append(mod)

    print(f"New entries: {len(new_mods)}")

    for mod in new_mods:
        print(f"Processing: {mod['name']}")

        details = get_mod_details(mod)

        try:
            send_discord(details)
            sent.add(mod["url"])

            print(
                f"Sent: {details['name']} "
                f"({'UPDATE' if details['is_update'] else 'NEW'})"
            )

        except Exception as e:
            print(f"Discord error: {e}")

    # Keep database from becoming unnecessarily huge.
    if len(sent) > 3000:
        sent = set(list(sent)[-2000:])

    save_sent(sent)

    print("Done.")


if __name__ == "__main__":
    main()
