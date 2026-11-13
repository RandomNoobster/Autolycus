# utils.py
MILITARIZATION_CHECKER = {"nations": [{"cities": ["barracks", "factory", "airforcebase", "drydock"]}, "soldiers", "tanks", "aircraft", "ships", "propaganda_bureau", "population"]}
PRICES = {"tradeprices": ["coal", "oil", "uranium", "iron", "bauxite", "lead", "gasoline", "munitions", "steel", "aluminum", "food", "credits"]}


# backgraound.py
_WAR_ATTACK_LOOT_FIELDS = [
    "type",
    "loot_info",
    "victor",
    "moneystolen",
    "money_looted",
    "coal_looted",
    "oil_looted",
    "uranium_looted",
    "iron_looted",
    "bauxite_looted",
    "lead_looted",
    "gasoline_looted",
    "munitions_looted",
    "steel_looted",
    "aluminum_looted",
    "food_looted",
]


# config.py


# general.py
WHO = (MILITARIZATION_CHECKER, {"nations": ["id", "nation_name", "discord", "pirate_economy", "advanced_pirate_economy", "leader_name", "num_cities", "cia", "spy_satellite", "warpolicy", "population", "dompolicy", "flag", "vmode", "color", "beige_turns", "last_active", "soldiers", "tanks", "aircraft", "ships", "nukes", "missiles", "mlp", "nrf", "vds", "irond", {"wars": ["attid", "turnsleft"]}, "score", "alliance_position", "alliance_seniority", {"alliance": ["name", "id", "score", "color", {"nations": ["alliance_position"]}]}]})
REVENUE = {"nations": ["nation_name", "leader_name", "id", "date", "continent", "color", "warpolicy", "resource_production_center", "clinical_research_center", "specialized_police_training_program", "government_support_agency", "bureau_of_domestic_affairs", "recycling_initiative", "cia", "fallout_shelter", "dompolicy", "alliance_id", {"alliance": ["name", "id"]}, "num_cities", "spies", "soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", {"wars": ["date", "turnsleft"]}, "ironw", "bauxitew", "armss", "egr", "massirr", "itc", "recycling_initiative", "telecom_satellite", "green_tech", "clinical_research_center", "specialized_police_training", "uap", {"military_research": ["ground_cost", "ground_capacity", "air_cost", "air_capacity", "naval_cost", "naval_capacity"]}, {"cities": ["id", "date", "powered", "infrastructure", "land", "oilpower", "windpower", "coalpower", "nuclearpower", "coalmine", "oilwell", "uramine", "barracks", "farm", "policestation", "hospital", "recyclingcenter", "subway", "supermarket", "bank", "mall", "stadium", "leadmine", "ironmine", "bauxitemine", "gasrefinery", "aluminumrefinery", "steelmill", "munitionsfactory", "factory", "airforcebase", "drydock"]}]}
VERIFY = {"nations": ["id", "nation_name", "leader_name", "discord"]}


# military.py
WINRATE_CALC = {"nations": ["soldiers", "tanks", "aircraft", "ships"]}
BATTLE_CALC = (WINRATE_CALC, {"nations": ["nation_name", "population", "warpolicy", "id", "flag", "soldiers", "tanks", "aircraft", "ships", "advanced_pirate_economy", "pirate_economy", "irond", "vds", "fallout_shelter", "guiding_satellite", "military_salvage", {"cities": ["infrastructure", "land"]}, {"wars": ["groundcontrol", "airsuperiority", "navalblockade", "attpeace", "defpeace", "attid", "defid", "att_fortify", "def_fortify", "turnsleft", "war_type"]}]})
NUKETARGETS = (BATTLE_CALC, {'nations': ['vacation_mode_turns', 'score', 'alliance_position', 'color', {'cities': ['infrastructure']}, {"wars": ['attid', 'defid']}, {"alliance": ['name', 'id']}]})
WAR_STATUS_DEPENDENCY = ["nation_name", "leader_name", "alliance_id", {"alliance": ["name"]}, "id", "pirate_economy", "advanced_pirate_economy", "score", "last_active", "beigeturns", "vmode", "num_cities", "color", "nukes", "missiles"]
WAR_STATUS = (MILITARIZATION_CHECKER, BATTLE_CALC, {"nations": WAR_STATUS_DEPENDENCY + [{"wars": [{"defender": WAR_STATUS_DEPENDENCY + MILITARIZATION_CHECKER["nations"] + [{"wars": ["attid", "defid", "turnsleft"]}]}, {"attacker": WAR_STATUS_DEPENDENCY + MILITARIZATION_CHECKER["nations"] + [{"wars": ["attid", "defid", "turnsleft"]}]}, "date", "id", "attid", "defid", "winner", "att_resistance", "def_resistance", "attpoints", "defpoints", "attpeace", "defpeace", "war_type", "groundcontrol", "airsuperiority", "navalblockade", "turnsleft", "att_fortify", "def_fortify"]}]})


# scanner.py
BACKGROUND_SCANNER = {"nations": ["id", "discord", "leader_name", "nation_name", "warpolicy", "vacation_mode_turns", "flag", "last_active", "alliance_position_id", "continent", "fallout_shelter", "guiding_satellite", "military_salvage", "pirate_economy", "advanced_pirate_economy", "warpolicy", "resource_production_center", "government_support_agency", "bureau_of_domestic_affairs", "dompolicy", "vds", "irond", "population", "alliance_id", "beige_turns", "score", "color", "spies", "soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", {"bounties": ["amount", "type"]}, {"treasures": ["name"]}, {"alliance": ["name", "id", "color", "flag"]}, {"wars": ["date", "end_date", "winner", "att_money_looted", "def_money_looted", {"attacker": ["war_policy", "advanced_pirate_economy"]}, {"defender": ["war_policy", "advanced_pirate_economy"]}, "war_type", "defid", "turnsleft", {"attacks": list(_WAR_ATTACK_LOOT_FIELDS)}]}, "alliance_position", "num_cities", "ironw", "bauxitew", "armss", "egr", "massirr", "itc", "recycling_initiative", "telecom_satellite", "green_tech", "clinical_research_center", "specialized_police_training", "uap", {"military_research": ['ground_cost', 'ground_capacity', 'air_cost', 'air_capacity', 'naval_cost', 'naval_capacity']}, {"cities": ["date", "powered", "infrastructure", "land", "oilpower", "windpower", "coalpower", "nuclearpower", "coalmine", "oilwell", "uramine", "barracks", "farm", "policestation", "hospital", "recyclingcenter", "subway", "supermarket", "bank", "mall", "stadium", "leadmine", "ironmine", "bauxitemine", "gasrefinery", "aluminumrefinery", "steelmill", "munitionsfactory", "factory", "airforcebase", "drydock"]}]}

# Alliance scanning
ALLIANCE_SCANNER = {
	"alliances": [
		"id",
		"name",
		"acronym",
		"color",
		"score",
		"average_score",
		"accept_members",
		"flag",
		"discord_link",
		"forum_link",
		"wiki_link",
		"date",
	]
}
