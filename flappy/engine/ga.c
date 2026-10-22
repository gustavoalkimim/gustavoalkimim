/*
 * ga.c — neuroevolução em enxame. Cada geração, a população inteira voa
 * junta nos mesmos mundos; as melhores redes sobrevivem (elitismo) e as
 * outras são substituídas por filhos de pais escolhidos por torneio, com
 * crossover uniforme e mutação gaussiana.
 */
#include "ga.h"

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

/* mundos mudam por geração: ninguém decora a sequência de canos */
uint64_t eval_seed(int generation, int world)
{
    return splitmix((uint64_t)generation * 1000003ULL + (uint64_t)world);
}

void pop_random(Population *p, int size, uint64_t seed)
{
    uint64_t rng = splitmix(seed) | 1;
    if (size > MAX_BIRDS) size = MAX_BIRDS;
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
    fprintf(f, "# flappy population v1\n");
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
        genes != NUM_GENES || p->size <= ELITE || p->size > MAX_BIRDS) {
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

/* um mundo, todos os pássaros juntos, até o último morrer ou chegar no teto */
static void fly(const Population *p, World *w, uint64_t seed)
{
    int flap[MAX_BIRDS];
    world_init(w, seed, p->size);
    while (w->alive > 0 && !w->finished) {
        for (int i = 0; i < p->size; i++)
            flap[i] = w->birds[i].alive && nn_should_flap(&p->ind[i].genome, w, i);
        world_step(w, flap);
    }
}

void pop_evaluate(Population *p)
{
    for (int i = 0; i < p->size; i++) p->ind[i].pipes = p->ind[i].ticks = 0;

    static World w;
    for (int k = 0; k < WORLDS_PER_EVAL; k++) {
        fly(p, &w, eval_seed(p->generation, k));
        for (int i = 0; i < p->size; i++) {
            p->ind[i].pipes += w.birds[i].pipes_passed;
            p->ind[i].ticks += (double)w.birds[i].ticks_alive;
        }
    }
    for (int i = 0; i < p->size; i++) {
        Individual *ind = &p->ind[i];
        ind->pipes /= WORLDS_PER_EVAL;
        ind->ticks /= WORLDS_PER_EVAL;
        /* os ticks desempatam quem morreu no mesmo cano: no começo,
           todo mundo morre no primeiro e só isso separa os melhores */
        ind->fitness = ind->pipes * 1000.0 + ind->ticks;
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

    double mean = 0, mean_pipes = 0;
    for (int i = 0; i < p->size; i++) {
        mean += sorted[i].fitness;
        mean_pipes += sorted[i].pipes;
    }
    printf("{\"generation\":%d,\"best\":%.1f,\"mean\":%.1f,\"median\":%.1f,"
           "\"best_pipes\":%.1f,\"mean_pipes\":%.2f}\n",
           p->generation, sorted[0].fitness, mean / p->size, sorted[p->size / 2].fitness,
           sorted[0].pipes, mean_pipes / p->size);
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
    uint64_t rng = splitmix(0xF1A99ULL + (uint64_t)p->generation) | 1;
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

void swarm_replay(const Population *p, uint64_t seed, long frame_ticks, int every, FILE *out)
{
    static World w;
    int flap[MAX_BIRDS];
    int first = 1;
    world_init(&w, seed, p->size);

    fprintf(out, "{\"frames\":[\n");
    while (w.alive > 0 && !w.finished) {
        if (w.tick < frame_ticks && w.tick % every == 0) {
            fprintf(out, "%s{\"t\":%ld,\"n\":%d,\"p\":[", first ? "" : ",\n", w.tick, w.pipes_passed);
            for (int i = 0; i < w.num_pipes; i++) {
                const Pipe *pp = &w.pipes[i];
                double c = pipe_gap_center(pp, w.tick);
                fprintf(out, "%s[%.1f,%.1f,%.1f]", i ? "," : "",
                        pp->x, c - pp->gap_size / 2, c + pp->gap_size / 2);
            }
            /* pássaros vivos como [índice, y]; quem sumiu da lista morreu */
            fprintf(out, "],\"b\":[");
            int k = 0;
            for (int i = 0; i < p->size; i++)
                if (w.birds[i].alive) fprintf(out, "%s[%d,%.1f]", k++ ? "," : "", i, w.birds[i].y);
            fprintf(out, "]}");
            first = 0;
        }
        for (int i = 0; i < p->size; i++)
            flap[i] = w.birds[i].alive && nn_should_flap(&p->ind[i].genome, &w, i);
        world_step(&w, flap);
    }

    int best = 0;
    for (int i = 0; i < p->size; i++)
        if (w.birds[i].pipes_passed > w.birds[best].pipes_passed) best = i;
    fprintf(out, "\n],\"ticks\":%ld,\"pipes\":%d,\"finished\":%s,\"alive_at_end\":%d,"
                 "\"champion_pipes\":%d,\"best_pipes\":%d,\"birds\":%d}\n",
            w.tick, w.pipes_passed, w.finished ? "true" : "false", w.alive,
            w.birds[0].pipes_passed, w.birds[best].pipes_passed, p->size);
}
