/*
 * ai.c — a rede neural não vê pixels: ela vê 8 números que descrevem o
 * tabuleiro *depois* de cada jogada possível e dá uma nota. A IA faz a
 * jogada de maior nota. O que a evolução ajusta são os pesos dessa nota.
 */
#include "ai.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

const char *FEATURE_NAMES[NUM_FEATURES] = {
    "lines", "holes", "height", "bumpiness", "max height", "wells", "row trans.", "col trans.",
};

static int popcount16(unsigned v)
{
    int n = 0;
    for (; v; v &= v - 1) n++;
    return n;
}

void board_features(const uint16_t *rows, int cleared, double *f)
{
    int heights[BOARD_W];
    int holes = 0, agg = 0, bump = 0, max_h = 0, wells = 0, row_tr = 0, col_tr = 0;

    for (int c = 0; c < BOARD_W; c++) {
        int h = 0;
        for (int y = BOARD_H - 1; y >= 0; y--)
            if (rows[y] & (1u << c)) { h = y + 1; break; }
        heights[c] = h;
        agg += h;
        if (h > max_h) max_h = h;
        for (int y = 0; y < h; y++)
            if (!(rows[y] & (1u << c))) holes++;
    }

    for (int c = 0; c < BOARD_W; c++) {
        if (c + 1 < BOARD_W) bump += abs(heights[c] - heights[c + 1]);
        int left = c > 0 ? heights[c - 1] : BOARD_H;
        int right = c + 1 < BOARD_W ? heights[c + 1] : BOARD_H;
        int depth = (left < right ? left : right) - heights[c];
        if (depth > 0) wells += depth;
    }

    /* transições: paredes e chão contam como cheios */
    for (int y = 0; y < max_h; y++) {
        unsigned v = ((unsigned)rows[y] << 1) | 1u | (1u << (BOARD_W + 1));
        row_tr += popcount16((v ^ (v >> 1)) & ((1u << (BOARD_W + 1)) - 1));
    }
    col_tr += popcount16(~(unsigned)rows[0] & FULL_ROW);
    for (int y = 0; y < max_h; y++)
        col_tr += popcount16((rows[y] ^ rows[y + 1]) & FULL_ROW);

    /* escalas aproximadas pra tudo ficar perto de [0, 1] */
    f[0] = cleared / 4.0;
    f[1] = holes / 40.0;
    f[2] = agg / 200.0;
    f[3] = bump / 60.0;
    f[4] = max_h / 20.0;
    f[5] = wells / 40.0;
    f[6] = row_tr / 200.0;
    f[7] = col_tr / 200.0;
}

double nn_forward(const Genome *g, const double *f)
{
    const double *w = g->w;
    double out = w[NUM_GENES - 1];
    for (int j = 0; j < HIDDEN; j++) {
        const double *wj = w + j * (NUM_FEATURES + 1);
        double sum = wj[NUM_FEATURES];
        for (int i = 0; i < NUM_FEATURES; i++) sum += wj[i] * f[i];
        out += w[HIDDEN * (NUM_FEATURES + 1) + j] * tanh(sum);
    }
    return out;
}

static void replay_move(FILE *out, const Game *g, int piece, const Drop *d)
{
    const PieceShape *s = &SHAPES[piece];
    fprintf(out, "%s{\"p\":\"%c\",\"cells\":[", g->pieces ? ",\n" : "", PIECE_NAMES[piece]);
    int first = 1;
    for (int dy = 0; dy < s->height[d->rot]; dy++)
        for (int dx = 0; dx < BOARD_W; dx++)
            if (s->mask[d->rot][dy] & (1u << dx)) {
                fprintf(out, "%s[%d,%d]", first ? "" : ",", d->x + dx, d->y + dy);
                first = 0;
            }
    fprintf(out, "],\"cleared\":[");
    for (int k = 0; k < d->cleared; k++) fprintf(out, "%s%d", k ? "," : "", d->cleared_rows[k]);
    fprintf(out, "]}");
}

void play_game(const Genome *net, uint64_t seed, int max_pieces, Game *g, FILE *replay)
{
    game_init(g, seed);
    while (g->pieces < max_pieces) {
        int piece = game_next_piece(g);
        const PieceShape *s = &SHAPES[piece];

        double best = -1e300;
        Drop best_drop;
        int found = 0;
        for (int rot = 0; rot < s->count; rot++) {
            for (int x = 0; x + s->width[rot] <= BOARD_W; x++) {
                uint16_t rows[BOARD_ROWS];
                Drop d;
                memcpy(rows, g->rows, sizeof(rows));
                if (!drop_piece(rows, piece, rot, x, &d)) continue;

                double f[NUM_FEATURES];
                board_features(rows, d.cleared, f);
                double v = nn_forward(net, f);
                if (!found || v > best) {
                    best = v;
                    best_drop = d;
                    found = 1;
                }
            }
        }
        if (!found) {           /* nenhuma jogada cabe: topo estourou */
            g->over = 1;
            break;
        }
        if (replay) replay_move(replay, g, piece, &best_drop);
        game_apply(g, piece, &best_drop);
    }
}
