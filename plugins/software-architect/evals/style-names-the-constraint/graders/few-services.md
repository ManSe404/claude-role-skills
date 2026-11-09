---
type: llm
---

The brief is 30 engineers in 4 teams and only 2 platform engineers, telemetry at 200 times the load of the rest, teams shipping on their own schedules, route optimisation in Python, several teams reacting to the same vehicle events, computations up to 40 minutes.
PASS if the reply recommends a small number of services (with or without an event backbone for vehicle events), explains that full microservices are ruled out by too few platform engineers, and names the constraint that decides.
FAIL if it recommends microservices, a monolith, or serverless functions as the main shape.
