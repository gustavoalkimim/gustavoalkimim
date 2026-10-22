/*
 * game.c — física, geração de canos e o currículo de dificuldade.
 * Todos os pássaros dividem o mesmo mundo: mesmos canos, mesma velocidade.
 */
#include "game.h"

#include <math.h>
#include <string.h>

/* ------------------------------------------------------------- aleatório */

/* xorshift64*: rápido e determinístico em qualquer plataforma */
uint64_t rng_next(uint64_t *s)
{
    uint64_t x = *s;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *s = x;
    return x * 0x2545F4914F6CDD1DULL;
}

double rng_uniform(uint64_t *s)
{
    return (double)(rng_next(s) >> 11) * (1.0 / 9007199254740992.0);
}

double rng_gauss(uint64_t *s)
{
    double u1 = rng_uniform(s), u2 = rng_uniform(s);
    if (u1 < 1e-12) u1 = 1e-12;
    return sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2);
}

/* ----------------------------------------------------------------- canos */

double pipe_gap_center(const Pipe *p, long tick)
{
    return p->base_center + p->amplitude * sin(MOVE_OMEGA * (double)tick + p->phase);
}

double pipe_gap_velocity(const Pipe *p, long tick)
{
    return p->amplitude * MOVE_OMEGA * cos(MOVE_OMEGA * (double)tick + p->phase);
}

static double clamp(double v, double lo, double hi)
{
    return v < lo ? lo : v > hi ? hi : v;
}

/* cria o cano número w->spawned na posição x, já com a dificuldade dele */
static void spawn_pipe(World *w, double x)
{
    int n = w->spawned++;
    Pipe *p = &w->pipes[w->num_pipes++];
    memset(p, 0, sizeof(*p));
    p->x = x;
    p->index = n;
    p->gap_size = fmax(GAP_MIN, GAP_START - GAP_STEP * n);

    if (n >= MOVING_FROM) {
        p->amplitude = fmin(30.0, 8.0 + 0.15 * (n - MOVING_FROM));
        p->phase = rng_uniform(&w->rng) * 6.283185307179586;
    }

    /* o vão inteiro (com o movimento) precisa caber entre teto e chão */
    double half = p->gap_size / 2 + p->amplitude;
    double lo = GAP_MARGIN + half, hi = WORLD_H - GAP_MARGIN - half;
    double center = lo + rng_uniform(&w->rng) * (hi - lo);

    /* nada de pular do teto pro chão entre dois canos seguidos */
    if (w->num_pipes > 1) {
        double prev = w->pipes[w->num_pipes - 2].base_center;
        center = clamp(center, prev - GAP_RISE, prev + GAP_DROP);   /* y cresce pra baixo */
    }
    p->base_center = clamp(center, lo, hi);
}

static double next_spacing(World *w)
{
    if (w->spawned < SPACING_FROM) return PIPE_SPACING;
    return PIPE_SPACING + (rng_uniform(&w->rng) * 2 - 1) * 30.0;
}

void world_init(World *w, uint64_t seed, int num_birds)
{
    memset(w, 0, sizeof(*w));
    w->rng = seed ? seed : 0x9E3779B97F4A7C15ULL;
    for (int i = 0; i < 8; i++) rng_next(&w->rng);
    w->speed = SPEED_START;
    w->num_birds = num_birds > MAX_BIRDS ? MAX_BIRDS : num_birds;
    w->alive = w->num_birds;
    for (int i = 0; i < w->num_birds; i++) {
        w->birds[i].y = WORLD_H / 2;
        w->birds[i].alive = 1;
    }
    spawn_pipe(w, WORLD_W + 40);
}

const Pipe *world_next_pipe(const World *w)
{
    for (int i = 0; i < w->num_pipes; i++)
        if (w->pipes[i].x + PIPE_W >= BIRD_X - BIRD_RADIUS) return &w->pipes[i];
    return &w->pipes[w->num_pipes - 1];
}

static int hits_pipe(const Pipe *p, double y, long tick)
{
    if (BIRD_X + BIRD_RADIUS <= p->x || BIRD_X - BIRD_RADIUS >= p->x + PIPE_W) return 0;
    double c = pipe_gap_center(p, tick);
    return y - BIRD_RADIUS < c - p->gap_size / 2 || y + BIRD_RADIUS > c + p->gap_size / 2;
}

void world_step(World *w, const int *flap)
{
    if (w->finished || w->alive == 0) return;
    w->tick++;

    for (int i = 0; i < w->num_pipes; i++) w->pipes[i].x -= w->speed;

    /* cano que saiu da tela vai embora; quando há espaço, nasce o próximo */
    if (w->num_pipes && w->pipes[0].x + PIPE_W < 0) {
        memmove(&w->pipes[0], &w->pipes[1], (size_t)(w->num_pipes - 1) * sizeof(Pipe));
        w->num_pipes--;
    }
    const Pipe *last = &w->pipes[w->num_pipes - 1];
    if (w->num_pipes < MAX_ACTIVE_PIPES && last->x < WORLD_W) {
        double x = last->x + next_spacing(w);
        if (x < WORLD_W + PIPE_SPACING) spawn_pipe(w, x);
    }

    for (int i = 0; i < w->num_pipes; i++) {
        Pipe *p = &w->pipes[i];
        if (!p->passed && p->x + PIPE_W < BIRD_X - BIRD_RADIUS) {
            p->passed = 1;
            w->pipes_passed++;
            w->speed = fmin(SPEED_MAX, SPEED_START + SPEED_STEP * w->pipes_passed);
            for (int b = 0; b < w->num_birds; b++)
                if (w->birds[b].alive) w->birds[b].pipes_passed = w->pipes_passed;
        }
    }

    for (int b = 0; b < w->num_birds; b++) {
        Bird *bird = &w->birds[b];
        if (!bird->alive) continue;
        if (flap && flap[b]) bird->vy = FLAP_VELOCITY;
        bird->vy = fmin(MAX_FALL, bird->vy + GRAVITY);
        bird->y += bird->vy;
        bird->ticks_alive++;

        int dead = bird->y - BIRD_RADIUS < 0 || bird->y + BIRD_RADIUS > WORLD_H;
        for (int i = 0; i < w->num_pipes && !dead; i++)
            dead = hits_pipe(&w->pipes[i], bird->y, w->tick);
        if (dead) {
            bird->alive = 0;
            w->alive--;
        }
    }

    if (w->pipes_passed >= MAX_PIPES) w->finished = 1;
}
