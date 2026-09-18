local map = script.Parent
local CollectionService = game:GetService("CollectionService")

-- The hub is deliberately built from a small vocabulary of anchored primitives.  This
-- keeps the silhouette strong on mobile while leaving all gameplay landmarks editable.
local function part(parent, name, size, position, color, material, shape)
	local value = Instance.new("Part")
	value.Name = name
	value.Size = size
	value.Position = position
	value.Color = color
	value.Material = material or Enum.Material.SmoothPlastic
	value.Anchored = true
	value.TopSurface = Enum.SurfaceType.Smooth
	value.BottomSurface = Enum.SurfaceType.Smooth
	value.Shape = shape or Enum.PartType.Block
	value.Parent = parent or map
	return value
end

local function tagged(parent, name, size, position, color, material, tag, shape)
	local value = part(parent, name, size, position, color, material, shape)
	CollectionService:AddTag(value, tag)
	return value
end

local function folder(name)
	local value = map:FindFirstChild(name) or Instance.new("Folder")
	value.Name = name
	value.Parent = map
	return value
end

local props = folder("LowPolyProps")
local bubbleRegions = folder("BubbleSpawnRegions")
local portals = folder("ZonePortals")
local vats = folder("VatLocations")
local spawns = folder("PlayerSpawns")

local colors = {
	ground = Color3.fromRGB(104, 151, 73),
	groundEdge = Color3.fromRGB(81, 108, 65),
	stone = Color3.fromRGB(116, 103, 82),
	stoneLight = Color3.fromRGB(157, 143, 112),
	metal = Color3.fromRGB(76, 82, 78),
	ink = Color3.fromRGB(40, 48, 38),
	cyan = Color3.fromRGB(75, 210, 232),
	mint = Color3.fromRGB(91, 206, 154),
	gold = Color3.fromRGB(244, 183, 69),
	pink = Color3.fromRGB(235, 82, 157),
	purple = Color3.fromRGB(131, 96, 220),
	orange = Color3.fromRGB(224, 126, 64),
}

local function light(parent, color, range, brightness)
	local value = Instance.new("PointLight")
	value.Color = color
	value.Range = range
	value.Brightness = brightness
	value.Shadows = true
	value.Parent = parent
	return value
end

local function pipe(name, a, b, radius, color)
	local delta = b - a
	local tube = part(props, name, Vector3.new(radius, radius, delta.Magnitude), (a + b) / 2, color, Enum.Material.Metal, Enum.PartType.Cylinder)
	tube.CFrame = CFrame.lookAt((a + b) / 2, b) * CFrame.Angles(math.pi / 2, 0, 0)
	return tube
end

local function mushroom(name, position, color)
	part(props, name .. "Stem", Vector3.new(1.2, 3, 1.2), position + Vector3.new(0, 1.5, 0), colors.stoneLight, Enum.Material.SmoothPlastic, Enum.PartType.Cylinder)
	part(props, name .. "Cap", Vector3.new(4, 1.4, 4), position + Vector3.new(0, 3.2, 0), color, Enum.Material.SmoothPlastic, Enum.PartType.Ball)
end

local function bubbleCluster(name, center, color)
	local cluster = folder("BubbleClusters")
	local marker = tagged(cluster, name, Vector3.new(10, 0.2, 10), center, color, Enum.Material.SmoothPlastic, "BubbleCluster")
	marker.Transparency = 0.94
	marker.CanCollide = false
	for index = 1, 5 do
		local offset = Vector3.new((index - 3) * 2, 1.5 + (index % 2), ((index * 3) % 5) - 2)
		local bubble = part(cluster, name .. "Marker" .. index, Vector3.new(1.4, 1.4, 1.4), center + offset, color, Enum.Material.SmoothPlastic, Enum.PartType.Ball)
		bubble.CanCollide = false
	end
end

local function sign(name, position, size, text, accent, facing)
	local boardSize = Vector3.new(size.X, math.min(size.Y, 3), size.Z)
	local boardPosition = Vector3.new(position.X, math.min(position.Y, 11.5), position.Z)
	local board = part(props, name, boardSize, boardPosition, colors.ink, Enum.Material.Metal)
	local postHeight = math.max(1, boardPosition.Y - boardSize.Y / 2 - 7.8)
	local postY = 7.8 + postHeight / 2
	local postOffset = math.max(1.5, math.min(5, boardSize.X * 0.28))
	for index, offset in ipairs({-postOffset, postOffset}) do
		part(props, name .. "Support" .. index, Vector3.new(0.55, postHeight, 0.55),
			Vector3.new(boardPosition.X + offset, postY, boardPosition.Z), colors.metal, Enum.Material.Metal)
	end
	local gui = Instance.new("SurfaceGui")
	gui.Face = facing or Enum.NormalId.Front
	gui.AlwaysOnTop = true
	gui.LightInfluence = 0
	gui.Parent = board
	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(0.94, 0.88)
	label.Position = UDim2.fromScale(0.03, 0.06)
	label.BackgroundTransparency = 1
	label.Text = text
	label.TextColor3 = accent
	label.TextScaled = true
	label.Font = Enum.Font.GothamBlack
	label.TextWrapped = true
	label.Parent = gui
	return board
end

-- A contained arena and a few tall silhouettes make the spawn camera read the space.
part(nil, "Arena", Vector3.new(180, 2, 120), Vector3.new(0, -1, 0), colors.ground, Enum.Material.Grass)

-- The courtyard is the top of a small floating island. Layered wedges, roots, and
-- narrow waterfalls sell the underside without adding a large physics-heavy mesh.
for index, item in ipairs({
	{"IslandDirtTop", Vector3.new(150, 8, 94), Vector3.new(0, -6, 0), Color3.fromRGB(126, 91, 54), Enum.PartType.Block},
	{"IslandRockCore", Vector3.new(112, 20, 74), Vector3.new(0, -18, 0), Color3.fromRGB(94, 82, 70), Enum.PartType.Wedge},
	{"IslandRockLeft", Vector3.new(46, 18, 42), Vector3.new(-48, -18, 6), Color3.fromRGB(109, 94, 75), Enum.PartType.Wedge},
	{"IslandRockRight", Vector3.new(46, 16, 40), Vector3.new(48, -20, -5), Color3.fromRGB(83, 77, 70), Enum.PartType.Wedge},
	{"IslandRockPoint", Vector3.new(34, 26, 30), Vector3.new(0, -31, 0), Color3.fromRGB(76, 72, 67), Enum.PartType.Wedge},
}) do
	part(props, item[1], item[2], item[3], item[4], Enum.Material.Ground, item[5])
end
for index, item in ipairs({
	{"RootLeft", Vector3.new(-58, 2, 0), Vector3.new(-52, -17, 0), Color3.fromRGB(77, 54, 35)},
	{"RootRight", Vector3.new(58, -1, -4), Vector3.new(52, -18, -4), Color3.fromRGB(77, 54, 35)},
	{"RootFront", Vector3.new(0, -2, 42), Vector3.new(0, -19, 34), Color3.fromRGB(86, 58, 35)},
}) do
	pipe(item[1], item[2], item[3], 2.8, item[4])
end
for index, item in ipairs({
	{"WaterfallLeft", Vector3.new(-62, -12, 20), Vector3.new(8, 20, 1), Color3.fromRGB(91, 186, 210)},
	{"WaterfallFront", Vector3.new(28, -13, 48), Vector3.new(6, 24, 1), Color3.fromRGB(91, 186, 210)},
	{"WaterfallRight", Vector3.new(67, -10, -18), Vector3.new(5, 18, 1), Color3.fromRGB(91, 186, 210)},
}) do
	local fall = part(props, item[1], item[3], item[2], item[4], Enum.Material.Water)
	fall.Transparency = 0.2
	fall.CanCollide = false
end

-- Raised circular plaza: two broad tiers and a dark inset floor give the vat a real footing.
part(props, "HubFoundation", Vector3.new(62, 3, 48), Vector3.new(0, 2, 0), colors.stone, Enum.Material.Slate)
part(props, "HubRoundTier", Vector3.new(56, 4, 56), Vector3.new(0, 4, 0), colors.stone, Enum.Material.Slate, Enum.PartType.Cylinder)
part(props, "HubRoundTrim", Vector3.new(48, 1, 48), Vector3.new(0, 6.5, 0), colors.stoneLight, Enum.Material.Concrete, Enum.PartType.Cylinder)
part(props, "HubFloor", Vector3.new(42, 0.8, 42), Vector3.new(0, 7.2, 0), colors.ink, Enum.Material.Metal, Enum.PartType.Cylinder)
for _, item in ipairs({
	{"HubStepNorth", Vector3.new(30, 1, 5), Vector3.new(0, 6, -25)},
	{"HubStepSouth", Vector3.new(30, 1, 5), Vector3.new(0, 6, 25)},
	{"HubStepWest", Vector3.new(5, 1, 22), Vector3.new(-25, 6, 0)},
	{"HubStepEast", Vector3.new(5, 1, 22), Vector3.new(25, 6, 0)},
}) do
	part(props, item[1], item[2], item[3], colors.stoneLight, Enum.Material.Concrete)
end

-- Paths are inset stone ribbons rather than a glowing grid.
for _, item in ipairs({
	{"GaragePath", Vector3.new(68, 0.5, 7), Vector3.new(-47, 5.5, 0), colors.orange},
	{"ForestPath", Vector3.new(68, 0.5, 7), Vector3.new(47, 5.5, 0), colors.cyan},
	{"SwampPath", Vector3.new(7, 0.5, 64), Vector3.new(0, 5.5, -45), colors.mint},
	{"LagoonPath", Vector3.new(7, 0.5, 64), Vector3.new(0, 5.5, 45), colors.cyan},
}) do
	tagged(props, item[1], item[2], item[3], colors.groundEdge, Enum.Material.Concrete, "ZonePath")
	local markerSize = item[2].X > item[2].Z and Vector3.new(2, 0.12, 4) or Vector3.new(4, 0.12, 2)
	for offset = -1, 1 do
		part(props, item[1] .. "Marker" .. offset, markerSize, item[3] + Vector3.new(item[2].X > item[2].Z and offset * 23 or 0, 0.32, item[2].X > item[2].Z and 0 or offset * 23), item[4], Enum.Material.SmoothPlastic)
	end
end

-- The central vat is intentionally layered: pedestal, bowl, thick rim, liquid, bubbles and pipes.
part(props, "VatPedestal", Vector3.new(20, 2, 20), Vector3.new(0, 8.4, 0), colors.metal, Enum.Material.Metal, Enum.PartType.Cylinder)
part(nil, "Reactor", Vector3.new(17, 10, 17), Vector3.new(0, 14, 0), colors.pink, Enum.Material.SmoothPlastic, Enum.PartType.Cylinder)
part(props, "VatRim", Vector3.new(20, 1.4, 20), Vector3.new(0, 19.1, 0), colors.gold, Enum.Material.Metal, Enum.PartType.Cylinder)
local liquid = part(props, "VatLiquid", Vector3.new(16, 0.35, 16), Vector3.new(0, 19.85, 0), colors.pink, Enum.Material.Neon, Enum.PartType.Cylinder)
light(liquid, colors.pink, 18, 1.2)
tagged(vats, "CentralJuiceVatLocation", Vector3.new(8, 0.25, 8), Vector3.new(0, 20, 0), colors.pink, Enum.Material.SmoothPlastic, "VatLocation")
for index, position in ipairs({
	Vector3.new(-4, 20.5, -2), Vector3.new(3, 20.6, 2), Vector3.new(0, 21.2, -4),
	Vector3.new(5, 20.4, -4), Vector3.new(-2, 20.7, 4),
}) do
	local bubble = part(props, "VatBubble" .. index, Vector3.new(1.4, 1.4, 1.4), position, colors.gold, Enum.Material.Neon, Enum.PartType.Ball)
	bubble.CanCollide = false
end
for _, x in ipairs({-9, 9}) do
	part(props, "VatPipe" .. x, Vector3.new(2, 11, 2), Vector3.new(x, 13, 0), colors.metal, Enum.Material.Metal, Enum.PartType.Cylinder)
	part(props, "VatPipeCap" .. x, Vector3.new(3, 2, 3), Vector3.new(x, 18.5, 0), colors.gold, Enum.Material.Metal, Enum.PartType.Cylinder)
end
part(props, "VatGauge", Vector3.new(3.5, 0.6, 3.5), Vector3.new(0, 22.2, 8.8), colors.stoneLight, Enum.Material.Metal, Enum.PartType.Cylinder)
part(props, "VatGaugeNeedle", Vector3.new(0.25, 0.25, 1.4), Vector3.new(0, 22.6, 8.8), colors.pink, Enum.Material.Neon)
sign("VatSign", Vector3.new(0, 10.8, 13), Vector3.new(30, 3, 0.6), "JUICE VAT\nSLURP YOUR BRAIN", colors.pink)

-- Readable workshop massing flanks the plaza.
local function workshop(name, center, accent, title)
	part(props, name .. "Body", Vector3.new(18, 10, 14), center + Vector3.new(0, 5, 0), colors.metal, Enum.Material.Metal)
	part(props, name .. "Roof", Vector3.new(21, 2, 17), center + Vector3.new(0, 11, 0), accent, Enum.Material.Slate)
	part(props, name .. "Door", Vector3.new(7, 7, 0.6), center + Vector3.new(0, 3.5, 7.3), colors.ink, Enum.Material.Metal)
	part(props, name .. "DoorGlow", Vector3.new(5, 0.35, 0.3), center + Vector3.new(0, 1, 7.7), accent, Enum.Material.Neon)
	sign(name .. "Sign", center + Vector3.new(0, 14, 7.8), Vector3.new(15, 4, 0.5), title, accent)
end
workshop("TurboWorkshop", Vector3.new(27, 7, -10), colors.purple, "TURBO LAB\nMORE BAG • MORE ZOOM")
workshop("GoblinWorkshop", Vector3.new(-27, 7, -10), colors.orange, "GOBLIN GARAGE\nFIX IT WITH JUICE")
local terminal = part(nil, "TurboTerminal", Vector3.new(7, 7, 7), Vector3.new(27, 11, -1), colors.purple, Enum.Material.SmoothPlastic)
light(terminal, colors.purple, 14, 1.5)

-- Zone portals use chunky stone posts and a single restrained luminous keystone.
local function zone(name, center, accent, subtitle)
	local pad = tagged(props, name .. "Platform", Vector3.new(34, 1, 28), center, colors.stone, Enum.Material.Slate, "ZonePlatform")
	pad.Transparency = 0.04
	local postOffset = Vector3.new(10, 7, 9)
	for index, dx in ipairs({-1, 1}) do
		part(portals, name .. "PortalPost" .. index, Vector3.new(4, 14, 4), center + Vector3.new(dx * postOffset.X, 7, postOffset.Z), colors.stoneLight, Enum.Material.Concrete)
	end
	part(portals, name .. "PortalLintel", Vector3.new(24, 4, 4), center + Vector3.new(0, 14, postOffset.Z), colors.stoneLight, Enum.Material.Concrete)
	local keystone = tagged(portals, name .. "Portal", Vector3.new(5, 2, 2), center + Vector3.new(0, 14, postOffset.Z), accent, Enum.Material.Neon, "ZonePortal")
	local gate = tagged(portals, name .. "PhysicalGate", Vector3.new(2, 8, 2), center + Vector3.new(-7, 7, postOffset.Z), accent, Enum.Material.Metal, "ZonePortal")
	local gate2 = tagged(portals, name .. "PhysicalGate2", Vector3.new(2, 8, 2), center + Vector3.new(7, 7, postOffset.Z), accent, Enum.Material.Metal, "ZonePortal")
	pipe(name .. "GateBar", center + Vector3.new(-7, 11, postOffset.Z), center + Vector3.new(7, 11, postOffset.Z), 1.2, accent)
	sign(name .. "Sign", center + Vector3.new(0, 19, postOffset.Z + 0.3), Vector3.new(26, 5, 0.5), name:upper() .. "\n" .. subtitle, accent)
	local region = tagged(bubbleRegions, name .. "BubbleField", Vector3.new(28, 0.3, 20), center + Vector3.new(0, 1, -4), accent, Enum.Material.SmoothPlastic, "BubbleSpawnRegion")
	region.Transparency = 0.88
	region.CanCollide = false
end
zone("Goblin Garage", Vector3.new(-64, 2, 0), colors.orange, "FIX IT WITH JUICE")
zone("Static Swamp", Vector3.new(0, 2, -55), colors.mint, "DO NOT LICK THE FOG")
zone("Error Forest", Vector3.new(64, 2, 0), colors.cyan, "TREES HAVE COMMIT RIGHTS")
zone("Lag Lagoon", Vector3.new(0, 2, 55), colors.cyan, "BUFFERING SINCE 1999")
zone("Forbidden Server Room", Vector3.new(58, 2, -42), colors.pink, "AUTHORIZED GOBLINS ONLY")

-- Four corner beacons establish depth behind the central silhouette.
for index, position in ipairs({
	Vector3.new(-76, 10, -47), Vector3.new(76, 10, -47),
	Vector3.new(-76, 10, 47), Vector3.new(76, 10, 47),
}) do
	part(nil, "Beacon" .. index, Vector3.new(6, 20, 6), position, colors.stoneLight, Enum.Material.Concrete)
	part(nil, "BeaconCap" .. index, Vector3.new(8, 1.5, 8), position + Vector3.new(0, 10.8, 0), index % 2 == 0 and colors.cyan or colors.purple, Enum.Material.Neon, Enum.PartType.Cylinder)
end

local spawnPad = tagged(spawns, "MainPlayerSpawn", Vector3.new(14, 1, 14), Vector3.new(0, 8, 39), colors.cyan, Enum.Material.Metal, "PlayerSpawn")
part(props, "SpawnInset", Vector3.new(10, 0.25, 10), Vector3.new(0, 8.65, 39), colors.cyan, Enum.Material.Neon, Enum.PartType.Cylinder)
light(spawnPad, colors.cyan, 18, 1.4)
sign("WelcomeSign", Vector3.new(0, 19, 50), Vector3.new(42, 8, 0.8), "GLITCH GOBLIN SIMULATOR\nABSORB  •  JUICE  •  UPGRADE", colors.cyan)

-- Kept as a named landmark for the existing cave prompt in Main.server.lua.
local gate = part(nil, "GlitchGate", Vector3.new(4, 16, 30), Vector3.new(78, 11, 0), colors.pink, Enum.Material.ForceField)
gate.Transparency = 0.12
sign("CaveSign", Vector3.new(75, 20, 0), Vector3.new(0.6, 8, 30), "LOCKED GLITCH CAVE\n500 JUICE TO ENTER", colors.pink, Enum.NormalId.Left)

-- Layered courtyard enclosure: stepped rock, scrap retaining walls, and service pipes
-- keep the playable footprint compact without making the horizon a flat box.
for index, item in ipairs({
	{"CliffNorthLow", Vector3.new(180, 10, 8), Vector3.new(0, 5, -56), colors.groundEdge},
	{"CliffWestLow", Vector3.new(8, 10, 120), Vector3.new(-86, 5, 0), colors.groundEdge},
	{"ScrapSouthWall", Vector3.new(150, 8, 5), Vector3.new(0, 4, 57), colors.metal},
}) do
	part(props, item[1], item[2], item[3], item[4], Enum.Material.Concrete)
end
for index, position in ipairs({
	Vector3.new(-65, 17, -61), Vector3.new(-35, 20, -62), Vector3.new(35, 17, -62),
	Vector3.new(68, 20, -61), Vector3.new(-91, 16, -36), Vector3.new(-92, 19, 28),
}) do
	part(props, "CliffRock" .. index, Vector3.new(12, 10, 10), position, colors.stoneLight, Enum.Material.Slate, Enum.PartType.Wedge)
end
pipe("NorthServicePipe", Vector3.new(-54, 9, -51), Vector3.new(-54, 17, -61), 2, colors.orange)
pipe("NorthServicePipeRun", Vector3.new(-54, 17, -61), Vector3.new(-18, 17, -61), 2, colors.orange)
pipe("WestServicePipe", Vector3.new(-82, 9, -35), Vector3.new(-91, 9, -35), 2, colors.mint)

-- The Turbo terminal reads as a glass machine rather than a colored cube.
part(props, "TurboMachineBase", Vector3.new(13, 2, 11), Vector3.new(27, 8, -1), colors.metal, Enum.Material.Metal)
local turboGlass = part(props, "TurboBrainGlass", Vector3.new(8, 9, 8), Vector3.new(27, 14, -1), Color3.fromRGB(130, 190, 255), Enum.Material.Glass, Enum.PartType.Cylinder)
turboGlass.Transparency = 0.38
turboGlass.CanCollide = false
local turboBrain = part(props, "TurboBrainCore", Vector3.new(4, 4, 4), Vector3.new(27, 14, -1), colors.purple, Enum.Material.SmoothPlastic, Enum.PartType.Ball)
turboBrain.CanCollide = false
light(turboBrain, colors.purple, 12, 1)
pipe("TurboPipeL", Vector3.new(22, 9, -4), Vector3.new(24, 13, -1), 1, colors.cyan)
pipe("TurboPipeR", Vector3.new(32, 9, -4), Vector3.new(30, 13, -1), 1, colors.cyan)
sign("TurboMachineLabel", Vector3.new(27, 20, 3.2), Vector3.new(14, 3, 0.5), "TURBO BRAIN", colors.cyan)

-- A short tutorial board is grounded beside the spawn platform, facing the arrival path.
part(props, "TutorialBoardPost", Vector3.new(1, 7, 1), Vector3.new(-10, 11, 39), colors.metal, Enum.Material.Metal)
sign("TutorialBoard", Vector3.new(-10, 15, 39), Vector3.new(16, 5, 0.6), "1 ABSORB\n2 JUICE VAT\n3 UPGRADE", colors.gold)

-- Organized visual bubble fields make the collectible loop legible before the first pickup.
bubbleCluster("GarageCluster", Vector3.new(-52, 7, 12), colors.orange)
bubbleCluster("SwampCluster", Vector3.new(-15, 7, -39), colors.mint)
bubbleCluster("ForestCluster", Vector3.new(52, 7, 12), colors.cyan)
bubbleCluster("LagoonCluster", Vector3.new(15, 7, 39), colors.cyan)
for index, item in ipairs({
	{"SwampMushroom", Vector3.new(-12, 6, -47), colors.mint},
	{"SwampMushroom2", Vector3.new(7, 6, -49), colors.pink},
	{"ForestMushroom", Vector3.new(53, 6, -10), colors.cyan},
	{"ForestMushroom2", Vector3.new(70, 6, 12), colors.orange},
}) do
	mushroom(item[1], item[2], item[3])
end

-- A few non-emissive props break up the horizon without making a grid.
for _, item in ipairs({
	{"GarageCrate", Vector3.new(-72, 8, -8), Vector3.new(7, 7, 7), colors.orange, Enum.PartType.Block},
	{"SwampCrystal", Vector3.new(-8, 7, -55), Vector3.new(6, 8, 6), colors.mint, Enum.PartType.Wedge},
	{"ForestPine", Vector3.new(70, 9, 8), Vector3.new(6, 10, 6), colors.cyan, Enum.PartType.Cylinder},
	{"LagBuoy", Vector3.new(8, 7, 58), Vector3.new(6, 6, 6), colors.cyan, Enum.PartType.Ball},
	{"ServerRack", Vector3.new(58, 9, -52), Vector3.new(7, 10, 5), colors.pink, Enum.PartType.Block},
}) do
	local prop = tagged(props, item[1], item[3], item[2], item[4], Enum.Material.SmoothPlastic, "LowPolyProp", item[5])
	prop.CanCollide = true
end

-- Meadow clumps and small debris islands give the open fields a grounded,
-- hand-placed silhouette while keeping sightlines clear for mobile players.
for index, item in ipairs({
	{"MeadowEast", Vector3.new(42, 7.8, 20), Vector3.new(16, 0.35, 10)},
	{"MeadowWest", Vector3.new(-43, 7.8, 20), Vector3.new(14, 0.35, 9)},
	{"MeadowNorth", Vector3.new(20, 7.8, -35), Vector3.new(12, 0.35, 9)},
}) do
	local patch = tagged(props, item[1], item[3], item[2], Color3.fromRGB(125, 176, 77), Enum.Material.Grass, "MeadowCluster")
	patch.CanCollide = false
end
for index, item in ipairs({
	{"SkyDebrisA", Vector3.new(-66, 34, -30), Vector3.new(10, 4, 7)},
	{"SkyDebrisB", Vector3.new(72, 30, 30), Vector3.new(8, 3, 6)},
	{"SkyRock", Vector3.new(12, 38, -72), Vector3.new(7, 5, 7)},
}) do
	local debris = tagged(props, item[1], item[3], item[2], colors.stoneLight, Enum.Material.Slate, "SkyProp", Enum.PartType.Wedge)
	debris.CanCollide = false
end

local lighting = game:GetService("Lighting")
-- Lighting.Technology is Studio-only and cannot be assigned by a published Script.
-- Set it manually in Studio when authoring the place; runtime-safe lighting values follow.
lighting.ClockTime = 14.5
lighting.Brightness = 2.2
lighting.GlobalShadows = true
lighting.Ambient = Color3.fromRGB(75, 85, 100)
lighting.OutdoorAmbient = Color3.fromRGB(130, 140, 150)
lighting.ExposureCompensation = 0.1
lighting.FogColor = Color3.fromRGB(205, 226, 238)
lighting.FogEnd = 1500
local atmosphere = lighting:FindFirstChild("GoblinNeonAtmosphere") or Instance.new("Atmosphere")
atmosphere.Name = "GoblinNeonAtmosphere"
atmosphere.Density = 0.18
atmosphere.Offset = 0.1
atmosphere.Height = 1500
atmosphere.Color = Color3.fromRGB(190, 220, 235)
atmosphere.Decay = Color3.fromRGB(190, 220, 235)
atmosphere.Glare = 0
atmosphere.Haze = 3
atmosphere.Parent = lighting
local bloom = lighting:FindFirstChild("GoblinCourtyardBloom") or Instance.new("BloomEffect")
bloom.Name = "GoblinCourtyardBloom"
bloom.Intensity = 0.4
bloom.Size = 24
bloom.Threshold = 1.5
bloom.Parent = lighting
local colorCorrection = lighting:FindFirstChild("GoblinCourtyardColor") or Instance.new("ColorCorrectionEffect")
colorCorrection.Name = "GoblinCourtyardColor"
colorCorrection.Brightness = 0
colorCorrection.Contrast = 0.12
colorCorrection.Saturation = 0.15
colorCorrection.TintColor = Color3.fromRGB(255, 255, 255)
colorCorrection.Parent = lighting
local sunRays = lighting:FindFirstChild("GoblinSunRays") or Instance.new("SunRaysEffect")
sunRays.Name = "GoblinSunRays"
sunRays.Intensity = 0.1
sunRays.Parent = lighting
local depthOfField = lighting:FindFirstChildOfClass("DepthOfFieldEffect")
if depthOfField then
	depthOfField.Enabled = false
end
