/** User-facing table column headers for the nuke targets page. */
export const NUKE_TARGET_COLUMN_LABELS: Record<string, string> = {
  id: 'ID',
  nationName: 'Nation Name',
  leaderName: 'Leader',
  allianceName: 'Alliance',
  alliancePosition: 'Position',
  numCities: 'Cities',
  score: 'Score',
  simNukeNet: 'Nuke War Net Damage',
  simMissileNet: 'Missile War Net Damage',
  nukeDamage: 'One Nuke Damage',
  nukeDamageWithoutVds: 'No-VDS Nuke Damage',
  nukeNet: 'One Nuke Net Damage',
  missileDamage: 'One Missile Damage',
  missileDamageWithoutIronDome: 'No Iron Dome Missile Damage',
  missileNet: 'One Missile Net Damage',
  nukeInfraLost: 'Infrastructure per Nuke',
  maxInfra: 'Best City Infrastructure',
  avgInfra: 'Average City Infrastructure',
  vds: 'VDS',
  ironDome: 'Iron Dome',
  falloutShelter: 'Fallout Shelter',
  defenderWarPolicy: 'Their War Policy',
  daysInactive: 'Inactive (days)',
  defSlots: 'Defensive Wars',
  beigeTurns: 'Beige Turns',
  simNukeShots: 'Nukes Needed',
  simMissileShots: 'Missiles Needed',
};

/** Column header tooltips — plain PnW language. */
export const NUKE_TARGET_COLUMN_DOCS: Record<string, string> = {
  id: 'Politics & War nation ID for the target.',
  nationName: 'Target nation. Right-click a row for Politics & War links and a quick-link to the damage calculator.',
  leaderName: 'Nation leader name.',
  allianceName: 'Their current alliance.',
  alliancePosition: 'Their position in the alliance.',
  numCities: 'Number of cities.',
  score: 'Nation score. The server only returns targets within your selected score range.',
  simNukeNet:
    'Simulated Attrition war using only nukes until war resistance reaches 0: total expected rebuild damage minus your nuke launch costs.',
  simMissileNet:
    'Same full-war simulation using only missiles until resistance reaches 0. Total rebuild damage minus missile launch costs.',
  nukeDamage:
    'Expected rebuild cost from one nuke on their highest-infrastructure city (before you pay to launch it).',
  nukeDamageWithoutVds:
    'Same one-nuke rebuild cost if the target had no VDS (100% hit rate instead of 75%).',
  nukeNet:
    'One nuke: expected rebuild damage minus launch cost. Negative means the nuke costs you more than it destroys.',
  missileDamage: 'Expected rebuild cost from one missile on their highest-infrastructure city.',
  missileDamageWithoutIronDome:
    'Same one-missile rebuild cost if the target had no Iron Dome (100% hit rate instead of 70%).',
  missileNet:
    'One missile: expected rebuild damage minus launch cost. Negative means the missile costs you more than it destroys.',
  nukeInfraLost:
    'Expected infrastructure points destroyed by one nuke launch (after VDS intercept chance).',
  maxInfra: 'Highest infrastructure in any city. Nukes and missiles always strike this city first.',
  avgInfra: 'Average infrastructure across all of their cities.',
  vds: 'VDS: 25% of nukes are shot down. Intercepted launches deal no damage and remove no resistance; successful hits remove 25 resistance.',
  ironDome:
    'Iron Dome: 30% of missiles are intercepted. Intercepted launches deal no damage and remove no resistance; successful hits remove 18 resistance.',
  falloutShelter: 'National project that reduces infrastructure damage from nukes by 10%.',
  defenderWarPolicy:
    'Defender War Policy (e.g. Turtle takes 10% less infrastructure damage; Moneybags, Covert, and Arcane take 5% more infrastructure damage).',
  daysInactive: 'Days since the nation last logged in.',
  defSlots:
    'Defensive war slots in use. A nation with 3 defensive wars cannot be declared on.',
  beigeTurns: 'Turns remaining in beige. Beige nations cannot be declared on.',
  simNukeShots: 'Nuke launches in the simulation before war resistance reaches 0.',
  simMissileShots: 'Missile launches in the simulation before war resistance reaches 0.',
};

/** Short help text for filter cards on the nuke targets page. */
export const NUKE_TARGET_FILTER_DOCS = {
  score:
    'The score range for the target list. Use your score (0.75×–2.5×) or set custom min/max.',
  alliances:
    'Include shows only the picked alliances; exclude removes them from results.',
  infra:
    'Minimum city infrastructure. Best city infra is the city with the highest infrastructure; avg city infra is the mean across cities.',
  defense:
    'Hide nations with VDS or Iron Dome if you want easier expected hits.',
  beige: 'Beige nations cannot be declared on until beige ends. Hide them when hunting active targets.',
  defWars: 'Nations with 3 defensive wars are not attackable. Lower caps find open slots.',
  inactivity: 'Minimum days since last activity.',
  damageMods:
    'Attrition war policy and Guiding Satellite are preset from your loaded nation. Toggle them to override the damage math without changing your in-game settings.',
} as const;

/** Cohesive on-page guide copy (PnW domain language). */
export const NUKE_TARGETS_PAGE_GUIDE = [
  {
    title: 'Attrition damage, not raids',
    body: 'This page ranks nations by how much infrastructure damage you can inflict in an Attrition war with nukes or missiles. Loot is not considered, we only regard rebuild-cost damage and the resources you spend launching weapons. Load your nation so we apply your War Policy, projects, and score range.',
  },
  {
    title: 'Damage is measured by the rebuild cost',
    body: 'Dollar columns show what the defender must pay to rebuild destroyed infrastructure.',
  },
  {
    title: 'Damage modifiers',
    body: 'We assume that each strike targets their highest-infrastructure city. Vital Defense System and Iron Dome are modeled as intercept probability (25% / 30%), a miss deals no infra damage. Fallout Shelter cuts nuke infrastructure damage by 10%. Load your nation to preset Attrition war policy (+10% infra dealt) and Guiding Satellite (+20% missile/nuke infra); you can toggle those on or off in Your Nation without changing your in-game settings. The defender\'s War Policy further adjusts damage taken and dealt.',
  },
  {
    title: 'War resistance and full-war net damage',
    body: 'Nations enter a war with 100 war resistance. A successful nuclear attack removes 25 resistance; a successful missile strike removes 18. Vital Defense System and Iron Dome adds intercept chance, meaning they reduce the expected decrease in resistance. The simulation fires one weapon type until resistance reaches 0, using expected value each launch. Nuke war net dmg is the total expected rebuild damage minus launch costs over that war.',
  },
  {
    title: 'Reading the table',
    body: 'One nuke damage is the expected rebuild cost from a single launch; One nuke net dmg subtracts launch cost. Nukes needed counts launches in the full simulation. You can hover over column headers for more details. Right-click on a row for nation links and a quick-link to the damage calculator.',
  },
] as const;
