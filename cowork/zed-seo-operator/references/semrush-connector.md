# Official SEMrush Connector Rules

Use the verified **Semrush** connector installed through Claude's connector directory. Authenticate with the approved Trackable Med SEMrush account.

## Preserve source truth

- Record the queried domain, country database, report type, retrieval time, and connector-reported limits.
- Preserve keyword text exactly.
- Prefer these columns when the connector returns them: `keyword`, `volume`, `kd`, `intent`, `position`, `url`, `source_domain`, `database`.
- Do not fabricate missing volume, difficulty, intent, ranking, or URL values.
- Deduplicate only exact duplicate rows unless the operator asks for a different rule.
- If the connector returns fewer rows than requested, state the returned count and the connector limit. Never describe a partial pull as complete.

## Large sources

For large competitor or gap pulls, paginate when the connector supports pagination. Write each completed page to the project folder before requesting the next page. Merge pages deterministically and preserve provenance columns.

If the connector cannot retrieve the requested volume in the current plan or session, ask Carlos to export the CSV from SEMrush and continue through the upload path. The downstream cleaning and mapping workflow is identical.

## Permissions

The connector is read-only. Do not promise that this plugin can change a SEMrush campaign, project, audit, or keyword list.
