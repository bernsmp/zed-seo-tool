# Result Contracts

These contracts are literal. Never rename fields, omit input keywords, change keyword text, or reorder rows.

## Cleaning batch

Return a JSON object:

```json
{
  "classifications": [
    {
      "keyword": "exact input keyword",
      "classification": "KEEP",
      "confidence": 92,
      "reason": "Brief client-specific reason"
    }
  ]
}
```

Allowed classifications are `KEEP`, `REMOVE`, and `UNSURE`. Confidence is an integer from 0 through 100.

## Mapping batch

Return a JSON object:

```json
{
  "mappings": [
    {
      "keyword": "exact input keyword",
      "url": "https://client.example/existing-page",
      "confidence": 88,
      "intent": "transactional",
      "notes": "Best genuine topical match"
    }
  ]
}
```

`url` must be an exact URL from the client profile or one of `NEW_PAGE` and `BLOG_POST`. Never invent an existing URL.

## Validation behavior

`jobctl.py record` rejects:

- missing or extra rows;
- changed keywords;
- reordered keywords;
- unknown classification labels;
- confidence outside 0 through 100;
- mapping URLs absent from the client profile;
- malformed JSON.

The same batch can be repaired and recorded again. A previously completed batch cannot be replaced unless the operator intentionally supplies `--replace`.
