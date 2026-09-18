# Glitch Goblin Simulator

Glitch Goblin Simulator is an original, replayable Roblox simulator designed for a
fast first release. Players absorb Common, Rare, and Epic Brain Bubbles (each with a server-owned juice value), carry them back to the pink Goblin Juice Vat, and earn Juice. The purple Turbo Brain Lab has two temporary tiers: larger carry capacity, faster movement, and better conversion value. The Glitch Cave is a 500-Juice progression gate with higher-value bubbles.

## Run locally

1. Install [Rojo](https://rojo.space/) and create a new empty Roblox experience.
2. Run `rojo serve` from this repository.
3. In Roblox Studio, install the Rojo Studio plugin and connect to the served project.
4. Press Play. Studio runs without DataStore access; published servers use DataStore automatically.
5. Replace `BoostProductId = 0` in `src/shared/GameConfig.lua` with a real
   Developer Product ID after creating one in the Creator Dashboard.

The server owns bubble pickup and capacity validation, juicing, upgrades, credits,
the cave unlock, round state, and receipt processing. The HUD displays live
Turbo/boost timers and capacity so the loop is readable on mobile.
DataStore calls fail closed (the run still works, but unsaved credits are not
pretended to be saved). Test purchases in a private published experience; Roblox
does not process Developer Products in Studio.

## Ethical monetization plan

The included product is an optional **2x Juice Boost** for 10 minutes. It does not
block the core loop, remove access to content, or provide an unfair competitive
advantage. A practical first-month target is 100 purchases at 100 Robux, but this is
only a planning targetÃ¢â‚¬â€not a guarantee of income. Reach it through a polished
thumbnail, a short tutorial, daily challenge variations, creator playtests, and
accurate store descriptions. Never use misleading prompts, fake scarcity, or
automated traffic.

Before launch, add a game icon and thumbnail, set the experience age guidelines,
test on mobile, and review the current Roblox Community Standards and monetization
rules.
## Static terrain layout

The map script builds a raised neon hub with colored paths and five labeled zones: Goblin Garage, Static Swamp, Error Forest, Lag Lagoon, and Forbidden Server Room. Studio-facing folders (BubbleSpawnRegions, ZonePortals, VatLocations, PlayerSpawns, and LowPolyProps) and CollectionService tags make the landmarks easy to find or replace. Atmosphere and anchored low-poly props are created at runtime for a readable mobile-safe silhouette.
