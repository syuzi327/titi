import requests
import os
import sys
import re
from xml.etree import ElementTree as ET

DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
LAST_ID_FILE = "last_tweet_id.txt"
USERNAME = "radio_tochan"

# 複数のNitterインスタンスを順番に試す（落ちてても他で取得できる）
NITTER_INSTANCES = [
    "nitter.net",
    "nitter.poast.org",
    "nitter.privacydev.net",
    "xcancel.com",
]


def fetch_rss():
    for instance in NITTER_INSTANCES:
        try:
            url = f"https://{instance}/{USERNAME}/rss"
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                try:
                    ET.fromstring(r.text)
                except ET.ParseError as e:
                    print(f"{instance} XMLパースエラー: {e}")
                    continue
                print(f"取得成功: {instance}")
                return r.text
            print(f"{instance} ステータス {r.status_code}")
        except Exception as e:
            print(f"{instance} 失敗: {e}")
    return None


def parse_posts(rss_text):
    root = ET.fromstring(rss_text)
    channel = root.find("channel")
    posts = []
    for item in channel.findall("item"):
        link = item.findtext("link", "")
        description = item.findtext("description", "")

        # ポストIDはURLの末尾の数字
        m = re.search(r"/status/(\d+)", link)
        if not m:
            continue
        post_id = m.group(1)

        # descriptionはHTMLなのでbrを改行に変換してからタグを除去
        text = re.sub(r"<br\s*/?>", "\n", description, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text).strip()
        # 連続する改行を1つにまとめる
        text = re.sub(r"\n{2,}", "\n", text)

        canonical_link = f"https://x.com/{USERNAME}/status/{post_id}"
        posts.append({"id": post_id, "text": text, "link": canonical_link})
    return posts


def read_last_id():
    if os.path.exists(LAST_ID_FILE):
        content = open(LAST_ID_FILE).read().strip()
        return content if content else None
    return None


def write_last_id(post_id):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(post_id))


def send_discord(text, link):
    message = {"content": text}
    r = requests.post(DISCORD_WEBHOOK_URL, json=message)
    r.raise_for_status()


def main():
    rss = fetch_rss()
    if not rss:
        print("全Nitterインスタンス失敗")
        sys.exit(1)

    posts = parse_posts(rss)
    if not posts:
        print("ポストが取得できませんでした")
        return

    last_id = read_last_id()
    latest_id = posts[0]["id"]

    # 初回実行時はIDだけ保存して通知しない（過去ポストで通知が溢れるのを防ぐ）
    if last_id is None:
        print(f"初回実行。最新ID {latest_id} を記録して終了")
        write_last_id(latest_id)
        return

    # last_idより新しいポストを収集
    new_posts = []
    for post in posts:
        if post["id"] == last_id:
            break
        new_posts.append(post)

    if not new_posts:
        print("新しいポストなし")
        return

    # 「今週のお題は」または「今週分のメール締切は」を含むものだけ通知
    matched = [p for p in new_posts if "今週のお題は" in p["text"] or "今週分のメール締切は" in p["text"]]

    for post in reversed(matched):  # 古い順に通知
        print(f"お題発見: {post['text'][:60]}...")
        send_discord(post["text"], post["link"])

    write_last_id(latest_id)
    print(f"完了。新規 {len(new_posts)} 件チェック、通知 {len(matched)} 件")


if __name__ == "__main__":
    main()
