from __future__ import annotations
from . import Nation


class ApiKeyPermissions:
    nation_view_resources: bool
    nation_deposit_to_bank: bool
    nation_military_buys: bool
    nation_see_reset_timers: bool
    nation_see_spies: bool
    nation_view_trades: bool
    nation_accept_trade: bool
    nation_send_message: bool
    alliance_view_bank: bool
    alliance_withdraw_bank: bool
    alliance_change_permissions: bool
    alliance_see_spies: bool
    alliance_see_reset_timers: bool
    alliance_tax_brackets: bool
    alliance_accept_applicants: bool
    alliance_remove_members: bool
    alliance_manage_treaties: bool
    alliance_promote_self_to_leader: bool

class ApiKeyDetails:
    nation: Nation
    key: str
    requests: int
    max_requests: int
    permissions: ApiKeyPermissions
    permission_bits: int