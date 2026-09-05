from pathlib import Path

from playwright.sync_api import sync_playwright


LOGIN_URL = "https://cityofmarkham.perfectmind.com/"

ACCOUNTS_DIR = Path("accounts")


def get_account_file():
    ACCOUNTS_DIR.mkdir(exist_ok=True)

    while True:
        name = input("Name this account/session: ").strip()

        if not name:
            print("Please enter a name.")
            continue

        if name.lower().endswith(".json"):
            name = name[:-5]

        # Keep filenames simple and safe.
        safe_name = "".join(
            char if char.isalnum() or char in ("-", "_") else "_"
            for char in name
        ).strip("_")

        if not safe_name:
            print("Please enter a valid name.")
            continue

        auth_file = ACCOUNTS_DIR / f"{safe_name}.json"

        if auth_file.exists():
            print(f"{auth_file} already exists.")
            overwrite = input("Overwrite it? (y/N): ").strip().lower()

            if overwrite != "y":
                continue

        return auth_file


def main():
    auth_file = get_account_file()

    print()
    print(f"Session will be saved to: {auth_file}")
    print("A browser will open. Log into PerfectMind normally.")
    print("When you are fully logged in, return here and press Enter.")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        input("Press Enter after you have finished logging in... ")

        context.storage_state(path=str(auth_file))

        print()
        print(f"Saved login session to: {auth_file}")

        browser.close()


if __name__ == "__main__":
    main()