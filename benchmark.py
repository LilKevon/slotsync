import statistics
import time

from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright



BOOKING_URL = "https://cityofmarkham.perfectmind.com/Clients/BookMe4LandingPages/Class?widgetId=6825ea71-e5b7-4c2a-948f-9195507ad90a&redirectedFromEmbededMode=False&classId=2d49360b-b07a-432d-a966-321f565d919a&occurrenceDate=20260902"

# Choose whichever account you want benchmark.py to use.
AUTH_FILE = "accounts/dad_account.json"

TORONTO_TZ = ZoneInfo("America/Toronto")

# Keep this modest on the real site.
SAMPLE_COUNT = 5

# Time between diagnostic refreshes.
SECONDS_BETWEEN_SAMPLES = 2


OBSERVATION_WINDOW_MS = 2000


PYTHON_OBSERVER_POLL_MS = 20




def local_now():
    return datetime.now(TORONTO_TZ)


def fmt_time(dt):
    return dt.strftime("%H:%M:%S.%f")[:-3]


def ms_between(start, end):
    return (end - start).total_seconds() * 1000


def format_epoch_ms(timestamp_ms):
    if timestamp_ms is None:
        return "N/A"

    try:
        dt = datetime.fromtimestamp(
            timestamp_ms / 1000,
            tz=TORONTO_TZ,
        )

        return fmt_time(dt)

    except Exception:
        return "N/A"


def percentile(values, p):
    if not values:
        return None

    values = sorted(values)

    if len(values) == 1:
        return values[0]

    position = (
        len(values) - 1
    ) * (p / 100)

    lower = int(position)

    upper = min(
        lower + 1,
        len(values) - 1,
    )

    fraction = position - lower

    return (
        values[lower]
        + (
            values[upper]
            - values[lower]
        ) * fraction
    )




def parse_server_date(value):
    if not value:
        return None

    try:
        return parsedate_to_datetime(value)

    except Exception:
        return None




def get_event_info(page):
    try:
        return page.evaluate("""
            () => {
                if (
                    typeof window.eventInfo === "undefined" ||
                    window.eventInfo === null
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
                        window.eventInfo.ResidentsRegistrationDateValue,

                    PublicRegistrationStartDateValue:
                        window.eventInfo.PublicRegistrationStartDateValue
                };
            }
        """)

    except Exception:
        return None


def wait_for_event_info(
    page,
    timeout_ms=1000,
):
    deadline = (
        time.perf_counter()
        + timeout_ms / 1000
    )

    while time.perf_counter() < deadline:

        event_info = get_event_info(page)

        if event_info is not None:
            return event_info

        time.sleep(0.01)

    return None




def install_timing_observer(page):

    page.add_init_script("""
        (() => {

            if (window.top !== window) {
                return;
            }

            const STORAGE_KEY =
                "__slotSyncBenchmarkHistory";


            function readHistory() {
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


            function stamp() {
                const perf =
                    performance.now();

                return {
                    perf: perf,
                    wall:
                        performance.timeOrigin
                        + perf
                };
            }


            const initStamp =
                stamp();


            const record = {

                id:
                    Date.now().toString()
                    + "-"
                    + Math.random()
                        .toString(16)
                        .slice(2),

                url:
                    location.href,

                timeOrigin:
                    performance.timeOrigin,

                initPerf:
                    initStamp.perf,

                initWall:
                    initStamp.wall,


                domContentLoadedPerf:
                    null,

                domContentLoadedWall:
                    null,


                loadPerf:
                    null,

                loadWall:
                    null,


                eventInfoAvailablePerf:
                    null,

                eventInfoAvailableWall:
                    null,


                eventInfoOpenPerf:
                    null,

                eventInfoOpenWall:
                    null,


                buttonInsertedPerf:
                    null,

                buttonInsertedWall:
                    null
            };


            const history =
                readHistory();


            history.push(record);


            // Prevent sessionStorage from growing forever.
            while (history.length > 20) {
                history.shift();
            }


            function save() {
                try {
                    sessionStorage.setItem(
                        STORAGE_KEY,
                        JSON.stringify(history)
                    );

                } catch (_) {
                }
            }


            function mark(name) {

                if (
                    record[name + "Perf"]
                    !== null
                ) {
                    return;
                }

                const value =
                    stamp();

                record[name + "Perf"] =
                    value.perf;

                record[name + "Wall"] =
                    value.wall;

                save();
            }


            // --------------------------------------------
            // eventInfo
            // --------------------------------------------

            function checkEventInfo() {

                try {

                    if (
                        typeof window.eventInfo
                            === "undefined"
                        ||
                        window.eventInfo === null
                    ) {
                        return;
                    }


                    if (
                        record
                            .eventInfoAvailablePerf
                        === null
                    ) {
                        mark(
                            "eventInfoAvailable"
                        );
                    }


                    if (
                        window.eventInfo
                            .CanNotBook
                        === false
                        &&
                        record.eventInfoOpenPerf
                        === null
                    ) {
                        mark(
                            "eventInfoOpen"
                        );
                    }

                } catch (_) {
                }
            }


            // --------------------------------------------
            // Register button
            // --------------------------------------------

            function checkExistingButton() {

                if (
                    record.buttonInsertedPerf
                    !== null
                ) {
                    return;
                }

                try {

                    if (
                        document.getElementById(
                            "bookButton"
                        )
                    ) {
                        mark(
                            "buttonInserted"
                        );
                    }

                } catch (_) {
                }
            }


            function addedNodeContainsButton(
                node
            ) {

                if (
                    !node
                    ||
                    node.nodeType
                        !== Node.ELEMENT_NODE
                ) {
                    return false;
                }


                if (
                    node.id === "bookButton"
                ) {
                    return true;
                }


                try {

                    return (
                        node.querySelector
                        &&
                        node.querySelector(
                            "#bookButton"
                        ) !== null
                    );

                } catch (_) {
                    return false;
                }
            }


            function attachMutationObserver() {

                if (
                    !document.documentElement
                ) {
                    return false;
                }


                const observer =
                    new MutationObserver(
                        mutations => {

                            if (
                                record
                                    .buttonInsertedPerf
                                !== null
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
                                        addedNodeContainsButton(
                                            node
                                        )
                                    ) {

                                        mark(
                                            "buttonInserted"
                                        );

                                        return;
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


                checkExistingButton();

                return true;
            }


            // --------------------------------------------
            // DOMContentLoaded
            // --------------------------------------------

            document.addEventListener(
                "DOMContentLoaded",
                () => {

                    mark(
                        "domContentLoaded"
                    );

                    checkEventInfo();

                    checkExistingButton();
                },
                {
                    once: true
                }
            );


            // --------------------------------------------
            // Full window load
            // --------------------------------------------

            window.addEventListener(
                "load",
                () => {

                    mark(
                        "load"
                    );

                    checkEventInfo();

                    checkExistingButton();
                },
                {
                    once: true
                }
            );


            // --------------------------------------------
            // MutationObserver
            // --------------------------------------------

            let mutationAttached =
                attachMutationObserver();


            if (!mutationAttached) {

                const attachTimer =
                    setInterval(
                        () => {

                            mutationAttached =
                                attachMutationObserver();

                            if (
                                mutationAttached
                            ) {
                                clearInterval(
                                    attachTimer
                                );
                            }

                        },
                        1
                    );
            }


            // --------------------------------------------
            // eventInfo polling
            //
            // Assignment to window.eventInfo does not
            // necessarily generate a DOM mutation.
            // --------------------------------------------

            const eventTimer =
                setInterval(
                    () => {

                        checkEventInfo();

                        checkExistingButton();


                        // Stop after five seconds.
                        if (
                            performance.now()
                            - record.initPerf
                            > 5000
                        ) {
                            clearInterval(
                                eventTimer
                            );
                        }

                    },
                    5
                );


            save();

        })();
    """)




def get_current_browser_record(page):

    try:

        return page.evaluate("""
            () => {

                try {

                    const raw =
                        sessionStorage.getItem(
                            "__slotSyncBenchmarkHistory"
                        );

                    if (!raw) {
                        return null;
                    }


                    const history =
                        JSON.parse(raw);


                    if (
                        !Array.isArray(history)
                        ||
                        history.length === 0
                    ) {
                        return null;
                    }


                    const currentOrigin =
                        performance.timeOrigin;


                    // Find the record created for the
                    // currently loaded document.
                    for (
                        let i =
                            history.length - 1;
                        i >= 0;
                        i--
                    ) {

                        const record =
                            history[i];


                        if (
                            Math.abs(
                                record.timeOrigin
                                - currentOrigin
                            ) < 2
                        ) {
                            return record;
                        }
                    }


                    return history[
                        history.length - 1
                    ];

                } catch (_) {
                    return null;
                }
            }
        """)

    except Exception:
        return None




def get_navigation_timing(page):

    try:

        return page.evaluate("""
            () => {

                const entries =
                    performance.getEntriesByType(
                        "navigation"
                    );

                if (
                    !entries
                    ||
                    entries.length === 0
                ) {
                    return null;
                }


                const n = entries[0];


                return {

                    startTime:
                        n.startTime,

                    fetchStart:
                        n.fetchStart,

                    requestStart:
                        n.requestStart,

                    responseStart:
                        n.responseStart,

                    responseEnd:
                        n.responseEnd,

                    domInteractive:
                        n.domInteractive,

                    domContentLoaded:
                        n.domContentLoadedEventEnd,

                    loadEventEnd:
                        n.loadEventEnd,

                    transferSize:
                        n.transferSize,

                    encodedBodySize:
                        n.encodedBodySize,

                    decodedBodySize:
                        n.decodedBodySize
                };
            }
        """)

    except Exception:
        return None




def collect_browser_diagnostics(page):

    deadline = (
        time.perf_counter()
        + OBSERVATION_WINDOW_MS / 1000
    )


    best_record = None


    while time.perf_counter() < deadline:

        record = (
            get_current_browser_record(
                page
            )
        )


        if record:

            best_record = record


            event_ready = (
                record.get(
                    "eventInfoAvailablePerf"
                )
                is not None
            )


            dom_ready = (
                record.get(
                    "domContentLoadedPerf"
                )
                is not None
            )


            button_ready = (
                record.get(
                    "buttonInsertedPerf"
                )
                is not None
            )


       
            if (
                event_ready
                and dom_ready
            ):

              
                if (
                    record.get(
                        "eventInfoOpenPerf"
                    )
                    is None
                ):
                    break

                if button_ready:
                    break


        time.sleep(
            PYTHON_OBSERVER_POLL_MS
            / 1000
        )


    navigation = (
        get_navigation_timing(
            page
        )
    )


    return (
        best_record,
        navigation,
    )



def relative_ms(
    record,
    field,
):
    if not record:
        return None

    value = record.get(field)

    init = record.get(
        "initPerf"
    )

    if (
        value is None
        or init is None
    ):
        return None

    return value - init


def print_relative(
    label,
    record,
    field,
):
    value = relative_ms(
        record,
        field,
    )

    if value is None:
        print(
            f"{label:<24}: N/A"
        )

    else:
        print(
            f"{label:<24}: "
            f"{value:.2f} ms"
        )




with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False
    )


    context = browser.new_context(
        storage_state=AUTH_FILE
    )


    page = context.new_page()


  
    install_timing_observer(page)


    print()
    print(
        "=========================================="
    )
    print(
        "BENCHMARK / DIAGNOSTIC MODE"
    )
    print(
        "=========================================="
    )
    print(
        "This script does NOT click Register."
    )
    print()




    print(
        "Loading booking page..."
    )


    initial_start = (
        local_now()
    )

    initial_perf = (
        time.perf_counter()
    )


    page.goto(
        BOOKING_URL,
        wait_until="domcontentloaded"
    )


    initial_end = (
        local_now()
    )


    initial_ms = (
        time.perf_counter()
        - initial_perf
    ) * 1000


    print()

    print(
        "Initial load started :",
        fmt_time(
            initial_start
        ),
    )

    print(
        "Initial DOM ready    :",
        fmt_time(
            initial_end
        ),
    )

    print(
        "Initial load time    :",
        f"{initial_ms:.2f} ms",
    )



    print()
    print(
        "=== AUTH CHECK ==="
    )


    if "login" in page.url.lower():

        print(
            "FAIL: Page redirected to login."
        )

        print(
            "Run login.py again."
        )

        browser.close()

        raise SystemExit


    print(
        "PASS: Session appears authenticated."
    )


  

    print()
    print(
        "=== PERFECTMIND STATE ==="
    )


    event_info = (
        wait_for_event_info(
            page,
            timeout_ms=1000,
        )
    )


    resident_opening = None


    if event_info is None:

        print(
            "Could not read window.eventInfo."
        )

    else:

        print(
            "IsFutureRegistration       :",
            event_info.get(
                "IsFutureRegistration"
            ),
        )

        print(
            "IsRegistrationClosed       :",
            event_info.get(
                "IsRegistrationClosed"
            ),
        )

        print(
            "AnyRegistrationDateInFuture:",
            event_info.get(
                "AnyRegistrationDateInFuture"
            ),
        )

        print(
            "CanNotBook                 :",
            event_info.get(
                "CanNotBook"
            ),
        )


        resident_value = (
            event_info.get(
                "ResidentsRegistrationDateValue"
            )
        )


        public_value = (
            event_info.get(
                "PublicRegistrationStartDateValue"
            )
        )


        print(
            "Resident opening           :",
            resident_value,
        )

        print(
            "Public opening             :",
            public_value,
        )


        if resident_value:

            try:

                resident_opening = (
                    datetime.fromisoformat(
                        resident_value
                    ).replace(
                        tzinfo=TORONTO_TZ
                    )
                )

            except Exception:

                resident_opening = None




    print()
    print(
        "=== REGISTER ELEMENT CHECK ==="
    )


    print(
        "#bookButton count :",
        page.locator(
            "#bookButton"
        ).count(),
    )





    print()
    print(
        "=========================================="
    )
    print(
        "REFRESH TIMING BENCHMARK"
    )
    print(
        "=========================================="
    )

    print(
        f"Taking {SAMPLE_COUNT} bounded samples."
    )

    print(
        "No registration button will be clicked."
    )


    samples = []


    for sample_number in range(
        1,
        SAMPLE_COUNT + 1,
    ):

        if sample_number > 1:

            print()

            print(
                f"Waiting "
                f"{SECONDS_BETWEEN_SAMPLES} "
                f"seconds..."
            )

            time.sleep(
                SECONDS_BETWEEN_SAMPLES
            )


        print()

        print(
            f"============== "
            f"SAMPLE {sample_number} "
            f"=============="
        )



        start_wall = (
            local_now()
        )

        start_perf = (
            time.perf_counter_ns()
        )


  

        try:

            response = page.reload(
                wait_until="commit",
                timeout=10000,
            )

        except Exception as e:

            print(
                "Refresh failed:",
                e,
            )

            continue


        commit_perf = (
            time.perf_counter_ns()
        )

        commit_wall = (
            local_now()
        )


        refresh_ms = (
            commit_perf
            - start_perf
        ) / 1_000_000


   

        status = None

        server_date_text = None

        server_date = None


        if response is not None:

            status = (
                response.status
            )

            server_date_text = (
                response.headers.get(
                    "date"
                )
            )

            server_date = (
                parse_server_date(
                    server_date_text
                )
            )




        (
            browser_record,
            navigation,
        ) = collect_browser_diagnostics(
            page
        )


        python_state_start = (
            local_now()
        )


        current_event_info = (
            get_event_info(page)
        )


        python_state_end = (
            local_now()
        )


        python_event_read_ms = (
            ms_between(
                python_state_start,
                python_state_end,
            )
        )


        python_button_start = (
            local_now()
        )


        try:

            python_button_exists = (
                page.locator(
                    "#bookButton"
                ).count()
                > 0
            )

        except Exception:

            python_button_exists = False


        python_button_end = (
            local_now()
        )


        python_button_read_ms = (
            ms_between(
                python_button_start,
                python_button_end,
            )
        )


     

        local_midpoint = (
            start_wall
            + (
                commit_wall
                - start_wall
            ) / 2
        )


        offset_low_ms = None
        offset_high_ms = None
        offset_mid_ms = None


        if server_date is not None:

            server_low = (
                server_date
            )

            server_high = (
                server_date
                + timedelta(
                    seconds=1
                )
            )


            local_mid_utc = (
                local_midpoint.astimezone(
                    server_date.tzinfo
                )
            )


            offset_low_ms = (
                server_low
                - local_mid_utc
            ).total_seconds() * 1000


            offset_high_ms = (
                server_high
                - local_mid_utc
            ).total_seconds() * 1000


            offset_mid_ms = (
                offset_low_ms
                + offset_high_ms
            ) / 2


     

        print(
            "Refresh started    :",
            fmt_time(
                start_wall
            ),
        )

        print(
            "Response committed :",
            fmt_time(
                commit_wall
            ),
        )

        print(
            "Refresh -> commit  :",
            f"{refresh_ms:.2f} ms",
        )

        print(
            "HTTP status        :",
            status,
        )

        print(
            "Server Date        :",
            server_date_text,
        )


     

        print()
        print(
            "--- BROWSER-SIDE TIMING ---"
        )


        if not browser_record:

            print(
                "Browser observer record unavailable."
            )

        else:

            print(
                "Document init       :",
                format_epoch_ms(
                    browser_record.get(
                        "initWall"
                    )
                ),
            )

            print(
                "DOMContentLoaded     :",
                format_epoch_ms(
                    browser_record.get(
                        "domContentLoadedWall"
                    )
                ),
            )

            print(
                "Window load          :",
                format_epoch_ms(
                    browser_record.get(
                        "loadWall"
                    )
                ),
            )

            print(
                "eventInfo available  :",
                format_epoch_ms(
                    browser_record.get(
                        "eventInfoAvailableWall"
                    )
                ),
            )

            print(
                "eventInfo OPEN       :",
                format_epoch_ms(
                    browser_record.get(
                        "eventInfoOpenWall"
                    )
                ),
            )

            print(
                "#bookButton inserted :",
                format_epoch_ms(
                    browser_record.get(
                        "buttonInsertedWall"
                    )
                ),
            )


            print()

            print_relative(
                "Init -> DOMContentLoaded",
                browser_record,
                "domContentLoadedPerf",
            )

            print_relative(
                "Init -> load",
                browser_record,
                "loadPerf",
            )

            print_relative(
                "Init -> eventInfo",
                browser_record,
                "eventInfoAvailablePerf",
            )

            print_relative(
                "Init -> OPEN",
                browser_record,
                "eventInfoOpenPerf",
            )

            print_relative(
                "Init -> button",
                browser_record,
                "buttonInsertedPerf",
            )


            open_perf = (
                browser_record.get(
                    "eventInfoOpenPerf"
                )
            )

            button_perf = (
                browser_record.get(
                    "buttonInsertedPerf"
                )
            )


            if (
                open_perf is not None
                and button_perf is not None
            ):

                print(
                    "Browser OPEN -> button :",
                    f"{button_perf - open_perf:.2f} ms",
                )


            commit_epoch_ms = (
                commit_wall.timestamp()
                * 1000
            )


            for (
                label,
                field,
            ) in [

                (
                    "Commit -> eventInfo",
                    "eventInfoAvailableWall",
                ),

                (
                    "Commit -> OPEN",
                    "eventInfoOpenWall",
                ),

                (
                    "Commit -> button",
                    "buttonInsertedWall",
                ),

            ]:

                value = (
                    browser_record.get(
                        field
                    )
                )

                if value is not None:

                    print(
                        f"{label:<23}: "
                        f"{value - commit_epoch_ms:.2f} ms"
                    )


        

        print()
        print(
            "--- NAVIGATION PERFORMANCE ---"
        )


        if not navigation:

            print(
                "Navigation timing unavailable."
            )

        else:

            def nav_value(name):
                value = (
                    navigation.get(name)
                )

                if value is None:
                    return "N/A"

                return (
                    f"{value:.2f} ms"
                )


            print(
                "requestStart        :",
                nav_value(
                    "requestStart"
                ),
            )

            print(
                "responseStart       :",
                nav_value(
                    "responseStart"
                ),
            )

            print(
                "responseEnd         :",
                nav_value(
                    "responseEnd"
                ),
            )

            print(
                "domInteractive      :",
                nav_value(
                    "domInteractive"
                ),
            )

            print(
                "DOMContentLoaded end:",
                nav_value(
                    "domContentLoaded"
                ),
            )

            print(
                "loadEventEnd        :",
                nav_value(
                    "loadEventEnd"
                ),
            )


            request_start = (
                navigation.get(
                    "requestStart"
                )
            )

            response_start = (
                navigation.get(
                    "responseStart"
                )
            )

            response_end = (
                navigation.get(
                    "responseEnd"
                )
            )


            if (
                request_start is not None
                and response_start is not None
            ):

                print(
                    "Request -> first byte:",
                    f"{response_start - request_start:.2f} ms",
                )


            if (
                response_start is not None
                and response_end is not None
            ):

                print(
                    "Response download     :",
                    f"{response_end - response_start:.2f} ms",
                )


   

        print()
        print(
            "--- PYTHON OBSERVATION ---"
        )


        if current_event_info is None:

            print(
                "eventInfo read       : unavailable"
            )

            can_not_book = None

            is_future = None

        else:

            can_not_book = (
                current_event_info.get(
                    "CanNotBook"
                )
            )

            is_future = (
                current_event_info.get(
                    "IsFutureRegistration"
                )
            )


            print(
                "CanNotBook           :",
                can_not_book,
            )

            print(
                "IsFutureRegistration :",
                is_future,
            )


        print(
            "eventInfo evaluate   :",
            f"{python_event_read_ms:.2f} ms",
        )

        print(
            "#bookButton exists   :",
            python_button_exists,
        )

        print(
            "button.count()       :",
            f"{python_button_read_ms:.2f} ms",
        )


        if (
            offset_low_ms is not None
            and offset_high_ms is not None
        ):

            print()

            print(
                "Date offset range  : "
                f"{offset_low_ms:+.1f} "
                f"to "
                f"{offset_high_ms:+.1f} ms"
            )


 

        samples.append(
            {
                "refresh_ms":
                    refresh_ms,

                "offset_low_ms":
                    offset_low_ms,

                "offset_high_ms":
                    offset_high_ms,

                "offset_mid_ms":
                    offset_mid_ms,

                "browser_record":
                    browser_record,

                "navigation":
                    navigation,

                "python_event_read_ms":
                    python_event_read_ms,

                "python_button_read_ms":
                    python_button_read_ms,

                "can_not_book":
                    can_not_book,

                "button_exists":
                    python_button_exists,
            }
        )




    print()
    print(
        "=========================================="
    )
    print(
        "TIMING SUMMARY"
    )
    print(
        "=========================================="
    )


    refresh_values = [
        s["refresh_ms"]
        for s in samples
    ]


    if refresh_values:

        print(
            "Samples             :",
            len(refresh_values),
        )

        print(
            "Fastest commit      :",
            f"{min(refresh_values):.2f} ms",
        )

        print(
            "Median commit       :",
            f"{statistics.median(refresh_values):.2f} ms",
        )

        print(
            "Average commit      :",
            f"{statistics.mean(refresh_values):.2f} ms",
        )

        print(
            "P10 commit          :",
            f"{percentile(refresh_values, 10):.2f} ms",
        )

        print(
            "P90 commit          :",
            f"{percentile(refresh_values, 90):.2f} ms",
        )

        print(
            "Slowest commit      :",
            f"{max(refresh_values):.2f} ms",
        )

        print(
            "Observed spread     :",
            f"{max(refresh_values) - min(refresh_values):.2f} ms",
        )




    event_info_init_values = []

    dom_init_values = []

    load_init_values = []

    open_init_values = []

    button_init_values = []


    for sample in samples:

        record = (
            sample["browser_record"]
        )

        if not record:
            continue


        for (
            destination,
            field,
        ) in [

            (
                dom_init_values,
                "domContentLoadedPerf",
            ),

            (
                load_init_values,
                "loadPerf",
            ),

            (
                event_info_init_values,
                "eventInfoAvailablePerf",
            ),

            (
                open_init_values,
                "eventInfoOpenPerf",
            ),

            (
                button_init_values,
                "buttonInsertedPerf",
            ),

        ]:

            value = relative_ms(
                record,
                field,
            )

            if value is not None:
                destination.append(
                    value
                )


    print()
    print(
        "=== BROWSER INITIALIZATION SUMMARY ==="
    )


    def print_median(
        label,
        values,
    ):

        if values:

            print(
                f"{label:<25}: "
                f"{statistics.median(values):.2f} ms"
            )

        else:

            print(
                f"{label:<25}: N/A"
            )


    print_median(
        "Median DOMContentLoaded",
        dom_init_values,
    )

    print_median(
        "Median window load",
        load_init_values,
    )

    print_median(
        "Median eventInfo",
        event_info_init_values,
    )

    print_median(
        "Median OPEN",
        open_init_values,
    )

    print_median(
        "Median button insertion",
        button_init_values,
    )




    event_read_values = [
        s["python_event_read_ms"]
        for s in samples
    ]


    button_read_values = [
        s["python_button_read_ms"]
        for s in samples
    ]


    print()
    print(
        "=== PLAYWRIGHT ROUND-TRIP SUMMARY ==="
    )


    if event_read_values:

        print(
            "Median page.evaluate :",
            f"{statistics.median(event_read_values):.2f} ms",
        )


    if button_read_values:

        print(
            "Median button.count  :",
            f"{statistics.median(button_read_values):.2f} ms",
        )


 

    valid_offsets = [
        s
        for s in samples
        if (
            s["offset_low_ms"]
            is not None
            and
            s["offset_high_ms"]
            is not None
        )
    ]


    print()
    print(
        "=== SERVER DATE ANALYSIS ==="
    )


    if valid_offsets:

        midpoint_values = [
            s["offset_mid_ms"]
            for s in valid_offsets
        ]


        common_low = max(
            s["offset_low_ms"]
            for s in valid_offsets
        )


        common_high = min(
            s["offset_high_ms"]
            for s in valid_offsets
        )


        print(
            "Date samples       :",
            len(valid_offsets),
        )

        print(
            "Median midpoint est:",
            f"{statistics.median(midpoint_values):+.1f} ms",
        )


        if common_low <= common_high:

            print(
                "Common offset band : "
                f"{common_low:+.1f} "
                f"to "
                f"{common_high:+.1f} ms"
            )

            print(
                "Band width         :",
                f"{common_high - common_low:.1f} ms",
            )

        else:

            print(
                "No clean common offset band."
            )


    else:

        print(
            "No usable HTTP Date samples."
        )




    print()
    print(
        "=== OPENING INFORMATION ==="
    )


    if resident_opening:

        current = (
            local_now()
        )

        remaining = (
            resident_opening
            - current
        ).total_seconds()


        print(
            "Resident opening   :",
            resident_opening.strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            ),
        )

        print(
            "Current local time :",
            fmt_time(current),
        )

        print(
            "Time until opening :",
            f"{remaining:.3f} seconds",
        )

    else:

        print(
            "Resident opening unavailable."
        )


 

    print()
   

    print()
    print(
        "=========================================="
    )
    print(
        "BENCHMARK COMPLETE"
    )
    print(
        "=========================================="
    )

    print()

    input(
        "Press Enter to close..."
    )

    browser.close()