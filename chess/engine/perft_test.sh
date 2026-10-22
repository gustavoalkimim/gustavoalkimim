#!/usr/bin/env bash
# Compara o perft da engine com os valores de referência.
# Qualquer bug em roque, en passant, promoção ou cravada muda esses números.
set -u
BIN="${1:-./chess}"
fail=0

check() {
    local depth="$1" expected="$2" fen="$3"
    local got
    got=$("$BIN" perft "$depth" "$fen" 2>/dev/null | tail -n 1 | tr -d '\r')
    if [ "$got" = "$expected" ]; then
        echo "ok    perft($depth) = $got   $fen"
    else
        echo "FALHA perft($depth) = $got (esperado $expected)   $fen"
        fail=1
    fi
}

check 5 4865609 "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
check 4 4085603 "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
check 5 674624  "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
check 4 422333  "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"
check 4 2103487 "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"
check 4 3894594 "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10"

exit $fail
