# Makefile to convert .puml, .gnu, and .dot files to .png

# Directories
SRC_DIR := .
OUT_DIR := .

# Find all .puml, .gnu, and .dot files
PUML_FILES := $(wildcard $(SRC_DIR)/*.puml)
GNU_FILES := $(wildcard $(SRC_DIR)/*.gnu)
DOT_FILES := $(wildcard $(SRC_DIR)/*.dot)
MMD_FILES := $(wildcard $(SRC_DIR)/*.mmd)

# Generate output file names with suffixes to avoid conflicts
PUML_PNGS := $(PUML_FILES:$(SRC_DIR)/%.puml=$(OUT_DIR)/%-puml.png)
GNU_PNGS := $(GNU_FILES:$(SRC_DIR)/%.gnu=$(OUT_DIR)/%-gnu.png)
DOT_PNGS := $(DOT_FILES:$(SRC_DIR)/%.dot=$(OUT_DIR)/%-dot.png)
MMD_PNGS := $(MMD_FILES:$(SRC_DIR)/%.mmd=$(OUT_DIR)/%-mmd.png)

# Default target
all: $(PUML_PNGS) $(GNU_PNGS) $(DOT_PNGS) $(MMD_PNGS)

# Rule to convert .puml to .png
$(OUT_DIR)/%-puml.png: $(SRC_DIR)/%.puml
	plantuml -tpng -pipe < $< > $@

# Rule to convert .gnu to .png
$(OUT_DIR)/%-gnu.png: $(SRC_DIR)/%.gnu
	gnuplot -e "set terminal png; set output '$@'; load '$<'"

# Rule to convert .dot to .png
$(OUT_DIR)/%-dot.png: $(SRC_DIR)/%.dot
	dot -Tpng $< -o $@

# Rule to convert .mmd to .png
$(OUT_DIR)/%-mmd.png: $(SRC_DIR)/%.mmd
	mmdc -i $< -o $@

# Clean up generated files
clean:
	rm -f $(OUT_DIR)/*png

.PHONY: all clean

