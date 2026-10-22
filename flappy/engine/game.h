/*
 * game.h — mundo do Flappy Bird: física com passo fixo e canos com
 * dificuldade que sobe durante a partida (vão fecha, velocidade sobe,
 * canos passam a se mexer). Ver flappy/PLAN.md.
 *
 * Coordenadas de tela: y cresce pra baixo, a gravidade é positiva.
 */
#ifndef GAME_H
#define GAME_H

#include <stdint.h>

#define WORLD_W        480.0
#define WORLD_H        360.0
#define BIRD_X         90.0
#define BIRD_RADIUS    10.0
#define PIPE_W         52.0
#define GAP_MARGIN     28.0     /* distância mínima do vão até o teto/chão */

#define GRAVITY        0.45
#define FLAP_VELOCITY  (-7.0)
#define MAX_FALL       10.0

#define SPEED_START    3.0
#define SPEED_MAX      5.0
#define SPEED_STEP     0.004    /* por cano passado */
#define GAP_START      140.0
#define GAP_MIN        92.0
#define GAP_STEP       0.25     /* por cano passado */
/* maior diferença de altura entre vãos seguidos. Subir é limitado mais que
   descer: com canos próximos, um pássaro não consegue subir 150 px a tempo,
   e um cano impossível não ensina nada à evolução */
#define GAP_RISE       95.0
#define GAP_DROP       150.0
#define PIPE_SPACING   220.0

#define MOVING_FROM    50       /* a partir deste cano, os vãos sobem e descem */
#define MOVE_OMEGA     0.025    /* rad/tick */
#define SPACING_FROM   150      /* a partir deste cano, o espaçamento varia ±30 */
#define MAX_PIPES      500      /* teto da partida */

#define MAX_BIRDS      128
#define MAX_ACTIVE_PIPES 6

typedef struct {
    double x;                /* borda esquerda */
    double base_center, gap_size;
    double amplitude, phase; /* movimento vertical (0 antes de MOVING_FROM) */
    int index;               /* número do cano desde o início */
    int passed;
} Pipe;

typedef struct {
    double y, vy;
    int alive;
    int pipes_passed;
    long ticks_alive;
} Bird;

typedef struct {
    uint64_t rng;
    long tick;
    double speed;
    int spawned, pipes_passed, finished;
    Pipe pipes[MAX_ACTIVE_PIPES];
    int num_pipes;
    Bird birds[MAX_BIRDS];
    int num_birds, alive;
} World;

uint64_t rng_next(uint64_t *s);
double   rng_uniform(uint64_t *s);
double   rng_gauss(uint64_t *s);

void world_init(World *w, uint64_t seed, int num_birds);

/* avança um tick; flap[i] != 0 faz o pássaro i pular antes da física */
void world_step(World *w, const int *flap);

/* próximo cano à frente dos pássaros (o que ainda não foi ultrapassado) */
const Pipe *world_next_pipe(const World *w);

double pipe_gap_center(const Pipe *p, long tick);   /* já com o movimento */
double pipe_gap_velocity(const Pipe *p, long tick);

#endif
