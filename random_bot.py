import eval7
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot

class MirrorBot(BaseBot):
    def get_move(self, game_info, current_state):
        if current_state.street == 'auction':
            # Specifically targets the common 35-chip bid limit
            return ActionBid(min(36, current_state.my_chips))
        valid = current_state.legal_actions
        if ActionCheck in valid: return ActionCheck()
        return ActionCall() if ActionCall in valid else ActionFold()

if __name__ == '__main__':
    run_bot(MirrorBot(), parse_args())