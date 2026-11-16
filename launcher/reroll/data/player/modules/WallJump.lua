mod_WJ = 0
mod_WMFC = 0
mod_WJC = 0
mod_WFC = 0
mod_WJT = 0

no_jump = 0
no_jump_f = 0
warping_f = 0

JUMP_KEY = ACTION_ARM_CHANGE_STYLE
function wj_Update()
	CanWJ()
	mod_WJ = 1
end

function CanWJ()
	if env(201) == FALSE and env(504) == FALSE and env(555) == FALSE and env(279) == FALSE and env(206) == FALSE and env(283) == FALSE then
		if ExecJumpMagic(jump_type) == FALSE and ExecFallMagic() == FALSE and IS_ATTACKED_JUMPMAGIC == FALSE and ExecFallAttack() == FALSE and GetVariable("JumpAttackForm") == 0 and no_jump == 0 and env(1000) > 0 and env(1001) > 0 then
			if mod_WJT > 0 then
				mod_WJT = mod_WJT + (1 * (env(ObtainedDT) / 1000))
					if mod_WJT > 0.42 then
						mod_WJT = 0
					end
			end
			    if warping_f == 0 then
					mod_WMFC = mod_WMFC + 1
				if mod_WFC < 1.59 and env(2012) == TRUE then
					if mod_WJC > 0 then
						mod_WFC = mod_WFC + (1 * (env(ObtainedDT) / 1000))
					end
					if mod_WFC < 1.29 then
						act(2002, 9000007)
					end
				end
				if key(0, JUMP_KEY) == TRUE and mod_WMFC > 12 and mod_WJT == 0 then
						if env(2012) == TRUE and mod_WFC < 1.59 then
                					act(LockonFixedAngleCancel)
							mod_WJC = mod_WJC + 1
							WallJump()
						end
				end
			    end
		end
    elseif env(201) == TRUE then
		mod_WMFC = 0
		mod_WJC = 0
		mod_WFC = 0
		mod_WJT = 0
		IS_ATTACKED_JUMPMAGIC = FALSE
	end
end

function WallJump()
			mod_WJT = mod_WJT + (1 * (env(ObtainedDT) / 1000))
                		act(LockonFixedAngleCancel)
    if env(GetStamina) <= 0 then
        ResetRequest()
        return FALSE
    end

    SetWeightIndex()

    -- Jump: Overweight
    if GetVariable("EvasionWeightIndex") == EVASION_WEIGHT_INDEX_OVERWEIGHT and env(IsAIJumpRequested) == FALSE then
        local jumpangle = env(GetJumpAngle) * 0.009999999776482582
            SetVariable("JumpOverweightIndex", 0)

        act(SetNpcAIAttackRequestIDAfterBlend, env(GetNpcAIAttackRequestID))
        SetAIActionState()
        ExecEventAllBody("W_Jump_Overweight")

        return TRUE
    end

    local style = c_Style

    if style == HAND_RIGHT then
        SetVariable("JumpAttack_HandCondition", 0)
    elseif style == HAND_RIGHT_BOTH then
        SetVariable("JumpAttack_HandCondition", 1)
    elseif style == HAND_LEFT_BOTH then
        if GetEquipType(HAND_LEFT, WEAPON_CATEGORY_CROSSBOW) == TRUE then
            SetVariable("JumpAttack_HandCondition", 4)
        else
            SetVariable("JumpAttack_HandCondition", 1)
        end
    end

    SetVariable("JumpAttackForm", 0)
    SetVariable("JumpUseMotion_Bool", false)
    SetVariable("JumpMotion_Override", 0.009999999776482582)
    SetVariable("JumpAttack_Land", 0)
    SetVariable("SwingPose", 0)
    IS_ATTACKED_JUMPMAGIC = FALSE

    if GetVariable("IsEnableToggleDashTest") == 2 then
        SetVariable("ToggleDash", 0)
    end

    local JumpMoveLevel = 0

    if GetVariable("LocomotionState") == 1 and GetVariable("MoveSpeedIndex") == 2 then
        JumpMoveLevel = 2
    elseif GetVariable("MoveSpeedLevel") >= 0.6000000238418579 then
        JumpMoveLevel = 1
    end

    -- Ironjar Aromatic
    if env(GetSpEffectID, 503520) == TRUE then
        JumpMoveLevel = 0
        -- Unknown
    elseif env(GetSpEffectID, 5520) == TRUE then
        JumpMoveLevel = 0
        -- Slug: Slow
    elseif env(GetSpEffectID, 425) == TRUE then
        JumpMoveLevel = 0
        -- Sanguine Noble: Slow
    elseif env(GetSpEffectID, 4101) == TRUE then
        JumpMoveLevel = 0
        -- Sanguine Noble: Slow
    elseif env(GetSpEffectID, 4100) == TRUE then
        JumpMoveLevel = 0
        -- Unknown (DLC)
    elseif env(GetSpEffectID, 19670) == TRUE then
        JumpMoveLevel = 0
    end

    if JumpMoveLevel == 2 then
        if env(IsAIJumpRequested) == TRUE then
            act(NotifyAIOfJumpState)
        end

        act(SetNpcAIAttackRequestIDAfterBlend, env(GetNpcAIAttackRequestID))
        SetAIActionState()
        act(2002, 9000002)
        ExecEvent("W_Jump_D")

        return TRUE
    elseif JumpMoveLevel == 1 then
            SetVariable("JumpDirection", 0)
            SetVariable("JumpAngle", 0)

        SetVariable("IsEnableDirectionJumpTAE", true)

        if env(IsAIJumpRequested) == TRUE then
            act(NotifyAIOfJumpState)
        end

        act(SetNpcAIAttackRequestIDAfterBlend, env(GetNpcAIAttackRequestID))
        SetAIActionState()
        act(2002, 9000002)
        ExecEvent("W_Jump_F")

        return TRUE
    else
        SetVariable("JumpReachSelector", 0)

        if env(IsAIJumpRequested) == TRUE then
            act(NotifyAIOfJumpState)
        end

        act(SetNpcAIAttackRequestIDAfterBlend, env(GetNpcAIAttackRequestID))
        SetAIActionState()
        act(2002, 9000002)
        ExecEvent("W_Jump_N")

        return TRUE
    end
end
Update = Include(Update, wj_Update)
