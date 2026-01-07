# Copilot Instructions for Autolycus Rewrite

This file contains guidelines for AI agents (including GitHub Copilot, Claude, and other AI assistants) working on the Autolycus Rewrite codebase.

## Ground Truth: The Encyclopedia

**`pwpedia_data.jsonl` is the authoritative source for all Politics & War game mechanics, formulas, and updates.**

### Before implementing ANY game-related functionality:

1. **Search `pwpedia_data.jsonl`** for the topic (e.g., "Infrastructure", "Disease", "Population-Density")
2. **Verify all formulas** against PWPedia content before coding
3. **Check for game updates** (e.g., July 2025 updates mentioned in the data)
4. **If nothing is found**, check the `fandom_data.jsonl` file for additional context (note that this is less authoritative than pwpedia_data.jsonl)
5. **API Schema**: Use `pnwSchema.graphql` to understand available API fields and types
6. **Document the source** in code comments with the article title
7. **Flag any discrepancies** between current implementation and PWPedia

### Example Verification Pattern:

```python
# Fact-checking example - DO THIS:
# Per PWPedia "Infrastructure" article:
# "Infrastructure has a bulk discount; in 500s"
# "Only buy it in batches of 100s for best discount"

def calculate_infra_cost(from_level: int, to_level: int) -> int:
    """Calculate infrastructure cost with bulk discount.
    
    Per PWPedia: Bulk discount applies at 100 level increments.
    Source: pwpedia_data.jsonl - Infrastructure article
    """
    # Implementation here
    pass
```

## Code Quality Standards

### Python Standards (Backend & Discord Bot)

- **Style Guide**: PEP 8 with 100-character line length
- **Type Hints**: Required for all function signatures
- **Docstrings**: Google-style docstrings for all public functions/classes
- **Testing**: Unit tests required for business logic
- **Error Handling**: Comprehensive exception handling with logging
- **Logging**: Use Python's logging module; no print statements
- **Separation of Concerns**: Separate API calls, business logic, and data models (IMPORTANT)
- **Modularization**: Break code into reusable modules/functions (IMPORTANT)

```python
def get_nation_info(nation_id: int) -> dict:
    """Retrieve detailed nation information.
    
    Args:
        nation_id: The P&W nation ID
        
    Returns:
        Dictionary containing nation data including score, infrastructure,
        city count, and other game metrics.
        
    Raises:
        ValueError: If nation_id is invalid (≤ 0)
        NationNotFound: If nation does not exist in P&W
        
    Note:
        Data is cached for 5 minutes to reduce API calls.
    """
    if not isinstance(nation_id, int) or nation_id <= 0:
        raise ValueError(f"Invalid nation_id: {nation_id}")
    # Implementation
```

### Django Backend Conventions

- **Models**: One model per core game entity (Nation, Alliance, War, City, etc.)
- **Views**: Use ViewSets with appropriate serializers
- **Serializers**: Include validation and computed fields
- **URLs**: Descriptive, RESTful, lowercase with hyphens
- **API Responses**: Follow consistent response format (see docs/api.md)

### Discord Bot Conventions

- **Cogs**: One cog per command category (nations.py, wars.py, trades.py, etc.)
- **Commands**: Slash commands preferred (modern Pycord)
- **Error Handling**: User-friendly error messages with context
- **Embeds**: Consistent color scheme and formatting
- **Rate Limiting**: Respect P&W API rate limits; cache appropriately

```python
@discord.slash_command(
    name="nation",
    description="Get detailed information about a nation",
)
async def nation_command(
    ctx: discord.ApplicationContext,
    nation_id: int,
):
    """Fetch and display nation information.
    
    Args:
        ctx: Discord context
        nation_id: The Politics & War nation ID
    """
    # Implementation
```

### Game Updates to Monitor

The `pwpedia_data.jsonl` file includes recent updates (e.g., July 2025). When implementing features:

1. **Check for update notes** in the encyclopedia
2. **Verify compatibility** with current game version
3. **Update code comments** if behavior changed
4. **Flag breaking changes** to team leads

## API Integration

### Politics & War GraphQL API

- **Schema Reference**: The `pnwSchema.graphql` file contains the complete API definition. Consult this file when working in the backend and designing API calls to the game.
- **Preferred Access**: While `pnwSchema.graphql` is used for designing external calls, it is natural to use the internal **Django API** for standard data operations and retrieval within the application.
- **Rate Limits**: Check X-RateLimit-* headers
- **Authentication**: Include X-Api-Key header
- **Error Handling**: Handle timeouts and rate limit exceeded gracefully
- **Caching**: Cache responses appropriately (5-15 minutes based on data freshness needs)

### Backend REST API

- **Response Format**: Consistent JSON structure (see docs/api.md)
- **Pagination**: Support offset/limit or cursor pagination
- **Filtering**: Support common filters (date ranges, status, etc.)
- **Error Codes**: Use standard HTTP status codes

## Testing Requirements

### Unit Tests

```python
def test_calculate_infra_cost():
    """Test infrastructure cost calculation against PWPedia formula."""
    # Test standard calculation
    cost = calculate_infra_cost(100, 200)
    assert cost > 0
    
    # Test bulk discount application
    cost_bulk = calculate_infra_cost(0, 100)
    # Verify matches PWPedia bulk discount at 100 level
```

### Integration Tests

- Test Discord bot commands end-to-end
- Test P&W API integration with actual (or mocked) data
- Verify database queries and caching behavior

## Documentation Standards

### Code Comments

- **Why** > **What**: Explain reasoning, not what the code does
- **PWPedia references**: Link to specific articles when implementing formulas
- **Gotchas**: Document non-obvious behaviors or game mechanics quirks

```python
# GOOD:
# Per PWPedia, disease decreases with hospitals OR increased land.
# We check hospital count first as it's more efficient.
hospital_count = count_improvement(city, "Hospital")

# BAD:
# Count the hospitals
hospital_count = count_improvement(city, "Hospital")
```

## Common Pitfalls to Avoid

1. ❌ **Hardcoding game values** → Reference PWPedia each time or use config
2. ❌ **Ignoring P&W API rate limits** → Implement proper caching
3. ❌ **Not validating user input** → Validate nation IDs, numbers, etc.
4. ❌ **Inconsistent error messages** → Use consistent, helpful messages
5. ❌ **Forgetting to update docs** → Update README/docs when changing features
6. ❌ **Not checking pwpedia_data.jsonl** → Always verify game mechanics
7. ❌ **Mixing concerns in functions** → Keep API calls separate from business logic

## Architecture Principles

### Backend (Django)

- **Single Responsibility**: Each view/serializer has one purpose
- **DRY**: Don't repeat P&W API calls; use services
- **Testability**: Mock external APIs for tests
- **Security**: Validate all inputs, use environment variables for secrets

### Discord Bot

- **Modularity**: One cog per command category
- **Composability**: Reusable utility functions
- **Resilience**: Graceful error handling; don't let one command failure crash bot
- **Performance**: Cache frequently accessed data

## New Feature Checklist

Before implementing a new feature:

- [ ] **Fact-check in `pwpedia_data.jsonl`** - Verify all game mechanics
- [ ] **Identify data model** - What database entities are involved?
- [ ] **Design API endpoint** - Check `pnwSchema.graphql` for external data, or use Django API for internal.
- [ ] **Write tests** - Unit tests for business logic
- [ ] **Handle errors** - What can go wrong?
- [ ] **Document it** - Update README/docs
- [ ] **Code review** - Have someone verify PWPedia accuracy

## Questions? Debugging Tips

### Game Mechanic Questions

1. Search `pwpedia_data.jsonl` first
2. Ask the user

### Code Issues

1. Check logs for error details
2. Verify against existing similar implementations
3. Test with small dataset first
4. Use print/logging statements (no debugger in Discord)

## Compliance & Updates

This document should be reviewed when:
- New features are added to the codebase
