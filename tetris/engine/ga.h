/*
 * ga.h — algoritmo genético sobre os pesos da rede.
 */
#ifndef GA_H
#define GA_H

#include "ai.h"

#define GAMES_PER_EVAL 3
#define MAX_PIECES     1000

typedef struct {
    Genome genome;
    double fitness;
    double score, lines, tetrises, pieces;   /* médias das partidas */
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
void pop_evolve(Population *p);              /* ordena e gera os filhos */

uint64_t eval_seed(int generation, int game);

#endif
