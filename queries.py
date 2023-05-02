NO_TYPE = str(None)

# utils.py
MILITARIZATION_CHECKER = {"nations": [{"cities": ["barracks", "factory", "airforcebase", "drydock"]}, "soldiers", "tanks", "aircraft", "ships", "propaganda_bureau", "population"]}
INFRA_COST = {"nations": ["domestic_policy", "advanced_engineering_corps", "center_for_civil_engineering", "government_support_agency"]}
LAND_COST = {"nations": ["domestic_policy", "advanced_engineering_corps", "arable_land_agency", "government_support_agency"]}
CITY_COST = {"nations": ["domestic_policy", "urban_planning", "advanced_urban_planning", "metropolitan_planning", "government_support_agency"]}
PRICES = {"tradeprices": ["coal", "oil", "uranium", "iron", "bauxite", "lead", "gasoline", "munitions", "steel", "aluminum", "food", "credits"]}


# backgraound.py
WARS_SCANNER = {"wars": ["id", "war_type", "att_peace", "def_peace", "turnsleft", "reason", "date", "att_id", "def_id", "att_alliance_id", "def_alliance_id", {"attacker": ["nation_name", "leader_name", {"alliance": ["name"]}, "alliance_id", "id", "num_cities"]}, {"defender": ["nation_name", "leader_name", {"alliance": ["name"]}, "alliance_id", "id", "num_cities"]}, {"attacks": ["type", "id", "date", "att_id", "def_id", "loot_info", "victor", "moneystolen", "success", "cityid", "resistance_eliminated", "infra_destroyed", "infra_destroyed_value", "improvements_lost", "aircraft_killed_by_tanks", "attcas1", "attcas2", "defcas1", "defcas2"]}]}


# config.py


# general.py
WHO = (MILITARIZATION_CHECKER, {"nations": ["id", "nation_name", "discord", "leader_name", "num_cities", "cia", "spy_satellite", "warpolicy", "population", "dompolicy", "flag", "vmode", "color", "beige_turns", "last_active", "soldiers", "tanks", "aircraft", "ships", "nukes", "missiles", "mlp", "nrf", "vds", "irond", {"wars": ["attid", "turnsleft"]}, "score", "alliance_position", "alliance_seniority", {"alliance": ["name", "id", "score", "color", {"nations": ["alliance_position"]}]}]})
REVENUE = {"nations": ["nation_name", "leader_name", "id", "date", "continent", "color", "warpolicy", "resource_production_center", "clinical_research_center", "specialized_police_training_program", "recycling_initiative", "cia", "fallout_shelter", "dompolicy", "alliance_id", {"alliance": ["name", "id"]}, "num_cities", "soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", {"wars": ["date", "turnsleft"]}, "ironw", "bauxitew", "armss", "egr", "massirr", "itc", "recycling_initiative", "telecom_satellite", "green_tech", "clinical_research_center", "specialized_police_training", "uap", {"cities": ["id", "date", "powered", "infrastructure", "land", "oilpower", "windpower", "coalpower", "nuclearpower", "coalmine", "oilwell", "uramine", "barracks", "farm", "policestation", "hospital", "recyclingcenter", "subway", "supermarket", "bank", "mall", "stadium", "leadmine", "ironmine", "bauxitemine", "gasrefinery", "aluminumrefinery", "steelmill", "munitionsfactory", "factory", "airforcebase", "drydock"]}]}
VERIFY = {"nations": ["id", "nation_name", "leader_name", "discord"]}
REQUEST = {NO_TYPE: [{"me": ["key", {"nation": ["nation_name", "id", {"alliance": ["name", "id", "coal", "oil", "uranium", "iron", "bauxite", "lead", "gasoline", "money", "munitions", "steel", "aluminum", "food"]}]}]}]}


# military.py
WINRATE_CALC = {"nations": ["soldiers", "tanks", "aircraft", "ships"]}
BATTLE_CALC = (WINRATE_CALC, {"nations": ["nation_name", "population", "warpolicy", "id", "soldiers", "tanks", "aircraft", "ships", "irond", "vds", "fallout_shelter", "military_salvage", {"cities": ["infrastructure", "land"]}, {"wars": ["groundcontrol", "airsuperiority", "navalblockade", "attpeace", "defpeace", "attid", "defid", "att_fortify", "def_fortify", "turnsleft", "war_type"]}]})
REMINDERS = {"nations": ["id", "nation_name", "vacation_mode_turns", "beige_turns"]}
NUKETARGETS = (BATTLE_CALC, {'nations': ['vacation_mode_turns', 'score', 'alliance_position', 'color', {'cities': ['infrastructure']}, {"wars": ['att_id', 'def_id']}, {"alliance": ['name', 'id']}]})
WAR_STATUS_DEPENDENCY = ["nation_name", "leader_name", "alliance_id", {"alliance": ["name"]}, "id", "pirate_economy", "score", "last_active", "beigeturns", "vmode", "num_cities", "color", "nukes", "missiles"]
WAR_STATUS = (MILITARIZATION_CHECKER, BATTLE_CALC, {"nations": WAR_STATUS_DEPENDENCY + [{"wars": [{"defender": WAR_STATUS_DEPENDENCY + MILITARIZATION_CHECKER["nations"] + [{"wars": ["attid", "defid", "turnsleft"]}]}, {"attacker": WAR_STATUS_DEPENDENCY + MILITARIZATION_CHECKER["nations"] + [{"wars": ["attid", "defid", "turnsleft"]}]}, "date", "id", "attid", "defid", "winner", "att_resistance", "def_resistance", "attpoints", "defpoints", "attpeace", "defpeace", "war_type", "groundcontrol", "airsuperiority", "navalblockade", "turnsleft", "att_fortify", "def_fortify"]}]})


# scanner.py
BACKGROUND_SCANNER = {"nations": ["id", "discord", "leader_name", "nation_name", "warpolicy", "vacation_mode_turns", "flag", "last_active", "alliance_position_id", "continent", "fallout_shelter", "military_salvage", "warpolicy", "resource_production_center", "dompolicy", "vds", "irond", "population", "alliance_id", "beige_turns", "score", "color", "soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", {"bounties": ["amount", "type"]}, {"treasures": ["name"]}, {"alliance": ["name", "id"]}, {"wars": ["date", "winner", {"attacker": ["war_policy"]}, {"defender": ["war_policy"]}, "war_type", "defid", "turnsleft", {"attacks": ["loot_info", "victor", "moneystolen"]}]}, "alliance_position", "num_cities", "ironw", "bauxitew", "armss", "egr", "massirr", "itc", "recycling_initiative", "telecom_satellite", "green_tech", "clinical_research_center", "specialized_police_training", "uap", {"cities": ["date", "powered", "infrastructure", "land", "oilpower", "windpower", "coalpower", "nuclearpower", "coalmine", "oilwell", "uramine", "barracks", "farm", "policestation", "hospital", "recyclingcenter", "subway", "supermarket", "bank", "mall", "stadium", "leadmine", "ironmine", "bauxitemine", "gasrefinery", "aluminumrefinery", "steelmill", "munitionsfactory", "factory", "airforcebase", "drydock"]}]}
TRANSACTIONS_DEPENDENCY = ["id", "date", "sender_id", "sender_type", "receiver_id", "receiver_type", "banker_id", "note", "money", "coal", "oil", "uranium", "iron", "bauxite", "lead", "gasoline", "munitions", "steel", "aluminum", "food"]
TRANSACTIONS = {"alliances": [{"bankrecs": TRANSACTIONS_DEPENDENCY}, {"taxrecs": TRANSACTIONS_DEPENDENCY}]}