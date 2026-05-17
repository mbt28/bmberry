CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -std=gnu11 -I..
LDFLAGS ?=

all: ibus_linux

ibus_linux: main_linux.c ../ibus_protocol.c ../ibus_protocol.h
	$(CC) $(CFLAGS) -o $@ main_linux.c ../ibus_protocol.c $(LDFLAGS)

clean:
	rm -f ibus_linux

.PHONY: all clean
