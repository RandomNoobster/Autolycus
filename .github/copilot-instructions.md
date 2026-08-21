# Copilot Instructions for Autolycus Rewrite

This file contains guidelines for AI agents (including GitHub Copilot, Claude, and other AI assistants) working on the Autolycus Rewrite codebase.

## 📂 Context & Knowledge Base

**IMPORTANT: All Politics & War (the game) related information, including mechanics, politics, and historical context, is located within the `.ctx` folder.**

When answering questions or writing code regarding game mechanics:
1.  **Primary Source:** `pwpedia_data.jsonl` (Most up-to-date and authoritative).
2.  **Backup Source:** `fandom_data.jsonl` (Use only if PWPedia is lacking; less reliable).
3.  **API Structure:** `pnwSchema.graphql` (Defines the external game API).

---

## 🏛️ Ground Truth: The Encyclopedia

**`pwpedia_data.jsonl` is the authoritative source for all Politics & War game mechanics, formulas, and updates.**

### Before implementing ANY game-related functionality:

1.  **Search `pwpedia_data.jsonl`** first for the topic (e.g., "Infrastructure", "Disease", "Population-Density").
2.  **Verify all formulas** against PWPedia content before coding.
3.  **Check for game updates** (e.g., July 2025 updates mentioned in the data).
4.  **Backup Search**: Only if nothing is found in PWPedia, check `fandom_data.jsonl`. Be aware that Fandom data may be outdated.
5.  **API Schema**: Consult `pnwSchema.graphql` to understand available API fields, types, and relationships.
6.  **Document the source** in code comments with the article title.
7.  **Flag any discrepancies** between current implementation and PWPedia.

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

## 🏗️ Architecture & Design Principles

### 1. Separation of Concerns (SoC)
Strict adherence to SoC is required to maintain maintainability.
*   **Data Access Layer:** Only code interacting with the DB or P&W API.
*   **Business Logic Layer:** Pure Python functions that calculate game mechanics (e.g., revenue calculators, combat simulation). These should **not** know about Discord Contexts or HTTP Requests.
*   **Presentation Layer:** 
    *   *Django Views:* Handle HTTP requests/responses.
    *   *Discord Cogs:* Handle user input and formatting embeds.
*   **Goal:** You should be able to swap the Discord bot for a CLI without changing the business logic.

### 2. Don't Repeat Yourself (DRY)
*   **Centralize Formulas:** Never write a tax calculation or combat formula in two places. If the bot needs it and the website needs it, it belongs in a shared utility module or service class.
*   **Reusable Components:** Use shared serializers and helper functions for common tasks (e.g., parsing nation IDs, formatting currency).

## 💻 Code Quality Standards

### Python Standards (Backend & Discord Bot)

-   **Style Guide**: PEP 8 with 100-character line length.
-   **Type Hints**: Required for all function signatures.
-   **Docstrings**: Google-style docstrings for all public functions/classes.
-   **Testing**: Unit tests required for business logic.
-   **Error Handling**: Comprehensive exception handling with logging.
-   **Logging**: Use Python's logging module; no print statements.
-   **Modularization**: Break code into reusable modules/functions.

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

-   **Models**: One model per core game entity (Nation, Alliance, War, City, etc.).
-   **Views**: Use ViewSets with appropriate serializers.
-   **Serializers**: Include validation and computed fields.
-   **URLs**: Descriptive, RESTful, lowercase with hyphens.
-   **API Responses**: Follow consistent response format (see docs/api.md).

### Discord Bot Conventions

-   **Cogs**: One cog per command category (nations.py, wars.py, trades.py, etc.).
-   **Commands**: Slash commands preferred (modern Pycord).
-   **Error Handling**: User-friendly error messages with context.
-   **Embeds**: Consistent color scheme and formatting.
-   **Rate Limiting**: Respect P&W API rate limits; cache appropriately.

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
    # Implementation calling Business Logic layer, NOT raw API/DB
```

## 🔌 API Integration

### Politics & War GraphQL API
-   **Schema Reference**: The `pnwSchema.graphql` file contains the complete definition of the game's API. Consult this file to see what data is available, the correct field names, and type definitions.
-   **Usage**: While `pnwSchema.graphql` is the blueprint for external calls, prefer using the internal **Django API** for standard operations within the application to maintain DRY principles.
-   **Rate Limits**: Check X-RateLimit-* headers.
-   **Authentication**: Include X-Api-Key header.
-   **Caching**: Cache responses appropriately (5-15 minutes based on data freshness needs).

### Backend REST API
-   **Response Format**: Consistent JSON structure (see docs/api.md).
-   **Pagination**: Support offset/limit or cursor pagination.
-   **Filtering**: Support common filters (date ranges, status, etc.).

## 🧪 Testing Requirements

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
-   Test Discord bot commands end-to-end.
-   Test P&W API integration with actual (or mocked) data.
-   Verify database queries and caching behavior.

## 📝 Documentation Standards

### Code Comments
-   **Why** > **What**: Explain reasoning, not what the code does.
-   **PWPedia references**: Link to specific articles when implementing formulas.
-   **Gotchas**: Document non-obvious behaviors or game mechanics quirks found in `pwpedia_data.jsonl`.

## 🚫 Common Pitfalls to Avoid

1.  ❌ **Hardcoding game values** → Reference PWPedia each time or use config.
2.  ❌ **Ignoring P&W API rate limits** → Implement proper caching.
3.  ❌ **Not validating user input** → Validate nation IDs, numbers, etc.
4.  ❌ **Inconsistent error messages** → Use consistent, helpful messages.
5.  ❌ **Forgetting to update docs** → Update README/docs when changing features.
6.  ❌ **Not checking `pwpedia_data.jsonl`** → Always verify game mechanics against the primary source.
7.  ❌ **Mixing concerns** → Do not put API calls inside Discord command functions; use a service layer.
8.  ❌ **Violating DRY** → Copy-pasting logic between the Bot and the Backend.

## New Feature Checklist

Before implementing a new feature:

-   [ ] **Fact-check in `pwpedia_data.jsonl`** - Verify all game mechanics.
-   [ ] **Identify data model** - What database entities are involved?
-   [ ] **Design API endpoint** - Check `pnwSchema.graphql` for external data availability.
-   [ ] **Write tests** - Unit tests for business logic.
-   [ ] **Handle errors** - What can go wrong?
-   [ ] **Document it** - Update README/docs.
-   [ ] **Code review** - Have someone verify PWPedia accuracy.
