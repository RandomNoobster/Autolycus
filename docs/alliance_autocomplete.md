# Alliance Name Autocomplete Implementation

## Overview
This document describes the implementation of the alliance name autocomplete feature on the Raids page.

## Architecture

### Frontend (TypeScript/React)
**File:** `frontend/src/pages/RaidsPage.tsx`

- Uses React Query for data fetching with debounced search input (300ms delay)
- Triggers API call when user types 2+ characters
- Displays alliance results in Mantine Autocomplete component
- Format: "Alliance Name [ACRONYM]"
- Extracts clean alliance name on selection for filtering

**File:** `frontend/src/api/raids.ts`

```typescript
export function searchAlliances(
  token: string,
  query: string,
  limit: number = 10
): Promise<AllianceSearchResult[]>
```

Returns array of:
```typescript
{
  value: string;     // Alliance name (used for filtering)
  label: string;     // Display text: "Name [ACRONYM]"
  id: string;        // Alliance ID
  acronym: string;   // Alliance acronym
}
```

### Backend (Python/Flask)
**File:** `api/routes/raids.py`

**Endpoint:** `GET /api/raids/alliances/search`

**Query Parameters:**
- `q` (required): Search query string
- `limit` (optional): Max results, default 10, capped at 50

**Authentication:** Requires valid token via `@require_token` decorator

**Algorithm:**
1. Query Politics & War GraphQL API for top 100 alliances by score
2. Perform client-side fuzzy matching with scoring:
   - **1000 points**: Exact match (name, acronym, or ID)
   - **100 points**: Starts with query
   - **50 points**: Contains query
   - **25 points**: ID partial match
3. Sort by score (desc), then alphabetically
4. Return top N results

**File:** `logic/api_client.py`

New synchronous function for Flask routes:

```python
def query_sync(query_string: str, api_key: str, 
               variables: dict[str, Any] | None = None) -> dict[str, Any]
```

Features:
- Synchronous P&W GraphQL queries (uses `requests` library)
- Automatic rate limit handling (sleeps on X-Ratelimit-Remaining: 0)
- Retry logic (up to 2 retries on failures)
- Proper error handling for authentication and API errors

## Data Flow

1. **User types in autocomplete** → Debounced input (300ms)
2. **React Query triggers** → `searchAlliances(token, query, 15)`
3. **Frontend API call** → `GET /api/raids/alliances/search?q={query}&limit=15`
4. **Backend validates token** → `@require_token` decorator
5. **Backend queries P&W API** → `api_client.query_sync()` with GraphQL
6. **Backend scores & filters** → Fuzzy matching algorithm
7. **Backend returns JSON** → Array of alliance objects
8. **Frontend renders** → Mantine Autocomplete dropdown
9. **User selects** → Clean name extracted and applied to filter

## P&W API Integration

**GraphQL Query:**
```graphql
query {
  alliances(first: 100, orderBy: {column: SCORE, order: DESC}) {
    data {
      id
      name
      acronym
      score
    }
  }
}
```

**API Key:** Retrieved from `api_key` environment variable

**Schema Reference:** See `.ctx/pnwSchema.graphql` for complete API structure

## Error Handling

### Frontend
- Empty query returns empty array immediately
- Failed requests show no results (graceful degradation)
- Loading state handled by React Query

### Backend
- Missing API key: 500 error with `CONFIG_ERROR` code
- Invalid API key: 500 error with `AUTH_ERROR` code
- P&W API failures: 500 error with `INTERNAL_ERROR` code
- All errors logged with full stack traces

## Testing

**Test File:** `tests/test_api_client.py`

Test coverage:
- ✓ Successful synchronous queries
- ✓ Query with variables
- ✓ Invalid API key handling
- ✓ Rate limit handling with sleep
- ✓ JSON decode errors
- ✓ Retry logic on temporary failures

**Run tests:**
```bash
python -m pytest tests/test_api_client.py -v
```

## Performance Considerations

1. **Frontend Debouncing:** 300ms delay reduces API calls
2. **Backend Caching:** Not implemented (consider Redis for production)
3. **Query Limit:** Max 100 alliances from P&W API, filtered client-side
4. **Rate Limiting:** Automatic sleep/retry on P&W API rate limits
5. **Response Size:** Limited to 50 results maximum

## Future Improvements

1. **Server-side caching** - Cache alliance list for 5-15 minutes
2. **Fuzzy search library** - Use `fuzzywuzzy` or `rapidfuzz` for better matching
3. **Database integration** - Store alliance data locally for faster queries
4. **Name normalization** - Handle special characters and accents
5. **Recent searches** - Remember user's recent alliance searches
6. **Alliance score display** - Show alliance score in dropdown for context

## Configuration

**Environment Variables:**
- `api_key`: Politics & War API key (required)
- `SECRET_KEY`: Flask token signing key (required)
- `pymongolink`: MongoDB connection string (for other features)

## Security

- Token validation required for all requests
- API key stored server-side only (not exposed to frontend)
- No SQL/NoSQL injection risks (uses GraphQL)
- Rate limiting handled gracefully

## Troubleshooting

**No results showing:**
1. Check `api_key` environment variable is set
2. Verify P&W API key is valid
3. Check browser console for network errors
4. Verify backend logs for API errors

**Slow autocomplete:**
1. Check P&W API rate limits in response headers
2. Verify debounce is working (300ms delay)
3. Monitor backend response times
4. Consider implementing caching

**Format issues:**
1. Ensure backend returns "Name [ACRONYM]" format
2. Verify frontend regex matches bracket format
3. Check for alliances without acronyms (handled gracefully)
