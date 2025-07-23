# Simple 485 Remastered

_A modern, rewritten, and enhanced version of the original [Simple485](https://github.com/rzeman9/Simple485) and [pySimple485](https://github.com/rzeman9/pySimple485) libraries._

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modern, robust, and easy-to-use Python library for Master-Slave communication over an RS485 serial bus.

This library provides a high-level API to handle the complexities of RS485 communication, including packet framing, error checking, message retries, and transceiver direction control, allowing you to focus on your application's logic.

## Project Background

This project is a complete, from-scratch rewrite inspired by the foundational work of **[rzeman9](https://github.com/rzeman9)** on [Simple485](https://github.com/rzeman9/Simple485) (for C++) and [pySimple485](https://github.com/rzeman9/pySimple485).

The goal of this "remastered" version is to build upon the original concepts with a focus on:
-   **Modern Python Features:** Utilizing modern language features and a fully type-hinted codebase.
-   **Simplified Threading:** Providing a clear, easy-to-use threaded API for synchronous, blocking communication.
-   **Testability:** A comprehensive suite of automated unit tests and hardware integration scripts.
-   **Extensive Documentation:** Including detailed API documentation, usage examples, and test guides.

Full credit goes to the original author for the protocol design and initial implementation that inspired this library.

## Key Features

-   **Clear Master/Slave Architecture:** A simple and powerful model where a Master node initiates requests and Slave nodes respond.
-   **Simple Threaded Interface:** The `ThreadedMaster` class provides a user-friendly, synchronous (blocking) API. It runs all the complex I/O in a background thread, so you can just call a method and get a response.
-   **Automatic Retries and Timeouts:** The master automatically handles unresponsive slaves by retrying requests a configurable number of times before timing out.
-   **Robust Packet Protocol:** Uses a CRC checksum for data integrity and a well-defined packet structure with byte-stuffing to prevent framing errors.
-   **GPIO Transceiver Control:** Built-in support for automatically controlling the `DE/RE` pins on common RS485 transceivers via Raspberry Pi GPIO.
-   **Well-Documented and Tested:** A complete suite of documentation, unit tests, and real-world hardware test scripts.

## Installation

This project uses `uv` for fast, modern package management.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/simple-485-remastered.git
    cd simple-485-remastered
    ```

2.  **Install `uv`:**
    If you don't have `uv` installed, you can get it via `pip`:
    ```bash
    pip install uv
    ```

3.  **Create and activate a virtual environment:**
    ```bash
    uv venv
    source .venv/bin/activate
    ```
    *(On Windows, use `.venv\Scripts\activate`)*

4.  **Sync dependencies:**
    This command reads the `uv.lock` or `requirements.lock` file and installs the exact versions of all dependencies into your virtual environment.
    ```bash
    uv pip sync
    ```
    > **Note on Raspberry Pi:** For use with GPIO control, ensure `RPi.GPIO` is included in your project's dependencies before the lock file is generated.

## Core Concepts

The library is built on a few key ideas:

-   **Master/Slave Roles:** The **Master** is the only node that can initiate a conversation. It sends a `Request` to a specific **Slave**. The Slave listens for requests, processes them, and sends back a `Response`.
-   **`ThreadedMaster` (Recommended Approach):** This is the easiest way to use the library. You instantiate it, start its `run_loop()` in a background thread, and then your main application thread can make simple, blocking calls to communicate with slaves.
-   **`Master` & `Slave` (Advanced Approach):** For more complex applications (e.g., integration into an existing `asyncio` event loop), you can use the base `Master` and `Slave` classes and manage the I/O loop yourself.

## Testing

The project contains two distinct test suites, each with a different purpose.

### Automated Tests (`/tests`)

These are unit and integration tests designed for a hardware-free environment. They use `pytest` and extensive mocking to verify the library's internal logic. They are fast, fully automated, and ideal for CI/CD pipelines.

-   **To Run:** From the project root, execute:
    ```bash
    pytest
    ```
-   **Details:** See [`tests/README.md`](./tests/README.md) for more information on the test design and philosophy.

### Manual Hardware Tests (`/test_scripts`)

These scripts are designed to test the library's performance and robustness on real hardware. They are essential for verifying behavior in a real-world environment with physical RS485 transceivers and wiring.

-   **To Run:**
    1.  Edit the serial port names (e.g., `"COM9"`) inside the chosen master and slave scripts.
    2.  On the slave device, start the slave script.
    3.  On the master device, start the master script.
-   **Details:** See [`test_scripts/README.md`](./test_scripts/README.md) for a breakdown of the available hardware tests.

## API at a Glance

The library's public API is focused on a few key components:

-   **`ThreadedMaster`**: The recommended, thread-safe, synchronous Master class for most applications.
-   **`Slave`**: The abstract base class for creating all slave devices. You must subclass it and implement `_handle_unicast_message`.
-   **`Master`**: The advanced, non-threaded base class for custom Master implementations (e.g., for `asyncio` integration).
-   **`Response`**: A simple data object that summarizes the result of a request, including success status, payload, and timing.
-   **`RequestException`**: The primary exception to catch for handling failed requests, such as timeouts or invalid responses.

## Contributing

Contributions are welcome! If you find a bug or have a feature request, please open an issue. If you'd like to contribute code, please feel free to fork the repository and submit a pull request.

## License

This project is licensed under the MIT License—see the [LICENSE](LICENSE) file for details.

## Acknowledgements
This project is inspired by the original work of [rzeman9](https://github.com/rzeman9)