import time
import os
import platform
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

from pathlib import Path
# Configuration
URL = ""
TORONTO_TZ = ZoneInfo("America/Toronto")

FIRST_REFRESH_EARLY_MS = 250
STATE_DETECTION_TIMEOUT_MS = 1000

SESSION_KEEPALIVE_SECONDS = 180
KEEPALIVE_CUTOFF_SECONDS = 15

ACCOUNTS_DIR = Path("accounts")
LOGIN_URL = "https://cityofmarkham.perfectmind.com/"

PREFERRED_PARTICIPANT = ""

# Logging configuration
GOOGLE_CREDENTIALS_FILE = Path(
    "secrets/service_account.json"
)
GOOGLE_SHEET_URL_FILE = Path(
    "secrets/google_sheet_url.txt"
)
GOOGLE_WORKSHEET_NAME = "Runs"

# Friendly label override:
#   set SLOTSYNC_COMPUTER_NAME=Parents-PC
COMPUTER_NAME = (
    os.getenv("SLOTSYNC_COMPUTER_NAME", "").strip()
    or platform.node()
    or "Unknown computer"
)

def now():
    return datetime.now(TORONTO_TZ)

def fmt(dt):
    return dt.strftime("%H:%M:%S.%f")[:-3]

def ms_between(start, end):
    return (end - start).total_seconds() * 1000

def parse_perfectmind_time(value):
    naive = datetime.fromisoformat(value)

    return naive.replace(tzinfo=TORONTO_TZ)


def safe_account_filename(email):
    """
    Turn an email address into a simple local JSON filename.
    The password is never written to this file.
    """
    safe = "".join(
        char if char.isalnum() or char in ("-", "_", ".")
        else "_"
        for char in email.strip().lower()
    ).strip("._")

    if not safe:
        safe = "account"

    return f"{safe}.json"


def looks_logged_out(page):
    """
    Detect the actual PerfectMind sign-in form.

    The page can contain other Email/password-like controls, so only
    the real sign-in username/password fields are considered here.
    """
    try:
        return page.evaluate(
            """
            () => {
                const username =
                    document.querySelector("#textBoxUsername");
                const password =
                    document.querySelector("#textBoxPassword");

                const visible = (el) => {
                    if (!el) {
                        return false;
                    }

                    const style =
                        window.getComputedStyle(el);

                    return (
                        style.display !== "none"
                        && style.visibility !== "hidden"
                        && el.offsetParent !== null
                    );
                };

                return (
                    visible(username)
                    && visible(password)
                );
            }
            """
        )

    except Exception:
        return False


def login_to_perfectmind(
    browser,
    email,
    password,
    auth_file,
):
    """
    Log in through PerfectMind's normal login form and save
    Playwright storage state for later runs.
    """
    context = browser.new_context()
    page = context.new_page()

    print()
    print("Logging into PerfectMind...")

    try:
        page.goto(
            LOGIN_URL,
            wait_until="domcontentloaded",
            timeout=20000,
        )

        # Use the actual PerfectMind sign-in controls directly.
        # The page also contains a separate signup Email field,
        # so get_by_label("Email") is ambiguous.
        email_field = page.locator(
            "#textBoxUsername"
        )

        password_field = page.locator(
            "#textBoxPassword"
        )

        if password_field.count() == 0:
            password_field = page.locator(
                'input[type="password"]:visible'
            ).first

        login_button = page.locator(
            '#buttonLogin, '
            'button:has-text("Login"), '
            'input[type="submit"][value="Login"]'
        ).first

        email_field.wait_for(
            state="visible",
            timeout=10000,
        )
        password_field.wait_for(
            state="visible",
            timeout=10000,
        )
        login_button.wait_for(
            state="visible",
            timeout=10000,
        )

        email_field.fill(email)
        password_field.fill(password)
        login_button.click()

        # Wait specifically for PerfectMind's real sign-in form to
        # disappear. Other signup/profile fields on the page should
        # not keep SlotSync stuck in the login loop.
        try:
            page.wait_for_function(
                """
                () => {
                    const username =
                        document.querySelector("#textBoxUsername");
                    const password =
                        document.querySelector("#textBoxPassword");

                    const visible = (el) => {
                        if (!el) {
                            return false;
                        }

                        const style =
                            window.getComputedStyle(el);

                        return (
                            style.display !== "none"
                            && style.visibility !== "hidden"
                            && el.offsetParent !== null
                        );
                    };

                    return (
                        !visible(username)
                        || !visible(password)
                    );
                }
                """,
                timeout=20000,
                polling=100,
            )
        except PlaywrightTimeoutError:
            print()
            print(
                "ERROR: Login form never disappeared. "
                "Please check the email/password."
            )
            context.close()
            return None, None

        print("Login form cleared.")

        ACCOUNTS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        context.storage_state(
            path=str(auth_file)
        )

        print("Login successful.")
        print(
            "Saved session     :",
            auth_file,
        )

        return context, page

    except Exception as e:
        print()
        print("ERROR: Automatic login failed:")
        print(e)

        try:
            context.close()
        except Exception:
            pass

        return None, None


def open_slotsync_session(browser):
    """
    Ask for an email and booking-page link, reuse a saved
    session when possible, otherwise log in automatically and
    save a fresh session. Then land directly on that booking page.
    """
    print()
    print("================================")
    print("           SlotSync")
    print("================================")
    print()
    print("Computer          :", COMPUTER_NAME)
    print()

    global URL

    global PREFERRED_PARTICIPANT

    PREFERRED_PARTICIPANT = input(
        "Preferred participant "
        "(blank = auto/select later): "
    ).strip()

    email = input("PerfectMind email: ").strip()

    if not email:
        print("ERROR: Email is required.")
        return None, None, None

    URL = input(
        "Booking page link: "
    ).strip()

    if not URL:
        print("ERROR: Booking page link is required.")
        return None, None, None

    if not (
        URL.startswith("https://")
        or URL.startswith("http://")
    ):
        print(
            "ERROR: Booking page link must start with "
            "http:// or https://"
        )
        return None, None, None

    ACCOUNTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    auth_file = (
        ACCOUNTS_DIR
        / safe_account_filename(email)
    )

    if auth_file.exists():
        print()
        print("Saved login found.")
        print("Checking session...")

        try:
            context = browser.new_context(
                storage_state=str(auth_file)
            )
            page = context.new_page()

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=20000,
            )

            if not looks_logged_out(page):
                print("Session still valid.")
                print("Booking page loaded.")

                context.storage_state(
                    path=str(auth_file)
                )

                return context, page, auth_file

            context.close()
            print("Saved session expired.")

        except Exception:
            try:
                context.close()
            except Exception:
                pass

            print(
                "Saved session could not be used."
            )

    password = input(
        "PerfectMind password: "
    )

    context, page = login_to_perfectmind(
        browser,
        email,
        password,
        auth_file,
    )

    password = None

    if context is None:
        return None, None, None

    print("Loading booking page...")

    try:
        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=20000,
        )
    except Exception as e:
        print(
            "ERROR: Could not load booking page:",
            e,
        )
        context.close()
        return None, None, None

    if looks_logged_out(page):
        print(
            "ERROR: PerfectMind returned to the login page."
        )
        context.close()
        return None, None, None

    context.storage_state(
        path=str(auth_file)
    )

    print("Booking page loaded.")

    return context, page, auth_file


def _log_fieldnames():
    return [
        "timestamp",
        "computer",
        "event_url",
        "participant",
        "resident_opening",
        "refresh_lead_ms",
        "refresh_started",
        "response_committed",
        "refresh_to_commit_ms",
        "commit_to_action_ms",
        "open_detected",
        "booking_action_time",
        "booking_action_fired",
        "attendee_next_fired",
        "free_activity_pass_fired",
        "checkout_loaded",
        "result",
    ]



def upload_log_to_google_sheet(row):
    """
    Google Sheets logging.
    Runs only after the time-sensitive booking flow.
    """
    if not GOOGLE_CREDENTIALS_FILE.exists():
        print(
            "Cloud logging skipped: "
            "missing secrets/google_credentials.json"
        )
        return False

    if not GOOGLE_SHEET_URL_FILE.exists():
        print(
            "Cloud logging skipped: "
            "missing secrets/google_sheet_url.txt"
        )
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print(
            "Cloud logging skipped: install with "
            "'py -m pip install gspread google-auth'"
        )
        return False

    try:
        sheet_url = (
            GOOGLE_SHEET_URL_FILE.read_text(
                encoding="utf-8"
            ).strip()
        )

        if not sheet_url:
            print(
                "Cloud logging skipped: "
                "google_sheet_url.txt is empty."
            )
            return False

        credentials = Credentials.from_service_account_file(
            str(GOOGLE_CREDENTIALS_FILE),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )

        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_url(sheet_url)

        try:
            worksheet = spreadsheet.worksheet(
                GOOGLE_WORKSHEET_NAME
            )
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(
                title=GOOGLE_WORKSHEET_NAME,
                rows=1000,
                cols=20,
            )

        fields = _log_fieldnames()

        if not worksheet.row_values(1):
            worksheet.append_row(
                fields,
                value_input_option="RAW",
            )

        worksheet.append_row(
            [row.get(field, "") for field in fields],
            value_input_option="RAW",
        )

        print(
            "Google log saved  :",
            GOOGLE_WORKSHEET_NAME,
        )
        return True

    except Exception as e:
        print("Cloud logging failed:", e)
        return False


def record_run_log(row):
    row["timestamp"] = now().isoformat()
    row["computer"] = COMPUTER_NAME

    upload_log_to_google_sheet(row)


def action_wall_to_local_time(action_record):
    if not action_record:
        return ""

    action_wall = action_record.get("actionWall")

    if action_wall is None:
        return ""

    try:
        return datetime.fromtimestamp(
            action_wall / 1000,
            tz=TORONTO_TZ,
        ).isoformat()
    except Exception:
        return ""

def get_event_info(page):
    try:
        return page.evaluate(
            """
            () => {
                if (
                    typeof window.eventInfo === "undefined"
                    || window.eventInfo === null
                ) {
                    return null;
                }

                return {
                    IsFutureRegistration:
                        window.eventInfo.IsFutureRegistration,

                    IsRegistrationClosed:
                        window.eventInfo.IsRegistrationClosed,

                    AnyRegistrationDateInFuture:
                        window.eventInfo.AnyRegistrationDateInFuture,

                    CanNotBook:
                        window.eventInfo.CanNotBook,

                    ResidentsRegistrationDateValue:
                        window.eventInfo
                            .ResidentsRegistrationDateValue,

                    PublicRegistrationStartDateValue:
                        window.eventInfo
                            .PublicRegistrationStartDateValue
                };
            }
            """
        )

    except Exception:
        return None

def install_fast_booking_hook(page):
    page.add_init_script(
        """
        (() => {

            if (window.top !== window) {
                return;
            }

            if (
                !location.pathname.includes(
                    "/Clients/BookMe4LandingPages/Class"
                )
            ) {
                return;
            }


            const STORAGE_KEY =
                "__slotSyncFastHistory";


  
            function loadHistory() {
                try {
                    const raw =
                        sessionStorage.getItem(
                            STORAGE_KEY
                        );

                    if (!raw) {
                        return [];
                    }

                    const parsed =
                        JSON.parse(raw);

                    return Array.isArray(parsed)
                        ? parsed
                        : [];

                } catch (_) {
                    return [];
                }
            }


            function saveHistory(history) {
                try {
                    sessionStorage.setItem(
                        STORAGE_KEY,
                        JSON.stringify(history)
                    );
                } catch (_) {
                }
            }


            function wallNow() {
                return (
                    performance.timeOrigin
                    + performance.now()
                );
            }


            const record = {
                id:
                    Date.now().toString()
                    + "-"
                    + Math.random()
                        .toString(16)
                        .slice(2),

                url:
                    location.href,

                initWall:
                    wallNow(),

                openSeenWall:
                    null,

                bookingUrlFoundWall:
                    null,

                buttonSeenWall:
                    null,

                actionWall:
                    null,

                actionType:
                    null,

                directUrl:
                    null
            };


            const history =
                loadHistory();


            history.push(record);


            while (history.length > 20) {
                history.shift();
            }


            function save() {
                saveHistory(history);
            }


            save();


            window.__slotSyncFast = {
                openSeen: false,
                directUrl: null,
                buttonSeen: false,
                actionFired: false,
                actionType: null,
                actionWall: null
            };


            function markOpen() {
                if (
                    window.__slotSyncFast.openSeen
                ) {
                    return;
                }

                window.__slotSyncFast.openSeen =
                    true;

                record.openSeenWall =
                    wallNow();

                save();
            }



            function pageIsOpen() {
                try {
                    return (
                        typeof window.eventInfo !==
                            "undefined"
                        &&
                        window.eventInfo !== null
                        &&
                        window.eventInfo.CanNotBook
                            === false
                    );

                } catch (_) {
                    return false;
                }
            }


     

            function findExistingBookingUrl() {

                let anchors;

                try {
                    anchors =
                        document.querySelectorAll(
                            'a[href*="/Clients/BookMe4EventParticipants"]'
                        );

                } catch (_) {
                    return null;
                }


                for (const anchor of anchors) {

                    let rawHref = null;

                    try {
                        rawHref =
                            anchor.getAttribute(
                                "href"
                            );
                    } catch (_) {
                        continue;
                    }


                    if (!rawHref) {
                        continue;
                    }


              
                    if (
                        rawHref.includes("${")
                        ||
                        rawHref.includes("{{")
                        ||
                        rawHref.includes("#=")
                        ||
                        rawHref.includes("#:")
                    ) {
                        continue;
                    }


                    try {
                        const resolved =
                            new URL(
                                rawHref,
                                location.href
                            );


                    
                        if (
                            resolved.origin
                            !== location.origin
                        ) {
                            continue;
                        }


                        if (
                            !resolved.pathname.includes(
                                "/Clients/"
                                + "BookMe4EventParticipants"
                            )
                        ) {
                            continue;
                        }


                        return resolved.href;

                    } catch (_) {
                    }
                }


                return null;
            }


        
            function markAction(
                type,
                directUrl = null
            ) {

                if (
                    window.__slotSyncFast
                        .actionFired
                ) {
                    return false;
                }


                const actionWall =
                    wallNow();


                window.__slotSyncFast.actionFired =
                    true;

                window.__slotSyncFast.actionType =
                    type;

                window.__slotSyncFast.actionWall =
                    actionWall;


                if (directUrl) {
                    window.__slotSyncFast.directUrl =
                        directUrl;
                }


                record.actionWall =
                    actionWall;

                record.actionType =
                    type;

                record.directUrl =
                    directUrl;


                save();

                return true;
            }


    

            function tryDirectBookingUrl() {

                if (
                    !pageIsOpen()
                    ||
                    window.__slotSyncFast
                        .actionFired
                ) {
                    return false;
                }


                markOpen();


                const bookingUrl =
                    findExistingBookingUrl();


                if (!bookingUrl) {
                    return false;
                }


                const foundWall =
                    wallNow();


                record.bookingUrlFoundWall =
                    foundWall;

                window.__slotSyncFast.directUrl =
                    bookingUrl;

                save();


                if (
                    !markAction(
                        "DIRECT_URL",
                        bookingUrl
                    )
                ) {
                    return false;
                }


                window.location.assign(
                    bookingUrl
                );


                return true;
            }




            function clickRegister(button) {

                if (
                    !button
                    ||
                    window.__slotSyncFast
                        .actionFired
                ) {
                    return false;
                }


                if (!pageIsOpen()) {
                    return false;
                }


                markOpen();


                const seenWall =
                    wallNow();


                window.__slotSyncFast.buttonSeen =
                    true;

                record.buttonSeenWall =
                    seenWall;

                save();


                if (
                    !markAction(
                        "DOM_CLICK"
                    )
                ) {
                    return false;
                }


                button.click();


                return true;
            }


      

            function check() {

                if (
                    window.__slotSyncFast
                        .actionFired
                ) {
                    return;
                }


                if (!pageIsOpen()) {
                    return;
                }


                markOpen();



                if (tryDirectBookingUrl()) {
                    return;
                }


   

                let button = null;

                try {
                    button =
                        document.getElementById(
                            "bookButton"
                        );
                } catch (_) {
                }


                if (button) {
                    clickRegister(button);
                }
            }


       
            function attachObserver() {

                if (
                    !document.documentElement
                ) {
                    return false;
                }


                const observer =
                    new MutationObserver(
                        mutations => {

                            if (
                                window.__slotSyncFast
                                    .actionFired
                            ) {
                                return;
                            }


                     
                            check();


                            if (
                                window.__slotSyncFast
                                    .actionFired
                            ) {
                                return;
                            }


                            for (
                                const mutation
                                of mutations
                            ) {

                                for (
                                    const node
                                    of mutation.addedNodes
                                ) {

                                    if (
                                        !node
                                        ||
                                        node.nodeType !== 1
                                    ) {
                                        continue;
                                    }


                                    let button = null;


                                    if (
                                        node.id ===
                                        "bookButton"
                                    ) {
                                        button = node;

                                    } else if (
                                        node.querySelector
                                    ) {

                                        try {
                                            button =
                                                node.querySelector(
                                                    "#bookButton"
                                                );

                                        } catch (_) {
                                        }
                                    }


                                    if (button) {

                                        if (
                                            clickRegister(
                                                button
                                            )
                                        ) {
                                            return;
                                        }
                                    }
                                }
                            }
                        }
                    );


                observer.observe(
                    document.documentElement,
                    {
                        childList: true,
                        subtree: true
                    }
                );


                check();


                return true;
            }



            if (!attachObserver()) {

                const attachTimer =
                    setInterval(
                        () => {

                            if (
                                attachObserver()
                            ) {
                                clearInterval(
                                    attachTimer
                                );
                            }

                        },
                        1
                    );
            }


       

            const stateTimer =
                setInterval(
                    () => {

                        check();


                        if (
                            window.__slotSyncFast
                                .actionFired
                        ) {
                            clearInterval(
                                stateTimer
                            );
                        }

                    },
                    2
                );

        })();
        """
    )

def wait_for_definitive_state(
    page,
    timeout_ms=
        STATE_DETECTION_TIMEOUT_MS
):
    try:

        handle = page.wait_for_function(
            """
            () => {

                const button =
                    document.getElementById(
                        "bookButton"
                    );


                if (button) {
                    return {
                        type: "button"
                    };
                }


                if (
                    typeof window.eventInfo
                        !== "undefined"
                    &&
                    window.eventInfo !== null
                    &&
                    typeof window.eventInfo
                        .CanNotBook
                        !== "undefined"
                ) {

                    return {
                        type: "state",

                        canNotBook:
                            window.eventInfo
                                .CanNotBook,

                        isFutureRegistration:
                            window.eventInfo
                                .IsFutureRegistration,

                        isRegistrationClosed:
                            window.eventInfo
                                .IsRegistrationClosed
                    };
                }


                return false;
            }
            """,

            timeout=
                timeout_ms,

            polling=5
        )


        return handle.json_value()


    except PlaywrightTimeoutError:

        return None


    except Exception:

        return None

def get_fast_action_history(page):
    try:

        return page.evaluate(
            """
            () => {
                try {

                    const raw =
                        sessionStorage.getItem(
                            "__slotSyncFastHistory"
                        );


                    if (!raw) {
                        return [];
                    }


                    const parsed =
                        JSON.parse(raw);


                    return Array.isArray(parsed)
                        ? parsed
                        : [];

                } catch (_) {
                    return [];
                }
            }
            """
        )


    except Exception:

        return []

def find_latest_fast_action(history):

    for record in reversed(
        history
    ):

        if (
            record.get(
                "actionWall"
            ) is not None
        ):
            return record


    return None


def select_participant_and_continue(
    page,
    preferred_name="",
    timeout_ms=15000,
):
    """
    Select one attendee on PerfectMind's participant page,
    wait for the site's own validation/hold logic, then click Next.
    """

    try:
        page.wait_for_url(
            "**/Clients/BookMe4EventParticipants**",
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        print(
            "Attendee page did not appear within "
            f"{timeout_ms} ms."
        )
        return False

    rows = page.locator(
        "#event-attendees .bm-selectable-row"
    )

    try:
        rows.first.wait_for(
            state="attached",
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        print("Could not find the participant list.")
        return False

    members = []

    for i in range(rows.count()):
        row = rows.nth(i)

        name_input = row.locator(
            'input[name$=".FullNameSimple"]'
        )
        checkbox = row.locator(
            'input[type="checkbox"]'
            '[name$=".IsParticipating"]'
        )

        if (
            name_input.count() == 0
            or checkbox.count() == 0
        ):
            continue

        name = (
            name_input.get_attribute("value")
            or ""
        ).strip()

        if not name:
            continue

        members.append(
            {
                "name": name,
                "checkbox": checkbox,
            }
        )

    if not members:
        print("No selectable participants were found.")
        return False

    target = None

    if preferred_name:
        wanted = preferred_name.casefold()

        for member in members:
            if member["name"].casefold() == wanted:
                target = member
                break

        if target is None:
            print()
            print(
                f'Participant "{preferred_name}" '
                "was not found."
            )

    if target is None and len(members) == 1:
        target = members[0]
        print(
            "Participant       :",
            target["name"],
            "(auto-selected)",
        )

    elif target is None:
        print()
        print("Available participants:")

        for index, member in enumerate(
            members,
            start=1,
        ):
            print(
                f"  {index}. {member['name']}"
            )

        while True:
            choice = input(
                "Select participant number: "
            ).strip()

            try:
                selected_index = int(choice) - 1
            except ValueError:
                print("Please enter a number.")
                continue

            if 0 <= selected_index < len(members):
                target = members[selected_index]
                break

            print("That participant number is invalid.")

    else:
        print(
            "Participant       :",
            target["name"],
        )

    # Ensure only the chosen participant is selected.
    for member in members:
        checkbox = member["checkbox"]

        try:
            checked = checkbox.is_checked()
            enabled = checkbox.is_enabled()
        except Exception:
            continue

        if (
            member is not target
            and checked
            and enabled
        ):
            checkbox.click()

    target_checkbox = target["checkbox"]

    try:
        if not target_checkbox.is_checked():
            target_checkbox.click()
    except Exception as e:
        print(
            "Could not select participant:",
            e,
        )
        return False

    print(
        "Selected participant:",
        target["name"],
    )

    # PerfectMind enables Next only after its own validation
    # and hold logic finishes.
    try:
        page.wait_for_function(
            """
            () => {
                const next =
                    document.querySelector(
                        ".bm-form-navbar "
                        + ".next-btn-container a"
                    );

                return (
                    next
                    && !next.classList.contains(
                        "disabled"
                    )
                    && !next.hasAttribute(
                        "disabled"
                    )
                );
            }
            """,
            timeout=timeout_ms,
            polling=10,
        )
    except PlaywrightTimeoutError:
        print(
            "Next did not become available after "
            "participant validation."
        )
        return False

    try:
        page.locator(
            ".bm-form-navbar "
            ".next-btn-container a"
        ).click()
    except Exception as e:
        print("Could not click Next:", e)
        return False

    print("NEXT ACTION FIRED")
    return True


def select_free_activity_pass_and_continue(
    page,
    timeout_ms=15000,
):
    """
    On PerfectMind's Fees/Extras page:
      1. find exactly "REC: Admission - Activity Pass",
      2. verify its amount is $0.00,
      3. select its real radio input,
      4. click the page's Next/Add to Cart button.
    """

    try:
        page.locator("#btnNext").wait_for(
            state="attached",
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        print("Fees/Extras page did not appear.")
        return False

    fee_rows = page.locator(
        ".bm-extras-prices tr.radio-item"
    )

    target_radio = None

    for i in range(fee_rows.count()):
        row = fee_rows.nth(i)

        name_locator = row.locator(
            ".fee-name-item"
        )
        amount_locator = row.locator(
            ".bm-extras-price-amount"
        )
        radio = row.locator(
            'input[type="radio"]'
        )

        if (
            name_locator.count() == 0
            or amount_locator.count() == 0
            or radio.count() == 0
        ):
            continue

        fee_name = (
            name_locator.inner_text()
            or ""
        ).strip()

        raw_amount = (
            amount_locator.get_attribute("value")
            or ""
        ).strip()

        try:
            amount = float(raw_amount)
        except ValueError:
            continue

        if (
            fee_name
            == "REC: Admission - Activity Pass"
            and amount == 0.0
        ):
            target_radio = radio
            break

    if target_radio is None:
        print(
            "ERROR: Free Activity Pass was not found. "
            "SlotSync will not select another fee."
        )
        return False

    try:
        if not target_radio.is_checked():
            target_radio.click()
    except Exception as e:
        print(
            "Could not select free Activity Pass:",
            e,
        )
        return False

    try:
        if not target_radio.is_checked():
            print(
                "ERROR: Free Activity Pass did not remain selected."
            )
            return False
    except Exception:
        return False

    print(
        "Fee selected       : "
        "REC: Admission - Activity Pass (Free)"
    )

    next_button = page.locator("#btnNext")

    try:
        page.wait_for_function(
            """
            () => {
                const button =
                    document.getElementById("btnNext");

                return (
                    button
                    && !button.classList.contains("disabled")
                    && !button.hasAttribute("disabled")
                );
            }
            """,
            timeout=timeout_ms,
            polling=10,
        )
    except PlaywrightTimeoutError:
        print(
            "Fees/Extras Next button did not become available."
        )
        return False

    try:
        next_button.click()
    except Exception as e:
        print(
            "Could not click Fees/Extras Next:",
            e,
        )
        return False

    print("FEES/EXTRAS NEXT FIRED")
    return True


def wait_for_checkout(
    page,
    timeout_ms=20000,
):
    """
    Wait for the checkout page and its embedded online-store frame.

    The final Place My Order action is intentionally left commented
    out for now.
    """

    try:
        page.locator(
            "iframe.online-store"
        ).wait_for(
            state="attached",
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        print(
            "Checkout iframe did not appear within "
            f"{timeout_ms} ms."
        )
        return False

    print("Checkout loaded.")

    
    checkout_frame = page.frame_locator(
        "iframe.online-store"
    )
    
    place_order_button = (
        checkout_frame.get_by_role(
            "button",
            name="Place My Order",
            exact=True,
        )
    )
    
    place_order_button.wait_for(
        state="visible",
        timeout=15000,
    )
    
    place_order_button.click()
    
    print("PLACE MY ORDER FIRED")
    
    

    return True

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    context, page, AUTH_FILE = (
        open_slotsync_session(browser)
    )

    if context is None:
        browser.close()
        raise SystemExit

    event_info = get_event_info(page)
    if not event_info:
        print("ERROR: Could not read PerfectMind eventInfo.")
        browser.close()
        raise SystemExit

    resident_opening = parse_perfectmind_time(
        event_info["ResidentsRegistrationDateValue"]
    )
    target_refresh = resident_opening - timedelta(
        milliseconds=FIRST_REFRESH_EARLY_MS
    )

    # Install the fast hook only AFTER the initial booking page load.
    # This keeps already-open test pages from firing Register during setup.
    install_fast_booking_hook(page)

    print()
    print(
        "Resident opening :",
        resident_opening.strftime("%Y-%m-%d %I:%M:%S.%f %p %Z")[:-7],
    )
    print("First refresh    :", fmt(target_refresh))
    print(f"Refresh lead     : {FIRST_REFRESH_EARLY_MS} ms")

    print()
    print("Waiting for target refresh time...")

    last_display = None

    next_keepalive = (
        now()
        + timedelta(
            seconds=SESSION_KEEPALIVE_SECONDS
        )
    )

    while True:

        current_time = now()
        remaining = (
            target_refresh - current_time
        ).total_seconds()

        if remaining <= 0:
            break

    #
    # Refresh session every 3 minutes while waiting.
    # Use page.goto() instead of reload() because it
    # tends to keep PerfectMind sessions alive more
    # reliably.
    #
        if (
            current_time >= next_keepalive
            and remaining > KEEPALIVE_CUTOFF_SECONDS
        ):
            try:

                print()
                print(
                    f"[{fmt(current_time)}] "
                    "KEEPALIVE NAVIGATION..."
                )

                page.goto(
                    URL,
                    wait_until="domcontentloaded",
                    timeout=15000,
                )

                if "login" in page.url.lower():
                    print(
                        "ERROR: PerfectMind session expired."
                    )
                    print(
                        "Restart SlotSync to sign in again."
                    )
                    browser.close()
                    raise SystemExit

                refreshed_info = get_event_info(page)

                if refreshed_info:
                    resident_opening = (
                        parse_perfectmind_time(
                            refreshed_info[
                                "ResidentsRegistrationDateValue"
                            ]
                        )
                    )

                    target_refresh = (
                        resident_opening
                        - timedelta(
                            milliseconds=
                            FIRST_REFRESH_EARLY_MS
                        )
                    )

                    print(
                        "Updated opening :",
                        resident_opening.strftime(
                            "%Y-%m-%d %I:%M:%S.%f %p %Z"
                        )[:-7],
                    )

                print(
                    f"[{fmt(now())}] "
                    "KEEPALIVE COMPLETE"
                )

            except Exception as e:
                print(
                    f"Keepalive failed: {e}"
                )

            next_keepalive = (
                now()
                + timedelta(
                    seconds=
                    SESSION_KEEPALIVE_SECONDS
                )
            )

            continue

        if remaining > 5:
            display = f"{remaining:5.1f}s"
        elif remaining > 1:
            display = f"{remaining:5.2f}s"
        else:
            display = (
                f"{remaining * 1000:6.0f} ms"
            )

        if display != last_display:
            print(
                f"\rARMING... {display} remaining",
                end="",
                flush=True,
            )
            last_display = display

        if remaining > 1:
            time.sleep(0.25)
        elif remaining > 0.050:
            time.sleep(0.005)
        else:
            time.sleep(0.001)
    print("\r" + " " * 50 + "\r", end="")
    print()
    print("================================")
    print("ARMED")
    print("================================")

    success = False
    committed = None
    detected_open = None
    latest_action_record = None
    attendee_success = False
    fee_success = False
    checkout_success = False

    print()
    print("============== ATTEMPT 1 ==============")

    refresh_started = now()
    print("Refresh started    :", fmt(refresh_started))

    try:
        response = page.reload(
            wait_until="commit",
            timeout=10000,
        )
    except Exception as e:
        print("Refresh error      :", e)
        response = None

    if response is not None:
        committed = now()

        print("Response committed :", fmt(committed))
        print(
            "Refresh -> commit  :",
            f"{ms_between(refresh_started, committed):.2f} ms",
        )

        state = wait_for_definitive_state(page)
        state_time = now()

        if state is None:
            print(
                f"State still unknown after "
                f"{STATE_DETECTION_TIMEOUT_MS} ms."
            )
            print("Keeping the current document and continuing to observe...")

        open_announced = False


        while True:
            try:
                if "BookMe4EventParticipants" in page.url:
                    success = True
                    break
            except Exception:
                pass

            history = get_fast_action_history(page)
            action_record = find_latest_fast_action(history)

            if action_record:
                latest_action_record = action_record
                success = True
                break

            if state is not None:
                if state.get("type") == "button":
                    state = None

                elif (
                    state.get("type") == "state"
                    and state.get("canNotBook") is False
                ):
                    print("State signal       :", fmt(state_time))
                    print("PerfectMind OPEN   :", fmt(state_time))
                    print("Browser fast-path active...")
                    if detected_open is None:
                        detected_open = state_time
                    open_announced = True
                    state = None

                elif (
                    state.get("type") == "state"
                    and state.get("canNotBook") is True
                ):
                    print("State signal       :", fmt(state_time))
                    print("RESULT             : CLOSED RESPONSE")
                    break

                else:
                    state = None

            else:
                current_info = get_event_info(page)

                if current_info is not None:
                    can_not_book = current_info.get("CanNotBook")

                    if can_not_book is False:
                        if not open_announced:
                            detected_open = now()
                            print("PerfectMind OPEN   :", fmt(detected_open))
                            print("Browser fast-path active...")
                            open_announced = True

                    elif can_not_book is True and not open_announced:
                        print("RESULT             : CLOSED RESPONSE")
                        break

            time.sleep(0.005)

    else:
        print(
            "BOOKING ATTEMPT FAILED: "
            "the single timed reload did not complete."
        )

    print()
    print("================================")
    print(
        "BOOKING ACTION FIRED"
        if success
        else "BOOKING ATTEMPT FAILED"
    )
    print("================================")
    print()

    if success:
        attendee_success = (
            select_participant_and_continue(
                page,
                preferred_name=
                    PREFERRED_PARTICIPANT,
            )
        )

        if attendee_success:
            print()
            print("==============================")
            print("ATTENDEE SELECTED + NEXT FIRED")
            print("==============================")
            print()

            fee_success = (
                select_free_activity_pass_and_continue(
                    page
                )
            )

            if fee_success:
                print()
                print("==============================")
                print("FREE ACTIVITY PASS + NEXT FIRED")
                print("==============================")
                print()

                checkout_success = (
                    wait_for_checkout(page)
                )

    # Logging happens only after all time-sensitive booking work.
    refresh_to_commit_ms = ""

    if committed is not None:
        refresh_to_commit_ms = round(
            ms_between(
                refresh_started,
                committed,
            ),
            2,
        )

    if latest_action_record is None:
        try:
            latest_action_record = find_latest_fast_action(
                get_fast_action_history(page)
            )
        except Exception:
            latest_action_record = None

    commit_to_action_ms = ""

    if (
        committed is not None
        and latest_action_record is not None
        and latest_action_record.get("actionWall") is not None
    ):
        try:
            action_dt = datetime.fromtimestamp(
                latest_action_record["actionWall"] / 1000,
                tz=TORONTO_TZ,
            )

            commit_to_action_ms = round(
                ms_between(
                    committed,
                    action_dt,
                ),
                2,
            )
        except Exception:
            commit_to_action_ms = ""

    run_log = {
        "event_url": URL,
        "participant": PREFERRED_PARTICIPANT,
        "resident_opening": resident_opening.isoformat(),
        "refresh_lead_ms": FIRST_REFRESH_EARLY_MS,
        "refresh_started": refresh_started.isoformat(),
        "response_committed": (
            committed.isoformat()
            if committed is not None
            else ""
        ),
        "refresh_to_commit_ms": refresh_to_commit_ms,
        "commit_to_action_ms": commit_to_action_ms,
        "open_detected": (
            detected_open.isoformat()
            if detected_open is not None
            else ""
        ),
        "booking_action_time": action_wall_to_local_time(
            latest_action_record
        ),
        "booking_action_fired": success,
        "attendee_next_fired": attendee_success,
        "free_activity_pass_fired": fee_success,
        "checkout_loaded": checkout_success,
        "result": (
            "CHECKOUT_LOADED"
            if checkout_success
            else "FEE_NEXT_FIRED"
            if fee_success
            else "ATTENDEE_NEXT_FIRED"
            if attendee_success
            else "BOOKING_ACTION_FIRED"
            if success
            else "FAILED"
        ),
    }

    if commit_to_action_ms != "":
        print(
            "Commit -> action   :",
            f"{commit_to_action_ms:.2f} ms",
        )

    print()
    print("Saving run log...")
    record_run_log(run_log)
    print()

    input("Press Enter to close...")
    browser.close()