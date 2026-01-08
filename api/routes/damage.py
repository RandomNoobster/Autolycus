"""
Damage API Routes

This module provides API endpoints for the damage calculator feature,
returning detailed attack damage analysis for war planning.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, request

from api.calculations.damage_calc import calculate_damage

logger = logging.getLogger(__name__)

damage_bp = Blueprint('damage', __name__, url_prefix='/api/damage')

# Attack types configuration
ATTACK_TYPES = [
    {'type': 'ground', 'maps': 3, 'label': 'Ground'},
    {'type': 'airvair', 'maps': 4, 'label': 'Air vs Air'},
    {'type': 'airvinfra', 'maps': 4, 'label': 'Air vs Infra'},
    {'type': 'airvsoldiers', 'maps': 4, 'label': 'Air vs Soldiers'},
    {'type': 'airvtanks', 'maps': 4, 'label': 'Air vs Tanks'},
    {'type': 'airvships', 'maps': 4, 'label': 'Air vs Ships'},
    {'type': 'navalvinfra', 'maps': 4, 'label': 'Naval vs Other'},
    {'type': 'navalvships', 'maps': 4, 'label': 'Naval vs Naval'},
    {'type': 'nuke', 'maps': 12, 'label': 'Nuke'},
    {'type': 'missile', 'maps': 8, 'label': 'Missile'},
]


@damage_bp.route('/', methods=['GET'])
def get_damage() -> tuple[Any, int]:
    """
    Get damage calculator results (public endpoint).
    
    Query parameters:
        - nation1: First nation ID
        - nation2: Second nation ID
    
    Returns:
        JSON response with:
        - nation1: First nation's data and name
        - nation2: Second nation's data and name
        - attacks: Detailed attack damage breakdown for each nation
        - chartData: Pre-formatted data for visualization charts
        - generatedAt: ISO timestamp of data generation
    """
    try:
        # Read nation1 and nation2 from query parameters
        nation1_id = request.args.get('nation1')
        nation2_id = request.args.get('nation2')

        if not nation1_id or not nation2_id:
            return jsonify({
                'error': 'Missing parameter',
                'message': 'Both nation1 and nation2 are required',
                'code': 'MISSING_NATIONS'
            }), 400

        # Convert to integers
        try:
            nation1_id = int(nation1_id)
            nation2_id = int(nation2_id)
        except ValueError:
            return jsonify({
                'error': 'Invalid parameter',
                'message': 'nation1 and nation2 must be integers',
                'code': 'INVALID_PARAMETER'
            }), 400

        # Run async calculation in event loop
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(
                calculate_damage(str(nation1_id), str(nation2_id))
            )
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        chart_data = _generate_chart_data(results)

        # Format response
        return jsonify({
            'nation1': {
                'id': results['nation1']['id'],
                'name': results['nation1']['nation_name'],
                'leader': results['nation1']['leader_name'],
                'soldiers': results['nation1']['soldiers'],
                'tanks': results['nation1']['tanks'],
                'aircraft': results['nation1']['aircraft'],
                'ships': results['nation1']['ships'],
                'missiles': results['nation1']['missiles'],
                'nukes': results['nation1']['nukes'],
                'vds': results['nation1'].get('vds', False),
                'irond': results['nation1'].get('irond', False),
                'groundWinRate': results.get('nation1_ground_win_rate', 0.5),
                'airWinRate': results.get('nation1_air_win_rate', 0.5),
                'navalWinRate': results.get('nation1_naval_win_rate', 0.5),
            },
            'nation2': {
                'id': results['nation2']['id'],
                'name': results['nation2']['nation_name'],
                'leader': results['nation2']['leader_name'],
                'soldiers': results['nation2']['soldiers'],
                'tanks': results['nation2']['tanks'],
                'aircraft': results['nation2']['aircraft'],
                'ships': results['nation2']['ships'],
                'missiles': results['nation2']['missiles'],
                'nukes': results['nation2']['nukes'],
                'vds': results['nation2'].get('vds', False),
                'irond': results['nation2'].get('irond', False),
                'groundWinRate': results.get('nation2_ground_win_rate', 0.5),
                'airWinRate': results.get('nation2_air_win_rate', 0.5),
                'navalWinRate': results.get('nation2_naval_win_rate', 0.5),
            },
            'warStatus': {
                'nation1Modifiers': results.get('nation1_append', ''),
                'nation2Modifiers': results.get('nation2_append', ''),
                'groundControl': results.get('gc', {}).get('nation_name') if results.get('gc') else None,
            },
            'chartData': chart_data,
            'generatedAt': datetime.now(timezone.utc).isoformat()
        }), 200

    except Exception as e:
        logger.error(f"Error in get_damage: {e}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred.',
            'code': 'INTERNAL_ERROR'
        }), 500


def _extract_nation_data(results: dict[str, Any], nation_key: str) -> dict[str, Any]:
    """
    Extract nation-specific data from results.
    
    Args:
        results: Raw results dict from cache.
        nation_key: Either 'nation1' or 'nation2'.
    
    Returns:
        Formatted nation info object.
    """
    nation_info = results.get(nation_key, {})
    
    return {
        'id': nation_info.get('id', 0),
        'nationName': nation_info.get('nation_name', 'Unknown'),
        'vds': nation_info.get('vds', False),  # Vital Defense System
        'irond': nation_info.get('irond', False),  # Iron Dome
        'groundWinRate': results.get(f'{nation_key}_ground_win_rate', 0.5),
        'airWinRate': results.get(f'{nation_key}_air_win_rate', 0.5),
        'navalWinRate': results.get(f'{nation_key}_naval_win_rate', 0.5),
    }


def _build_attack_analysis(
    results: dict[str, Any], 
    attacker: str, 
    defender: str
) -> dict[str, Any]:
    """
    Build comprehensive attack analysis for an attacker.
    
    Args:
        results: Raw results dict from cache.
        attacker: Key for attacking nation ('nation1' or 'nation2').
        defender: Key for defending nation.
    
    Returns:
        Object containing per-resistance, per-MAP, and total stats.
    """
    attacker_info = results.get(attacker, {})
    vds = attacker_info.get('vds', False)
    irond = attacker_info.get('irond', False)
    
    per_resistance = []
    per_map = []
    total_stats = []
    
    for attack_config in ATTACK_TYPES:
        attack_type = attack_config['type']
        maps = attack_config['maps']
        label = attack_config['label']
        
        # Calculate resistance based on attack type and win rates
        resistance = _calculate_resistance(
            attack_type, 
            results.get(f'{attacker}_ground_win_rate', 0.5),
            results.get(f'{attacker}_air_win_rate', 0.5),
            results.get(f'{attacker}_naval_win_rate', 0.5),
            vds,
            irond
        )
        
        # Base values from results
        net_damage = results.get(f'{attacker}_{attack_type}_net', 0)
        attacker_total = results.get(f'{attacker}_{attack_type}_{attacker}_total', 0)
        defender_total = results.get(f'{attacker}_{attack_type}_{defender}_total', 0)
        attacker_gas = results.get(f'{attacker}_{attack_type}_{attacker}_gas', 0)
        attacker_mun = results.get(f'{attacker}_{attack_type}_{attacker}_mun', 0)
        attacker_steel = results.get(f'{attacker}_{attack_type}_{attacker}_steel', 0)
        attacker_alum = results.get(f'{attacker}_{attack_type}_{attacker}_alum', 0)
        attacker_money = results.get(f'{attacker}_{attack_type}_{attacker}_money', 0)
        infra_destroyed = results.get(f'{attacker}_{attack_type}_{defender}_lost_infra_avg_value', 0)
        
        # Per resistance stats (for when you're winning)
        if resistance > 0:
            per_resistance.append({
                'attackType': attack_type,
                'label': label,
                'netDamage': round(net_damage / resistance),
                'damageDealt': round(defender_total / resistance),
                'damageReceived': round(attacker_total / resistance),
                'gasConsumed': round(attacker_gas / resistance),
                'munConsumed': round(attacker_mun / resistance),
                'steelConsumed': round(attacker_steel / resistance),
                'alumConsumed': round(attacker_alum / resistance),
                'moneyUsed': round(attacker_money / resistance),
                'infraDestroyed': round(infra_destroyed / resistance),
            })
        else:
            per_resistance.append({
                'attackType': attack_type,
                'label': label,
                'netDamage': 0,
                'damageDealt': 0,
                'damageReceived': 0,
                'gasConsumed': 0,
                'munConsumed': 0,
                'steelConsumed': 0,
                'alumConsumed': 0,
                'moneyUsed': 0,
                'infraDestroyed': 0,
            })
        
        # Per MAP stats (for when you're losing)
        per_map.append({
            'attackType': attack_type,
            'label': label,
            'netDamage': round(net_damage / maps),
            'damageDealt': round(defender_total / maps),
            'damageReceived': round(attacker_total / maps),
            'gasConsumed': round(attacker_gas / maps),
            'munConsumed': round(attacker_mun / maps),
            'steelConsumed': round(attacker_steel / maps),
            'alumConsumed': round(attacker_alum / maps),
            'moneyUsed': round(attacker_money / maps),
            'infraDestroyed': round(infra_destroyed / maps),
        })
        
        # Total stats (reference values)
        total_stats.append({
            'attackType': attack_type,
            'label': label,
            'netDamage': round(net_damage),
            'damageDealt': round(defender_total),
            'damageReceived': round(attacker_total),
            'gasConsumed': round(attacker_gas),
            'munConsumed': round(attacker_mun),
            'steelConsumed': round(attacker_steel),
            'alumConsumed': round(attacker_alum),
            'moneyUsed': round(attacker_money),
            'infraDestroyed': round(infra_destroyed),
        })
    
    return {
        'perResistance': per_resistance,
        'perMap': per_map,
        'totalStats': total_stats,
    }


def _calculate_resistance(
    attack_type: str,
    ground_win_rate: float,
    air_win_rate: float,
    naval_win_rate: float,
    vds: bool,
    irond: bool
) -> float:
    """
    Calculate resistance dealt per attack based on type and win rates.
    
    Args:
        attack_type: The type of attack being performed.
        ground_win_rate: Probability of winning ground battles.
        air_win_rate: Probability of winning air battles.
        naval_win_rate: Probability of winning naval battles.
        vds: Whether defender has Vital Defense System.
        irond: Whether defender has Iron Dome.
    
    Returns:
        Expected resistance dealt per attack.
    """
    if attack_type == 'ground':
        return 10 * ground_win_rate
    elif attack_type.startswith('air'):
        return 12 * air_win_rate
    elif attack_type.startswith('naval'):
        return 14 * naval_win_rate
    elif attack_type == 'nuke':
        return 25 * (1 - 0.2 * int(vds))
    elif attack_type == 'missile':
        return 18 * (1 - 0.5 * int(irond))
    return 0


def _generate_chart_data(results: dict[str, Any]) -> dict[str, Any]:
    """
    Generate pre-formatted data for frontend charts.
    
    Args:
        results: Raw results dict from cache.
    
    Returns:
        Chart-ready data structure for Mantine Charts.
    """
    nation1_name = results.get('nation1', {}).get('nation_name', 'Nation 1')
    nation2_name = results.get('nation2', {}).get('nation_name', 'Nation 2')
    
    # Net damage comparison bar chart data
    net_damage_chart = []
    for attack_config in ATTACK_TYPES:
        attack_type = attack_config['type']
        label = attack_config['label']
        
        nation1_net = results.get(f'nation1_{attack_type}_net', 0)
        nation2_net = results.get(f'nation2_{attack_type}_net', 0)
        
        net_damage_chart.append({
            'attackType': label,
            nation1_name: round(nation1_net),
            nation2_name: round(nation2_net),
        })
    
    return {
        'netDamageComparison': {
            'data': net_damage_chart,
            'series': [
                {'name': nation1_name, 'color': 'blue.6'},
                {'name': nation2_name, 'color': 'red.6'},
            ],
        },
    }
