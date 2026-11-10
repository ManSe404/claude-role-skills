"""The git history of the acme-design fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds and the edits it
makes, as (path, before, after). The builder walks the list backwards, undoing each edit, to recover the state after
every commit, then replays it forwards with git.

The story: in October 2026 Acme Logistics, the parcel company in Novi Sad, wrote down Parcel booking v2 before
building any of it. A draft proposal and its quality goals came first, then three ADRs, then a proposed ADR for the
message broker, and in November a second revision of the proposal after the first review. There is no code: only
design documents. Everything here is fictional.
"""

JELENA = ("Jelena Savkov", "jelena.savkov@example.com")
BOJAN = ("Bojan Ostojin", "bojan.ostojin@example.com")
IVANA = ("Ivana Kerac", "ivana.kerac@example.com")

PROPOSAL = "design/proposal.md"
GOALS = "design/quality-goals.md"
ADR_SERVICES = "design/adr/0001-split-booking-into-services.md"
ADR_DATA = "design/adr/0002-central-data-service.md"
ADR_TRACKING = "design/adr/0003-tracking-polls-booking.md"
ADR_BROKER = "design/adr/0004-message-broker.md"

COMMITS = [
    {
        "date": "2026-10-06T10:00:00+02:00",
        "author": JELENA,
        "message": "Draft the Parcel booking v2 proposal and its quality goals",
        "add": ["README.md", PROPOSAL, GOALS],
    },
    {
        "date": "2026-10-14T16:20:00+02:00",
        "author": BOJAN,
        "message": "ADRs 1 to 3: services, one Data Service, tracking by polling",
        "add": [ADR_SERVICES, ADR_DATA, ADR_TRACKING],
        "edit": [
            ("README.md", "", "- `design/adr/`: the architecture decision records.\n"),
        ],
    },
    {
        "date": "2026-10-22T11:40:00+02:00",
        "author": IVANA,
        "message": "ADR-0004: the message broker, proposed",
        "add": [ADR_BROKER],
        "edit": [
            (
                PROPOSAL,
                "Which broker product we run is not chosen yet.\n",
                "Which broker product we run is to be decided later (ADR-0004).\n",
            ),
            (
                ADR_SERVICES,
                "exchange events through a message broker.\n",
                "exchange events through a message broker (ADR-0004).\n",
            ),
        ],
    },
    {
        "date": "2026-11-03T09:15:00+01:00",
        "author": JELENA,
        "message": "Revision 2 after the first review: address check budget, tariff cache, charge retries",
        "edit": [
            (PROPOSAL, "- Revision: 1, draft for review\n", "- Revision: 2, after the first review on 2026-10-30\n"),
            (
                PROPOSAL,
                "    BK -->|REST| AV[Address Validator]\n",
                "    BK -->|REST, 50 ms budget| AV[Address Validator]\n",
            ),
            (
                PROPOSAL,
                "    PR -->|SQL| PDB[(Pricing database)]\n",
                "    PR -->|SQL, read-through cache| PDB[(Pricing database)]\n",
            ),
            (
                PROPOSAL,
                "",
                "\n"
                "The Pricing service reads tariffs through a read-through cache that keeps each tariff for "
                "15 minutes.\n"
                "A tariff change can therefore take up to 15 minutes to reach quotes: quotes are eventually consistent "
                "with the tariff table.\n"
                "The commercial team accepted this on 2026-10-29, because tariffs change at most once a week and take "
                "effect on the following Monday.\n",
            ),
            (
                PROPOSAL,
                "The Booking service calls the Address Validator synchronously.\n",
                "The Booking service calls the Address Validator synchronously with a time budget of 50 ms.\n"
                "If the Address Validator has not answered within 50 ms, the Booking service accepts the address as "
                "typed and marks the booking for an address check by the counter staff.\n"
                "A slow Address Validator therefore never delays a booking by more than 50 ms.\n",
            ),
            (
                PROPOSAL,
                "3. The Booking service calls the Address Validator.\n",
                "3. The Booking service calls the Address Validator (budget 50 ms, section 6).\n",
            ),
            (
                PROPOSAL,
                "",
                "If the charge call times out after 2 seconds, the Booking service retries the charge, up to three "
                "times.\n"
                "If the charge still fails after the retries, the booking stays confirmed and the Billing service "
                "e-mails the customer a payment link.\n",
            ),
            (
                PROPOSAL,
                "3. Quotes use the new tariff from the next booking on.\n",
                "3. Quotes use the new tariff once the cached copy has expired, at the latest 15 minutes later.\n",
            ),
            (
                PROPOSAL,
                "",
                "\n"
                "## 18. Changes in revision 2\n"
                "\n"
                "- Added the time budget of the Address Validator and what the Booking service does when it is "
                "exceeded.\n"
                "- Added the read-through cache for tariffs and the staleness the commercial team accepted.\n"
                "- Added retries of the charge call when it times out.\n",
            ),
            (
                GOALS,
                "",
                "| Tariff consistency | Quotes are eventually consistent with the tariff table, at most 15 minutes "
                "behind it. | Milan Tadin |\n"
                "| Address check latency | Checking an address adds at most 50 ms of latency to a booking. | "
                "Jelena Savkov |\n",
            ),
            (
                GOALS,
                "",
                "- Tariff consistency: the commercial team accepted the 15 minutes on 2026-10-29, because tariffs "
                "change at most once a week.\n"
                "- Address check latency: inside the Booking service, around the call to the Address Validator.\n",
            ),
        ],
    },
]
