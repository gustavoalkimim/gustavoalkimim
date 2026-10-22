# 🧠 Tetris AI, Learning in Public

A neural network that teaches itself to play Tetris through evolution.
Nobody shows it a game and no weights are tuned by hand. Every Monday a
GitHub Action trains **2 more generations**, so the profile gets a little
smarter each week.

## How it plays

The network never sees pixels and never presses buttons. For each piece, the
engine tries **every rotation × column** (up to 34 options), drops the piece,
and describes the resulting board with 8 numbers:

| Feature | Meaning |
| --- | --- |
| lines | lines cleared by this move |
| holes | empty cells with something above them |
| height | sum of the column heights |
| bumpiness | how jagged the surface is |
| max height | tallest column |
| wells | depth of the narrow gaps between columns |
| row / col trans. | how often filled and empty cells alternate |

These go through a small network: **8 inputs → 8 hidden neurons (tanh) → 1
score**, which is 81 weights in total. The move with the highest score is
played. What the network actually "learns" is which board shapes are good.

## How it learns ([`engine/ga.c`](./engine/ga.c))

1. There are 100 networks. In generation 0 they all have random weights.
2. Every network plays the **same 3 games**, each up to 1,000 pieces. The pieces come from a seeded 7-bag shuffle, and the seeds change every generation so no network can memorize a sequence.
3. Fitness is the classic Tetris score (100 / 300 / 500 / 800 points for 1–4 lines) plus 1 point per piece survived.
4. The **top 5 survive unchanged**. Every other network is replaced by a child of two parents, each picked by **tournament selection** (best of 5 random networks), using **uniform crossover** and **Gaussian mutation**.

Because of the scoring, the learning happens in two phases:
1. **Survive.** It takes a few generations to stop topping out.
2. **Go for Tetrises.** A 4-line clear scores 800 points instead of 4 × 100, so the networks slowly learn to stack cleanly and leave a well open. This phase takes many more generations, which is why progress shows up over weeks instead of all at once.

## Files

| File | What's inside |
| --- | --- |
| `engine/game.c` | bitboard Tetris (each row is a `uint16_t`), 7-bag randomizer, drop and line clear |
| `engine/ai.c` | board features, neural network forward pass, the autoplayer |
| `engine/ga.c` | population, evaluation, selection, crossover, mutation |
| `engine/main.c` | `train` and `replay` commands used by the Action |
| `train.py` | keeps the history and renders `replay.gif`, `brain.svg` and the README section |
| `data/population.txt` | all 100 genomes, one per line; line 1 is the current champion |
| `data/history.json` | best, mean and median fitness of every generation |

## Try it locally

```bash
cd tetris/engine && make
./tetris train pop.txt 10                 # 10 generations from scratch
./tetris replay pop.txt 0 42 1000         # the champion plays one game (JSON)
```
