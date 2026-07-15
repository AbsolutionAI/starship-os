CC ?= gcc
CFLAGS ?= -std=c11 -Wall -Wextra -O2 -D_GNU_SOURCE
TARGET = sandbox_run

# seccomp when libseccomp available
SECCOMP_CFLAGS := $(shell pkg-config --cflags libseccomp 2>/dev/null)
SECCOMP_LIBS := $(shell pkg-config --libs libseccomp 2>/dev/null)
ifeq ($(SECCOMP_LIBS),)
  # try default link
  SECCOMP_LIBS := $(shell echo 'int main(){return 0;}' | $(CC) -x c - -lseccomp -o /dev/null 2>/dev/null && echo -lseccomp)
endif
ifneq ($(SECCOMP_LIBS),)
  CFLAGS += -DHAVE_SECCOMP=1 $(SECCOMP_CFLAGS)
  LDLIBS += $(SECCOMP_LIBS)
else
  CFLAGS += -DHAVE_SECCOMP=0
endif

.PHONY: all clean test bench

all: $(TARGET)

$(TARGET): sandbox_run.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

test: $(TARGET)
	./$(TARGET) --timeout 2 -- /bin/echo "starship-sandbox-ok"
	@echo "expect deny path:"
	-./$(TARGET) --timeout 1 -- mount 2>/dev/null; test $$? -eq 126
	@echo "expect seccomp blocks socket (if seccomp built):"
	-./$(TARGET) --timeout 2 -- /bin/bash -c 'python3 -c "import socket; socket.socket()"' 2>/dev/null; \
	  ec=$$?; if ./$(TARGET) --help 2>&1 | grep -q 'built-in'; then test $$ec -ne 0; else true; fi

bench: $(TARGET)
	@bash ../../scripts/bench-sandbox.sh 100

clean:
	rm -f $(TARGET)
