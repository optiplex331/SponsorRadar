# NL Sponsor Radar

International students looking for junior tech jobs in the Netherlands need an employer that the IND recognises as a sponsor for the highly skilled migrant permit. Job boards do not say which employers qualify. NL Sponsor Radar collects postings from public company job boards, links each employer to the [IND public register](https://ind.nl/en/public-register-recognised-sponsors/public-register-regular-labour-and-highly-skilled-migrants) by KvK number, and shows how confident each link is.

Live at <https://sponsorradar.halligalli.games>, refreshed daily from 500 job boards. Deployment lives in [SponsorRadar-infrastructure](https://github.com/optiplex331/SponsorRadar-infrastructure). An hourly GitHub Actions probe (`scripts/probe.sh`) checks from outside the cluster that the site is up and that collection, posting counts, and the register snapshot are fresh; a failed run is the alert.

## How it works

1. Collectors fetch Greenhouse, Ashby, and Recruitee public board APIs. Each payload is stored unmodified before parsing, so parser changes can be replayed.
2. Postings are upserted by source and external id; postings that disappear are closed.
3. The IND register is snapshotted only when its rows change.
4. Each employer is linked to the register: a hand-verified KvK number first, then normalized name matching.
5. Rules mark each posting's seniority, whether it is a tech role, whether it requires Dutch, the years of experience it asks for, and whether it offers or refuses visa sponsorship. The page filters on these in the browser, and the filter lives in the URL. By default it shows non-senior tech postings from register sponsors that do not require Dutch, ask for at most 2 years (or do not say), and do not refuse visa sponsorship.
6. The page also shows what changed in the latest register update, flags salaries against the IND highly skilled migrant threshold, and lets visitors look up whether an employer is on the register.

See `AGENTS.md` for commands.
