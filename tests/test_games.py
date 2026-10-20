"""Games written in Open8 assembly, played in the simulator by scripted key presses."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import asm             # noqa: E402
import build_firmware  # noqa: E402
import fwsim           # noqa: E402

FRAME = 52500


class Game:
    """A game assembled with the reference assembler, run under the real firmware."""

    def __init__(self, fname):
        self.src = build_firmware.example_text(fname)
        image, a = asm.assemble(self.src, limit=0xAEFF)
        self.sym = a.symbols
        s = fwsim.boot()
        assert s.run_until(s.sym["GK_L"])          # firmware booted (welcome screen)
        for addr, b in image.items():
            s.m.sram[addr - 0x8000] = b
        exit_ret = s.sym["R_EXIT"]                  # RET from the game -> firmware exit path
        s.m.sram[0xAFFE - 0x8000] = exit_ret & 0xFF
        s.m.sram[0xAFFF - 0x8000] = exit_ret >> 8
        s.cpu.sp, s.cpu.pc = 0xFE, 0x8000
        self.s = s

    def var(self, name, size=1):
        a = self.sym[name.upper()] - 0x8000
        v = self.s.m.sram[a]
        return v | self.s.m.sram[a + 1] << 8 if size == 2 else v

    def poke(self, name, value, offset=0):
        self.s.m.sram[self.sym[name.upper()] - 0x8000 + offset] = value

    def sync(self, label="MAIN"):
        """Run to the top of the game loop, so pokes are not overwritten mid-frame."""
        assert self.s.run_until(self.sym[label], max_cycles=5_000_000)

    def frames(self, n):
        self.s.run(n * FRAME)

    def key(self, text=None, keys=(), frames=3):
        self.s.type(text, keys)
        self.frames(frames)

    def screen(self):
        return "\n".join(fwsim.screen_text(self.s))


class TestTetris(unittest.TestCase):
    def board(self, g, row, col):
        return g.s.m.sram[g.sym["BOARD"] - 0x8000 + row * 16 + col]

    def new(self):
        g = Game("07_tetris.asm")
        g.frames(3)
        return g

    def test_screen_and_empty_board(self):
        g = self.new()
        scr = g.screen()
        for text in ("O P E N 8   T E T R I S", "NEXT", "SCORE", "LINES", "LEVEL", "by Adham Elshafei"):
            self.assertIn(text, scr)
        for r in range(20):
            self.assertEqual([self.board(g, r, c) for c in range(16)],
                             [8, 8] + [0] * 10 + [8, 8, 8, 8])
        self.assertEqual([self.board(g, 20, c) for c in range(16)], [8] * 16)
        self.assertIn(g.var("piece"), range(7))
        self.assertIn(g.var("next"), range(7))

    def test_gravity(self):
        g = self.new()
        y0 = g.var("py")
        g.frames(48 * 3 + 2)
        self.assertEqual(g.var("py"), y0 + 3)

    def test_walls_stop_movement(self):
        g = self.new()
        for _ in range(8):
            g.key(keys=["LEFT"], frames=2)
        left = g.var("px")
        g.key(keys=["LEFT"], frames=2)
        self.assertEqual(g.var("px"), left)             # blocked by the wall
        shape = g.sym["SHAPES"] - 0x8000 + g.var("piece") * 32 + g.var("rot") * 8
        min_dx = min(g.s.m.sram[shape + 2 * i] for i in range(4))
        self.assertEqual(left + min_dx, 2)              # leftmost cell in column 2
        for _ in range(12):
            g.key(keys=["RIGHT"], frames=2)
        max_dx = max(g.s.m.sram[shape + 2 * i] for i in range(4))
        self.assertEqual(g.var("px") + max_dx, 11)      # rightmost cell in column 11

    def test_rotation(self):
        g = self.new()
        g.poke("piece", 2)                              # T
        g.key(keys=["UP"])
        self.assertEqual(g.var("rot"), 1)
        g.key("z")
        self.assertEqual(g.var("rot"), 0)

    def test_hard_drop_locks_at_bottom(self):
        g = self.new()
        g.poke("piece", 1)                              # O piece: cells (1,0)(2,0)(1,1)(2,1)
        g.key(" ", frames=4)
        self.assertEqual([self.board(g, 19, c) for c in (6, 7)], [2, 2])
        self.assertEqual([self.board(g, 18, c) for c in (6, 7)], [2, 2])
        self.assertEqual(g.var("score", 2), 2 * 18)    # 18 rows dropped

    def fill_rows(self, g, rows, gap_col=11):
        base = g.sym["BOARD"] - 0x8000
        for r in rows:
            for c in range(2, 12):
                g.s.m.sram[base + r * 16 + c] = 0 if c == gap_col else 5

    def drop_vertical_i(self, g):
        g.poke("piece", 0)
        g.poke("rot", 1)                                # vertical I: cells at dx = 2
        g.poke("px", 9)                                 # -> column 11
        g.poke("py", 0)
        g.key(" ", frames=4)

    def test_single_line_clear(self):
        g = self.new()
        self.fill_rows(g, [19])
        self.drop_vertical_i(g)
        self.assertEqual(g.var("lines", 2), 1)
        self.assertEqual(g.var("score", 2), 2 * 16 + 40)
        # the three remaining I cells moved down one row
        self.assertEqual([self.board(g, r, 11) for r in (17, 18, 19)], [1, 1, 1])
        self.assertEqual([self.board(g, 19, c) for c in range(2, 11)], [0] * 9)

    def test_tetris_four_lines(self):
        g = self.new()
        self.fill_rows(g, [16, 17, 18, 19])
        self.drop_vertical_i(g)
        self.assertEqual(g.var("lines", 2), 4)
        self.assertEqual(g.var("score", 2), 2 * 16 + 1200)
        for r in range(20):
            self.assertEqual([self.board(g, r, c) for c in range(2, 12)], [0] * 10)
        self.assertIn("1232", g.screen())

    def test_level_up_after_ten_lines(self):
        g = self.new()
        for _ in range(3):
            self.fill_rows(g, [16, 17, 18, 19])
            self.drop_vertical_i(g)
        self.assertEqual(g.var("lines", 2), 12)
        self.assertEqual(g.var("level"), 1)

    def test_game_over_restart_and_quit(self):
        g = self.new()
        for _ in range(40):
            g.key(" ", frames=3)
            if "GAME  OVER" in g.screen():
                break
        self.assertIn("GAME  OVER", g.screen())
        g.key(keys=["\n"], frames=4)
        self.assertNotIn("GAME  OVER", g.screen())
        self.assertEqual(g.var("score", 2), 0)
        g.key(keys=["ESC"], frames=4)
        self.assertIn("Program finished", g.screen())

    def test_redraw_fits_in_one_frame(self):
        g = self.new()
        s = g.s
        fwsim.call(s, "R_CLS")
        start = s.m.now
        # call the game's draw_all directly: a full redraw must finish within one frame
        s.m.sram[0xAFFE - 0x8000] = s.sym["TEST_HALT"] & 0xFF
        s.m.sram[0xAFFF - 0x8000] = s.sym["TEST_HALT"] >> 8
        s.cpu.sp, s.cpu.pc, s.cpu.halted = 0xFE, g.sym["DRAW_ALL"], False
        self.assertTrue(s.run_until_halt(FRAME * 2))
        self.assertLess(s.m.now - start, FRAME)


if __name__ == "__main__":
    unittest.main()


def hold(g, name):
    code = {"RIGHT": (1, 0x74), "LEFT": (1, 0x6B), "SPACE": (0, 0x29)}[name]
    g.s.kb.type_bytes(([0xE0] if code[0] else []) + [code[1]], g.s.m.now)


def release(g, name):
    code = {"RIGHT": (1, 0x74), "LEFT": (1, 0x6B), "SPACE": (0, 0x29)}[name]
    g.s.kb.type_bytes(([0xE0] if code[0] else []) + [0xF0, code[1]], g.s.m.now)


class TestPlatformer(unittest.TestCase):
    def new(self):
        g = Game("08_platformer.asm")
        self.assertTrue(g.s.run_until(g.sym["MAIN"], max_cycles=20_000_000))
        g.frames(40)
        g.sync()
        return g

    def map_tile(self, g, row, col):
        return g.s.m.sram[0x9000 - 0x8000 + row * 128 + (col & 127)]

    def test_level_start(self):
        g = self.new()
        self.assertIn("SCORE 00000  COINS 00000  LIVES 3   WORLD 1-1", g.s.text_row(1))
        self.assertEqual((g.var("px"), g.var("py"), g.var("onground")), (3, 26, 1))
        self.assertEqual(self.map_tile(g, 27, 10), 22)                 # ground
        self.assertEqual(self.map_tile(g, 27, 51), 32)                 # pit
        self.assertEqual(self.map_tile(g, 25, 28), 23)                 # pipe rim
        self.assertEqual(self.map_tile(g, 26, 29), 217)                # pipe body
        self.assertEqual(sum(g.s.m.sram[g.sym["E_ON"] - 0x8000 + i] for i in range(6)), 5)

    def test_jump(self):
        g = self.new()
        hold(g, "SPACE")
        g.frames(6)
        release(g, "SPACE")
        y = g.var("py")
        self.assertLess(y, 26)
        g.frames(40)
        self.assertEqual((g.var("py"), g.var("onground")), (26, 1))

    def test_pipe_blocks_and_scrolling(self):
        g = self.new()
        for i in range(6):                                             # no walkers in the way
            g.s.m.sram[g.sym["E_ON"] - 0x8000 + i] = 0
        hold(g, "RIGHT")
        g.frames(140)
        self.assertEqual(g.var("px"), 27)                              # stopped by the pipe at 28
        self.assertEqual(g.var("pxf"), 0)
        hold(g, "SPACE")                                               # jump over it
        g.frames(5)
        release(g, "SPACE")
        g.frames(60)
        self.assertGreater(g.var("px"), 30)
        self.assertEqual(g.var("cam"), g.var("px") - 30)
        self.assertEqual(g.s.m.scroll_x, g.var("cam") & 127)
        self.assertIn("SCORE", g.s.text_row(1))                        # status line follows the scroll
        release(g, "RIGHT")

    def test_second_pit_can_be_jumped(self):
        g = self.new()
        for c in range(79, 85):                                        # no blocks over the run-up
            self.assertNotIn(self.map_tile(g, 23, c), (20, 21))
        for i in range(6):
            g.s.m.sram[g.sym["E_ON"] - 0x8000 + i] = 0
        g.poke("px", 79)                                               # pit is columns 83-86
        g.poke("pxf", 0)
        g.frames(2)
        hold(g, "RIGHT")
        g.frames(6)
        hold(g, "SPACE")
        g.frames(20)
        release(g, "SPACE")
        g.frames(40)
        self.assertEqual((g.var("py"), g.var("onground"), g.var("lives")), (26, 1, 3))
        self.assertGreaterEqual(g.var("px"), 87)
        release(g, "RIGHT")

    def test_bump_question_block_and_coin(self):
        g = self.new()
        g.poke("px", 14)                                               # under the ? block at (14, 23)
        g.frames(2)
        hold(g, "SPACE")
        g.frames(4)
        release(g, "SPACE")
        g.frames(40)
        self.assertEqual(self.map_tile(g, 23, 14), 3)                  # used block
        self.assertEqual(g.var("coins"), 1)
        self.assertEqual(g.var("score", 2), 10)

    def test_collect_coins(self):
        g = self.new()
        g.poke("px", 51)                                               # coins at (51-53, 20)
        g.poke("py", 20)
        g.poke("onground", 0)
        g.frames(1)
        self.assertGreaterEqual(g.var("coins"), 1)
        self.assertEqual(self.map_tile(g, 20, 51), 32)

    def test_stomp_walker(self):
        g = self.new()
        slot = g.sym["E_DATA"] - 0x8000                                # walker 0 starts at column 24
        ex = g.s.m.sram[slot]
        g.poke("px", ex)
        g.poke("pxf", g.s.m.sram[slot + 1])
        g.poke("py", 24)
        g.poke("onground", 0)
        g.poke("vy", 60)
        g.frames(6)
        self.assertEqual(g.var("state"), 0)
        self.assertEqual(g.var("score", 2), 100)
        self.assertEqual(g.s.m.sram[g.sym["E_ON"] - 0x8000], 0)

    def test_walking_into_walker_costs_a_life(self):
        g = self.new()
        hold(g, "RIGHT")
        for _ in range(100):
            g.frames(2)
            if g.var("lives") < 3:
                break
        release(g, "RIGHT")
        self.assertEqual(g.var("lives"), 2)
        g.frames(90)
        self.assertEqual((g.var("px"), g.var("state")), (3, 0))       # level restarted

    def test_falling_into_pit(self):
        g = self.new()
        for name, v in (("px", 51), ("cam", 21), ("py", 20), ("onground", 0)):
            g.poke(name, v)
        for _ in range(60):                                            # falls, then "OUCH" for 60 frames
            g.frames(2)
            if g.var("lives") < 3:
                break
        self.assertEqual(g.var("lives"), 2)

    def test_reach_the_flag(self):
        g = self.new()
        g.poke("px", 225)
        for _ in range(300):                                           # camera catches up, level built
            for name, v in (("py", 10), ("pyf", 0), ("vy", 0), ("onground", 1)):
                g.poke(name, v)
            g.frames(1)
            if g.var("cam") >= 174:
                break
        for i in range(6):                                             # no walkers in the way
            g.s.m.sram[g.sym["E_ON"] - 0x8000 + i] = 0
        g.poke("onground", 0)
        hold(g, "RIGHT")
        for _ in range(120):
            g.frames(2)
            if "COURSE CLEAR" in g.screen():
                break
        self.assertIn("COURSE CLEAR", g.screen())
        self.assertIn("|", g.screen())                                 # the flag pole
