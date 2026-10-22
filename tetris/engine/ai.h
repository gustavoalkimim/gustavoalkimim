/*
 * ai.h — características do tabuleiro, rede neural e o jogador automático.
 */
#ifndef AI_H
#define AI_H

#include <stdio.h>

#include "game.h"

#define NUM_FEATURES 8
#define HIDDEN       8
/* entrada->oculta (com bias) + oculta->saída (com bias) */
#define NUM_GENES    (HIDDEN * (NUM_FEATURES + 1) + HIDDEN + 1)

extern const char *FEATURE_NAMES[NUM_FEATURES];

typedef struct {
    double w[NUM_GENES];
} Genome;

void   board_features(const uint16_t *rows, int cleared, double *f);
double nn_forward(const Genome *g, const double *f);

/* joga até o fim ou até max_pieces; replay != NULL grava cada lance em JSON */
void play_game(const Genome *net, uint64_t seed, int max_pieces, Game *out, FILE *replay);

#endif
