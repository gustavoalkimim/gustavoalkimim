CC     ?= gcc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Wpedantic

SRC = board.c search.c main.c
BIN = chess

$(BIN): $(SRC) board.h search.h
	$(CC) $(CFLAGS) -o $@ $(SRC)

# valida o gerador de lances contra contagens conhecidas (chessprogramming.org/Perft_Results)
test: $(BIN)
	bash perft_test.sh ./$(BIN)

clean:
	rm -f $(BIN) $(BIN).exe

.PHONY: test clean
