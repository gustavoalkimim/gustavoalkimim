/*
 * ga.h — mesmo algoritmo genético do Tetris, mas a avaliação é em enxame:
 * a população inteira voa no mesmo mundo ao mesmo tempo.
 */
#ifndef GA_H
#define GA_H

#include <stdio.h>

#include "ai.h"

#define WORLDS_PER_EVAL 3

typedef struct {
    Genome genome;
    double fitness;          /* canos × 1000 + ticks vivo, média dos mundos */
    double pipes, ticks;
} Individual;

typedef struct {
    int generation;          /* geração que ainda vai ser avaliada */
    int size;
    Individual *ind;
} Population;

void pop_random(Population *p, int size, uint64_t seed);
int  pop_load(Population *p, const char *path);
int  pop_save(const Population *p, const char *path);
void pop_free(Population *p);

void pop_evaluate(Population *p);
void pop_print_stats(const Population *p);   /* JSON de uma linha */
void pop_evolve(Population *p);              /* elitismo + torneio + crossover + mutação */

uint64_t eval_seed(int generation, int world);

/* todos os pássaros voam um mundo; grava cada tick em JSON pro GIF */
void swarm_replay(const Population *p, uint64_t seed, long max_ticks, FILE *out);

#endif
