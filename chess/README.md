# ♟️ Community Chess

Everyone who visits my profile plays **White** together, one move per issue.
**Black** is a chess engine I wrote from scratch in C, with no libraries.

## How a move works

```
you click a move ──► pre-filled issue "chess|move|e2e4"
                          │
                          ▼
              GitHub Action (chess.yml)
   ┌──────────────────────────────────────────────┐
   │ make            → compiles the C engine      │
   │ chess state …   → is e2e4 legal right now?   │
   │ chess think …   → engine searches ~3 s       │
   │ play.py         → state.json, board.svg,     │
   │                   README section             │
   │ git push, then reply on the issue and close  │
   └──────────────────────────────────────────────┘
```

Every run handles **all** open `chess|` issues, oldest first. If two people
move at the same time, the second one is told the position changed.

## The engine ([`engine/`](./engine))

| File | What's inside |
| --- | --- |
| `board.c` | 0x88 board, FEN, Zobrist hashing, pseudo-legal move generation, make/unmake with an undo stack, SAN, perft |
| `search.c` | evaluation and search |
| `main.c` | JSON command-line interface used by the Action |

**Board.** The board is a 128-square 0x88 array: `sq & 0x88` is non-zero
exactly when a square is off the board, so moving off an edge is caught by
one AND. Castling rights are updated with a per-square mask, and the position
hash is updated incrementally on every move.

**Search.**
- Iterative deepening with **principal variation search** (alpha-beta).
- **Transposition table** with 1M entries, keyed by Zobrist hash. Mate scores are stored relative to the node.
- **Null-move pruning**, **late move reductions** and a **check extension**.
- Move ordering: TT move, then captures by MVV-LVA, promotions, **killer moves**, then the **history heuristic**.
- **Quiescence search** on captures, which stops the horizon effect from hiding hanging pieces.
- Draws by repetition and the 50-move rule are detected inside the search.

**Evaluation.**
- Material plus piece-square tables, **tapered** between middlegame and endgame by game phase.
- Pawn structure: passed, doubled and isolated pawns.
- Bishop pair bonus and rooks on open files.
- A "mop-up" term so the engine can actually deliver mate in won endgames.

**Correctness.** The move generator matches the reference
[perft](https://www.chessprogramming.org/Perft_Results) node counts on 6
positions that exercise castling, en passant, promotions and pins. The
starting position at depth 5 is 4,865,609 nodes. CI runs these on every
change (`chess-engine-ci.yml`).

## Try it locally

```bash
cd chess/engine && make && make test
./chess think 3000 e2e4 e7e5        # engine move after 1.e4 e5
./chess state e2e4                   # position, status and legal moves (JSON)
./chess divide 3                     # perft split by root move
```
