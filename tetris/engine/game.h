/*
 * game.h — Tetris como bitboard: cada linha é um uint16_t com 10 bits.
 *
 * A IA não aperta botões: para cada peça ela enumera toda combinação
 * rotação × coluna, "solta" a peça e avalia o tabuleiro resultante.
 *   linha 0 = fundo; linhas 20..23 são a zona de spawn (acima da tela)
 */
#ifndef GAME_H
#define GAME_H

#include <stdint.h>

#define BOARD_W     10
#define BOARD_H     20
#define BOARD_ROWS  24
#define FULL_ROW    0x3FF
#define NUM_PIECES  7

enum { PIECE_I, PIECE_O, PIECE_T, PIECE_S, PIECE_Z, PIECE_J, PIECE_L };
extern const char PIECE_NAMES[NUM_PIECES + 1];

typedef struct {
    int count;              /* rotações distintas (1, 2 ou 4) */
    uint16_t mask[4][4];    /* [rotação][dy] bits das colunas, a partir de x = 0 */
    int width[4], height[4];
} PieceShape;

extern PieceShape SHAPES[NUM_PIECES];

typedef struct {
    uint64_t state;
    int bag[NUM_PIECES], left;
} Rng;

typedef struct {
    uint16_t rows[BOARD_ROWS];
    uint8_t color[BOARD_ROWS][BOARD_W];   /* só pra replay: qual peça pintou a casa */
    Rng rng;
    long score;
    int lines, tetrises, pieces, over;
} Game;

/* resultado de soltar uma peça: onde ela parou e o que limpou */
typedef struct {
    int rot, x, y;
    int cleared;
    int cleared_rows[4];    /* índices das linhas antes da limpeza */
} Drop;

void     shapes_init(void);
uint64_t rng_next(uint64_t *s);
double   rng_uniform(uint64_t *s);
double   rng_gauss(uint64_t *s);
void     game_init(Game *g, uint64_t seed);
int      game_next_piece(Game *g);

/* solta a peça em rows (modifica); 0 se não cabe ou estoura o topo */
int  drop_piece(uint16_t *rows, int piece, int rot, int x, Drop *out);
void game_apply(Game *g, int piece, const Drop *d);

#endif
