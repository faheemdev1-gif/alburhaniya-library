# Require the connector gate on `main`

GitHub Actions can report a failing check, but repository rules are what stop
an unsafe merge or direct push.

In the GitHub repository:

1. Open **Settings → Rules → Rulesets**.
2. Create a branch ruleset targeting the default branch (`main`).
3. Enable **Require a pull request before merging**.
4. Enable **Require status checks to pass**.
5. Add the required check **independent-corpus-and-regression**.
6. Enable **Block force pushes** and **Restrict deletions**.
7. Activate the ruleset.

Do not require `live-production-contract` as a pull-request check: it is a
post-deployment/scheduled check and is intentionally skipped on pull requests.
Run it after Render deploys, or let the weekly schedule run it every Monday at
03:00 UTC.
