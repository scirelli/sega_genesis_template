TARGET          ?= main
IMAGE_NAME      := asm68k
DOCKERFILE      := .docker/asm68k_dockerfile
EMU             ?= mame genesis -cart
SRCDIR          := src
DISTDIR         := dist

# Auto-detect container runtime (prefer podman)
CONTAINER_RT    := $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)
ifeq ($(CONTAINER_RT),)
  $(error Neither podman nor docker found in PATH)
endif

# Assembler flags
ASM_FLAGS       := /p /ov+ /oos+ /oop+ /oow+ /ooz+ /ooaq+ /oosq+ /oomq+ /ow+

# Container paths & volumes
CONTAINER_APP   := /home/wineuser/app
VOLUMES         := --volume "$(CURDIR)/$(SRCDIR):$(CONTAINER_APP)/src" \
                   --volume "$(CURDIR)/$(DISTDIR):$(CONTAINER_APP)/dist"

# Container run (ENTRYPOINT is wine, so this executes: wine asm68k.exe ...)
RUN             = $(CONTAINER_RT) run --rm -t $(VOLUMES) $(IMAGE_NAME) asm68k.exe

# asm68k argument format: [options] source,binary,symbol
ASM_ARGS        = $(ASM_FLAGS) src/$(TARGET).s,dist/$(TARGET).bin,dist/$(TARGET).sym
ASM_ARGS_DEBUG  = $(ASM_FLAGS) src/$(TARGET).s,dist/$(TARGET).db.bin,dist/$(TARGET).db.sym

# ---------- Targets ----------

.PHONY: help all emu debug debugemu clean image

help: ## Show available targets
	@echo "Usage: make [target] [TARGET=<stem>]  (default TARGET=$(TARGET))"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

all: $(DISTDIR)/$(TARGET).bin ## Build ROM binary

emu: $(DISTDIR)/$(TARGET).bin ## Build and run in emulator
	$(EMU) $(DISTDIR)/$(TARGET).bin

$(DISTDIR)/$(TARGET).bin: $(SRCDIR)/$(TARGET).s | $(DISTDIR) image
	$(RUN) $(ASM_ARGS)

debug: $(DISTDIR)/$(TARGET).db.bin ## Build debug ROM with symbols

$(DISTDIR)/$(TARGET).db.bin: $(SRCDIR)/$(TARGET).s | $(DISTDIR) image
	$(RUN) $(ASM_ARGS_DEBUG)

debugemu: $(DISTDIR)/$(TARGET).db.bin ## Debug build + emulator debugger
	$(EMU) -debug $(DISTDIR)/$(TARGET).db.bin

image: ## Build container image if not present
	@if ! $(CONTAINER_RT) image inspect $(IMAGE_NAME) >/dev/null 2>&1; then \
		echo "Building container image '$(IMAGE_NAME)'..."; \
		$(CONTAINER_RT) build -t $(IMAGE_NAME) -f $(DOCKERFILE) .; \
	fi

clean: ## Remove build artifacts
	rm -f $(DISTDIR)/*

$(DISTDIR):
	mkdir -p $(DISTDIR)
