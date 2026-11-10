"""The git history of the acme-cloud-aws fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds and the edits it
makes, as (path, before, after). The story: Stagefront, a ticket seller on AWS, built its estate by hand between
March and October 2026, and in October the group's brief for the festival platform arrived. Everything here is
fictional, including the account id, which is all zeros.
"""

MARKO = ("Marko Ilic", "marko.ilic@example.com")
SANJA = ("Sanja Petkov", "sanja.petkov@example.com")

TF = "infra/terraform"
CFN = "infra/cloudformation"

COMMITS = [
    {
        "date": "2026-03-10T09:40:00+01:00",
        "author": MARKO,
        "message": "Start the estate: the network, the portal, the worker and the database",
        "add": [
            "README.md",
            ".gitignore",
            f"{TF}/versions.tf",
            f"{TF}/variables.tf",
            f"{TF}/locals.tf",
            f"{TF}/network.tf",
            f"{TF}/iam.tf",
            f"{TF}/app.tf",
            f"{TF}/data.tf",
            f"{TF}/messaging.tf",
            f"{TF}/monitoring.tf",
            f"{TF}/modules/queue/main.tf",
        ],
    },
    {
        "date": "2026-07-02T16:05:00+02:00",
        "author": SANJA,
        "message": "Open the database for the load test",
        "edit": [
            (
                f"{TF}/data.tf",
                "  publicly_accessible             = false\n",
                "  publicly_accessible             = true\n",
            ),
            (
                f"{TF}/network.tf",
                "",
                '\nresource "aws_security_group_rule" "db_load_test" {\n'
                '  type              = "ingress"\n'
                "  from_port         = 5432\n"
                "  to_port           = 5432\n"
                '  protocol          = "tcp"\n'
                '  cidr_blocks       = ["0.0.0.0/0"]\n'
                "  security_group_id = aws_security_group.db.id\n"
                "}\n",
            ),
        ],
    },
    {
        "date": "2026-08-12T11:30:00+02:00",
        "author": SANJA,
        "message": "Reports: a CloudFormation stack for the analytics team",
        "add": [f"{CFN}/reports.yaml"],
    },
    {
        "date": "2026-09-22T14:10:00+02:00",
        "author": MARKO,
        "message": "The admin host and the alert topic",
        "add": [f"{CFN}/admin.yaml", f"{CFN}/alerts.json"],
    },
    {
        "date": "2026-10-20T09:15:00+02:00",
        "author": SANJA,
        "message": "The brief for the festival platform",
        "add": ["docs/briefs/festival-platform.md"],
    },
]
