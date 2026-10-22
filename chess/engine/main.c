/*
 * main.c — interface de linha de comando, pensada pra ser chamada pelo
 * GitHub Action. Toda saída de `state` e `think` é JSON.
 *
 *   chess state [lances...]          posição após os lances (UCI, desde o início)
 *   chess think <ms> [lances...]     a engine escolhe o próximo lance
 *   chess perft <prof> [fen]         conta nós da árvore de lances (teste)
 *   chess divide <prof> [fen]        perft por lance da raiz (debug)
 */
#include "board.h"
#include "search.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static const char *game_status(Position *p)
{
    MoveList l;
    gen_legal(p, &l);
    if (l.count == 0) return in_check(p, p->side) ? "checkmate" : "stalemate";
    if (p->halfmove >= 100) return "fifty_move";
    if (repetition_count(p) >= 3) return "threefold";
    if (insufficient_material(p)) return "insufficient_material";
    return "ongoing";
}

/* reproduz os lances a partir da posição inicial, guardando a SAN de cada um */
static int replay(Position *p, int argc, char **argv, char san[][12])
{
    pos_from_fen(p, START_FEN);
    if (argc > MAX_HIST - MAX_PLY - 8) {
        printf("{\"error\":\"game too long\"}\n");
        return 0;
    }
    for (int i = 0; i < argc; i++) {
        int m = parse_uci(p, argv[i]);
        if (!m) {
            printf("{\"error\":\"illegal move\",\"index\":%d,\"move\":\"%.8s\"}\n", i, argv[i]);
            return 0;
        }
        if (san) move_to_san(p, m, san[i]);
        make_move(p, m);
    }
    return 1;
}

static void print_str_array(const char *name, char items[][12], int n)
{
    printf("\"%s\":[", name);
    for (int i = 0; i < n; i++) printf("%s\"%s\"", i ? "," : "", items[i]);
    printf("]");
}

static int cmd_state(int argc, char **argv)
{
    static Position pos;
    static char san[MAX_HIST][12];
    if (!replay(&pos, argc, argv, san)) return 2;

    char fen[128];
    pos_to_fen(&pos, fen);

    MoveList l;
    gen_legal(&pos, &l);

    printf("{\"fen\":\"%s\",\"turn\":\"%s\",\"check\":%s,\"status\":\"%s\",",
           fen, pos.side == WHITE ? "white" : "black",
           in_check(&pos, pos.side) ? "true" : "false", game_status(&pos));
    print_str_array("history_san", san, argc);
    printf(",\"legal\":[");
    for (int i = 0; i < l.count; i++) {
        char uci[6], s[12];
        move_to_uci(l.moves[i], uci);
        move_to_san(&pos, l.moves[i], s);
        printf("%s{\"uci\":\"%s\",\"san\":\"%s\"}", i ? "," : "", uci, s);
    }
    printf("]}\n");
    return 0;
}

static int cmd_think(int argc, char **argv)
{
    static Position pos;
    if (argc < 1) return 1;
    int time_ms = atoi(argv[0]);
    if (!replay(&pos, argc - 1, argv + 1, NULL)) return 2;

    search_init();
    SearchResult r = think(&pos, time_ms, MAX_PLY);
    if (!r.best_move) {
        printf("{\"error\":\"no legal moves\"}\n");
        return 2;
    }

    char uci[6], pv_san[MAX_PLY][12];
    move_to_uci(r.best_move, uci);

    /* SAN da PV: cada lance precisa da posição em que foi jogado */
    for (int i = 0; i < r.pv_len; i++) {
        move_to_san(&pos, r.pv[i], pv_san[i]);
        make_move(&pos, r.pv[i]);
    }
    for (int i = 0; i < r.pv_len; i++) unmake_move(&pos);

    int mate_in = 0;
    if (r.score > MATE - MAX_PLY) mate_in = (MATE - r.score + 1) / 2;
    if (r.score < -MATE + MAX_PLY) mate_in = -(MATE + r.score) / 2;

    long long nps = r.time_ms > 0 ? r.nodes * 1000 / r.time_ms : r.nodes;
    printf("{\"best\":\"%s\",\"san\":\"%s\",\"score\":%d,\"mate_in\":%d,\"depth\":%d,"
           "\"nodes\":%lld,\"time_ms\":%d,\"nps\":%lld,",
           uci, pv_san[0], r.score, mate_in, r.depth, r.nodes, r.time_ms, nps);
    print_str_array("pv_san", pv_san, r.pv_len);
    printf("}\n");
    return 0;
}

static int cmd_perft(int argc, char **argv, int divide)
{
    static Position pos;
    if (argc < 1) return 1;
    int depth = atoi(argv[0]);
    if (!pos_from_fen(&pos, argc > 1 ? argv[1] : START_FEN)) {
        fprintf(stderr, "FEN inválida\n");
        return 1;
    }

    clock_t t0 = clock();
    uint64_t total = 0;
    if (divide) {
        MoveList l;
        gen_legal(&pos, &l);
        for (int i = 0; i < l.count; i++) {
            char uci[6];
            make_move(&pos, l.moves[i]);
            uint64_t n = perft(&pos, depth - 1);
            unmake_move(&pos);
            move_to_uci(l.moves[i], uci);
            printf("%s: %llu\n", uci, (unsigned long long)n);
            total += n;
        }
    } else {
        total = perft(&pos, depth);
    }
    double secs = (double)(clock() - t0) / CLOCKS_PER_SEC;
    printf("%llu\n", (unsigned long long)total);
    fprintf(stderr, "perft(%d) = %llu em %.2fs\n", depth, (unsigned long long)total, secs);
    return 0;
}

int main(int argc, char **argv)
{
    board_init();
    if (argc < 2) {
        fprintf(stderr, "uso: %s state|think|perft|divide ...\n", argv[0]);
        return 1;
    }
    if (strcmp(argv[1], "state") == 0)  return cmd_state(argc - 2, argv + 2);
    if (strcmp(argv[1], "think") == 0)  return cmd_think(argc - 2, argv + 2);
    if (strcmp(argv[1], "perft") == 0)  return cmd_perft(argc - 2, argv + 2, 0);
    if (strcmp(argv[1], "divide") == 0) return cmd_perft(argc - 2, argv + 2, 1);
    fprintf(stderr, "comando desconhecido: %s\n", argv[1]);
    return 1;
}
