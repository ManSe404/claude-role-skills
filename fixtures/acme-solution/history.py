"""The git history of the acme-solution fixture.

The files under files/ are the state after the last commit. The story: Acme Mutual's client brief arrived in
October 2026, and in the first week of November five specialists each wrote their page about it, with nobody joining
them. Everything here is fictional.
"""

TEA = ("Tea Vidmar", "tea.vidmar@example.com")
LUKA = ("Luka Horvat", "luka.horvat@example.com")

BRIEF = "docs/briefs/claims-platform.md"
ROOMS = "docs/briefs/room-booking.md"

COMMITS = [
    {
        "date": "2026-10-20T10:00:00+02:00",
        "author": TEA,
        "message": "The client brief for the claims platform, and a small one for room booking",
        "add": ["README.md", BRIEF, ROOMS],
    },
    {
        "date": "2026-11-08T17:30:00+01:00",
        "author": LUKA,
        "message": "The specialists' pages, one per area",
        "add": [
            "pages/ai-pattern-2026-11-03.json",
            "pages/ai-stack-2026-11-04.json",
            "pages/data-platform-2026-11-05.json",
            "pages/arch-style-2026-11-05.json",
            "pages/cloud-design-2026-11-07.json",
        ],
    },
]
