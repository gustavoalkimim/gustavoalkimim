/*
 * game.c — peças, sorteio 7-bag, queda e limpeza de linhas.
 */
#include "game.h"

#include <math.h>
#include <string.h>

const char PIECE_NAMES[NUM_PIECES + 1] = "IOTSZJL";

PieceShape SHAPES[NUM_PIECES];

/* forma base de cada peça como (x, y), y pra cima */
static const int BASE[NUM_PIECES][4][2] = {
    { {0, 0}, {1, 0}, {2, 0}, {3, 0} },   /* I */
    { {0, 0}, {1, 0}, {0, 1}, {1, 1} },   /* O */
    { {0, 0}, {1, 0}, {2, 0}, {1, 1} },   /* T */
    { {0, 0}, {1, 0}, {1, 1}, {2, 1} },   /* S */
    { {1, 0}, {2, 0}, {0, 1}, {1, 1} },   /* Z */
    { {0, 0}, {1, 0}, {2, 0}, {0, 1} },   /* J */
    { {0, 0}, {1, 0}, {2, 0}, {2, 1} },   /* L */
};

/* gira 90° quantas vezes for preciso e guarda só as rotações distintas */
void shapes_init(void)
{
    for (int p = 0; p < NUM_PIECES; p++) {
        int cells[4][2];
        memcpy(cells, BASE[p], sizeof(cells));
        PieceShape *s = &SHAPES[p];
        s->count = 0;

        for (int r = 0; r < 4; r++) {
            int minx = 99, miny = 99, maxx = -99, maxy = -99;
            for (int i = 0; i < 4; i++) {
                if (cells[i][0] < minx) minx = cells[i][0];
                if (cells[i][1] < miny) miny = cells[i][1];
            }
            uint16_t mask[4] = { 0, 0, 0, 0 };
            for (int i = 0; i < 4; i++) {
                int x = cells[i][0] - minx, y = cells[i][1] - miny;
                mask[y] |= (uint16_t)(1u << x);
                if (x > maxx) maxx = x;
                if (y > maxy) maxy = y;
            }

            int dup = 0;
            for (int k = 0; k < s->count; k++)
                if (memcmp(s->mask[k], mask, sizeof(mask)) == 0) dup = 1;
            if (!dup) {
                memcpy(s->mask[s->count], mask, sizeof(mask));
                s->width[s->count] = maxx + 1;
                s->height[s->count] = maxy + 1;
                s->count++;
            }

            for (int i = 0; i < 4; i++) {   /* (x, y) -> (y, -x) */
                int x = cells[i][0];
                cells[i][0] = cells[i][1];
                cells[i][1] = -x;
            }
        }
    }
}

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

void game_init(Game *g, uint64_t seed)
{
    memset(g, 0, sizeof(*g));
    g->rng.state = seed ? seed : 0x9E3779B97F4A7C15ULL;
    for (int i = 0; i < 8; i++) rng_next(&g->rng.state);   /* aquece sementes parecidas */
}

/* 7-bag: embaralha as 7 peças e entrega uma de cada antes de repetir */
int game_next_piece(Game *g)
{
    Rng *r = &g->rng;
    if (r->left == 0) {
        for (int i = 0; i < NUM_PIECES; i++) r->bag[i] = i;
        for (int i = NUM_PIECES - 1; i > 0; i--) {
            int j = (int)(rng_next(&r->state) % (uint64_t)(i + 1));
            int t = r->bag[i];
            r->bag[i] = r->bag[j];
            r->bag[j] = t;
        }
        r->left = NUM_PIECES;
    }
    return r->bag[NUM_PIECES - r->left--];
}

/* ----------------------------------------------------------------- queda */

static int collides(const uint16_t *rows, const uint16_t *mask, int h, int x, int y)
{
    if (y < 0) return 1;
    for (int dy = 0; dy < h; dy++)
        if (rows[y + dy] & (uint16_t)(mask[dy] << x)) return 1;
    return 0;
}

int drop_piece(uint16_t *rows, int piece, int rot, int x, Drop *out)
{
    const PieceShape *s = &SHAPES[piece];
    const uint16_t *mask = s->mask[rot];
    int h = s->height[rot];

    if (x < 0 || x + s->width[rot] > BOARD_W) return 0;
    int y = BOARD_H;                       /* nasce logo acima da tela */
    if (collides(rows, mask, h, x, y)) return 0;
    while (!collides(rows, mask, h, x, y - 1)) y--;
    if (y + h > BOARD_H) return 0;         /* travou fora da tela: game over */

    for (int dy = 0; dy < h; dy++) rows[y + dy] |= (uint16_t)(mask[dy] << x);

    out->rot = rot;
    out->x = x;
    out->y = y;
    out->cleared = 0;
    int write = y;
    for (int read = y; read < BOARD_ROWS; read++) {
        if (rows[read] == FULL_ROW) {
            out->cleared_rows[out->cleared++] = read;
            continue;
        }
        rows[write++] = rows[read];
    }
    while (write < BOARD_ROWS) rows[write++] = 0;
    return 1;
}

/* aplica de verdade no jogo: placar e cores (o drop já foi validado) */
void game_apply(Game *g, int piece, const Drop *d)
{
    static const int POINTS[5] = { 0, 100, 300, 500, 800 };
    const PieceShape *s = &SHAPES[piece];

    for (int dy = 0; dy < s->height[d->rot]; dy++)
        for (int dx = 0; dx < BOARD_W; dx++)
            if (s->mask[d->rot][dy] & (1u << dx))
                g->color[d->y + dy][d->x + dx] = (uint8_t)(piece + 1);

    Drop tmp;
    drop_piece(g->rows, piece, d->rot, d->x, &tmp);

    /* mesma compactação de linhas, agora nas cores */
    int write = 0;
    for (int read = 0; read < BOARD_ROWS; read++) {
        int full = 0;
        for (int k = 0; k < d->cleared; k++)
            if (d->cleared_rows[k] == read) full = 1;
        if (full) continue;
        if (write != read) memcpy(g->color[write], g->color[read], BOARD_W);
        write++;
    }
    for (; write < BOARD_ROWS; write++) memset(g->color[write], 0, BOARD_W);

    g->score += POINTS[d->cleared];
    g->lines += d->cleared;
    if (d->cleared == 4) g->tetrises++;
    g->pieces++;
}
