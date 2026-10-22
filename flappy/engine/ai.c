/*
 * ai.c — o que o pássaro "vê": 6 números sobre ele e o próximo cano.
 * A rede devolve um número; se for positivo, ele pula.
 */
#include "ai.h"

#include <math.h>

const char *INPUT_NAMES[NUM_INPUTS] = {
    "height", "velocity", "pipe dist.", "gap top", "gap bottom", "gap speed",
};

void bird_inputs(const World *w, int bird, double *in)
{
    const Bird *b = &w->birds[bird];
    const Pipe *p = world_next_pipe(w);
    double center = pipe_gap_center(p, w->tick);

    in[0] = b->y / WORLD_H;
    in[1] = b->vy / MAX_FALL;
    in[2] = (p->x + PIPE_W - BIRD_X) / WORLD_W;
    in[3] = (center - p->gap_size / 2 - b->y) / WORLD_H;
    in[4] = (center + p->gap_size / 2 - b->y) / WORLD_H;
    in[5] = pipe_gap_velocity(p, w->tick) / 2.0;
}

double nn_forward(const Genome *g, const double *in)
{
    const double *w = g->w;
    double out = w[NUM_GENES - 1];
    for (int j = 0; j < HIDDEN; j++) {
        const double *wj = w + j * (NUM_INPUTS + 1);
        double sum = wj[NUM_INPUTS];
        for (int i = 0; i < NUM_INPUTS; i++) sum += wj[i] * in[i];
        out += w[HIDDEN * (NUM_INPUTS + 1) + j] * tanh(sum);
    }
    return out;
}

int nn_should_flap(const Genome *g, const World *w, int bird)
{
    double in[NUM_INPUTS];
    bird_inputs(w, bird, in);
    return nn_forward(g, in) > 0;
}
