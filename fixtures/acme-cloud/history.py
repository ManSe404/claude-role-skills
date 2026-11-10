"""The git history of the acme-cloud fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds and the edits it
makes, as (path, before, after). The story: Acme Tickets, a ticket seller, built its Azure estate by hand between
June and October 2026, and in October two briefs arrived for what comes next. Everything here is fictional, including
the subscription and tenant ids, which are all zeros.
"""

JELENA = ("Jelena Vukic", "jelena.vukic@example.com")
MILOS = ("Milos Radin", "milos.radin@example.com")

TF = "infra/terraform"

COMMITS = [
    {
        "date": "2026-06-02T09:30:00+02:00",
        "author": JELENA,
        "message": "Start the estate: resource groups, the network, the portal and the database",
        "add": [
            "README.md",
            ".gitignore",
            f"{TF}/versions.tf",
            f"{TF}/variables.tf",
            f"{TF}/locals.tf",
            f"{TF}/main.tf",
            f"{TF}/network.tf",
            f"{TF}/app.tf",
            f"{TF}/data.tf",
            f"{TF}/messaging.tf",
            f"{TF}/monitoring.tf",
            f"{TF}/modules/worker/main.tf",
        ],
    },
    {
        "date": "2026-07-14T11:20:00+02:00",
        "author": MILOS,
        "message": "Open the database for the load test",
        "edit": [
            (
                f"{TF}/data.tf",
                "",
                'resource "azurerm_mssql_firewall_rule" "allow_all" {\n'
                '  name             = "allow-all-temporary"\n'
                "  server_id        = azurerm_mssql_server.main.id\n"
                '  start_ip_address = "0.0.0.0"\n'
                '  end_ip_address   = "255.255.255.255"\n'
                "}\n\n",
            ),
        ],
    },
    {
        "date": "2026-08-05T10:00:00+02:00",
        "author": JELENA,
        "message": "Reports: a Bicep deployment for the analytics team",
        "add": ["infra/bicep/main.bicep", "infra/bicep/modules/reports.bicep"],
    },
    {
        "date": "2026-09-16T15:45:00+02:00",
        "author": MILOS,
        "message": "The alert group, from the old portal template",
        "add": ["infra/arm/alerts.json"],
    },
    {
        "date": "2026-10-20T09:15:00+02:00",
        "author": JELENA,
        "message": "Briefs: the box office and the festival platform",
        "add": ["docs/briefs/box-office.md", "docs/briefs/festival-platform.md"],
    },
]
