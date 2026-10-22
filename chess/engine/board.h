/*
 * board.h — representação do tabuleiro (0x88), lances e regras.
 *
 * O tabuleiro 0x88 usa um array de 128 casas: a metade "fantasma" (bit 0x88)
 * faz a detecção de saída do tabuleiro virar um único AND, sem tabelas.
 *   casa = rank * 16 + file      (a1 = 0, h1 = 7, a8 = 112, h8 = 119)
 */
#ifndef BOARD_H
#define BOARD_H

#include <stdint.h>

enum { WHITE, BLACK };
enum { EMPTY, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING };

#define MAKE_PIECE(c, t) (((c) << 3) | (t))
#define COLOR(p)         ((p) >> 3)
#define TYPE(p)          ((p) & 7)

#define SQ(file, rank)   ((rank) * 16 + (file))
#define FILE_OF(s)       ((s) & 7)
#define RANK_OF(s)       ((s) >> 4)
#define OFFBOARD(s)      ((s) & 0x88)
#define NO_SQ            (-1)

enum { CASTLE_WK = 1, CASTLE_WQ = 2, CASTLE_BK = 4, CASTLE_BQ = 8 };

/* lance em 22 bits: origem(7) destino(7) promoção(3) flags(5) */
#define MOVE(f, t, pr, fl) ((f) | ((t) << 7) | ((pr) << 14) | ((fl) << 17))
#define MV_FROM(m)  ((m) & 0x7f)
#define MV_TO(m)    (((m) >> 7) & 0x7f)
#define MV_PROMO(m) (((m) >> 14) & 7)
#define MV_FLAGS(m) ((m) >> 17)
enum { F_CAPTURE = 1, F_EP = 2, F_CASTLE = 4, F_DOUBLE = 8, F_PROMO = 16 };

#define MAX_MOVES 256
#define MAX_HIST  1024

typedef struct {
    int moves[MAX_MOVES];
    int scores[MAX_MOVES];
    int count;
} MoveList;

/* tudo que make_move destrói e unmake_move precisa restaurar */
typedef struct {
    int move, captured, castle, ep, halfmove;
    uint64_t hash;
} Undo;

typedef struct {
    int board[128];
    int side, castle, ep, halfmove, fullmove;
    int king[2];
    uint64_t hash;           /* Zobrist, atualizado incrementalmente */
    int hply;                /* lances feitos desde a posição inicial */
    Undo hist[MAX_HIST];
} Position;

#define START_FEN "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

extern uint64_t zob_piece[16][128], zob_side, zob_castle[16], zob_ep[8];

void     board_init(void);
int      pos_from_fen(Position *p, const char *fen);
void     pos_to_fen(const Position *p, char *out);
uint64_t pos_compute_hash(const Position *p);

int  is_attacked(const Position *p, int sq, int by);
int  in_check(const Position *p, int side);
void gen_moves(const Position *p, MoveList *l, int captures_only);
void gen_legal(Position *p, MoveList *l);
int  make_move(Position *p, int m);   /* 0 = ilegal (já desfeito) */
void unmake_move(Position *p);
void make_null(Position *p);
void unmake_null(Position *p);

int  repetition_count(const Position *p);
int  insufficient_material(const Position *p);
int  has_non_pawn_material(const Position *p, int side);

void move_to_uci(int m, char *out);
void move_to_san(Position *p, int m, char *out);
int  parse_uci(Position *p, const char *s);   /* lance legal ou 0 */

uint64_t perft(Position *p, int depth);

#endif
