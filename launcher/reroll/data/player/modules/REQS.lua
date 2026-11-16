------------------------------------
--ACTION_ARM_R1 = 0
--ACTION_ARM_R2 = 1
--ACTION_ARM_L1 = 2
--ACTION_ARM_L2 = 3
--ACTION_ARM_ACTION = 4
--ACTION_ARM_SP_MOVE = 5
--ACTION_ARM_CHANGE_STYLE = 6
--ACTION_ARM_USE_ITEM = 7
--ACTION_ARM_SWITCH_FORM = 8
--ACTION_ARM_CHANGE_WEAPON_R = 9
--ACTION_ARM_CHANGE_WEAPON_L = 10
--ACTION_ARM_CHANGE_ITEM =  11
--ACTION_ARM_R3 = 12
--ACTION_ARM_L3 = 13
--14
--15
--ACTION_ARM_BACKSTEP = 16
--ACTION_ARM_ROLLING = 17
--
--
--
--ACTION_ARM_GESTURE = 21
--
--
--
--
--ACTION_ARM_LIGHT_KICK = 26
--ACTION_ARM_HEAVY_KICK = 27
------------------------------------
function Include(funct, addition)
    local prefunct = funct
    return function(...)
	addition(...)
	return prefunct(...)
    end
end

--w  rite
--a  ppend
--r  ead
--b  inary
function Write(file, content)
    local f = io.open(file, "w")
    f:write(content)
    io.close(f)
end

function Exists(file)
        local f = io.open(file, "r")
        if f then
            io.close(f)
            return true
        else
            return false
        end
end
------------
g_DeltaRunTime = 0
------------
local Dt_ACTION_ARM_R1 = 0
local Dt_ACTION_ARM_R2 = 0
local Dt_ACTION_ARM_L1 = 0
local Dt_ACTION_ARM_L2 = 0
local Dt_ACTION_ARM_ACTION = 0
local Dt_ACTION_ARM_SP_MOVE = 0
local Dt_ACTION_ARM_CHANGE_STYLE = 0
local Dt_ACTION_ARM_USE_ITEM = 0
local Dt_ACTION_ARM_SWITCH_FORM = 0
local Dt_ACTION_ARM_CHANGE_WEAPON_R = 0
local Dt_ACTION_ARM_CHANGE_WEAPON_L = 0
local Dt_ACTION_ARM_CHANGE_ITEM = 0
local Dt_ACTION_ARM_R3 = 0
local Dt_ACTION_ARM_L3 = 0
------------
local bu_ACTION_ARM_R1 = 0
local bu_ACTION_ARM_R2 = 0
local bu_ACTION_ARM_L1 = 0
local bu_ACTION_ARM_L2 = 0
local bu_ACTION_ARM_ACTION = 0
local bu_ACTION_ARM_SP_MOVE = 0
local bu_ACTION_ARM_CHANGE_STYLE = 0
local bu_ACTION_ARM_USE_ITEM = 0
local bu_ACTION_ARM_SWITCH_FORM = 0
local bu_ACTION_ARM_CHANGE_WEAPON_R = 0
local bu_ACTION_ARM_CHANGE_WEAPON_L = 0
local bu_ACTION_ARM_CHANGE_ITEM = 0
local bu_ACTION_ARM_R3 = 0
local bu_ACTION_ARM_L3 = 0
------------
local pr_ACTION_ARM_R1 = 0
local pr_ACTION_ARM_R2 = 0
local pr_ACTION_ARM_L1 = 0
local pr_ACTION_ARM_L2 = 0
local pr_ACTION_ARM_ACTION = 0
local pr_ACTION_ARM_SP_MOVE = 0
local pr_ACTION_ARM_CHANGE_STYLE = 0
local pr_ACTION_ARM_USE_ITEM = 0
local pr_ACTION_ARM_SWITCH_FORM = 0
local pr_ACTION_ARM_CHANGE_WEAPON_R = 0
local pr_ACTION_ARM_CHANGE_WEAPON_L = 0
local pr_ACTION_ARM_CHANGE_ITEM = 0
local pr_ACTION_ARM_R3 = 0
local pr_ACTION_ARM_L3 = 0
------------
local re_ACTION_ARM_R1 = 0
local re_ACTION_ARM_R2 = 0
local re_ACTION_ARM_L1 = 0
local re_ACTION_ARM_L2 = 0
local re_ACTION_ARM_ACTION = 0
local re_ACTION_ARM_SP_MOVE = 0
local re_ACTION_ARM_CHANGE_STYLE = 0
local re_ACTION_ARM_USE_ITEM = 0
local re_ACTION_ARM_SWITCH_FORM = 0
local re_ACTION_ARM_CHANGE_WEAPON_R = 0
local re_ACTION_ARM_CHANGE_WEAPON_L = 0
local re_ACTION_ARM_CHANGE_ITEM = 0
local re_ACTION_ARM_R3 = 0
local re_ACTION_ARM_L3 = 0
------------
local P = 0
local T = 1
local R = 2
local p = 0
local t = 1
local r = 2
local Press = 0
local Pressed = 0
local Time = 1
local Timed = 1
local Release = 2
local Released = 2
local press = 0
local pressed = 0
local time = 1
local timed = 1
local release = 2
local released = 2
------------
function key(pressed_timed_released, action_arm_key)
    local iskeypressed = 0
    local iskeyreleased = 0
    local dT = GetDeltaTime()
	local dT_total = 0
    if env(1108, action_arm_key) > 0 then
	if action_arm_key == ACTION_ARM_R1 then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_R1 == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_R1 = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_R1 == 0 then
			Dt_ACTION_ARM_R1 = g_DeltaRunTime
			bu_ACTION_ARM_R1 = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_R1)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_R1 == 0 then
		    re_ACTION_ARM_R1 = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_R2 then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_R2 == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_R2 = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_R2 == 0 then
			Dt_ACTION_ARM_R2 = g_DeltaRunTime
			bu_ACTION_ARM_R2 = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_R2)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_R2 == 0 then
		    re_ACTION_ARM_R2 = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_L1 then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_L1 == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_L1 = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_L1 == 0 then
			Dt_ACTION_ARM_L1 = g_DeltaRunTime
			bu_ACTION_ARM_L1 = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_L1)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_L1 == 0 then
		    re_ACTION_ARM_L1 = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_L2 then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_L2 == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_L2 = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_L2 == 0 then
			Dt_ACTION_ARM_L2 = g_DeltaRunTime
			bu_ACTION_ARM_L2 = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_L2)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_L2 == 0 then
		    re_ACTION_ARM_L2 = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_ACTION then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_ACTION == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_ACTION = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_ACTION == 0 then
			Dt_ACTION_ARM_ACTION = g_DeltaRunTime
			bu_ACTION_ARM_ACTION = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_ACTION)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_ACTION == 0 then
		    re_ACTION_ARM_ACTION = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_SP_MOVE then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_SP_MOVE == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_SP_MOVE = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_SP_MOVE == 0 then
			Dt_ACTION_ARM_SP_MOVE = g_DeltaRunTime
			bu_ACTION_ARM_SP_MOVE = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_SP_MOVE)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_SP_MOVE == 0 then
		    re_ACTION_ARM_SP_MOVE = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_CHANGE_STYLE then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_CHANGE_STYLE == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_CHANGE_STYLE = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_CHANGE_STYLE == 0 then
			Dt_ACTION_ARM_CHANGE_STYLE = g_DeltaRunTime
			bu_ACTION_ARM_CHANGE_STYLE = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_CHANGE_STYLE)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_CHANGE_STYLE == 0 then
		    re_ACTION_ARM_CHANGE_STYLE = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_USE_ITEM then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_USE_ITEM == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_USE_ITEM = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_USE_ITEM == 0 then
			Dt_ACTION_ARM_USE_ITEM = g_DeltaRunTime
			bu_ACTION_ARM_USE_ITEM = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_USE_ITEM)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_USE_ITEM == 0 then
		    re_ACTION_ARM_USE_ITEM = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_SWITCH_FORM then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_SWITCH_FORM == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_SWITCH_FORM = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_SWITCH_FORM == 0 then
			Dt_ACTION_ARM_SWITCH_FORM = g_DeltaRunTime
			bu_ACTION_ARM_SWITCH_FORM = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_SWITCH_FORM)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_SWITCH_FORM == 0 then
		    re_ACTION_ARM_SWITCH_FORM = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_CHANGE_WEAPON_R then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_CHANGE_WEAPON_R == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_CHANGE_WEAPON_R = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_CHANGE_WEAPON_R == 0 then
			Dt_ACTION_ARM_CHANGE_WEAPON_R = g_DeltaRunTime
			bu_ACTION_ARM_CHANGE_WEAPON_R = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_CHANGE_WEAPON_R)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_CHANGE_WEAPON_R == 0 then
		    re_ACTION_ARM_CHANGE_WEAPON_R = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_CHANGE_WEAPON_L then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_CHANGE_WEAPON_L == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_CHANGE_WEAPON_L = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_CHANGE_WEAPON_L == 0 then
			Dt_ACTION_ARM_CHANGE_WEAPON_L = g_DeltaRunTime
			bu_ACTION_ARM_CHANGE_WEAPON_L = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_CHANGE_WEAPON_L)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_CHANGE_WEAPON_L == 0 then
		    re_ACTION_ARM_CHANGE_WEAPON_L = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_CHANGE_ITEM then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_CHANGE_ITEM == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_CHANGE_ITEM = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_CHANGE_ITEM == 0 then
			Dt_ACTION_ARM_CHANGE_ITEM = g_DeltaRunTime
			bu_ACTION_ARM_CHANGE_ITEM = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_CHANGE_ITEM)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_CHANGE_ITEM == 0 then
		    re_ACTION_ARM_CHANGE_ITEM = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_R3 then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_ARM_R3 == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_ARM_R3 = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_ARM_R3 == 0 then
			Dt_ACTION_ARM_ARM_R3 = g_DeltaRunTime
			bu_ACTION_ARM_ARM_R3 = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_ARM_R3)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_ARM_R3 == 0 then
		    re_ACTION_ARM_ARM_R3 = 1
	        end
	    end
	elseif action_arm_key == ACTION_ARM_L3 then
	    if pressed_timed_released == 0 then
	        if pr_ACTION_ARM_ARM_L3 == 0 then
		    iskeypressed = 1
		    pr_ACTION_ARM_ARM_L3 = 1
	        end
	    elseif pressed_timed_released == 1 then
		if bu_ACTION_ARM_ARM_L3 == 0 then
			Dt_ACTION_ARM_ARM_L3 = g_DeltaRunTime
			bu_ACTION_ARM_ARM_L3 = 1
		end
		dT_total = (g_DeltaRunTime - Dt_ACTION_ARM_ARM_L3)
	    elseif pressed_timed_released == 2 then
	        if re_ACTION_ARM_ARM_L3 == 0 then
		    re_ACTION_ARM_ARM_L3 = 1
	        end
	    end
	end

    else
	if action_arm_key == ACTION_ARM_R1 then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_R1 = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_R1 = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_R1 == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_R1 = 0
	    end

	elseif action_arm_key == ACTION_ARM_R2 then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_R2 = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_R2 = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_R2 == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_R2 = 0
	    end

	elseif action_arm_key == ACTION_ARM_L1 then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_L1 = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_L1 = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_L1 == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_L1 = 0
	    end

	elseif action_arm_key == ACTION_ARM_L2 then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_L2 = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_L2 = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_L2 == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_L2 = 0
	    end

	elseif action_arm_key == ACTION_ARM_ACTION then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_ACTION = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_ACTION = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_ACTION == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_ACTION = 0
	    end

	elseif action_arm_key == ACTION_ARM_SP_MOVE then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_SP_MOVE = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_SP_MOVE = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_SP_MOVE == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_SP_MOVE = 0
	    end

	elseif action_arm_key == ACTION_ARM_CHANGE_STYLE then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_CHANGE_STYLE = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_CHANGE_STYLE = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_CHANGE_STYLE == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_CHANGE_STYLE = 0
	    end

	elseif action_arm_key == ACTION_ARM_USE_ITEM then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_USE_ITEM = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_USE_ITEM = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_USE_ITEM == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_USE_ITEM = 0
	    end

	elseif action_arm_key == ACTION_ARM_SWITCH_FORM then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_SWITCH_FORM = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_SWITCH_FORM = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_SWITCH_FORM == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_SWITCH_FORM = 0
	    end

	elseif action_arm_key == ACTION_ARM_CHANGE_WEAPON_R then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_CHANGE_WEAPON_R = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_CHANGE_WEAPON_R = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_CHANGE_WEAPON_R == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_CHANGE_WEAPON_R = 0
	    end

	elseif action_arm_key == ACTION_ARM_CHANGE_WEAPON_L then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_CHANGE_WEAPON_L = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_CHANGE_WEAPON_L = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_CHANGE_WEAPON_L == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_CHANGE_WEAPON_L = 0
	    end

	elseif action_arm_key == ACTION_ARM_CHANGE_ITEM then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_CHANGE_ITEM = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_CHANGE_ITEM = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_CHANGE_ITEM == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_CHANGE_ITEM = 0
	    end

	elseif action_arm_key == ACTION_ARM_R3 then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_ARM_R3 = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_ARM_R3 = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_ARM_R3 == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_ARM_R3 = 0
	    end

	elseif action_arm_key == ACTION_ARM_L3 then
	    if pressed_timed_released == 0 then
        	pr_ACTION_ARM_ARM_L3 = 0
	    elseif pressed_timed_released == 1 then
        	bu_ACTION_ARM_ARM_L3 = 0
	    elseif pressed_timed_released == 2 then
		if re_ACTION_ARM_ARM_L3 == 1 then
			iskeyreleased = 1
		end
        	re_ACTION_ARM_ARM_L3 = 0
	    end

	end


	dT_total = 0

    end
	if pressed_timed_released == 0 then
    	    if iskeypressed == 1 then
		return TRUE
    	    else
		return FALSE
    	    end
	elseif pressed_timed_released == 1 then
        	return dT_total
	elseif pressed_timed_released == 2 then
    	    if iskeyreleased == 1 then
		return TRUE
    	    else
		return FALSE
    	    end
	end
end

------------------------------------
------------------------------------
function common_Update()
	g_DeltaRunTime = g_DeltaRunTime + (1 * (env(ObtainedDT) / 1000))
	--if key(0, ACTION_ARM_SP_MOVE) == TRUE then
            --Write("vwepstor.lua", env(GetWeaponStorageSpotType, HAND_RIGHT))
            --Write("vevas.lua", env(IsEmergencyEvasionPossible))
            --Write("vatkduration.lua", env(GetAtkDuration))
	--end

end

Update = Include(Update, common_Update)