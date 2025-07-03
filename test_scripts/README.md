# Integration Test Scripts

This directory contains a collection of handwritten Python scripts designed to test the `simple485-remastered` library in a real-world environment.

### Purpose

These are **integration tests**, not automated unit tests. Their purpose is to verify the entire communication stack by running the library on physical Master and Slave hardware (e.g., Raspberry Pis with RS485 transceivers) connected via a serial bus. They simulate how the library would be used in a real application.

### General Usage Instructions

All test suites follow a similar setup procedure:

1.  **Hardware Setup:** Connect your Master and Slave devices to the same RS485 bus.
2.  **Configure Serial Ports:** Each script contains a hardcoded serial port (e.g., `serial.Serial("COM9", ...)`). **You must edit this line** in both the master and slave scripts to match the port names on your respective systems.
3.  **Run the Slave Script First:** The slave script must be started first, as it will initialize and wait for messages from the master.
4.  **Run the Master Script:** Once the slave is running, execute the corresponding master script to begin the test.

> **Note on Imports:** All scripts use `sys.path.append(...)` to add the project's root directory to the Python path. This allows them to import the library from the `src/` directory directly.

---

### Available Test Suites

This collection includes the following tests:

*   **[Address Range Test](./address_range_test/README.md):** A fundamental connectivity test. The master "pings" every possible slave address in a range to ensure each one is reachable and responsive.
*   **[Storm Test](./storm_test/README.md):** A data integrity stress test. The master sends random payloads of varying lengths to slaves and verifies that the "echoed" response is a perfect match, testing the protocol's robustness.

For detailed instructions on a specific test, please see the `README.md` file within its respective directory.