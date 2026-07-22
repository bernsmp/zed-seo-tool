# Client Profile Contract

Each client lives at `clients/<client-slug>/profile.json` in the Cowork project folder.

Required shape:

```json
{
  "business_name": "Client name",
  "domain": "example.com",
  "services": ["service one"],
  "locations": ["city, state"],
  "specialties": ["specialty"],
  "negative_keywords": ["competitor name"],
  "negative_categories": ["unrelated service category"],
  "url_inventory": [
    {
      "url": "https://example.com/service",
      "title": "Service page title",
      "summary": "What the page genuinely covers"
    }
  ],
  "updated_at": "ISO-8601 timestamp",
  "source_notes": "Where these facts came from"
}
```

Preserve the client's exact domain and URL casing. Missing inputs stay visibly missing. Never invent services, locations, specialties, negatives, or pages.
