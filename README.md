# NL Sponsor Radar

International students looking for junior tech jobs in the Netherlands need an employer that the IND recognises as a sponsor for the highly skilled migrant permit. Job boards do not say which employers qualify. NL Sponsor Radar collects postings from public company job boards, links each employer to the [IND public register](https://ind.nl/en/public-register-recognised-sponsors/public-register-regular-labour-and-highly-skilled-migrants) by KvK number, and shows how confident each link is.

Status: data pipeline (phase 1). The public web page comes next.

## How it works

1. Collectors fetch Greenhouse, Ashby, and Recruitee public board APIs. Each payload is stored unmodified before parsing, so parser changes can be replayed.
2. Postings are upserted by source and external id; postings that disappear are closed.
3. The IND register is snapshotted only when its rows change.
4. Each employer is linked to the register: a hand-verified KvK number first, then normalized name matching.

See `AGENTS.md` for commands.
