/*
 * search.h — avaliação e busca (alpha-beta / PVS com aprofundamento iterativo).
 */
#ifndef SEARCH_H
#define SEARCH_H

#include "board.h"

#define INF        32000
#define MATE       31000
#define MAX_PLY    64

typedef struct {
    int best_move;
    int score;              /* centipeões, do ponto de vista de quem joga */
    int depth;
    long long nodes;
    int time_ms;
    int pv[MAX_PLY];
    int pv_len;
} SearchResult;

int  evaluate(const Position *p);
void search_init(void);
SearchResult think(Position *p, int time_ms, int max_depth);

#endif
