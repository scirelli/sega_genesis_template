TARGET          ?= main
IMAGE_NAME      := asm68k
DOCKERFILE      := .docker/asm68k_dockerfile
EMU             ?= mame genesis -cart
SRCDIR          := src
DISTDIR         := dist
DEBUGDIR        := debug
ASMDIR          := Assembler

# Load saved assembler preference
-include .make_config

# Backward compat: map old WINE_MODE values to ASM_MODE
ifdef WINE_MODE
  ifndef ASM_MODE
    ifeq ($(WINE_MODE),native)
      ASM_MODE := wine
    else
      ASM_MODE := $(WINE_MODE)
    endif
  endif
endif

# ASM_MODE: vasm | wine | container | (empty = auto-detect)
ASM_MODE        ?=

# Auto-detect assembler
ifeq ($(ASM_MODE),)
  ifneq ($(or $(shell command -v vasmm68k_mot 2>/dev/null),$(wildcard $(ASMDIR)/vasmm68k_mot)),)
    _ASM_MODE := vasm
  else ifneq ($(shell command -v wine 2>/dev/null),)
    _ASM_MODE := wine
  else ifneq ($(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null),)
    _ASM_MODE := container
  else
    _ASM_MODE := vasm
  endif
else
  _ASM_MODE := $(ASM_MODE)
endif

# --- vasm setup ---
ifeq ($(_ASM_MODE),vasm)
  VASM := $(or $(shell command -v vasmm68k_mot 2>/dev/null),$(ASMDIR)/vasmm68k_mot)
  VASM_FLAGS := -Fbin -m68000 -opt-allbra -opt-speed -opt-lsl -opt-pea -opt-movem -I $(SRCDIR)/
  RUN = $(VASM)
  ASM_ARGS = $(VASM_FLAGS) -o $(DISTDIR)/$(TARGET).bin -L $(DISTDIR)/$(TARGET).lst $(SRCDIR)/$(TARGET).s
  ASM_ARGS_DEBUG = $(VASM_FLAGS) -o $(DEBUGDIR)/$(TARGET).db.bin -L $(DEBUGDIR)/$(TARGET).db.lst $(SRCDIR)/$(TARGET).s
  _IMAGE_DEP :=
  _VASM_DEP := $(VASM)
endif

# --- wine (native) setup ---
ifeq ($(_ASM_MODE),wine)
  ifneq ($(shell command -v wine 2>/dev/null),)
    RUN = cd $(CURDIR) && wine $(CURDIR)/$(ASMDIR)/asm68k.exe
  else
    $(error wine not found in PATH — install wine or use: make ASM_MODE=vasm)
  endif
  ASM_FLAGS := /p /j src/\* /ov+ /oos+ /oop+ /oow+ /ooz+ /ooaq+ /oosq+ /oomq+ /ow+
  ASM_ARGS = $(ASM_FLAGS) src/$(TARGET).s,dist/$(TARGET).bin,dist/$(TARGET).sym
  ASM_ARGS_DEBUG = $(ASM_FLAGS) src/$(TARGET).s,debug/$(TARGET).db.bin,debug/$(TARGET).db.sym
  _IMAGE_DEP :=
  _VASM_DEP :=
endif

# --- container setup ---
ifeq ($(_ASM_MODE),container)
  CONTAINER_RT  := $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)
  ifeq ($(CONTAINER_RT),)
    $(error Neither podman nor docker found in PATH — install one or set ASM_MODE=vasm)
  endif

  CONTAINER_APP := /home/wineuser/app
  VOLUMES       := --volume "$(CURDIR)/$(SRCDIR):$(CONTAINER_APP)/src" \
                   --volume "$(CURDIR)/$(DISTDIR):$(CONTAINER_APP)/dist" \
                   --volume "$(CURDIR)/$(DEBUGDIR):$(CONTAINER_APP)/debug"
  RUN           = $(CONTAINER_RT) run --rm -t $(VOLUMES) $(IMAGE_NAME) asm68k.exe
  ASM_FLAGS     := /p /j src/\* /ov+ /oos+ /oop+ /oow+ /ooz+ /ooaq+ /oosq+ /oomq+ /ow+
  ASM_ARGS      = $(ASM_FLAGS) src/$(TARGET).s,dist/$(TARGET).bin,dist/$(TARGET).sym
  ASM_ARGS_DEBUG = $(ASM_FLAGS) src/$(TARGET).s,debug/$(TARGET).db.bin,debug/$(TARGET).db.sym
  _IMAGE_DEP    := image
  _VASM_DEP     :=
endif

# ---------- vasm download/build ----------

VASM_URL := http://sun.hasenbraten.de/vasm/release/vasm.tar.gz

$(ASMDIR)/vasmm68k_mot:
	@echo "=== Downloading vasm source ==="
	curl -L $(VASM_URL) | tar xz -C $(ASMDIR)
	@echo "=== Building vasmm68k_mot ==="
	$(MAKE) -C $(ASMDIR)/vasm CPU=m68k SYNTAX=mot
	cp $(ASMDIR)/vasm/vasmm68k_mot $(ASMDIR)/vasmm68k_mot
	@echo "=== vasm ready: $(ASMDIR)/vasmm68k_mot ==="

# ---------- Targets ----------

.PHONY: help all emu debug debugemu clean image setup setup-vasm asm-info convert

help: ## Show available targets
	@echo "Usage: make [target] [TARGET=<stem>]  (default TARGET=$(TARGET)) [ASM_MODE=<vasm | wine | container>] (default ASM_MODE=auto-detect)"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'
	@echo ""
	@echo "  ASM_MODE=$(_ASM_MODE) (override with ASM_MODE=vasm|wine|container)"

all: $(DISTDIR)/$(TARGET).bin ## Build ROM binary

emu: $(DISTDIR)/$(TARGET).bin ## Build and run in emulator
	$(EMU) $(DISTDIR)/$(TARGET).bin -cfg_directory $(DISTDIR)/cfg -nvram_directory $(DISTDIR)/nvram -snapshot_directory $(DISTDIR)/snap

$(DISTDIR)/$(TARGET).bin: $(SRCDIR)/$(TARGET).s | $(DISTDIR) $(_IMAGE_DEP) $(_VASM_DEP)
	$(RUN) $(ASM_ARGS)

debug: $(DEBUGDIR)/$(TARGET).db.bin ## Build debug ROM with symbols

$(DEBUGDIR)/$(TARGET).db.bin: $(SRCDIR)/$(TARGET).s | $(DEBUGDIR) $(_IMAGE_DEP) $(_VASM_DEP)
	$(RUN) $(ASM_ARGS_DEBUG)

debugemu: $(DEBUGDIR)/$(TARGET).db.bin ## Debug build + emulator debugger
	$(EMU) $(DEBUGDIR)/$(TARGET).db.bin -debug -cfg_directory $(DEBUGDIR)/cfg -nvram_directory $(DEBUGDIR)/nvram -snapshot_directory $(DEBUGDIR)/snap

image: ## Build container image if not present
ifeq ($(_ASM_MODE),container)
	@if ! $(CONTAINER_RT) image inspect $(IMAGE_NAME) >/dev/null 2>&1; then \
		echo "Building container image '$(IMAGE_NAME)'..."; \
		$(CONTAINER_RT) build -t $(IMAGE_NAME) -f $(DOCKERFILE) .; \
	fi
else
	@echo "Skipping — not using container mode (ASM_MODE=$(_ASM_MODE))"
endif

setup: ## Interactive assembler selection (saved to .make_config)
	@echo "Select assembler mode:"
	@echo "  1) vasm      — vasmm68k_mot (native, no wine needed)"
	@echo "  2) wine      — wine + asm68k.exe (requires wine in PATH)"
	@echo "  3) container — Docker/Podman + wine + asm68k.exe"
	@printf "Choice [1-3]: "; \
	read c; \
	case $$c in \
	  1) echo "ASM_MODE=vasm" > .make_config ;; \
	  2) echo "ASM_MODE=wine" > .make_config ;; \
	  3) echo "ASM_MODE=container" > .make_config ;; \
	  *) echo "Invalid choice"; exit 1 ;; \
	esac
	@echo "Saved to .make_config"

setup-vasm: $(ASMDIR)/vasmm68k_mot ## Download and build vasm from source

asm-info: ## Show detected assembler mode and paths
	@echo "ASM_MODE=$(_ASM_MODE)"
ifeq ($(_ASM_MODE),vasm)
	@echo "VASM=$(VASM)"
else ifeq ($(_ASM_MODE),wine)
	@echo "WINE=$(shell command -v wine 2>/dev/null)"
	@echo "ASM68K=$(CURDIR)/$(ASMDIR)/asm68k.exe"
else ifeq ($(_ASM_MODE),container)
	@echo "CONTAINER_RT=$(CONTAINER_RT)"
	@echo "IMAGE_NAME=$(IMAGE_NAME)"
endif

convert: ## Convert asm68k source files to vasm syntax
	python3 tools/asm68k_to_vasm.py $(SRCDIR)/ -o $(SRCDIR)/

clean: ## Remove build artifacts
	rm -f $(DISTDIR)/*
	rm -rf $(DEBUGDIR)

$(DISTDIR):
	mkdir -p $(DISTDIR)

$(DEBUGDIR):
	mkdir -p $(DEBUGDIR)
