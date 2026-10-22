/*
 * ai.h — a rede decide a cada tick se o pássaro pula.
 *   6 entradas -> 6 ocultos (tanh) -> 1 saída; pula se saída > 0
 */
#ifndef AI_H
#define AI_H

#include "game.h"

#define NUM_INPUTS  6
#define HIDDEN      6
#define NUM_GENES   (HIDDEN * (NUM_INPUTS + 1) + HIDDEN + 1)

extern const char *INPUT_NAMES[NUM_INPUTS];

typedef struct {
    double w[NUM_GENES];
} Genome;

/* altura, velocidade, distância ao cano, topo e base do vão, velocidade do vão */
void   bird_inputs(const World *w, int bird, double *in);
double nn_forward(const Genome *g, const double *in);
int    nn_should_flap(const Genome *g, const World *w, int bird);

#endif
