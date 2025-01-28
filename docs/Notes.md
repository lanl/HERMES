# HERMES: TPX3Cam Data Acquisition & Analysis

HERMES is a software framework designed for **facilitating the acquisition and analysis of TPX3Cam data**. It consists of **C++** modules for data unpacking and analysis, as well as **Python** scripts for data acquisition and interfacing with commercial tools.

## 📂 Project Structure

```
HERMES/
├── src/
│   ├── cpp/                 # C++ codebase for unpacking & analysis
│   │   ├── include/         # Header files (.h)
│   │   ├── unpackers/       # C++ TPX3Cam data unpackers
│   │   ├── analyzers/       # C++ data analyzers
│   │   ├── utils/           # Common C++ utilities
│   │   ├── main.cpp         # (Optional) Main entry for standalone execution
│   │   ├── CMakeLists.txt   # Build instructions (modern approach over Makefile)
│   ├── python/              # Python-based acquisition, analysis, and wrappers
│   │   ├── acquisition/     # Data acquisition scripts
│   │   ├── wrappers/        # Python interfaces for C++ and commercial tools
│   │   ├── analysis/        # Python-based analysis scripts
│   │   ├── utils/           # Shared Python utilities (logging, config parsing, etc.)
│   │   ├── __init__.py      # Makes this a package
│   │   ├── main.py          # Main script for Python execution
│   ├── shared/              # Code and data shared between C++ and Python
│   │   ├── data/            # Shared data files
│   │   ├── config/          # Common configuration files (YAML, JSON, etc.)
│   │   ├── constants/       # Shared constants (error codes, settings)
│   │   ├── bindings/        # C++/Python bindings (ctypes, pybind11, etc.)
│   │   ├── utils/           # Cross-language utilities (e.g., C++ helper scripts, JSON parsers)
│
├── tests/                   # Unit and integration tests
│   ├── cpp/                 # C++ tests
│   ├── python/              # Python tests
│
├── examples/                # Example scripts for users
│   ├── example_acquire.py   # Example acquisition script
│   ├── example_unpack.cpp   # Example unpacking script
│
├── docs/                    # Documentation
│   ├── API.md               # API documentation
│   ├── Setup.md             # Installation & setup guide
│   ├── Usage.md             # How to use the software
│
├── scripts/                 # Build, deployment, and automation scripts
│   ├── build.sh             # Build automation script
│   ├── deploy.sh            # Deployment script
│
├── CMakeLists.txt           # Root CMake file for building C++ code
├── requirements.txt         # Python dependencies
├── setup.py                 # Python packaging setup (if applicable)
├── LICENSE
└── README.md
```

## 🛠 Build & Installation

### **Building C++ Code**
```sh
cd HERMES/src/cpp
mkdir build && cd build
cmake ..
make
```

### **Installing Python Dependencies**
```sh
pip install -r requirements.txt
```

## 🚀 Usage

### **Running Python Acquisition**
```sh
python3 src/python/acquisition/tpx3cam_acquire.py --config shared/config/settings.yaml
```

### **Using Python Wrapper for C++ Unpacker**
```python
from hermes.wrappers import unpacker
data = unpacker.load_tpx3_data("data.bin")
```

## ✅ Testing

### **Running Python Tests**
```sh
pytest tests/python
```

### **Running C++ Tests**
```sh
cd HERMES/src/cpp/build
make test
```

## 🔗 Integration: Python & C++

- Use **`pybind11`**, **`ctypes`**, or **`cffi`** for interfacing between Python and C++.
- Shared constants and configuration files should be stored in `shared/config/`.
- Example configuration file (`shared/config/settings.yaml`):
  ```yaml
  acquisition_rate: 60
  output_directory: "/data"
  ```

## 📝 Documentation

- **[API Documentation](docs/API.md)**
- **[Installation & Setup](docs/Setup.md)**
- **[Usage Guide](docs/Usage.md)**

## 📜 License

This project is licensed under the **MIT License**.

---

🚀 *HERMES is designed for high-performance TPX3Cam data handling. Contributions are welcome!*

