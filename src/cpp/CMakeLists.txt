cmake_minimum_required(VERSION 3.20)
project(agnetic_vector_index LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(pybind11 REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Development Interpreter)

pybind11_add_module(vector_index MODULE vector_index.cpp)
target_link_libraries(vector_index PRIVATE pybind11::headers Python3::Python)
target_compile_options(vector_index PRIVATE -O3 -march=native -ffast-math -fopenmp)
target_link_libraries(vector_index PRIVATE -fopenmp)
