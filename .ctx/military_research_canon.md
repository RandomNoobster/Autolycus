# Military research: confirmed in-game values

As of 2026-11-13, read from the in-game Military Research page
(`/nation/military/research/`). Where the wiki dumps in this folder disagree,
this file wins.

Six research tracks, each from level 0 to 20. The API exposes the levels as
`Nation.military_research { ground_capacity ground_cost air_capacity air_cost
naval_capacity naval_cost }`. The in-game "Efficiency" research is the API's
`*_cost` field.

The page only shows the step from level 0 to level 1. The code assumes every
level adds the same step (see `logic/military.py`).

## Capacity research (`*_capacity`)

Raises the unit cap and lowers upkeep. It does not raise daily recruitment.

| Track | Cap per level | Upkeep, peace (level 0 → 1) | Upkeep, war (level 0 → 1) |
|---|---|---|---|
| Ground | +3,000 soldiers, +250 tanks | Soldier $1.25 → $1.21, food 1/750 → 1/770; tank $50 → $48 | Soldier $1.88 → $1.82, food 1/500 → 1/530; tank $75 → $72 |
| Air | +15 aircraft | Aircraft $750 → $720 | Aircraft $1,000 → $980 |
| Naval | +5 ships | Ship $3,300 → $3,240 | Ship $5,000 → $4,900 |

"Food 1/750" means one food per 750 soldiers per day.

The population cap still applies on top of the research bonus. PWPedia
`population-cap` says the total unit cap is limited by both military
improvements and population.

## Efficiency research (`*_cost`)

Lowers unit buy cost and raises daily recruitment ("rebuy").

| Track | Buy cost (level 0 → 1) | Daily recruitment per level |
|---|---|---|
| Ground | Soldier $5.00 → $4.90; tank $60 + 0.50 steel → $59 + 0.49 steel | +2,000 soldiers, +100 tanks |
| Air | Aircraft $4,000 + 10 aluminum → $3,950 + 9.80 aluminum | +6 aircraft |
| Naval | Ship $50,000 + 30 steel → $49,500 + 29.50 steel | +2 ships |

## Research cost

Every track's first level costs $602,250, 100 gasoline, 100 munitions,
100 steel, 400 aluminum and 10,000 food. Each upgrade makes the other upgrades
more expensive.

A reset costs 1 credit. It refunds the money spent on research, but not the
resources.

## Score

PWPedia july-2025-update: each level adds nation score: air 4, ground 3,
naval 2.
