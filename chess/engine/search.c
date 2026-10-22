/*
 * search.c — avaliação tapered + busca.
 *
 * Busca: aprofundamento iterativo -> PVS (principal variation search) com
 *   tabela de transposição (Zobrist), null-move pruning, late move
 *   reductions, extensão de xeque, killers + history heuristic e
 *   quiescência só com capturas (ordenadas por MVV-LVA).
 * Avaliação: material + tabelas peça-casa interpoladas entre meio-jogo e
 *   final pela fase do jogo, estrutura de peões (passados, dobrados,
 *   isolados), par de bispos, torres em colunas abertas e "mop-up" para
 *   conseguir dar mate em finais ganhos.
 */
#include "search.h"

#include <stdlib.h>
#include <string.h>
#include <time.h>

/* --------------------------------------------------------------- avaliação */

static const int piece_val[7] = { 0, 100, 320, 330, 500, 900, 0 };
static const int phase_inc[7] = { 0, 0, 1, 1, 2, 4, 0 };

/* tabelas do ponto de vista das brancas, índice 0 = a8 (como se lê o tabuleiro) */
static const int pawn_pst[64] = {
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
};
static const int knight_pst[64] = {
   -50,-40,-30,-30,-30,-30,-40,-50,
   -40,-20,  0,  0,  0,  0,-20,-40,
   -30,  0, 10, 15, 15, 10,  0,-30,
   -30,  5, 15, 20, 20, 15,  5,-30,
   -30,  0, 15, 20, 20, 15,  0,-30,
   -30,  5, 10, 15, 15, 10,  5,-30,
   -40,-20,  0,  5,  5,  0,-20,-40,
   -50,-40,-30,-30,-30,-30,-40,-50,
};
static const int bishop_pst[64] = {
   -20,-10,-10,-10,-10,-10,-10,-20,
   -10,  0,  0,  0,  0,  0,  0,-10,
   -10,  0,  5, 10, 10,  5,  0,-10,
   -10,  5,  5, 10, 10,  5,  5,-10,
   -10,  0, 10, 10, 10, 10,  0,-10,
   -10, 10, 10, 10, 10, 10, 10,-10,
   -10,  5,  0,  0,  0,  0,  5,-10,
   -20,-10,-10,-10,-10,-10,-10,-20,
};
static const int rook_pst[64] = {
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0,
};
static const int queen_pst[64] = {
   -20,-10,-10, -5, -5,-10,-10,-20,
   -10,  0,  0,  0,  0,  0,  0,-10,
   -10,  0,  5,  5,  5,  5,  0,-10,
    -5,  0,  5,  5,  5,  5,  0, -5,
     0,  0,  5,  5,  5,  5,  0, -5,
   -10,  5,  5,  5,  5,  5,  0,-10,
   -10,  0,  5,  0,  0,  0,  0,-10,
   -20,-10,-10, -5, -5,-10,-10,-20,
};
static const int king_mg_pst[64] = {
   -30,-40,-40,-50,-50,-40,-40,-30,
   -30,-40,-40,-50,-50,-40,-40,-30,
   -30,-40,-40,-50,-50,-40,-40,-30,
   -30,-40,-40,-50,-50,-40,-40,-30,
   -20,-30,-30,-40,-40,-30,-30,-20,
   -10,-20,-20,-20,-20,-20,-20,-10,
    20, 20,  0,  0,  0,  0, 20, 20,
    20, 30, 10,  0,  0, 10, 30, 20,
};
static const int king_eg_pst[64] = {
   -50,-40,-30,-20,-20,-30,-40,-50,
   -30,-20,-10,  0,  0,-10,-20,-30,
   -30,-10, 20, 30, 30, 20,-10,-30,
   -30,-10, 30, 40, 40, 30,-10,-30,
   -30,-10, 30, 40, 40, 30,-10,-30,
   -30,-10, 20, 30, 30, 20,-10,-30,
   -30,-30,  0,  0,  0,  0,-30,-30,
   -50,-30,-30,-30,-30,-30,-30,-50,
};

/* bônus de peão passado por fileira relativa (1..6) */
static const int passed_mg[8] = { 0, 5, 10, 15, 25, 40, 60, 0 };
static const int passed_eg[8] = { 0, 10, 20, 35, 60, 100, 150, 0 };

static int center_distance(int sq)
{
    int f = FILE_OF(sq), r = RANK_OF(sq);
    int df = f < 4 ? 3 - f : f - 4;
    int dr = r < 4 ? 3 - r : r - 4;
    return df + dr;
}

static int king_distance(int a, int b)
{
    return abs(FILE_OF(a) - FILE_OF(b)) + abs(RANK_OF(a) - RANK_OF(b));
}

int evaluate(const Position *p)
{
    int mg[2] = { 0, 0 }, eg[2] = { 0, 0 };
    int phase = 0, bishops[2] = { 0, 0 };
    int pawns_on_file[2][8] = { { 0 } };
    int min_rank[2][8], max_rank[2][8];

    if (insufficient_material(p)) return 0;

    for (int f = 0; f < 8; f++) {
        min_rank[WHITE][f] = min_rank[BLACK][f] = 8;
        max_rank[WHITE][f] = max_rank[BLACK][f] = -1;
    }
    for (int s = 0; s < 128; s++) {
        if (OFFBOARD(s) || TYPE(p->board[s]) != PAWN) continue;
        int c = COLOR(p->board[s]), f = FILE_OF(s), r = RANK_OF(s);
        pawns_on_file[c][f]++;
        if (r < min_rank[c][f]) min_rank[c][f] = r;
        if (r > max_rank[c][f]) max_rank[c][f] = r;
    }

    for (int s = 0; s < 128; s++) {
        if (OFFBOARD(s) || !p->board[s]) continue;
        int pc = p->board[s], c = COLOR(pc), t = TYPE(pc);
        int f = FILE_OF(s), r = RANK_OF(s);
        int idx = c == WHITE ? (7 - r) * 8 + f : r * 8 + f;

        mg[c] += piece_val[t];
        eg[c] += piece_val[t];
        phase += phase_inc[t];

        switch (t) {
        case PAWN: {
            mg[c] += pawn_pst[idx];
            eg[c] += pawn_pst[idx];

            int passed = 1, isolated = 1;
            for (int ff = f - 1; ff <= f + 1; ff++) {
                if (ff < 0 || ff > 7) continue;
                if (c == WHITE && max_rank[BLACK][ff] > r) passed = 0;
                if (c == BLACK && min_rank[WHITE][ff] < r) passed = 0;
                if (ff != f && pawns_on_file[c][ff]) isolated = 0;
            }
            if (passed) {
                int rel = c == WHITE ? r : 7 - r;
                mg[c] += passed_mg[rel];
                eg[c] += passed_eg[rel];
            }
            if (isolated) { mg[c] -= 10; eg[c] -= 15; }
            break;
        }
        case KNIGHT:
            mg[c] += knight_pst[idx];
            eg[c] += knight_pst[idx];
            break;
        case BISHOP:
            mg[c] += bishop_pst[idx];
            eg[c] += bishop_pst[idx];
            bishops[c]++;
            break;
        case ROOK:
            mg[c] += rook_pst[idx];
            eg[c] += rook_pst[idx];
            if (!pawns_on_file[c][f]) {
                int bonus = pawns_on_file[c ^ 1][f] ? 10 : 20;
                mg[c] += bonus;
                eg[c] += bonus / 2;
            }
            break;
        case QUEEN:
            mg[c] += queen_pst[idx];
            eg[c] += queen_pst[idx];
            break;
        case KING:
            mg[c] += king_mg_pst[idx];
            eg[c] += king_eg_pst[idx];
            break;
        }
    }

    for (int c = 0; c < 2; c++) {
        for (int f = 0; f < 8; f++) {
            if (pawns_on_file[c][f] > 1) {
                mg[c] -= 12 * (pawns_on_file[c][f] - 1);
                eg[c] -= 20 * (pawns_on_file[c][f] - 1);
            }
        }
        if (bishops[c] >= 2) { mg[c] += 30; eg[c] += 50; }
    }

    /* mop-up: com vantagem grande, empurra o rei inimigo pra borda
       e aproxima o próprio rei — sem isso a engine "passeia" em finais ganhos */
    int diff = eg[WHITE] - eg[BLACK];
    if (abs(diff) > 300) {
        int strong = diff > 0 ? WHITE : BLACK;
        int ks = p->king[strong], kw = p->king[strong ^ 1];
        eg[strong] += center_distance(kw) * 10 + (14 - king_distance(ks, kw)) * 4;
    }

    if (phase > 24) phase = 24;
    int mg_score = mg[WHITE] - mg[BLACK];
    int eg_score = eg[WHITE] - eg[BLACK];
    int score = (mg_score * phase + eg_score * (24 - phase)) / 24;

    return (p->side == WHITE ? score : -score) + 10;   /* +10 = tempo */
}

/* ---------------------------------------------------- tabela de transposição */

enum { TT_EXACT, TT_LOWER, TT_UPPER };

typedef struct {
    uint64_t key;
    int move;
    short score;
    signed char depth;
    unsigned char flag;
} TTEntry;

#define TT_BITS 20
#define TT_SIZE (1u << TT_BITS)
static TTEntry tt[TT_SIZE];

static TTEntry *tt_probe(uint64_t key)
{
    TTEntry *e = &tt[key & (TT_SIZE - 1)];
    return e->key == key ? e : NULL;
}

static void tt_store(uint64_t key, int move, int score, int depth, int flag)
{
    TTEntry *e = &tt[key & (TT_SIZE - 1)];
    /* substitui se for outra posição ou se a busca nova for ao menos tão funda */
    if (e->key != key || depth >= e->depth) {
        e->key = key;
        e->move = move;
        e->score = (short)score;
        e->depth = (signed char)depth;
        e->flag = (unsigned char)flag;
    } else if (move) {
        e->move = move;
    }
}

/* mates são guardados relativos ao nó, não à raiz */
static int score_to_tt(int s, int ply)
{
    if (s > MATE - MAX_PLY) return s + ply;
    if (s < -MATE + MAX_PLY) return s - ply;
    return s;
}

static int score_from_tt(int s, int ply)
{
    if (s > MATE - MAX_PLY) return s - ply;
    if (s < -MATE + MAX_PLY) return s + ply;
    return s;
}

/* ------------------------------------------------------------------- busca */

static struct {
    long long nodes;
    clock_t start;
    int time_ms;
    int stop;
    int root_best;
    int killers[MAX_PLY][2];
    int history[16][128];
} S;

void search_init(void)
{
    memset(tt, 0, sizeof(tt));
}

static int elapsed_ms(void)
{
    return (int)((clock() - S.start) * 1000 / CLOCKS_PER_SEC);
}

static void check_time(void)
{
    if (elapsed_ms() >= S.time_ms) S.stop = 1;
}

static void score_moves(const Position *p, MoveList *l, int tt_move, int ply)
{
    for (int i = 0; i < l->count; i++) {
        int m = l->moves[i], fl = MV_FLAGS(m);
        int attacker = TYPE(p->board[MV_FROM(m)]);
        if (m == tt_move) {
            l->scores[i] = 1000000;
        } else if (fl & F_CAPTURE) {
            int victim = (fl & F_EP) ? PAWN : TYPE(p->board[MV_TO(m)]);
            l->scores[i] = 100000 + piece_val[victim] * 10 - attacker;   /* MVV-LVA */
            if (fl & F_PROMO) l->scores[i] += piece_val[MV_PROMO(m)];
        } else if (fl & F_PROMO) {
            l->scores[i] = 90000 + piece_val[MV_PROMO(m)];
        } else if (m == S.killers[ply][0]) {
            l->scores[i] = 80000;
        } else if (m == S.killers[ply][1]) {
            l->scores[i] = 79000;
        } else {
            l->scores[i] = S.history[p->board[MV_FROM(m)]][MV_TO(m)];
        }
    }
}

/* seleção parcial: só ordena o que a poda de fato chega a olhar */
static int pick_move(MoveList *l, int start)
{
    int best = start;
    for (int i = start + 1; i < l->count; i++)
        if (l->scores[i] > l->scores[best]) best = i;
    int m = l->moves[best], s = l->scores[best];
    l->moves[best] = l->moves[start];
    l->scores[best] = l->scores[start];
    l->moves[start] = m;
    l->scores[start] = s;
    return m;
}

static int quiesce(Position *p, int alpha, int beta, int ply)
{
    if ((++S.nodes & 2047) == 0) check_time();
    if (S.stop) return 0;

    int stand = evaluate(p);
    if (ply >= MAX_PLY - 1 || stand >= beta) return stand;
    if (stand > alpha) alpha = stand;

    MoveList l;
    gen_moves(p, &l, 1);
    score_moves(p, &l, 0, ply);
    for (int i = 0; i < l.count; i++) {
        int m = pick_move(&l, i);
        if (!make_move(p, m)) continue;
        int score = -quiesce(p, -beta, -alpha, ply + 1);
        unmake_move(p);
        if (S.stop) return 0;
        if (score > alpha) {
            alpha = score;
            if (score >= beta) return score;
        }
    }
    return alpha;
}

static int search(Position *p, int depth, int alpha, int beta, int ply, int allow_null)
{
    int pv_node = beta - alpha > 1;

    if (ply && (p->halfmove >= 100 || repetition_count(p) > 1)) return 0;

    int checked = in_check(p, p->side);
    if (checked) depth++;   /* extensão de xeque: não deixa o horizonte esconder mates */
    if (depth <= 0) return quiesce(p, alpha, beta, ply);

    if ((++S.nodes & 2047) == 0) check_time();
    if (S.stop) return 0;
    if (ply >= MAX_PLY - 1) return evaluate(p);

    int tt_move = 0;
    TTEntry *e = tt_probe(p->hash);
    if (e) {
        tt_move = e->move;
        if (ply && !pv_node && e->depth >= depth) {
            int s = score_from_tt(e->score, ply);
            if (e->flag == TT_EXACT) return s;
            if (e->flag == TT_LOWER && s >= beta) return s;
            if (e->flag == TT_UPPER && s <= alpha) return s;
        }
    }

    /* null move: se mesmo passando a vez a posição ainda passa de beta,
       a linha é boa demais e o oponente nunca vai permitir */
    if (allow_null && !checked && !pv_node && depth >= 3 &&
        has_non_pawn_material(p, p->side) && evaluate(p) >= beta) {
        make_null(p);
        int s = -search(p, depth - 3, -beta, -beta + 1, ply + 1, 0);
        unmake_null(p);
        if (S.stop) return 0;
        if (s >= beta) return beta;
    }

    MoveList l;
    gen_moves(p, &l, 0);
    score_moves(p, &l, tt_move, ply);

    int legal = 0, best = -INF, best_move = 0, old_alpha = alpha;
    for (int i = 0; i < l.count; i++) {
        int m = pick_move(&l, i);
        int piece = p->board[MV_FROM(m)];
        int quiet = !(MV_FLAGS(m) & (F_CAPTURE | F_PROMO));
        if (!make_move(p, m)) continue;
        legal++;

        int score;
        if (legal == 1) {
            score = -search(p, depth - 1, -beta, -alpha, ply + 1, 1);
        } else {
            /* LMR: lances quietos lá no fim da lista provavelmente são ruins */
            int r = 0;
            if (depth >= 3 && legal > 4 && quiet && !checked && !in_check(p, p->side) &&
                m != S.killers[ply][0] && m != S.killers[ply][1])
                r = legal > 10 ? 2 : 1;

            score = -search(p, depth - 1 - r, -alpha - 1, -alpha, ply + 1, 1);
            if (score > alpha && r)
                score = -search(p, depth - 1, -alpha - 1, -alpha, ply + 1, 1);
            if (score > alpha && score < beta)
                score = -search(p, depth - 1, -beta, -alpha, ply + 1, 1);
        }
        unmake_move(p);
        if (S.stop) return 0;

        if (score > best) {
            best = score;
            best_move = m;
            if (ply == 0) S.root_best = m;
            if (score > alpha) {
                alpha = score;
                if (score >= beta) {
                    if (quiet) {
                        if (S.killers[ply][0] != m) {
                            S.killers[ply][1] = S.killers[ply][0];
                            S.killers[ply][0] = m;
                        }
                        S.history[piece][MV_TO(m)] += depth * depth;
                    }
                    break;
                }
            }
        }
    }

    if (!legal) return checked ? -MATE + ply : 0;

    int flag = best >= beta ? TT_LOWER : best > old_alpha ? TT_EXACT : TT_UPPER;
    tt_store(p->hash, best_move, score_to_tt(best, ply), depth, flag);
    return best;
}

/* reconstrói a variante principal seguindo os melhores lances da TT */
static int extract_pv(Position *p, int *pv, int max_len)
{
    int len = 0;
    while (len < max_len) {
        TTEntry *e = tt_probe(p->hash);
        if (!e || !e->move) break;
        MoveList l;
        gen_legal(p, &l);
        int found = 0;
        for (int i = 0; i < l.count; i++)
            if (l.moves[i] == e->move) found = 1;
        if (!found || repetition_count(p) > 1) break;
        make_move(p, e->move);
        pv[len++] = e->move;
    }
    for (int i = 0; i < len; i++) unmake_move(p);
    return len;
}

SearchResult think(Position *p, int time_ms, int max_depth)
{
    SearchResult res;
    memset(&res, 0, sizeof(res));
    memset(S.killers, 0, sizeof(S.killers));
    memset(S.history, 0, sizeof(S.history));
    S.nodes = 0;
    S.stop = 0;
    S.time_ms = time_ms;
    S.start = clock();

    MoveList legal;
    gen_legal(p, &legal);
    if (legal.count == 0) return res;
    res.best_move = legal.moves[0];
    if (max_depth > MAX_PLY - 4) max_depth = MAX_PLY - 4;

    for (int depth = 1; depth <= max_depth; depth++) {
        S.root_best = 0;
        int score = search(p, depth, -INF, INF, 0, 1);

        if (S.stop) {
            /* iteração incompleta: o melhor lance parcial ainda é confiável,
               pois o lance da iteração anterior é sempre buscado primeiro */
            if (S.root_best) res.best_move = S.root_best;
            break;
        }
        res.best_move = S.root_best ? S.root_best : res.best_move;
        res.score = score;
        res.depth = depth;

        if (legal.count == 1) break;                       /* lance forçado */
        if (abs(score) > MATE - MAX_PLY) break;            /* mate encontrado */
        if (elapsed_ms() * 2 > time_ms) break;             /* não dá tempo da próxima */
    }

    res.nodes = S.nodes;
    res.time_ms = elapsed_ms();
    res.pv_len = extract_pv(p, res.pv, MAX_PLY - 1);
    if (res.pv_len == 0 || res.pv[0] != res.best_move) {
        res.pv[0] = res.best_move;
        res.pv_len = 1;
    }
    return res;
}
