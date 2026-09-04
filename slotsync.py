import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

from pathlib import Path
# Configuration
URL = "https://cityofmarkham.perfectmind.com/Clients/BookMe4LandingPages/Class?widgetId=6825ea71-e5b7-4c2a-948f-9195507ad90a&redirectedFromEmbededMode=False&classId=3892f0ea-9243-4a60-b1b9-174f63460ae4&occurrenceDate=20260905"
TORONTO_TZ = ZoneInfo("America/Toronto")

FIRST_REFRESH_EARLY_MS = 350
STATE_DETECTION_TIMEOUT_MS = 1000


ACCOUNTS_DIR = Path("accounts")

account_name = input("Enter account JSON name: ").strip()

if not account_name.endswith(".json"):
    account_name += ".json"

AUTH_FILE = ACCOUNTS_DIR / account_name

def now():
    return datetime.now(TORONTO_TZ)

def fmt(dt):
    return dt.strftime("%H:%M:%S.%f")[:-3]

def ms_between(start, end):
    return (end - start).total_seconds() * 1000

def parse_perfectmind_time(value):
    naive = datetime.fromisoformat(value)

    return naive.replace(tzinfo=TORONTO_TZ)

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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(storage_state=AUTH_FILE)
    page = context.new_page()


    install_fast_booking_hook(page)

    print("Loading booking page...")
    page.goto(URL, wait_until="domcontentloaded")

    if "login" in page.url.lower():
        print("ERROR: PerfectMind session expired.")
        print("Run login.py again.")
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

    while True:
        remaining = (target_refresh - now()).total_seconds()

        if remaining <= 0:
            break

        if remaining > 5:
            display = f"{remaining:5.1f}s"
        elif remaining > 1:
            display = f"{remaining:5.2f}s"
        else:
            display = f"{remaining * 1000:6.0f} ms"

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
    print("BOOKING ACTION FIRED" if success else "BOOKING ATTEMPT FAILED")
    print("================================")
    print()

    input("Press Enter to close...")
    browser.close()
