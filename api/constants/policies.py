"""
Domestic Policies Constants

Only include policies that change revenue math in logic.revenue.
War policies are excluded (no revenue impact).
"""

DOMESTIC_POLICIES = {
    'Open Markets': {
        'name': 'Open Markets',
        'description': 'Gross income 1% better (1.5% with Government Support Agency, 1.75% with Bureau of Domestic Affairs).'
    },
    'Imperialism': {
        'name': 'Imperialism',
        'description': 'Military upkeep 5% better (7.5% with Government Support Agency, 8.75% with Bureau of Domestic Affairs).'
    },
}

