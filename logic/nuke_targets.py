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

Attacker Guiding Satellite multiplies missile/nuke infrastructure destroyed
by 1.2 (pwpedia Guiding-Satellite). Improvement destruction is not valued.

We never roll individual intercepts; we accumulate *expected* outcomes per
launch (``value_if_hit * P(hit)``). War simulations repeat launches until
expected resistance reaches zero.

Resistance on a successful hit (PnWPedia Nuclear-Attack / Missile-Strike):

- Nuke: 25
- Missile: 18

Dollar damage uses ``infra_rebuild_cost`` (buy/rebuild price), not sell value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from logic.common import _normalize_war_policy, _war_field
from logic.damage import war_infra_share
from logic.economy import infra_rebuild_cost
from logic.raids import war_turns_left

Weapon = Literal["nuke", "missile"]

# ---------------------------------------------------------------------------
# PnWPedia ground truth (.ctx/pwpedia_data.jsonl)
# ---------------------------------------------------------------------------

DEFENDER_STARTING_RESISTANCE = 100  # politicsandwar.fandom.com/wiki/War

NUKE_RESISTANCE_ON_HIT = 25.0  # pwpedia Nuclear-Attack
MISSILE_RESISTANCE_ON_HIT = 18.0  # pwpedia Missile-Strike

VDS_INTERCEPT_CHANCE = 0.25  # pwpedia Vital-Defense-System, Nukes
IRON_DOME_INTERCEPT_CHANCE = 0.30  # pwpedia Iron-Dome, Missiles

# Attacker project: +20% missile/nuke infrastructure damage (pwpedia Guiding-Satellite)
GUIDING_SATELLITE_INFRA_MOD = 1.2

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
    rebuild_damage_if_hit: float
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


def _has_vds(nation: dict[str, Any]) -> bool:
    return _project_bool(nation, "vds", "vital_defense_system")


def _has_iron_dome(nation: dict[str, Any]) -> bool:
    return _project_bool(nation, "irond", "iron_dome")


def _has_fallout_shelter(nation: dict[str, Any]) -> bool:
    return _project_bool(nation, "fallout_shelter", "falloutShelter")


def _war_policy_label(nation: dict[str, Any]) -> str:
    """The war policy as stored: "Turtle" from scans, "TURTLE" from subscription rows."""
    return str(nation.get("warpolicy") or nation.get("war_policy") or "")


def _policy_modifiers(nation: dict[str, Any]) -> dict[str, float]:
    mods = {
        "policy_infra_dealt": 1.0,
        "policy_infra_lost": 1.0,
        "fallout_shelter_mod": 1.0,
        "guiding_satellite_mod": 1.0,
    }
    # Scans store "Attrition", subscription rows the enum name "ATTRITION".
    policy = _normalize_war_policy(nation.get("warpolicy") or nation.get("war_policy"))
    if policy == "ATTRITION":
        mods["policy_infra_dealt"] = 1.1
    elif policy == "TURTLE":
        mods["policy_infra_lost"] = 0.9
    elif policy in ("MONEYBAGS", "COVERT", "ARCANE"):
        mods["policy_infra_lost"] = 1.05
    if _has_fallout_shelter(nation):
        mods["fallout_shelter_mod"] = 0.9
    if _project_bool(nation, "guiding_satellite", "guidingSatellite"):
        mods["guiding_satellite_mod"] = GUIDING_SATELLITE_INFRA_MOD
    return mods


def _attacker_war_infra_mod(attacker: dict[str, Any], defender_id: str) -> float:
    """Infra share the attacker deals the defender.

    From an active war between the two, by its war type and by which side declared
    it (a defender deals 50% in a raid war, the declarer 25%). With no such war, 1.0:
    the page assumes the attacker declares an attrition war.
    """
    attacker_id = str(attacker.get("id"))
    defender_id = str(defender_id)
    for war in attacker.get("wars") or []:
        if not isinstance(war, dict) or war_turns_left(war) <= 0:
            continue
        att_id = str(_war_field(war, "attid", "att_id"))
        def_id = str(_war_field(war, "defid", "def_id"))
        if att_id == attacker_id and def_id == defender_id:
            declarer = True
        elif att_id == defender_id and def_id == attacker_id:
            declarer = False
        else:
            continue
        share = war_infra_share(_war_field(war, "war_type", "warType"), declarer=declarer)
        # An unknown war type counts as ordinary, the game's default.
        return share if share is not None else 0.5
    return 1.0


def _strike_mods(attacker: dict[str, Any], defender: dict[str, Any]) -> dict[str, float]:
    """Keyword arguments for :func:`compute_expected_launch_outcome` for this pair."""
    att_mods = _policy_modifiers(attacker)
    def_mods = _policy_modifiers(defender)
    return {
        "war_infra_mod": _attacker_war_infra_mod(attacker, str(defender.get("id", ""))),
        "policy_infra_dealt": att_mods["policy_infra_dealt"],
        "policy_infra_lost": def_mods["policy_infra_lost"],
        "fallout_shelter_mod": def_mods["fallout_shelter_mod"],
        "guiding_satellite_mod": att_mods["guiding_satellite_mod"],
    }


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
    guiding_satellite_mod: float = 1.0,
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
        * guiding_satellite_mod
    )


def _raw_missile_infra(
    city: CityState,
    *,
    war_infra_mod: float,
    policy_infra_dealt: float,
    policy_infra_lost: float,
    guiding_satellite_mod: float = 1.0,
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
    return (
        base
        * war_infra_mod
        * policy_infra_dealt
        * policy_infra_lost
        * guiding_satellite_mod
    )


def _infra_destroyed_if_hit(
    strike: InterceptStrikeEV,
    city: CityState,
    *,
    war_infra_mod: float,
    policy_infra_dealt: float,
    policy_infra_lost: float,
    fallout_shelter_mod: float,
    guiding_satellite_mod: float = 1.0,
) -> float:
    if strike.weapon == "nuke":
        raw = _raw_nuke_infra(
            city,
            war_infra_mod=war_infra_mod,
            policy_infra_dealt=policy_infra_dealt,
            policy_infra_lost=policy_infra_lost,
            fallout_shelter_mod=fallout_shelter_mod,
            guiding_satellite_mod=guiding_satellite_mod,
        )
    else:
        raw = _raw_missile_infra(
            city,
            war_infra_mod=war_infra_mod,
            policy_infra_dealt=policy_infra_dealt,
            policy_infra_lost=policy_infra_lost,
            guiding_satellite_mod=guiding_satellite_mod,
        )
    # A strike can't destroy more than the city has (Fandom War Formulas:
    # min(..., Total City Infra)).
    return min(raw, max(city.infrastructure, 0.0))


def compute_expected_launch_outcome(
    strike: InterceptStrikeEV,
    city: CityState,
    defender: dict[str, Any],
    *,
    war_infra_mod: float,
    policy_infra_dealt: float,
    policy_infra_lost: float,
    fallout_shelter_mod: float,
    guiding_satellite_mod: float = 1.0,
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
        guiding_satellite_mod=guiding_satellite_mod,
    )
    rebuild_if_hit = (
        infra_rebuild_cost(city.infrastructure, infra_if_hit, defender) if infra_if_hit > 0 else 0.0
    )
    return ExpectedLaunchOutcome(
        hit_probability=p_hit,
        infra_destroyed_if_hit=infra_if_hit,
        expected_infra_destroyed=infra_if_hit * p_hit,
        rebuild_damage_if_hit=rebuild_if_hit,
        expected_rebuild_damage=rebuild_if_hit * p_hit if p_hit > 0 else 0.0,
        expected_resistance_reduction=strike.expected_resistance_reduction,
        launch_cost=strike.launch_cost,
    )


def _simulate_war(
    strike: InterceptStrikeEV,
    cities: list[CityState],
    defender: dict[str, Any],
    mods: dict[str, float],
    starting_resistance: float,
) -> tuple[float, int, float, float]:
    resistance = float(starting_resistance)
    total_defender_damage = 0.0
    total_attacker_cost = 0.0
    shots = 0
    # The simulation lowers infra as it goes, so work on copies.
    city_states = [CityState(c.infrastructure, c.land) for c in cities]

    while resistance > 0 and shots < MAX_SIMULATION_SHOTS:
        city = _highest_city(city_states)
        if city is None:
            break

        # Depleted cities still exist in-game; use a floor so resistance can reach 0.
        strike_city = CityState(
            infrastructure=max(city.infrastructure, 1.0),
            land=max(city.land, 1.0),
        )

        outcome = compute_expected_launch_outcome(strike, strike_city, defender, **mods)

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
    strike = InterceptStrikeEV(weapon, vds=_has_vds(defender), iron_dome=_has_iron_dome(defender))
    return _simulate_war(
        strike, cities, defender, _strike_mods(attacker, defender), starting_resistance
    )


def compute_nuke_missile_metrics(
    attacker: dict[str, Any],
    defender: dict[str, Any],
) -> Optional[NukeMissileMetrics]:
    cities = _parse_cities(defender)
    if not cities:
        return None

    mods = _strike_mods(attacker, defender)
    vds = _has_vds(defender)
    iron_dome = _has_iron_dome(defender)

    city = _highest_city(cities)
    assert city is not None

    nuke_strike = InterceptStrikeEV("nuke", vds=vds, iron_dome=False)
    missile_strike = InterceptStrikeEV("missile", vds=False, iron_dome=iron_dome)
    nuke_outcome = compute_expected_launch_outcome(nuke_strike, city, defender, **mods)
    missile_outcome = compute_expected_launch_outcome(missile_strike, city, defender, **mods)

    sim_nuke_net, sim_nuke_shots, _, _ = _simulate_war(
        nuke_strike, cities, defender, mods, DEFENDER_STARTING_RESISTANCE
    )
    sim_missile_net, sim_missile_shots, _, _ = _simulate_war(
        missile_strike, cities, defender, mods, DEFENDER_STARTING_RESISTANCE
    )

    max_infra, avg_infra = _infra_stats(cities)

    return NukeMissileMetrics(
        max_infra=max_infra,
        avg_infra=avg_infra,
        nuke_infra_lost=nuke_outcome.expected_infra_destroyed,
        nuke_damage=nuke_outcome.expected_rebuild_damage,
        # Without the defender's VDS / Iron Dome every launch hits.
        nuke_damage_without_vds=nuke_outcome.rebuild_damage_if_hit,
        nuke_net=nuke_outcome.expected_rebuild_damage - NUKE_LAUNCH_COST,
        missile_infra_lost=missile_outcome.expected_infra_destroyed,
        missile_damage=missile_outcome.expected_rebuild_damage,
        missile_damage_without_iron_dome=missile_outcome.rebuild_damage_if_hit,
        missile_net=missile_outcome.expected_rebuild_damage - MISSILE_LAUNCH_COST,
        sim_nuke_net=sim_nuke_net,
        sim_nuke_shots=sim_nuke_shots,
        sim_missile_net=sim_missile_net,
        sim_missile_shots=sim_missile_shots,
        vds=vds,
        iron_dome=iron_dome,
        fallout_shelter=_has_fallout_shelter(defender),
        defender_war_policy=_war_policy_label(defender),
    )


def defender_summary(defender: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Infra and defensive fields for a target when no attacker is known.

    Same keys and rounding as :func:`metrics_to_dict`; None when it has no cities.
    """
    cities = _parse_cities(defender)
    if not cities:
        return None
    max_infra, avg_infra = _infra_stats(cities)
    return {
        "maxInfra": round(max_infra, 2),
        "avgInfra": round(avg_infra, 2),
        "vds": _has_vds(defender),
        "ironDome": _has_iron_dome(defender),
        "falloutShelter": _has_fallout_shelter(defender),
        "defenderWarPolicy": _war_policy_label(defender),
    }


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
