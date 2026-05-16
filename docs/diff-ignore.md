# Diff ignore rules

`diff_ignore.json` lives next to `app.json` and tells scout which
differences in API responses are noise (timestamps, IDs, server-generated
tokens) rather than real regressions. Without it, the diff report fills
up with `created_at` and ULID noise that drowns out actual changes.

## File layout

```json
{
  "field_ignore": [...],
  "header_ignore": [...],
  "status_only": [...],
  "endpoint_ignore": [...],
  "known_changes": [...]
}
```

All keys are optional.

---

## `field_ignore`

Suppress specific fields anywhere in the JSON response body. Two forms:

**Simple field name** — matches a key anywhere in the response tree
regardless of depth:

```json
{
  "field_ignore": [
    "updated_at",
    "created_at",
    "id",
    "token"
  ]
}
```

This hides differences in `$.updated_at`, `$.user.created_at`,
`$.items[].id`, `$.session.token`, etc.

**JSONPath expression** — pin to a specific location:

```json
{
  "field_ignore": [
    "$.product_category.handle",
    "$.product_categories[].handle",
    "$.stock_location.address.postal_code"
  ]
}
```

Path syntax:

- `$` — root
- `.field` — object field
- `[]` or `[*]` — any array element
- `[N]` — specific array index

---

## `header_ignore`

Response headers to ignore. Most useful for things like
`Access-Control-Allow-Origin` that vary by deployment, or
server-generated tracing headers:

```json
{
  "header_ignore": [
    "access-control-allow-origin",
    "x-request-id"
  ]
}
```

Header names are case-insensitive.

---

## `status_only`

Endpoints to compare by HTTP status code only, ignoring response body.
Use for endpoints whose body is noisy by design (notification feeds,
polling endpoints, dashboards) but whose status code still matters:

```json
{
  "status_only": [
    {"endpoint": "GET /admin/notifications"},
    {"endpoint": "GET /admin/*", "step_seq": "4"},
    {"endpoint": "GET /admin/orders", "scenario": "orders.export"}
  ]
}
```

Filter fields (combine with AND):

- `endpoint` — `METHOD /path` pattern, glob-supported (`*` matches a
  segment, `**` matches multiple)
- `step_seq` — match only at a specific step index in the scenario
- `scenario` — match only in named scenarios (glob supported)

---

## `endpoint_ignore`

Drop endpoints entirely from the diff. Use when an endpoint is irrelevant
to the comparison (e.g., third-party analytics calls, prefetch
endpoints, health checks):

```json
{
  "endpoint_ignore": [
    {"endpoint": "GET /admin/_internal/health"},
    {"endpoint": "POST /telemetry/*"}
  ]
}
```

Same filter fields as `status_only`.

---

## `known_changes`

Behavioral changes you've intentionally introduced or accepted. Each rule
pins a specific path in a specific endpoint, and includes the version
where the change appeared. The diff report shows known-changes in their
own section (collapsed by default) so they don't clutter the active
regression list:

```json
{
  "known_changes": [
    {
      "endpoint": "POST /admin/customers",
      "path": "$.customer.metadata",
      "kind": "added",
      "added_in": "2.14.0",
      "note": "v2.14 introduced customer metadata blob"
    }
  ]
}
```

The `added_in` version appears as a badge in the diff report. Useful for
showing reviewers "yes, this change is documented and expected".

---

## A complete example

See [scout-medusa's `admin/diff_ignore.json`](https://github.com/boxprobe/scout-medusa/blob/main/admin/diff_ignore.json)
— hand-tuned across 15 admin scenarios against Medusa v2.13.6 → v2.14.0.
