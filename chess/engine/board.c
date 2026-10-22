/*
 * board.c — FEN, Zobrist, geração de lances, make/unmake, SAN e perft.
 */
#include "board.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

uint64_t zob_piece[16][128], zob_side, zob_castle[16], zob_ep[8];

static const int knight_off[8] = { 33, 31, 18, 14, -33, -31, -18, -14 };
static const int king_off[8]   = { 1, -1, 16, -16, 15, 17, -15, -17 };
static const int bishop_dir[4] = { 15, 17, -15, -17 };
static const int rook_dir[4]   = { 1, -1, 16, -16 };

/* direitos de roque que sobrevivem a um lance que toca a casa */
static int castle_mask[128];

static uint64_t rng_state = 0x9E3779B97F4A7C15ULL;

/* splitmix64: semente fixa = hashes iguais em toda execução */
static uint64_t rand64(void)
{
    uint64_t z = (rng_state += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

void board_init(void)
{
    for (int p = 0; p < 16; p++)
        for (int s = 0; s < 128; s++)
            zob_piece[p][s] = rand64();
    zob_side = rand64();
    for (int i = 0; i < 16; i++) zob_castle[i] = rand64();
    for (int i = 0; i < 8; i++)  zob_ep[i] = rand64();

    for (int s = 0; s < 128; s++) castle_mask[s] = 15;
    castle_mask[SQ(0, 0)] &= ~CASTLE_WQ;
    castle_mask[SQ(7, 0)] &= ~CASTLE_WK;
    castle_mask[SQ(4, 0)] &= ~(CASTLE_WK | CASTLE_WQ);
    castle_mask[SQ(0, 7)] &= ~CASTLE_BQ;
    castle_mask[SQ(7, 7)] &= ~CASTLE_BK;
    castle_mask[SQ(4, 7)] &= ~(CASTLE_BK | CASTLE_BQ);
}

uint64_t pos_compute_hash(const Position *p)
{
    uint64_t h = 0;
    for (int s = 0; s < 128; s++)
        if (!OFFBOARD(s) && p->board[s]) h ^= zob_piece[p->board[s]][s];
    if (p->side == BLACK) h ^= zob_side;
    h ^= zob_castle[p->castle];
    if (p->ep != NO_SQ) h ^= zob_ep[FILE_OF(p->ep)];
    return h;
}

/* ------------------------------------------------------------------ FEN */

static int piece_from_char(char c)
{
    const char *s = strchr("pnbrqk", tolower((unsigned char)c));
    if (!s || !c) return EMPTY;
    return MAKE_PIECE(isupper((unsigned char)c) ? WHITE : BLACK, (int)(s - "pnbrqk") + 1);
}

int pos_from_fen(Position *p, const char *fen)
{
    memset(p, 0, sizeof(*p));
    p->ep = NO_SQ;
    p->king[WHITE] = p->king[BLACK] = NO_SQ;

    int file = 0, rank = 7;
    const char *c = fen;
    for (; *c && *c != ' '; c++) {
        if (*c == '/') { file = 0; rank--; continue; }
        if (isdigit((unsigned char)*c)) { file += *c - '0'; continue; }
        int pc = piece_from_char(*c);
        if (!pc || file > 7 || rank < 0) return 0;
        p->board[SQ(file, rank)] = pc;
        if (TYPE(pc) == KING) p->king[COLOR(pc)] = SQ(file, rank);
        file++;
    }
    if (p->king[WHITE] == NO_SQ || p->king[BLACK] == NO_SQ) return 0;

    while (*c == ' ') c++;
    p->side = (*c == 'b') ? BLACK : WHITE;
    if (*c) c++;
    while (*c == ' ') c++;
    for (; *c && *c != ' '; c++) {
        if (*c == 'K') p->castle |= CASTLE_WK;
        if (*c == 'Q') p->castle |= CASTLE_WQ;
        if (*c == 'k') p->castle |= CASTLE_BK;
        if (*c == 'q') p->castle |= CASTLE_BQ;
    }
    while (*c == ' ') c++;
    if (c[0] >= 'a' && c[0] <= 'h' && c[1] >= '1' && c[1] <= '8') {
        p->ep = SQ(c[0] - 'a', c[1] - '1');
        c += 2;
    } else if (*c) {
        c++;
    }
    p->fullmove = 1;
    sscanf(c, "%d %d", &p->halfmove, &p->fullmove);
    p->hash = pos_compute_hash(p);
    return 1;
}

void pos_to_fen(const Position *p, char *out)
{
    for (int rank = 7; rank >= 0; rank--) {
        int empty = 0;
        for (int file = 0; file < 8; file++) {
            int pc = p->board[SQ(file, rank)];
            if (!pc) { empty++; continue; }
            if (empty) { *out++ = (char)('0' + empty); empty = 0; }
            char ch = " pnbrqk"[TYPE(pc)];
            *out++ = COLOR(pc) == WHITE ? (char)toupper(ch) : ch;
        }
        if (empty) *out++ = (char)('0' + empty);
        if (rank) *out++ = '/';
    }
    *out++ = ' ';
    *out++ = p->side == WHITE ? 'w' : 'b';
    *out++ = ' ';
    if (!p->castle) *out++ = '-';
    if (p->castle & CASTLE_WK) *out++ = 'K';
    if (p->castle & CASTLE_WQ) *out++ = 'Q';
    if (p->castle & CASTLE_BK) *out++ = 'k';
    if (p->castle & CASTLE_BQ) *out++ = 'q';
    *out++ = ' ';
    if (p->ep == NO_SQ) {
        *out++ = '-';
    } else {
        *out++ = (char)('a' + FILE_OF(p->ep));
        *out++ = (char)('1' + RANK_OF(p->ep));
    }
    sprintf(out, " %d %d", p->halfmove, p->fullmove);
}

/* -------------------------------------------------------------- ataques */

int is_attacked(const Position *p, int sq, int by)
{
    const int *b = p->board;

    if (by == WHITE) {
        if (!OFFBOARD(sq - 15) && b[sq - 15] == MAKE_PIECE(WHITE, PAWN)) return 1;
        if (!OFFBOARD(sq - 17) && b[sq - 17] == MAKE_PIECE(WHITE, PAWN)) return 1;
    } else {
        if (!OFFBOARD(sq + 15) && b[sq + 15] == MAKE_PIECE(BLACK, PAWN)) return 1;
        if (!OFFBOARD(sq + 17) && b[sq + 17] == MAKE_PIECE(BLACK, PAWN)) return 1;
    }

    for (int i = 0; i < 8; i++) {
        int t = sq + knight_off[i];
        if (!OFFBOARD(t) && b[t] == MAKE_PIECE(by, KNIGHT)) return 1;
        t = sq + king_off[i];
        if (!OFFBOARD(t) && b[t] == MAKE_PIECE(by, KING)) return 1;
    }

    for (int i = 0; i < 4; i++) {
        for (int t = sq + bishop_dir[i]; !OFFBOARD(t); t += bishop_dir[i]) {
            if (!b[t]) continue;
            if (b[t] == MAKE_PIECE(by, BISHOP) || b[t] == MAKE_PIECE(by, QUEEN)) return 1;
            break;
        }
        for (int t = sq + rook_dir[i]; !OFFBOARD(t); t += rook_dir[i]) {
            if (!b[t]) continue;
            if (b[t] == MAKE_PIECE(by, ROOK) || b[t] == MAKE_PIECE(by, QUEEN)) return 1;
            break;
        }
    }
    return 0;
}

int in_check(const Position *p, int side)
{
    return is_attacked(p, p->king[side], side ^ 1);
}

/* ------------------------------------------------------ geração de lances */

static void add(MoveList *l, int m) { l->moves[l->count++] = m; }

static void add_promos(MoveList *l, int from, int to, int flags, int captures_only)
{
    add(l, MOVE(from, to, QUEEN, flags | F_PROMO));
    if (captures_only) return;   /* na quiescência só a dama importa */
    add(l, MOVE(from, to, ROOK, flags | F_PROMO));
    add(l, MOVE(from, to, BISHOP, flags | F_PROMO));
    add(l, MOVE(from, to, KNIGHT, flags | F_PROMO));
}

static void gen_pawn(const Position *p, MoveList *l, int sq, int captures_only)
{
    int side = p->side;
    int fwd = side == WHITE ? 16 : -16;
    int start_rank = side == WHITE ? 1 : 6;
    int promo_rank = side == WHITE ? 7 : 0;

    int t = sq + fwd;
    if (!OFFBOARD(t) && !p->board[t]) {
        if (RANK_OF(t) == promo_rank) {
            add_promos(l, sq, t, 0, captures_only);
        } else if (!captures_only) {
            add(l, MOVE(sq, t, 0, 0));
            if (RANK_OF(sq) == start_rank && !p->board[t + fwd])
                add(l, MOVE(sq, t + fwd, 0, F_DOUBLE));
        }
    }

    for (int d = -1; d <= 1; d += 2) {
        t = sq + fwd + d;
        if (OFFBOARD(t)) continue;
        int victim = p->board[t];
        if (victim && COLOR(victim) != side) {
            if (RANK_OF(t) == promo_rank) add_promos(l, sq, t, F_CAPTURE, captures_only);
            else add(l, MOVE(sq, t, 0, F_CAPTURE));
        } else if (t == p->ep) {
            add(l, MOVE(sq, t, 0, F_CAPTURE | F_EP));
        }
    }
}

static void gen_leaper(const Position *p, MoveList *l, int sq, const int *off, int captures_only)
{
    for (int i = 0; i < 8; i++) {
        int t = sq + off[i];
        if (OFFBOARD(t)) continue;
        int victim = p->board[t];
        if (!victim) {
            if (!captures_only) add(l, MOVE(sq, t, 0, 0));
        } else if (COLOR(victim) != p->side) {
            add(l, MOVE(sq, t, 0, F_CAPTURE));
        }
    }
}

static void gen_slider(const Position *p, MoveList *l, int sq, const int *dir, int captures_only)
{
    for (int i = 0; i < 4; i++) {
        for (int t = sq + dir[i]; !OFFBOARD(t); t += dir[i]) {
            int victim = p->board[t];
            if (!victim) {
                if (!captures_only) add(l, MOVE(sq, t, 0, 0));
                continue;
            }
            if (COLOR(victim) != p->side) add(l, MOVE(sq, t, 0, F_CAPTURE));
            break;
        }
    }
}

static void gen_castles(const Position *p, MoveList *l)
{
    int side = p->side, them = side ^ 1;
    int base = side == WHITE ? 0 : 112;
    int ks = side == WHITE ? CASTLE_WK : CASTLE_BK;
    int qs = side == WHITE ? CASTLE_WQ : CASTLE_BQ;
    int rook = MAKE_PIECE(side, ROOK);
    int e = base + 4;

    if (p->king[side] != e) return;
    /* a casa de destino é checada pelo próprio make_move */
    if ((p->castle & ks) && p->board[base + 7] == rook &&
        !p->board[base + 5] && !p->board[base + 6] &&
        !is_attacked(p, e, them) && !is_attacked(p, base + 5, them))
        add(l, MOVE(e, base + 6, 0, F_CASTLE));
    if ((p->castle & qs) && p->board[base] == rook &&
        !p->board[base + 3] && !p->board[base + 2] && !p->board[base + 1] &&
        !is_attacked(p, e, them) && !is_attacked(p, base + 3, them))
        add(l, MOVE(e, base + 2, 0, F_CASTLE));
}

/* pseudo-legais: o rei pode ficar em xeque; make_move filtra */
void gen_moves(const Position *p, MoveList *l, int captures_only)
{
    l->count = 0;
    for (int sq = 0; sq < 128; sq++) {
        if (OFFBOARD(sq)) { sq += 7; continue; }
        int pc = p->board[sq];
        if (!pc || COLOR(pc) != p->side) continue;
        switch (TYPE(pc)) {
        case PAWN:   gen_pawn(p, l, sq, captures_only); break;
        case KNIGHT: gen_leaper(p, l, sq, knight_off, captures_only); break;
        case BISHOP: gen_slider(p, l, sq, bishop_dir, captures_only); break;
        case ROOK:   gen_slider(p, l, sq, rook_dir, captures_only); break;
        case QUEEN:
            gen_slider(p, l, sq, bishop_dir, captures_only);
            gen_slider(p, l, sq, rook_dir, captures_only);
            break;
        case KING:
            gen_leaper(p, l, sq, king_off, captures_only);
            if (!captures_only) gen_castles(p, l);
            break;
        }
    }
}

void gen_legal(Position *p, MoveList *l)
{
    MoveList all;
    gen_moves(p, &all, 0);
    l->count = 0;
    for (int i = 0; i < all.count; i++) {
        if (!make_move(p, all.moves[i])) continue;
        unmake_move(p);
        add(l, all.moves[i]);
    }
}

/* ---------------------------------------------------------- make/unmake */

static void castle_rook_squares(int to, int *rf, int *rt)
{
    if (FILE_OF(to) == 6) { *rf = to + 1; *rt = to - 1; }   /* O-O   */
    else                  { *rf = to - 2; *rt = to + 1; }   /* O-O-O */
}

int make_move(Position *p, int m)
{
    int from = MV_FROM(m), to = MV_TO(m), fl = MV_FLAGS(m);
    int side = p->side;
    int piece = p->board[from];
    uint64_t h = p->hash;

    Undo *u = &p->hist[p->hply++];
    u->move = m;
    u->captured = p->board[to];
    u->castle = p->castle;
    u->ep = p->ep;
    u->halfmove = p->halfmove;
    u->hash = p->hash;

    if (p->ep != NO_SQ) h ^= zob_ep[FILE_OF(p->ep)];
    h ^= zob_castle[p->castle];

    if (u->captured) h ^= zob_piece[u->captured][to];
    if (fl & F_EP) {
        int cap = side == WHITE ? to - 16 : to + 16;
        u->captured = p->board[cap];
        p->board[cap] = EMPTY;
        h ^= zob_piece[u->captured][cap];
    }

    int placed = (fl & F_PROMO) ? MAKE_PIECE(side, MV_PROMO(m)) : piece;
    p->board[from] = EMPTY;
    p->board[to] = placed;
    h ^= zob_piece[piece][from] ^ zob_piece[placed][to];

    if (fl & F_CASTLE) {
        int rf, rt;
        castle_rook_squares(to, &rf, &rt);
        int rook = p->board[rf];
        p->board[rf] = EMPTY;
        p->board[rt] = rook;
        h ^= zob_piece[rook][rf] ^ zob_piece[rook][rt];
    }

    if (TYPE(piece) == KING) p->king[side] = to;
    p->castle &= castle_mask[from] & castle_mask[to];
    h ^= zob_castle[p->castle];

    /* en passant só entra no hash se alguém puder capturar de fato —
       assim posições idênticas são reconhecidas como repetição */
    p->ep = NO_SQ;
    if (fl & F_DOUBLE) {
        int enemy_pawn = MAKE_PIECE(side ^ 1, PAWN);
        if ((!OFFBOARD(to - 1) && p->board[to - 1] == enemy_pawn) ||
            (!OFFBOARD(to + 1) && p->board[to + 1] == enemy_pawn)) {
            p->ep = (from + to) / 2;
            h ^= zob_ep[FILE_OF(p->ep)];
        }
    }

    p->halfmove = (TYPE(piece) == PAWN || u->captured) ? 0 : p->halfmove + 1;
    if (side == BLACK) p->fullmove++;
    p->side ^= 1;
    h ^= zob_side;
    p->hash = h;

    if (is_attacked(p, p->king[side], side ^ 1)) {
        unmake_move(p);
        return 0;
    }
    return 1;
}

void unmake_move(Position *p)
{
    Undo *u = &p->hist[--p->hply];
    int m = u->move, from = MV_FROM(m), to = MV_TO(m), fl = MV_FLAGS(m);

    p->side ^= 1;
    int side = p->side;
    int piece = (fl & F_PROMO) ? MAKE_PIECE(side, PAWN) : p->board[to];

    p->board[from] = piece;
    if (fl & F_EP) {
        p->board[to] = EMPTY;
        p->board[side == WHITE ? to - 16 : to + 16] = u->captured;
    } else {
        p->board[to] = u->captured;
    }

    if (fl & F_CASTLE) {
        int rf, rt;
        castle_rook_squares(to, &rf, &rt);
        p->board[rf] = p->board[rt];
        p->board[rt] = EMPTY;
    }

    if (TYPE(piece) == KING) p->king[side] = from;
    if (side == BLACK) p->fullmove--;
    p->castle = u->castle;
    p->ep = u->ep;
    p->halfmove = u->halfmove;
    p->hash = u->hash;
}

/* "passar a vez" — usado pelo null-move pruning na busca */
void make_null(Position *p)
{
    Undo *u = &p->hist[p->hply++];
    u->move = 0;
    u->captured = EMPTY;
    u->castle = p->castle;
    u->ep = p->ep;
    u->halfmove = p->halfmove;
    u->hash = p->hash;

    if (p->ep != NO_SQ) p->hash ^= zob_ep[FILE_OF(p->ep)];
    p->ep = NO_SQ;
    p->halfmove = 0;   /* repetição não atravessa um null move */
    p->side ^= 1;
    p->hash ^= zob_side;
}

void unmake_null(Position *p)
{
    Undo *u = &p->hist[--p->hply];
    p->side ^= 1;
    p->ep = u->ep;
    p->halfmove = u->halfmove;
    p->hash = u->hash;
}

/* ------------------------------------------------------------ empates */

int repetition_count(const Position *p)
{
    int count = 1;
    for (int i = p->hply - 2; i >= 0 && i >= p->hply - p->halfmove; i -= 2)
        if (p->hist[i].hash == p->hash) count++;
    return count;
}

int insufficient_material(const Position *p)
{
    int minors = 0;
    for (int s = 0; s < 128; s++) {
        if (OFFBOARD(s) || !p->board[s]) continue;
        int t = TYPE(p->board[s]);
        if (t == PAWN || t == ROOK || t == QUEEN) return 0;
        if (t == KNIGHT || t == BISHOP) minors++;
    }
    return minors <= 1;
}

int has_non_pawn_material(const Position *p, int side)
{
    for (int s = 0; s < 128; s++) {
        if (OFFBOARD(s)) continue;
        int pc = p->board[s];
        if (pc && COLOR(pc) == side && TYPE(pc) != PAWN && TYPE(pc) != KING) return 1;
    }
    return 0;
}

/* ------------------------------------------------------------- notação */

void move_to_uci(int m, char *out)
{
    int from = MV_FROM(m), to = MV_TO(m);
    out[0] = (char)('a' + FILE_OF(from));
    out[1] = (char)('1' + RANK_OF(from));
    out[2] = (char)('a' + FILE_OF(to));
    out[3] = (char)('1' + RANK_OF(to));
    out[4] = (MV_FLAGS(m) & F_PROMO) ? " pnbrqk"[MV_PROMO(m)] : '\0';
    out[5] = '\0';
}

void move_to_san(Position *p, int m, char *out)
{
    int from = MV_FROM(m), to = MV_TO(m), fl = MV_FLAGS(m);
    int pc = p->board[from];
    char *o = out;

    if (fl & F_CASTLE) {
        strcpy(o, FILE_OF(to) == 6 ? "O-O" : "O-O-O");
        o += strlen(o);
    } else if (TYPE(pc) == PAWN) {
        if (fl & F_CAPTURE) {
            *o++ = (char)('a' + FILE_OF(from));
            *o++ = 'x';
        }
        *o++ = (char)('a' + FILE_OF(to));
        *o++ = (char)('1' + RANK_OF(to));
        if (fl & F_PROMO) {
            *o++ = '=';
            *o++ = " PNBRQK"[MV_PROMO(m)];
        }
    } else {
        *o++ = " PNBRQK"[TYPE(pc)];

        /* desambiguação: outra peça igual que também chega em `to` */
        MoveList l;
        gen_legal(p, &l);
        int ambiguous = 0, same_file = 0, same_rank = 0;
        for (int i = 0; i < l.count; i++) {
            int f2 = MV_FROM(l.moves[i]);
            if (MV_TO(l.moves[i]) != to || f2 == from || p->board[f2] != pc) continue;
            ambiguous = 1;
            if (FILE_OF(f2) == FILE_OF(from)) same_file = 1;
            if (RANK_OF(f2) == RANK_OF(from)) same_rank = 1;
        }
        if (ambiguous) {
            if (!same_file) {
                *o++ = (char)('a' + FILE_OF(from));
            } else if (!same_rank) {
                *o++ = (char)('1' + RANK_OF(from));
            } else {
                *o++ = (char)('a' + FILE_OF(from));
                *o++ = (char)('1' + RANK_OF(from));
            }
        }
        if (fl & F_CAPTURE) *o++ = 'x';
        *o++ = (char)('a' + FILE_OF(to));
        *o++ = (char)('1' + RANK_OF(to));
    }

    if (make_move(p, m)) {
        if (in_check(p, p->side)) {
            MoveList replies;
            gen_legal(p, &replies);
            *o++ = replies.count ? '+' : '#';
        }
        unmake_move(p);
    }
    *o = '\0';
}

int parse_uci(Position *p, const char *s)
{
    MoveList l;
    char buf[6];
    gen_legal(p, &l);
    for (int i = 0; i < l.count; i++) {
        move_to_uci(l.moves[i], buf);
        if (strcmp(buf, s) == 0) return l.moves[i];
    }
    return 0;
}

/* ---------------------------------------------------------------- perft */

uint64_t perft(Position *p, int depth)
{
    if (depth == 0) return 1;
    MoveList l;
    gen_moves(p, &l, 0);
    uint64_t nodes = 0;
    for (int i = 0; i < l.count; i++) {
        if (!make_move(p, l.moves[i])) continue;
        nodes += perft(p, depth - 1);
        unmake_move(p);
    }
    return nodes;
}
