/*
 * main.c — interface usada pelo GitHub Action.
 *
 *   flappy train <população.txt> <gerações> [tamanho]
 *       avalia e evolui; cria a população aleatória se o arquivo não existir.
 *       imprime uma linha JSON por geração avaliada.
 *   flappy replay <população.txt> <semente> <ticks_com_quadros> <a_cada>
 *       o enxame inteiro voa um mundo; imprime os quadros em JSON.
 *       o pássaro 0 é sempre o campeão da última geração avaliada.
 */
#include "ga.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int cmd_train(int argc, char **argv)
{
    if (argc < 2) return 1;
    const char *path = argv[0];
    int generations = atoi(argv[1]);
    int size = argc > 2 ? atoi(argv[2]) : 100;

    Population pop;
    if (!pop_load(&pop, path)) {
        fprintf(stderr, "criando população aleatória (%d pássaros, %d genes)\n", size, NUM_GENES);
        pop_random(&pop, size, 2026);
    }
    for (int i = 0; i < generations; i++) {
        pop_evaluate(&pop);
        pop_print_stats(&pop);
        pop_evolve(&pop);
    }
    if (!pop_save(&pop, path)) {
        fprintf(stderr, "não consegui salvar %s\n", path);
        return 1;
    }
    pop_free(&pop);
    return 0;
}

static int cmd_replay(int argc, char **argv)
{
    if (argc < 4) return 1;
    Population pop;
    if (!pop_load(&pop, argv[0])) {
        fprintf(stderr, "população inválida: %s\n", argv[0]);
        return 1;
    }
    uint64_t seed = strtoull(argv[1], NULL, 10);
    long frame_ticks = atol(argv[2]);
    int every = atoi(argv[3]);
    if (every < 1) every = 1;
    swarm_replay(&pop, seed, frame_ticks, every, stdout);
    pop_free(&pop);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc >= 2 && strcmp(argv[1], "train") == 0) return cmd_train(argc - 2, argv + 2);
    if (argc >= 2 && strcmp(argv[1], "replay") == 0) return cmd_replay(argc - 2, argv + 2);
    fprintf(stderr, "uso: %s train|replay ...\n", argv[0]);
    return 1;
}
