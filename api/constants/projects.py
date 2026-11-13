"""
Projects Constants - revenue-relevant only.

Only include projects that actually change revenue math in logic.revenue
or alter infrastructure caps used in build generation.

Effects follow .ctx/projects_canon.md, the confirmed project descriptions.
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
        'description': 'Munitions Factories output +20% (1.5 -> 1.8 munitions/turn); lead usage does not increase.'
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
        'description': 'Raises city commerce cap to 115%, grants +1 base commerce, and raises bank cap from 5 to 6.'
    },
    'telecom_satellite': {
        'name': 'Telecommunications Satellite',
        'description': 'Adds +2 commerce to every city, lifts commerce cap to 125%, and raises mall cap from 4 to 5.'
    },
    'recycling_initiative': {
        'name': 'Recycling Initiative',
        'description': 'Each Recycling Center removes 75 pollution (up from 70) and city cap rises from 3 to 4.'
    },
    'green_tech': {
        'name': 'Green Technologies',
        'description': 'Cuts manufacturing pollution by 25% and farm pollution by 50%, subways remove 25 more pollution each, and resource production upkeep drops 10%.'
    },
    'clinical_research_center': {
        'name': 'Clinical Research Center',
        'description': 'Hospitals reduce disease by 3.5% each (up from 2.5%) and hospital cap rises to 6.'
    },
    'specialized_police_training': {
        'name': 'Specialized Police Training',
        'description': 'Police stations cut crime by 3.5% each (up from 2.5%) and cities gain +4% commerce.'
    },
    'uap': {
        'name': 'Uranium Enrichment Program',
        'description': 'Doubles Uranium Mine output (0.25 -> 0.5 uranium/turn per mine).'
    },
    'fallout_shelter': {
        'name': 'Fallout Shelter',
        'description': 'Reduces food lost to radiation by 15%.'
    },
    'government_support_agency': {
        'name': 'Government Support Agency',
        'description': 'Boosts domestic policy effects by 50% (Open Markets 1% → 1.5%; Imperialism 5% → 7.5%).'
    },
    'bureau_of_domestic_affairs': {
        'name': 'Bureau of Domestic Affairs',
        'description': 'Boosts domestic policy effects by a further 25% (Open Markets 1.5% → 1.75%; Imperialism 7.5% → 8.75%) and removes the policy change timer. Requires Government Support Agency.'
    },
}

PROJECT_FIELD_NAMES = list(PROJECTS.keys())
