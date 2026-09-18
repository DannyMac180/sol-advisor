local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local MarketplaceService = game:GetService("MarketplaceService")
local DataStoreService = game:GetService("DataStoreService")
local RunService = game:GetService("RunService")

local Config = require(ReplicatedStorage.Shared.GameConfig)
local profileStore
local dataStoreReady = false
-- DataStore calls are deliberately disabled in Studio so local play never needs publishing/API access.
if not RunService:IsStudio() then
	profileStore = DataStoreService:GetDataStore("GlitchGoblinProfilesV2")
	dataStoreReady = true
end

local remotes = ReplicatedStorage:FindFirstChild("Remotes") or Instance.new("Folder")
remotes.Name = "Remotes"
remotes.Parent = ReplicatedStorage
local stateEvent = remotes:FindFirstChild("StateChanged") or Instance.new("RemoteEvent")
stateEvent.Name = "StateChanged"
stateEvent.Parent = remotes
local toastEvent = remotes:FindFirstChild("Toast") or Instance.new("RemoteEvent")
toastEvent.Name = "Toast"
toastEvent.Parent = remotes

local profiles = {}
local roundEndsAt = 0
local roundScores = {}
local bubbleParts = {}

local function notify(player, text, color)
	toastEvent:FireClient(player, text, color or Color3.new(1, 1, 1))
end

local function makePart(parent, name, size, position, color, material)
	local part = Instance.new("Part")
	part.Name = name
	part.Size = size
	part.Position = position
	part.Anchored = true
	part.Color = color
	part.Material = material or Enum.Material.Neon
	part.TopSurface = Enum.SurfaceType.Smooth
	part.BottomSurface = Enum.SurfaceType.Smooth
	part.Parent = parent
	return part
end

local function labelPart(parent, name, position, text, color)
	local sign = makePart(parent, name, Vector3.new(24, 6, 0.5), position, Color3.fromRGB(15, 20, 42), Enum.Material.Metal)
	local gui = Instance.new("SurfaceGui")
	gui.Face = Enum.NormalId.Front
	gui.AlwaysOnTop = true
	gui.Parent = sign
	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(1, 1)
	label.BackgroundTransparency = 1
	label.Text = text
	label.TextColor3 = color
	label.TextScaled = true
	label.Font = Enum.Font.GothamBlack
	label.Parent = gui
	return sign
end

local function currentTier(profile)
	if profile.turboUntil > os.time() then return Config.TurboTiers[profile.turboTier] end
	return nil
end

local function capacity(profile)
	local tier = currentTier(profile)
	return tier and tier.Capacity or Config.StartingCapacity
end

local function sendState(player)
	local profile = profiles[player]
	if profile then
		profile.capacity = capacity(profile)
		stateEvent:FireClient(player, profile, roundEndsAt)
	end
end

local function bubbleValue(profile, bubble)
	local value = bubble:GetAttribute("BubbleValue") or 1
	local tier = currentTier(profile)
	local multiplier = tier and tier.ValueMultiplier or 1
	if profile.boostUntil > os.time() then multiplier *= Config.BoostMultiplier end
	return math.floor(value * multiplier)
end

local function buildBubble(parent, index, position, rarity, value, color)
	local bubble = makePart(parent, "BrainBubble" .. index, Vector3.new(3, 3, 3), position, color, Enum.Material.Neon)
	bubble.Shape = Enum.PartType.Ball
	bubble.CanCollide = false
	bubble:SetAttribute("Rarity", rarity)
	bubble:SetAttribute("BubbleValue", value)
	local light = Instance.new("PointLight")
	light.Color = color
	light.Range = 12
	light.Brightness = 1.5
	light.Parent = bubble
	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Absorb"
	prompt.ObjectText = rarity .. " Brain Bubble  [" .. value .. " juice]"
	prompt.HoldDuration = 0.12
	prompt.MaxActivationDistance = 10
	prompt.Parent = bubble
	prompt.Triggered:Connect(function(player)
		local profile = profiles[player]
		if not profile or bubble.Transparency > 0.5 then return end
		if profile.carried >= capacity(profile) then
			notify(player, "Your goblin brain-bag is full! Juice it at the vat.", Color3.fromRGB(255, 180, 120))
			return
		end
		bubble.Transparency = 1
		prompt.Enabled = false
		profile.carried += 1
		profile.carriedValue += value
		sendState(player)
		task.delay(Config.BubbleRespawnSeconds, function()
			if bubble.Parent then
				bubble.Transparency = 0
				prompt.Enabled = true
			end
		end)
	end)
	table.insert(bubbleParts, bubble)
end

local function buildMap()
	local map = workspace:FindFirstChild("NeonCourierMap") or Instance.new("Folder")
	map.Name = "NeonCourierMap"
	map.Parent = workspace

	-- A small hub gives every interaction a readable landmark and keeps the prototype playable without assets.
	local vat = map:FindFirstChild("Reactor") or makePart(map, "Reactor", Vector3.new(16, 6, 16), Vector3.new(0, 5, 0), Color3.fromRGB(255, 65, 180))
	local vatPrompt = vat:FindFirstChildOfClass("ProximityPrompt") or Instance.new("ProximityPrompt")
	vatPrompt.ActionText = "Juice bubbles"
	vatPrompt.ObjectText = "Goblin Juice Vat"
	vatPrompt.HoldDuration = 0.35
	vatPrompt.MaxActivationDistance = 14
	vatPrompt.Parent = vat
	vatPrompt.Triggered:Connect(function(player)
		local profile = profiles[player]
		if not profile or profile.carried <= 0 then
			notify(player, "The vat is thirsty. Bring it Brain Bubbles!", Color3.fromRGB(255, 180, 120))
			return
		end
		local delivered = profile.carried
		local value = profile.carriedValue
		profile.carried, profile.carriedValue = 0, 0
		profile.delivered += delivered
		profile.credits += math.floor(value * (profile.boostUntil > os.time() and Config.BoostMultiplier or 1) * (currentTier(profile) and currentTier(profile).ValueMultiplier or 1))
		roundScores[player] = (roundScores[player] or 0) + delivered
		notify(player, string.format("Slurp! %d bubbles became %d Goblin Juice.", delivered, profile.credits), Color3.fromRGB(100, 255, 190))
		sendState(player)
	end)

	local terminal = map:FindFirstChild("TurboTerminal") or makePart(map, "TurboTerminal", Vector3.new(7, 7, 7), Vector3.new(28, 3.5, 0), Color3.fromRGB(119, 76, 255))
	local terminalPrompt = terminal:FindFirstChildOfClass("ProximityPrompt") or Instance.new("ProximityPrompt")
	terminalPrompt.ActionText = "Upgrade Turbo Brain"
	terminalPrompt.ObjectText = "Turbo Brain Lab"
	terminalPrompt.HoldDuration = 0.4
	terminalPrompt.MaxActivationDistance = 12
	terminalPrompt.Parent = terminal
	terminalPrompt.Triggered:Connect(function(player)
		local profile = profiles[player]
		if not profile then return end
		local nextTier = math.min(profile.turboTier + 1, #Config.TurboTiers)
		if profile.turboUntil > os.time() and profile.turboTier >= #Config.TurboTiers then
			notify(player, "Turbo Brain is already dangerously turbo.", Color3.fromRGB(220, 170, 255))
			return
		end
		local tier = Config.TurboTiers[nextTier]
		if profile.credits < tier.Cost then
			notify(player, string.format("Need %d more Goblin Juice.", tier.Cost - profile.credits), Color3.fromRGB(255, 150, 120))
			return
		end
		profile.credits -= tier.Cost
		profile.turboTier, profile.turboUntil = nextTier, os.time() + tier.Duration
		local humanoid = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
		if humanoid then humanoid.WalkSpeed = tier.WalkSpeed end
		notify(player, string.format("TURBO BRAIN %d! Bag %d, value %.1fx.", nextTier, tier.Capacity, tier.ValueMultiplier), Color3.fromRGB(200, 150, 255))
		sendState(player)
	end)

	local gate = map:FindFirstChild("GlitchGate") or makePart(map, "GlitchGate", Vector3.new(4, 16, 30), Vector3.new(78, 8, 0), Color3.fromRGB(255, 90, 120), Enum.Material.ForceField)
	local gatePrompt = gate:FindFirstChildOfClass("ProximityPrompt") or Instance.new("ProximityPrompt")
	gatePrompt.ActionText = "Unlock"
	gatePrompt.ObjectText = "Glitch Cave — 500 Juice"
	gatePrompt.HoldDuration = 0.5
	gatePrompt.Parent = gate
	gatePrompt.Triggered:Connect(function(player)
		local profile = profiles[player]
		if not profile then return end
		if profile.zoneUnlocked then
			notify(player, "The glitch cave is open. Go get weird!", Color3.fromRGB(100, 255, 190))
		elseif profile.credits >= Config.ZoneUnlockCost then
			profile.credits -= Config.ZoneUnlockCost
			profile.zoneUnlocked = true
			gate.CanCollide, gate.Transparency = false, 0.75
			gatePrompt.Enabled = false
			notify(player, "GLITCH CAVE UNLOCKED! Rare bubbles detected.", Color3.fromRGB(255, 110, 220))
			sendState(player)
		else
			notify(player, "The cave wants 500 Goblin Juice. Goblin capitalism!", Color3.fromRGB(255, 150, 120))
		end
	end)

	labelPart(map, "VatSign", Vector3.new(0, 13, 12), "JUICE VAT\nSLURP YOUR BRAIN", Color3.fromRGB(255, 110, 210))
	labelPart(map, "TurboSign", Vector3.new(28, 12, -9), "TURBO LAB\nMORE BAG • MORE ZOOM", Color3.fromRGB(190, 140, 255))
	labelPart(map, "CaveSign", Vector3.new(76, 15, 0), "LOCKED GLITCH CAVE\n500 JUICE TO ENTER", Color3.fromRGB(255, 120, 140))

	for index = 1, 18 do
		local angle = index / 18 * math.pi * 2
		local rare = index % 6 == 0
		buildBubble(map, index, Vector3.new(rare and 84 or math.cos(angle) * 56, 3, math.sin(angle) * 42), rare and "EPIC" or (index % 3 == 0 and "RARE" or "COMMON"), rare and 35 or (index % 3 == 0 and 12 or 4), rare and Color3.fromRGB(255, 80, 220) or (index % 3 == 0 and Color3.fromRGB(80, 180, 255) or Color3.fromRGB(255, 218, 72)))
	end
end

local function loadProfile(player)
	local profile = { credits = Config.StartingCredits, carried = 0, carriedValue = 0, delivered = 0, boostUntil = 0, turboTier = 0, turboUntil = 0, zoneUnlocked = false }
	if dataStoreReady then
		local success, saved = pcall(function() return profileStore:GetAsync("player_" .. player.UserId) end)
		if success and type(saved) == "table" then
			profile.credits = tonumber(saved.credits) or profile.credits
			profile.zoneUnlocked = saved.zoneUnlocked == true
		end
	end
	profiles[player], roundScores[player] = profile, 0
	return profile
end

local function saveProfile(player)
	local profile = profiles[player]
	if not profile or not dataStoreReady then return end
	pcall(function()
		profileStore:UpdateAsync("player_" .. player.UserId, function(previous)
			previous = type(previous) == "table" and previous or {}
			previous.credits, previous.zoneUnlocked = profile.credits, profile.zoneUnlocked
			return previous
		end)
	end)
end

local function beginRound()
	roundEndsAt = os.time() + Config.RoundSeconds
	for player, profile in pairs(profiles) do
		profile.carried, profile.carriedValue, profile.delivered = 0, 0, 0
		roundScores[player] = 0
		sendState(player)
		notify(player, "New goblin run! Absorb, juice, upgrade.", Color3.fromRGB(100, 220, 255))
	end
end

buildMap()
beginRound()
Players.PlayerAdded:Connect(function(player)
	local profile = loadProfile(player)
	local gate = workspace.NeonCourierMap:FindFirstChild("GlitchGate")
	if gate and profile.zoneUnlocked then
		gate.CanCollide = false
		gate.Transparency = 0.75
		local prompt = gate:FindFirstChildOfClass("ProximityPrompt")
		if prompt then prompt.Enabled = false end
	end
	player.CharacterAdded:Connect(function(character)
		local humanoid = character:WaitForChild("Humanoid")
		local tier = currentTier(profiles[player])
		humanoid.WalkSpeed = tier and tier.WalkSpeed or 16
	end)
	sendState(player)
end)
Players.PlayerRemoving:Connect(function(player)
	saveProfile(player)
	profiles[player], roundScores[player] = nil, nil
end)

MarketplaceService.ProcessReceipt = function(receipt)
	if receipt.ProductId ~= Config.BoostProductId or Config.BoostProductId == 0 then return Enum.ProductPurchaseDecision.NotProcessedYet end
	local player = Players:GetPlayerByUserId(receipt.PlayerId)
	if not player or not profiles[player] then return Enum.ProductPurchaseDecision.NotProcessedYet end
	profiles[player].boostUntil = os.time() + Config.BoostDurationSeconds
	notify(player, "2x Goblin Juice activated for 10 minutes!", Color3.fromRGB(255, 220, 90))
	sendState(player)
	return Enum.ProductPurchaseDecision.PurchaseGranted
end

task.spawn(function()
	while true do
		task.wait(1)
		for player, profile in pairs(profiles) do
			local tier = currentTier(profile)
			local humanoid = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
			if humanoid then humanoid.WalkSpeed = tier and tier.WalkSpeed or 16 end
			sendState(player)
		end
		if os.time() >= roundEndsAt then beginRound() end
	end
end)

game:BindToClose(function()
	for _, player in Players:GetPlayers() do saveProfile(player) end
end)
