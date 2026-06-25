"""Hidden terminal mini-game for the XY interactive menu.

Kept separate from the dispatcher because it owns no plot/figure state; it only
needs a blocking line-input callback. This mirrors the per-mode module split
used by the other plot modes (small, single-purpose files).
"""

from __future__ import annotations

import random
from typing import Callable


def play_jump_game(safe_input: Callable[[str], str]) -> None:
    """Simple terminal 'jumping bird' (Flappy-style) game.

    Controls: j = jump, Enter = let bird fall, q = quit game.
    Avoid hitting '#' pillars. Score increases when you pass a pillar.
    Difficulty lowered: bigger gaps, stronger jump, sparser pillars.
    """
    # Board/config
    WIDTH = 32
    HEIGHT = 12
    BIRD_X = 5
    GRAVITY = 1
    JUMP_VEL = -3   # stronger jump for easier play
    GAP_SIZE = 5    # larger gap for easier passage
    MIN_OBS_SPACING = 12  # more spacing between obstacles

    class Obstacle:
        __slots__ = ("x", "gap_start", "scored")
        def __init__(self, x):
            self.x = x
            self.gap_start = random.randint(1, max(1, HEIGHT - GAP_SIZE - 1))
            self.scored = False

    bird_y = HEIGHT // 2
    vel = 0
    tick = 0
    score = 0
    obstacles = [Obstacle(WIDTH - 1)]

    def need_new():
        if not obstacles:
            return True
        rightmost = max(o.x for o in obstacles)
        return rightmost < WIDTH - MIN_OBS_SPACING

    def new_obstacle():
        obstacles.append(Obstacle(WIDTH - 1))

    def collision():
        # Out of bounds
        if bird_y < 0 or bird_y >= HEIGHT:
            return True
        # Pillar collisions at or just before bird column unless within gap
        for o in obstacles:
            if o.x in (BIRD_X, BIRD_X - 1):
                if not (o.gap_start <= bird_y < o.gap_start + GAP_SIZE):
                    return True
        return False

    def move_obstacles():
        for o in obstacles:
            o.x -= 1

    def purge_obstacles():
        while obstacles and obstacles[0].x < -1:
            obstacles.pop(0)

    def render():
        border = "+" + ("-" * WIDTH) + "+"
        print("\n" + border)
        for y in range(HEIGHT):
            row = []
            for x in range(WIDTH):
                ch = " "
                if x == BIRD_X and y == bird_y:
                    ch = "@"
                else:
                    for o in obstacles:
                        if x == o.x and not (o.gap_start <= y < o.gap_start + GAP_SIZE):
                            ch = "#"
                            break
                row.append(ch)
            print("|" + "".join(row) + "|")
        print(border)
        print(f"Score: {score}   (j=jump, Enter=fall, q=quit)")

    # One-time instructions
    print("\nJumping Bird: pass through the gaps!")
    print("Controls: j = jump, Enter = fall, q = quit\n")

    while True:
        render()
        cmd = safe_input("> ").strip().lower()
        if cmd == 'q':
            print("Exited game. Returning to interactive menu.\n")
            break
        if cmd == 'j':
            vel = JUMP_VEL
        else:
            vel += GRAVITY

        bird_y += vel

        move_obstacles()
        if need_new():
            new_obstacle()
        purge_obstacles()

        # Scoring: mark a pillar once it moves left of bird
        for o in obstacles:
            if not o.scored and o.x < BIRD_X:
                o.scored = True
                score += 1

        tick += 1
        if collision():
            render()
            print(f"Game Over! Final score: {score}\n")
            break


__all__ = ["play_jump_game"]
