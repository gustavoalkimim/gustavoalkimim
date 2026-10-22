# 🐦 Flappy Bird Swarm, Evolving in Public

100 birds, each with its own tiny neural network, all flying through the
**same pipes at the same time**. Nobody teaches them to fly. Every Monday a
GitHub Action breeds **2 more generations**, and the GIF on the profile shows
the whole swarm: in early generations they crash at the first pipe, and over
the weeks they learn to get through harder and harder sections.

## How a bird decides

Sixty times per second, every bird looks at 6 numbers:

| Input | Meaning |
| --- | --- |
| height | where the bird is |
| velocity | how fast it is rising or falling |
| pipe dist. | how far the end of the next pipe is |
| gap top / gap bottom | where the opening is, relative to the bird |
| gap speed | how fast the opening is moving (pipes move later in the run) |

These go through **6 → 6 hidden neurons (tanh) → 1 output**, which is 49
weights in total. If the output is positive, the bird flaps.

## The twist: the game gets harder as you fly

Classic Flappy Bird is the "hello world" of neuroevolution: it is solved in
about 15 generations and then nothing interesting happens. Here the world
keeps getting harder during each flight:

| From pipe | What changes |
| ---: | --- |
| 0 | the gap shrinks from 140 px toward 92 px, and the speed rises from 3 to 5 px/tick |
| 50 | **gaps start moving** up and down (each pipe has its own random phase) |
| 150 | **spacing between pipes varies** by ±30 px |
| 500 | end of the run (the cap) |

Every pipe is guaranteed to be passable. The next gap can only rise 95 px
above the previous one, because a bird cannot climb much more than that
between two close pipes, and an impossible pipe teaches evolution nothing.
In local tests the best bird went from 45 to ~360 pipes, and the swarm
average from 0.5 to ~180, over 80 generations. At 2 generations a week,
that is close to a year of visible progress.

## How it learns ([`engine/ga.c`](./engine/ga.c))

1. There are 100 networks. In generation 0 they all have random weights.
2. The whole swarm flies **3 worlds together**. The seeds change every generation, so no bird can memorize a pipe sequence.
3. Fitness is `pipes passed × 1000 + ticks survived`. The ticks break ties: early on, everybody dies at the first pipe, and how long a bird lasted is the only signal left.
4. The top 5 survive unchanged. Every other bird is replaced by a child of two parents, each picked by tournament selection (best of 5), using uniform crossover and Gaussian mutation.

## Files

| File | What's inside |
| --- | --- |
| `engine/game.c` | fixed-step physics, seeded pipe generation, the difficulty curriculum, collisions |
| `engine/ai.c` | the 6 inputs and the neural network forward pass |
| `engine/ga.c` | swarm evaluation, selection, crossover, mutation, the JSON replay |
| `engine/main.c` | `train` and `replay` commands used by the Action |
| `render.py` | keeps the history and renders `swarm.gif`, `evolution.svg` and the README section |
| `data/population.txt` | all 100 genomes, one per line; line 1 is the current champion (the gold bird) |
| `data/history.json` | best and average pipes of every generation |

## Try it locally

```bash
cd flappy/engine && make
./flappy train pop.txt 20              # 20 generations from scratch
./flappy replay pop.txt 42 1600 4      # the swarm flies one world (JSON frames)
```
