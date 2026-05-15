TARGET          ?= main
IMAGE_NAME      := asm68k
DOCKERFILE      := .docker/asm68k_dockerfile
EMU             ?= mame genesis -cart
SRCDIR          := src
DISTDIR         := dist
ASMDIR          := Assembler

# WINE_MODE: native | container | (empty = auto-detect)
# Override to bypass auto-detection:
#   make WINE_MODE=native    — use wine from PATH
#   make WINE_MODE=container — use the container
WINE_MODE       ?=

# Auto-detect: prefer native wine, fall back to container
ifeq ($(WINE_MODE),)
  ifneq ($(shell command -v wine 2>/dev/null),)
    _WINE_MODE := native
  else
    _WINE_MODE := container
  endif
else
  _WINE_MODE := $(WINE_MODE)
endif

# --- Container setup (only needed in container mode) ---
ifeq ($(_WINE_MODE),container)
  CONTAINER_RT  := $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)
  ifeq ($(CONTAINER_RT),)
    $(error Neither podman nor docker found in PATH — install one or set WINE_MODE=native)
  endif

  CONTAINER_APP := /home/wineuser/app
  VOLUMES       := --volume "$(CURDIR)/$(SRCDIR):$(CONTAINER_APP)/src" \
                   --volume "$(CURDIR)/$(DISTDIR):$(CONTAINER_APP)/dist"
  RUN           = $(CONTAINER_RT) run --rm -t $(VOLUMES) $(IMAGE_NAME) asm68k.exe
  _IMAGE_DEP    := image
else
  RUN           = cd $(CURDIR) && wine $(CURDIR)/$(ASMDIR)/asm68k.exe
  _IMAGE_DEP    :=
endif

# Assembler flags
ASM_FLAGS 		:= /p /j src/\* /ov+ /oos+ /oop+ /oow+ /ooz+ /ooaq+ /oosq+ /oomq+ /ow+

# asm68k argument format: [options] source,binary,symbol
ASM_ARGS        = $(ASM_FLAGS) src/$(TARGET).s,dist/$(TARGET).bin,dist/$(TARGET).sym
ASM_ARGS_DEBUG  = $(ASM_FLAGS) src/$(TARGET).s,dist/$(TARGET).db.bin,dist/$(TARGET).db.sym

# ---------- Targets ----------

.PHONY: help all emu debug debugemu clean image wine-info

help: ## Show available targets
	@echo "Usage: make [target] [TARGET=<stem>]  (default TARGET=$(TARGET))"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'
	@echo ""
	@echo "  WINE_MODE=$(_WINE_MODE) (override with WINE_MODE=native|container)"

all: $(DISTDIR)/$(TARGET).bin ## Build ROM binary

emu: $(DISTDIR)/$(TARGET).bin ## Build and run in emulator
	$(EMU) $(DISTDIR)/$(TARGET).bin

$(DISTDIR)/$(TARGET).bin: $(SRCDIR)/$(TARGET).s | $(DISTDIR) $(_IMAGE_DEP)
	$(RUN) $(ASM_ARGS)

debug: $(DISTDIR)/$(TARGET).db.bin ## Build debug ROM with symbols

$(DISTDIR)/$(TARGET).db.bin: $(SRCDIR)/$(TARGET).s | $(DISTDIR) $(_IMAGE_DEP)
	$(RUN) $(ASM_ARGS_DEBUG)

debugemu: $(DISTDIR)/$(TARGET).db.bin ## Debug build + emulator debugger
	$(EMU) -debug $(DISTDIR)/$(TARGET).db.bin

image: ## Build container image if not present
ifeq ($(_WINE_MODE),container)
	@if ! $(CONTAINER_RT) image inspect $(IMAGE_NAME) >/dev/null 2>&1; then \
		echo "Building container image '$(IMAGE_NAME)'..."; \
		$(CONTAINER_RT) build -t $(IMAGE_NAME) -f $(DOCKERFILE) .; \
	fi
else
	@echo "Skipping — using native wine (WINE_MODE=$(_WINE_MODE))"
endif

wine-info: ## Show detected wine mode and paths
	@echo "WINE_MODE=$(_WINE_MODE)"
ifeq ($(_WINE_MODE),container)
	@echo "CONTAINER_RT=$(CONTAINER_RT)"
	@echo "IMAGE_NAME=$(IMAGE_NAME)"
else
	@echo "WINE=$(shell command -v wine 2>/dev/null)"
	@echo "ASM68K=$(CURDIR)/$(ASMDIR)/asm68k.exe"
endif

clean: ## Remove build artifacts
	rm -f $(DISTDIR)/*

$(DISTDIR):
	mkdir -p $(DISTDIR)
