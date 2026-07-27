"""
Nuke/missile target metrics and attrition-war simulation for the web UI.

Simulation model (expected value)
---------------------------------
Each launch is one random trial:

- With probability ``hit_probability``, the strike lands: infra is destroyed,
  rebuild-cost damage applies, and war resistance drops by the weapon's
  on-hit amount (PnWPedia).
- With probability ``1 - hit_probability``, the strike is intercepted: no
  infra loss, no resistance loss.
- Launch cost is always paid.

Intercept chances come from PnWPedia (.ctx/pwpedia_data.jsonl):

- Vital Defense System: 25% of nukes shot down
- Iron Dome: 30% of missiles shot down

We never roll individual intercepts; we accumulate *expected* outcomes per
launch (``value_if_hit * P(hit)``). War simulations repeat launches until
expected resistance reaches zero.

Resistance on a successful hit (PnWPedia Nuclear-Attack / Missile-Strike):

- Nuke: 25
- Missile: 18

Dollar damage uses ``infra_rebuild_cost`` (buy/rebuild price), not sell value.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Literal, Optional

from logic.economy import infra_rebuild_cost

Weapon = Literal["nuke", "missile"]

# ---------------------------------------------------------------------------
# PnWPedia ground truth (.ctx/pwpedia_data.jsonl)
# ---------------------------------------------------------------------------

DEFENDER_STARTING_RESISTANCE = 100  # politicsandwar.fandom.com/wiki/War

NUKE_RESISTANCE_ON_HIT = 25.0  # pwpedia Nuclear-Attack
MISSILE_RESISTANCE_ON_HIT = 18.0  # pwpedia Missile-Strike

VDS_INTERCEPT_CHANCE = 0.25  # pwpedia Vital-Defense-System, Nukes
IRON_DOME_INTERCEPT_CHANCE = 0.30  # pwpedia Iron-Dome, Missiles

MAX_SIMULATION_SHOTS = 500

# Resource prices aligned with logic/damage.py
_ALUM_PRICE = 2971
_GAS_PRICE = 3340
_MUN_PRICE = 1960
_URANIUM_PRICE = 3039

NUKE_LAUNCH_COST = (
    1000 * _ALUM_PRICE
    + 500 * _GAS_PRICE
    + 1_750_000
    + 500 * _URANIUM_PRICE
)
MISSILE_LAUNCH_COST = (
    150 * _ALUM_PRICE
    + 100 * _GAS_PRICE
    + 100 * _MUN_PRICE
    + 150_000
)


@dataclass(frozen=True)
class InterceptStrikeEV:
    """
    Expected-value intercept model for a single nuke or missile launch.

    ``hit_probability`` is P(not intercepted). Resistance and infra effects
    are scaled by this probability; launch cost is not.
    """

    weapon: Weapon
    vds: bool
    iron_dome: bool

    @property
    def hit_probability(self) -> float:
        if self.weapon == "nuke":
            intercept = VDS_INTERCEPT_CHANCE if self.vds else 0.0
        else:
            intercept = IRON_DOME_INTERCEPT_CHANCE if self.iron_dome else 0.0
        return 1.0 - intercept

    @property
    def resistance_on_successful_hit(self) -> float:
        if self.weapon == "nuke":
            return NUKE_RESISTANCE_ON_HIT
        return MISSILE_RESISTANCE_ON_HIT

    @property
    def expected_resistance_reduction(self) -> float:
        return self.resistance_on_successful_hit * self.hit_probability

    @property
    def launch_cost(self) -> float:
        return NUKE_LAUNCH_COST if self.weapon == "nuke" else MISSILE_LAUNCH_COST


@dataclass
class ExpectedLaunchOutcome:
    """Per-launch expected outcomes under :class:`InterceptStrikeEV`."""

    hit_probability: float
    infra_destroyed_if_hit: float
    expected_infra_destroyed: float
    expected_rebuild_damage: float
    expected_resistance_reduction: float
    launch_cost: float


@dataclass
class CityState:
    infrastructure: float
    land: float


@dataclass
class NukeMissileMetrics:
    max_infra: float
    avg_infra: float
    nuke_infra_lost: float
    nuke_damage: float
    nuke_damage_without_vds: float
    nuke_net: float
    missile_infra_lost: float
    missile_damage: float
    missile_damage_without_iron_dome: float
    missile_net: float
    sim_nuke_net: float
    sim_nuke_shots: int
    sim_missile_net: float
    sim_missile_shots: int
    vds: bool
    iron_dome: bool
    fallout_shelter: bool
    defender_war_policy: str


def _project_bool(nation: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        if nation.get(key):
            return True
    return False


def _policy_modifiers(nation: dict[str, Any]) -> dict[str, float]:
    mods = {
        "policy_infra_dealt": 1.0,
        "policy_infra_lost": 1.0,
        "fallout_shelter_mod": 1.0,
    }
    policy = nation.get("warpolicy") or nation.get("war_policy") or ""
    if policy == "Attrition":
        mods["policy_infra_dealt"] = 1.1
    elif policy == "Turtle":
        mods["policy_infra_lost"] = 0.9
    elif policy == "Moneybags":
        mods["policy_infra_lost"] = 1.05
    elif policy in ("Covert", "Arcane"):
        mods["policy_infra_lost"] = 1.05
    if _project_bool(nation, "fallout_shelter", "falloutShelter"):
        mods["fallout_shelter_mod"] = 0.9
    return mods


def _attacker_war_infra_mod(attacker: dict[str, Any], defender_id: str) -> float:
    """Default attrition attacker infra mod; override if already at war."""
    defender_id = str(defender_id)
    for war in attacker.get("wars") or []:
        att_id = str(war.get("attid", ""))
        def_id = str(war.get("defid", ""))
        if war.get("turnsleft", 0) <= 0:
            continue
        if att_id == str(attacker.get("id")) and def_id == defender_id:
            war_type = war.get("war_type") or war.get("warType") or "ORDINARY"
            if war_type == "RAID":
                return 0.5
            if war_type == "ATTRITION":
                return 1.0
            return 0.5
    return 1.0


def _parse_cities(nation: dict[str, Any]) -> list[CityState]:
    cities: list[CityState] = []
    for city in nation.get("cities") or []:
        if not isinstance(city, dict):
            continue
        infra = float(city.get("infrastructure") or city.get("infra") or 0)
        land = float(city.get("land") or 1)
        if land <= 0:
            land = 1.0
        cities.append(CityState(infrastructure=infra, land=land))
    return cities


def _highest_city(cities: list[CityState]) -> Optional[CityState]:
    if not cities:
        return None
    return max(cities, key=lambda c: c.infrastructure)


def _infra_stats(cities: list[CityState]) -> tuple[float, float]:
    if not cities:
        return 0.0, 0.0
    values = [c.infrastructure for c in cities]
    return max(values), sum(values) / len(values)


def _raw_nuke_infra(
    city: CityState,
    *,
    war_infra_mod: float,
    policy_infra_dealt: float,
    policy_infra_lost: float,
    fallout_shelter_mod: float,
) -> float:
    infra = city.infrastructure
    land = max(city.land, 1.0)
    base = max(
        min(
            (1700 + max(2000, infra * 100 / land * 13.5)) / 2,
            infra * 0.8 + 150,
        ),
        0,
    )
    return (
        base
        * war_infra_mod
        * policy_infra_dealt
        * policy_infra_lost
        * fallout_shelter_mod
    )


def _raw_missile_infra(
    city: CityState,
    *,
    war_infra_mod: float,
    policy_infra_dealt: float,
    policy_infra_lost: float,
) -> float:
    infra = city.infrastructure
    land = max(city.land, 1.0)
    base = max(
        min(
            (300 + max(350, infra * 100 / land * 3)) / 2,
            infra * 0.3 + 100,
        ),
        0,
    )
    return base * war_infra_mod * policy_infra_dealt * policy_infra_lost


def _expected_rebuild_damage(
    city: CityState,
    infra_lost_on_hit: float,
    hit_probability: float,
    nation: Optional[dict[str, Any]] = None,
) -> float:
    if infra_lost_on_hit <= 0 or hit_probability <= 0:
        return 0.0
    rebuild_on_hit = infra_rebuild_cost(city.infrastructure, infra_lost_on_hit, nation)
    return rebuild_on_hit * hit_probability


def _infra_destroyed_if_hit(
    strike: InterceptStrikeEV,
    city: CityState,
    *,
    war_infra_mod: float,
    policy_infra_dealt: float,
    policy_infra_lost: float,
    fallout_shelter_mod: float,
) -> float:
    if strike.weapon == "nuke":
        return _raw_nuke_infra(
            city,
            war_infra_mod=war_infra_mod,
            policy_infra_dealt=policy_infra_dealt,
            policy_infra_lost=policy_infra_lost,
            fallout_shelter_mod=fallout_shelter_mod,
        )
    return _raw_missile_infra(
        city,
        war_infra_mod=war_infra_mod,
        policy_infra_dealt=policy_infra_dealt,
        policy_infra_lost=policy_infra_lost,
    )


def compute_expected_launch_outcome(
    strike: InterceptStrikeEV,
    city: CityState,
    defender: dict[str, Any],
    *,
    war_infra_mod: float,
    policy_infra_dealt: float,
    policy_infra_lost: float,
    fallout_shelter_mod: float,
) -> ExpectedLaunchOutcome:
    """
    Expected infra, rebuild $, and resistance for one launch.

    Uses ``InterceptStrikeEV``: only successful hits deal damage and reduce
    resistance; intercepts are modeled via ``hit_probability``.
    """
    p_hit = strike.hit_probability
    infra_if_hit = _infra_destroyed_if_hit(
        strike,
        city,
        war_infra_mod=war_infra_mod,
        policy_infra_dealt=policy_infra_dealt,
        policy_infra_lost=policy_infra_lost,
        fallout_shelter_mod=fallout_shelter_mod,
    )
    return ExpectedLaunchOutcome(
        hit_probability=p_hit,
        infra_destroyed_if_hit=infra_if_hit,
        expected_infra_destroyed=infra_if_hit * p_hit,
        expected_rebuild_damage=_expected_rebuild_damage(
            city, infra_if_hit, p_hit, defender
        ),
        expected_resistance_reduction=strike.expected_resistance_reduction,
        launch_cost=strike.launch_cost,
    )


def simulate_war_net_damage(
    attacker: dict[str, Any],
    defender: dict[str, Any],
    weapon: Weapon,
    *,
    starting_resistance: float = DEFENDER_STARTING_RESISTANCE,
) -> tuple[float, int, float, float]:
    """
    Expected-value war simulation: fire only ``weapon`` until resistance <= 0.

    Each iteration is one paid launch. Resistance and infra use expected
    outcomes from :func:`compute_expected_launch_outcome` (not binary rolls).

    Returns (net_damage, shots_fired, total_defender_damage, total_attacker_cost).
    """
    cities = _parse_cities(defender)
    if not cities:
        return 0.0, 0, 0.0, 0.0

    att_mods = _policy_modifiers(attacker)
    def_mods = _policy_modifiers(defender)
    war_infra_mod = _attacker_war_infra_mod(attacker, str(defender.get("id", "")))

    vds = _project_bool(defender, "vds", "vital_defense_system")
    iron_dome = _project_bool(defender, "irond", "iron_dome")
    strike = InterceptStrikeEV(weapon, vds=vds, iron_dome=iron_dome)

    resistance = float(starting_resistance)
    total_defender_damage = 0.0
    total_attacker_cost = 0.0
    shots = 0
    city_states = copy.deepcopy(cities)

    while resistance > 0 and shots < MAX_SIMULATION_SHOTS:
        city = _highest_city(city_states)
        if city is None:
            break

        # Depleted cities still exist in-game; use a floor so resistance can reach 0.
        strike_city = CityState(
            infrastructure=max(city.infrastructure, 1.0),
            land=max(city.land, 1.0),
        )

        outcome = compute_expected_launch_outcome(
            strike,
            strike_city,
            defender,
            war_infra_mod=war_infra_mod,
            policy_infra_dealt=att_mods["policy_infra_dealt"],
            policy_infra_lost=def_mods["policy_infra_lost"],
            fallout_shelter_mod=def_mods["fallout_shelter_mod"],
        )

        total_defender_damage += outcome.expected_rebuild_damage
        total_attacker_cost += outcome.launch_cost
        resistance -= outcome.expected_resistance_reduction
        city.infrastructure = max(
            0.0, city.infrastructure - outcome.expected_infra_destroyed
        )
        shots += 1

    return (
        total_defender_damage - total_attacker_cost,
        shots,
        total_defender_damage,
        total_attacker_cost,
    )


def compute_nuke_missile_metrics(
    attacker: dict[str, Any],
    defender: dict[str, Any],
) -> Optional[NukeMissileMetrics]:
    cities = _parse_cities(defender)
    if not cities:
        return None

    att_mods = _policy_modifiers(attacker)
    def_mods = _policy_modifiers(defender)
    war_infra_mod = _attacker_war_infra_mod(attacker, str(defender.get("id", "")))

    vds = _project_bool(defender, "vds", "vital_defense_system")
    iron_dome = _project_bool(defender, "irond", "iron_dome")
    fallout_shelter = _project_bool(defender, "fallout_shelter", "falloutShelter")

    city = _highest_city(cities)
    assert city is not None

    nuke_strike = InterceptStrikeEV("nuke", vds=vds, iron_dome=False)
    missile_strike = InterceptStrikeEV("missile", vds=False, iron_dome=iron_dome)
    nuke_no_vds = InterceptStrikeEV("nuke", vds=False, iron_dome=False)
    missile_no_dome = InterceptStrikeEV("missile", vds=False, iron_dome=False)

    nuke_outcome = compute_expected_launch_outcome(
        nuke_strike,
        city,
        defender,
        war_infra_mod=war_infra_mod,
        policy_infra_dealt=att_mods["policy_infra_dealt"],
        policy_infra_lost=def_mods["policy_infra_lost"],
        fallout_shelter_mod=def_mods["fallout_shelter_mod"],
    )
    nuke_baseline_outcome = compute_expected_launch_outcome(
        nuke_no_vds,
        city,
        defender,
        war_infra_mod=war_infra_mod,
        policy_infra_dealt=att_mods["policy_infra_dealt"],
        policy_infra_lost=def_mods["policy_infra_lost"],
        fallout_shelter_mod=def_mods["fallout_shelter_mod"],
    )
    missile_outcome = compute_expected_launch_outcome(
        missile_strike,
        city,
        defender,
        war_infra_mod=war_infra_mod,
        policy_infra_dealt=att_mods["policy_infra_dealt"],
        policy_infra_lost=def_mods["policy_infra_lost"],
        fallout_shelter_mod=def_mods["fallout_shelter_mod"],
    )
    missile_baseline_outcome = compute_expected_launch_outcome(
        missile_no_dome,
        city,
        defender,
        war_infra_mod=war_infra_mod,
        policy_infra_dealt=att_mods["policy_infra_dealt"],
        policy_infra_lost=def_mods["policy_infra_lost"],
        fallout_shelter_mod=def_mods["fallout_shelter_mod"],
    )

    sim_nuke_net, sim_nuke_shots, _, _ = simulate_war_net_damage(attacker, defender, "nuke")
    sim_missile_net, sim_missile_shots, _, _ = simulate_war_net_damage(
        attacker, defender, "missile"
    )

    max_infra, avg_infra = _infra_stats(cities)

    return NukeMissileMetrics(
        max_infra=max_infra,
        avg_infra=avg_infra,
        nuke_infra_lost=nuke_outcome.expected_infra_destroyed,
        nuke_damage=nuke_outcome.expected_rebuild_damage,
        nuke_damage_without_vds=nuke_baseline_outcome.expected_rebuild_damage,
        nuke_net=nuke_outcome.expected_rebuild_damage - NUKE_LAUNCH_COST,
        missile_infra_lost=missile_outcome.expected_infra_destroyed,
        missile_damage=missile_outcome.expected_rebuild_damage,
        missile_damage_without_iron_dome=missile_baseline_outcome.expected_rebuild_damage,
        missile_net=missile_outcome.expected_rebuild_damage - MISSILE_LAUNCH_COST,
        sim_nuke_net=sim_nuke_net,
        sim_nuke_shots=sim_nuke_shots,
        sim_missile_net=sim_missile_net,
        sim_missile_shots=sim_missile_shots,
        vds=vds,
        iron_dome=iron_dome,
        fallout_shelter=fallout_shelter,
        defender_war_policy=str(defender.get("warpolicy") or defender.get("war_policy") or ""),
    )


def metrics_to_dict(metrics: NukeMissileMetrics) -> dict[str, Any]:
    return {
        "maxInfra": round(metrics.max_infra, 2),
        "avgInfra": round(metrics.avg_infra, 2),
        "nukeInfraLost": round(metrics.nuke_infra_lost, 2),
        "nukeDamage": round(metrics.nuke_damage, 2),
        "nukeDamageWithoutVds": round(metrics.nuke_damage_without_vds, 2),
        "nukeNet": round(metrics.nuke_net, 2),
        "missileInfraLost": round(metrics.missile_infra_lost, 2),
        "missileDamage": round(metrics.missile_damage, 2),
        "missileDamageWithoutIronDome": round(metrics.missile_damage_without_iron_dome, 2),
        "missileNet": round(metrics.missile_net, 2),
        "simNukeNet": round(metrics.sim_nuke_net, 2),
        "simNukeShots": metrics.sim_nuke_shots,
        "simMissileNet": round(metrics.sim_missile_net, 2),
        "simMissileShots": metrics.sim_missile_shots,
        "vds": metrics.vds,
        "ironDome": metrics.iron_dome,
        "falloutShelter": metrics.fallout_shelter,
        "defenderWarPolicy": metrics.defender_war_policy,
    }
