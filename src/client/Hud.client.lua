local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")
local MarketplaceService = game:GetService("MarketplaceService")

local player = Players.LocalPlayer
local Config = require(ReplicatedStorage.Shared.GameConfig)
local remotes = ReplicatedStorage:WaitForChild("Remotes")
local stateEvent = remotes:WaitForChild("StateChanged")
local toastEvent = remotes:WaitForChild("Toast")

local gui = Instance.new("ScreenGui")
gui.Name = "GlitchGoblinHUD"
gui.ResetOnSpawn = false
gui.IgnoreGuiInset = true
gui.Parent = player:WaitForChild("PlayerGui")

local panel = Instance.new("Frame")
panel.Size = UDim2.fromScale(0.31, 0.22)
panel.Position = UDim2.fromScale(0.025, 0.04)
panel.BackgroundColor3 = Color3.fromRGB(12, 18, 38)
panel.BackgroundTransparency = 0.08
panel.Parent = gui
Instance.new("UICorner", panel).CornerRadius = UDim.new(0, 14)
local stroke = Instance.new("UIStroke", panel)
stroke.Color = Color3.fromRGB(75, 230, 255)
stroke.Thickness = 2

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -24, 0, 30)
title.Position = UDim2.fromOffset(12, 8)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBlack
title.Text = "GLITCH GOBLIN SIM"
title.TextColor3 = Color3.fromRGB(91, 232, 255)
title.TextScaled = true
title.TextXAlignment = Enum.TextXAlignment.Left
title.Parent = panel

local stats = Instance.new("TextLabel")
stats.Size = UDim2.new(1, -24, 1, -54)
stats.Position = UDim2.fromOffset(12, 43)
stats.BackgroundTransparency = 1
stats.Font = Enum.Font.GothamBold
stats.TextColor3 = Color3.fromRGB(236, 242, 255)
stats.TextSize = 16
stats.TextWrapped = true
stats.TextXAlignment = Enum.TextXAlignment.Left
stats.TextYAlignment = Enum.TextYAlignment.Top
stats.Text = "Connecting to goblin brain..."
stats.Parent = panel

local boostButton = Instance.new("TextButton")
boostButton.Size = UDim2.fromOffset(150, 34)
boostButton.Position = UDim2.new(1, -166, 0, 42)
boostButton.BackgroundColor3 = Color3.fromRGB(255, 190, 74)
boostButton.Font = Enum.Font.GothamBlack
boostButton.Text = "GET 2X JUICE"
boostButton.TextColor3 = Color3.fromRGB(26, 22, 38)
boostButton.TextScaled = true
boostButton.Parent = panel
Instance.new("UICorner", boostButton).CornerRadius = UDim.new(0, 8)
boostButton.Visible = Config.BoostProductId > 0
boostButton.Activated:Connect(function()
	if Config.BoostProductId > 0 then MarketplaceService:PromptProductPurchase(player, Config.BoostProductId) end
end)

local timer = Instance.new("TextLabel")
timer.Size = UDim2.fromScale(0.5, 0.05)
timer.Position = UDim2.fromScale(0.25, 0.94)
timer.BackgroundTransparency = 1
timer.Font = Enum.Font.GothamBlack
timer.TextColor3 = Color3.fromRGB(255, 192, 92)
timer.TextScaled = true
timer.Parent = gui

local toast = Instance.new("TextLabel")
toast.Size = UDim2.fromScale(0.6, 0.065)
toast.Position = UDim2.fromScale(0.2, 0.84)
toast.BackgroundColor3 = Color3.fromRGB(20, 28, 55)
toast.BackgroundTransparency = 1
toast.Font = Enum.Font.GothamBold
toast.TextColor3 = Color3.new(1, 1, 1)
toast.TextScaled = true
toast.TextTransparency = 1
toast.Parent = gui
Instance.new("UICorner", toast).CornerRadius = UDim.new(0, 12)

local state
local roundEndsAt = 0
local function fmt(seconds)
	return string.format("%02d:%02d", math.floor(math.max(0, seconds) / 60), math.max(0, seconds) % 60)
end

stateEvent.OnClientEvent:Connect(function(profile, endsAt)
	state, roundEndsAt = profile, endsAt or roundEndsAt
	local turboText = "Turbo: OFF"
	if profile.turboUntil > os.time() then
		turboText = string.format("Turbo Brain %d: %s", profile.turboTier, fmt(profile.turboUntil - os.time()))
	end
	local boostText = profile.boostUntil > os.time() and "  •  2X JUICE " .. fmt(profile.boostUntil - os.time()) or ""
	local caveText = profile.zoneUnlocked and "Cave: OPEN" or "Cave: LOCKED (500)"
	stats.Text = string.format("🫧 Bubbles  %d / %d   (%d juice)\n💰 Goblin Juice  %d\n⚡ %s%s\n🗺 %s", profile.carried, profile.capacity or Config.StartingCapacity, profile.carriedValue, profile.credits, turboText, boostText, caveText)
end)

toastEvent.OnClientEvent:Connect(function(message, color)
	toast.Text = message
	toast.TextColor3 = color or Color3.new(1, 1, 1)
	TweenService:Create(toast, TweenInfo.new(0.18), {TextTransparency = 0, BackgroundTransparency = 0.1}):Play()
	task.delay(2.8, function()
		TweenService:Create(toast, TweenInfo.new(0.35), {TextTransparency = 1, BackgroundTransparency = 1}):Play()
	end)
end)

task.spawn(function()
	while true do
		timer.Text = "GOBLIN RUN  " .. fmt(roundEndsAt - os.time()) .. "   •   ABSORB → VAT → TURBO"
		task.wait(1)
	end
end)
