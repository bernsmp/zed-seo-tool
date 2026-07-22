---
name: zed-seo-client
description: >
  Create, review, or update a Zed SEO client profile and verified URL inventory.
  Use when Carlos says "add a client", "set up this client", "update the client
  profile", "crawl the site", "add URLs", or names a client before a cleaning
  or mapping job exists.
metadata:
  version: "0.1.0"
---

# Create or Update a Client

The client profile controls every downstream judgment. Missing information remains visibly missing.

## 1. Read the contract

Read `${CLAUDE_PLUGIN_ROOT}/references/client-profile-schema.md`.

## 2. Establish verified inputs

Collect or verify:

- business name and exact domain;
- services and specialties;
- served locations;
- known competitor names, wrong locations, and irrelevant categories;
- the current URL inventory with title and factual page summary.

Use files Carlos supplies, the client's live site, or connected sources. State the source of each fact. Never infer a service, location, specialty, or URL from a keyword list alone.

For an existing profile, preserve validated fields unless the new evidence clearly supersedes them. Show Carlos any meaningful change to services, locations, negatives, or URL inventory before saving it.

## 3. Save through the validator

Choose a stable lowercase hyphenated slug. Write the proposed JSON to a temporary file in the project folder, then run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" client-put \
  --workspace "$WORKSPACE" \
  --client "$CLIENT_SLUG" \
  --profile "$PROFILE_JSON"
```

The canonical profile is `clients/<client-slug>/profile.json`. Remove the temporary proposal after the validated copy exists.

## 4. Close

Report the exact slug, domain, service count, location count, URL count, and any missing inputs that could weaken cleaning or mapping.
