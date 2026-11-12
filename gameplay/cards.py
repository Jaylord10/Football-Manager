"""
gameplay/cards.py
=================
Foul detection, card assessment, and player suspension management.

Flow:
  1. assess_tackle()  — called after every failed tackle attempt
  2. apply_card()     — called by match_engine when a foul is confirmed
  3. _send_off()      — internal: removes red-carded player from the pitch
"""

import random
from config.constants import WIDTH, HEIGHT, M_TO_PX, MAX_SPEED

# ── Thresholds ────────────────────────────────────────────────────────────────
_FOUL_THRESHOLD   = 0.45   # minimum recklessness to call a foul (was 0.50; players now move at realistic speeds)
_YELLOW_THRESHOLD = 0.64   # foul + yellow card (was 0.72)
_RED_THRESHOLD    = 0.90   # straight red (very dangerous / DOGSO)

# Minimum seconds between fouls from the same player (avoids foul spam)
_FOUL_COOLDOWN = 4.0


# ── Public: assess whether a failed tackle is a foul ─────────────────────────

def assess_tackle(defender, carrier, current_time, tackle_succeeded):
    """
    Called after every tackle attempt resolves.

    Returns one of:
        "none"   – clean / borderline, no restart needed
        "foul"   – foul given, no card
        "yellow" – foul + yellow card
        "red"    – straight red card (extreme danger or DOGSO)
    """
    # Clean tackles are never fouls in this model
    if tackle_succeeded:
        return "none"

    # Enforce per-player foul cooldown so fouls don't spam
    last_foul = getattr(defender, 'last_foul_time', -_FOUL_COOLDOWN - 1.0)
    if current_time - last_foul < _FOUL_COOLDOWN:
        return "none"

    recklessness = _recklessness_score(defender, carrier)

    if recklessness < _FOUL_THRESHOLD:
        return "none"
    elif recklessness >= _RED_THRESHOLD:
        return "red"
    elif recklessness >= _YELLOW_THRESHOLD:
        return "yellow"
    else:
        return "foul"


def _recklessness_score(defender, carrier):
    """
    Produce a 0–1 recklessness value for a failed tackle.

    Factors:
      • Aggression attribute (high aggression → more reckless)
      • Tackling from behind (clearly chasing the carrier)
      • High approach speed
      • Random referee variance
    """
    score = 0.0

    # Aggression attribute raises baseline recklessness
    aggression = defender.attributes.get("Aggression", 10)
    score += (aggression / 20.0) * 0.25

    # Chasing from behind is more reckless
    if carrier.vel.length() > 1.0 and defender.vel.length() > 1.0:
        to_carrier = carrier.pos - defender.pos
        if to_carrier.length() > 0:
            align = to_carrier.normalize().dot(carrier.vel.normalize())
            if align > 0.5:
                score += 0.30   # clearly from behind

    # High approach speed
    speed_fraction = min(defender.vel.length() / (MAX_SPEED + 1.0), 1.0)
    score += speed_fraction * 0.20

    # Referee's interpretation variance
    score += random.uniform(-0.10, 0.14)

    return max(0.0, min(score, 1.0))


# ── Public: issue a card to a player ─────────────────────────────────────────

def apply_card(player, card_type, team, current_time):
    """
    Issue a card to the fouling player.

    Returns the display result:
        "none"          – foul only, no card shown
        "yellow"        – first booking
        "second_yellow" – second yellow → automatic red
        "red"           – straight red
    """
    # Stamp the foul time regardless of card
    player.last_foul_time = current_time

    if card_type == "foul":
        return "none"   # foul with no card

    if card_type == "yellow":
        player.yellow_cards += 1
        if player.yellow_cards >= 2:
            _send_off(player)
            return "second_yellow"
        return "yellow"

    if card_type == "red":
        _send_off(player)
        return "red"

    return "none"


def reset_cards(team):
    """Clear all bookings for a team at the start of a new match."""
    for player in team:
        player.yellow_cards  = 0
        player.red_card      = False
        player.is_active     = True
        player.last_foul_time = -99.0
        # Return red-carded players to their formation position
        # (actual repositioning handled by reset_game in set_pieces.py)


# ── Internal ──────────────────────────────────────────────────────────────────

def _send_off(player):
    """
    Remove a red-carded player from active play.
    Moves them off the visible pitch so they don't interfere with physics.
    """
    player.red_card   = True
    player.is_active  = False
    player.has_ball   = False
    player.state      = "idle"
    # Park them well off-screen
    player.pos.x      = -300.0
    player.pos.y      = -300.0
    player.target.x   = -300.0
    player.target.y   = -300.0
    player.vel.x      = 0.0
    player.vel.y      = 0.0
