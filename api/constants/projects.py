"""
Projects Constants - revenue-relevant only.

Only include projects that actually change revenue math in logic.revenue
or alter infrastructure caps used in build generation.
"""

PROJECTS = {
    'ironw': {
        'name': 'Iron Works',
        'description': 'Steel Mills output +36% (0.75 -> 1.02 steel/turn) and coal/iron inputs rise in lockstep.'
    },
    'bauxitew': {
        'name': 'Bauxite Works',
        'description': 'Aluminum Refineries output +36% (0.75 -> 1.02 aluminum/turn) with matching bauxite consumption.'
    },
    'armss': {
        'name': 'Arms Stockpile',
        'description': 'Munitions Factories output +34% (1.5 -> 2.01 munitions/turn) and lead usage scales up accordingly.'
    },
    'egr': {
        'name': 'Emergency Gasoline Reserve',
        'description': 'Gasoline Refineries double their output (0.5 -> 1.0 gasoline/turn) while doubling oil input.'
    },
    'massirr': {
        'name': 'Mass Irrigation',
        'description': 'Farm yield improves from land/500 to land/400 per farm.'
    },
    'itc': {
        'name': 'International Trade Center',
        'description': 'Raises city commerce cap to 115% and grants +1 base commerce.'
    },
    'telecom_satellite': {
        'name': 'Telecommunications Satellite',
        'description': 'Adds +2 commerce to every city and lifts commerce cap to 125%.'
    },
    'recycling_initiative': {
        'name': 'Recycling Initiative',
        'description': 'Each Recycling Center removes 75 pollution (up from 70) and city cap rises from 3 to 4.'
    },
    'green_tech': {
        'name': 'Green Technologies',
        'description': 'Cuts manufacturing pollution by 25%, farm pollution by 50%, subways produce less pollution, and resource production upkeep drops 10%.'
    },
    'clinical_research_center': {
        'name': 'Clinical Research Center',
        'description': 'Hospitals reduce disease by 3.5% each (up from 2.5%) and hospital cap rises to 6.'
    },
    'specialized_police_training': {
        'name': 'Specialized Police Training',
        'description': 'Police stations cut crime by 3.5% each (up from 2.5%), station cap rises, and cities gain +4 base commerce.'
    },
    'uap': {
        'name': 'Uranium Enrichment Program',
        'description': 'Doubles Uranium Mine output (0.25 -> 0.5 uranium/turn per mine).'
    },
    'fallout_shelter': {
        'name': 'Fallout Shelter',
        'description': 'Caps radiation food penalty at 85% hit.'
    },
    'government_support_agency': {
        'name': 'Government Support Agency',
        'description': 'Boosts domestic policy effects by 50% (Open Markets 1% → 1.5%; Imperialism 5% → 7.5%).'
    },
    'bureau_of_domestic_affairs': {
        'name': 'Bureau of Domestic Affairs',
        'description': 'Boost domestic policy effects by 25% (Open Markets 1.5% → 1.75%; Imperialism 7.5% → 8.75%). Requires Government Support Agency.'
    },
}

PROJECT_FIELD_NAMES = list(PROJECTS.keys())
