/*
 * ga.c — neuroevolução: ninguém ensina a rede a jogar. Cada geração, todas
 * as redes jogam as mesmas partidas; as melhores sobrevivem (elitismo) e
 * as outras são substituídas por filhos de pais escolhidos por torneio,
 * com crossover uniforme e mutação gaussiana.
 */
#include "ga.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ELITE          5
#define TOURNAMENT     5
#define MUTATION_RATE  0.10
#define MUTATION_SIGMA 0.25
#define BIG_MUTATION   0.05    /* chance de um "salto" maior num gene */

static uint64_t splitmix(uint64_t x)
{
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}

/* sementes mudam por geração: a rede não pode decorar uma sequência de peças */
uint64_t eval_seed(int generation, int game)
{
    return splitmix((uint64_t)generation * 1000003ULL + (uint64_t)game);
}

void pop_random(Population *p, int size, uint64_t seed)
{
    uint64_t rng = splitmix(seed) | 1;
    p->generation = 0;
    p->size = size;
    p->ind = calloc((size_t)size, sizeof(Individual));
    for (int i = 0; i < size; i++)
        for (int k = 0; k < NUM_GENES; k++)
            p->ind[i].genome.w[k] = rng_gauss(&rng);
}

void pop_free(Population *p)
{
    free(p->ind);
    p->ind = NULL;
}

/* formato texto: legível no git diff e fácil de ler no Python */
int pop_save(const Population *p, const char *path)
{
    FILE *f = fopen(path, "w");
    if (!f) return 0;
    fprintf(f, "# tetris population v1\n");
    fprintf(f, "generation %d\nsize %d\ngenes %d\n", p->generation, p->size, NUM_GENES);
    for (int i = 0; i < p->size; i++) {
        for (int k = 0; k < NUM_GENES; k++)
            fprintf(f, "%s%.6f", k ? " " : "", p->ind[i].genome.w[k]);
        fprintf(f, "\n");
    }
    fclose(f);
    return 1;
}

int pop_load(Population *p, const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    char line[256];
    int genes = 0;
    if (!fgets(line, sizeof(line), f) ||
        fscanf(f, " generation %d size %d genes %d", &p->generation, &p->size, &genes) != 3 ||
        genes != NUM_GENES || p->size <= ELITE) {
        fclose(f);
        return 0;
    }
    p->ind = calloc((size_t)p->size, sizeof(Individual));
    for (int i = 0; i < p->size; i++)
        for (int k = 0; k < NUM_GENES; k++)
            if (fscanf(f, "%lf", &p->ind[i].genome.w[k]) != 1) {
                fclose(f);
                pop_free(p);
                return 0;
            }
    fclose(f);
    return 1;
}

void pop_evaluate(Population *p)
{
    for (int i = 0; i < p->size; i++) {
        Individual *ind = &p->ind[i];
        ind->score = ind->lines = ind->tetrises = ind->pieces = 0;
        for (int k = 0; k < GAMES_PER_EVAL; k++) {
            Game g;
            play_game(&ind->genome, eval_seed(p->generation, k), MAX_PIECES, &g, NULL);
            ind->score += g.score;
            ind->lines += g.lines;
            ind->tetrises += g.tetrises;
            ind->pieces += g.pieces;
        }
        ind->score /= GAMES_PER_EVAL;
        ind->lines /= GAMES_PER_EVAL;
        ind->tetrises /= GAMES_PER_EVAL;
        ind->pieces /= GAMES_PER_EVAL;
        /* sobreviver dá um pouquinho de pontos: sem isso, no começo todo mundo
           empata em zero e a seleção não tem pra onde puxar */
        ind->fitness = ind->score + ind->pieces;
    }
}

static int by_fitness_desc(const void *a, const void *b)
{
    double fa = ((const Individual *)a)->fitness, fb = ((const Individual *)b)->fitness;
    return (fa < fb) - (fa > fb);
}

void pop_print_stats(const Population *p)
{
    Individual *sorted = malloc((size_t)p->size * sizeof(Individual));
    memcpy(sorted, p->ind, (size_t)p->size * sizeof(Individual));
    qsort(sorted, (size_t)p->size, sizeof(Individual), by_fitness_desc);

    double mean = 0;
    for (int i = 0; i < p->size; i++) mean += sorted[i].fitness;
    mean /= p->size;
    const Individual *b = &sorted[0];
    printf("{\"generation\":%d,\"best\":%.1f,\"mean\":%.1f,\"median\":%.1f,"
           "\"score\":%.1f,\"lines\":%.1f,\"tetrises\":%.2f,\"pieces\":%.1f}\n",
           p->generation, b->fitness, mean, sorted[p->size / 2].fitness,
           b->score, b->lines, b->tetrises, b->pieces);
    fflush(stdout);
    free(sorted);
}

static const Individual *tournament(const Population *p, uint64_t *rng)
{
    const Individual *best = NULL;
    for (int i = 0; i < TOURNAMENT; i++) {
        const Individual *c = &p->ind[rng_next(rng) % (uint64_t)p->size];
        if (!best || c->fitness > best->fitness) best = c;
    }
    return best;
}

void pop_evolve(Population *p)
{
    uint64_t rng = splitmix(0xC0FFEEULL + (uint64_t)p->generation) | 1;
    qsort(p->ind, (size_t)p->size, sizeof(Individual), by_fitness_desc);

    Individual *next = calloc((size_t)p->size, sizeof(Individual));
    for (int i = 0; i < ELITE; i++) next[i] = p->ind[i];   /* [0] = campeão */

    for (int i = ELITE; i < p->size; i++) {
        const Individual *a = tournament(p, &rng), *b = tournament(p, &rng);
        Genome *child = &next[i].genome;
        for (int k = 0; k < NUM_GENES; k++) {
            child->w[k] = (rng_next(&rng) & 1) ? a->genome.w[k] : b->genome.w[k];
            if (rng_uniform(&rng) < MUTATION_RATE) {
                double sigma = rng_uniform(&rng) < BIG_MUTATION ? 1.0 : MUTATION_SIGMA;
                child->w[k] += rng_gauss(&rng) * sigma;
            }
        }
    }

    free(p->ind);
    p->ind = next;
    p->generation++;
}
