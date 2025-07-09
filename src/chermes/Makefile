# Compiler and flags
CXX = g++
CFLAGS = -Wall -O2
CXXFLAGS = $(CFLAGS) -std=c++17

# Directories
SRC_DIR = ./src
INC_DIR = ./inc
OBJ_DIR = ./obj
BIN_DIR = ./bin

# Include directories
CXXFLAGS += -I$(INC_DIR)

# Files
MAIN_SRC = tpx3SpidrUnpacker.cpp
TARGET = tpx3SpidrUnpacker
BIN_TARGET = $(BIN_DIR)/$(TARGET)

# Source files (excluding histgrams.cpp as in original Makefile)
LIB_SRCS = $(filter-out $(SRC_DIR)/histgrams.cpp, $(wildcard $(SRC_DIR)/*.cpp))
LIB_SRCS := $(filter-out $(SRC_DIR)/$(MAIN_SRC), $(LIB_SRCS))

# Object files
MAIN_OBJ = $(OBJ_DIR)/$(MAIN_SRC:.cpp=.o)
LIB_OBJS = $(LIB_SRCS:$(SRC_DIR)/%.cpp=$(OBJ_DIR)/%.o)
ALL_OBJS = $(MAIN_OBJ) $(LIB_OBJS)

# Header dependencies
DEPS = $(wildcard $(INC_DIR)/*.h)

# Default target
all: $(BIN_TARGET)

# Create necessary directories
$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

$(BIN_DIR):
	mkdir -p $(BIN_DIR)

# Link object files to create the binary and move to bin directory
$(BIN_TARGET): $(ALL_OBJS) | $(BIN_DIR)
	$(CXX) $(LDFLAGS) -o $@ $(ALL_OBJS)
	@echo "Binary created and moved to $(BIN_DIR)/$(TARGET)"

# Compile source files into object files
$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp $(DEPS) | $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) -c -o $@ $<

# Clean build artifacts
clean:
	rm -f $(OBJ_DIR)/*.o $(BIN_TARGET)
	@echo "Cleaned object files and binary"

# Install target (same as all for this case)
install: $(BIN_TARGET)

# Help target
help:
	@echo "Available targets:"
	@echo "  all      - Build the tpx3SpidrUnpacker binary (default)"
	@echo "  clean    - Remove object files and binary"
	@echo "  install  - Build and install the binary"
	@echo "  help     - Show this help message"
	@echo ""
	@echo "Binary will be created at: $(BIN_DIR)/$(TARGET)"

.PHONY: all clean install help
