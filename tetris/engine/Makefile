CC     ?= gcc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Wpedantic

SRC = game.c ai.c ga.c main.c
BIN = tetris

$(BIN): $(SRC) game.h ai.h ga.h
	$(CC) $(CFLAGS) -o $@ $(SRC) -lm

clean:
	rm -f $(BIN) $(BIN).exe

.PHONY: clean
