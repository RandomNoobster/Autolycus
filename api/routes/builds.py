"""
Builds API Routes

This module provides API endpoints for the city builds feature,
returning build templates and resource production data.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, request

from api.constants import DOMESTIC_POLICIES, PROJECTS
from api.pnw import UPSTREAM_TIMEOUT_RESPONSE, UPSTREAM_TIMEOUT_SECONDS, call_pnw as _call_pnw
from infra.async_bridge import run_sync
from logic.builds import (
    BuildInputError,
    NationNotFoundError,
    calculate_builds,
    generate_build_template,
    normalize_continent_code,
)

logger = logging.getLogger(__name__)

builds_bp = Blueprint('builds', __name__, url_prefix='/api/builds')

# Canonical project keys used across API validation + frontend picker.
CANONICAL_PROJECT_FIELDS = list(PROJECTS.keys())

# P&W field aliases normalized into canonical keys used by this app.
# NOTE: We keep internal canonical names aligned with existing logic constants.
PROJECT_FIELD_ALIASES = {
    'telecommunications_satellite': 'telecom_satellite',
    'green_technologies': 'green_tech',
    'specialized_police_training_program': 'specialized_police_training',
}

# Source field -> canonical key mapping for nation profile autofill extraction.
PROJECT_SOURCE_TO_CANONICAL = {
    **{key: key for key in CANONICAL_PROJECT_FIELDS},
    **PROJECT_FIELD_ALIASES,
}


@builds_bp.route('/nation/<int:nation_id>', methods=['GET'])
def get_nation_profile(nation_id: int) -> tuple[Any, int]:
    """
    Get nation profile data for build configuration import.
    
    Fetches nation infrastructure, land, continent, military buildings,
    projects, and policies to auto-fill the build calculator form.
    
    Path parameters:
        - nation_id: The Politics & War nation ID
    
    Returns:
        JSON response with:
        - id: Nation ID
        - name: Nation name
        - leader: Leader name
        - continent: Continent code (na, sa, eu, af, as, au, an)
        - cities: Array of city data with infrastructure, land, and military buildings
        - projects: Array of active project names
        - policies: Object with warpolicy and dompolicy
        - generatedAt: ISO timestamp
    """
    try:
        nation_data = run_sync(_fetch_nation_profile(str(nation_id)), timeout=UPSTREAM_TIMEOUT_SECONDS)

        return jsonify(nation_data), 200

    except ValueError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e),
            'code': 'NATION_NOT_FOUND'
        }), 404
    except TimeoutError:
        return jsonify(UPSTREAM_TIMEOUT_RESPONSE), 504
    except Exception as e:
        logger.error(f"Error in get_nation_profile: {e}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred.',
            'code': 'INTERNAL_ERROR'
        }), 500


@builds_bp.route('/game-data', methods=['GET'])
def get_game_data() -> tuple[Any, int]:
    """
    Get projects and policies data for build configuration.
    
    Returns:
        JSON response with:
        - projects: Object mapping project field names to their display names and descriptions
        - domesticPolicies: Object mapping domestic policy names to descriptions
    
    Note:
        Only revenue-relevant projects and policies are included per analysis of 
        calculate_nation_modifiers in logic.revenue
    """
    return jsonify({
        'projects': PROJECTS,
        'domesticPolicies': DOMESTIC_POLICIES
    }), 200


@builds_bp.route('/', methods=['GET'])
def get_builds() -> tuple[Any, int]:
    """
    Get city build templates (public endpoint).
    
    Query parameters:
        - nation_id: Nation ID to calculate builds for (optional for manual config)
        - infra: Infrastructure level (default: nation's average; required without nation_id)
        - land: Land amount (default: nation's average; required without nation_id)
        - mmr: Military requirement (default: 0/0/0/0); values >0 match exactly
        - continent: Continent code (na, sa, eu, af, as, au, an) - overrides nation's continent
        - use_live_prices: Boolean (true/false) - use current market prices vs historical average
        - include_military_upkeep: Boolean (true/false) - include max military unit upkeep costs
        - projects: Comma-separated project keys. Present (even empty) overrides nation projects.
        - domestic_policy: Policy name. Present (even empty) overrides nation domestic policy.
    
    Returns:
        JSON response with:
        - builds: Object mapping resource types to their optimal builds
        - resources: List of resource types available
        - land: Current land value used in calculations
        - uniqueBuilds: Array of unique build configurations
        - generatedAt: ISO timestamp of data generation
    """
    try:
        # Read nation_id from query parameters (optional for fully manual configuration)
        nation_id_raw = request.args.get('nation_id')
        nation_id: int | None = None

        if nation_id_raw not in (None, ''):
            try:
                nation_id = int(nation_id_raw)
            except ValueError:
                return jsonify({
                    'error': 'Invalid parameter',
                    'message': 'nation_id must be an integer',
                    'code': 'INVALID_PARAMETER'
                }), 400
            if nation_id <= 0:
                nation_id = None
        
        # Get optional parameters
        infra = request.args.get('infra')
        land = request.args.get('land')
        mmr = request.args.get('mmr', '0/0/0/0')
        continent = request.args.get('continent')  # Override continent
        use_live_prices = request.args.get('use_live_prices', 'true').lower() == 'true'
        include_military_upkeep = request.args.get('include_military_upkeep', 'false').lower() == 'true'
        disable_population_income = request.args.get('disable_population_income', 'false').lower() == 'true'
        military_upkeep_mode = request.args.get('military_upkeep_mode', 'peace').lower()
        valid_upkeep_modes = {'peace', 'war'}
        if military_upkeep_mode not in valid_upkeep_modes:
            return jsonify({
                'error': 'Invalid parameter',
                'message': 'military_upkeep_mode must be one of: peace, war',
                'code': 'INVALID_PARAMETER'
            }), 400

        # Optional: override projects/domestic policy for manual configuration.
        # Presence of the query key (even when empty) means "use form value";
        # absence means "keep the nation's existing value".
        project_overrides: list[str] | None
        if 'projects' in request.args:
            projects_param = request.args.get('projects', '')
            project_overrides = [p for p in projects_param.split(',') if p]
            project_overrides = [p for p in project_overrides if p in PROJECTS]
        else:
            project_overrides = None

        domestic_policy_override: str | None
        if 'domestic_policy' in request.args:
            domestic_policy_override = request.args.get('domestic_policy') or ''
            if domestic_policy_override and domestic_policy_override not in DOMESTIC_POLICIES:
                domestic_policy_override = ''
        else:
            domestic_policy_override = None
        
        # Convert infra and land if provided
        infra_level = None
        land_amount = None
        continent_override = None
        
        if infra:
            try:
                infra_level = int(infra)
            except ValueError:
                infra_level = None
            if infra_level is None or infra_level < 50:
                return jsonify({
                    'error': 'Invalid parameter',
                    'message': 'infra must be an integer of at least 50',
                    'code': 'INVALID_PARAMETER'
                }), 400

        if land:
            try:
                land_amount = int(land)
            except ValueError:
                land_amount = None
            # Population density divides by land, so it has to be positive.
            if land_amount is None or land_amount <= 0:
                return jsonify({
                    'error': 'Invalid parameter',
                    'message': 'land must be a positive integer',
                    'code': 'INVALID_PARAMETER'
                }), 400

        if nation_id is None and (infra_level is None or land_amount is None):
            return jsonify({
                'error': 'Missing parameter',
                'message': 'nation_id is required unless both infra and land are provided',
                'code': 'MISSING_PARAMETER'
            }), 400
        
        if continent:
            # Codes (na, sa, ...) and full names (North America) are both accepted.
            continent_override = normalize_continent_code(continent)
            if continent_override is None:
                return jsonify({
                    'error': 'Invalid parameter',
                    'message': 'continent must be one of: na, sa, eu, af, as, au, an',
                    'code': 'INVALID_PARAMETER'
                }), 400
        
        results = run_sync(
            calculate_builds(
                call_pnw=_call_pnw,
                nation_id=str(nation_id) if nation_id is not None else None,
                infra=infra_level,
                land=land_amount,
                mmr=mmr,
                continent_override=continent_override,
                use_live_prices=use_live_prices,
                include_military_upkeep=include_military_upkeep,
                projects_override=project_overrides,
                domestic_policy_override=domestic_policy_override,
                military_upkeep_mode=military_upkeep_mode,
                disable_population_income=disable_population_income,
            ),
            timeout=UPSTREAM_TIMEOUT_SECONDS,
        )

        # Transform builds to API shape expected by frontend
        raw_builds = results.get('builds', {})
        transformed_builds = {k: _transform_build(v) for k, v in raw_builds.items()}

        raw_unique = results.get('uniqueBuilds', [])
        transformed_unique = [_transform_build(b) for b in raw_unique]

        # Format response
        return jsonify({
            'nation': results.get('nation'),
            'builds': transformed_builds,
            'resources': results.get('resources', []),
            'land': results.get('land'),
            'infrastructure': results.get('infrastructure'),
            'uniqueBuilds': transformed_unique,
            'totalUniqueBuilds': results.get('totalUniqueBuilds', len(transformed_unique)),
            'displayedUniqueBuilds': results.get('displayedUniqueBuilds', len(transformed_unique)),
            'prices': results.get('prices', {}),
            'radiation': results.get('radiation'),
            'foodModifiers': results.get('foodModifiers'),
            'generatedAt': datetime.now(timezone.utc).isoformat()
        }), 200

    except NationNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e),
            'code': 'NATION_NOT_FOUND'
        }), 404
    except BuildInputError as e:
        # Inputs calculate_builds can't use (MMR format, infra with no matching
        # builds); its messages are written for users.
        return jsonify({
            'error': 'Invalid parameter',
            'message': str(e),
            'code': 'INVALID_PARAMETER'
        }), 400
    except TimeoutError:
        return jsonify(UPSTREAM_TIMEOUT_RESPONSE), 504
    except Exception as e:
        logger.error(f"Error in get_builds: {e}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred.',
            'code': 'INTERNAL_ERROR'
        }), 500


def _transform_build(build_data: dict[str, Any]) -> dict[str, Any]:
    """
    Transform a build dict into the API response format.
    
    Args:
        build_data: Raw build data from the cache file.
    
    Returns:
        Formatted build object for the API response.
    """
    if not build_data:
        return {}
    
    # Same bulk-import template the Discord bot posts.
    template = generate_build_template(build_data)
    
    return {
        # Identification
        'template': template,
        
        # Infrastructure
        'infrastructure': build_data.get('infrastructure', 0),
        'impTotal': int(build_data.get('infrastructure', 0) // 50),
        
        # Power plants
        'coalpower': build_data.get('coalpower', 0),
        'oilpower': build_data.get('oilpower', 0),
        'windpower': build_data.get('windpower', 0),
        'nuclearpower': build_data.get('nuclearpower', 0),
        
        # Raw resource extraction
        'coalmine': build_data.get('coalmine', 0),
        'oilwell': build_data.get('oilwell', 0),
        'uramine': build_data.get('uramine', 0),
        'leadmine': build_data.get('leadmine', 0),
        'ironmine': build_data.get('ironmine', 0),
        'bauxitemine': build_data.get('bauxitemine', 0),
        'farm': build_data.get('farm', 0),
        
        # Manufacturing
        'gasrefinery': build_data.get('gasrefinery', 0),
        'aluminumrefinery': build_data.get('aluminumrefinery', 0),
        'steelmill': build_data.get('steelmill', 0),
        'munitionsfactory': build_data.get('munitionsfactory', 0),
        
        # Civil improvements
        'policestation': build_data.get('policestation', 0),
        'hospital': build_data.get('hospital', 0),
        'recyclingcenter': build_data.get('recyclingcenter', 0),
        'subway': build_data.get('subway', 0),
        'supermarket': build_data.get('supermarket', 0),
        'bank': build_data.get('bank', 0),
        'mall': build_data.get('mall', 0),
        'stadium': build_data.get('stadium', 0),
        
        # Military
        'barracks': build_data.get('barracks', 0),
        'factory': build_data.get('factory', 0),
        'airforcebase': build_data.get('airforcebase', 0),
        'drydock': build_data.get('drydock', 0),
        
        # Stats
        'diseaseRate': round(build_data.get('disease_rate', 0), 1),
        'realDiseaseRate': build_data.get('real_disease_rate', 0),
        'pollution': round(build_data.get('pollution', 0)),
        'realPollution': build_data.get('real_pollution', 0),
        'crimeRate': round(build_data.get('crime_rate', 0), 1),
        'realCrimeRate': build_data.get('real_crime_rate', 0),
        'commerce': round(build_data.get('commerce', 0)),
        'realCommerce': build_data.get('real_commerce', 0),
        
        # Military Readiness Rating (MMR)
        'mmr': f"{build_data.get('barracks', 0)}/{build_data.get('factory', 0)}/{build_data.get('airforcebase', 0)}/{build_data.get('drydock', 0)}",
        
        # Income
        'netIncome': round(build_data.get('net income', 0)),
        'netIncomeReal': round(build_data.get('net income real', build_data.get('net income', 0))),
        'netCash': round(build_data.get('net_cash_num', 0)),
        'netCashReal': round(build_data.get('net_cash_num_real', build_data.get('net_cash_num', 0))),
        'unitUpkeep': build_data.get('unit_upkeep'),
        
        # Resource production
        'aluminum': round(build_data.get('aluminum', 0), 1),
        'bauxite': round(build_data.get('bauxite', 0), 1),
        'coal': round(build_data.get('coal', 0), 1),
        'food': round(build_data.get('food', 0), 1),
        'gasoline': round(build_data.get('gasoline', 0), 1),
        'iron': round(build_data.get('iron', 0), 1),
        'lead': round(build_data.get('lead', 0), 1),
        'munitions': round(build_data.get('munitions', 0), 1),
        'oil': round(build_data.get('oil', 0), 1),
        'steel': round(build_data.get('steel', 0), 1),
        'uranium': round(build_data.get('uranium', 0), 1),

        # Population snapshot for upkeep calcs
        'population': round(build_data.get('population', 0)),
    }


async def _fetch_nation_profile(nation_id: str) -> dict[str, Any]:
    """
    Fetch nation profile data from P&W API for build configuration.
    
    Args:
        nation_id: The nation ID to fetch
        
    Returns:
        Dictionary containing nation profile data
        
    Raises:
        ValueError: If nation is not found
    """
    # GraphQL query for nation profile
    project_fields_for_query = sorted(PROJECT_SOURCE_TO_CANONICAL.keys())
    project_fields_block = "\n                ".join(project_fields_for_query)

    query = f"""{{
        nations(first:1 id:{nation_id}){{
            data{{
                id
                nation_name
                leader_name
                continent
                warpolicy
                dompolicy
                {project_fields_block}
                cities{{
                    id
                    infrastructure
                    land
                    barracks
                    factory
                    airforcebase
                    drydock
                }}
            }}
        }}
    }}"""
    
    # Fetch nation data from P&W API
    response = await _call_pnw(query)
    nation_data = ((response.get('data') or {}).get('nations') or {}).get('data') or []
    
    if len(nation_data) == 0:
        raise ValueError(f"Nation {nation_id} not found")
    
    nation = nation_data[0]
    
    # Extract active projects as canonical keys so frontend values always match
    # game-data options and backend validation.
    active_projects: set[str] = set()
    for source_field, canonical_key in PROJECT_SOURCE_TO_CANONICAL.items():
        if nation.get(source_field) is True and canonical_key in PROJECTS:
            active_projects.add(canonical_key)
    projects = [key for key in CANONICAL_PROJECT_FIELDS if key in active_projects]
    
    # Extract policies
    policies = {
        'warpolicy': nation.get('warpolicy', ''),
        'dompolicy': nation.get('dompolicy', '')
    }
    
    # Extract city data
    cities = []
    for city in nation.get('cities', []):
        cities.append({
            'id': city.get('id'),
            'infrastructure': city.get('infrastructure', 0),
            'land': city.get('land', 0),
            'barracks': city.get('barracks', 0),
            'factory': city.get('factory', 0),
            'airforcebase': city.get('airforcebase', 0),
            'drydock': city.get('drydock', 0),
        })
    
    return {
        'id': nation.get('id'),
        'name': nation.get('nation_name', ''),
        'leader': nation.get('leader_name', ''),
        # P&W reports names like "South America" or "SOUTH_AMERICA".
        'continent': normalize_continent_code(str(nation.get('continent') or '')) or 'na',
        'cities': cities,
        'projects': projects,
        'policies': policies,
        'generatedAt': datetime.now(timezone.utc).isoformat()
    }
